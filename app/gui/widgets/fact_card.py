"""FactCard — rotující kartička "Než to doběhne" během dlouhé pipeline.

Layout dle prototypu (running.jsx FactCard):

  ┌──────────────────────────────────────────────────────────┐
  │ [VTIP · VYSOKÁ ŠKOLA]                ✨ Než to doběhne   │
  │                                                            │
  │ "Kolik vysokoškoláků je potřeba na výměnu žárovky?         │
  │  Jeden — ale dostane za to 6 kreditů…"                     │
  │                                                            │
  │ • • ● • • • •                                Další ›       │
  └──────────────────────────────────────────────────────────┘

  - Category pill vlevo nahoře (accent text, uppercase)
  - "Než to doběhne" + sparkles ikona vpravo nahoře
  - Hlavní text wordwrap, 14px
  - Dot pagination dole (active = accent, ostatní = palette mid)
  - "Další ›" link vpravo dole

QTimer rotuje fakty 7s/fakt. Timer se pauzuje, když widget není visible.

API:
    FactCard(role: str)              — "student" / "teacher" → odpovídající FACTS
    next_fact()                       — manuálně posune
    set_role(role)                    — přepne na faktové pole jiné role
    refresh_accent()                  — přebarví accent prvky
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.gui.styles import tokens
from app.gui.widgets._fact_data import facts_for_role
from app.gui.widgets.icons import pixmap

_ROTATE_MS = 7000


class FactCard(QFrame):
    """Rotující kartička s fakty / triviálkami během běhu pipeline."""

    next_pressed = Signal()

    def __init__(self, role: str = "student", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FactCard")
        self._role = role
        self._facts = facts_for_role(role)
        self._index = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)

        # Top row: category pill vlevo, "Než to doběhne" + sparkles vpravo
        top = QHBoxLayout()
        top.setSpacing(8)
        self._category = QLabel("")
        self._category.setObjectName("FactCategory")
        top.addWidget(self._category)
        top.addStretch(1)

        self._while_icon = QLabel()
        self._while_icon.setPixmap(pixmap("sparkles", size=12, color="#9aa7b6"))
        self._while_icon.setFixedSize(14, 14)
        top.addWidget(self._while_icon)
        self._while_label = QLabel("Než to doběhne")
        self._while_label.setStyleSheet(
            "color: palette(placeholder-text); font-size: 11.5px; font-weight: 500;"
        )
        top.addWidget(self._while_label)
        outer.addLayout(top)

        # Hlavní text
        self._text = QLabel("")
        self._text.setWordWrap(True)
        f = QFont()
        f.setPointSize(13)
        self._text.setFont(f)
        self._text.setStyleSheet("color: palette(text); line-height: 1.5;")
        outer.addWidget(self._text)

        # Foot: dots vlevo, "Další ›" vpravo
        foot = QHBoxLayout()
        foot.setSpacing(6)

        self._dots_wrap = QWidget()
        self._dots_layout = QHBoxLayout(self._dots_wrap)
        self._dots_layout.setContentsMargins(0, 0, 0, 0)
        self._dots_layout.setSpacing(5)
        self._dots: list[QLabel] = []
        for _ in range(len(self._facts)):
            d = QLabel()
            d.setFixedSize(6, 6)
            self._dots.append(d)
            self._dots_layout.addWidget(d)
        foot.addWidget(self._dots_wrap)
        foot.addStretch(1)

        self._next_btn = QPushButton("Další ›")
        self._next_btn.setObjectName("Link")
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.clicked.connect(self._on_next_clicked)
        foot.addWidget(self._next_btn)
        outer.addLayout(foot)

        # Timer pro rotaci — pauza když není visible
        self._timer = QTimer(self)
        self._timer.setInterval(_ROTATE_MS)
        self._timer.timeout.connect(self._tick)

        self._apply_inline_styles()
        self._render_current()

    # ------ Public API ------

    def set_role(self, role: str) -> None:
        if role == self._role:
            return
        self._role = role
        self._facts = facts_for_role(role)
        self._index = 0
        # Rebuild dots pokud má jiná role jiný počet faktů
        while self._dots_layout.count():
            item = self._dots_layout.takeAt(0)
            w = item.widget() if item else None
            if w:
                w.deleteLater()
        self._dots.clear()
        for _ in range(len(self._facts)):
            d = QLabel()
            d.setFixedSize(6, 6)
            self._dots.append(d)
            self._dots_layout.addWidget(d)
        self._render_current()

    def next_fact(self) -> None:
        """Programmatically jump to next fact."""
        self._tick()

    def refresh_accent(self) -> None:
        self._apply_inline_styles()
        self._render_current()  # přebarví aktivní tečku + category pill

    # ------ Internal ------

    def _on_next_clicked(self) -> None:
        self.next_pressed.emit()
        self._tick()

    def _tick(self) -> None:
        if not self._facts:
            return
        self._index = (self._index + 1) % len(self._facts)
        self._render_current()
        # Restart timer (každý cyklus = 7s od posledního zobrazení)
        if self._timer.isActive():
            self._timer.start()

    def _render_current(self) -> None:
        if not self._facts:
            return
        cat, text = self._facts[self._index]
        self._category.setText(cat.upper())
        self._text.setText(text)
        # Dot states
        accent = tokens.accent()
        for i, dot in enumerate(self._dots):
            if i == self._index:
                dot.setStyleSheet(
                    f"QLabel {{ background: {accent}; border-radius: 3px; }}"
                )
            else:
                dot.setStyleSheet(
                    "QLabel { background: palette(mid); border-radius: 3px; }"
                )

    def _apply_inline_styles(self) -> None:
        accent = tokens.accent()
        # Card outer
        self.setStyleSheet(
            "QFrame#FactCard { background: palette(base); "
            "border: 1px solid palette(midlight); border-radius: 12px; }"
        )
        # Category pill — accent text, uppercase letterspacing
        self._category.setStyleSheet(
            f"QLabel#FactCategory {{ "
            f"color: {accent}; "
            "font-size: 10.5px; font-weight: 800; letter-spacing: 1.2px; "
            f"background: {tokens.accent_soft(0.10)}; "
            "padding: 3px 9px; border-radius: 999px; }"
        )
        # "Další ›" link button
        self._next_btn.setStyleSheet(
            "QPushButton#Link { background: transparent; border: none; "
            f"color: {accent}; padding: 2px 4px; font-weight: 600; font-size: 12px; }}"
            f"QPushButton#Link:hover {{ color: {tokens.accent_strong()}; "
            "text-decoration: underline; }"
        )

    # ------ Lifecycle ------

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._timer.stop()
