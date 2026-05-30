"""Wordmark — logo komponenta dle prototypu.

Glyph 34px (accent background + 9px radius + bílá mic ikona) + textový pár:
  - title 13pt DemiBold "Hlas do textu"
  - subtitle 9pt ("Studijní poznámky z přednášek" / "Pedagogický nástroj")

V hlavičkách:
  - StudentScreen / TeacherScreen editor: compact (jen glyph)
  - ProjectsHome: full (glyph + title + subtitle podle role)

Přepínání compact ↔ full za běhu přes set_compact().

API:
    __init__(subtitle=None, compact=False, parent=None)
    set_compact(bool)
    set_subtitle(text)
    refresh_accent()
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.gui.styles import tokens
from app.gui.widgets.icons import pixmap


class Wordmark(QWidget):
    """Logo + textový pár. Glyph v accent kruhu s mic ikonou."""

    def __init__(
        self,
        subtitle: str | None = None,
        *,
        compact: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(11)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Glyph — 34px zakulacený čtverec s mic ikonou
        self._glyph = QLabel()
        self._glyph.setFixedSize(34, 34)
        self._glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self._glyph)

        # Textový pár — vždy vyroben, viditelnost dle compact stavu
        self._text_wrap = QWidget()
        text_col = QVBoxLayout(self._text_wrap)
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)

        self._title = QLabel("Hlas do textu")
        tf = QFont()
        tf.setPointSize(13)
        tf.setWeight(QFont.Weight.DemiBold)
        self._title.setFont(tf)
        self._title.setStyleSheet("color: palette(text);")
        text_col.addWidget(self._title)

        self._subtitle = QLabel(subtitle or "")
        sf = QFont()
        sf.setPointSize(9)
        self._subtitle.setFont(sf)
        self._subtitle.setStyleSheet(
            "color: palette(placeholder-text); letter-spacing: 0.3px;"
        )
        self._subtitle.setVisible(bool(subtitle))
        text_col.addWidget(self._subtitle)

        row.addWidget(self._text_wrap)

        self._text_wrap.setVisible(not compact)
        self._apply_inline_styles()

    def _apply_inline_styles(self) -> None:
        """Re-aplikuje glyph styling s aktuálním accentem (role switch hook)."""
        accent = tokens.accent()
        # Mic ikona uvnitř accent kruhu — bílá
        self._glyph.setPixmap(pixmap("mic", size=18, color="#ffffff"))
        self._glyph.setStyleSheet(
            f"QLabel {{ background: {accent}; border-radius: 9px; }}"
        )

    def refresh_accent(self) -> None:
        """Veřejné API — MainWindow zavolá po změně role v Settings."""
        self._apply_inline_styles()

    def set_compact(self, compact: bool) -> None:
        """Přepne mezi compact (jen glyph) a full (glyph + text) módem."""
        self._text_wrap.setVisible(not compact)

    def set_subtitle(self, text: str) -> None:
        """Změní podtitul (např. při přepnutí role student↔učitel)."""
        self._subtitle.setText(text)
        self._subtitle.setVisible(bool(text))
