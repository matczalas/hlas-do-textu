"""Projects home — vstupní obrazovka aplikace.

Místo aby se app otvírala rovnou v editoru, ukáže se nejdřív seznam dříve
vytvořených projektů (recent_outputs ze settings). Klik na projekt otevře
soubor v defaultní aplikaci, klik na "Nový projekt" přepne na editor.

Prázdný stav: kruh s ikonou, headline "Zatím tu nic není" a jedno CTA.

Veřejné API:
    project_opened = Signal(Path)     — klik na existující projekt
    new_project_requested = Signal()  — klik na "Nový projekt"
    refresh(recent_outputs: list[str])
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.gui.styles import tokens
from app.gui.widgets.icons import icon, icon_size, pixmap


class _ProjectCard(QPushButton):
    """Klikatelná karta jednoho projektu — titul, datum, meta, file chips."""

    def __init__(
        self,
        *,
        title: str,
        date_str: str,
        meta: str,
        path: Path,
        chips: list[tuple[str, str]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ProjectCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(str(path))

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(6)

        # Top: document ikona vlevo + (vpravo) clock ikona + datum
        top = QHBoxLayout()
        top.setSpacing(8)

        self._doc_icon = QLabel()
        self._doc_icon.setFixedSize(20, 20)
        top.addWidget(self._doc_icon)
        top.addStretch(1)

        # Datum s clock ikonou (dle prototypu)
        date_wrap = QHBoxLayout()
        date_wrap.setSpacing(4)
        clock_icon = QLabel()
        clock_icon.setPixmap(pixmap("clock", size=11, color="#9aa7b6"))
        clock_icon.setFixedSize(13, 13)
        date_wrap.addWidget(clock_icon)
        date_lbl = QLabel(date_str)
        date_lbl.setStyleSheet("color: palette(placeholder-text); font-size: 11.5px;")
        date_wrap.addWidget(date_lbl)
        top.addLayout(date_wrap)
        v.addLayout(top)

        # Titul
        title_lbl = QLabel(title)
        f = QFont()
        f.setPointSize(13)
        f.setWeight(QFont.Weight.DemiBold)
        title_lbl.setFont(f)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet("color: palette(text);")
        v.addWidget(title_lbl)

        # Meta řádek
        meta_lbl = QLabel(meta)
        meta_lbl.setStyleSheet("color: palette(placeholder-text); font-size: 12px;")
        v.addWidget(meta_lbl)

        # File-type chips (pill značky pro typy výstupních souborů)
        if chips:
            chips_row = QHBoxLayout()
            chips_row.setSpacing(6)
            for label, kind in chips:
                chip = QLabel(label)
                chip.setObjectName("ProjectChip")
                chip.setProperty("kind", kind)
                chips_row.addWidget(chip)
            chips_row.addStretch(1)
            v.addLayout(chips_row)

        v.addStretch(1)
        self._apply_inline_styles()

    def _apply_inline_styles(self) -> None:
        """Re-aplikuje accent-závislé prvky (document ikonu) po role switch."""
        self._doc_icon.setPixmap(pixmap("document", size=18, color=tokens.accent()))

    def refresh_accent(self) -> None:
        self._apply_inline_styles()


class _NewProjectCard(QPushButton):
    """Klikatelná dashed-border karta s "+" ikonou — vytvořit nový projekt."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("NewProjectCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(130)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)
        v.addStretch(1)

        # Plus ikona v accent kruhu
        plus_lbl = QLabel()
        plus_lbl.setPixmap(pixmap("plus", size=22, color=tokens.accent()))
        plus_lbl.setFixedSize(48, 48)
        plus_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plus_lbl.setStyleSheet(
            f"QLabel {{ background: {tokens.accent_soft(0.10)}; border-radius: 12px; }}"
        )
        plus_row = QHBoxLayout()
        plus_row.addStretch(1)
        plus_row.addWidget(plus_lbl)
        plus_row.addStretch(1)
        v.addLayout(plus_row)

        lbl = QLabel("Nový projekt")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont()
        f.setPointSize(13)
        f.setWeight(QFont.Weight.DemiBold)
        lbl.setFont(f)
        lbl.setStyleSheet(f"color: {tokens.accent()};")
        v.addWidget(lbl)

        v.addStretch(1)


class ProjectsHome(QWidget):
    """Domovská obrazovka — mřížka karet projektů + 'Nový projekt'.

    Pokud je seznam prázdný, ukáže se centrovaný empty state s jediným CTA.
    """

    project_opened = Signal(Path)
    new_project_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        # Hlavička: titul + meta + tlačítko "Nový projekt"
        self._head = QWidget()
        head_layout = QHBoxLayout(self._head)
        head_layout.setContentsMargins(0, 0, 0, 0)

        head_col = QVBoxLayout()
        head_col.setSpacing(2)
        title = QLabel("Moje projekty")
        f = QFont()
        f.setPointSize(20)
        f.setWeight(QFont.Weight.DemiBold)
        title.setFont(f)
        head_col.addWidget(title)
        self._count_label = QLabel("0 projektů")
        self._count_label.setStyleSheet("color: palette(placeholder-text); font-size: 12.5px;")
        head_col.addWidget(self._count_label)
        head_layout.addLayout(head_col)
        head_layout.addStretch(1)

        new_btn = QPushButton("Nový projekt")
        new_btn.setObjectName("Primary")
        new_btn.setIcon(icon("plus", size=14, color="#ffffff"))
        new_btn.setIconSize(icon_size(14))
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.clicked.connect(self.new_project_requested.emit)
        head_layout.addWidget(new_btn)

        root.addWidget(self._head)

        # Mřížka karet ve scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; }")

        self._grid_container = QWidget()
        self._grid = QGridLayout(self._grid_container)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(14)
        self._grid.setVerticalSpacing(14)
        self._scroll.setWidget(self._grid_container)
        root.addWidget(self._scroll, 1)

        # Empty state — skrytý dokud máme nějaký projekt
        self._empty = self._build_empty_state()
        self._empty.hide()
        root.addWidget(self._empty, 1)

    # ------ Public API ------

    def refresh(self, recent_outputs: list[str]) -> None:
        """Přerender mřížky podle aktuálních recent_outputs."""
        # Vyčistit grid
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

        valid_paths = self._filter_valid(recent_outputs)

        if not valid_paths:
            # Empty state
            self._head.hide()
            self._scroll.hide()
            self._empty.show()
            self._count_label.setText("0 projektů")
            return

        self._head.show()
        self._scroll.show()
        self._empty.hide()
        self._count_label.setText(
            f"{len(valid_paths)} projektů · vrať se ke kterémukoliv"
        )

        # Karty do mřížky 2 sloupců
        for index, path in enumerate(valid_paths):
            card = self._make_project_card(path)
            row = index // 2
            col = index % 2
            self._grid.addWidget(card, row, col)

        # "Nový projekt" karta jako poslední
        new_card = _NewProjectCard()
        new_card.clicked.connect(self.new_project_requested.emit)
        next_index = len(valid_paths)
        self._grid.addWidget(new_card, next_index // 2, next_index % 2)

        # Stretch poslední sloupec aby karty nevisely na konci
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)

    # ------ Internal ------

    @staticmethod
    def _filter_valid(recent: list[str]) -> list[Path]:
        """Vrátí jen existující cesty. Recent_outputs může obsahovat smazané."""
        out: list[Path] = []
        for s in recent:
            p = Path(s)
            if p.is_file():
                out.append(p)
        return out

    def _make_project_card(self, path: Path) -> _ProjectCard:
        try:
            mtime = path.stat().st_mtime
            date_str = datetime.fromtimestamp(mtime).strftime("%d. %m. %Y")
            size_kb = path.stat().st_size // 1024
            meta = f"{size_kb} KB · {path.suffix.lstrip('.').upper()}"
        except OSError:
            date_str = "—"
            meta = path.suffix.lstrip(".").upper()

        # Titulek z názvu souboru bez přípony, podtržítka / pomlčky na mezery
        title = path.stem.replace("_", " ").replace("-", " ")
        # Capitalize první písmeno
        if title:
            title = title[0].upper() + title[1:]

        # Chip pro hlavní soubor + scan sourozenců (sdílený základ názvu).
        # Mapování přípona → (label, kind):
        #   .docx → "Studijní body"  | accent
        #   .md   → "Prompt pro AI"  | teal
        #   .txt  → "Přepis"          | neutral
        chips: list[tuple[str, str]] = []
        seen_kinds: set[str] = set()
        chip_for = {
            ".docx": ("Studijní body", "accent"),
            ".md":   ("Prompt pro AI", "teal"),
            ".txt":  ("Přepis", "neutral"),
        }
        main_chip = chip_for.get(path.suffix.lower())
        if main_chip:
            chips.append(main_chip)
            seen_kinds.add(main_chip[0])

        # Sourozenecké soubory se stejným base name (např. foo.docx + foo.txt)
        try:
            base_stem = path.stem
            for sibling in path.parent.iterdir():
                if not sibling.is_file() or sibling == path:
                    continue
                # Match: stejný stem (po odečtení časového razítka v názvu)
                # nebo prefix shoda do podtržítka.
                sib_stem = sibling.stem
                if sib_stem == base_stem or sib_stem.startswith(base_stem):
                    sib_chip = chip_for.get(sibling.suffix.lower())
                    if sib_chip and sib_chip[0] not in seen_kinds:
                        chips.append(sib_chip)
                        seen_kinds.add(sib_chip[0])
        except OSError:
            pass

        card = _ProjectCard(
            title=title,
            date_str=date_str,
            meta=meta,
            path=path,
            chips=chips or None,
        )
        card.clicked.connect(lambda _checked=False, p=path: self.project_opened.emit(p))
        return card

    def _build_empty_state(self) -> QWidget:
        """Vystředěný empty state pro úplně nové uživatele."""
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.addStretch(2)

        # Velký kruh s ikonou audio (88px dle prototypu, perfect circle)
        circle = QLabel()
        circle.setPixmap(pixmap("audio", size=36, color=tokens.accent()))
        circle.setFixedSize(88, 88)
        circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        circle.setStyleSheet(
            f"QLabel {{ background: {tokens.accent_soft(0.10)}; border-radius: 44px; }}"
        )
        circle_row = QHBoxLayout()
        circle_row.addStretch(1)
        circle_row.addWidget(circle)
        circle_row.addStretch(1)
        v.addLayout(circle_row)

        v.addSpacing(20)

        title = QLabel("Zatím tu nic není")
        f = QFont()
        f.setPointSize(22)
        f.setWeight(QFont.Weight.Bold)
        title.setFont(f)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)

        sub = QLabel(
            "Pojď vytvořit svůj první projekt. Nahraješ přednášku nebo hodinu "
            "a uděláme z ní studijní materiál — najdeš ho tady pokaždé, "
            "když se vrátíš."
        )
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setMaximumWidth(520)
        sub.setStyleSheet("color: palette(placeholder-text); font-size: 13.5px;")
        sub_row = QHBoxLayout()
        sub_row.addStretch(1)
        sub_row.addWidget(sub)
        sub_row.addStretch(1)
        v.addLayout(sub_row)

        v.addSpacing(24)

        # CTA tlačítko
        cta = QPushButton("Vytvořit první projekt")
        cta.setObjectName("Primary")
        cta.setIcon(icon("plus", size=16, color="#ffffff"))
        cta.setIconSize(icon_size(16))
        cta.setCursor(Qt.CursorShape.PointingHandCursor)
        cta.setMinimumHeight(48)
        cta.setMinimumWidth(260)
        cta.clicked.connect(self.new_project_requested.emit)
        cta_row = QHBoxLayout()
        cta_row.addStretch(1)
        cta_row.addWidget(cta)
        cta_row.addStretch(1)
        v.addLayout(cta_row)

        v.addStretch(3)
        return wrap
