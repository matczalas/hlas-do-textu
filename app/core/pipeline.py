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
from app.core.md_export import export_markdown
from app.core.models import (
    JobConfig,
    JobMode,
    SlideText,
    SourceKind,
    StudyMaterial,
    TranscribeBackend,
    Transcript,
    TranscriptSegment,
)
from app.core.pdf_extract import extract_pdf_text
from app.core.pptx_extract import extract_pptx_text
from app.core.transcribe import TranscribeCancelled, transcribe_audio
from app.core.transcribe_gemini import (
    TranscribeGeminiCancelled,
    transcribe_audio_via_gemini,
)
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


# Váhy fází pro režim FULL — transkripce dominuje
_STAGES_FULL: list[_Stage] = [
    _Stage("Příprava", 0.02),
    _Stage("Extrakce audia", 0.05),
    _Stage("Přepis mluveného slova", 0.70),
    _Stage("Čtení prezentací", 0.03),
    _Stage("Generování bodů přes AI", 0.18),
    _Stage("Export do Wordu", 0.02),
]

# Váhy fází pro režim TRANSCRIBE_ONLY — bez AI, bez slidů
_STAGES_TRANSCRIBE_ONLY: list[_Stage] = [
    _Stage("Příprava", 0.02),
    _Stage("Extrakce audia", 0.06),
    _Stage("Přepis mluveného slova", 0.88),
    _Stage("Export do Wordu", 0.04),
]

_STAGES = _STAGES_FULL  # backward compat pro místa která indexují _STAGES[2]


class PipelineError(RuntimeError):
    pass


def run_pipeline(
    job: JobConfig,
    *,
    gemini_api_key: str | None,
    progress_cb: Callable[[str, float], None] | None = None,
    transcript_text_cb: Callable[[float, str, str], None] | None = None,
    cloud_fallback_cb: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> PipelineResult:
    """Hlavní entry point. Předává progresy přes callback (label, fraction_0_1).

    `transcript_text_cb(seconds_into_audio, label, text)` — volá se po každém přepsaném segmentu
    (pro živý feed v UI).
    """
    ensure_dirs()
    _check_disk_space()

    transcribe_only = job.mode == JobMode.TRANSCRIBE_ONLY
    stages = _STAGES_TRANSCRIBE_ONLY if transcribe_only else _STAGES_FULL
    router = None if transcribe_only else _build_router(job, gemini_api_key)

    work_dir = Path(tempfile.mkdtemp(prefix="hdt_", dir=TEMP_DIR))
    logger.info("Pipeline workspace: {} (mode={})", work_dir, job.mode.value)

    try:
        cumulative = 0.0
        report = _make_reporter(progress_cb)

        # Stage: Příprava
        cumulative = _begin_stage(report, stages[0], cumulative)
        audio_sources = [s for s in job.sources if s.kind == SourceKind.AUDIO_VIDEO]
        presentation_sources = [s for s in job.sources if s.kind == SourceKind.PRESENTATION]
        if not audio_sources and not presentation_sources:
            raise PipelineError("Nejsou nahrány žádné soubory")
        if transcribe_only and not audio_sources:
            raise PipelineError("Režim 'Jen přepis' potřebuje aspoň jednu nahrávku")

        # Striktnější kontrola klíče: whitespace " " by jinak prošel `bool()`
        # a cloud volání by selhalo až na transcribe_gemini straně.
        clean_key = (gemini_api_key or "").strip()
        use_gemini = (
            job.transcribe_backend == TranscribeBackend.CLOUD_GEMINI
            and bool(clean_key)
        )
        if job.transcribe_backend == TranscribeBackend.CLOUD_GEMINI and not clean_key:
            logger.warning(
                "Cloud Gemini backend zvolen, ale chybí API klíč — padáme zpět na lokální Whisper"
            )
            # User vidí v UI, že vybral cloud, ale klíč nemá. Informujeme ho přes
            # stejný kanál jako runtime cloud chyby.
            if cloud_fallback_cb is not None:
                try:
                    cloud_fallback_cb(
                        "Nemáš Gemini API klíč v Nastavení — používám lokální Whisper."
                    )
                except Exception as cb_exc:  # noqa: BLE001
                    logger.warning("cloud_fallback_cb selhal: {}", cb_exc)

        # Stage: Příprava audia
        # - Lokální Whisper: extrakce do 16 kHz mono WAV přes ffmpeg
        # - Cloud Gemini: stačí původní soubor (Gemini umí mp3/m4a/wav přímo),
        #   přesto si zjistíme délku pro progress a estimáty
        extract_stage = stages[1]
        cumulative = _begin_stage(report, extract_stage, cumulative)
        audio_jobs: list[tuple[Path, str, float]] = []  # (path, label, duration_sec)
        for i, src in enumerate(audio_sources):
            _raise_if_cancelled(cancel_event)
            sub_fraction = (i + 1) / max(len(audio_sources), 1)
            duration = probe_duration_seconds(src.path) or 0.0
            if use_gemini:
                report(
                    f"Připravuji: {src.label}",
                    cumulative - extract_stage.weight + extract_stage.weight * sub_fraction,
                )
                audio_jobs.append((src.path, src.label, duration))
            else:
                report(
                    f"Extrahuji audio: {src.label}",
                    cumulative - extract_stage.weight + extract_stage.weight * sub_fraction,
                )
                wav = work_dir / f"audio_{i:02d}.wav"
                extract_to_wav(src.path, wav)
                audio_jobs.append((wav, src.label, duration))

        # Stage: Transkripce
        transcribe_stage = stages[2]
        cumulative = _begin_stage(report, transcribe_stage, cumulative)
        transcripts: list[Transcript] = []
        total_duration = sum(d for _, _, d in audio_jobs) or 1.0
        accumulated_duration = 0.0
        for audio_path, label, duration in audio_jobs:
            _raise_if_cancelled(cancel_event)
            stage_base = cumulative - transcribe_stage.weight
            file_weight = (duration or 1.0) / total_duration

            def inner_cb(
                fraction: float,
                _label=label,
                _accum=accumulated_duration,
                _weight=file_weight,
                _stage_base=stage_base,
                _total=total_duration,
                _stage_weight=transcribe_stage.weight,
            ) -> None:
                overall = _stage_base + _stage_weight * (_accum / _total + _weight * fraction)
                report(f"Přepis: {_label}", overall)

            def inner_text_cb(seconds: float, text: str, _label=label) -> None:
                if transcript_text_cb is not None:
                    try:
                        transcript_text_cb(seconds, _label, text)
                    except Exception as cb_exc:  # noqa: BLE001
                        logger.warning("transcript_text_cb selhal: {}", cb_exc)

            tr = _run_transcribe(
                audio_path=audio_path,
                label=label,
                job=job,
                use_gemini=use_gemini,
                gemini_api_key=gemini_api_key,
                progress_cb=inner_cb,
                text_cb=inner_text_cb,
                cloud_fallback_cb=cloud_fallback_cb,
                cancel_event=cancel_event,
                fallback_work_dir=work_dir,
            )
            transcripts.append(tr)
            # Po cloud přepisu rozsekáme segmenty na text_cb, ať se v UI něco zjeví
            if use_gemini and transcript_text_cb is not None and tr.segments:
                for seg in tr.segments:
                    try:
                        transcript_text_cb(seg.start, label, seg.text)
                    except Exception as cb_exc:  # noqa: BLE001
                        logger.warning("transcript_text_cb selhal: {}", cb_exc)
            accumulated_duration += duration

        # Auto-save raw přepisu (vždy — i v TRANSCRIBE_ONLY je užitečný)
        backup_txt = _save_transcript_backup(transcripts, Path(job.output_dir))
        if backup_txt is not None:
            logger.info("Záloha přepisu: {}", backup_txt)

        if transcribe_only:
            # Skip slide extract a AI; jdi rovnou na Word export jen s přepisem
            material = StudyMaterial(title=_make_transcribe_only_title(transcripts))
            slides: list[SlideText] = []
            word_stage = stages[3]
        else:
            # Stage: Slide extract
            slide_stage = stages[3]
            cumulative = _begin_stage(report, slide_stage, cumulative)
            slides = []
            for i, src in enumerate(presentation_sources):
                _raise_if_cancelled(cancel_event)
                sub_fraction = (i + 1) / max(len(presentation_sources), 1)
                report(
                    f"Čtu prezentaci: {src.label}",
                    cumulative - slide_stage.weight + slide_stage.weight * sub_fraction,
                )
                if src.path.suffix.lower() == ".pdf":
                    slides.append(extract_pdf_text(src.path, src.label))
                elif src.path.suffix.lower() == ".pptx":
                    slides.append(extract_pptx_text(src.path, src.label))

            # Stage: AI
            ai_stage = stages[4]
            cumulative = _begin_stage(report, ai_stage, cumulative)
            _raise_if_cancelled(cancel_event)
            report("Generuji body přes AI…", cumulative - ai_stage.weight * 0.5)
            material = generate_study_material(
                router=router,
                transcripts=transcripts,
                slides=slides,
                user_prompt=job.user_prompt,
            )
            word_stage = stages[5]

        # Stage: Word export
        cumulative = _begin_stage(report, word_stage, cumulative)
        _raise_if_cancelled(cancel_event)
        out_filename = suggested_output_filename(material)
        if transcribe_only:
            out_filename = "Prepis_" + out_filename.replace("Studijni-material_", "")
        out_path = Path(job.output_dir) / out_filename
        export_docx(
            output_path=out_path,
            material=material,
            transcripts=transcripts,
            slides=slides,
            sources=job.sources,
            user_prompt=job.user_prompt if not transcribe_only else None,
        )

        # Volitelný .md export pro AI agenta
        if job.create_md_export and transcripts:
            try:
                md_path = out_path.with_suffix(".md")
                export_markdown(
                    output_path=md_path,
                    transcripts=transcripts,
                    slides=slides,
                    user_prompt=job.user_prompt if not transcribe_only else None,
                    ai_service=job.user_ai_service,
                    whisper_model=job.whisper_model,
                )
                logger.info("Vyrobil jsem také .md prompt pro AI: {}", md_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning(".md export selhal (ne-fatal): {}", exc)

        report("Hotovo", 1.0)
        return PipelineResult(output_path=out_path, material=material, transcripts=transcripts, slides=slides)

    finally:
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except OSError:
            logger.warning("Nepodařilo se smazat workspace {}", work_dir)


def _make_transcribe_only_title(transcripts: list[Transcript]) -> str:
    if not transcripts:
        return "Přepis"
    if len(transcripts) == 1:
        return f"Přepis: {transcripts[0].source_label}"
    return f"Přepis z {len(transcripts)} nahrávek"


def _run_transcribe(
    *,
    audio_path: Path,
    label: str,
    job: JobConfig,
    use_gemini: bool,
    gemini_api_key: str | None,
    progress_cb: Callable[[float], None],
    text_cb: Callable[[float, str], None],
    cloud_fallback_cb: Callable[[str], None] | None,
    cancel_event: threading.Event | None,
    fallback_work_dir: Path | None = None,
) -> Transcript:
    """Přepis jednoho souboru. Cloud Gemini s fallback na lokální Whisper.

    Když Gemini selže kvůli síti, kvótě nebo authu, **automaticky** spadneme
    na lokální Whisper — uživatel místo erroru dostane výsledek (pomalejší,
    ale jistý). Důvod zaroveň propagujeme do GUI přes `cloud_fallback_cb`,
    aby uživatel viděl tray notifikaci (např. "Vyčerpaná denní kvóta…").
    """
    if use_gemini and gemini_api_key:
        try:
            return transcribe_audio_via_gemini(
                audio_path,
                source_label=label,
                api_key=gemini_api_key,
                language=job.language,
                progress_cb=progress_cb,
                cancel_event=cancel_event,
            )
        except TranscribeGeminiCancelled:
            # Cancel je explicitní volba uživatele, ne fallback
            raise TranscribeCancelled(f"Cloud přepis zrušen ({label})") from None
        except Exception as exc:  # noqa: BLE001
            reason = _humanize_cloud_error(exc)
            logger.warning(
                "Cloud Gemini přepis selhal ({}: {}) — zkouším lokální Whisper",
                type(exc).__name__,
                exc,
            )
            if cloud_fallback_cb is not None:
                try:
                    cloud_fallback_cb(reason)
                except Exception as cb_exc:  # noqa: BLE001
                    logger.warning("cloud_fallback_cb selhal: {}", cb_exc)
            # Pokračujeme dolů — fallback na lokální
            # Lokální Whisper potřebuje 16 kHz mono WAV; pokud `audio_path`
            # je originál (mp3 atd.), musíme extrahovat teď.
            # Píšeme do workspace dir, ne do user directory (collision + read-only risk).
            if audio_path.suffix.lower() != ".wav":
                target_dir = fallback_work_dir or audio_path.parent
                wav_fallback = target_dir / f"{audio_path.stem}_fallback.wav"
                try:
                    extract_to_wav(audio_path, wav_fallback)
                    audio_path = wav_fallback
                except Exception as wav_exc:  # noqa: BLE001
                    logger.exception("Fallback WAV extract selhal pro {}", audio_path)
                    raise PipelineError(
                        f"Cloud přepis selhal a převod na WAV pro lokální Whisper také: {wav_exc}. "
                        f"Původní cloud chyba: {exc}"
                    ) from wav_exc

    try:
        return transcribe_audio(
            audio_path,
            source_label=label,
            model_size=job.whisper_model,
            language=job.language,
            progress_cb=progress_cb,
            text_cb=text_cb,
            cancel_event=cancel_event,
        )
    except TranscribeCancelled:
        raise


def _humanize_cloud_error(exc: BaseException) -> str:
    """Krátká česká hláška pro tray notifikaci, když Gemini Audio selže."""
    from app.core.ai.base import AIAuthError, AINetworkError, AIRateLimitError

    if isinstance(exc, AIRateLimitError):
        return "Gemini Free hlásí vyčerpanou kvótu (limit dotazů). Zkus to později."
    if isinstance(exc, AINetworkError):
        return "Není připojení k internetu nebo Google neodpovídá."
    if isinstance(exc, AIAuthError):
        return "Neplatný Gemini API klíč — zkontroluj ho v Nastavení."
    return f"Cloud přepis selhal: {exc}"


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
    transcribe_only: bool = False,
    transcribe_backend: str = "local_whisper",
) -> tuple[float, float]:
    """Odhad celkového času pipeline. Vrací (low, high) v sekundách.

    Použito pro pre-start dialog typu "počítej s 60-90 min".
    """
    from app.core.transcribe import estimate_transcribe_seconds
    from app.core.transcribe_gemini import estimate_gemini_transcribe_seconds

    total_audio = sum(source_durations_sec)
    if transcribe_backend == "cloud_gemini":
        base = estimate_gemini_transcribe_seconds(total_audio)
        transcribe_low = base * 0.7
        transcribe_high = base * 2.0  # cloud má vyšší varianci (síť, kvóty)
    else:
        transcribe_low = estimate_transcribe_seconds(total_audio, whisper_model) * 0.7
        transcribe_high = estimate_transcribe_seconds(total_audio, whisper_model) * 1.3

    if transcribe_only:
        ai_seconds = 0.0
    else:
        ai_seconds = 30.0 if has_ai else 0.0
        if total_audio > 1800:  # > 30 min → map-reduce, víc dotazů
            ai_seconds = 60.0

    overhead = 10.0 if transcribe_only else 15.0  # bez slide extract
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
