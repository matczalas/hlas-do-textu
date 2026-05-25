"""GitHub Releases klient pro auto-update.

Implementace:
- check_for_update() — GET https://api.github.com/repos/{owner}/{repo}/releases/latest
- download_installer() — stáhne `.exe` asset z release s progress callbackem
- apply_update() — spustí installer s /SILENT a ukončí aplikaci

Bez authentication (read-only public repo). Network errors jsou tiše ošetřeny
(žádný update prostě znamená "ticho", uživatel není rušen kdyby byl bez internetu).
"""
from __future__ import annotations

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

    # Najdi .exe asset
    download_url = ""
    download_size = 0
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if name.lower().endswith(".exe"):
            download_url = asset.get("browser_download_url", "")
            download_size = int(asset.get("size", 0))
            break

    if not download_url:
        logger.info("Update check: release {} nemá .exe asset", tag)
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
    target = TEMP_DIR / f"HlasDoTextu-Setup-{info.version}.exe"

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
    """Spustí installer s /SILENT a ukončí aplikaci.

    Inno Setup default upgrade chování: stejné AppId → přemaže staré soubory,
    zachová user data v AppData. /SILENT = bez interaktivního UI (jen progress bar).
    """
    if not installer_path.is_file():
        raise FileNotFoundError(f"Installer nenalezen: {installer_path}")

    if sys.platform != "win32":
        logger.warning("apply_update: na ne-Windows platformě nefunguje (jen log)")
        return

    cmd = [str(installer_path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
    logger.info("Spouštím installer: {}", " ".join(cmd))

    # Detach so installer keeps running po našem exitu
    subprocess.Popen(
        cmd,
        creationflags=0x00000008,  # DETACHED_PROCESS
        close_fds=True,
    )
    # Necháme MainWindow.closeEvent doběhnout přirozeně
    sys.exit(0)
