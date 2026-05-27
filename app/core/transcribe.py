"""Wrapper nad faster-whisper.

Vzor: /Users/macbook/Safe4future/claude_video/studio/pipeline/captions/viral.py:53-120
— ale BEZ word_timestamps (pro studijní body nepotřebujeme).
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from app.config import DEFAULT_LANGUAGE, DEFAULT_WHISPER_MODEL, MODELS_DIR
from app.core.models import Transcript, TranscriptSegment


class TranscribeCancelled(RuntimeError):
    """Vyhozeno, když cancel_event proběhne uprostřed transkripce."""


def transcribe_audio(
    wav_path: Path,
    *,
    source_label: str,
    model_size: str = DEFAULT_WHISPER_MODEL,
    language: str = DEFAULT_LANGUAGE,
    progress_cb: Callable[[float], None] | None = None,
    text_cb: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
    checkpoint_audio: Path | None = None,
) -> Transcript:
    """Přepíše `wav_path` přes faster-whisper.

    Parametry:
        wav_path: 16 kHz mono WAV (viz `audio_extract.extract_to_wav`)
        source_label: editovatelný štítek od uživatele (např. "Část 1: Úvod")
        model_size: small/medium/large-v3
        language: ISO kód ("cs"); pokud None → auto-detect
        progress_cb: callback(0.0–1.0) volaný po každém segmentu
        cancel_event: pokud nastaven, transkripce skončí TranscribeCancelled
        checkpoint_audio: originální audio soubor (pro klíč checkpointu). Když
            je předán a existuje použitelný checkpoint, přepis NAVÁŽE od místa
            přerušení (ořeže audio, posune časy, spojí s hotovými segmenty).
            None = bez checkpointování (staré chování).

    Faster-whisper se importuje líně — heavy dependency, GUI startup nesmí čekat.
    """
    from faster_whisper import WhisperModel  # lazy import

    from app.core import checkpoint as ckpt
    from app.core.model_downloader import _target_dir, model_is_cached

    # ----- Resume příprava (čistě aditivní — chyba = plný přepis od nuly) -----
    prior_segments: list[TranscriptSegment] = []
    time_offset = 0.0
    actual_wav = wav_path
    if checkpoint_audio is not None:
        try:
            cp = ckpt.load(checkpoint_audio, model_size, language)
            if cp is not None and cp.is_useful():
                from app.core.audio_extract import trim_wav

                trimmed = wav_path.parent / f"{wav_path.stem}_resume.wav"
                trim_wav(wav_path, trimmed, cp.completed_until_sec)
                actual_wav = trimmed
                time_offset = cp.completed_until_sec
                prior_segments = [
                    TranscriptSegment(start=s["start"], end=s["end"], text=s["text"])
                    for s in cp.segments
                ]
                logger.info(
                    "Resume: navazuji od {:.0f}s ({} hotových segmentů)",
                    time_offset, len(prior_segments),
                )
        except Exception as exc:  # noqa: BLE001 — resume nesmí shodit přepis
            logger.warning("Resume selhal ({}), přepisuji od začátku", exc)
            try:
                ckpt.delete(checkpoint_audio, model_size, language)
            except Exception:  # noqa: BLE001
                pass
            prior_segments = []
            time_offset = 0.0
            actual_wav = wav_path

    # KRITICKÁ OPTIMALIZACE: pokud model máme lokálně, předáme přímou cestu.
    # Jinak WhisperModel(name, download_root=...) volá huggingface_hub.snapshot_download
    # který POKAŽDÉ kontroluje HF Hub (i s cache hit). Bez HF tokenu = rate-limited,
    # čeká minuty místo sekund. S lokální cestou = 1.7s místo 140s na startup.
    if model_is_cached(model_size):
        model_arg = str(_target_dir(model_size))
        logger.info("Načítám Whisper z lokální cache: {}", model_arg)
    else:
        model_arg = model_size
        logger.info("Whisper model '{}' v cache není, stáhne se z HF", model_size)

    # cpu_threads: faster-whisper default je min(4, cpu_count). Na M-series
    # a moderním Intelu máme 8-10 jader; využijeme všechny.
    cpu_threads = os.cpu_count() or 4
    model = WhisperModel(
        model_arg,
        device="cpu",
        compute_type="int8",
        download_root=str(MODELS_DIR),
        cpu_threads=cpu_threads,
    )

    logger.info(
        "Spouštím přepis: {} (jazyk={}, threads={}, offset={:.0f}s)",
        wav_path.name, language, cpu_threads, time_offset,
    )
    # beam_size=1 + condition_on_previous_text=False: na CPU 5-8x rychlejší
    # než faster-whisper defaulty. Trade-off: WER nahoru o 1-3 % na CS, což
    # je pro studijní body neviditelné (AI to dál parafrázuje).
    try:
        segments_iter, info = model.transcribe(
            str(actual_wav),
            language=language,
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
            word_timestamps=False,
        )

        # info.duration je délka PŘEPISOVANÉHO (případně oříznutého) audia.
        # Celková délka = offset (hotová část) + zbytek.
        rest_duration = info.duration if info.duration else 1.0
        total = time_offset + rest_duration

        # Začneme s hotovými segmenty z checkpointu (absolutní časy už mají)
        segments: list[TranscriptSegment] = list(prior_segments)
        text_parts: list[str] = [s.text for s in prior_segments]

        # Při resume pošleme do UI i hotové segmenty (živý feed by jinak začal
        # uprostřed)
        if text_cb is not None:
            for s in prior_segments:
                if s.text:
                    text_cb(s.start, s.text)

        last_ckpt_save = time_offset

        def _persist_checkpoint(until_sec: float) -> None:
            if checkpoint_audio is None:
                return
            ckpt.save(
                checkpoint_audio, model_size, language,
                [{"start": s.start, "end": s.end, "text": s.text} for s in segments],
                until_sec,
            )

        for seg in segments_iter:
            if cancel_event is not None and cancel_event.is_set():
                logger.warning("Přepis zrušen v {:.1f}s — ukládám checkpoint", seg.start + time_offset)
                # Uložit hotový postup, ať na něj jde navázat
                _persist_checkpoint(segments[-1].end if segments else time_offset)
                raise TranscribeCancelled(f"Přepis zrušen uživatelem ({wav_path.name})")

            # Posun časů o offset (při resume); bez resume je offset 0
            abs_start = seg.start + time_offset
            abs_end = seg.end + time_offset
            clean = seg.text.strip()
            segments.append(TranscriptSegment(start=abs_start, end=abs_end, text=clean))
            text_parts.append(clean)

            if progress_cb is not None and total > 0:
                progress_cb(min(abs_end / total, 1.0))
            if text_cb is not None and clean:
                text_cb(abs_start, clean)

            # Průběžné ukládání checkpointu každých ~30 s hotového audia
            if abs_end - last_ckpt_save >= 30.0:
                _persist_checkpoint(abs_end)
                last_ckpt_save = abs_end

        full_text = " ".join(text_parts).strip()
        logger.info(
            "Přepis hotov: {} segmentů, {:.0f}s, {} znaků",
            len(segments),
            total,
            len(full_text),
        )

        # Úspěch → checkpoint už není potřeba
        if checkpoint_audio is not None:
            ckpt.delete(checkpoint_audio, model_size, language)

        return Transcript(
            source_label=source_label,
            language=info.language,
            duration_sec=total,
            text=full_text,
            segments=segments,
        )
    finally:
        # faster-whisper (CTranslate2) drží stovky MB nativní paměti a nemá
        # close(). Bez explicitního uvolnění by RSS rostl s každým přepisem
        # v jedné GUI session. del + gc.collect() uvolní referenci hned.
        del model
        import gc

        gc.collect()


def estimate_transcribe_seconds(media_duration_sec: float, model_size: str = DEFAULT_WHISPER_MODEL) -> float:
    """Hrubý odhad pro UI hint. Hodnoty cca pro slušné desktop CPU bez GPU
    s beam_size=1 (greedy decode).

    Není to predikce, jen ballpark pro očekávání uživatele.
    """
    rtf = {
        "tiny": 0.05,
        "base": 0.10,
        "small": 0.20,
        "medium": 0.45,
        "large-v3": 0.80,
    }.get(model_size, 0.45)
    return media_duration_sec * rtf
