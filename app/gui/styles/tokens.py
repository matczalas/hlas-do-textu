"""tokens.py — jediný zdroj pravdy pro vzhled aplikace Hlas do textu.

Sjednocuje to, co bylo dříve rozkopírované napříč kódem:
  - ACCENT = "#205ca8" bylo zkopírované v ~10 souborech
  - app.qss mělo #205ca8 natvrdo na mnoha místech
  - nebylo rozlišení role (student × učitel)

Po nasazení:
  - barvy/rádiusy/spacing/typografie se mění JEN tady
  - role (student/teacher) přepne accent jediným voláním set_role()
  - QSS se vykreslí přes render_qss() — accent se doplní z tokenů
  - světlý/tmavý režim řeší QPalette přes build_palette()
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QPalette

# =============================================================================
# 1) BAREVNÉ TOKENY (Safe4Future)
# =============================================================================
# Neutrály a sémantika jsou společné pro obě role. Accent se liší podle role.

# --- Brand / role accenty ---------------------------------------------------
STUDENT_ACCENT = "#205ca8"          # Safe4Future modrá
STUDENT_ACCENT_STRONG = "#1a4d8f"   # hover / pressed (tmavší)
STUDENT_ACCENT_PRESS = "#163f76"

TEACHER_ACCENT = "#00897B"          # Original Teal — vážnější, pedagogický nástroj
TEACHER_ACCENT_STRONG = "#00695C"
TEACHER_ACCENT_PRESS = "#004d40"

# --- Sémantické stavové barvy (společné) ------------------------------------
SUCCESS = "#2e7d32"   # AI připojena / hotovo
WARNING = "#d68910"   # má alternativu (klíč chybí / Ollama neaktivní) — ne chyba
DANGER = "#c0392b"    # zrušit / chyba
CONSENT_BG = "rgba(243, 196, 60, 0.16)"   # GDPR žlutá (souhlas)
CONSENT_BORDER = "rgba(243, 196, 60, 0.55)"

# --- Neutrály: SVĚTLÝ režim -------------------------------------------------
LIGHT = {
    "window":        "#eaeef3",   # plátno za kartami
    "base":          "#ffffff",   # karty, inputy
    "alt_base":      "#f3f6f9",   # log, status pill pozadí
    "surface_2":     "#f3f6f9",
    "surface_3":     "#eef2f6",
    "border":        "#e3e8ee",
    "border_strong": "#d2dae3",
    "text":          "#0A1628",   # Deep Ink
    "text_2":        "#566576",   # Slate-ish (sekundární)
    "text_3":        "#9aa7b6",   # placeholder / hint
}

# --- Neutrály: TMAVÝ režim --------------------------------------------------
# v1.4.2: zvýšen kontrast mezi window/base/border, aby karty nesplývaly
# s pozadím. Předtím byl base jen 5 % světlejší než window — karty
# a tlačítka v dark mode prakticky zmizely v Deep Ink pozadí.
DARK = {
    "window":        "#0A1628",   # Deep Ink (background)
    "base":          "#1c2e4f",   # Karty/inputy — výrazněji světlejší než window
    "alt_base":      "#243a5e",   # Log / status pill
    "surface_2":     "#243a5e",
    "surface_3":     "#2d456b",
    "border":        "#3a5278",   # Border viditelný na window i base
    "border_strong": "#5a7194",
    "text":          "#eef2f8",
    "text_2":        "#bccada",   # Sekundární text — lepší WCAG kontrast
    "text_3":        "#8295b0",   # Placeholder — světlejší (z #637791)
}


# =============================================================================
# 2) GEOMETRIE A TYPOGRAFIE
# =============================================================================
RADIUS = {
    "xs":    "4px",    # badge
    "sm":    "6px",
    "input": "8px",    # inputy, malá tlačítka
    "md":    "10px",
    "card":  "12px",   # karty (brand bible)
    "modal": "16px",   # dialogy
    "pill":  "999px",  # CTA pill, segmenty, status
}

# 4px base (brand bible: spacing není předepsaný, držíme 4px rytmus)
SPACE = {n: f"{n*4}px" for n in (0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24)}

FONT_STACK = (
    '"Segoe UI Variable Display", "Segoe UI", "SF Pro Text", '
    '-apple-system, "Helvetica Neue", Arial, sans-serif'
)
FONT_MONO = '"JetBrains Mono", "Cascadia Code", "Consolas", "Menlo", monospace'

TYPE = {
    "body":    "13px",
    "small":   "12px",
    "micro":   "11px",
    "h_label": "11px",   # SectionLabel (uppercase)
    "title":   "16px",
    "h2":      "19px",
    "cta":     "14px",
}

# Pohyb (brand bible)
EASE = "cubic-bezier(0.2, 0.8, 0.2, 1)"   # Qt QSS animace neumí; pro QPropertyAnimation v kódu
DUR_MICRO = 150
DUR_BASE = 220
DUR_PANEL = 320


# =============================================================================
# 3) AKTIVNÍ ROLE
# =============================================================================
@dataclass
class RoleTokens:
    name: str
    accent: str
    accent_strong: str
    accent_press: str


STUDENT = RoleTokens("student", STUDENT_ACCENT, STUDENT_ACCENT_STRONG, STUDENT_ACCENT_PRESS)
TEACHER = RoleTokens("teacher", TEACHER_ACCENT, TEACHER_ACCENT_STRONG, TEACHER_ACCENT_PRESS)

# Globální aktivní role. Měň jen přes set_role().
_active_role: RoleTokens = STUDENT


def set_role(role: str) -> None:
    """Přepne aktivní roli ('student' | 'teacher'). Po volání znovu aplikuj
    paletu i stylesheet (viz apply_theme v theme.py)."""
    global _active_role
    _active_role = TEACHER if role == "teacher" else STUDENT


def active_role() -> RoleTokens:
    return _active_role


def accent() -> str:
    return _active_role.accent


def accent_strong() -> str:
    return _active_role.accent_strong


def accent_press() -> str:
    return _active_role.accent_press


def _rgba(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def accent_soft(alpha: float = 0.11) -> str:
    """Jemné accent pozadí (hover karet, soft chip)."""
    return _rgba(_active_role.accent, alpha)


# =============================================================================
# 4) QPALETTE (řeší světlo/tmu out-of-the-box, jako dnes)
# =============================================================================
def build_palette(dark: bool = False) -> QPalette:
    """Vytvoří QPalette pro daný režim. QSS používá palette() role,
    takže stačí vyměnit paletu a styl se přebarví."""
    n = DARK if dark else LIGHT
    p = QPalette()
    C = QColor
    p.setColor(QPalette.Window,           C(n["window"]))
    p.setColor(QPalette.WindowText,       C(n["text"]))
    p.setColor(QPalette.Base,             C(n["base"]))
    p.setColor(QPalette.AlternateBase,    C(n["alt_base"]))
    p.setColor(QPalette.Text,             C(n["text"]))
    p.setColor(QPalette.PlaceholderText,  C(n["text_3"]))
    p.setColor(QPalette.Button,           C(n["base"]))
    p.setColor(QPalette.ButtonText,       C(n["text"]))
    # mid / midlight / dark mapujeme na border systém
    p.setColor(QPalette.Midlight,         C(n["surface_2"]))
    p.setColor(QPalette.Mid,              C(n["border_strong"]))
    p.setColor(QPalette.Dark,             C(n["text_3"]))
    p.setColor(QPalette.Highlight,        C(_active_role.accent))
    p.setColor(QPalette.HighlightedText,  C("#ffffff"))
    # disabled
    p.setColor(QPalette.Disabled, QPalette.Text,       C(n["text_3"]))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, C(n["text_3"]))
    return p


# =============================================================================
# 5) QSS RENDER — doplní accent z aktivní role do šablony app.qss
# =============================================================================
# app.qss používá sentinely:  @ACCENT@  @ACCENT_STRONG@  @ACCENT_PRESS@
#                             @ACCENT_06@ @ACCENT_08@ @ACCENT_10@ @ACCENT_12@
#                             @ACCENT_16@ @ACCENT_25@ @ACCENT_30@
#                             @SUCCESS@ @WARNING@ @DANGER@ @CONSENT_BG@ @CONSENT_BORDER@
#                             @FONT@ @FONT_MONO@
def render_qss(template: str) -> str:
    """Doplní do QSS šablony hodnoty podle aktivní role. Volej při startu
    a po každém set_role()."""
    r = _active_role
    mapping = {
        "@ACCENT@":         r.accent,
        "@ACCENT_STRONG@":  r.accent_strong,
        "@ACCENT_PRESS@":   r.accent_press,
        "@ACCENT_06@":      _rgba(r.accent, 0.06),
        "@ACCENT_08@":      _rgba(r.accent, 0.08),
        "@ACCENT_10@":      _rgba(r.accent, 0.10),
        "@ACCENT_12@":      _rgba(r.accent, 0.12),
        "@ACCENT_16@":      _rgba(r.accent, 0.16),
        "@ACCENT_25@":      _rgba(r.accent, 0.25),
        "@ACCENT_30@":      _rgba(r.accent, 0.30),
        "@SUCCESS@":        SUCCESS,
        "@WARNING@":        WARNING,
        "@DANGER@":         DANGER,
        "@DANGER_10@":      _rgba(DANGER, 0.10),
        "@CONSENT_BG@":     CONSENT_BG,
        "@CONSENT_BORDER@": CONSENT_BORDER,
        "@FONT@":           FONT_STACK,
        "@FONT_MONO@":      FONT_MONO,
    }
    out = template
    for k, v in mapping.items():
        out = out.replace(k, v)
    return out
