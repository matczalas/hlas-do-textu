"""Status řádek — dvě barevné tečky s minimálním labelem. Detail v tooltipu.

Veřejné API: refresh(gemini_api_key)
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class _HealthWorker(QObject):
    result_ready = Signal(bool, bool)

    def __init__(self, gemini_api_key: str | None) -> None:
        super().__init__()
        self._gemini_api_key = gemini_api_key

    def run(self) -> None:
        from app.core.ai.ollama import OllamaProvider

        gemini_ok = False
        if self._gemini_api_key:
            try:
                from google import genai  # noqa: F401

                gemini_ok = True
            except ImportError:
                gemini_ok = False

        ollama_ok = OllamaProvider().health_check()
        self.result_ready.emit(gemini_ok, ollama_ok)


class _Dot(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor("#bdbdbd")
        self.setFixedSize(10, 10)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        halo = QColor(self._color)
        halo.setAlpha(60)
        p.setBrush(halo)
        p.drawEllipse(0, 0, 10, 10)
        p.setBrush(self._color)
        p.drawEllipse(2, 2, 6, 6)
        p.end()


class _Pill(QWidget):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.setObjectName("StatusPillWrap")
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 5, 12, 5)
        h.setSpacing(7)
        self._dot = _Dot()
        h.addWidget(self._dot)
        self._label = QLabel(name)
        self._label.setStyleSheet("font-size: 12px; color: palette(text); font-weight: 500;")
        h.addWidget(self._label)
        self.setStyleSheet(
            "QWidget#StatusPillWrap { background: palette(alternate-base); "
            "border: 1px solid palette(midlight); border-radius: 999px; }"
        )

    def set_state(self, name: str, ok: bool | None, ok_text: str, bad_text: str) -> None:
        self._label.setText(name)
        if ok is None:
            self._dot.set_color("#bdbdbd")
            self.setToolTip("Kontroluji…")
        elif ok:
            self._dot.set_color("#3ba55d")
            self.setToolTip(ok_text)
        else:
            self._dot.set_color("#c97a2a")
            self.setToolTip(bad_text)


class StatusBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._gemini = _Pill("Gemini")
        self._ollama = _Pill("Ollama")
        self._gemini.set_state("Gemini", None, "", "")
        self._ollama.set_state("Ollama", None, "", "")
        layout.addWidget(self._gemini)
        layout.addWidget(self._ollama)
        layout.addStretch(1)

        self._thread: QThread | None = None
        self._worker: _HealthWorker | None = None

    def refresh(self, gemini_api_key: str | None) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(500)

        self._gemini.set_state("Gemini", None, "", "")
        self._ollama.set_state("Ollama", None, "", "")

        self._thread = QThread(self)
        self._worker = _HealthWorker(gemini_api_key)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.result_ready.connect(self._on_result)
        self._worker.result_ready.connect(self._thread.quit)
        self._thread.start()

    def _on_result(self, gemini_ok: bool, ollama_ok: bool) -> None:
        self._gemini.set_state(
            "Gemini", gemini_ok,
            "Klíč nastaven — AI body fungují.",
            "Klíč chybí — můžeš použít jen Přepis nebo offline Ollamu.",
        )
        self._ollama.set_state(
            "Ollama", ollama_ok,
            "Offline AI běží.",
            "Offline AI neaktivní — Gemini funguje sám.",
        )

    def stop_and_wait(self, timeout_ms: int = 2000) -> None:
        """Čistě ukončí background health-check thread (volat z closeEvent)."""
        if self._thread is None:
            return
        try:
            if self._thread.isRunning():
                self._thread.quit()
                if not self._thread.wait(timeout_ms):
                    self._thread.terminate()
                    self._thread.wait(500)
        except RuntimeError:
            pass
