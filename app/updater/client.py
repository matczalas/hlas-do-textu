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
import shutil
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
    # `data.get("assets", [])` nestačí — GitHub může vrátit "assets": null
    # (klíč existuje, hodnota None) → default se neuplatní → TypeError v for.
    for asset in (data.get("assets") or []):
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
    """Stáhne installer do TEMP_DIR. Vrací cestu k ověřenému souboru.

    `progress_cb(downloaded_bytes, total_bytes)` — volá se přibližně každých 256 KB.

    Robustnost:
    - Píše do `.part` souboru a až po ověření přejmenuje na finální (atomic rename),
      takže přerušený download nikdy nevypadá jako hotový.
    - Před stažením kontroluje volné místo na disku.
    - Po stažení ověří, že velikost odpovídá Content-Length (částečný = chyba).
    - Maže staré installery, ať TEMP_DIR neroste donekonečna.

    Raises:
        RuntimeError: málo místa na disku nebo neúplné stažení.
        httpx.HTTPError: síťová chyba.
    """
    ensure_dirs()
    _cleanup_old_installers(keep_version=info.version)

    target = TEMP_DIR / f"HlasDoTextu-Setup-{info.version}{_installer_extension()}"
    part = target.with_name(target.name + ".part")

    # Pre-flight: dost místa? (s 20% rezervou na rozbalení Inno Setup)
    expected = info.download_size_bytes or 0
    if expected > 0:
        try:
            free = shutil.disk_usage(TEMP_DIR).free
        except OSError as exc:
            logger.warning("Nelze zjistit volné místo: {}", exc)
            free = None
        if free is not None and free < int(expected * 1.2):
            raise RuntimeError(
                f"Málo místa na disku pro stažení aktualizace: potřeba "
                f"~{expected / 1024 / 1024:.0f} MB, volných jen "
                f"{free / 1024 / 1024:.0f} MB. Uvolni místo a zkus to znovu."
            )

    logger.info("Stahuji update {} → {}", info.tag_name, target)

    try:
        with httpx.stream(
            "GET", info.download_url, timeout=60.0, follow_redirects=True
        ) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length", expected))
            downloaded = 0
            last_report = 0
            with part.open("wb") as f:
                for chunk in response.iter_bytes(chunk_size=64 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb is not None and downloaded - last_report >= 256 * 1024:
                        try:
                            progress_cb(downloaded, total)
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("Update progress callback selhal: {}", exc)
                        last_report = downloaded
            if progress_cb is not None:
                try:
                    progress_cb(downloaded, total)
                except Exception:
                    pass
    except BaseException:
        # Jakákoli chyba (network, disk full, cancel) → uklidíme částečný .part
        part.unlink(missing_ok=True)
        raise

    # Verifikace velikosti — částečné stažení nesmí projít jako hotové
    if total > 0 and downloaded != total:
        part.unlink(missing_ok=True)
        raise RuntimeError(
            f"Neúplné stažení aktualizace: {downloaded} z {total} B "
            f"({downloaded * 100 // max(total, 1)} %). Zkus to znovu."
        )

    # Atomic rename — od teď je soubor "hotový"
    part.replace(target)
    logger.info("Update stažen: {} ({:.1f} MB)", target, target.stat().st_size / 1024 / 1024)
    return target


def _cleanup_old_installers(*, keep_version: str) -> None:
    """Smaže staré stažené installery z TEMP_DIR (kromě aktuální verze).

    Bez tohoto by se každá stažená verze hromadila (~200 MB/kus).
    """
    try:
        keep_name = f"HlasDoTextu-Setup-{keep_version}"
        for pattern in ("HlasDoTextu-Setup-*.exe", "HlasDoTextu-Setup-*.dmg",
                        "HlasDoTextu-Setup-*.part"):
            for old in TEMP_DIR.glob(pattern):
                if old.name.startswith(keep_name):
                    continue  # ponecháme aktuální verzi (+ její .part při retry)
                try:
                    old.unlink()
                    logger.info("Smazán starý installer: {}", old.name)
                except OSError as exc:
                    logger.warning("Nelze smazat starý installer {}: {}", old.name, exc)
    except OSError as exc:
        logger.warning("Cleanup starých installerů selhal: {}", exc)


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
    """Spustí Inno Setup installer odděleně od běžící aplikace a ukončí ji.

    Windows nedovolí přepsat běžící `.exe`. Potřebujeme tedy:
    1. Spustit installer jako proces NEZÁVISLÝ na naší aplikaci (přežije náš exit).
    2. Dát aplikaci čas se ukončit, NEŽ installer začne kopírovat soubory.
    3. Po dokončení installeru AUTOMATICKY spustit novou verzi.

    Historie bugu: dřívější verze používala `cmd /c "timeout /t 3 & start ..."`
    s `creationflags=CREATE_BREAKAWAY_FROM_JOB`. Na reálném Windows to padalo
    ze dvou důvodů:
      - `timeout` vyžaduje konzoli — se stdin=DEVNULL skončí chybou
        "Input redirection is not supported" a delay vůbec neproběhne.
      - `CREATE_BREAKAWAY_FROM_JOB` vyhodí "Access denied", když proces běží
        v Job Objectu bez povoleného breakaway (časté u PyInstaller bundlu).

    Stav v v1.7.1 — tichý update + auto-restart:
      - `/VERYSILENT` místo `/SILENT` — žádné progress okno během instalace,
        uživatel uvidí jen "app zmizela → nová app se otevřela".
      - `/SUPPRESSMSGBOXES` — žádné Inno chyby v okně, jen v logu.
      - `/NORESTART` — pojistka, ať se Windows neptá na restart systému.
      - `installer/HlasDoTextu.iss` má dvojici [Run] entries — druhý
        s `Check: WizardSilent` spustí novou .exe po VERYSILENT upgrade.
      - delay přes `ping` (spolehlivé bez konzole/stdin),
      - installer spuštěn přes `ShellExecuteW` (nativní Windows API —
        proces mimo náš Job Object bez breakaway flagu),
      - pojistka: Inno Setup má `CloseApplications=yes` + `AppMutex`, takže
        i kdyby naše app ještě běžela, installer ji sám korektně zavře.
    """
    installer_str = str(installer_path)

    # Flagy pro tichý update (v1.7.1): žádné progress okno, žádné chybové
    # message boxy, žádný systém-restart prompt. Auto-restart aplikace řeší
    # [Run] entry s Check: WizardSilent v .iss.
    silent_flags = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART"

    # Wrapper .bat: počká přes `ping` (spolehlivé bez konzole), spustí installer
    # a sám se smaže. `ping -n 4` = ~3 s prodleva.
    bat_path = installer_path.with_name("hdt_update_launch.bat")
    bat_content = (
        "@echo off\r\n"
        "ping 127.0.0.1 -n 4 >nul\r\n"
        f'start "" "{installer_str}" {silent_flags}\r\n'
        'del "%~f0"\r\n'
    )
    try:
        bat_path.write_text(bat_content, encoding="ascii")
    except OSError as exc:
        logger.warning("Nelze zapsat update .bat ({}), zkusím přímé spuštění", exc)
        bat_path = None

    target = str(bat_path) if bat_path is not None else installer_str
    params = "" if bat_path is not None else silent_flags

    # 1) Primární cesta: ShellExecuteW (nejnativnější, neřeší Job Object).
    launched = _shellexecute(target, params)

    # 2) Fallback: subprocess.Popen BEZ breakaway flagu (jen DETACHED_PROCESS).
    if not launched:
        logger.warning("ShellExecuteW selhal, fallback na subprocess.Popen")
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        try:
            if bat_path is not None:
                subprocess.Popen(
                    ["cmd.exe", "/c", str(bat_path)],
                    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                    close_fds=True,
                    cwd=str(Path.home()),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(
                    [installer_str, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                    close_fds=True,
                    cwd=str(Path.home()),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            launched = True
        except OSError as exc:
            logger.exception("Fallback subprocess.Popen také selhal: {}", exc)
            raise RuntimeError(
                f"Nepodařilo se spustit instalátor: {exc}. "
                f"Spusť ho prosím ručně: {installer_path}"
            ) from exc

    logger.info("Installer spuštěn (bat={}, target={})", bat_path is not None, target)

    # Ukončíme aplikaci, ať uvolní .exe pro přepsání. Installer čeká přes
    # ping delay v .bat + Inno Setup CloseApplications jako pojistka.
    _request_app_quit()


def _shellexecute(target: str, params: str) -> bool:
    """Spustí proces přes Windows ShellExecuteW. Vrací True při úspěchu.

    ShellExecuteW vrací hodnotu >32 při úspěchu. Proces se spustí nezávisle
    na našem (mimo Job Object), takže nepotřebujeme CREATE_BREAKAWAY_FROM_JOB.
    """
    try:
        import ctypes

        # SW_SHOWNORMAL=1. Vrací HINSTANCE > 32 při úspěchu.
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "open", target, params or None, str(Path.home()), 1
        )
        return int(rc) > 32
    except Exception as exc:  # noqa: BLE001
        logger.warning("ShellExecuteW výjimka: {}", exc)
        return False

    _request_app_quit()


def _apply_update_macos(installer_path: Path) -> None:
    """macOS auto-update: spustí externí skript, který nahradí .app a restartuje.

    Workflow:
    1. Lokalizuje aktuální .app bundle (přes sys.executable v PyInstaller bundlu).
    2. Vytvoří shell skript v /tmp/hdt_updater_<pid>.sh.
    3. Skript po našem exit:
       a) wait while ps -p <parent_pid> > /dev/null  — počká až app skončí
       b) hdiutil attach DMG -nobrowse
       c) atomic replace: mv app app.bak → ditto new app → rm -rf bak
          (při chybě rollback z .bak)
       d) hdiutil detach
       e) open -a nové app
       f) skript se sám smaže
    4. App pak zavolá _request_app_quit() (totéž co Windows path).

    Fallback: pokud běžíme v dev módu (python -m app, ne PyInstaller bundle)
    nebo nelze najít .app, spadne zpět na "jen open DMG" jako dříve.
    """
    current_app = _find_current_app_path()
    if current_app is None:
        logger.warning("Auto-update nedostupný v dev módu, jen otevřu DMG")
        _open_dmg_fallback(installer_path)
        return

    logger.info("macOS auto-update: current_app={}", current_app)

    try:
        script_path = _create_macos_updater_script(
            dmg=installer_path,
            current_app=current_app,
            parent_pid=os.getpid(),
        )
    except OSError as exc:
        logger.exception("Nelze vytvořit update skript: {}", exc)
        _open_dmg_fallback(installer_path)
        return

    # Spustit skript jako nezávislý proces (přežije náš exit).
    try:
        subprocess.Popen(
            ["/bin/bash", str(script_path)],
            close_fds=True,
            start_new_session=True,  # detach z naší process group
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        logger.exception("Nelze spustit update skript: {}", exc)
        _open_dmg_fallback(installer_path)
        return

    logger.info("Update skript spuštěn: {}", script_path)

    # Ukončit app — skript čeká na náš exit, pak provede replace.
    _request_app_quit()


def _open_dmg_fallback(installer_path: Path) -> None:
    """Fallback chování (dev mode / chyba skriptu) — jen otevře DMG."""
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


def _find_current_app_path() -> Path | None:
    """Najít .app bundle běžící aplikace.

    V PyInstaller bundlu na macOS je sys.executable cesta k binárce uvnitř
    bundle, např. /Applications/Hlas do textu.app/Contents/MacOS/HlasDoTextu.
    Hledáme .app někde v jejích parents.

    Vrací None pokud běžíme v dev módu (python -m app) — pak auto-update
    nemá co nahrazovat.
    """
    if not getattr(sys, "frozen", False):
        return None

    try:
        exe = Path(sys.executable).resolve()
    except OSError:
        return None

    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent
    return None


def _create_macos_updater_script(
    *,
    dmg: Path,
    current_app: Path,
    parent_pid: int,
) -> Path:
    """Vytvoří shell skript v /tmp, který provede update + restart.

    Skript je samostatně spustitelný a NESMÍ záviset na běžící aplikaci —
    všechny cesty se substituují at write time.
    """
    import tempfile

    work_dir = Path(tempfile.mkdtemp(prefix=f"hdt_update_{parent_pid}_"))
    script_path = work_dir / "update.sh"
    log_path = work_dir / "update.log"

    # Bash script — pozor na quoting cest s mezerami ("Hlas do textu.app").
    # Cesty jsou substituovány Pythonem do f-stringu, uvnitř skriptu pak
    # vždy v double-quotes pro shell.
    script = f"""#!/bin/bash
# Hlas do textu — auto-update worker
# Generated by app/updater/client.py for PID {parent_pid}
exec > "{log_path}" 2>&1
set -u

echo "=== Hlas do textu auto-update ==="
echo "Parent PID: {parent_pid}"
echo "Source DMG: {dmg}"
echo "Target app: {current_app}"
echo "Started: $(date)"

DMG="{dmg}"
APP="{current_app}"
PARENT_PID={parent_pid}
MOUNT_POINT="/tmp/hdt_dmg_{parent_pid}"
BAK="${{APP}}.update-bak"

# 1) Wait for parent app to exit (max 30 sekund safety)
echo "Waiting for parent process to exit..."
for i in $(seq 1 60); do
    if ! ps -p "$PARENT_PID" > /dev/null 2>&1; then
        echo "Parent exited after ${{i}} half-seconds."
        break
    fi
    sleep 0.5
done

# Extra grace period — aby Qt stihl uvolnit lock soubory
sleep 1

# 2) Mount DMG
echo "Mounting DMG to $MOUNT_POINT..."
mkdir -p "$MOUNT_POINT"
if ! hdiutil attach "$DMG" -nobrowse -mountpoint "$MOUNT_POINT" -quiet; then
    echo "ERROR: hdiutil attach failed"
    open "$DMG"  # last-resort fallback
    exit 1
fi

# 3) Find .app inside DMG (depth 2 = symlinks i v root)
NEW_APP=$(find "$MOUNT_POINT" -maxdepth 2 -name "*.app" -type d 2>/dev/null | head -1)
if [ -z "$NEW_APP" ]; then
    echo "ERROR: No .app found in DMG"
    hdiutil detach "$MOUNT_POINT" -force >/dev/null 2>&1 || true
    open "$DMG"
    exit 1
fi
echo "Found new app: $NEW_APP"

# 4) Atomic replace s rollback
echo "Backing up current app..."
if ! mv "$APP" "$BAK"; then
    echo "ERROR: Cannot rename current app (permission?). Aborting."
    hdiutil detach "$MOUNT_POINT" -force >/dev/null 2>&1 || true
    open "$DMG"
    exit 1
fi

echo "Copying new app..."
if ! ditto "$NEW_APP" "$APP"; then
    echo "ERROR: ditto failed, rolling back..."
    rm -rf "$APP" 2>/dev/null || true
    mv "$BAK" "$APP" || echo "ROLLBACK ALSO FAILED — app is at $BAK"
    hdiutil detach "$MOUNT_POINT" -force >/dev/null 2>&1 || true
    exit 1
fi

# Remove quarantine flag tak, aby Gatekeeper neptal podruhé (jen pokud máme
# práva — pokud .app je v /Applications, xattr vyžaduje sudo, ignorujeme)
xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true

echo "Removing backup..."
rm -rf "$BAK"

# 5) Unmount
echo "Unmounting DMG..."
hdiutil detach "$MOUNT_POINT" -force >/dev/null 2>&1 || true
rmdir "$MOUNT_POINT" 2>/dev/null || true

# 6) Launch new app
echo "Launching new app..."
sleep 0.5
open "$APP"

# 7) Self-destruct (smaže celý tmpdir včetně logu)
echo "Update completed at: $(date)"
sleep 2
rm -rf "$(dirname "$0")"
"""

    script_path.write_text(script, encoding="utf-8")
    script_path.chmod(0o755)
    logger.info("Update skript vytvořen: {} (log: {})", script_path, log_path)
    return script_path


def _request_app_quit() -> None:
    # Qt potřebuje aspoň jeden event loop tick na cleanup (closeEvent,
    # uložení nastavení, zavření workerů). Když je app k dispozici, použijeme
    # QTimer.singleShot — jinak fallback na os._exit bez Python atexit hooků.
    #
    # KRITICKÉ: app.quit() je no-op, pokud běží modální dialog nebo nějaký
    # closeEvent handler quit zruší. Pak by stará app dál držela .exe a
    # Inno Setup by nemohl přepsat soubory. Proto přidáváme TVRDÝ fallback:
    # když se proces neukončí do ~2.5 s (méně než 3s delay installeru),
    # zabijeme ho přes os._exit. Installer pak najde uvolněný .exe.
    try:
        from PySide6.QtCore import QCoreApplication, QTimer

        app = QCoreApplication.instance()
        if app is not None:
            QTimer.singleShot(100, app.quit)
            QTimer.singleShot(2500, lambda: os._exit(0))
            return
    except ImportError:
        pass
    os._exit(0)
