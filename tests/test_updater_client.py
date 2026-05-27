"""Testy pro app.updater.client.apply_update — chování per platforma + delay wrapper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.updater import client as updater_client


@pytest.fixture
def fake_installer(tmp_path: Path) -> Path:
    path = tmp_path / "HlasDoTextu-Setup-0.2.1.exe"
    path.write_bytes(b"\x4d\x5a\x00")
    return path


def test_apply_update_missing_file(tmp_path: Path) -> None:
    bogus = tmp_path / "does_not_exist.exe"
    with pytest.raises(FileNotFoundError):
        updater_client.apply_update(bogus)


def test_apply_update_windows_uses_shellexecute_with_bat(fake_installer: Path) -> None:
    """Primární cesta: ShellExecuteW spustí .bat wrapper (s ping delayem)."""
    with (
        patch.object(updater_client.sys, "platform", "win32"),
        patch.object(updater_client, "_shellexecute", return_value=True) as shell_exec,
        patch.object(updater_client.subprocess, "Popen") as popen,
        patch.object(updater_client, "_request_app_quit") as quit_app,
    ):
        updater_client.apply_update(fake_installer)

    # ShellExecuteW se zavolal, fallback Popen ne
    shell_exec.assert_called_once()
    popen.assert_not_called()
    quit_app.assert_called_once()

    # ShellExecuteW dostal cestu k .bat wrapperu (s ping delayem, ne timeout!)
    target_arg = shell_exec.call_args[0][0]
    assert target_arg.endswith(".bat")
    # Ověříme obsah .bat — ping delay, ne timeout (ten padá bez konzole)
    bat = fake_installer.with_name("hdt_update_launch.bat")
    content = bat.read_text(encoding="ascii")
    assert "ping" in content
    assert "timeout" not in content
    assert "/SILENT" in content


def test_apply_update_windows_falls_back_to_popen_without_breakaway(fake_installer: Path) -> None:
    """Když ShellExecuteW selže, fallback na Popen BEZ breakaway flagu
    (breakaway byl příčina 'Access denied' na reálném Windows)."""
    with (
        patch.object(updater_client.sys, "platform", "win32"),
        patch.object(updater_client, "_shellexecute", return_value=False),
        patch.object(updater_client.subprocess, "Popen") as popen,
        patch.object(updater_client, "_request_app_quit") as quit_app,
    ):
        updater_client.apply_update(fake_installer)

    popen.assert_called_once()
    _, kwargs = popen.call_args
    flags = kwargs["creationflags"]
    CREATE_BREAKAWAY_FROM_JOB = 0x01000000
    DETACHED_PROCESS = 0x00000008
    # KLÍČOVÉ: breakaway flag UŽ NESMÍ být (padal na Access denied)
    assert not (flags & CREATE_BREAKAWAY_FROM_JOB)
    assert flags & DETACHED_PROCESS
    quit_app.assert_called_once()


def test_apply_update_windows_both_paths_fail_raises(fake_installer: Path) -> None:
    with (
        patch.object(updater_client.sys, "platform", "win32"),
        patch.object(updater_client, "_shellexecute", return_value=False),
        patch.object(
            updater_client.subprocess, "Popen",
            side_effect=OSError("[WinError 740] Vyžaduje elevation"),
        ),
        patch.object(updater_client, "_request_app_quit") as quit_app,
    ):
        with pytest.raises(RuntimeError) as excinfo:
            updater_client.apply_update(fake_installer)

    assert "ručně" in str(excinfo.value)
    quit_app.assert_not_called()


def test_apply_update_macos_opens_dmg(tmp_path: Path) -> None:
    dmg = tmp_path / "HlasDoTextu-Setup-0.2.1.dmg"
    dmg.write_bytes(b"DMG")

    with (
        patch.object(updater_client.sys, "platform", "darwin"),
        patch.object(updater_client.subprocess, "Popen") as popen,
        patch.object(updater_client, "_request_app_quit") as quit_app,
    ):
        updater_client.apply_update(dmg)

    popen.assert_called_once()
    args, kwargs = popen.call_args
    assert args[0] == ["open", str(dmg)]
    # macOS NESMÍ ukončit aplikaci automaticky — uživatel musí stihnout
    # přetáhnout novou verzi z DMG do Aplikací.
    quit_app.assert_not_called()


def test_apply_update_linux_is_noop(fake_installer: Path) -> None:
    with (
        patch.object(updater_client.sys, "platform", "linux"),
        patch.object(updater_client.subprocess, "Popen") as popen,
        patch.object(updater_client, "_request_app_quit") as quit_app,
    ):
        updater_client.apply_update(fake_installer)

    popen.assert_not_called()
    quit_app.assert_not_called()


def test_cleanup_old_installers_removes_other_versions(tmp_path: Path) -> None:
    """_cleanup_old_installers smaže staré verze, ponechá aktuální."""
    with patch.object(updater_client, "TEMP_DIR", tmp_path):
        # Staré verze + aktuální + .part
        (tmp_path / "HlasDoTextu-Setup-0.3.0.exe").write_bytes(b"old")
        (tmp_path / "HlasDoTextu-Setup-0.3.1.exe").write_bytes(b"old")
        (tmp_path / "HlasDoTextu-Setup-0.4.0.exe").write_bytes(b"current")
        (tmp_path / "HlasDoTextu-Setup-0.4.0.exe.part").write_bytes(b"partial")

        updater_client._cleanup_old_installers(keep_version="0.4.0")

        remaining = {p.name for p in tmp_path.iterdir()}
        assert "HlasDoTextu-Setup-0.3.0.exe" not in remaining
        assert "HlasDoTextu-Setup-0.3.1.exe" not in remaining
        assert "HlasDoTextu-Setup-0.4.0.exe" in remaining  # aktuální zůstane
        assert "HlasDoTextu-Setup-0.4.0.exe.part" in remaining  # retry téže verze


def test_download_verifies_size_and_uses_atomic_rename(tmp_path: Path) -> None:
    """Neúplný download (downloaded != Content-Length) musí selhat a nenechat
    finální soubor — jen smazaný .part."""
    info = updater_client.UpdateInfo(
        version="0.4.0",
        tag_name="v0.4.0",
        download_url="https://example.com/x.exe",
        download_size_bytes=1000,
        release_notes="",
        is_newer_than_current=True,
    )

    # Mock httpx.stream context manager — vrátí jen 500 B z deklarovaných 1000
    class _FakeResponse:
        headers = {"Content-Length": "1000"}

        def raise_for_status(self):
            return None

        def iter_bytes(self, chunk_size=0):
            yield b"x" * 500  # jen půlka

    class _FakeStream:
        def __enter__(self):
            return _FakeResponse()

        def __exit__(self, *a):
            return False

    with (
        patch.object(updater_client, "TEMP_DIR", tmp_path),
        patch.object(updater_client.httpx, "stream", return_value=_FakeStream()),
        patch.object(updater_client.shutil, "disk_usage") as disk,
    ):
        disk.return_value = type("U", (), {"free": 10**9})()
        with pytest.raises(RuntimeError, match="Neúplné stažení"):
            updater_client.download_installer(info)

    # Finální soubor NESMÍ existovat, .part má být uklizený
    assert not (tmp_path / "HlasDoTextu-Setup-0.4.0.exe").exists()
    assert not (tmp_path / "HlasDoTextu-Setup-0.4.0.exe.part").exists()


def test_download_aborts_when_disk_full(tmp_path: Path) -> None:
    """Málo místa na disku → RuntimeError ještě před stahováním."""
    info = updater_client.UpdateInfo(
        version="0.4.0",
        tag_name="v0.4.0",
        download_url="https://example.com/x.exe",
        download_size_bytes=200 * 1024 * 1024,  # 200 MB
        release_notes="",
        is_newer_than_current=True,
    )
    with (
        patch.object(updater_client, "TEMP_DIR", tmp_path),
        patch.object(updater_client.shutil, "disk_usage") as disk,
    ):
        disk.return_value = type("U", (), {"free": 50 * 1024 * 1024})()  # jen 50 MB
        with pytest.raises(RuntimeError, match="Málo místa"):
            updater_client.download_installer(info)


def test_installer_extension_per_platform() -> None:
    with patch.object(updater_client.sys, "platform", "darwin"):
        assert updater_client._installer_extension() == ".dmg"
    with patch.object(updater_client.sys, "platform", "win32"):
        assert updater_client._installer_extension() == ".exe"
    with patch.object(updater_client.sys, "platform", "linux"):
        assert updater_client._installer_extension() == ".exe"
