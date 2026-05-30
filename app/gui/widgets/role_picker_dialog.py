"""Role picker — modální dialog před prvním spuštěním.

Uživatel vybírá mezi rolemi:
- student (Safe4Future modrá #205ca8) — výchozí, optimalizováno pro studium
- učitel (Original Teal #00897B) — pedagogický nástroj se 3 akčními kartami

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
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.gui.styles import tokens
from app.gui.widgets.icons import pixmap


class RolePickerDialog(QDialog):
    """Dialog pro výběr role. Vrací 'student' nebo 'teacher' přes chosen_role()."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kdo aplikaci používá?")
        self.setMinimumWidth(640)
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

        # Dvě hero karty
        cards = QHBoxLayout()
        cards.setSpacing(16)

        student_card = self._build_card(
            role="student",
            icon_name="graduation",
            accent=tokens.STUDENT_ACCENT,
            title_text="Jsem žák / student",
            desc=(
                "Z přednášek a hodin chci studijní body, "
                "definice a otázky ke zkoušení."
            ),
        )
        teacher_card = self._build_card(
            role="teacher",
            icon_name="school",
            accent=tokens.TEACHER_ACCENT,
            title_text="Jsem učitel/ka",
            desc=(
                "Z vlastních hodin chci testové otázky pro žáky "
                "a reflexi svého projevu."
            ),
        )

        cards.addWidget(student_card, 1)
        cards.addWidget(teacher_card, 1)
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
        card.setMinimumHeight(280)
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
