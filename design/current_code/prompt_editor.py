"""Textové pole pro popis/instrukce uživatele s placeholder + nápovědou."""

from __future__ import annotations

from PySide6.QtWidgets import QGroupBox, QPlainTextEdit, QVBoxLayout, QWidget


class PromptEditor(QGroupBox):
    """GroupBox s velkým textovým polem."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Popis / instrukce pro AI", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)

        self._edit = QPlainTextEdit()
        self._edit.setPlaceholderText(
            "Napiš pár vět: co jsou tyto soubory, který předmět a téma, jaký výstup chceš.\n\n"
            "Příklad: 'Toto je přednáška z makroekonomie, semestr jaro 2026, prof. Novotný. "
            "Téma: monetární politika ČNB. Chci body ke zkoušce + definice klíčových pojmů.'"
        )
        self._edit.setMinimumHeight(110)
        layout.addWidget(self._edit)

    def text(self) -> str:
        return self._edit.toPlainText().strip()

    def set_text(self, value: str) -> None:
        self._edit.setPlainText(value)
