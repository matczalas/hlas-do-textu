"""QThread worker, který v pozadí spustí `core.pipeline.run_pipeline`."""

from __future__ import annotations

import threading

from loguru import logger
from PySide6.QtCore import QObject, QThread, Signal

from app.core.models import JobConfig
from app.core.pipeline import PipelineError, PipelineResult, humanize_error, run_pipeline
from app.core.transcribe import TranscribeCancelled


class _PipelineRunner(QObject):
    progress = Signal(str, float)        # label, fraction
    transcript_text = Signal(float, str, str)  # seconds, source_label, text
    finished_ok = Signal(object)         # PipelineResult
    finished_error = Signal(str, bool)   # message, was_cancelled

    def __init__(self, job: JobConfig, gemini_api_key: str | None, cancel_event: threading.Event) -> None:
        super().__init__()
        self._job = job
        self._gemini_api_key = gemini_api_key
        self._cancel_event = cancel_event

    def run(self) -> None:
        try:
            result = run_pipeline(
                self._job,
                gemini_api_key=self._gemini_api_key,
                progress_cb=self._emit_progress,
                transcript_text_cb=self._emit_transcript_text,
                cancel_event=self._cancel_event,
            )
            self.finished_ok.emit(result)
        except TranscribeCancelled as exc:
            logger.warning("Pipeline cancelled: {}", exc)
            self.finished_error.emit(str(exc), True)
        except PipelineError as exc:
            logger.error("Pipeline error: {}", exc)
            self.finished_error.emit(str(exc), False)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Pipeline unexpected: {}", exc)
            self.finished_error.emit(humanize_error(exc), False)

    def _emit_progress(self, label: str, fraction: float) -> None:
        self.progress.emit(label, fraction)

    def _emit_transcript_text(self, seconds: float, label: str, text: str) -> None:
        self.transcript_text.emit(seconds, label, text)


class PipelineWorker(QObject):
    """Veřejný API obal — vlastní QThread + cancel_event."""

    progress = Signal(str, float)
    transcript_text = Signal(float, str, str)  # seconds, label, text
    finished_ok = Signal(object)       # PipelineResult
    finished_error = Signal(str, bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._runner: _PipelineRunner | None = None
        self._cancel_event = threading.Event()

    def start(self, job: JobConfig, gemini_api_key: str | None) -> None:
        if self._thread is not None and self._thread.isRunning():
            raise RuntimeError("Pipeline už běží")

        self._cancel_event = threading.Event()
        self._thread = QThread()
        self._runner = _PipelineRunner(job, gemini_api_key, self._cancel_event)
        self._runner.moveToThread(self._thread)

        self._thread.started.connect(self._runner.run)
        self._runner.progress.connect(self.progress.emit)
        self._runner.transcript_text.connect(self.transcript_text.emit)
        self._runner.finished_ok.connect(self._on_finished_ok)
        self._runner.finished_error.connect(self._on_finished_error)
        self._runner.finished_ok.connect(self._thread.quit)
        self._runner.finished_error.connect(self._thread.quit)

        self._thread.start()

    def cancel(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._cancel_event.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def stop_and_wait(self, timeout_ms: int = 5000) -> None:
        if self._thread is None:
            return
        self._cancel_event.set()
        self._thread.quit()
        self._thread.wait(timeout_ms)

    def _on_finished_ok(self, result: PipelineResult) -> None:
        self.finished_ok.emit(result)

    def _on_finished_error(self, message: str, cancelled: bool) -> None:
        self.finished_error.emit(message, cancelled)
