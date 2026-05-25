"""Stáhne statický build FFmpeg pro Windows do `app/vendor/ffmpeg/win64/`.

Spouští se v CI nebo lokálně před PyInstaller buildem.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

# Veřejný mirror staticky linkovaného FFmpeg buildu (BtbN release artefakt).
FFMPEG_ZIP_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip"

ROOT = Path(__file__).resolve().parent.parent
TARGET_DIR = ROOT / "app" / "vendor" / "ffmpeg" / "win64"


def main() -> int:
    if (TARGET_DIR / "ffmpeg.exe").is_file():
        print(f"FFmpeg už existuje: {TARGET_DIR / 'ffmpeg.exe'}")
        return 0

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Stahuji {FFMPEG_ZIP_URL}…")

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        urllib.request.urlretrieve(FFMPEG_ZIP_URL, tmp.name)
        zip_path = Path(tmp.name)

    print("Rozbaluji…")
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            name = Path(member).name
            if name in ("ffmpeg.exe", "ffprobe.exe"):
                with zf.open(member) as src, (TARGET_DIR / name).open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                print(f"  → {TARGET_DIR / name}")

    zip_path.unlink(missing_ok=True)

    if not (TARGET_DIR / "ffmpeg.exe").is_file():
        print("CHYBA: ffmpeg.exe nebyl v archivu.", file=sys.stderr)
        return 1
    print("Hotovo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
