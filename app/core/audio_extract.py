"""FFmpeg wrapper pro extrakci 16 kHz mono WAV z libovolného audio/video souboru.

Vzor: /Users/macbook/.claude/skills/video-use/helpers/transcribe.py:39-45
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from loguru import logger

from app.config import ffmpeg_path


class AudioExtractError(RuntimeError):
    """FFmpeg selhal nebo vstupní soubor nelze přečíst."""


def extract_to_wav(src: Path, dest: Path) -> Path:
    """Převede `src` (audio/video) na 16 kHz mono WAV `dest`.

    Vrací cestu k `dest`. Vyhodí `AudioExtractError` při selhání.
    """
    src = Path(src)
    dest = Path(dest)
    if not src.is_file():
        raise AudioExtractError(f"Soubor nenalezen: {src}")

    dest.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg_path(),
        "-y",
        "-i", str(src),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(dest),
    ]
    logger.debug("FFmpeg: {}", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        logger.error("FFmpeg selhal pro {}: {}", src, result.stderr.strip()[-500:])
        raise AudioExtractError(f"FFmpeg selhal pro {src.name}: {result.stderr.strip()[-200:]}")

    if not dest.is_file() or dest.stat().st_size == 0:
        raise AudioExtractError(f"FFmpeg neprodukoval výstup pro {src.name}")

    logger.info("Extrahováno audio: {} → {} ({:.1f} KB)", src.name, dest.name, dest.stat().st_size / 1024)
    return dest


def probe_duration_seconds(src: Path) -> float | None:
    """Vrátí délku média v sekundách přes ffprobe (best-effort).

    Pokud ffprobe selže, vrátí None — volající si poradí (např. odhad z velikosti).
    """
    ffprobe = ffmpeg_path().replace("ffmpeg", "ffprobe")
    cmd = [
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(src),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return float(value) if value else None
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return None
