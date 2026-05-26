"""GitHub Releases klient pro auto-update.

Implementace:
- check_for_update() — GET https://api.github.com/repos/{owner}/{repo}/releases/latest
- download_installer() — stáhne `.exe` (Windows) nebo `.dmg` (macOS) asset s progress
- apply_update() — spustí installer a ukončí aplikaci

Bez authentication (read-only public repo). Network errors jsou tiše ošetřeny
(žádný update prostě znamená "ticho", uživatel není rušen kdyby byl bez internetu).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
from loguru import logger

from app import __version__
from app.config import GITHUB_OWNER, GITHUB_REPO, TEMP_DIR, ensure_dirs


@dataclass(slots=True)
class UpdateInfo:
    """Info o dostupné novější verzi."""

    version: str            # např. "0.2.0" (bez "v" prefixu)
    tag_name: str           # např. "v0.2.0"
    download_url: str       # přímý link na .exe asset
    download_size_bytes: int
    release_notes: str      # markdown z GitHub release body
    is_newer_than_current: bool


def _installer_extension() -> str:
    """Vrátí příponu installeru podle aktuální platformy."""
    if sys.platform == "darwin":
        return ".dmg"
    return ".exe"


def _parse_version(s: str) -> tuple[int, ...]:
    """Vrátí (major, minor, patch) tuple pro porovnání verzí."""
    s = s.lstrip("vV").strip()
    parts = re.split(r"[.+-]", s)
    out: list[int] = []
    for p in parts[:3]:
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)


def check_for_update(timeout: float = 10.0) -> UpdateInfo | None:
    """Zkontroluje GitHub Releases na novější verzi.

    Vrací None pokud:
    - nedostupný internet / GitHub
    - žádný release ještě nepublikovaný
    - server vrátil error
    - není novější než current __version__
    - nemá .exe asset (např. release-in-progress)
    """
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    try:
        response = httpx.get(url, timeout=timeout, headers={"Accept": "application/vnd.github+json"})
    except httpx.RequestError as exc:
        logger.info("Update check: nedostupný (network): {}", exc)
        return None

    if response.status_code == 404:
        logger.info("Update check: zatím žádný release v {}/{}", GITHUB_OWNER, GITHUB_REPO)
        return None
    if response.status_code >= 400:
        logger.warning("Update check: GitHub API {} → {}", response.status_code, response.text[:200])
        return None

    try:
        data = response.json()
    except ValueError as exc:
        logger.warning("Update check: nevalidní JSON odpověď: {}", exc)
        return None

    tag = data.get("tag_name", "")
    if not tag:
        return None
    remote_ver = _parse_version(tag)
    local_ver = _parse_version(__version__)
    is_newer = remote_ver > local_ver

    # Najdi asset podle platformy (Windows .exe, macOS .dmg)
    wanted_ext = _installer_extension()
    download_url = ""
    download_size = 0
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if name.lower().endswith(wanted_ext):
            download_url = asset.get("browser_download_url", "")
            download_size = int(asset.get("size", 0))
            break

    if not download_url:
        logger.info("Update check: release {} nemá {} asset", tag, wanted_ext)
        return None

    return UpdateInfo(
        version=tag.lstrip("vV"),
        tag_name=tag,
        download_url=download_url,
        download_size_bytes=download_size,
        release_notes=(data.get("body") or "").strip(),
        is_newer_than_current=is_newer,
    )


def download_installer(
    info: UpdateInfo,
    *,
    progress_cb: Callable[[int, int], None] | None = None,
) -> Path:
    """Stáhne installer .exe do TEMP_DIR. Vrací cestu k souboru.

    `progress_cb(downloaded_bytes, total_bytes)` — volá se přibližně každých 256 KB.
    """
    ensure_dirs()
    target = TEMP_DIR / f"HlasDoTextu-Setup-{info.version}{_installer_extension()}"

    logger.info("Stahuji update {} → {}", info.tag_name, target)

    with httpx.stream("GET", info.download_url, timeout=60.0, follow_redirects=True) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length", info.download_size_bytes or 0))
        downloaded = 0
        last_report = 0
        with target.open("wb") as f:
            for chunk in response.iter_bytes(chunk_size=64 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb is not None and downloaded - last_report >= 256 * 1024:
                    try:
                        progress_cb(downloaded, total)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Update progress callback selhal: {}", exc)
                    last_report = downloaded
        # Final callback
        if progress_cb is not None:
            try:
                progress_cb(downloaded, total)
            except Exception:
                pass

    logger.info("Update stažen: {} ({:.1f} MB)", target, target.stat().st_size / 1024 / 1024)
    return target


def apply_update(installer_path: Path) -> None:
    """Spustí installer a ukončí aplikaci.

    Windows: Inno Setup `/SILENT` upgrade, ale s 3s delayem aby naše app
    stihla skončit a uvolnit `HlasDoTextu.exe` před přepsáním.
    macOS: otevře `.dmg` přes `open` — uživatel přetáhne .app do Applications.
    Linux / ostatní: nepodporováno, jen log.
    """
    if not installer_path.is_file():
        raise FileNotFoundError(f"Installer nenalezen: {installer_path}")

    if sys.platform == "win32":
        _apply_update_windows(installer_path)
    elif sys.platform == "darwin":
        _apply_update_macos(installer_path)
    else:
        logger.warning("apply_update: platforma {} není podporována", sys.platform)


def _apply_update_windows(installer_path: Path) -> None:
    # Windows nedovolí přepsat běžící .exe. Naše aplikace musí skončit DŘÍV,
    # než Inno Setup začne kopírovat soubory. Spustíme cmd wrapper, který
    # 3 sekundy spí a teprve pak nahodí installer — a hned ukončíme app.
    #
    # creationflags musí odpojit child úplně: bez DETACHED_PROCESS by share-il
    # konzoli, bez CREATE_BREAKAWAY_FROM_JOB by zemřel s parentem v Job objectu
    # (PyInstaller bundle běží často v takovém jobu).
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_BREAKAWAY_FROM_JOB = 0x01000000
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB

    installer_str = str(installer_path)
    # `start ""` odpojí installer od cmd wrapperu, takže cmd hned skončí
    # a installer doběhne sám. Prázdné `""` je title — povinné, jinak `start`
    # interpretuje cestu jako title.
    shell_cmd = (
        f'timeout /t 3 /nobreak >nul & '
        f'start "" "{installer_str}" /SILENT /SUPPRESSMSGBOXES /NORESTART'
    )
    logger.info("Spouštím installer (delayed 3s): {}", shell_cmd)

    try:
        subprocess.Popen(
            ["cmd.exe", "/c", shell_cmd],
            creationflags=flags,
            close_fds=True,
            cwd=str(Path.home()),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        logger.exception("Nelze spustit installer: {}", exc)
        raise RuntimeError(
            f"Nepodařilo se spustit instalátor: {exc}. "
            f"Spusť ho prosím ručně: {installer_path}"
        ) from exc

    _request_app_quit()


def _apply_update_macos(installer_path: Path) -> None:
    logger.info("Otevírám DMG: {}", installer_path)
    try:
        subprocess.Popen(
            ["open", str(installer_path)],
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        logger.exception("Nelze otevřít DMG: {}", exc)
        raise RuntimeError(
            f"Nepodařilo se otevřít DMG: {exc}. "
            f"Otevři ho prosím ručně: {installer_path}"
        ) from exc

    _request_app_quit()


def _request_app_quit() -> None:
    # Qt potřebuje aspoň jeden event loop tick na cleanup (closeEvent,
    # uložení nastavení, zavření workerů). Když je app k dispozici, použijeme
    # QTimer.singleShot — jinak fallback na os._exit bez Python atexit hooků,
    # protože sys.exit by mohl spustit threading cleanup, který blokne.
    try:
        from PySide6.QtCore import QCoreApplication, QTimer

        app = QCoreApplication.instance()
        if app is not None:
            QTimer.singleShot(100, app.quit)
            return
    except ImportError:
        pass
    os._exit(0)
