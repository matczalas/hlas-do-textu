"""Vygeneruje placeholder ikonu pro instalátor a aplikaci.

Spouští se v CI nebo lokálně před PyInstaller buildem, pokud `icon.ico` chybí.
Vytvoří jednoduchý kruhový design s textem "S4F" (Safe4Future).

Závislost: Pillow (přichází jako transitive dep PySide6 / huggingface_hub).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
RESOURCES = ROOT / "app" / "resources"
PNG_PATH = RESOURCES / "icon.png"
ICO_PATH = RESOURCES / "icon.ico"
ICNS_PATH = RESOURCES / "icon.icns"


def main() -> int:
    import platform as _plat

    RESOURCES.mkdir(parents=True, exist_ok=True)

    # Na macOS musí být i .icns; na Windows stačí .ico
    needs_icns = _plat.system() == "Darwin"
    all_present = ICO_PATH.is_file() and PNG_PATH.is_file()
    if needs_icns:
        all_present = all_present and ICNS_PATH.is_file()
    if all_present:
        print(f"Ikony existují: PNG, ICO{', ICNS' if needs_icns else ''}")
        return 0

    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Pozadí — kulatý gradient (zjednodušený jako plný kruh s outline)
    bg_color = (32, 92, 168, 255)         # S4F modrá
    accent = (255, 196, 0, 255)           # zlatá
    margin = 20
    draw.ellipse((margin, margin, size - margin, size - margin), fill=bg_color)

    # Textový monogram
    try:
        font = ImageFont.truetype("Arial.ttf", 200)
    except OSError:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 200)
        except OSError:
            font = ImageFont.load_default()

    text = "S4F"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    tx = (size - text_w) // 2 - bbox[0]
    ty = (size - text_h) // 2 - bbox[1]
    draw.text((tx, ty), text, fill=accent, font=font)

    img.save(PNG_PATH, format="PNG")
    print(f"Vytvořeno: {PNG_PATH}")

    # ICO obsahuje více velikostí pro Windows
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ICO_PATH, format="ICO", sizes=sizes)
    print(f"Vytvořeno: {ICO_PATH}")

    # ICNS pro macOS — vyžaduje iconutil (built-in macOS) nebo PNG fallback
    icns_path = RESOURCES / "icon.icns"
    _make_icns(img, icns_path)
    return 0


def _make_icns(img: Image.Image, out_path: Path) -> None:
    """Vyrobí .icns pomocí macOS iconutil. Mimo macOS jen nahraje PNG jako fallback."""
    import platform as _plat
    import subprocess

    if _plat.system() != "Darwin":
        print(f"Přeskočeno (.icns): běžíme na {_plat.system()}, ne macOS")
        return

    # macOS .iconset structure
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
        for name, size in sizes_iconset:
            img.resize((size, size), Image.Resampling.LANCZOS).save(iconset_dir / name, "PNG")
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(out_path)],
            check=True,
        )
        print(f"Vytvořeno: {out_path}")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"iconutil selhalo: {exc}")
    finally:
        import shutil

        shutil.rmtree(iconset_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
