"""JobQueueController — passive tracker batch jobů pro QueuePanel UI.

Tohle NENÍ refaktor pipeline state managementu. Pipeline_worker, _job_queue,
_queue_index v MainWindow zůstávají jak jsou. Controller je *pasivní pozorovatel*
— MainWindow volá add_job/start/update/finish a controller drží list pro UI.

Účel: oddělit "co aktuálně probíhá" od "co je v queue dock UI" — aby QueuePanel
mohl renderovat sekvenční seznam queued/running/done jobů s reuse-přepisu badgi
bez toho, abychom přepisovali existující batch logiku.

Veřejné API:
    JobQueueController()
    add_job(label, file_path, *, cached=False) -> str (id)
    start_job(id)
    update_progress(id, phase: str, fraction: float)
    finish_job(id, output_path: Path)
    error_job(id, message: str)
    cancel_job(id)
    clear_done()
    jobs() -> list[JobState]
    has_running() -> bool

    jobs_changed = Signal()    # vždy když se cokoli změní
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Signal


@dataclass
class JobState:
    """Snapshot jednoho jobu pro QueuePanel renderer.

    Atributy:
        id: unikátní identifikátor (UUID hex, generuje add_job)
        label: lidsky čitelný titulek (např. název souboru bez přípony)
        file_path: zdrojový audio/video soubor
        status: "queued" | "running" | "done" | "error" | "cancelled"
        progress: 0.0..1.0 (relevantní jen pro running)
        phase: kategorie fáze (transcribe / ai / export / atd.) — pro badge
        cached: True pokud byl použit hotový přepis z knihovny (reuse)
        output_path: cesta k vyrobenému .docx (pro done stav)
        error_message: text chyby (pro error stav)
    """

    id: str
    label: str
    file_path: Path
    status: str = "queued"
    progress: float = 0.0
    phase: str = ""
    cached: bool = False
    output_path: Path | None = None
    error_message: str | None = None

    def is_active(self) -> bool:
        return self.status in ("queued", "running")


@dataclass
class _JobsContainer:
    """Wrapper pro list, ať jobs_changed signál může mít typ-safe payload."""

    items: list[JobState] = field(default_factory=list)


class JobQueueController(QObject):
    """Passive job state tracker. UI (QueuePanel) se naslouchá jobs_changed."""

    jobs_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._container = _JobsContainer()

    # ------ Public API ------

    def add_job(
        self,
        label: str,
        file_path: Path,
        *,
        cached: bool = False,
    ) -> str:
        """Přidá nový job do fronty ve stavu 'queued'. Vrátí jeho id."""
        job_id = uuid.uuid4().hex[:8]
        job = JobState(
            id=job_id,
            label=label,
            file_path=file_path,
            cached=cached,
        )
        self._container.items.append(job)
        self.jobs_changed.emit()
        return job_id

    def start_job(self, job_id: str) -> None:
        """Označí job jako 'running'."""
        job = self._find(job_id)
        if job is None or job.status == "running":
            return
        job.status = "running"
        job.progress = 0.0
        self.jobs_changed.emit()

    def update_progress(
        self,
        job_id: str,
        phase: str,
        fraction: float,
    ) -> None:
        """Updatuje progress + fázi running jobu. Bez emit pokud job není 'running'."""
        job = self._find(job_id)
        if job is None or job.status != "running":
            return
        job.progress = max(0.0, min(1.0, fraction))
        if phase:
            job.phase = phase
        self.jobs_changed.emit()

    def finish_job(self, job_id: str, output_path: Path | None = None) -> None:
        """Označí job jako 'done'. Pokud byl cached, status zůstane cached+done."""
        job = self._find(job_id)
        if job is None:
            return
        job.status = "done"
        job.progress = 1.0
        job.output_path = output_path
        self.jobs_changed.emit()

    def error_job(self, job_id: str, message: str) -> None:
        """Označí job jako 'error' s textem chyby."""
        job = self._find(job_id)
        if job is None:
            return
        job.status = "error"
        job.error_message = message
        self.jobs_changed.emit()

    def cancel_job(self, job_id: str) -> None:
        """Označí job jako 'cancelled' (zrušeno uživatelem)."""
        job = self._find(job_id)
        if job is None:
            return
        job.status = "cancelled"
        self.jobs_changed.emit()

    def clear_done(self) -> None:
        """Smaže všechny done/error/cancelled joby z fronty."""
        before = len(self._container.items)
        self._container.items = [j for j in self._container.items if j.is_active()]
        if len(self._container.items) != before:
            self.jobs_changed.emit()

    def clear_all(self) -> None:
        """Smaže všechny joby (resetuje state)."""
        if self._container.items:
            self._container.items = []
            self.jobs_changed.emit()

    def jobs(self) -> list[JobState]:
        """Vrátí kopii listu jobů (UI nesmí mutovat)."""
        return list(self._container.items)

    def has_running(self) -> bool:
        """True pokud existuje alespoň jeden 'running' job."""
        return any(j.status == "running" for j in self._container.items)

    def has_queued(self) -> bool:
        """True pokud existuje alespoň jeden 'queued' job."""
        return any(j.status == "queued" for j in self._container.items)

    def __len__(self) -> int:
        return len(self._container.items)

    # ------ Internal ------

    def _find(self, job_id: str) -> JobState | None:
        for j in self._container.items:
            if j.id == job_id:
                return j
        return None
