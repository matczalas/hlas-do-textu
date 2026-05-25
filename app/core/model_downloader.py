"""Lazy stažení Whisper modelu přes huggingface_hub.

Modely se cachují do `MODELS_DIR` (v USER_DATA_DIR), takže instalátor je nemusí vendorovat.
Repo mapping z https://huggingface.co/Systran (oficiální faster-whisper weights).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from loguru import logger

from app.config import MODELS_DIR

# Faster-whisper distribuce Systran (přímo CTranslate2 weighty — bez konverze)
HF_REPO_MAP: dict[str, str] = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
}


def model_is_cached(model_name: str) -> bool:
    """Heuristika: existuje aspoň jeden soubor `model.bin` v target_dir."""
    target = _target_dir(model_name)
    if not target.is_dir():
        return False
    return any(target.rglob("model.bin"))


def download_model(
    model_name: str,
    *,
    progress_cb: Callable[[str, float], None] | None = None,
) -> Path:
    """Stáhne model z Hugging Face. Vrací cestu k cache adresáři.

    `progress_cb(status_text, fraction_0_1)` — fraction může být -1.0 pro neznámý progres.
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

    from huggingface_hub import snapshot_download

    repo_id = HF_REPO_MAP[model_name]
    logger.info("Stahuji '{}' z {}", model_name, repo_id)
    if progress_cb:
        progress_cb(f"Stahuji model {model_name} z Hugging Face…", -1.0)

    snapshot_download(
        repo_id=repo_id,
        local_dir=str(target),
        local_dir_use_symlinks=False,
    )

    if progress_cb:
        progress_cb(f"Model {model_name} stažen", 1.0)
    logger.info("Model '{}' připraven v {}", model_name, target)
    return target


def _target_dir(model_name: str) -> Path:
    return MODELS_DIR / f"faster-whisper-{model_name}"
