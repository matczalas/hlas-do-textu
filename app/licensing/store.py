"""Uložení license klíče v keyring (Windows Credential Manager / macOS Keychain).

Klíč se ukládá pod service 'HlasDoTextu.license'. Pokud keyring backend selže
(některé Win Server / Linux without dbus), použijeme fallback do souboru
v USER_CONFIG_DIR — ale i tam je validace přes HMAC, takže utajení secretu
v souboru nehraje roli (uložen je hotový validní klíč, ne secret).
"""
from __future__ import annotations

from loguru import logger

from app import __app_name__
from app.config import USER_CONFIG_DIR, ensure_dirs
from app.licensing.keys import normalize_key, validate_key

_KEYRING_SERVICE = f"{__app_name__}.license"
_KEYRING_USER = "default"
_FALLBACK_FILE_NAME = ".license"


def _fallback_path():
    ensure_dirs()
    return USER_CONFIG_DIR / _FALLBACK_FILE_NAME


def store_key(key: str) -> None:
    """Uloží klíč po validaci. Vyhodí ValueError pokud klíč neplatný."""
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
        # Na unixu nastavíme rw jen pro uživatele
        try:
            path.chmod(0o600)
        except OSError:
            pass
        logger.info("Licenční klíč zazálohován do {}", path)
    except Exception as exc:  # noqa: BLE001
        if not stored_via_keyring:
            raise RuntimeError(f"Nepodařilo se uložit licenční klíč: {exc}") from exc
        logger.warning("Fallback file uložit selhal: {}", exc)


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
