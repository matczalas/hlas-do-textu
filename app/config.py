"""Centrální místo pro cesty, konstanty a runtime hodnoty.

Nepouštět zde imports z PySide6 nebo těžkých knihoven — modul musí jít načíst kdekoliv
(GUI vlákno, worker, CLI smoke test).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app import __app_name__

# ---------------------------------------------------------------------------
# Platform-specific user data paths
# ---------------------------------------------------------------------------


def _user_data_dir() -> Path:
    """Per-user, per-app writable directory pro modely, cache, settings, logy."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:  # Linux a podobné
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / __app_name__


def _user_config_dir() -> Path:
    if sys.platform == "win32":
        return _user_data_dir()  # na Win sjednocujeme s daty
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / __app_name__
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / __app_name__


USER_DATA_DIR: Path = _user_data_dir()
USER_CONFIG_DIR: Path = _user_config_dir()
MODELS_DIR: Path = USER_DATA_DIR / "models"
TEMP_DIR: Path = USER_DATA_DIR / "tmp"
LOGS_DIR: Path = USER_DATA_DIR / "logs"

CONFIG_FILE: Path = USER_CONFIG_DIR / "config.json"

DEFAULT_OUTPUT_DIR: Path = Path.home() / "Documents" / __app_name__


def ensure_dirs() -> None:
    """Volat při startu aplikace. Idempotentní."""
    for d in (USER_DATA_DIR, USER_CONFIG_DIR, MODELS_DIR, TEMP_DIR, LOGS_DIR, DEFAULT_OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Vendored ffmpeg (na Windows v PyInstaller bundlu; jinak fallback na PATH)
# ---------------------------------------------------------------------------


def ffmpeg_path() -> str:
    """Vrátí cestu k ffmpeg binárce.

    V PyInstaller bundlu hledá ve `vendor/ffmpeg/<platform>/ffmpeg(.exe)`.
    Mimo bundle (dev na macOS/Linux) spadne zpět na `ffmpeg` z PATH.
    """
    bundle_dir: Path | None = None
    if getattr(sys, "frozen", False):
        bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))

    candidates: list[Path] = []
    if bundle_dir is not None:
        if sys.platform == "win32":
            candidates.append(bundle_dir / "vendor" / "ffmpeg" / "win64" / "ffmpeg.exe")
        elif sys.platform == "darwin":
            candidates.append(bundle_dir / "vendor" / "ffmpeg" / "macos" / "ffmpeg")
        else:
            candidates.append(bundle_dir / "vendor" / "ffmpeg" / "linux" / "ffmpeg")

    for c in candidates:
        if c.is_file():
            return str(c)

    # Fallback na systémový ffmpeg
    return "ffmpeg"


# ---------------------------------------------------------------------------
# Whisper / AI defaults
# ---------------------------------------------------------------------------

DEFAULT_WHISPER_MODEL: str = "medium"  # akceptováno uživatelem; kvalita češtiny
WHISPER_MODEL_CHOICES: tuple[str, ...] = ("small", "medium", "large-v3")
DEFAULT_LANGUAGE: str = "cs"

DEFAULT_GEMINI_MODEL: str = "gemini-flash-latest"
DEFAULT_OLLAMA_MODEL: str = "llama3.2:3b"
DEFAULT_OLLAMA_BASE_URL: str = "http://localhost:11434"

# Threshold pro map-reduce strategii (tokenů transkriptu)
MAP_REDUCE_THRESHOLD_TOKENS: int = 8000
# Velikost chunku v map fázi
MAP_CHUNK_TOKENS: int = 3000
# Max paralelních requestů na Gemini (rate limit 15 RPM pro free tier)
MAX_PARALLEL_AI_REQUESTS: int = 4

# Podporované formáty pro import
AUDIO_VIDEO_EXTENSIONS: tuple[str, ...] = (".mp4", ".mov", ".mkv", ".avi", ".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm")
PRESENTATION_EXTENSIONS: tuple[str, ...] = (".pdf", ".pptx")

# Minimum volného místa pro běh pipeline (bytes)
MIN_FREE_DISK_BYTES: int = 2 * 1024 * 1024 * 1024  # 2 GB

# ---------------------------------------------------------------------------
# Externí odkazy (otvírané v default browseru přes QDesktopServices)
# ---------------------------------------------------------------------------

GEMINI_API_KEY_URL: str = "https://aistudio.google.com/api-keys"
OLLAMA_DOWNLOAD_URL: str = "https://ollama.com/download/windows"

# ---------------------------------------------------------------------------
# Auto-updater — GitHub Releases
# ---------------------------------------------------------------------------

GITHUB_OWNER: str = "matczalas"
GITHUB_REPO: str = "hlas-do-textu"

# Interval mezi tichými kontrolami aktualizace (sekundy). 24h = 86400.
UPDATE_CHECK_INTERVAL_SEC: int = 86_400

# Klíč v settings.json — kdy jsme naposled kontrolovali
UPDATE_LAST_CHECK_KEY: str = "update_last_check_iso"
