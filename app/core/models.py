"""Sdílené datové struktury pro celou aplikaci.

Bez Qt importů — používá se v core/, scripts/, testech a GUI workerech."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class SourceKind(StrEnum):
    AUDIO_VIDEO = "audio_video"
    PRESENTATION = "presentation"


class JobMode(StrEnum):
    """Režim zpracování — vybírá si uživatel v hlavním okně."""

    TRANSCRIBE_ONLY = "transcribe_only"  # jen přepis do Wordu, bez AI a internetu
    FULL = "full"                        # přepis + AI body + pojmy + příklady


class TranscribeBackend(StrEnum):
    """Kdo dělá vlastní speech-to-text."""

    LOCAL_WHISPER = "local_whisper"  # faster-whisper na CPU, offline
    CLOUD_GEMINI = "cloud_gemini"    # Gemini Audio API, vyžaduje internet a souhlas


@dataclass(slots=True)
class SourceFile:
    """Jeden importovaný soubor (audio/video nebo prezentace)."""

    path: Path
    kind: SourceKind
    label: str  # editovatelný štítek od uživatele, default = stem souboru


@dataclass(slots=True)
class TranscriptSegment:
    start: float  # sekundy
    end: float
    text: str


@dataclass(slots=True)
class Transcript:
    """Výsledek přepisu jednoho audio souboru."""

    source_label: str
    language: str
    duration_sec: float
    text: str
    segments: list[TranscriptSegment] = field(default_factory=list)


@dataclass(slots=True)
class SlideText:
    """Textový extrakt jedné prezentace (zploštěný přes všechny slidy)."""

    source_label: str
    text: str
    slide_count: int


@dataclass(slots=True)
class StudyMaterial:
    """Strukturovaný výstup z AI — sériová struktura pro Word export."""

    title: str
    bullets: list[str] = field(default_factory=list)        # Hlavní body k zapamatování
    terms: list[tuple[str, str]] = field(default_factory=list)  # (pojem, definice)
    examples: list[str] = field(default_factory=list)       # Příklady z přednášky
    further_study: list[str] = field(default_factory=list)  # Doporučení k dalšímu studiu
    quiz_questions: list[str] = field(default_factory=list)  # Otázky k procvičení / ke zkoušení žáků
    topic: str = ""  # Krátké téma/předmět (1-2 slova) — pro třídění exportu do složek


@dataclass(slots=True)
class JobConfig:
    """Vstup do pipeline z UI."""

    sources: list[SourceFile]
    user_prompt: str                # slovní popis / instrukce pro AI (ignorováno v TRANSCRIBE_ONLY)
    output_dir: Path
    mode: JobMode = JobMode.FULL
    whisper_model: str = "medium"
    language: str = "cs"
    ai_consent_gemini: bool = False  # uživatel souhlasil s odesláním textu do Gemini
    prefer_offline: bool = False     # použít rovnou Ollama, přeskočit Gemini
    create_md_export: bool = False   # vytvořit .md prompt pro AI agenta
    user_ai_service: str = "none"    # ChatGPT/Claude/Gemini → custom instrukce v .md
    transcribe_backend: TranscribeBackend = TranscribeBackend.LOCAL_WHISPER  # kdo přepisuje audio
