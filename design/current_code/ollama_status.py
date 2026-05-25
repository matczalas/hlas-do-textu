"""Status řádek: Gemini + Ollama dostupnost."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class _HealthWorker(QObject):
    """Spustí health-checks na pozadí (síťové operace nesmí blokovat UI)."""

    result_ready = Signal(bool, bool)  # gemini_ok, ollama_ok

    def __init__(self, gemini_api_key: str | None) -> None:
        super().__init__()
        self._gemini_api_key = gemini_api_key

    def run(self) -> None:
        from app.core.ai.ollama import OllamaProvider

        gemini_ok = False
        if self._gemini_api_key:
            try:
                # Health check Gemini = jen že klíč není prázdný a SDK je k dispozici;
                # plný API call bychom dělali zbytečně často
                from google import genai  # noqa: F401

                gemini_ok = True
            except ImportError:
                gemini_ok = False

        ollama_ok = OllamaProvider().health_check()
        self.result_ready.emit(gemini_ok, ollama_ok)


class StatusBar(QWidget):
    """Inline řádek s tečkami pro Gemini a Ollama."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        self._gemini_label = QLabel("Gemini: ⏳ kontroluji…")
        self._ollama_label = QLabel("Ollama (offline AI): ⏳ kontroluji…")
        layout.addWidget(self._gemini_label)
        layout.addWidget(self._ollama_label)
        layout.addStretch(1)

        self._thread: QThread | None = None
        self._worker: _HealthWorker | None = None

    def refresh(self, gemini_api_key: str | None) -> None:
        # Cancel previous run pokud probíhá
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(500)

        self._thread = QThread(self)
        self._worker = _HealthWorker(gemini_api_key)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.result_ready.connect(self._on_result)
        self._worker.result_ready.connect(self._thread.quit)
        self._thread.start()

    def _on_result(self, gemini_ok: bool, ollama_ok: bool) -> None:
        self._gemini_label.setText("Gemini: ✅ klíč nastaven" if gemini_ok else "Gemini: ❌ nedostupný (chybí klíč nebo SDK)")
        self._ollama_label.setText(
            "Ollama (offline AI): ✅ běží" if ollama_ok else "Ollama (offline AI): ❌ neaktivní"
        )
