"""FFmpeg wrapper pro extrakci 16 kHz mono WAV z libovolného audio/video souboru.

Vzor: /Users/macbook/.claude/skills/video-use/helpers/transcribe.py:39-45
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from loguru import logger

from app.config import ffmpeg_path


class AudioExtractError(RuntimeError):
    """FFmpeg selhal nebo vstupní soubor nelze přečíst."""


def _ffprobe_path() -> str:
    """Odvodí cestu k ffprobe z ffmpeg cesty.

    Naivní `str.replace("ffmpeg", "ffprobe")` by rozbil cesty, kde je "ffmpeg"
    i v názvu adresáře (náš vendor bundle: `.../vendor/ffmpeg/macos/ffmpeg`
    → `.../vendor/ffprobe/macos/ffprobe`, což neexistuje). Nahrazujeme jen
    název souboru přes Path.with_name.
    """
    ffmpeg = ffmpeg_path()
    if ffmpeg == "ffmpeg":  # systémový z PATH
        return "ffprobe"
    p = Path(ffmpeg)
    new_name = p.name.replace("ffmpeg", "ffprobe")
    return str(p.with_name(new_name))


def _subprocess_kwargs() -> dict:
    """Společné kwargs — na Windows skrýt black flash okno cmd.exe.

    FFmpeg / ffprobe jsou console aplikace. Bez CREATE_NO_WINDOW by každý jejich
    běh blikl černým oknem (rušivé když pipeline volá ffmpeg pro každý audio soubor).
    """
    kwargs: dict = {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace"}
    if sys.platform == "win32":
        # 0x08000000 = CREATE_NO_WINDOW — process nemá konzoli
        kwargs["creationflags"] = 0x08000000
    return kwargs


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

    try:
        # timeout 1 h — corrupt/zaseknutý vstup jinak GUI worker zamrzne navždy.
        # Reálná hodinová přednáška se extrahuje za sekundy, takže 3600 s je
        # bohatá rezerva i pro velmi dlouhé soubory.
        result = subprocess.run(cmd, timeout=3600, **_subprocess_kwargs())
    except FileNotFoundError as exc:
        # ffmpeg binárka chybí (dev bez bundlu / poškozená instalace).
        # Bez tohoto by propadl raw FileNotFoundError, ale pipeline/UI
        # očekává AudioExtractError s čitelnou hláškou.
        raise AudioExtractError(
            "FFmpeg nebyl nalezen. Přeinstaluj aplikaci, nebo (dev) doinstaluj "
            "ffmpeg do PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioExtractError(
            f"Zpracování {src.name} trvalo příliš dlouho (přes hodinu) — "
            "soubor může být poškozený."
        ) from exc

    if result.returncode != 0:
        logger.error("FFmpeg selhal pro {}: {}", src, result.stderr.strip()[-500:])
        raise AudioExtractError(f"FFmpeg selhal pro {src.name}: {result.stderr.strip()[-200:]}")

    if not dest.is_file() or dest.stat().st_size == 0:
        raise AudioExtractError(f"FFmpeg neprodukoval výstup pro {src.name}")

    logger.info("Extrahováno audio: {} → {} ({:.1f} KB)", src.name, dest.name, dest.stat().st_size / 1024)
    return dest


def trim_wav(src: Path, dest: Path, start_sec: float) -> Path:
    """Ořízne WAV od `start_sec` do konce — pro resume přepisu.

    Použije přesný (sample-accurate) seek: `-ss` AŽ ZA `-i` zaručuje, že ffmpeg
    dekóduje od začátku a ořízne přesně, ne na nejbližší keyframe. U PCM WAV
    je to rychlé (žádné re-enkódování, jen kopie samplů).

    Vrací `dest`. Vyhodí AudioExtractError při selhání.
    """
    src = Path(src)
    dest = Path(dest)
    if not src.is_file():
        raise AudioExtractError(f"Soubor pro ořez nenalezen: {src}")
    dest.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg_path(),
        "-y",
        "-i", str(src),
        "-ss", f"{start_sec:.3f}",   # output seeking = přesný
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(dest),
    ]
    logger.debug("FFmpeg trim: {}", " ".join(cmd))
    try:
        result = subprocess.run(cmd, timeout=600, **_subprocess_kwargs())
    except FileNotFoundError as exc:
        raise AudioExtractError("FFmpeg nebyl nalezen (trim).") from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioExtractError(f"Ořez {src.name} trval příliš dlouho.") from exc

    if result.returncode != 0:
        raise AudioExtractError(
            f"FFmpeg ořez selhal pro {src.name}: {result.stderr.strip()[-200:]}"
        )
    if not dest.is_file() or dest.stat().st_size == 0:
        raise AudioExtractError(f"FFmpeg ořez neprodukoval výstup pro {src.name}")
    return dest


def probe_duration_seconds(src: Path) -> float | None:
    """Vrátí délku média v sekundách přes ffprobe (best-effort).

    Pokud ffprobe selže, vrátí None — volající si poradí (např. odhad z velikosti).
    """
    ffprobe = _ffprobe_path()
    cmd = [
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(src),
    ]
    try:
        result = subprocess.run(cmd, timeout=15, **_subprocess_kwargs())
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return float(value) if value else None
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return None
