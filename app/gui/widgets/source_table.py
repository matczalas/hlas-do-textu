"""Tabulka importovaných zdrojů — typed pills, file ikony, soft styling.

Veřejné API:
    files_changed = Signal()
    add_sources(sources), sources() -> list, clear_all()
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from app.core.models import SourceFile, SourceKind
from app.gui.widgets.icons import icon, icon_size, pixmap

ACCENT = "#205ca8"


class _TypePill(QWidget):
    """Pill s ikonou + textem ('Nahrávka' / 'Slidy')."""

    def __init__(self, kind: SourceKind, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 12, 3)
        layout.setSpacing(6)

        if kind == SourceKind.AUDIO_VIDEO:
            ico_name = "audio"
            text = "Nahrávka"
            color = "#205ca8"
            bg = "rgba(32,92,168,0.10)"
        else:
            ico_name = "document"
            text = "Slidy"
            color = "#8b5a2b"
            bg = "rgba(139, 90, 43, 0.12)"

        ico = QLabel()
        ico.setPixmap(pixmap(ico_name, size=14, color=color))
        ico.setFixedSize(16, 16)
        layout.addWidget(ico)

        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {color}; font-size: 11.5px; font-weight: 600;")
        layout.addWidget(lbl)

        self.setStyleSheet(
            f"QWidget {{ background: {bg}; border-radius: 999px; }}"
        )
        self.setFixedHeight(24)


class _RemoveButton(QPushButton):
    """Tichý X button — viditelný spíš při hover, ale klikatelný vždy."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setIcon(icon("trash", size=15, color="#9a9a9a"))
        self.setIconSize(icon_size(15))
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Odebrat ze seznamu")
        self.setStyleSheet(
            "QPushButton { background: transparent; border: none; border-radius: 6px; }"
            "QPushButton:hover { background: rgba(216,70,70,0.10); }"
        )


class SourceTable(QTableWidget):
    """Tabulka 5 sloupců: #, Soubor, Typ, Štítek, Odebrat."""

    files_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sources: list[SourceFile] = []
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["#", "SOUBOR", "TYP", "ŠTÍTEK", ""])
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.verticalHeader().setDefaultSectionSize(46)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setFixedHeight(36)

        self.cellChanged.connect(self._on_cell_changed)
        self.setMinimumHeight(180)

        # Drobný hover hint na řádcích — barevný odstín
        self.setStyleSheet(self.styleSheet() + (
            "QTableWidget::item:hover { background: rgba(32,92,168,0.04); }"
        ))

    # ------ Public API ------

    def add_sources(self, sources: list[SourceFile]) -> None:
        if not sources:
            return
        existing_paths = {s.path for s in self._sources}
        for src in sources:
            if src.path in existing_paths:
                continue
            self._sources.append(src)
        self._rebuild()
        self.files_changed.emit()

    def sources(self) -> list[SourceFile]:
        return list(self._sources)

    def clear_all(self) -> None:
        self._sources.clear()
        self._rebuild()
        self.files_changed.emit()

    # ------ Internal ------

    def _rebuild(self) -> None:
        self.blockSignals(True)
        try:
            self.setRowCount(len(self._sources))
            for row, src in enumerate(self._sources):
                self._fill_row(row, src)
        finally:
            self.blockSignals(False)

    def _fill_row(self, row: int, src: SourceFile) -> None:
        # #
        idx_item = QTableWidgetItem(str(row + 1))
        idx_item.setFlags(idx_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        idx_item.setForeground(QColor("#9a9a9a"))
        self.setItem(row, 0, idx_item)

        # Soubor
        name_item = QTableWidgetItem("  " + src.path.name)
        name_item.setToolTip(str(src.path))
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, 1, name_item)

        # Typ — pill widget
        pill = _TypePill(src.kind)
        pill_wrap = QWidget()
        wl = QHBoxLayout(pill_wrap)
        wl.setContentsMargins(8, 0, 8, 0)
        wl.addWidget(pill)
        wl.addStretch(1)
        self.setCellWidget(row, 2, pill_wrap)
        # Prázdná item kvůli selection
        self.setItem(row, 2, QTableWidgetItem())

        # Štítek — editable
        label_item = QTableWidgetItem(src.label)
        label_item.setToolTip("Dvojklik pro úpravu štítku — používá se v poznámkách.")
        self.setItem(row, 3, label_item)

        # Remove
        remove_btn = _RemoveButton()
        remove_btn.clicked.connect(lambda _checked=False, p=src.path: self._remove(p))
        wrap = QWidget()
        wl2 = QHBoxLayout(wrap)
        wl2.setContentsMargins(4, 0, 8, 0)
        wl2.addStretch(1)
        wl2.addWidget(remove_btn)
        self.setCellWidget(row, 4, wrap)

    def _on_cell_changed(self, row: int, col: int) -> None:
        if col != 3:
            return
        if not (0 <= row < len(self._sources)):
            return
        item = self.item(row, 3)
        if item is None:
            # cellChanged může přijít během rebuildu, kdy item ještě/už neexistuje
            return
        new_label = (item.text() or "").strip()
        if not new_label:
            new_label = Path(self._sources[row].path).stem
            item.setText(new_label)
        self._sources[row].label = new_label

    def _remove(self, path) -> None:
        self._sources = [s for s in self._sources if s.path != path]
        self._rebuild()
        self.files_changed.emit()
