"""Empty state — zobrazí se v tabulce souborů, dokud uživatelka nic nepřidá.

Krátký 4-step tutoriál, který studentce ukáže celý workflow na první pohled.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

_STEPS = [
    ("1️⃣", "Přidej nahrávku", "Klikni '+ Přidat nahrávku' nahoře nebo přetáhni mp3/mp4/wav přímo do okna."),
    ("2️⃣", "Přidej slidy (volitelné)", "Pokud máš PDF nebo PPTX z přednášky, přidej je — AI je propojí s přepisem."),
    ("3️⃣", "Napiš popis (pro režim s AI)", "Pár vět: co je to za přednášku, předmět, co od materiálu chceš (body ke zkoušce / souhrn / definice)."),
    ("4️⃣", "Vyber režim a spusť", "📝 'Jen přepis' = rychlé, offline, jen přesný text mluveného slova. 🤖 'Přepis + body z AI' = strukturované poznámky pro učení (potřebuje internet)."),
]


class EmptyStateWidget(QWidget):
    """Vizuálně viditelný 4-step tutoriál pro první spuštění (a kdykoliv prázdná tabulka)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)

        title = QLabel("Jak začít")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: 600; color: #205ca8;")
        layout.addWidget(title)

        for emoji, heading, body in _STEPS:
            row = QLabel(
                f'<table cellspacing="0"><tr>'
                f'<td valign="top" style="font-size: 22px; padding-right: 16px;">{emoji}</td>'
                f'<td valign="top">'
                f'<div style="font-size: 14px; font-weight: 600; color: #333;">{heading}</div>'
                f'<div style="font-size: 12px; color: #555; padding-top: 4px;">{body}</div>'
                f'</td></tr></table>'
            )
            row.setTextFormat(Qt.TextFormat.RichText)
            row.setWordWrap(True)
            row.setStyleSheet("padding: 6px;")
            layout.addWidget(row)

        layout.addStretch(1)
