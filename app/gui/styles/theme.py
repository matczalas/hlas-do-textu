"""theme.py — aplikace vzhledu na QApplication.

Použití (v app entrypointu):

    from app.gui.styles import theme
    theme.apply_theme(app, role="student", dark=False)

Při přepnutí role (role picker / nastavení):

    theme.apply_theme(app, role="teacher", dark=is_dark)

To je všechno — accent (modrá/teal) i světlo/tma se propíšou do celé appky.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from . import tokens

_QSS_PATH = Path(__file__).with_name("app.qss")


def apply_theme(app: QApplication, role: str = "student", dark: bool = False) -> None:
    """Nastaví roli, paletu (světlo/tma) a vykreslí role-aware stylesheet."""
    tokens.set_role(role)
    app.setPalette(tokens.build_palette(dark=dark))
    template = _QSS_PATH.read_text(encoding="utf-8")
    app.setStyleSheet(tokens.render_qss(template))
