"""Orchestrátor celé zakázky: audio extract → transkripce → slide extract → AI → Word.

Volá se z `gui/workers/pipeline_worker.py` v QThread, ale je 100% Qt-free (testovatelné).
"""

from __future__ import annotations

import shutil
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from loguru import logger

from app.config import MIN_FREE_DISK_BYTES, TEMP_DIR, ensure_dirs
from app.core.ai.gemini import GeminiProvider
from app.core.ai.ollama import OllamaProvider
from app.core.ai.router import AIRouter, generate_study_material
from app.core.audio_extract import extract_to_wav, probe_duration_seconds
from app.core.models import (
    JobConfig,
    SlideText,
    SourceKind,
    StudyMaterial,
    Transcript,
    TranscriptSegment,
)
from app.core.pdf_extract import extract_pdf_text
from app.core.pptx_extract import extract_pptx_text
from app.core.transcribe import TranscribeCancelled, transcribe_audio
from app.core.word_export import export_docx, suggested_output_filename


@dataclass(slots=True)
class PipelineResult:
    output_path: Path
    material: StudyMaterial
    transcripts: list[Transcript]
    slides: list[SlideText]


@dataclass(slots=True)
class _Stage:
    """Pomocný descriptor pro reporting progresu."""

    label: str
    weight: float  # podíl na celkovém progresu (sum = 1.0)


# Váhy fází: transkripce dominuje
_STAGES: list[_Stage] = [
    _Stage("Příprava", 0.02),
    _Stage("Extrakce audia", 0.05),
    _Stage("Přepis mluveného slova", 0.70),
    _Stage("Čtení prezentací", 0.03),
    _Stage("Generování bodů přes AI", 0.18),
    _Stage("Export do Wordu", 0.02),
]


class PipelineError(RuntimeError):
    pass


def run_pipeline(
    job: JobConfig,
    *,
    gemini_api_key: str | None,
    progress_cb: Callable[[str, float], None] | None = None,
    transcript_text_cb: Callable[[float, str, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> PipelineResult:
    """Hlavní entry point. Předává progresy přes callback (label, fraction_0_1).

    `transcript_text_cb(seconds_into_audio, label, text)` — volá se po každém přepsaném segmentu
    (pro živý feed v UI).
    """
    ensure_dirs()
    _check_disk_space()

    router = _build_router(job, gemini_api_key)

    work_dir = Path(tempfile.mkdtemp(prefix="hdt_", dir=TEMP_DIR))
    logger.info("Pipeline workspace: {}", work_dir)

    try:
        cumulative = 0.0
        report = _make_reporter(progress_cb)

        # Stage: Příprava
        cumulative = _begin_stage(report, _STAGES[0], cumulative)
        audio_sources = [s for s in job.sources if s.kind == SourceKind.AUDIO_VIDEO]
        presentation_sources = [s for s in job.sources if s.kind == SourceKind.PRESENTATION]
        if not audio_sources and not presentation_sources:
            raise PipelineError("Nejsou nahrány žádné soubory")

        # Stage: Extrakce audia
        cumulative = _begin_stage(report, _STAGES[1], cumulative)
        wav_paths: list[tuple[Path, str, float]] = []  # (wav, label, duration_sec)
        for i, src in enumerate(audio_sources):
            _raise_if_cancelled(cancel_event)
            sub_fraction = (i + 1) / max(len(audio_sources), 1)
            report(f"Extrahuji audio: {src.label}", cumulative - _STAGES[1].weight + _STAGES[1].weight * sub_fraction)
            wav = work_dir / f"audio_{i:02d}.wav"
            extract_to_wav(src.path, wav)
            duration = probe_duration_seconds(src.path) or 0.0
            wav_paths.append((wav, src.label, duration))

        # Stage: Transkripce
        cumulative = _begin_stage(report, _STAGES[2], cumulative)
        transcripts: list[Transcript] = []
        total_duration = sum(d for _, _, d in wav_paths) or 1.0
        accumulated_duration = 0.0
        for wav, label, duration in wav_paths:
            _raise_if_cancelled(cancel_event)
            stage_base = cumulative - _STAGES[2].weight
            file_weight = (duration or 1.0) / total_duration

            def inner_cb(
                fraction: float,
                _label=label,
                _accum=accumulated_duration,
                _weight=file_weight,
                _stage_base=stage_base,
                _total=total_duration,
            ) -> None:
                overall = _stage_base + _STAGES[2].weight * (_accum / _total + _weight * fraction)
                report(f"Přepis: {_label}", overall)

            def inner_text_cb(seconds: float, text: str, _label=label) -> None:
                if transcript_text_cb is not None:
                    try:
                        transcript_text_cb(seconds, _label, text)
                    except Exception as cb_exc:  # noqa: BLE001
                        logger.warning("transcript_text_cb selhal: {}", cb_exc)

            try:
                tr = transcribe_audio(
                    wav,
                    source_label=label,
                    model_size=job.whisper_model,
                    language=job.language,
                    progress_cb=inner_cb,
                    text_cb=inner_text_cb,
                    cancel_event=cancel_event,
                )
            except TranscribeCancelled:
                raise
            transcripts.append(tr)
            accumulated_duration += duration

        # Stage: Slide extract
        cumulative = _begin_stage(report, _STAGES[3], cumulative)
        slides: list[SlideText] = []
        for i, src in enumerate(presentation_sources):
            _raise_if_cancelled(cancel_event)
            sub_fraction = (i + 1) / max(len(presentation_sources), 1)
            report(f"Čtu prezentaci: {src.label}", cumulative - _STAGES[3].weight + _STAGES[3].weight * sub_fraction)
            if src.path.suffix.lower() == ".pdf":
                slides.append(extract_pdf_text(src.path, src.label))
            elif src.path.suffix.lower() == ".pptx":
                slides.append(extract_pptx_text(src.path, src.label))

        # Auto-save raw přepisu PŘED voláním AI — kdyby Gemini selhalo,
        # uživatel má aspoň přepis jako .txt v output složce.
        backup_txt = _save_transcript_backup(transcripts, Path(job.output_dir))
        if backup_txt is not None:
            logger.info("Záloha přepisu: {}", backup_txt)

        # Stage: AI
        cumulative = _begin_stage(report, _STAGES[4], cumulative)
        _raise_if_cancelled(cancel_event)
        report("Generuji body přes AI…", cumulative - _STAGES[4].weight * 0.5)
        material = generate_study_material(
            router=router,
            transcripts=transcripts,
            slides=slides,
            user_prompt=job.user_prompt,
        )

        # Stage: Word export
        cumulative = _begin_stage(report, _STAGES[5], cumulative)
        _raise_if_cancelled(cancel_event)
        out_filename = suggested_output_filename(material)
        out_path = Path(job.output_dir) / out_filename
        export_docx(
            output_path=out_path,
            material=material,
            transcripts=transcripts,
            slides=slides,
            sources=job.sources,
            user_prompt=job.user_prompt,
        )

        report("Hotovo", 1.0)
        return PipelineResult(output_path=out_path, material=material, transcripts=transcripts, slides=slides)

    finally:
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except OSError:
            logger.warning("Nepodařilo se smazat workspace {}", work_dir)


def _build_router(job: JobConfig, gemini_api_key: str | None) -> AIRouter:
    primary = None
    fallback = OllamaProvider()

    if not job.prefer_offline and job.ai_consent_gemini and gemini_api_key:
        try:
            primary = GeminiProvider(api_key=gemini_api_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Nepodařilo se inicializovat Gemini: {}", exc)
            primary = None

    if primary is None:
        # Bez Gemini → Ollama je primární i jediný
        return AIRouter(primary=fallback, fallback=None)
    return AIRouter(primary=primary, fallback=fallback)


def _make_reporter(callback: Callable[[str, float], None] | None) -> Callable[[str, float], None]:
    if callback is None:

        def noop(_label: str, _fraction: float) -> None:
            return

        return noop

    def _wrap(label: str, fraction: float) -> None:
        try:
            callback(label, max(0.0, min(1.0, fraction)))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Progress callback selhal: {}", exc)

    return _wrap


def _begin_stage(report: Callable[[str, float], None], stage: _Stage, cumulative: float) -> float:
    new_total = cumulative + stage.weight
    report(stage.label, new_total - stage.weight)
    return new_total


def _check_disk_space() -> None:
    usage = shutil.disk_usage(TEMP_DIR.parent if TEMP_DIR.exists() else Path.home())
    if usage.free < MIN_FREE_DISK_BYTES:
        gb_free = usage.free / 1024 / 1024 / 1024
        raise PipelineError(
            f"Málo místa na disku: {gb_free:.1f} GB volných (potřeba aspoň 2 GB). "
            "Uvolni místo a zkus to znovu."
        )


def _raise_if_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise TranscribeCancelled("Zpracování zrušeno uživatelem")


def _save_transcript_backup(transcripts: list[Transcript], output_dir: Path) -> Path | None:
    """Uloží raw přepis do .txt souboru pro případ že AI selže.

    Soubor je čitelný i jako pouhý text — kamarádka má co studovat i bez bodů.
    """
    if not transcripts:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    path = output_dir / f"prepis_{timestamp}.txt"

    lines: list[str] = []
    lines.append(f"# Přepis přednášky — {datetime.now().strftime('%d. %m. %Y %H:%M')}\n")
    for tr in transcripts:
        lines.append(f"\n\n=== {tr.source_label} ({_format_seconds(tr.duration_sec)}) ===\n\n")
        if tr.segments:
            for seg in tr.segments:
                lines.append(f"[{_format_seconds(seg.start)}] {seg.text}\n")
        else:
            lines.append(tr.text + "\n")
    try:
        path.write_text("".join(lines), encoding="utf-8")
        return path
    except OSError as exc:
        logger.warning("Nepodařilo se uložit zálohu přepisu: {}", exc)
        return None


def _format_seconds(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def estimate_total_processing_seconds(
    source_durations_sec: list[float],
    *,
    whisper_model: str = "medium",
    has_ai: bool = True,
) -> tuple[float, float]:
    """Odhad celkového času pipeline. Vrací (low, high) v sekundách.

    Použito pro pre-start dialog typu "počítej s 60-90 min".
    """
    from app.core.transcribe import estimate_transcribe_seconds

    total_audio = sum(source_durations_sec)
    transcribe_low = estimate_transcribe_seconds(total_audio, whisper_model) * 0.7
    transcribe_high = estimate_transcribe_seconds(total_audio, whisper_model) * 1.3

    ai_seconds = 30.0 if has_ai else 0.0  # Gemini je rychlý, Ollama by byla výrazně víc
    if total_audio > 1800:  # > 30 min → map-reduce, víc dotazů
        ai_seconds = 60.0

    overhead = 15.0  # FFmpeg + slide extract + Word export
    return (transcribe_low + ai_seconds + overhead, transcribe_high + ai_seconds + overhead)


def format_duration_human(seconds: float) -> str:
    """Vrátí lidsky čitelnou délku: 'cca 4 minuty', 'cca 1 hod 15 min'."""
    seconds = int(seconds)
    if seconds < 60:
        return f"cca {seconds} sekund"
    minutes = seconds // 60
    if minutes < 60:
        return f"cca {minutes} {_minutes_word(minutes)}"
    hours = minutes // 60
    rem_min = minutes % 60
    if rem_min == 0:
        return f"cca {hours} {_hours_word(hours)}"
    return f"cca {hours} {_hours_word(hours)} {rem_min} min"


def _minutes_word(n: int) -> str:
    if n == 1:
        return "minutu"
    if 2 <= n <= 4:
        return "minuty"
    return "minut"


def _hours_word(n: int) -> str:
    if n == 1:
        return "hodinu"
    if 2 <= n <= 4:
        return "hodiny"
    return "hodin"


def parse_transcript_backup_file(txt_path: Path) -> list[Transcript]:
    """Načte zálohu přepisu (.txt) zpět do `Transcript` objektů.

    Očekává formát, který produkuje `_save_transcript_backup`:
        # Přepis přednášky — DD. MM. YYYY HH:MM

        === Štítek (HH:MM:SS) ===

        [00:00] věta
        [00:10] věta
    """
    txt_path = Path(txt_path)
    if not txt_path.is_file():
        raise FileNotFoundError(f"Soubor přepisu nenalezen: {txt_path}")

    content = txt_path.read_text(encoding="utf-8")
    transcripts: list[Transcript] = []
    current_label: str | None = None
    current_segments: list[TranscriptSegment] = []
    current_lines: list[str] = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("#"):
            continue
        if line.startswith("===") and line.endswith("==="):
            if current_label is not None:
                transcripts.append(_finalize_loaded(current_label, current_segments, current_lines))
            inner = line.strip("= ").strip()
            if "(" in inner:
                inner = inner.split("(")[0].strip()
            current_label = inner or "Přepis"
            current_segments = []
            current_lines = []
            continue
        if not line:
            continue

        timestamp_sec, text = _parse_transcript_line(line)
        if text:
            current_lines.append(text)
            if timestamp_sec is not None:
                current_segments.append(TranscriptSegment(start=timestamp_sec, end=timestamp_sec, text=text))

    if current_label is not None or current_lines:
        transcripts.append(_finalize_loaded(current_label or "Přepis", current_segments, current_lines))

    return [t for t in transcripts if t.text]


def _finalize_loaded(label: str, segments: list[TranscriptSegment], lines: list[str]) -> Transcript:
    duration = segments[-1].start if segments else 0.0
    return Transcript(
        source_label=label,
        language="cs",
        duration_sec=duration,
        text=" ".join(lines).strip(),
        segments=segments,
    )


def _parse_transcript_line(line: str) -> tuple[float | None, str]:
    """Parsuje řádek typu `[00:23] text` nebo `[01:02:03] text`."""
    if not line.startswith("["):
        return None, line.strip()
    close = line.find("]")
    if close == -1:
        return None, line.strip()
    timestamp_str = line[1:close].strip()
    text = line[close + 1 :].strip()
    parts = timestamp_str.split(":")
    try:
        if len(parts) == 2:
            m, s = int(parts[0]), int(parts[1])
            seconds = m * 60 + s
        elif len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            seconds = h * 3600 + m * 60 + s
        else:
            return None, text
    except ValueError:
        return None, text
    return float(seconds), text


def regenerate_from_transcript(
    *,
    txt_path: Path,
    user_prompt: str,
    output_dir: Path,
    gemini_api_key: str | None,
    ai_consent_gemini: bool,
    prefer_offline: bool,
    slides: list[SlideText] | None = None,
    progress_cb: Callable[[str, float], None] | None = None,
) -> PipelineResult:
    """Vytvoří nový .docx ze stávajícího .txt přepisu — přeskočí transkripci.

    Užitečné když Gemini vrátilo slabé body a kamarádka chce zkusit upravený popis.
    """
    from app.core.word_export import export_docx, suggested_output_filename

    report = _make_reporter(progress_cb)

    report("Čtu přepis ze souboru…", 0.10)
    transcripts = parse_transcript_backup_file(txt_path)
    if not transcripts:
        raise PipelineError(f"Přepis v {txt_path.name} je prázdný nebo nevalidní.")

    slides = slides or []

    # Vytvořit ad-hoc job pro router
    pseudo_job = JobConfig(
        sources=[],
        user_prompt=user_prompt,
        output_dir=Path(output_dir),
        ai_consent_gemini=ai_consent_gemini,
        prefer_offline=prefer_offline,
    )
    router = _build_router(pseudo_job, gemini_api_key)

    report("Generuji body přes AI…", 0.50)
    material = generate_study_material(
        router=router,
        transcripts=transcripts,
        slides=slides,
        user_prompt=user_prompt,
    )

    report("Ukládám Word…", 0.90)
    out_path = Path(output_dir) / suggested_output_filename(material)
    export_docx(
        output_path=out_path,
        material=material,
        transcripts=transcripts,
        slides=slides,
        sources=[],
        user_prompt=user_prompt,
    )
    report("Hotovo", 1.0)
    return PipelineResult(output_path=out_path, material=material, transcripts=transcripts, slides=slides)


def humanize_error(exc: BaseException) -> str:
    """Přepíše obvyklé technické chyby do srozumitelné češtiny.

    Volá se v pipeline_worker při neočekávané chybě (jiné než `PipelineError`,
    který už má smysluplnou zprávu).
    """
    name = type(exc).__name__
    message = str(exc)

    if name in ("ConnectError", "ConnectTimeout", "ReadTimeout"):
        return "Není připojení k internetu nebo Gemini neodpovídá. Zkontroluj síť a zkus to znovu."
    if isinstance(exc, PermissionError):
        return f"Nemám oprávnění zapisovat soubor: {message}. Vyber jinou výstupní složku v Nastavení."
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return "Plný disk. Uvolni alespoň 2 GB a zkus to znovu."
    if isinstance(exc, FileNotFoundError):
        return f"Soubor nenalezen: {message}. Zkontroluj, jestli existuje a není přejmenovaný."

    lowered = message.lower()
    if "out of memory" in lowered or "cuda out of memory" in lowered:
        return "Whisper model potřebuje víc paměti, než PC nabízí. Vyber menší model v Nastavení (např. small)."
    if "ffmpeg" in lowered and ("not found" in lowered or "no such file" in lowered):
        return "FFmpeg nebyl nalezen. Pokud používáš dev verzi, doinstaluj `brew install ffmpeg` / `apt install ffmpeg`."
    if "model.bin" in lowered or "snapshot_download" in lowered:
        return "Whisper model se nestáhl správně. Otevři Nastavení → změň model → stáhne se znovu."

    return f"Neočekávaná chyba: {message}"
