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
) -> Transcript:
    """Přepíše `wav_path` přes faster-whisper.

    Parametry:
        wav_path: 16 kHz mono WAV (viz `audio_extract.extract_to_wav`)
        source_label: editovatelný štítek od uživatele (např. "Část 1: Úvod")
        model_size: small/medium/large-v3
        language: ISO kód ("cs"); pokud None → auto-detect
        progress_cb: callback(0.0–1.0) volaný po každém segmentu
        cancel_event: pokud nastaven, transkripce skončí TranscribeCancelled

    Faster-whisper se importuje líně — heavy dependency, GUI startup nesmí čekat.
    """
    from faster_whisper import WhisperModel  # lazy import

    from app.core.model_downloader import _target_dir, model_is_cached

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
        "Spouštím přepis: {} (jazyk={}, threads={})",
        wav_path.name, language, cpu_threads,
    )
    # beam_size=1 + condition_on_previous_text=False: na CPU 5-8x rychlejší
    # než faster-whisper defaulty. Trade-off: WER nahoru o 1-3 % na CS, což
    # je pro studijní body neviditelné (AI to dál parafrázuje).
    try:
        segments_iter, info = model.transcribe(
            str(wav_path),
            language=language,
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
            word_timestamps=False,
        )

        total = info.duration if info.duration else 1.0
        segments: list[TranscriptSegment] = []
        text_parts: list[str] = []

        for seg in segments_iter:
            if cancel_event is not None and cancel_event.is_set():
                logger.warning("Přepis zrušen v {:.1f}s", seg.start)
                raise TranscribeCancelled(f"Přepis zrušen uživatelem ({wav_path.name})")

            clean = seg.text.strip()
            segments.append(TranscriptSegment(start=seg.start, end=seg.end, text=clean))
            text_parts.append(clean)

            if progress_cb is not None and total > 0:
                progress_cb(min(seg.end / total, 1.0))
            if text_cb is not None and clean:
                text_cb(seg.start, clean)

        full_text = " ".join(text_parts).strip()
        logger.info(
            "Přepis hotov: {} segmentů, {:.0f}s, {} znaků",
            len(segments),
            total,
            len(full_text),
        )

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
