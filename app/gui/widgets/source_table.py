"""Tabulka importovaných souborů s editovatelnými štítky."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from app.core.models import SourceFile, SourceKind


class SourceTable(QTableWidget):
    """Tabulka 4 sloupců: #, Soubor, Typ, Štítek + tlačítko Odebrat."""

    files_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sources: list[SourceFile] = []
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["#", "Soubor", "Typ", "Štítek (klikni pro úpravu)", ""])
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked)
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.cellChanged.connect(self._on_cell_changed)
        self.setMinimumHeight(160)

    # ------ Veřejné API ------

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

    # ------ Vnitřní ------

    def _rebuild(self) -> None:
        self.blockSignals(True)
        try:
            self.setRowCount(len(self._sources))
            for row, src in enumerate(self._sources):
                self._fill_row(row, src)
        finally:
            self.blockSignals(False)

    def _fill_row(self, row: int, src: SourceFile) -> None:
        idx_item = QTableWidgetItem(str(row + 1))
        idx_item.setFlags(idx_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 0, idx_item)

        name_item = QTableWidgetItem(src.path.name)
        name_item.setToolTip(str(src.path))
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, 1, name_item)

        kind_label = "Nahrávka" if src.kind == SourceKind.AUDIO_VIDEO else "Slidy"
        type_item = QTableWidgetItem(kind_label)
        type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 2, type_item)

        label_item = QTableWidgetItem(src.label)
        self.setItem(row, 3, label_item)

        remove_btn = QPushButton("Odebrat")
        remove_btn.setFlat(True)
        remove_btn.clicked.connect(lambda _checked=False, p=src.path: self._remove(p))
        self.setCellWidget(row, 4, remove_btn)

    def _on_cell_changed(self, row: int, col: int) -> None:
        if col != 3:
            return
        if 0 <= row < len(self._sources):
            new_label = (self.item(row, 3).text() or "").strip()
            if not new_label:
                new_label = Path(self._sources[row].path).stem
                self.item(row, 3).setText(new_label)
            self._sources[row].label = new_label

    def _remove(self, path) -> None:
        self._sources = [s for s in self._sources if s.path != path]
        self._rebuild()
        self.files_changed.emit()
