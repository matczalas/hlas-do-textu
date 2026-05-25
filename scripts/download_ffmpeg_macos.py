"""Stáhne statický build FFmpeg pro macOS do `app/vendor/ffmpeg/macos/`.

Použité zdroje:
- evermeet.cx — veřejný service distribuující statické macOS buildy
  (universal2: arm64 + x86_64 ve stejné binárce)

Spouští se v CI nebo lokálně před PyInstaller buildem na macOS.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

# Universal builds (arm64 + x86_64) pro Apple Silicon + Intel Macs.
# evermeet.cx je dlouhodobě stabilní mirror.
FFMPEG_URL = "https://evermeet.cx/ffmpeg/ffmpeg-7.1.zip"
FFPROBE_URL = "https://evermeet.cx/ffmpeg/ffprobe-7.1.zip"

ROOT = Path(__file__).resolve().parent.parent
TARGET_DIR = ROOT / "app" / "vendor" / "ffmpeg" / "macos"


def _download_and_extract(url: str, name: str) -> Path:
    """Stáhne ZIP, vytáhne binárku jménem `name`, vrátí cestu."""
    print(f"Stahuji {url}...")
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        urllib.request.urlretrieve(url, tmp.name)
        zip_path = Path(tmp.name)

    dest = TARGET_DIR / name
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            if Path(member).name == name:
                with zf.open(member) as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out)
                # Spustitelné (FFmpeg static binary)
                dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
                print(f"  -> {dest} ({dest.stat().st_size / 1024 / 1024:.1f} MB)")
                break

    zip_path.unlink(missing_ok=True)
    return dest


def main() -> int:
    if sys.platform != "darwin":
        print(f"VAROVANI: bezi na {sys.platform}, ne na macOS. Bin nemusi jit spustit.", file=sys.stderr)

    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    if (TARGET_DIR / "ffmpeg").is_file() and (TARGET_DIR / "ffprobe").is_file():
        print(f"FFmpeg uz existuje: {TARGET_DIR}")
        return 0

    try:
        _download_and_extract(FFMPEG_URL, "ffmpeg")
        _download_and_extract(FFPROBE_URL, "ffprobe")
    except Exception as exc:
        print(f"CHYBA: {exc}", file=sys.stderr)
        return 1

    # Odebrat macOS quarantine attribute aby se daly spustit bez warning
    if sys.platform == "darwin":
        for binary in ("ffmpeg", "ffprobe"):
            p = TARGET_DIR / binary
            if p.is_file():
                os.system(f"xattr -d com.apple.quarantine '{p}' 2>/dev/null")

    print("Hotovo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
