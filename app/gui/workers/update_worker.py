"""QThread worker pro update flow.

Dvě fáze:
- check() — GET na GitHub API, vrátí UpdateInfo nebo None
- download() — stáhne installer s progress, pak emituje finished_ok s Path
"""
from __future__ import annotations

from loguru import logger
from PySide6.QtCore import QObject, QThread, Signal

from app.updater import UpdateInfo, check_for_update, download_installer


class _CheckRunner(QObject):
    finished = Signal(object)  # UpdateInfo | None

    def run(self) -> None:
        try:
            info = check_for_update()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Update check selhal: {}", exc)
            info = None
        self.finished.emit(info)


class _DownloadRunner(QObject):
    progress = Signal(int, int)  # downloaded, total
    finished_ok = Signal(object)  # Path
    finished_error = Signal(str)

    def __init__(self, info: UpdateInfo) -> None:
        super().__init__()
        self._info = info

    def run(self) -> None:
        try:
            path = download_installer(self._info, progress_cb=self._emit_progress)
            self.finished_ok.emit(path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Update download selhal: {}", exc)
            self.finished_error.emit(str(exc))

    def _emit_progress(self, downloaded: int, total: int) -> None:
        self.progress.emit(downloaded, total)


class UpdateCheckWorker(QObject):
    """Background check — vrací UpdateInfo nebo None přes signál."""

    finished = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._runner: _CheckRunner | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        self._thread = QThread()
        self._runner = _CheckRunner()
        self._runner.moveToThread(self._thread)
        self._thread.started.connect(self._runner.run)
        self._runner.finished.connect(self.finished.emit)
        self._runner.finished.connect(self._thread.quit)
        self._thread.start()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()


class UpdateDownloadWorker(QObject):
    """Background download installer .exe — emituje progress, na konci Path."""

    progress = Signal(int, int)
    finished_ok = Signal(object)  # Path
    finished_error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._runner: _DownloadRunner | None = None

    def start(self, info: UpdateInfo) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        self._thread = QThread()
        self._runner = _DownloadRunner(info)
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
