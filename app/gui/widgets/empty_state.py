"""Empty state — zobrazí se v tabulce souborů, dokud uživatelka nic nepřidá.

Krátký 4-step tutoriál, který studentce ukáže celý workflow na první pohled.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

_STEPS = [
    ("1", "Přidej nahrávku",
     "Klikni nahoře na 'Přidat nahrávku' nebo přetáhni mp3 / mp4 / wav / m4a přímo do okna."),
    ("2", "Přidej slidy (volitelné)",
     "Pokud máš k přednášce PDF nebo PPTX, přidej je — AI je propojí s přepisem."),
    ("3", "Napiš popis (jen pro režim s AI)",
     "Pár vět: co je to za přednášku, předmět, co od materiálu chceš (body ke zkoušce / souhrn / definice)."),
    ("4", "Vyber režim a spusť",
     "Jen přepis = rychlé, offline, jen přesný text mluveného slova.\n"
     "Přepis + body z AI = strukturované poznámky pro učení (potřebuje internet)."),
]


class EmptyStateWidget(QWidget):
    """4-step tutoriál pro nového uživatele — v dark i light mode čitelný."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 40, 60, 40)
        layout.setSpacing(18)

        title = QLabel("Jak začít")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: 700; color: #4a8fde;")
        layout.addWidget(title)

        subtitle = QLabel("4 kroky k vygenerování studijního materiálu z přednášky")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 13px; color: palette(text); padding-bottom: 8px;")
        layout.addWidget(subtitle)

        for number, heading, body in _STEPS:
            layout.addWidget(_make_step_row(number, heading, body))

        layout.addStretch(1)


def _make_step_row(number: str, heading: str, body: str) -> QWidget:
    row = QFrame()
    row.setStyleSheet(
        "QFrame { background-color: palette(alternate-base); border-radius: 8px; padding: 4px; }"
    )
    h = QHBoxLayout(row)
    h.setContentsMargins(16, 14, 16, 14)
    h.setSpacing(16)

    badge = QLabel(number)
    badge.setFixedSize(40, 40)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(
        "QLabel { background-color: #205ca8; color: white; border-radius: 20px; "
        "font-size: 18px; font-weight: 700; }"
    )
    h.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)

    text_box = QVBoxLayout()
    text_box.setSpacing(4)
    head_lbl = QLabel(heading)
    head_lbl.setStyleSheet("font-size: 15px; font-weight: 600; color: palette(text);")
    text_box.addWidget(head_lbl)

    body_lbl = QLabel(body)
    body_lbl.setWordWrap(True)
    body_lbl.setStyleSheet("font-size: 13px; color: palette(text);")
    text_box.addWidget(body_lbl)

    h.addLayout(text_box, 1)
    return row
