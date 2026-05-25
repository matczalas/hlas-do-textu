"""QThread worker pro regeneraci bodů ze stávajícího .txt přepisu (bez Whisper)."""

from __future__ import annotations

from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, QThread, Signal

from app.core.pipeline import (
    PipelineError,
    humanize_error,
    regenerate_from_transcript,
)


class _Runner(QObject):
    progress = Signal(str, float)
    finished_ok = Signal(object)
    finished_error = Signal(str)

    def __init__(
        self,
        txt_path: Path,
        user_prompt: str,
        output_dir: Path,
        gemini_api_key: str | None,
        ai_consent_gemini: bool,
        prefer_offline: bool,
    ) -> None:
        super().__init__()
        self._txt_path = txt_path
        self._user_prompt = user_prompt
        self._output_dir = output_dir
        self._gemini_api_key = gemini_api_key
        self._ai_consent_gemini = ai_consent_gemini
        self._prefer_offline = prefer_offline

    def run(self) -> None:
        try:
            result = regenerate_from_transcript(
                txt_path=self._txt_path,
                user_prompt=self._user_prompt,
                output_dir=self._output_dir,
                gemini_api_key=self._gemini_api_key,
                ai_consent_gemini=self._ai_consent_gemini,
                prefer_offline=self._prefer_offline,
                progress_cb=lambda lbl, frac: self.progress.emit(lbl, frac),
            )
            self.finished_ok.emit(result)
        except PipelineError as exc:
            logger.error("Regenerate error: {}", exc)
            self.finished_error.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Regenerate unexpected: {}", exc)
            self.finished_error.emit(humanize_error(exc))


class RegenerateWorker(QObject):
    progress = Signal(str, float)
    finished_ok = Signal(object)  # PipelineResult
    finished_error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._runner: _Runner | None = None

    def start(
        self,
        *,
        txt_path: Path,
        user_prompt: str,
        output_dir: Path,
        gemini_api_key: str | None,
        ai_consent_gemini: bool,
        prefer_offline: bool,
    ) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        self._thread = QThread()
        self._runner = _Runner(
            txt_path,
            user_prompt,
            output_dir,
            gemini_api_key,
            ai_consent_gemini,
            prefer_offline,
        )
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
