"""User settings: API klíče v keyring (Windows Credential Manager / macOS Keychain),
zbytek v JSON v USER_CONFIG_DIR.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from loguru import logger

from app import __app_name__
from app.config import (
    CONFIG_FILE,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_LANGUAGE,
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_WHISPER_MODEL,
    ensure_dirs,
)

_KEYRING_SERVICE = f"{__app_name__}.gemini"
_KEYRING_USER = "default"


@dataclass(slots=True)
class AppSettings:
    whisper_model: str = DEFAULT_WHISPER_MODEL
    language: str = DEFAULT_LANGUAGE
    gemini_model: str = DEFAULT_GEMINI_MODEL
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    output_dir: str = str(DEFAULT_OUTPUT_DIR)
    ai_consent_gemini: bool = False
    prefer_offline: bool = False
    first_run_done: bool = False
    last_used_sources_dir: str = field(default_factory=lambda: str(Path.home()))
    # Volitelná .md verze přepisu (prompt pro AI agenta jako ChatGPT/Claude)
    create_md_export: bool = False
    # Kterou AI student používá — určuje custom instrukce v .md exportu
    # "none" | "chatgpt" | "claude" | "gemini" | "other"
    user_ai_service: str = "none"
    # Backend pro speech-to-text:
    # "local_whisper" = faster-whisper na CPU (default, offline)
    # "cloud_gemini"  = Gemini Audio API (rychlejší, vyžaduje internet a souhlas)
    transcribe_backend: str = "local_whisper"


def load_settings() -> AppSettings:
    ensure_dirs()
    if CONFIG_FILE.is_file():
        try:
            with CONFIG_FILE.open(encoding="utf-8") as fh:
                data = json.load(fh)
            # Tolerate extra/missing fields
            known = {f.name for f in AppSettings.__dataclass_fields__.values()}
            data = {k: v for k, v in data.items() if k in known}
            return AppSettings(**data)
        except (OSError, ValueError) as exc:
            logger.warning("Nevalidní config.json ({}), použiju defaulty", exc)
    return AppSettings()


def save_settings(settings: AppSettings) -> None:
    ensure_dirs()
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(asdict(settings), fh, ensure_ascii=False, indent=2)
    tmp.replace(CONFIG_FILE)
    logger.debug("Settings uloženy: {}", CONFIG_FILE)


# ---------------------------------------------------------------------------
# API klíče přes keyring (s fallback na env var pro dev)
# ---------------------------------------------------------------------------


def get_gemini_api_key() -> str | None:
    """Vrátí klíč v pořadí: ENV → keyring. None pokud nikde."""
    env = os.environ.get("GEMINI_API_KEY", "").strip()
    if env:
        return env

    try:
        import keyring

        value = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER)
        if value:
            return value.strip()
    except Exception as exc:  # noqa: BLE001 — keyring backend může selhat
        logger.warning("Keyring není dostupný: {}", exc)

    return None


def set_gemini_api_key(key: str) -> None:
    key = (key or "").strip()
    try:
        import keyring

        if not key:
            try:
                keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USER)
            except keyring.errors.PasswordDeleteError:
                pass
            logger.info("Gemini API klíč smazán z keyring")
            return
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, key)
        logger.info("Gemini API klíč uložen do keyring")
    except Exception as exc:  # noqa: BLE001
        logger.error("Nepodařilo se uložit klíč do keyring: {}", exc)
        raise
