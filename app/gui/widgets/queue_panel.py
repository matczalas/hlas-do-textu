"""QueuePanel — sekvenční seznam batch jobů dle prototypu (running.jsx).

Layout per row (QueueItem):

  queued   ⏰  Název projektu                                 Ve frontě   ✕
  running  ⟳   Název projektu     [Přepis][————▓————] 42 %    Přepis…    ✕
  done     ✓   Název projektu                                 Otevřít

Pokud má job cached=True (Whisper přepis nalezen v knihovně), přidá se pill
badge "Přepis z knihovny" (queued/running) nebo "Použit hotový přepis" (done).

Tlačítko "Vyčistit hotové" na konci, pokud existuje aspoň 1 done/error job.

Wiring: QueuePanel(controller).controller.jobs_changed → self._render().
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.gui.job_queue import JobQueueController, JobState
from app.gui.styles import tokens
from app.gui.widgets.icons import icon, icon_size, pixmap


class _Spinner(QWidget):
    """Mini spinner — rotující arc pro running jobs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(45)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._angle = (self._angle + 12) % 360
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        accent = QColor(tokens.accent())
        # Track (light circle)
        track = QColor(accent)
        track.setAlpha(40)
        from PySide6.QtGui import QPen

        pen_track = QPen(track, 2.2)
        pen_track.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen_track)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(2, 2, 14, 14, 0, 360 * 16)
        # Spinning arc (90°)
        pen = QPen(accent, 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        span = 90 * 16
        p.drawArc(2, 2, 14, 14, int(self._angle * 16), span)
        p.end()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self.stop()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.start()


class _QueueItem(QFrame):
    """Jeden řádek ve frontě — stav queued / running / done / error / cancelled."""

    cancel_requested = Signal(str)   # job_id
    open_requested = Signal(Path)    # output_path

    def __init__(self, job: JobState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("QueueItem")
        self._job_id = job.id

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)

        # Stav ikona / spinner (vlevo)
        self._state_wrap = QWidget()
        self._state_wrap.setFixedSize(28, 28)
        self._state_layout = QHBoxLayout(self._state_wrap)
        self._state_layout.setContentsMargins(0, 0, 0, 0)
        self._state_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._state_icon = QLabel()
        self._spinner: _Spinner | None = None
        self._state_layout.addWidget(self._state_icon)
        row.addWidget(self._state_wrap)

        # Hlavní sloupec — label + (pokud running) progress bar a phase
        main_col = QVBoxLayout()
        main_col.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self._title = QLabel(job.label)
        tf = QFont()
        tf.setPointSize(12)
        tf.setWeight(QFont.Weight.DemiBold)
        self._title.setFont(tf)
        title_row.addWidget(self._title)

        # Cache badge (pokud cached) — pill mezi titulkem a stavem
        self._cache_badge = QLabel("")
        self._cache_badge.setObjectName("CacheBadge")
        self._cache_badge.hide()
        title_row.addWidget(self._cache_badge)
        title_row.addStretch(1)
        main_col.addLayout(title_row)

        # Spodní řádek — progress bar (running) nebo status text
        self._bottom_row = QHBoxLayout()
        self._bottom_row.setSpacing(8)

        self._progress = QProgressBar()
        self._progress.setRange(0, 1000)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(5)
        self._progress.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._bottom_row.addWidget(self._progress, 1)

        self._status_text = QLabel("")
        self._status_text.setStyleSheet(
            "color: palette(placeholder-text); font-size: 11.5px;"
        )
        self._bottom_row.addWidget(self._status_text)
        main_col.addLayout(self._bottom_row)

        row.addLayout(main_col, 1)

        # Pravá akce — cancel X / Otevřít link
        self._cancel_btn = QPushButton()
        self._cancel_btn.setIcon(icon("x", size=13, color="#9aa7b6"))
        self._cancel_btn.setIconSize(icon_size(13))
        self._cancel_btn.setFixedSize(28, 28)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setToolTip("Zrušit / odstranit z fronty")
        self._cancel_btn.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid transparent; "
            "border-radius: 7px; }"
            "QPushButton:hover { background: rgba(192,57,43,0.10); border-color: #c0392b; }"
        )
        self._cancel_btn.clicked.connect(
            lambda: self.cancel_requested.emit(self._job_id)
        )
        row.addWidget(self._cancel_btn)

        self._open_btn = QPushButton("Otevřít")
        self._open_btn.setObjectName("Link")
        self._open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_btn.clicked.connect(
            lambda: self._on_open_clicked()
        )
        self._open_btn.hide()
        row.addWidget(self._open_btn)

        # Apply styling
        self.setStyleSheet(
            "QFrame#QueueItem { background: palette(base); "
            "border: 1px solid palette(midlight); border-radius: 10px; }"
            "QLabel#CacheBadge { padding: 2px 8px; border-radius: 999px; "
            "font-size: 10.5px; font-weight: 700; }"
        )

        self.update_from_state(job)

    def update_from_state(self, job: JobState) -> None:
        """Re-renderuje podle aktuálního JobState (volá QueuePanel při refresh)."""
        self._title.setText(job.label)

        # Cache badge
        if job.cached:
            if job.status == "done":
                self._cache_badge.setText("Použit hotový přepis")
            else:
                self._cache_badge.setText("Přepis z knihovny")
            accent = tokens.accent()
            self._cache_badge.setStyleSheet(
                f"QLabel#CacheBadge {{ padding: 2px 8px; border-radius: 999px; "
                f"font-size: 10.5px; font-weight: 700; "
                f"background: {tokens.accent_soft(0.12)}; color: {accent}; }}"
            )
            self._cache_badge.show()
        else:
            self._cache_badge.hide()

        # State-specific rendering
        accent = tokens.accent()
        status = job.status

        # Reset visual state
        self._destroy_spinner()
        self._open_btn.hide()
        self._cancel_btn.show()

        if status == "queued":
            self._state_icon.setPixmap(pixmap("clock", size=14, color="#9aa7b6"))
            self._state_icon.show()
            self._progress.hide()
            self._status_text.setText("Ve frontě")
            self._status_text.setStyleSheet(
                "color: palette(placeholder-text); font-size: 11.5px;"
            )
        elif status == "running":
            # Spinner místo ikony
            self._state_icon.hide()
            self._make_spinner()
            self._progress.show()
            if not math.isfinite(job.progress):
                job.progress = 0.0
            self._progress.setValue(int(max(0.0, min(1.0, job.progress)) * 1000))
            self._progress.setStyleSheet(
                "QProgressBar { background: palette(midlight); border: none; border-radius: 3px; }"
                f"QProgressBar::chunk {{ background: {accent}; border-radius: 3px; }}"
            )
            pct = int(job.progress * 100)
            phase_text = job.phase or "Probíhá"
            self._status_text.setText(f"{phase_text} · {pct} %")
            self._status_text.setStyleSheet(
                f"color: {accent}; font-size: 11.5px; font-weight: 600;"
            )
        elif status == "done":
            # Zelený check pill
            self._state_icon.setPixmap(pixmap("check", size=14, color="#ffffff"))
            self._state_icon.setFixedSize(22, 22)
            self._state_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._state_icon.setStyleSheet(
                f"QLabel {{ background: {tokens.SUCCESS}; border-radius: 11px; }}"
            )
            self._state_icon.show()
            self._progress.hide()
            self._status_text.setText("Hotovo")
            self._status_text.setStyleSheet(
                f"color: {tokens.SUCCESS}; font-size: 11.5px; font-weight: 600;"
            )
            self._cancel_btn.hide()
            if job.output_path is not None:
                self._open_btn.show()
        elif status == "error":
            self._state_icon.setPixmap(pixmap("info", size=14, color="#ffffff"))
            self._state_icon.setFixedSize(22, 22)
            self._state_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._state_icon.setStyleSheet(
                f"QLabel {{ background: {tokens.DANGER}; border-radius: 11px; }}"
            )
            self._state_icon.show()
            self._progress.hide()
            self._status_text.setText(
                (job.error_message or "Chyba")[:60]
            )
            self._status_text.setStyleSheet(
                f"color: {tokens.DANGER}; font-size: 11.5px; font-weight: 500;"
            )
            self._cancel_btn.hide()
        elif status == "cancelled":
            self._state_icon.setPixmap(pixmap("x", size=14, color="#9aa7b6"))
            self._state_icon.setFixedSize(22, 22)
            self._state_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._state_icon.setStyleSheet("")
            self._state_icon.show()
            self._progress.hide()
            self._status_text.setText("Zrušeno")
            self._status_text.setStyleSheet(
                "color: palette(placeholder-text); font-size: 11.5px;"
            )
            self._cancel_btn.hide()

        # Uložit output_path pro open klik
        self._output_path = job.output_path

    def _make_spinner(self) -> None:
        if self._spinner is None:
            self._spinner = _Spinner()
            self._state_layout.addWidget(self._spinner)
        self._spinner.show()
        self._spinner.start()

    def _destroy_spinner(self) -> None:
        if self._spinner is not None:
            self._spinner.stop()
            self._spinner.hide()
            self._spinner.deleteLater()
            self._spinner = None

    def _on_open_clicked(self) -> None:
        if self._output_path is not None:
            self.open_requested.emit(self._output_path)


class QueuePanel(QFrame):
    """Dock-style fronta jobů. Subscribne na controller.jobs_changed."""

    cancel_requested = Signal(str)
    open_requested = Signal(Path)

    def __init__(
        self,
        controller: JobQueueController,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("QueuePanel")
        self._controller = controller
        self._items: dict[str, _QueueItem] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        # Hlavička s titulkem + počtem + "Vyčistit hotové"
        head = QHBoxLayout()
        head.setSpacing(8)
        self._title = QLabel("Fronta zpracování")
        tf = QFont()
        tf.setPointSize(12)
        tf.setWeight(QFont.Weight.DemiBold)
        self._title.setFont(tf)
        head.addWidget(self._title)

        self._count_label = QLabel("")
        self._count_label.setStyleSheet(
            "color: palette(placeholder-text); font-size: 11.5px;"
        )
        head.addWidget(self._count_label)
        head.addStretch(1)

        self._clear_btn = QPushButton("Vyčistit hotové")
        self._clear_btn.setObjectName("Link")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(controller.clear_done)
        self._clear_btn.hide()
        head.addWidget(self._clear_btn)
        outer.addLayout(head)

        # Container pro QueueItem widgety
        self._items_container = QWidget()
        self._items_layout = QVBoxLayout(self._items_container)
        self._items_layout.setContentsMargins(0, 0, 0, 0)
        self._items_layout.setSpacing(6)
        self._items_layout.addStretch(1)
        outer.addWidget(self._items_container)

        # Subscribe
        controller.jobs_changed.connect(self._render)
        self._render()

    def _render(self) -> None:
        """Re-render na základě aktuálního controller.jobs()."""
        jobs = self._controller.jobs()

        # Update count + clear button visibility
        running = sum(1 for j in jobs if j.status == "running")
        queued = sum(1 for j in jobs if j.status == "queued")
        done_or_error = sum(1 for j in jobs if j.status in ("done", "error", "cancelled"))
        parts = []
        if running:
            parts.append(f"{running} běží")
        if queued:
            parts.append(f"{queued} ve frontě")
        if done_or_error:
            parts.append(f"{done_or_error} hotovo")
        self._count_label.setText("  ·  ".join(parts) if parts else "")
        self._clear_btn.setVisible(done_or_error > 0)

        # Sync UI items (zachovat existující widgety, ne destroy+rebuild)
        current_ids = {j.id for j in jobs}
        existing_ids = set(self._items.keys())

        # Remove deleted
        for jid in existing_ids - current_ids:
            item = self._items.pop(jid)
            item.deleteLater()

        # Add new + update existing
        for job in jobs:
            if job.id in self._items:
                self._items[job.id].update_from_state(job)
            else:
                item = _QueueItem(job)
                item.cancel_requested.connect(self.cancel_requested.emit)
                item.open_requested.connect(self.open_requested.emit)
                # Insert before stretch (poslední item v layoutu je addStretch)
                insert_idx = self._items_layout.count() - 1
                self._items_layout.insertWidget(insert_idx, item)
                self._items[job.id] = item

        # Skryj celý panel pokud je fronta úplně prázdná
        self.setVisible(len(jobs) > 0)

    def refresh_accent(self) -> None:
        """Po změně role re-renderuj všechny položky (cache badge, accent text…)."""
        for job in self._controller.jobs():
            if job.id in self._items:
                self._items[job.id].update_from_state(job)
