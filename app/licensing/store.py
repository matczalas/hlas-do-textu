"""Uložení license klíče v keyring (Windows Credential Manager / macOS Keychain).

Klíč se ukládá pod service 'HlasDoTextu.license'. Pokud keyring backend selže
(některé Win Server / Linux without dbus), použijeme fallback do souboru
v USER_CONFIG_DIR — ale i tam je validace přes HMAC, takže utajení secretu
v souboru nehraje roli (uložen je hotový validní klíč, ne secret).

Vedle samotného klíče ukládáme metadata aktivace (.license_meta.json):
- machine_fingerprint (16-hex char hash zařízení)
- activated_at (ISO timestamp)
- activation_count (kolikrát byla na tomhle PC aktivace volána)

Tato metadata jsou informativní (honor system per EULA — max 2 zařízení per klíč).
Sledování přes zařízení mezi PC by vyžadovalo server (out of scope MVP).
"""
from __future__ import annotations

import json
from datetime import datetime

from loguru import logger

from app import __app_name__
from app.config import USER_CONFIG_DIR, ensure_dirs
from app.licensing._machine import get_machine_display_name, get_machine_fingerprint
from app.licensing.keys import normalize_key, validate_key

_KEYRING_SERVICE = f"{__app_name__}.license"
_KEYRING_USER = "default"
_FALLBACK_FILE_NAME = ".license"
_META_FILE_NAME = ".license_meta.json"


def _fallback_path():
    ensure_dirs()
    return USER_CONFIG_DIR / _FALLBACK_FILE_NAME


def _meta_path():
    ensure_dirs()
    return USER_CONFIG_DIR / _META_FILE_NAME


def store_key(key: str) -> None:
    """Uloží klíč po validaci. Vyhodí ValueError pokud klíč neplatný.

    Po uložení klíče zaznamená aktivaci do .license_meta.json
    (machine fingerprint, datum, counter).
    """
    normalized = normalize_key(key)

    # Primárně keyring
    stored_via_keyring = False
    try:
        import keyring

        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, normalized)
        stored_via_keyring = True
        logger.info("Licenční klíč uložen do keyring")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Keyring nedostupný ({}), použiji fallback file", exc)

    # Fallback (taky vždycky, kdyby keyring přestal fungovat)
    try:
        path = _fallback_path()
        path.write_text(normalized, encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        logger.info("Licenční klíč zazálohován do {}", path)
    except Exception as exc:  # noqa: BLE001
        if not stored_via_keyring:
            raise RuntimeError(f"Nepodařilo se uložit licenční klíč: {exc}") from exc
        logger.warning("Fallback file uložit selhal: {}", exc)

    # Zaznamenat aktivaci do meta souboru
    try:
        _record_activation(normalized)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Záznam aktivace selhal (ne-fatal): {}", exc)


def _record_activation(key: str) -> None:
    """Uloží machine fingerprint + datum do .license_meta.json. Kumulativní counter."""
    meta = _read_meta()
    fingerprint = get_machine_fingerprint()
    display = get_machine_display_name()
    timestamp = datetime.now().isoformat(timespec="seconds")

    # Pokud meta už existuje pro stejný key, jen inkrementuj counter
    if meta.get("key_hash") == _hash_key(key):
        meta["activation_count"] = int(meta.get("activation_count", 0)) + 1
        meta["last_activated_at"] = timestamp
    else:
        meta = {
            "key_hash": _hash_key(key),  # NE klíč samotný — hash kvůli privacy
            "machine_fingerprint": fingerprint,
            "machine_display": display,
            "activated_at": timestamp,
            "last_activated_at": timestamp,
            "activation_count": 1,
        }

    _write_meta(meta)
    logger.info(
        "Aktivace zaznamenána: machine={}, count={}", fingerprint, meta["activation_count"]
    )


def _hash_key(key: str) -> str:
    """Krátký hash klíče (8 znaků) — nezachovává sám klíč v meta souboru."""
    import hashlib

    return hashlib.sha256(key.encode("ascii")).hexdigest()[:16]


def _read_meta() -> dict:
    path = _meta_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_meta(meta: dict) -> None:
    path = _meta_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def get_activation_info() -> dict | None:
    """Vrátí info o aktivaci pro UI ('Aktivováno X. Y. 2026 na zařízení ABCD')."""
    meta = _read_meta()
    if not meta:
        return None
    return {
        "machine_fingerprint": meta.get("machine_fingerprint", "?"),
        "machine_display": meta.get("machine_display", "?"),
        "activated_at": meta.get("activated_at"),
        "last_activated_at": meta.get("last_activated_at"),
        "activation_count": meta.get("activation_count", 0),
    }


def get_stored_key() -> str | None:
    """Vrátí uložený klíč, pokud existuje. Preferuje keyring."""
    try:
        import keyring

        value = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER)
        if value:
            return value.strip().upper()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Keyring nedostupný při čtení licence: {}", exc)

    # Fallback
    try:
        path = _fallback_path()
        if path.is_file():
            return path.read_text(encoding="utf-8").strip().upper()
    except OSError as exc:
        logger.warning("Fallback file čtení selhalo: {}", exc)

    return None


def is_activated() -> bool:
    """True jen pokud je uložený klíč a stále projde validací."""
    key = get_stored_key()
    if not key:
        return False
    return validate_key(key)


def clear_stored_key() -> None:
    """Smaže klíč ze všech úložišť — debug nástroj."""
    try:
        import keyring

        try:
            keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USER)
        except keyring.errors.PasswordDeleteError:
            pass
    except Exception:  # noqa: BLE001
        pass
    try:
        path = _fallback_path()
        if path.is_file():
            path.unlink()
    except OSError:
        pass
    try:
        meta = _meta_path()
        if meta.is_file():
            meta.unlink()
    except OSError:
        pass
