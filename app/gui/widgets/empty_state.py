"""Empty state — jedna věta + tři piktogramy ukazující flow.

Žádný onboarding text. Šipka vzhůru do drop zóny.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.gui.styles import tokens
from app.gui.widgets.icons import pixmap


class EmptyStateWidget(QWidget):
    """Maximálně tichý empty state — text rezervuju pro to, co fakt pomůže."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(2)

        # Hlavní message — jedna věta
        headline = QLabel("Přetáhni přednášku nahoru")
        f = QFont()
        f.setPointSize(18)
        f.setWeight(QFont.Weight.DemiBold)
        headline.setFont(f)
        headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        headline.setStyleSheet("color: palette(text);")
        outer.addWidget(headline)

        sub = QLabel("MP3 · MP4 · WAV · M4A  —  případně i PDF nebo PPTX se slidy")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("color: palette(placeholder-text); font-size: 12.5px;")
        outer.addWidget(sub)

        outer.addSpacing(28)

        # Flow piktogramy:  mic → sparkles → document
        # Uložíme reference, ať můžeme volat refresh_accent() po role switch.
        self._flow_icons: list[_FlowIcon] = []
        flow = QHBoxLayout()
        flow.setSpacing(4)
        flow.addStretch(1)
        for name, caption in [
            ("mic", "Nahrávka"),
            ("sparkles", "AI body"),
            ("document", "Word"),
        ]:
            icon_widget = _FlowIcon(name, caption)
            self._flow_icons.append(icon_widget)
            flow.addWidget(icon_widget)
            if name != "document":
                flow.addWidget(_Arrow())
        flow.addStretch(1)
        outer.addLayout(flow)

        outer.addStretch(3)

    def refresh_accent(self) -> None:
        """Po změně role přebarví flow ikony na nový accent."""
        for ico in self._flow_icons:
            ico.refresh_accent()


class _FlowIcon(QWidget):
    def __init__(self, name: str, caption: str) -> None:
        super().__init__()
        self._icon_name = name
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        self._bubble = QLabel()
        self._bubble.setFixedSize(56, 56)
        self._bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self._bubble, 0, Qt.AlignmentFlag.AlignHCenter)

        cap = QLabel(caption)
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cap.setStyleSheet("color: palette(placeholder-text); font-size: 12px;")
        v.addWidget(cap)

        self._apply_inline_styles()

    def _apply_inline_styles(self) -> None:
        accent = tokens.accent()
        self._bubble.setPixmap(pixmap(self._icon_name, size=24, color=accent))
        self._bubble.setStyleSheet(
            f"QLabel {{ background: {tokens.accent_soft(0.10)}; border-radius: 14px; }}"
        )

    def refresh_accent(self) -> None:
        self._apply_inline_styles()


class _Arrow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(48)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 22)  # zarovnání s bubble středy
        lbl = QLabel("›")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: palette(mid); font-size: 28px; font-weight: 300;")
        v.addWidget(lbl)
