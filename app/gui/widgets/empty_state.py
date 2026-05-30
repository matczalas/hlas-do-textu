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
        flow = QHBoxLayout()
        flow.setSpacing(4)
        flow.addStretch(1)
        flow.addWidget(_FlowIcon("mic", "Nahrávka"))
        flow.addWidget(_Arrow())
        flow.addWidget(_FlowIcon("sparkles", "AI body"))
        flow.addWidget(_Arrow())
        flow.addWidget(_FlowIcon("document", "Word"))
        flow.addStretch(1)
        outer.addLayout(flow)

        outer.addStretch(3)


class _FlowIcon(QWidget):
    def __init__(self, name: str, caption: str) -> None:
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        bubble = QLabel()
        bubble.setPixmap(pixmap(name, size=24, color=tokens.accent()))
        bubble.setFixedSize(56, 56)
        bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bubble.setStyleSheet(
            f"QLabel {{ background: {tokens.accent_soft(0.10)}; border-radius: 14px; }}"
        )
        v.addWidget(bubble, 0, Qt.AlignmentFlag.AlignHCenter)

        cap = QLabel(caption)
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cap.setStyleSheet("color: palette(placeholder-text); font-size: 12px;")
        v.addWidget(cap)


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
