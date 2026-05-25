"""Prompt editor — textarea + rychlé chipy. Bez heading, bez eyebrow.

Veřejné API: text(), set_text(value)
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

ACCENT = "#205ca8"

_CHIPS = [
    "Body ke zkoušce",
    "Souhrn",
    "Definice pojmů",
]


class PromptEditor(QGroupBox):
    """Textarea + rychlé chipy. Žádný heading — placeholder vysvětluje."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("", parent)
        self.setObjectName("PromptCard")
        self.setStyleSheet(
            "QGroupBox#PromptCard { background: transparent; border: none; "
            "margin-top: 0; padding: 0; }"
            "QGroupBox#PromptCard::title { padding: 0; }"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self._edit = QPlainTextEdit()
        self._edit.setPlaceholderText(
            "Volitelně: o čem ta přednáška je? Pomáhá to AI udělat lepší poznámky."
        )
        self._edit.setMinimumHeight(80)
        self._edit.setMaximumHeight(120)
        self._edit.setStyleSheet(
            "QPlainTextEdit { background: palette(base); "
            "border: 1px solid palette(midlight); border-radius: 10px; "
            "padding: 12px 14px; font-size: 13px; }"
            "QPlainTextEdit:focus { border: 1px solid " + ACCENT + "; }"
        )
        outer.addWidget(self._edit, 1)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)
        for txt in _CHIPS:
            chip = QPushButton(txt)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            chip.setStyleSheet(
                "QPushButton { background: palette(alternate-base); "
                "border: 1px solid palette(midlight); border-radius: 999px; "
                "padding: 4px 12px; font-size: 11.5px; color: palette(text); }"
                "QPushButton:hover { border-color: " + ACCENT + "; "
                "color: " + ACCENT + "; background: rgba(32,92,168,0.06); }"
            )
            chip.clicked.connect(lambda _checked=False, t=txt: self._append_hint(t))
            chips_row.addWidget(chip)
        chips_row.addStretch(1)
        outer.addLayout(chips_row)

    def text(self) -> str:
        return self._edit.toPlainText().strip()

    def set_text(self, value: str) -> None:
        self._edit.setPlainText(value)

    def _append_hint(self, hint: str) -> None:
        existing = self._edit.toPlainText().strip()
        if hint.lower() in existing.lower():
            return
        if existing:
            self._edit.setPlainText(f"{existing}\n{hint}.")
        else:
            self._edit.setPlainText(f"{hint}.")
        cursor = self._edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._edit.setTextCursor(cursor)
        self._edit.setFocus()
