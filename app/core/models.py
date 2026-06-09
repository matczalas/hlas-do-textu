"""Sdílené datové struktury pro celou aplikaci.

Bez Qt importů — používá se v core/, scripts/, testech a GUI workerech."""

from __future__ import annotations

from collections.abc import Iterator
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
    # Označení mluvčího z diarizace (např. "Mluvčí 1"). Prázdné = nerozlišeno
    # (lokální Whisper diarizaci neumí; Gemini ji dělá jen když je zapnutá).
    speaker: str = ""


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


# ---------------------------------------------------------------------------
# Flexibilní sekční struktura výstupu
# ---------------------------------------------------------------------------
# Místo pevných polí (bullets/terms/examples/...) má AI volnost vracet libovolné
# pojmenované sekce s konkrétním obsahem typu (bullets / definice / Q&A /
# klíč-hodnota / odstavec). Tím sedí jedna struktura na studenta, učitele
# i finančního poradce — každý template má jiné sekce.
#
# Legacy pole (`bullets`, `terms`, `examples`, `further_study`, `quiz_questions`)
# zůstávají na `StudyMaterial` kvůli zpětné kompatibilitě (starý chat parser,
# regenerate z .txt, testy). Pokud `sections` je neprázdný, použije se přednostně.

SECTION_KIND_BULLETS = "bullets"          # items: list[str]
SECTION_KIND_DEFINITIONS = "definitions"  # items: list[(pojem, definice)]
SECTION_KIND_QA = "qa"                    # items: list[(otázka, odpověď_nebo_prazdny_string)]
SECTION_KIND_KEY_VALUE = "key_value"      # items: list[(klíč, hodnota)]
SECTION_KIND_PARAGRAPH = "paragraph"      # items: list[str]  (každý prvek = jeden odstavec)

_VALID_SECTION_KINDS = frozenset(
    {
        SECTION_KIND_BULLETS,
        SECTION_KIND_DEFINITIONS,
        SECTION_KIND_QA,
        SECTION_KIND_KEY_VALUE,
        SECTION_KIND_PARAGRAPH,
    }
)


@dataclass(slots=True)
class StudySection:
    """Jedna kapitola finálního dokumentu.

    `kind` určuje, jak Word export vykreslí položky. `items` má strukturu
    závislou na `kind`:
        - bullets / paragraph: list[str]
        - definitions / qa / key_value: list[(str, str)]
    """

    title: str
    kind: str
    items: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.kind not in _VALID_SECTION_KINDS:
            # Nezvalidní kind → spadneme na bullets, ať to nezhasí export
            self.kind = SECTION_KIND_BULLETS


@dataclass(slots=True)
class StudyMaterial:
    """Strukturovaný výstup z AI — flexibilní sekce + zpětná kompatibilita."""

    title: str
    # Krátké téma/předmět (1-2 slova) — pro třídění exportu do podsložek
    topic: str = ""
    # Nová cesta — pokud neprázdný, použije se přednostně
    sections: list[StudySection] = field(default_factory=list)

    # ----- Legacy pole (zachovaná kvůli starému chatu a testům) -----
    # Pokud AI vrátí starý formát, parser je naplní; iter_sections() z nich
    # postaví "syntetické" sekce s defaultními českými nadpisy.
    bullets: list[str] = field(default_factory=list)
    terms: list[tuple[str, str]] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    further_study: list[str] = field(default_factory=list)
    quiz_questions: list[str] = field(default_factory=list)

    def iter_sections(self) -> Iterator[StudySection]:
        """Vrací sekce k vykreslení. Pokud `sections` je prázdný, sestaví je z legacy polí."""
        if self.sections:
            yield from self.sections
            return
        yield from _legacy_fields_to_sections(self)

    def has_any_content(self) -> bool:
        """True, pokud existuje aspoň jedna sekce s nějakou položkou."""
        return any(s.items for s in self.iter_sections())


def _legacy_fields_to_sections(material: StudyMaterial) -> Iterator[StudySection]:
    """Postaví defaultní sekce z legacy polí — kvůli compat se starým výstupem."""
    if material.bullets:
        yield StudySection(
            title="Hlavní body k zapamatování",
            kind=SECTION_KIND_BULLETS,
            items=list(material.bullets),
        )
    if material.terms:
        yield StudySection(
            title="Klíčové pojmy",
            kind=SECTION_KIND_DEFINITIONS,
            items=[(t, d) for t, d in material.terms],
        )
    if material.examples:
        yield StudySection(
            title="Příklady z přednášky",
            kind=SECTION_KIND_BULLETS,
            items=list(material.examples),
        )
    if material.quiz_questions:
        yield StudySection(
            title="Otázky k procvičení a zkoušení",
            kind=SECTION_KIND_QA,
            # Legacy formát: jen otázky bez odpovědí
            items=[(q, "") for q in material.quiz_questions],
        )
    if material.further_study:
        yield StudySection(
            title="Doporučení k dalšímu studiu",
            kind=SECTION_KIND_BULLETS,
            items=list(material.further_study),
        )


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
    # Klíč šablony z PROMPT_TEMPLATES (student/teacher_lesson/sales_meeting/...).
    # Určuje, jaké sekce AI vyrobí. Default = obecný "student" prompt.
    prompt_template_key: str = "student"
    # Rozlišovat mluvčí (diarizace). Funguje jen s cloud Gemini přepisem —
    # lokální Whisper to neumí. Zapíná se automaticky u konverzačních šablon
    # (sales_*, meeting_minutes), kde je to užitečné.
    diarize: bool = False
