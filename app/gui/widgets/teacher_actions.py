"""Učitelská sekce — 3 akční karty + segmented "Režim testu".

Zobrazuje se v editoru pouze pokud settings.app_role == "teacher".

Sekce:
  1 · Nahrávka hodiny     — řeší stávající drop zone + source table
  2 · Režim testu         — segmented Ústní / Písemka / Procvičování
  3 · Co vyrobit          — 3 karty: Otázky / Materiály / Reflexe

Klik na akční kartu vyemituje action_requested(prompt_key) → MainWindow
předvyplní prompt editor a spustí pipeline (JobMode.FULL).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
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
from app.gui.widgets.icons import icon, icon_size, pixmap

TEST_MODES = ("Ústní", "Písemka", "Procvičování")

# Mapování segmentu na konkrétní šablonu otázek v prompts.py
_QUESTIONS_PROMPT_BY_MODE = {
    "Ústní":        "teacher_questions_oral",
    "Písemka":      "teacher_questions_written",
    "Procvičování": "teacher_questions_practice",
}


class _SectionLabel(QLabel):
    """Očíslovaný section label — '1 · Nahrávka hodiny' v accent barvě."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("SectionLabel")


class _Segmented(QWidget):
    """Pill-style segmentovaný přepínač. Emit value_changed(text)."""

    value_changed = Signal(str)

    def __init__(self, options: tuple[str, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: list[QPushButton] = []
        self._value: str = options[0] if options else ""

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        for opt in options:
            btn = QPushButton(opt)
            btn.setObjectName("SegmentedBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("checked", opt == self._value)
            btn.clicked.connect(lambda _checked=False, o=opt: self._pick(o))
            row.addWidget(btn)
            self._buttons.append(btn)
        row.addStretch(1)
        self._restyle()

    def value(self) -> str:
        return self._value

    def _pick(self, option: str) -> None:
        if option == self._value:
            return
        self._value = option
        self._restyle()
        self.value_changed.emit(option)

    def _restyle(self) -> None:
        """Propíše property 'checked' do všech tlačítek a force-repolish QSS."""
        for btn in self._buttons:
            is_on = btn.text() == self._value
            btn.setProperty("checked", is_on)
            btn.setChecked(is_on)
            btn.style().unpolish(btn)
            btn.style().polish(btn)


class _ActionCard(QFrame):
    """Jedna akční karta: ikona, titulek, popis, CTA s šipkou.

    Disabled stav (no recording): ztlumený + dashed border + krátká hláška.
    """

    clicked = Signal(str)   # emituje prompt_key z PROMPT_TEMPLATES

    def __init__(
        self,
        *,
        icon_name: str,
        title: str,
        description: str,
        cta_label: str,
        prompt_key: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._prompt_key = prompt_key
        self._enabled_logical = True   # vlastní stav, ne Qt setEnabled

        self.setObjectName("ActionCard")
        self.setProperty("disabled", False)
        self.setMinimumHeight(168)

        accent = tokens.accent()
        accent_soft = tokens.accent_soft(0.10)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(16)

        # Ikona v accent kruhu
        icon_lbl = QLabel()
        icon_lbl.setPixmap(pixmap(icon_name, size=26, color=accent))
        icon_lbl.setFixedSize(56, 56)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(
            f"QLabel {{ background: {accent_soft}; border-radius: 14px; }}"
        )
        outer.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignTop)

        # Texty
        text_col = QVBoxLayout()
        text_col.setSpacing(6)

        self._title_lbl = QLabel(title)
        f = QFont()
        f.setPointSize(14)
        f.setWeight(QFont.Weight.DemiBold)
        self._title_lbl.setFont(f)
        text_col.addWidget(self._title_lbl)

        self._desc_lbl = QLabel(description)
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setStyleSheet("color: palette(placeholder-text); font-size: 12.5px;")
        text_col.addWidget(self._desc_lbl)

        # Disabled note (skrytý, dokud nedostaneme disabled)
        self._disabled_note = QLabel("Nejdřív přidej nahrávku hodiny.")
        self._disabled_note.setStyleSheet(
            f"color: {tokens.WARNING}; font-size: 11.5px; font-weight: 600;"
        )
        self._disabled_note.hide()
        text_col.addWidget(self._disabled_note)

        text_col.addStretch(1)

        # CTA
        cta_row = QHBoxLayout()
        cta_row.addStretch(1)
        self._cta_btn = QPushButton(cta_label)
        self._cta_btn.setObjectName("Primary")
        self._cta_btn.setIcon(icon("arrow-right", size=14, color="#ffffff"))
        self._cta_btn.setIconSize(icon_size(14))
        self._cta_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cta_btn.clicked.connect(lambda: self.clicked.emit(self._prompt_key))
        cta_row.addWidget(self._cta_btn)
        text_col.addLayout(cta_row)

        outer.addLayout(text_col, 1)

    def set_card_enabled(self, enabled: bool) -> None:
        """Přepne kartu mezi normálním a "disabled" (no recording) stavem."""
        if enabled == self._enabled_logical:
            return
        self._enabled_logical = enabled
        self.setProperty("disabled", not enabled)
        self._cta_btn.setEnabled(enabled)
        self._disabled_note.setVisible(not enabled)
        # Repolish, ať se app.qss [disabled="true"] varianta propíše
        self.style().unpolish(self)
        self.style().polish(self)

    def update_prompt_key(self, prompt_key: str) -> None:
        """Pro 'Otázky' kartu — měníme klíč podle vybraného režimu testu."""
        self._prompt_key = prompt_key


class TeacherActionsWidget(QWidget):
    """Učitelská sekce: section labels + segmented + 3 karty.

    Veřejné API:
        action_requested = Signal(str)   — emituje prompt_key
        set_has_recording(bool)          — povolí / zakáže akční karty
    """

    action_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        # Sekce 1 (Nahrávka hodiny) řeší drop zone + source table v MainWindow,
        # její section label je nad nimi. Tady jen sekce 2 a 3.

        # ---- 2 · Režim testu (segmented) ----
        outer.addWidget(_SectionLabel("2 · Režim testu"))
        self._segmented = _Segmented(TEST_MODES)
        self._segmented.value_changed.connect(self._on_test_mode_changed)
        outer.addWidget(self._segmented)

        # ---- 3 · Co vyrobit (3 karty) ----
        outer.addWidget(_SectionLabel("3 · Co vyrobit"))

        # Karta "Otázky" — prompt_key se mění podle režimu testu
        self._questions_card = _ActionCard(
            icon_name="clipboard",
            title="Otázky vhodné k testu",
            description=(
                "Sada otázek pro žáky podle vybraného režimu (ústní / písemka / "
                "procvičování). Připravené k tisku i do sešitu."
            ),
            cta_label="Vytvořit",
            prompt_key=_QUESTIONS_PROMPT_BY_MODE[TEST_MODES[0]],
        )
        self._questions_card.clicked.connect(self.action_requested.emit)
        outer.addWidget(self._questions_card)

        # Karta "Materiály pro studenty"
        materials_card = _ActionCard(
            icon_name="send",
            title="Materiály k zaslání pro studenty",
            description=(
                "Shrnutí a studijní body z hodiny ve formátu, který rovnou pošleš "
                "žákům (Word). Vhodné i pro nepřítomné nebo opakování doma."
            ),
            cta_label="Připravit",
            prompt_key="teacher_materials",
        )
        materials_card.clicked.connect(self.action_requested.emit)
        outer.addWidget(materials_card)

        # Karta "Reflexe hodiny"
        reflection_card = _ActionCard(
            icon_name="reflect",
            title="Reflexe hodiny",
            description=(
                "Upřímná zpětná vazba k tvému projevu: tempo, výplňová slova, "
                "dynamika, délka monologů. Konkrétní příklady z hodiny."
            ),
            cta_label="Spustit",
            prompt_key="teacher_reflection",
        )
        reflection_card.clicked.connect(self.action_requested.emit)
        outer.addWidget(reflection_card)

        self._cards = [self._questions_card, materials_card, reflection_card]
        # Default: žádná nahrávka → karty disabled
        self.set_has_recording(False)

    # ------ Public API ------

    def set_has_recording(self, has: bool) -> None:
        """Přepne karty mezi 'připravené' a 'čekám na nahrávku'."""
        for card in self._cards:
            card.set_card_enabled(has)

    def selected_test_mode(self) -> str:
        return self._segmented.value()

    # ------ Internal ------

    def _on_test_mode_changed(self, mode: str) -> None:
        """Při změně režimu testu se přepne prompt klíč u "Otázky" karty."""
        prompt_key = _QUESTIONS_PROMPT_BY_MODE.get(mode, "teacher_questions_oral")
        self._questions_card.update_prompt_key(prompt_key)
