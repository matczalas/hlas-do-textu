"""Vygeneruje ikonu aplikace Hlas do textu.

Design: rounded-square pozadí (macOS/iOS konvence), gradient modrá #1a4d8f → #205ca8,
bílý stylizovaný mikrofon nahoře a tři textové řádky dole — vizuální metafora
"hlas → text". Akcent v zlaté Safe4Future barvě jako záři kolem mikrofonu.

Generuje:
- icon.png  512×512 (zdroj pro UI)
- icon.ico  multi-size 16/32/48/64/128/256 (Windows)
- icon.icns multi-size až 1024 (macOS, jen na macOS přes iconutil)

Závislost: Pillow (transitive dep PySide6).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
RESOURCES = ROOT / "app" / "resources"
PNG_PATH = RESOURCES / "icon.png"
ICO_PATH = RESOURCES / "icon.ico"
ICNS_PATH = RESOURCES / "icon.icns"

# Barvy
BG_TOP = (26, 77, 143, 255)        # #1a4d8f — tmavší modrá nahoře
BG_BOTTOM = (32, 92, 168, 255)     # #205ca8 — světlejší modrá dole (S4F accent)
WHITE = (255, 255, 255, 255)
GLOW = (255, 196, 60, 90)          # zlatá záře (Safe4Future second color), poloprůhledná


def main() -> int:
    RESOURCES.mkdir(parents=True, exist_ok=True)

    size = 1024  # generujeme ve vysokém rozlišení, downscale do PNG/ICO/ICNS
    img = _render_icon(size)

    # 512×512 PNG pro UI a tray
    img.resize((512, 512), Image.Resampling.LANCZOS).save(PNG_PATH, format="PNG")
    print(f"Vytvořeno: {PNG_PATH}")

    # ICO multi-size pro Windows
    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ICO_PATH, format="ICO", sizes=ico_sizes)
    print(f"Vytvořeno: {ICO_PATH}")

    # ICNS pro macOS (vyžaduje iconutil)
    _make_icns(img, ICNS_PATH)
    return 0


def _render_icon(size: int) -> Image.Image:
    """Vyrobí PIL Image se zdrojovou ikonou v daném rozlišení."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # 1) Rounded square pozadí s gradientem
    bg = _gradient_rounded_square(size, BG_TOP, BG_BOTTOM, corner_radius=size // 5)
    img = Image.alpha_composite(img, bg)

    # 2) Zlatá záře okolo mikrofonu (efekt "hlas svítí")
    glow_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    cx, cy = size // 2, int(size * 0.40)
    glow_r = int(size * 0.22)
    glow_draw.ellipse(
        (cx - glow_r, cy - glow_r, cx + glow_r, cy + glow_r), fill=GLOW
    )
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=size // 25))
    img = Image.alpha_composite(img, glow_layer)

    # 3) Mikrofon (bílý) — capsule body + stojánek + base
    draw = ImageDraw.Draw(img)
    _draw_microphone(draw, size, cx, cy)

    # 4) Textové řádky pod mikrofonem
    _draw_text_lines(draw, size)

    return img


def _gradient_rounded_square(
    size: int,
    top_color: tuple[int, int, int, int],
    bottom_color: tuple[int, int, int, int],
    corner_radius: int,
) -> Image.Image:
    """Rounded square s vertikálním gradientem."""
    # Vyrobíme gradient v plné velikosti
    gradient = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gradient_pixels = gradient.load()
    for y in range(size):
        t = y / max(size - 1, 1)
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * t)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * t)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * t)
        a = int(top_color[3] + (bottom_color[3] - top_color[3]) * t)
        for x in range(size):
            gradient_pixels[x, y] = (r, g, b, a)

    # Mask: rounded rectangle
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=corner_radius, fill=255
    )

    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(gradient, (0, 0), mask)
    return out


def _draw_microphone(draw: ImageDraw.ImageDraw, size: int, cx: int, cy: int) -> None:
    """Stylizovaný mikrofon: capsule body + spodní oblouk (stand) + nožka + base.

    cx, cy: střed capsule body.
    Rozměry jsou relativní k `size`, aby mikrofon dobře vypadal v 16×16 i 1024.
    """
    # Capsule body
    body_half_w = int(size * 0.085)   # poloviční šířka
    body_half_h = int(size * 0.155)   # poloviční výška
    body_box = (
        cx - body_half_w,
        cy - body_half_h,
        cx + body_half_w,
        cy + body_half_h,
    )
    draw.rounded_rectangle(body_box, radius=body_half_w, fill=WHITE)

    # Detail: 3 horizontální linky uvnitř capsule (přidá "mikrofon mřížku")
    detail_color = (180, 200, 230, 255)  # mírně modřejší než bílá pro kontrast
    line_w = int(size * 0.005)
    spacing = body_half_h // 2
    for i in range(-1, 2):
        y = cy + i * spacing
        x1 = cx - int(body_half_w * 0.55)
        x2 = cx + int(body_half_w * 0.55)
        draw.line([(x1, y), (x2, y)], fill=detail_color, width=max(line_w, 2))

    # Stojánek — oblouk (U-tvar) pod capsule
    arc_outer_r = int(size * 0.135)
    arc_inner_r = int(size * 0.105)
    arc_cy = cy + int(size * 0.025)  # střed oblouku trochu níž než capsule
    arc_box_outer = (
        cx - arc_outer_r,
        arc_cy - arc_outer_r,
        cx + arc_outer_r,
        arc_cy + arc_outer_r,
    )
    # Outer arc — vyhneme se inner arc (čistý U-tvar drží mikrofonní siluetu)
    _ = arc_inner_r  # ponecháno pro budoucí variantu s inner ringem
    draw.arc(arc_box_outer, start=0, end=180, fill=WHITE, width=max(int(size * 0.018), 3))
    # Pro lepší tloušťku přidáme druhý arc o pixel jinde
    draw.arc(
        (arc_box_outer[0] + 1, arc_box_outer[1] + 1, arc_box_outer[2] - 1, arc_box_outer[3] - 1),
        start=0, end=180, fill=WHITE, width=max(int(size * 0.018), 3),
    )

    # Nožka (vertikální tyč pod arc)
    leg_top = arc_cy + arc_outer_r - int(size * 0.005)
    leg_bottom = leg_top + int(size * 0.05)
    leg_half_w = max(int(size * 0.012), 2)
    draw.rectangle(
        (cx - leg_half_w, leg_top, cx + leg_half_w, leg_bottom),
        fill=WHITE,
    )

    # Base (horizontální podstavec)
    base_half_w = int(size * 0.06)
    base_y = leg_bottom
    base_h = max(int(size * 0.014), 2)
    draw.rounded_rectangle(
        (cx - base_half_w, base_y, cx + base_half_w, base_y + base_h),
        radius=base_h // 2,
        fill=WHITE,
    )


def _draw_text_lines(draw: ImageDraw.ImageDraw, size: int) -> None:
    """Čtyři horizontální čárky reprezentující přepis."""
    # Hodně transparentní bílé (aby se mikrofon stále tlačil do popředí)
    line_color = (255, 255, 255, 220)

    base_y = int(size * 0.73)
    spacing = int(size * 0.062)
    line_thickness = max(int(size * 0.022), 4)

    # 4 řádky s různými délkami, leftmost-align s lehce variabilním offsetem
    rows = [
        (0.18, 0.78),   # plný řádek (start_x_ratio, end_x_ratio)
        (0.18, 0.70),
        (0.18, 0.82),
        (0.18, 0.58),   # poslední, nejkratší (jako konec odstavce)
    ]
    for i, (sx, ex) in enumerate(rows):
        y = base_y + i * spacing
        x1 = int(size * sx)
        x2 = int(size * ex)
        draw.rounded_rectangle(
            (x1, y - line_thickness // 2, x2, y + line_thickness // 2),
            radius=line_thickness // 2,
            fill=line_color,
        )


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
