"""Prompt editor — textarea + rychlé chipy. Bez heading, bez eyebrow.

Veřejné API: text(), set_text(value)
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.ai.prompts import PROMPT_TEMPLATES
from app.gui.styles import tokens

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

        # Combo šablon — předvyplní zadání podle toho, co uživatel chce vyrobit
        tpl_row = QHBoxLayout()
        tpl_row.setSpacing(8)
        tpl_label = QLabel("Co vyrobit:")
        tpl_label.setStyleSheet("font-size: 12.5px; color: palette(text);")
        tpl_row.addWidget(tpl_label)

        self._template_combo = QComboBox()
        self._template_combo.setMinimumHeight(32)
        self._template_combo.addItem("— vlastní zadání —", userData="")
        for key, tpl in PROMPT_TEMPLATES.items():
            self._template_combo.addItem(tpl["label"], userData=key)
        self._template_combo.currentIndexChanged.connect(self._on_template_changed)
        tpl_row.addWidget(self._template_combo, 1)
        outer.addLayout(tpl_row)

        self._edit = QPlainTextEdit()
        self._edit.setPlaceholderText(
            "Volitelně: o čem ta přednáška je? Pomáhá to AI udělat lepší poznámky."
        )
        self._edit.setMinimumHeight(80)
        self._edit.setMaximumHeight(120)
        outer.addWidget(self._edit, 1)

        self._chips: list[QPushButton] = []
        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)
        for txt in _CHIPS:
            chip = QPushButton(txt)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            chip.clicked.connect(lambda _checked=False, t=txt: self._append_hint(t))
            chips_row.addWidget(chip)
            self._chips.append(chip)
        chips_row.addStretch(1)
        outer.addLayout(chips_row)

        # Aplikuj inline styly s aktuálním accentem.
        self._apply_inline_styles()

    def _apply_inline_styles(self) -> None:
        accent = tokens.accent()
        accent_soft = tokens.accent_soft(0.06)
        self._edit.setStyleSheet(
            "QPlainTextEdit { background: palette(base); "
            "border: 1px solid palette(midlight); border-radius: 10px; "
            "padding: 12px 14px; font-size: 13px; }"
            f"QPlainTextEdit:focus {{ border: 1px solid {accent}; }}"
        )
        for chip in self._chips:
            chip.setStyleSheet(
                "QPushButton { background: palette(alternate-base); "
                "border: 1px solid palette(midlight); border-radius: 999px; "
                "padding: 4px 12px; font-size: 11.5px; color: palette(text); }"
                f"QPushButton:hover {{ border-color: {accent}; "
                f"color: {accent}; background: {accent_soft}; }}"
            )

    def refresh_accent(self) -> None:
        self._apply_inline_styles()

    def _on_template_changed(self, _index: int) -> None:
        """Po výběru šablony předvyplní zadání. Prázdná volba ('vlastní') nic nemění."""
        key = self._template_combo.currentData()
        if not key:
            return
        from app.core.ai.prompts import template_prompt

        prompt = template_prompt(key)
        if prompt:
            self._edit.setPlainText(prompt)

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
