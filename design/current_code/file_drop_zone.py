"""Drag-drop oblast nad tabulkou souborů + dvě tlačítka pro file dialog."""

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

_DROP_ZONE_STYLE_IDLE = (
    "FileDropZone { border: 2px dashed palette(mid); border-radius: 8px; "
    "background-color: palette(alternate-base); }"
)
_DROP_ZONE_STYLE_ACTIVE = (
    "FileDropZone { border: 2px solid #205ca8; border-radius: 8px; "
    "background-color: rgba(32, 92, 168, 40); }"
)


class FileDropZone(QFrame):
    """Drag-drop frame + tlačítka [Přidat nahrávku] [Přidat slidy]."""

    sources_added = Signal(list)  # list[SourceFile]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(_DROP_ZONE_STYLE_IDLE)
        self.setMinimumHeight(110)
        self._last_dir: str = str(Path.home())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        label = QLabel("Sem přetáhni nahrávky nebo prezentace — nebo použij tlačítka.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("border: none; color: palette(text); font-size: 13px;")
        layout.addWidget(label)

        button_row = QHBoxLayout()
        button_row.setSpacing(12)
        button_style = (
            "QPushButton { background-color: palette(button); color: palette(button-text); "
            "border: 1px solid palette(mid); border-radius: 4px; padding: 8px 16px; "
            "font-size: 13px; font-weight: 500; }"
            "QPushButton:hover { background-color: palette(midlight); }"
            "QPushButton:pressed { background-color: palette(mid); }"
        )
        btn_audio = QPushButton("🎙  Přidat nahrávku")
        btn_audio.setStyleSheet(button_style)
        btn_audio.setMinimumHeight(36)
        btn_audio.clicked.connect(self._pick_audio)
        btn_slides = QPushButton("📄  Přidat slidy")
        btn_slides.setStyleSheet(button_style)
        btn_slides.setMinimumHeight(36)
        btn_slides.clicked.connect(self._pick_slides)
        button_row.addStretch(1)
        button_row.addWidget(btn_audio)
        button_row.addWidget(btn_slides)
        button_row.addStretch(1)
        layout.addLayout(button_row)

    def set_last_dir(self, path: str) -> None:
        if path:
            self._last_dir = path

    # ------ Drag&drop ------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            self.setStyleSheet(_DROP_ZONE_STYLE_ACTIVE)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self.setStyleSheet(_DROP_ZONE_STYLE_IDLE)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setStyleSheet(_DROP_ZONE_STYLE_IDLE)
        urls = event.mimeData().urls()
        paths = [Path(u.toLocalFile()) for u in urls if u.toLocalFile()]
        if not paths:
            return
        sources = self._classify_paths(paths)
        if sources:
            self.sources_added.emit(sources)

    # ------ File dialogy ------

    def _pick_audio(self) -> None:
        filter_str = "Audio/video (" + " ".join(f"*{ext}" for ext in AUDIO_VIDEO_EXTENSIONS) + ");;Všechny soubory (*)"
        paths, _ = QFileDialog.getOpenFileNames(self, "Vyber záznamy přednášky", self._last_dir, filter_str)
        if not paths:
            return
        self._last_dir = str(Path(paths[0]).parent)
        sources = self._classify_paths([Path(p) for p in paths])
        if sources:
            self.sources_added.emit(sources)

    def _pick_slides(self) -> None:
        filter_str = "Prezentace (" + " ".join(f"*{ext}" for ext in PRESENTATION_EXTENSIONS) + ");;Všechny soubory (*)"
        paths, _ = QFileDialog.getOpenFileNames(self, "Vyber prezentace", self._last_dir, filter_str)
        if not paths:
            return
        self._last_dir = str(Path(paths[0]).parent)
        sources = self._classify_paths([Path(p) for p in paths])
        if sources:
            self.sources_added.emit(sources)

    def _classify_paths(self, paths: list[Path]) -> list[SourceFile]:
        out: list[SourceFile] = []
        for p in paths:
            ext = p.suffix.lower()
            if ext in AUDIO_VIDEO_EXTENSIONS:
                out.append(SourceFile(path=p, kind=SourceKind.AUDIO_VIDEO, label=p.stem))
            elif ext in PRESENTATION_EXTENSIONS:
                out.append(SourceFile(path=p, kind=SourceKind.PRESENTATION, label=p.stem))
        return out

    @property
    def last_dir(self) -> str:
        return self._last_dir
