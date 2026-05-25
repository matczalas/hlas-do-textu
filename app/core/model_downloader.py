"""Stahování Whisper modelů z Hugging Face — s real-time progressem.

Místo `huggingface_hub.snapshot_download()` (která vrátí až po dokončení,
bez fine-grained progressu) stahujeme přímo přes `httpx.stream` a hlásíme
byte-level progress callback do UI.

Soubory v Systran/faster-whisper-* repu:
    config.json, model.bin (~770 MB pro medium), tokenizer.json, vocabulary.txt
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
from loguru import logger

from app.config import MODELS_DIR

HF_REPO_MAP: dict[str, str] = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
}

# Soubory potřebné pro faster-whisper run.
_REQUIRED_FILES: tuple[str, ...] = (
    "config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.txt",
)

_HF_BASE: str = "https://huggingface.co"


def _target_dir(model_name: str) -> Path:
    return MODELS_DIR / f"faster-whisper-{model_name}"


def model_is_cached(model_name: str) -> bool:
    """Heuristika: existuje model.bin v target_dir."""
    target = _target_dir(model_name)
    if not target.is_dir():
        return False
    return (target / "model.bin").is_file()


def download_model(
    model_name: str,
    *,
    progress_cb: Callable[[str, float], None] | None = None,
) -> Path:
    """Stáhne všechny potřebné soubory modelu z Hugging Face.

    `progress_cb(status_text, fraction)` — volá se průběžně.
    `fraction` je celkový postup 0.0–1.0 přes všechny soubory.
    """
    if model_name not in HF_REPO_MAP:
        raise ValueError(f"Neznámý model: {model_name}. Volby: {list(HF_REPO_MAP)}")

    target = _target_dir(model_name)
    target.mkdir(parents=True, exist_ok=True)

    if model_is_cached(model_name):
        logger.info("Model '{}' už je nacachovaný v {}", model_name, target)
        if progress_cb:
            progress_cb(f"Model {model_name} už je stažený", 1.0)
        return target

    repo = HF_REPO_MAP[model_name]

    # 1) Zjisti velikost každého souboru (HEAD request) pro výpočet váhy
    if progress_cb:
        progress_cb(f"Připravuji stahování modelu {model_name}…", 0.0)

    file_sizes: dict[str, int] = {}
    for fname in _REQUIRED_FILES:
        size = _head_size(repo, fname)
        file_sizes[fname] = size
        logger.info("HEAD {}: {} bytes", fname, size)

    total_bytes = sum(file_sizes.values())
    if total_bytes == 0:
        # Pokud HEAD selhal, downloadneme bez progress baru, jen status messages
        logger.warning("HEAD requesty selhaly — stahuji bez progress baru")
        total_bytes = 1

    # 2) Stáhni každý soubor s progressem
    downloaded_total = 0
    for fname in _REQUIRED_FILES:
        size = file_sizes.get(fname, 0)
        dest = target / fname

        if dest.is_file() and size > 0 and dest.stat().st_size == size:
            logger.info("{} už existuje a má správnou velikost, přeskočím", fname)
            downloaded_total += size
            if progress_cb and total_bytes > 0:
                progress_cb(
                    f"Mám {fname} v cache", min(downloaded_total / total_bytes, 1.0)
                )
            continue

        url = f"{_HF_BASE}/{repo}/resolve/main/{fname}"
        size_mb = size / 1024 / 1024 if size > 0 else 0
        nice_status = (
            f"Stahuji {fname} ({size_mb:.0f} MB)…"
            if size_mb >= 1
            else f"Stahuji {fname}…"
        )
        logger.info(nice_status)
        if progress_cb:
            progress_cb(
                nice_status, min(downloaded_total / total_bytes, 1.0) if total_bytes else 0.0
            )

        _fs = file_sizes.get(fname, 0)

        def _on_chunk(
            bytes_now: int,
            _f: str = fname,
            _base: int = downloaded_total,
            _file_size: int = _fs,
            _total: int = total_bytes,
        ) -> None:
            _emit_chunk_progress(progress_cb, _f, _base, bytes_now, _file_size, _total)

        _download_file_streaming(url=url, dest=dest, on_chunk=_on_chunk)
        downloaded_total += size if size > 0 else dest.stat().st_size
        logger.info("✓ {} stažen ({:.1f} MB)", fname, dest.stat().st_size / 1024 / 1024)

    if progress_cb:
        progress_cb(f"Model {model_name} připraven", 1.0)
    logger.info("Model '{}' kompletní v {}", model_name, target)
    return target


def _head_size(repo: str, fname: str) -> int:
    """HEAD request → Content-Length nebo 0 pokud selže."""
    url = f"{_HF_BASE}/{repo}/resolve/main/{fname}"
    try:
        with httpx.Client(follow_redirects=True, timeout=15.0) as client:
            response = client.head(url)
            if response.status_code >= 400:
                return 0
            return int(response.headers.get("Content-Length", 0))
    except (httpx.RequestError, ValueError):
        return 0


def _download_file_streaming(
    *,
    url: str,
    dest: Path,
    on_chunk: Callable[[int], None],
) -> None:
    """Stáhne URL do dest po blocích, volá on_chunk(downloaded_in_file) po každém."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_suffix(dest.suffix + ".part")

    with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as response:
        response.raise_for_status()
        downloaded = 0
        last_reported = 0
        with temp.open("wb") as f:
            for chunk in response.iter_bytes(chunk_size=256 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                # Hlásit progress max 5× za sekundu (každých 256 KB je dost často)
                if downloaded - last_reported >= 1024 * 1024:  # 1 MB
                    try:
                        on_chunk(downloaded)
                    except Exception:  # noqa: BLE001
                        pass
                    last_reported = downloaded
        # Final report
        try:
            on_chunk(downloaded)
        except Exception:  # noqa: BLE001
            pass

    temp.replace(dest)


def _emit_chunk_progress(
    cb: Callable[[str, float], None] | None,
    fname: str,
    cumulative_before: int,
    bytes_in_file: int,
    file_size: int,
    total_size: int,
) -> None:
    if cb is None:
        return
    overall_done = cumulative_before + bytes_in_file
    if total_size > 0:
        fraction = min(overall_done / total_size, 0.999)
    else:
        fraction = -1.0
    mb_now = bytes_in_file / 1024 / 1024
    if file_size > 0:
        mb_total = file_size / 1024 / 1024
        status = f"Stahuji {fname}: {mb_now:.0f} / {mb_total:.0f} MB"
    else:
        status = f"Stahuji {fname}: {mb_now:.0f} MB"
    cb(status, fraction)
