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


def main() -> int:
    RESOURCES.mkdir(parents=True, exist_ok=True)

    if ICO_PATH.is_file() and PNG_PATH.is_file():
        print(f"Ikony existují: {PNG_PATH}, {ICO_PATH}")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
