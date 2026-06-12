"""User settings: Gemini API klíč v souboru 0600 (viz níže — proč ne Keychain),
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
    USER_CONFIG_DIR,
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
    # Posledních 10 vygenerovaných .docx — pro File → Naposledy vyrobené.
    recent_outputs: list[str] = field(default_factory=list)
    # Kalibrace rychlosti tohoto počítače pro přesnější odhad času.
    # = skutečné_RTF / tabulkové_RTF z posledních běhů (1.0 = přesně podle tabulky,
    # >1 = počítač je pomalejší, <1 = rychlejší). Aktualizuje se po každém přepisu.
    cpu_speed_factor: float = 1.0
    # Role aktivního uživatele — řídí accent (modrá/teal) a UI vrstvu (učitel = 3 akční karty).
    # "student" = výchozí (Safe4Future modrá), "teacher" = pedagogický nástroj (teal).
    app_role: str = "student"
    # Tmavý režim UI (paleta + accent přes role); pokud false, světlý.
    dark_mode: bool = False
    # Sledovaná složka — nové nahrávky v ní se zpracují automaticky
    # (šablona watch_template_key). Viz app/core/watch_folder.py.
    watch_enabled: bool = False
    watch_folder: str = ""
    watch_template_key: str = "student"


def load_settings() -> AppSettings:
    ensure_dirs()
    if CONFIG_FILE.is_file():
        try:
            with CONFIG_FILE.open(encoding="utf-8") as fh:
                data = json.load(fh)
            # config.json mohl být ručně upraven na ne-objekt ([], null, 123…) —
            # bez této kontroly by data.items() vyhodilo AttributeError → crash
            # při startu a dialog s defaulty by se nikdy nezobrazil.
            if not isinstance(data, dict):
                raise ValueError(f"config.json není objekt, ale {type(data).__name__}")
            # Tolerate extra/missing fields + coerce typy podle defaultů
            return _coerce_settings(data)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            logger.warning("Nevalidní config.json ({}), použiju defaulty", exc)
    return AppSettings()


def _coerce_settings(data: dict) -> AppSettings:
    """Z dictu vyrobí AppSettings — ignoruje neznámá pole a opravuje špatné typy.

    Bez type-coerce by `recent_outputs: "x"` (string místo listu) prošlo
    dataclass konstruktorem a spadlo až později jinde (např. `Path(p)` iterující
    znaky stringu). Každé pole zkontrolujeme proti typu defaultní hodnoty.
    """
    defaults = AppSettings()
    kwargs: dict = {}
    for f in AppSettings.__dataclass_fields__.values():
        if f.name not in data:
            continue
        value = data[f.name]
        default_value = getattr(defaults, f.name)
        # list pole musí být list; jinak ignorujeme (vezme se default)
        if isinstance(default_value, list):
            if isinstance(value, list):
                kwargs[f.name] = [str(x) for x in value]
            continue
        # bool/str/int/float — coerce na typ defaultu, jinak default
        expected_type = type(default_value)
        if isinstance(value, expected_type):
            kwargs[f.name] = value
        elif expected_type is bool and isinstance(value, int):
            kwargs[f.name] = bool(value)
        elif expected_type is float and isinstance(value, int | float):
            kwargs[f.name] = float(value)
        # jinak ponecháme default (kwargs neobsahuje → dataclass default)
    return AppSettings(**kwargs)


def save_settings(settings: AppSettings) -> None:
    ensure_dirs()
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(asdict(settings), fh, ensure_ascii=False, indent=2)
    tmp.replace(CONFIG_FILE)
    logger.debug("Settings uloženy: {}", CONFIG_FILE)


# ---------------------------------------------------------------------------
# Gemini API klíč — uložení v souboru (0600), ne v Keychainu
# ---------------------------------------------------------------------------
# Proč ne Keychain: nepodepsaná macOS aplikace dostane při KAŽDÉM čtení
# Keychainu dotaz na systémové heslo (po updatu se podpis mění → "Always Allow"
# nesedí). Ukládáme proto klíč do souboru s právy 0600 (čitelný jen vlastníkem)
# v USER_CONFIG_DIR. Keychain čteme už jen jednorázově kvůli migraci klíče
# z předchozích verzí. Výsledek navíc cachujeme v paměti (1 čtení za běh).
#
# Bezpečnost: Gemini Free klíč je nízkohodnotový a soubor je čitelný jen pro
# přihlášeného uživatele (0600) — stejný model, jaký už používá licence.

_GEMINI_FILE_NAME = ".gemini_key"


class _Unset:
    """Sentinel — rozliší 'cache ještě nenačtena' od 'načteno, ale klíč není'."""


_UNSET: _Unset = _Unset()
_gemini_cache: str | None | _Unset = _UNSET


def _gemini_file_path() -> Path:
    ensure_dirs()
    return USER_CONFIG_DIR / _GEMINI_FILE_NAME


def get_gemini_api_key() -> str | None:
    """Vrátí Gemini klíč. Pořadí: ENV → cache → soubor → (migrace z) Keychainu.

    Soubor i Keychain se čtou max jednou za běh (výsledek se cachuje). Jakmile
    soubor existuje (i prázdný = "uživatel klíč smazal"), Keychain se už nesahá
    — díky tomu se macOS neptá na systémové heslo.
    """
    env = os.environ.get("GEMINI_API_KEY", "").strip()
    if env:
        return env

    global _gemini_cache
    if not isinstance(_gemini_cache, _Unset):
        return _gemini_cache  # type: ignore[return-value]

    # 1) Soubor je autoritativní zdroj. Když existuje, Keychain ignorujeme.
    try:
        path = _gemini_file_path()
        if path.is_file():
            value = path.read_text(encoding="utf-8").strip()
            _gemini_cache = value or None
            return _gemini_cache  # type: ignore[return-value]
    except OSError as exc:
        logger.warning("Čtení Gemini klíče ze souboru selhalo: {}", exc)

    # 2) Soubor neexistuje → jednorázová migrace z Keychainu (staré instalace).
    #    Tohle je JEDINÉ místo, kde se Keychain ještě čte — po migraci už nikdy.
    try:
        import keyring

        value = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER)
        if value:
            value = value.strip()
            _write_gemini_file(value)  # zmigruj do souboru
            _gemini_cache = value
            return value
    except Exception as exc:  # noqa: BLE001 — keyring backend může selhat
        logger.warning("Keyring není dostupný: {}", exc)

    _gemini_cache = None
    return None


def set_gemini_api_key(key: str) -> None:
    """Uloží/smaže Gemini klíč do souboru (0600). Keychain se nepoužívá.

    Prázdný klíč zapíše prázdný soubor (tombstone) — tím se zabrání, aby se
    starý klíč z Keychainu při dalším čtení "vzkřísil" migrací.
    """
    global _gemini_cache
    key = (key or "").strip()
    try:
        _write_gemini_file(key)  # i prázdný = tombstone
        _gemini_cache = key or None
        logger.info("Gemini API klíč {}", "uložen" if key else "smazán")
    except OSError as exc:
        logger.error("Nepodařilo se uložit Gemini klíč: {}", exc)
        raise


def _write_gemini_file(value: str) -> None:
    """Zapíše hodnotu (i prázdnou) do souboru s právy 0600."""
    path = _gemini_file_path()
    path.write_text(value, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
