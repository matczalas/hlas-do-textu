"""Role picker — modální dialog před prvním spuštěním.

Uživatel vybírá roli aplikace (student / učitel / sales / podcast / HR /
kouč / spolky). Role řídí accent barvu a nabídku šablon. Od v1.13 je karet 7
→ mřížka 4×2 místo jedné řady.

Výsledek se uloží do AppSettings.app_role a je možné ji kdykoliv změnit
v Nastavení. Po výběru se zavolá theme.apply_theme() s novou rolí.

Veřejné API: __init__(parent=None), exec() -> DialogCode, chosen_role -> str
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.gui.styles import tokens
from app.gui.widgets.icons import pixmap

# Centrální definice rolí — sdílí ji picker (karty) i hlavička MainWindow
# (přepínací čip). Pořadí = pořadí karet v mřížce.
ROLE_DEFS: list[dict[str, str]] = [
    {"role": "student", "icon": "graduation", "accent": tokens.STUDENT_ACCENT,
     "short": "Student", "title": "Jsem žák / student",
     "desc": "Z přednášek chci studijní body, definice a otázky ke zkoušení."},
    {"role": "teacher", "icon": "school", "accent": tokens.TEACHER_ACCENT,
     "short": "Učitel/ka", "title": "Jsem učitel/ka",
     "desc": "Z hodin chci testové otázky pro žáky a reflexi projevu."},
    {"role": "sales", "icon": "clipboard", "accent": tokens.SALES_ACCENT,
     "short": "Sales / poradce", "title": "Jsem poradce / sales",
     "desc": "Ze schůzek chci úkoly, data o klientovi a další termín."},
    {"role": "podcast", "icon": "mic", "accent": tokens.PODCAST_ACCENT,
     "short": "Podcasty", "title": "Točím rozhovory / podcast",
     "desc": "Chci show notes, kapitoly, citáty a článek z rozhovoru."},
    {"role": "hr", "icon": "users", "accent": tokens.HR_ACCENT,
     "short": "HR & nábor", "title": "Dělám HR / nábor",
     "desc": "Z pohovorů chci zápisy, hodnocení a dohodnuté kroky."},
    {"role": "coach", "icon": "target", "accent": tokens.COACH_ACCENT,
     "short": "Kouč", "title": "Jsem kouč",
     "desc": "Ze sezení chci poznámky, kroky klienta a přípravu na další."},
    {"role": "spolek", "icon": "building", "accent": tokens.SPOLEK_ACCENT,
     "short": "Spolky & SVJ", "title": "Vedu spolek / SVJ",
     "desc": "Ze schůzí chci zápisy s usneseními, hlasováním a úkoly."},
]


def role_def(role: str) -> dict[str, str]:
    """Vrátí definici role podle klíče (fallback = student)."""
    for d in ROLE_DEFS:
        if d["role"] == role:
            return d
    return ROLE_DEFS[0]


class RolePickerDialog(QDialog):
    """Dialog pro výběr role. Vrací klíč role přes chosen_role()."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kdo aplikaci používá?")
        # 7 karet v mřížce 4×2 — šířka pro 4 sloupce.
        self.setMinimumWidth(980)
        self.setModal(True)
        # Bez křížku v rohu — uživatel musí vybrat
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        self._chosen_role: str = "student"

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 32, 36, 28)
        root.setSpacing(12)

        title = QLabel("Kdo aplikaci používá?")
        f = QFont()
        f.setPointSize(20)
        f.setWeight(QFont.Weight.DemiBold)
        title.setFont(f)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        sub = QLabel(
            "Podle role přizpůsobíme hlavní obrazovku. "
            "Změníš ji kdykoliv v Nastavení."
        )
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("color: palette(placeholder-text); font-size: 13px;")
        root.addWidget(sub)

        root.addSpacing(12)

        # 7 karet v mřížce 4×2 (poslední buňka prázdná)
        cards = QGridLayout()
        cards.setSpacing(14)

        for i, d in enumerate(ROLE_DEFS):
            card = self._build_card(
                role=d["role"],
                icon_name=d["icon"],
                accent=d["accent"],
                title_text=d["title"],
                desc=d["desc"],
            )
            cards.addWidget(card, i // 4, i % 4)
        # Sloupce roztahovat rovnoměrně
        for col in range(4):
            cards.setColumnStretch(col, 1)
        root.addLayout(cards)

    # ------ Public API ------

    def chosen_role(self) -> str:
        return self._chosen_role

    # ------ Internal ------

    def _build_card(
        self,
        *,
        role: str,
        icon_name: str,
        accent: str,
        title_text: str,
        desc: str,
    ) -> QFrame:
        """Vyrobí klikatelnou kartu pro výběr role."""
        card = QFrame()
        card.setObjectName("RoleCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        # 230 místo 280 — od v1.13 jsou karty ve dvou řadách (7 rolí),
        # vyšší karty by dialog vyhnaly přes výšku menších notebooků.
        card.setMinimumHeight(230)
        card.setStyleSheet(
            f"QFrame#RoleCard {{ background: palette(base); "
            f"border: 1.5px solid palette(mid); border-radius: 16px; }}"
            f"QFrame#RoleCard:hover {{ border-color: {accent}; }}"
        )

        # Klik na kartu = výběr role
        def on_click(_event):
            self._chosen_role = role
            self.accept()

        card.mousePressEvent = on_click  # type: ignore[method-assign]

        v = QVBoxLayout(card)
        v.setContentsMargins(28, 28, 28, 28)
        v.setSpacing(14)

        # Ikona v barevném kruhu
        icon_lbl = QLabel()
        icon_lbl.setPixmap(pixmap(icon_name, size=40, color="#ffffff"))
        icon_lbl.setFixedSize(80, 80)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(
            f"QLabel {{ background: {accent}; border-radius: 24px; }}"
        )
        icon_wrap = QHBoxLayout()
        icon_wrap.addStretch(1)
        icon_wrap.addWidget(icon_lbl)
        icon_wrap.addStretch(1)
        v.addLayout(icon_wrap)

        # Titulek
        name = QLabel(title_text)
        f = QFont()
        f.setPointSize(15)
        f.setWeight(QFont.Weight.DemiBold)
        name.setFont(f)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet("color: palette(text);")
        v.addWidget(name)

        # Popis
        d = QLabel(desc)
        d.setWordWrap(True)
        d.setAlignment(Qt.AlignmentFlag.AlignCenter)
        d.setStyleSheet("color: palette(placeholder-text); font-size: 12.5px;")
        v.addWidget(d)

        v.addStretch(1)

        # CTA stripe (vizuální tip — celá karta je klik)
        cta = QLabel("Pokračovat  →")
        cta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cta.setStyleSheet(
            f"color: {accent}; font-size: 12.5px; font-weight: 700;"
        )
        v.addWidget(cta)

        return card
