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

import math
import time
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

        # ETA stav — start času běhu a vyhlazený odhad zbývajícího času
        self._start_monotonic: float | None = None
        self._smoothed_eta: float | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)

        # Top row: fáze badge + label + ETA + percent + cancel
        top = QHBoxLayout()
        top.setSpacing(10)

        # Fázový badge — barevně rozlišuje krok (Příprava / Přepis / AI / Ukládání)
        self._phase = QLabel("")
        self._phase.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: white; "
            "background: #888; border-radius: 8px; padding: 3px 9px;"
        )
        self._phase.hide()
        top.addWidget(self._phase)

        self._status = QLabel("Připraveno")
        self._status.setStyleSheet("font-size: 13px; font-weight: 600; color: palette(text);")
        top.addWidget(self._status, 1)

        # Indikátor pozice v dávce ("2 / 5") — viditelný jen při více nahrávkách
        self._batch = QLabel("")
        self._batch.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #205ca8; "
            "background: rgba(32,92,168,0.12); border-radius: 8px; padding: 3px 9px;"
        )
        self._batch.hide()
        top.addWidget(self._batch)

        # Živý odhad zbývajícího času (ETA) — počítá se z reálné rychlosti
        self._eta = QLabel("")
        self._eta.setStyleSheet("color: palette(mid); font-size: 12px;")
        top.addWidget(self._eta)

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
        # Limit počtu bloků — u dlouhé přednášky (tisíce segmentů živého přepisu)
        # by jinak QTextEdit rostl bez omezení a UI by se sekalo / žralo RAM.
        # Starší řádky se automaticky odřezávají.
        self._log.document().setMaximumBlockCount(5000)
        outer.addWidget(self._log, 1)

    @property
    def cancel_button(self) -> QPushButton:
        return self._cancel_btn

    def set_busy(self, busy: bool) -> None:
        self._cancel_btn.setEnabled(busy)
        if busy:
            # Start měření pro ETA
            self._start_monotonic = time.monotonic()
            self._smoothed_eta = None
            self._eta.setText("počítám čas…")
        else:
            self._bar.setValue(0)
            self._percent.setText("")
            self._eta.setText("")
            self._start_monotonic = None

    def update(self, label: str, fraction: float) -> None:
        self._status.setText(label)
        self._set_phase_badge(label)
        # Guard proti NaN/inf — int(nan) vyhodí ValueError a shodil by panel.
        if not math.isfinite(fraction):
            fraction = 0.0
        fraction = max(0.0, min(1.0, fraction))
        value = int(fraction * 1000)
        self._bar.setValue(value)
        self._percent.setText(f"{fraction * 100:.0f} %")
        self._update_eta(fraction)
        self._append_log(f"[{fraction * 100:5.1f}%] {label}")

    def set_batch_position(self, index: int, total: int) -> None:
        """Zobrazí 'X / N' při dávkovém zpracování. total<=1 → skryté."""
        if total > 1:
            self._batch.setText(f"dávka {index} / {total}")
            self._batch.show()
        else:
            self._batch.hide()

    def _set_phase_badge(self, label: str) -> None:
        """Z textu progresu odvodí fázi a obarví badge. Uživatel hned vidí,
        jestli běží přepis (Whisper) nebo AI zpracování."""
        low = label.lower()
        # (text badge, barva) podle klíčových slov v labelu
        if "přepis" in low or "transcrib" in low:
            text, color = "Přepis řeči", "#205ca8"   # modrá = Whisper/cloud přepis
        elif "body" in low or "generuj" in low or " ai" in low or "ai " in low:
            text, color = "AI zpracování", "#7c3aed"  # fialová = AI
        elif "prezentac" in low or "slid" in low or "čtu" in low:
            text, color = "Čtení slidů", "#0891b2"
        elif "word" in low or "ukládám" in low or "export" in low:
            text, color = "Ukládání", "#16a34a"       # zelená = finalizace
        elif "extrah" in low or "připrav" in low or "stahuj" in low:
            text, color = "Příprava", "#888"
        elif "hotovo" in low:
            text, color = "Hotovo", "#16a34a"
        else:
            self._phase.hide()
            return
        self._phase.setText(text)
        self._phase.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: white; "
            f"background: {color}; border-radius: 8px; padding: 3px 9px;"
        )
        self._phase.show()

    def _update_eta(self, fraction: float) -> None:
        """Spočítá a zobrazí odhad zbývajícího času z reálné rychlosti.

        ETA = (uplynulý čas / hotová část) × zbývající část. Hodnotu vyhladíme
        exponenciálním průměrem (EMA), ať číslo neposkakuje. Ke konci (>92 %)
        přejdeme na "už jen chvilku" — poslední fáze (AI body, export Wordu)
        jsou rychlé proti přepisu, takže odhad tam přirozeně klesá.
        """
        if self._start_monotonic is None:
            return
        # Dokud nemáme dost dat, neodhadujeme (jinak by ETA byla divoká)
        if fraction < 0.03:
            self._eta.setText("počítám čas…")
            return
        if fraction >= 0.92:
            self._eta.setText("už jen chvilku…")
            return

        elapsed = time.monotonic() - self._start_monotonic
        raw_eta = elapsed * (1.0 - fraction) / fraction

        # EMA smoothing — váha 0.3 na nový odhad, 0.7 na předchozí
        if self._smoothed_eta is None:
            self._smoothed_eta = raw_eta
        else:
            self._smoothed_eta = 0.3 * raw_eta + 0.7 * self._smoothed_eta

        self._eta.setText(f"zbývá ~{_format_eta(self._smoothed_eta)}")

    def reset(self) -> None:
        self._status.setText("Připraveno")
        self._phase.hide()
        self._bar.setValue(0)
        self._percent.setText("")
        self._eta.setText("")
        self._start_monotonic = None
        self._smoothed_eta = None
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


def _format_eta(seconds: float) -> str:
    """Lidsky čitelný zbývající čas pro ETA label."""
    if not math.isfinite(seconds) or seconds < 0:
        return "chvíli"
    seconds = int(seconds)
    if seconds < 10:
        return "pár sekund"
    if seconds < 60:
        # zaokrouhlit na 10 s, ať to neposkakuje po sekundě
        return f"{(seconds // 10 + 1) * 10} s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min" if minutes == 1 else f"{minutes} min"
    hours = minutes // 60
    rem_min = minutes % 60
    if rem_min == 0:
        return f"{hours} h"
    return f"{hours} h {rem_min} min"
