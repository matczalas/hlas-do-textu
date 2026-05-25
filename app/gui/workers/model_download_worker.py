"""QThread worker pro stažení Whisper modelu z Hugging Face."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from app.core.model_downloader import download_model


class _Runner(QObject):
    progress = Signal(str, float)       # status, fraction (-1 = neznámý)
    finished_ok = Signal()
    finished_error = Signal(str)

    def __init__(self, model_name: str) -> None:
        super().__init__()
        self._model_name = model_name

    def run(self) -> None:
        try:
            download_model(self._model_name, progress_cb=self._emit)
            self.finished_ok.emit()
        except Exception as exc:  # noqa: BLE001
            self.finished_error.emit(str(exc))

    def _emit(self, status: str, fraction: float) -> None:
        self.progress.emit(status, fraction)


class ModelDownloadWorker(QObject):
    progress = Signal(str, float)
    finished_ok = Signal()
    finished_error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._runner: _Runner | None = None

    def start(self, model_name: str) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        self._thread = QThread()
        self._runner = _Runner(model_name)
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
