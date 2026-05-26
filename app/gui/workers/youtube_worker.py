"""QThread worker pro stahování audia z YouTube URL přes yt-dlp."""

from __future__ import annotations

from loguru import logger
from PySide6.QtCore import QObject, QThread, Signal

from app.core.youtube_fetch import YouTubeFetchError, fetch_audio

__all__ = ["YouTubeFetchWorker"]


class _YouTubeRunner(QObject):
    progress = Signal(float, str)        # fraction, status_text
    finished_ok = Signal(object)         # SourceFile
    finished_error = Signal(str)

    def __init__(self, url: str) -> None:
        super().__init__()
        self._url = url

    def run(self) -> None:
        try:
            source = fetch_audio(self._url, progress_cb=self._emit_progress)
            self.finished_ok.emit(source)
        except YouTubeFetchError as exc:
            logger.warning("YouTube fetch failed: {}", exc)
            self.finished_error.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("YouTube fetch unexpected: {}", exc)
            self.finished_error.emit(f"Nečekaná chyba: {exc}")

    def _emit_progress(self, fraction: float, status: str) -> None:
        self.progress.emit(fraction, status)


class YouTubeFetchWorker(QObject):
    """Background download — emituje progress a na konci SourceFile."""

    progress = Signal(float, str)
    finished_ok = Signal(object)
    finished_error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._runner: _YouTubeRunner | None = None

    def start(self, url: str) -> None:
        if self._thread is not None and self._thread.isRunning():
            raise RuntimeError("YouTube fetch už běží")

        self._thread = QThread()
        self._runner = _YouTubeRunner(url)
        self._runner.moveToThread(self._thread)
        self._thread.started.connect(self._runner.run)
        self._runner.progress.connect(self.progress.emit)
        self._runner.finished_ok.connect(self.finished_ok.emit)
        self._runner.finished_error.connect(self.finished_error.emit)
        self._runner.finished_ok.connect(self._thread.quit)
        self._runner.finished_error.connect(self._thread.quit)
        self._thread.start()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def stop_and_wait(self, timeout_ms: int = 3000) -> None:
        if self._thread is None:
            return
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(timeout_ms)


