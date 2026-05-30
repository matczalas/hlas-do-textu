"""Model Download Dialog — standalone dialog pro stažení Whisper modelu.

Layout dle prototypu:
- 64px ikona kruhu (audio = stahuje se, check = hotovo) + rotující prsten
- Title + sub
- QProgressBar (8px) + meta XX / NN MB · YY %
- 3-krokový checklist (Licence ověřena → Stahuji → Připraveno)
- Bottom: "Otevřít aplikaci" tlačítko (po dokončení) nebo hint

Wiring: napojené na existující ModelDownloadWorker přes progress/finished_ok/error
signály. Při zavření před hotovo zavolá worker.stop_and_wait().

API:
    ModelDownloadDialog(model_name, worker, parent=None)
    update_progress(status, fraction)
    set_done()
    set_error(message)
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.gui.styles import tokens
from app.gui.widgets.icons import pixmap

# Velikost modelu dle settings.whisper_model — pro display jen orientační
_MODEL_SIZE_MB = {
    "small": 250,
    "medium": 770,
    "large-v3": 1500,
}


class _RingIcon(QWidget):
    """64px kruh s ikonou uvnitř + rotující accent prsten kolem.

    Stav 'active' = prsten se točí (download běží). 'done' = statický check.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(72, 72)
        self._angle = 0
        self._state = "active"  # "active" | "done"
        self._timer = QTimer(self)
        self._timer.setInterval(40)  # ~25 FPS
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        self._angle = (self._angle + 8) % 360
        self.update()

    def set_done(self) -> None:
        self._state = "done"
        self._timer.stop()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        accent = QColor(tokens.accent())

        # Vnitřní kruh — accent-soft bg
        soft = QColor(accent)
        soft.setAlpha(30)
        p.setBrush(soft)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(8, 8, 56, 56)

        # Ikona uprostřed
        if self._state == "done":
            ico = pixmap("check", size=28, color=tokens.accent())
        else:
            ico = pixmap("audio", size=28, color=tokens.accent())
        # center pixmap
        ico_x = (self.width() - ico.width() // int(ico.devicePixelRatio())) // 2
        ico_y = (self.height() - ico.height() // int(ico.devicePixelRatio())) // 2
        p.drawPixmap(ico_x, ico_y, ico)

        # Rotující prsten — jen v aktivním stavu
        if self._state == "active":
            pen = QPen(accent, 3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            # drawArc bere úhly v 1/16 stupně
            span = 90 * 16  # 90° arc
            start = self._angle * 16
            p.drawArc(4, 4, 64, 64, int(start), span)

        p.end()


class _StepRow(QFrame):
    """Jeden řádek 3-krokového checklistu (idle/active/done)."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = label
        self._state = "idle"  # "idle" | "active" | "done"

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 4, 0, 4)
        h.setSpacing(10)

        # Stav badge (číslo / spinner / check)
        self._mark = QLabel()
        self._mark.setFixedSize(22, 22)
        self._mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(self._mark)

        self._text = QLabel(label)
        self._text.setStyleSheet("font-size: 12.5px;")
        h.addWidget(self._text, 1)

        self._apply_state()

    def set_state(self, state: str) -> None:
        self._state = state
        self._apply_state()

    def _apply_state(self) -> None:
        accent = tokens.accent()
        if self._state == "done":
            self._mark.setPixmap(pixmap("check", size=14, color="#ffffff"))
            self._mark.setStyleSheet(
                f"QLabel {{ background: {tokens.SUCCESS}; border-radius: 11px; }}"
            )
            self._text.setStyleSheet("font-size: 12.5px; color: palette(text);")
        elif self._state == "active":
            self._mark.setPixmap(pixmap("clock", size=12, color=accent))
            self._mark.setStyleSheet(
                f"QLabel {{ background: {tokens.accent_soft(0.18)}; "
                f"border: 1.5px solid {accent}; border-radius: 11px; }}"
            )
            self._text.setStyleSheet(
                f"font-size: 12.5px; color: {accent}; font-weight: 600;"
            )
        else:  # idle
            self._mark.setPixmap(pixmap("clock", size=12, color="#9aa7b6"))
            self._mark.setStyleSheet(
                "QLabel { background: palette(midlight); border-radius: 11px; }"
            )
            self._text.setStyleSheet("font-size: 12.5px; color: palette(placeholder-text);")


class ModelDownloadDialog(QDialog):
    """Standalone dialog pro stažení Whisper modelu (Hugging Face).

    Připojí se k existujícímu ModelDownloadWorker přes signály. Dialog je
    non-modal (show() místo exec()), aby zbytek UI zůstal odezvavý.
    """

    def __init__(
        self,
        model_name: str,
        worker,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._model_name = model_name
        self._worker = worker
        self._size_mb = _MODEL_SIZE_MB.get(model_name, 250)

        self.setWindowTitle("Stahování modelu — Hlas do textu")
        self.setMinimumWidth(460)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 22)
        root.setSpacing(14)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Hero — ring icon vystředěná
        hero_row = QHBoxLayout()
        hero_row.addStretch(1)
        self._ring = _RingIcon()
        hero_row.addWidget(self._ring)
        hero_row.addStretch(1)
        root.addLayout(hero_row)

        # Title
        self._title = QLabel("Připravuji offline přepis")
        tf = QFont()
        tf.setPointSize(16)
        tf.setWeight(QFont.Weight.DemiBold)
        self._title.setFont(tf)
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._title)

        self._subtitle = QLabel(
            "Stahuje se Whisper model pro lokální přepis. "
            "Jednorázově, pak už appka funguje i offline."
        )
        self._subtitle.setWordWrap(True)
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle.setStyleSheet("color: palette(placeholder-text); font-size: 12.5px;")
        root.addWidget(self._subtitle)

        # Progress bar + meta
        self._bar = QProgressBar()
        self._bar.setRange(0, 1000)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        root.addWidget(self._bar)

        self._meta = QLabel(f"0 / {self._size_mb} MB · 0 %")
        self._meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._meta.setStyleSheet("color: palette(placeholder-text); font-size: 11.5px;")
        root.addWidget(self._meta)

        root.addSpacing(6)

        # 3-krokový checklist
        steps_box = QFrame()
        steps_box.setObjectName("StepsBox")
        steps_box.setStyleSheet(
            "QFrame#StepsBox { background: palette(alternate-base); "
            "border: 1px solid palette(midlight); border-radius: 10px; padding: 4px; }"
        )
        sb = QVBoxLayout(steps_box)
        sb.setContentsMargins(12, 8, 12, 8)
        sb.setSpacing(2)
        self._step_license = _StepRow("Licence ověřena")
        self._step_license.set_state("done")
        sb.addWidget(self._step_license)
        self._step_download = _StepRow(f"Stahuji {model_name} (~{self._size_mb} MB)")
        self._step_download.set_state("active")
        sb.addWidget(self._step_download)
        self._step_ready = _StepRow("Připraveno — můžeš začít")
        self._step_ready.set_state("idle")
        sb.addWidget(self._step_ready)
        root.addWidget(steps_box)

        # Bottom action — primary tlačítko (skryto dokud nehotovo)
        self._action_btn = QPushButton("Otevřít aplikaci")
        self._action_btn.setObjectName("Primary")
        self._action_btn.setMinimumHeight(40)
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.clicked.connect(self.accept)
        self._action_btn.hide()

        self._hint = QLabel("Můžeš zatím přidat nahrávku v hlavním okně.")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
        root.addWidget(self._hint)
        root.addWidget(self._action_btn)

        # Wire worker signály
        worker.progress.connect(self.update_progress)
        worker.finished_ok.connect(self.set_done)
        worker.finished_error.connect(self.set_error)

    # ----- Worker callbacks -----

    def update_progress(self, status: str, fraction: float) -> None:
        if not math.isfinite(fraction):
            fraction = 0.0
        fraction = max(0.0, min(1.0, fraction))
        self._bar.setValue(int(fraction * 1000))
        mb_down = int(fraction * self._size_mb)
        pct = int(fraction * 100)
        self._meta.setText(f"{mb_down} / {self._size_mb} MB · {pct} %")
        self._subtitle.setText(status or "Stahuji Whisper model…")

    def set_done(self) -> None:
        self._ring.set_done()
        self._title.setText("Hotovo — můžeš začít")
        self._subtitle.setText("Model je stažený, offline přepis je připravený.")
        self._bar.setValue(1000)
        self._step_download.set_state("done")
        self._step_ready.set_state("done")
        self._hint.hide()
        self._action_btn.show()

    def set_error(self, message: str) -> None:
        self._title.setText("Stahování selhalo")
        self._subtitle.setText(message[:200])
        self._subtitle.setStyleSheet(
            f"color: {tokens.DANGER}; font-size: 12.5px;"
        )
        self._step_download.set_state("idle")
        self._hint.hide()
        self._action_btn.setText("Zavřít")
        self._action_btn.show()

    # ----- Lifecycle -----

    def closeEvent(self, event) -> None:  # noqa: N802
        """Při zavření před hotovo počkat na worker (CLAUDE.md pattern)."""
        try:
            self._worker.progress.disconnect(self.update_progress)
            self._worker.finished_ok.disconnect(self.set_done)
            self._worker.finished_error.disconnect(self.set_error)
        except (RuntimeError, TypeError):
            pass
        if self._worker.is_running():
            self._worker.stop_and_wait(timeout_ms=2000)
        super().closeEvent(event)

    def reject(self) -> None:  # noqa: N802
        # Esc / [×] → stejný cleanup jako closeEvent
        try:
            self._worker.progress.disconnect(self.update_progress)
            self._worker.finished_ok.disconnect(self.set_done)
            self._worker.finished_error.disconnect(self.set_error)
        except (RuntimeError, TypeError):
            pass
        if self._worker.is_running():
            self._worker.stop_and_wait(timeout_ms=2000)
        super().reject()
