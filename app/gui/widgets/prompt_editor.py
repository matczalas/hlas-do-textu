"""Prompt editor — dropdown šablony + info o sekcích + textarea pro doplnění.

Veřejné API: text(), set_text(value), current_template_key(), set_template_key(key),
set_role(role), refresh_accent().

UX záměr:
- Dropdown "Co vyrobit" je primární — uživatel si vybere typ výstupu.
- Pod dropdown se okamžitě zobrazí, *jaké sekce* AI vyrobí ("Vyrobí: Hlavní body
  · Klíčové pojmy · Otázky · …"). Uživatel ví, co dostane, bez toho aby musel
  hádat z textu zadání.
- Textarea slouží jen na *doplnění* (jméno klienta, předmět, téma kapitoly,
  o čem to je). Šablonu nepřepisuje — pouze přidává kontext.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.ai.prompts import sections_for_template, templates_for_role
from app.gui.styles import tokens


class PromptEditor(QGroupBox):
    """Dropdown + info-lišta sekcí + textarea pro doplnění zadání.

    Šablony v dropdownu se filtrují podle role aplikace (`student` / `teacher`
    / `sales`) — viz `templates_for_role`.
    """

    def __init__(
        self,
        role: str = "student",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("", parent)
        self._role = role
        self.setObjectName("PromptCard")
        self.setStyleSheet(
            "QGroupBox#PromptCard { background: transparent; border: none; "
            "margin-top: 0; padding: 0; }"
            "QGroupBox#PromptCard::title { padding: 0; }"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        # ---- Řada: "Co vyrobit:" + dropdown ----
        tpl_row = QHBoxLayout()
        tpl_row.setSpacing(8)
        tpl_label = QLabel("Co vyrobit:")
        tpl_label.setStyleSheet("font-size: 12.5px; color: palette(text);")
        tpl_row.addWidget(tpl_label)

        self._template_combo = QComboBox()
        self._template_combo.setMinimumHeight(32)
        self._populate_templates()
        self._template_combo.currentIndexChanged.connect(self._on_template_changed)
        tpl_row.addWidget(self._template_combo, 1)
        outer.addLayout(tpl_row)

        # ---- Info-lišta: jaké sekce šablona vyrobí ----
        # Updatuje se s každou změnou dropdown výběru. Uživatel hned vidí,
        # co konkrétně AI vytvoří.
        self._sections_info = QLabel("")
        self._sections_info.setWordWrap(True)
        self._sections_info.setTextFormat(Qt.TextFormat.RichText)
        self._sections_info.setStyleSheet(
            "color: palette(placeholder-text); font-size: 11.5px; "
            "padding: 4px 10px; background: palette(alternate-base); "
            "border-radius: 8px;"
        )
        outer.addWidget(self._sections_info)

        # ---- Textarea pro doplnění zadání ----
        self._edit = QPlainTextEdit()
        self._edit.setPlaceholderText(
            "Doplnění zadání (volitelné) — kontext, který AI pomůže.\n"
            "Např. „Klient se jmenuje Novák, řeší hypotéku.“\n"
            "      „Hodina dějepisu, 8. třída, téma první světová válka.“\n"
            "      „Zaměř se hlavně na statistické metody.“"
        )
        self._edit.setMinimumHeight(96)
        self._edit.setMaximumHeight(140)
        outer.addWidget(self._edit, 1)

        # Apply inline styly + první update info-lišty
        self._apply_inline_styles()
        self._refresh_sections_info()

    # ------ Veřejné API ------

    def text(self) -> str:
        return self._edit.toPlainText().strip()

    def set_text(self, value: str) -> None:
        self._edit.setPlainText(value)

    def current_template_key(self) -> str:
        """Klíč aktuálně zvolené šablony z PROMPT_TEMPLATES.

        Vrací "" pokud uživatel vybral "— vlastní zadání —". Volající typicky
        spadne na "student" jako default.
        """
        return str(self._template_combo.currentData() or "")

    def set_template_key(self, key: str) -> None:
        """Vybere šablonu podle klíče. Pro neznámý klíč nic nedělá."""
        for i in range(self._template_combo.count()):
            if self._template_combo.itemData(i) == key:
                self._template_combo.setCurrentIndex(i)
                return

    def set_role(self, role: str) -> None:
        """Po změně role aplikace přefiltrovat dropdown."""
        if role == self._role:
            return
        self._role = role
        self._populate_templates()
        self._refresh_sections_info()

    def refresh_accent(self) -> None:
        self._apply_inline_styles()

    # ------ Internal ------

    def _populate_templates(self) -> None:
        """Naplní dropdown podle aktuální role."""
        self._template_combo.blockSignals(True)
        self._template_combo.clear()
        self._template_combo.addItem("— vlastní zadání —", userData="")
        for key, tpl in templates_for_role(self._role).items():
            self._template_combo.addItem(tpl["label"], userData=key)
        self._template_combo.blockSignals(False)

    def _on_template_changed(self, _index: int) -> None:
        """Po výběru šablony: předvyplní zadání + update info-lišty.

        Prázdná volba („vlastní zadání“) text nemění, jen aktualizuje info.
        """
        key = self._template_combo.currentData()
        if key:
            from app.core.ai.prompts import template_prompt

            prompt = template_prompt(key)
            if prompt:
                self._edit.setPlainText(prompt)
        self._refresh_sections_info()

    def _refresh_sections_info(self) -> None:
        """Update info-lišty pod dropdown podle aktuální šablony."""
        key = self.current_template_key()
        if not key:
            # Vlastní zadání — žádné garantované sekce
            self._sections_info.setText(
                "<i>Vlastní zadání — AI vytvoří strukturu podle tvého popisu níže.</i>"
            )
            return

        specs = sections_for_template(key)
        if not specs:
            self._sections_info.setText("")
            return

        titles = " · ".join(spec.title for spec in specs)
        self._sections_info.setText(
            f"<b>Vyrobí ({len(specs)} sekcí):</b> {titles}"
        )

    def _apply_inline_styles(self) -> None:
        accent = tokens.accent()
        self._edit.setStyleSheet(
            "QPlainTextEdit { background: palette(base); "
            "border: 1px solid palette(midlight); border-radius: 10px; "
            "padding: 12px 14px; font-size: 13px; }"
            f"QPlainTextEdit:focus {{ border: 1px solid {accent}; }}"
        )
