"""Vygeneruje ikony aplikace (PNG / ICO / ICNS) z bitmap zdroje.

Zdroj: `app/resources/logo_source.png` (commitnutý v repu).
Výstupy: `app/resources/icon.png` / `.ico` / `.icns`.

Použití:
    python scripts/generate_icon.py
    python scripts/generate_icon.py --source ~/Downloads/nove_logo.png

Závislost: Pillow (transitive dep PySide6). ICNS vyžaduje macOS + iconutil.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RESOURCES = ROOT / "app" / "resources"
DEFAULT_SOURCE = RESOURCES / "logo_source.png"
PNG_PATH = RESOURCES / "icon.png"
ICO_PATH = RESOURCES / "icon.ico"
ICNS_PATH = RESOURCES / "icon.icns"

# Výstupní rozlišení master PNG (jdou z něj všechny menší velikosti)
MASTER_SIZE = 1024
UI_PNG_SIZE = 512  # pro app/resources/icon.png (UI, tray)
ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"Vstupní logo (PNG). Default: {DEFAULT_SOURCE.relative_to(ROOT)}",
    )
    args = parser.parse_args()

    source_path: Path = args.source.expanduser().resolve()
    if not source_path.is_file():
        print(f"CHYBA: Zdrojový obrázek neexistuje: {source_path}")
        return 1

    RESOURCES.mkdir(parents=True, exist_ok=True)
    print(f"Zdroj: {source_path}")

    master = _prepare_master(source_path, MASTER_SIZE)

    # icon.png — pro UI a tray
    master.resize((UI_PNG_SIZE, UI_PNG_SIZE), Image.Resampling.LANCZOS).save(
        PNG_PATH, format="PNG", optimize=True
    )
    print(f"Vytvořeno: {PNG_PATH}  ({UI_PNG_SIZE}×{UI_PNG_SIZE})")

    # icon.ico — multi-size pro Windows
    master.save(ICO_PATH, format="ICO", sizes=ICO_SIZES)
    print(f"Vytvořeno: {ICO_PATH}  (sizes: {', '.join(f'{w}×{h}' for w, h in ICO_SIZES)})")

    # icon.icns — macOS, jen na macOS přes iconutil
    _make_icns(master, ICNS_PATH)
    return 0


def _prepare_master(source_path: Path, target_size: int) -> Image.Image:
    """Načte zdroj, fitne ho do čtverce a vrátí master image v `target_size`.

    Pravidla:
    - RGB i RGBA vstup je OK.
    - Pokud zdroj není čtverec, dopadne se na čtverec přidáním okrajů
      stejné barvy jako rohové pixely (defaultně bílá u tohoto loga,
      aby to vypadalo přirozeně i v ikoně).
    - Resize na cílový čtverec pomocí LANCZOS (vysoká kvalita).
    """
    img = Image.open(source_path)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")

    width, height = img.size
    if width != height:
        # Padding na čtverec barvou rohového pixelu (typicky bílá pro toto logo).
        size = max(width, height)
        bg_color = _detect_corner_color(img)
        canvas = Image.new(img.mode, (size, size), bg_color)
        canvas.paste(img, ((size - width) // 2, (size - height) // 2))
        img = canvas

    if img.size != (target_size, target_size):
        img = img.resize((target_size, target_size), Image.Resampling.LANCZOS)

    return img


def _detect_corner_color(img: Image.Image) -> tuple:
    """Vrátí barvu levého horního pixelu (předpoklad pozadí). RGBA-safe."""
    pixel = img.getpixel((0, 0))
    if img.mode == "RGB":
        return pixel  # type: ignore[return-value]
    if img.mode == "RGBA":
        return pixel  # type: ignore[return-value]
    # Fallback — neměl by nastat, ale ať se nesype
    return (255, 255, 255, 255) if img.mode == "RGBA" else (255, 255, 255)


def _make_icns(img: Image.Image, out_path: Path) -> None:
    """Vyrobí .icns pomocí macOS iconutil. Mimo macOS přeskočí."""
    import platform as _plat
    import shutil
    import subprocess

    if _plat.system() != "Darwin":
        print(f"Přeskočeno (.icns): běžíme na {_plat.system()}, ne macOS")
        return

    sizes_iconset = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]
    iconset_dir = out_path.parent / "icon.iconset"
    iconset_dir.mkdir(parents=True, exist_ok=True)
    try:
        for name, target_size in sizes_iconset:
            img.resize((target_size, target_size), Image.Resampling.LANCZOS).save(
                iconset_dir / name, "PNG"
            )
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(out_path)],
            check=True,
        )
        print(f"Vytvořeno: {out_path}")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"iconutil selhalo: {exc}")
    finally:
        shutil.rmtree(iconset_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
