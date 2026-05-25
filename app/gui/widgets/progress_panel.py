"""Progress panel — status + bar + log. Bez eyebrow, bez ozdob.

Veřejné API:
    @property cancel_button -> QPushButton
    set_busy(busy: bool)
    update(label: str, fraction: float)
    reset()
    append_message(msg: str)
    append_transcript_line(seconds: float, label: str, text: str)
"""

from __future__ import annotations

from datetime import datetime
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.gui.widgets.icons import icon, icon_size

ACCENT = "#205ca8"


class ProgressPanel(QGroupBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("", parent)
        self.setObjectName("ProgressCard")
        self.setStyleSheet(
            "QGroupBox#ProgressCard { background: palette(base); "
            "border: 1px solid palette(midlight); border-radius: 10px; "
            "margin-top: 0; }"
            "QGroupBox#ProgressCard::title { padding: 0; }"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)

        # Top row: label + percent + cancel
        top = QHBoxLayout()
        top.setSpacing(10)

        self._status = QLabel("Připraveno")
        self._status.setStyleSheet("font-size: 13px; font-weight: 600; color: palette(text);")
        top.addWidget(self._status, 1)

        self._percent = QLabel("")
        self._percent.setStyleSheet(f"color: {ACCENT}; font-size: 13px; font-weight: 600;")
        top.addWidget(self._percent)

        self._cancel_btn = QPushButton("Zrušit")
        self._cancel_btn.setIcon(icon("x", size=13, color="#c84444"))
        self._cancel_btn.setIconSize(icon_size(13))
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid palette(midlight); "
            "border-radius: 7px; padding: 5px 10px; color: palette(text); font-size: 12px; }"
            "QPushButton:hover:enabled { background: rgba(216,70,70,0.10); "
            "border-color: #c84444; color: #c84444; }"
            "QPushButton:disabled { color: palette(placeholder-text); border-color: palette(midlight); }"
        )
        top.addWidget(self._cancel_btn)
        outer.addLayout(top)

        # Progress bar
        self._bar = QProgressBar()
        self._bar.setRange(0, 1000)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        outer.addWidget(self._bar)

        # Log
        self._log = QTextEdit()
        self._log.setObjectName("Log")
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(110)
        self._log.setPlaceholderText("Zde se ti budou objevovat zprávy a živý přepis…")
        outer.addWidget(self._log, 1)

    @property
    def cancel_button(self) -> QPushButton:
        return self._cancel_btn

    def set_busy(self, busy: bool) -> None:
        self._cancel_btn.setEnabled(busy)
        if not busy:
            self._bar.setValue(0)
            self._percent.setText("")

    def update(self, label: str, fraction: float) -> None:
        self._status.setText(label)
        value = max(0, min(1000, int(fraction * 1000)))
        self._bar.setValue(value)
        self._percent.setText(f"{fraction * 100:.0f} %")
        self._append_log(f"[{fraction * 100:5.1f}%] {label}")

    def reset(self) -> None:
        self._status.setText("Připraveno")
        self._bar.setValue(0)
        self._percent.setText("")
        self._log.clear()

    def append_message(self, msg: str) -> None:
        self._append_log(msg)

    def append_transcript_line(self, seconds: float, label: str, text: str) -> None:
        time_str = self._format_audio_time(seconds)
        if len(text) > 180:
            text = text[:177] + "…"
        safe_label = escape(label)
        safe_text = escape(text)
        self._log.append(
            f'<span style="color:#888;">[{time_str}]</span> '
            f'<span style="color:{ACCENT}; font-weight:600;">{safe_label}</span>'
            f'&nbsp;&nbsp;<span style="color:palette(text);">{safe_text}</span>'
        )
        self._scroll_to_end()

    def _append_log(self, msg: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log.append(f'<span style="color:#888;">{timestamp}</span>&nbsp;&nbsp;{escape(msg)}')
        self._scroll_to_end()

    def _scroll_to_end(self) -> None:
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
