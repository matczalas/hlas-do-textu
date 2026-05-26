"""Stahování audia z YouTube (a desítek dalších služeb) přes yt-dlp.

Vrátí lokální `.m4a` / `.mp3` v TEMP_DIR a `SourceFile` se sensible labelem.
Pak ho `pipeline.run_pipeline` zpracuje úplně stejně jako jakýkoliv lokální soubor.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from app.config import TEMP_DIR, ensure_dirs
from app.core.models import SourceFile, SourceKind

# Krátký regex jen na rychlou plausibility kontrolu — skutečnou validaci
# nechává yt-dlp na sobě (umí YouTube, Vimeo, SoundCloud, Loom, atd.).
_URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)


class YouTubeFetchError(RuntimeError):
    """Stahování selhalo (network, neexistující video, geo-block, atd.)."""


def is_supported_url(text: str) -> bool:
    return bool(_URL_RE.match(text.strip()))


def _sanitize_filename(s: str, max_len: int = 80) -> str:
    """Odstraní znaky, které vadí na Windows/macOS file systému."""
    s = re.sub(r'[<>:"/\\|?*]', "", s)
    s = s.strip().rstrip(".")
    return s[:max_len] if len(s) > max_len else s


def fetch_audio(
    url: str,
    *,
    progress_cb: Callable[[float, str], None] | None = None,
) -> SourceFile:
    """Stáhne audio stopu URL do TEMP_DIR. Vrací `SourceFile` připravený pro pipeline.

    `progress_cb(fraction_0_1, status_text)` — volá se jak yt-dlp parsuje progress
    z TUI výstupu. Není to perfektní granularita, ale pro UI bar stačí.

    Raises:
        YouTubeFetchError pro síťové/geo/neexistující chyby.
    """
    if not is_supported_url(url):
        raise YouTubeFetchError(f"Neplatná URL: {url}")

    try:
        import yt_dlp
    except ImportError as exc:
        raise YouTubeFetchError(
            "yt-dlp není nainstalován. Spusť `pip install yt-dlp`."
        ) from exc

    ensure_dirs()
    out_dir = TEMP_DIR / "youtube"
    out_dir.mkdir(parents=True, exist_ok=True)

    # yt-dlp progress hook
    def _hook(d: dict) -> None:
        if progress_cb is None:
            return
        status = d.get("status", "")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                progress_cb(min(downloaded / total, 0.95), "Stahuji…")
        elif status == "finished":
            progress_cb(0.97, "Stažení dokončeno, převádím…")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(out_dir / "%(title)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [_hook],
        # Neukládáme thumbnail, popis, subtitly — chceme jen audio
        "writeinfojson": False,
        "writethumbnail": False,
        "writedescription": False,
    }

    logger.info("yt-dlp: stahuji {}", url)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        raise YouTubeFetchError(f"yt-dlp selhal: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise YouTubeFetchError(f"Nečekaná chyba při stahování: {exc}") from exc

    if not isinstance(info, dict):
        raise YouTubeFetchError("yt-dlp nevrátil info dict")

    # Spočítáme reálnou cestu — yt-dlp dělá různé post-processing
    raw_path = info.get("requested_downloads", [{}])[0].get("filepath") or info.get("filepath")
    if not raw_path:
        # Fallback: hledat podle title
        title = info.get("title", "video")
        candidates = list(out_dir.glob(f"{_sanitize_filename(title)}.*"))
        if not candidates:
            raise YouTubeFetchError(
                f"yt-dlp neoznámil cestu k souboru a nic se nenašlo v {out_dir}"
            )
        raw_path = candidates[0]

    target = Path(raw_path)
    if not target.is_file():
        raise YouTubeFetchError(f"Stažený soubor nenalezen: {target}")

    title = info.get("title") or target.stem
    label = _sanitize_filename(title)
    logger.info(
        "yt-dlp: hotovo — {} ({:.1f} MB, {} s)",
        target.name,
        target.stat().st_size / 1024 / 1024,
        info.get("duration", 0),
    )

    if progress_cb is not None:
        progress_cb(1.0, "Hotovo")

    return SourceFile(path=target, kind=SourceKind.AUDIO_VIDEO, label=label)
