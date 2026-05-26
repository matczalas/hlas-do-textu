"""Modální dialog pro vložení YouTube/Vimeo/SoundCloud URL.

Sám stahování nedělá — vrátí URL a hlavní okno přes worker spustí fetch.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from app.core.youtube_fetch import is_supported_url


class YouTubeUrlDialog(QDialog):
    """Vstupní dialog: URL + Stáhnout. Po start emituje url_submitted."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Přepis z YouTube / podcastu / Vimeo")
        self.setMinimumWidth(540)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        title = QLabel("Odkaz na video nebo audio")
        title.setStyleSheet("font-weight: 600; font-size: 14px;")
        root.addWidget(title)

        hint = QLabel(
            "Podporujeme YouTube, Vimeo, SoundCloud, Loom a další.\n"
            "Stáhne se jen audio stopa do dočasné složky a po přepisu se smaže."
        )
        hint.setStyleSheet("color: palette(mid); font-size: 12px;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://www.youtube.com/watch?v=…")
        self._url_edit.setMinimumHeight(36)
        self._url_edit.textChanged.connect(self._validate)
        root.addWidget(self._url_edit)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: palette(mid); font-size: 12px;")
        root.addWidget(self._status_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.hide()
        root.addWidget(self._progress)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setText("Stáhnout")
        self._ok_btn.setEnabled(False)
        self._ok_btn.setMinimumHeight(36)
        self._ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setText("Zavřít")
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        root.addWidget(self._buttons)

    def url(self) -> str:
        return self._url_edit.text().strip()

    def set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def set_progress(self, fraction: float, status: str) -> None:
        if not self._progress.isVisible():
            self._progress.show()
        self._progress.setValue(int(fraction * 100))
        self.set_status(status)

    def lock_for_download(self) -> None:
        self._url_edit.setEnabled(False)
        self._ok_btn.setEnabled(False)
        self._ok_btn.setText("Stahuji…")

    def _validate(self) -> None:
        ok = is_supported_url(self._url_edit.text())
        self._ok_btn.setEnabled(ok)
        if self._url_edit.text() and not ok:
            self._status_label.setText("URL nevypadá platně — zkontroluj http(s) prefix.")
        else:
            self._status_label.setText("")
