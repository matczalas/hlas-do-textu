"""Panel s progress barem, status labelem a log viewem."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class ProgressPanel(QGroupBox):
    """[label] [progress bar] [log textarea]."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Postup", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)

        self._status = QLabel("Připraveno.")
        self._status.setStyleSheet("font-weight: 600;")
        layout.addWidget(self._status)

        self._bar = QProgressBar()
        self._bar.setRange(0, 1000)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        layout.addWidget(self._bar)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(120)
        self._log.setStyleSheet("font-family: Menlo, 'Courier New', monospace; font-size: 11px;")
        layout.addWidget(self._log)

        self._cancel_btn = QPushButton("Zrušit zpracování")
        self._cancel_btn.setEnabled(False)
        layout.addWidget(self._cancel_btn, alignment=Qt.AlignmentFlag.AlignRight)

    @property
    def cancel_button(self) -> QPushButton:
        return self._cancel_btn

    def set_busy(self, busy: bool) -> None:
        self._cancel_btn.setEnabled(busy)
        if not busy:
            self._bar.setValue(0)

    def update(self, label: str, fraction: float) -> None:
        self._status.setText(label)
        self._bar.setValue(int(fraction * 1000))
        self._append_log(f"[{fraction * 100:5.1f}%] {label}")

    def reset(self) -> None:
        self._status.setText("Připraveno.")
        self._bar.setValue(0)
        self._log.clear()

    def append_message(self, msg: str) -> None:
        self._append_log(msg)

    def append_transcript_line(self, seconds: float, label: str, text: str) -> None:
        """Živý feed přepisu — místo timestampu reálná pozice v audio."""
        time_str = self._format_audio_time(seconds)
        # Zkrátit dlouhé sektory
        if len(text) > 180:
            text = text[:177] + "…"
        self._log.append(f'<span style="color:#888;">[{time_str}]</span> <span style="color:#205ca8;">{label}:</span> {text}')
        cursor = self._log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._log.setTextCursor(cursor)

    def _append_log(self, msg: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log.append(f"{timestamp}  {msg}")
        cursor = self._log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._log.setTextCursor(cursor)

    @staticmethod
    def _format_audio_time(seconds: float) -> str:
        total = int(seconds)
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
