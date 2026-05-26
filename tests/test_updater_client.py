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


def test_apply_update_windows_launches_delayed_cmd_wrapper(fake_installer: Path) -> None:
    with (
        patch.object(updater_client.sys, "platform", "win32"),
        patch.object(updater_client.subprocess, "Popen") as popen,
        patch.object(updater_client, "_request_app_quit") as quit_app,
    ):
        updater_client.apply_update(fake_installer)

    popen.assert_called_once()
    args, kwargs = popen.call_args
    cmd = args[0]
    assert cmd[0] == "cmd.exe"
    assert cmd[1] == "/c"
    shell_str = cmd[2]
    assert "timeout /t 3" in shell_str
    assert "/SILENT" in shell_str
    assert "/SUPPRESSMSGBOXES" in shell_str
    assert str(fake_installer) in shell_str
    # start "" musí předcházet cestě, jinak start interpretuje cestu jako title.
    assert 'start ""' in shell_str

    flags = kwargs["creationflags"]
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_BREAKAWAY_FROM_JOB = 0x01000000
    assert flags & DETACHED_PROCESS
    assert flags & CREATE_NEW_PROCESS_GROUP
    assert flags & CREATE_BREAKAWAY_FROM_JOB

    assert kwargs["close_fds"] is True
    quit_app.assert_called_once()


def test_apply_update_windows_popen_failure_raises_runtime_error(fake_installer: Path) -> None:
    with (
        patch.object(updater_client.sys, "platform", "win32"),
        patch.object(
            updater_client.subprocess,
            "Popen",
            side_effect=OSError("[WinError 740] Vyžaduje elevation"),
        ),
        patch.object(updater_client, "_request_app_quit") as quit_app,
    ):
        with pytest.raises(RuntimeError) as excinfo:
            updater_client.apply_update(fake_installer)

    assert "ručně" in str(excinfo.value)
    assert str(fake_installer) in str(excinfo.value)
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
    quit_app.assert_called_once()


def test_apply_update_linux_is_noop(fake_installer: Path) -> None:
    with (
        patch.object(updater_client.sys, "platform", "linux"),
        patch.object(updater_client.subprocess, "Popen") as popen,
        patch.object(updater_client, "_request_app_quit") as quit_app,
    ):
        updater_client.apply_update(fake_installer)

    popen.assert_not_called()
    quit_app.assert_not_called()


def test_installer_extension_per_platform() -> None:
    with patch.object(updater_client.sys, "platform", "darwin"):
        assert updater_client._installer_extension() == ".dmg"
    with patch.object(updater_client.sys, "platform", "win32"):
        assert updater_client._installer_extension() == ".exe"
    with patch.object(updater_client.sys, "platform", "linux"):
        assert updater_client._installer_extension() == ".exe"
