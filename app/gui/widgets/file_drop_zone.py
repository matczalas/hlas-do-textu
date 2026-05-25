"""Drop zóna — jedna věta a dvě tlačítka. Žádný subtitle.

Veřejné API:
    sources_added = Signal(list)
    set_last_dir(path: str)
    @property last_dir
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import AUDIO_VIDEO_EXTENSIONS, PRESENTATION_EXTENSIONS
from app.core.models import SourceFile, SourceKind
from app.gui.widgets.icons import icon, icon_size, pixmap

ACCENT = "#205ca8"


class FileDropZone(QFrame):
    """Velká drop zóna s jasným 'Drag or Find File' sdělením."""

    sources_added = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setProperty("active", False)
        self.setMinimumHeight(180)
        self._last_dir: str = str(Path.home())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 26, 24, 22)
        outer.setSpacing(8)

        # Velká ikona uploadu nahoře, centered
        icon_lbl = QLabel()
        icon_lbl.setPixmap(pixmap("upload", size=44, color=ACCENT))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setFixedHeight(60)
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        outer.addWidget(icon_lbl)

        # Hlavní text "Přetáhni soubor nebo vyber..."
        title = QLabel("Přetáhni soubor sem")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"font-size: 17px; font-weight: 600; color: {ACCENT}; "
            "border: none; background: transparent;"
        )
        outer.addWidget(title)

        # Subtitle "or"
        subtitle = QLabel("nebo klikni na tlačítko níže")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(
            "font-size: 12px; color: palette(mid); "
            "border: none; background: transparent;"
        )
        outer.addWidget(subtitle)

        # Tlačítka pod tím, centered
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch(1)
        btn_audio = self._make_button("Vybrat nahrávku", "mic", self._pick_audio)
        btn_slides = self._make_button("Vybrat slidy", "slides", self._pick_slides)
        btn_row.addWidget(btn_audio)
        btn_row.addWidget(btn_slides)
        btn_row.addStretch(1)
        outer.addLayout(btn_row)

    def _make_button(self, text: str, ico_name: str, handler) -> QPushButton:
        btn = QPushButton(text)
        btn.setIcon(icon(ico_name, size=15, color=ACCENT))
        btn.setIconSize(icon_size(15))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { padding: 8px 14px; font-weight: 600; color: palette(text); "
            "border: 1px solid palette(mid); border-radius: 8px; background: palette(base); }"
            "QPushButton:hover { background: palette(midlight); border-color: " + ACCENT + "; }"
        )
        btn.clicked.connect(handler)
        return btn

    # ------ API ------

    def set_last_dir(self, path: str) -> None:
        if path:
            self._last_dir = path

    @property
    def last_dir(self) -> str:
        return self._last_dir

    # ------ Drag&drop ------

    def _set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            self._set_active(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._set_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._set_active(False)
        urls = event.mimeData().urls()
        paths = [Path(u.toLocalFile()) for u in urls if u.toLocalFile()]
        if not paths:
            return
        sources = self._classify_paths(paths)
        if sources:
            self.sources_added.emit(sources)

    # ------ File dialogy ------

    def _pick_audio(self) -> None:
        filter_str = (
            "Audio/video (" + " ".join(f"*{ext}" for ext in AUDIO_VIDEO_EXTENSIONS)
            + ");;Všechny soubory (*)"
        )
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Vyber nahrávku", self._last_dir, filter_str
        )
        if not paths:
            return
        self._last_dir = str(Path(paths[0]).parent)
        sources = self._classify_paths([Path(p) for p in paths])
        if sources:
            self.sources_added.emit(sources)

    def _pick_slides(self) -> None:
        filter_str = (
            "Prezentace (" + " ".join(f"*{ext}" for ext in PRESENTATION_EXTENSIONS)
            + ");;Všechny soubory (*)"
        )
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Vyber prezentaci", self._last_dir, filter_str
        )
        if not paths:
            return
        self._last_dir = str(Path(paths[0]).parent)
        sources = self._classify_paths([Path(p) for p in paths])
        if sources:
            self.sources_added.emit(sources)

    @staticmethod
    def _classify_paths(paths: list[Path]) -> list[SourceFile]:
        out: list[SourceFile] = []
        for p in paths:
            ext = p.suffix.lower()
            if ext in AUDIO_VIDEO_EXTENSIONS:
                out.append(SourceFile(path=p, kind=SourceKind.AUDIO_VIDEO, label=p.stem))
            elif ext in PRESENTATION_EXTENSIONS:
                out.append(SourceFile(path=p, kind=SourceKind.PRESENTATION, label=p.stem))
        return out
