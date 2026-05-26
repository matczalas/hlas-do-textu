"""QThread worker pro chat session — posílá zprávy AI bez blokování UI."""

from __future__ import annotations

from loguru import logger
from PySide6.QtCore import QObject, QThread, Signal

from app.core.ai.chat import ChatSession

__all__ = ["ChatWorker"]


class _ChatRunner(QObject):
    finished_ok = Signal(object)         # ChatResponse
    finished_error = Signal(str)

    def __init__(self, session: ChatSession, message: str) -> None:
        super().__init__()
        self._session = session
        self._message = message

    def run(self) -> None:
        try:
            response = self._session.send(self._message)
            self.finished_ok.emit(response)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Chat selhal: {}", exc)
            self.finished_error.emit(str(exc))


class ChatWorker(QObject):
    """Pošle zprávu na pozadí, emituje response signál."""

    finished_ok = Signal(object)
    finished_error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._runner: _ChatRunner | None = None

    def send(self, session: ChatSession, message: str) -> None:
        if self._thread is not None and self._thread.isRunning():
            raise RuntimeError("Chat už zpracovává předchozí zprávu")

        # Před přepsáním self._thread počkáme na předchozí thread (i když už
        # quit() byl emitnutý), jinak by mohl být GC'd před doběhem.
        if self._thread is not None:
            self._thread.wait(1000)

        self._thread = QThread()
        self._runner = _ChatRunner(session, message)
        self._runner.moveToThread(self._thread)
        self._thread.started.connect(self._runner.run)
        self._runner.finished_ok.connect(self.finished_ok.emit)
        self._runner.finished_error.connect(self.finished_error.emit)
        self._runner.finished_ok.connect(self._thread.quit)
        self._runner.finished_error.connect(self._thread.quit)
        self._thread.start()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def stop_and_wait(self, timeout_ms: int = 3000) -> None:
        """Zavolat před destrukcí parent dialogu, ať vlákno doběhne čistě."""
        if self._thread is None:
            return
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(timeout_ms)


