"""Testy ukládání Gemini klíče a licence do souboru místo keychainu.

Cíl změny: nepodepsaná macOS aplikace nesmí při normálním provozu sahat na
Keychain (každé čtení = dotaz na systémové heslo). Klíče se proto ukládají do
souboru 0600 a Keychain se čte max jednou (migrace ze starých verzí).

Testy izolují USER_CONFIG_DIR přes monkeypatch do tmp_path a mockují `keyring`,
ať se nesahá na reálný systémový Keychain.
"""

from __future__ import annotations

import sys
import types

import pytest


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Přesměruje USER_CONFIG_DIR (a souborové cesty) do tmp_path.

    Resetuje i in-memory cache Gemini klíče mezi testy.
    """
    import app.config as config
    import app.settings as settings

    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config, "USER_CONFIG_DIR", cfg_dir, raising=True)
    monkeypatch.setattr(settings, "USER_CONFIG_DIR", cfg_dir, raising=True)
    # ensure_dirs nesmí vyrábět reálné systémové složky
    monkeypatch.setattr(settings, "ensure_dirs", lambda: None, raising=True)
    # reset cache
    monkeypatch.setattr(settings, "_gemini_cache", settings._UNSET, raising=True)
    # bez env override
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    return cfg_dir


def _install_fake_keyring(monkeypatch, *, stored: dict | None = None):
    """Nainstaluje fake `keyring` modul do sys.modules. Vrací dict se stavem."""
    state = {"store": stored or {}, "get_calls": 0, "set_calls": 0}

    fake = types.ModuleType("keyring")
    errors_mod = types.ModuleType("keyring.errors")

    class PasswordDeleteError(Exception):
        pass

    errors_mod.PasswordDeleteError = PasswordDeleteError

    def get_password(service, user):
        state["get_calls"] += 1
        return state["store"].get((service, user))

    def set_password(service, user, value):
        state["set_calls"] += 1
        state["store"][(service, user)] = value

    def delete_password(service, user):
        if (service, user) not in state["store"]:
            raise PasswordDeleteError()
        del state["store"][(service, user)]

    fake.get_password = get_password
    fake.set_password = set_password
    fake.delete_password = delete_password
    fake.errors = errors_mod

    monkeypatch.setitem(sys.modules, "keyring", fake)
    monkeypatch.setitem(sys.modules, "keyring.errors", errors_mod)
    return state


# ---------------------------------------------------------------------------
# Gemini klíč
# ---------------------------------------------------------------------------


def test_gemini_set_writes_file_not_keychain(isolated_config, monkeypatch):
    import app.settings as settings

    state = _install_fake_keyring(monkeypatch)
    settings.set_gemini_api_key("AIzaTESTKEY123")

    # Soubor existuje, keychain se NEPSAL
    key_file = isolated_config / settings._GEMINI_FILE_NAME
    assert key_file.is_file()
    assert key_file.read_text(encoding="utf-8") == "AIzaTESTKEY123"
    assert state["set_calls"] == 0, "set_gemini_api_key nesmí psát do keychainu"


def test_gemini_file_is_0600(isolated_config, monkeypatch):
    import app.settings as settings

    _install_fake_keyring(monkeypatch)
    settings.set_gemini_api_key("AIzaSECRET")
    key_file = isolated_config / settings._GEMINI_FILE_NAME
    mode = key_file.stat().st_mode & 0o777
    assert mode == 0o600, f"Očekávám 0600, je {oct(mode)}"


def test_gemini_get_reads_from_file_without_keychain(isolated_config, monkeypatch):
    import app.settings as settings

    state = _install_fake_keyring(monkeypatch)
    settings.set_gemini_api_key("AIzaFROMFILE")
    # reset cache, ať čteme z disku
    monkeypatch.setattr(settings, "_gemini_cache", settings._UNSET)

    value = settings.get_gemini_api_key()
    assert value == "AIzaFROMFILE"
    assert state["get_calls"] == 0, "Když existuje soubor, keychain se nesmí číst"


def test_gemini_get_is_cached(isolated_config, monkeypatch):
    import app.settings as settings

    _install_fake_keyring(monkeypatch)
    settings.set_gemini_api_key("AIzaCACHED")
    monkeypatch.setattr(settings, "_gemini_cache", settings._UNSET)

    # První čtení naplní cache; pak smažeme soubor — druhé čtení musí jít z cache
    first = settings.get_gemini_api_key()
    (isolated_config / settings._GEMINI_FILE_NAME).unlink()
    second = settings.get_gemini_api_key()
    assert first == second == "AIzaCACHED"


def test_gemini_migrates_from_keychain_once(isolated_config, monkeypatch):
    import app.settings as settings

    # Starý uživatel: klíč jen v keychainu, žádný soubor
    state = _install_fake_keyring(
        monkeypatch,
        stored={(settings._KEYRING_SERVICE, settings._KEYRING_USER): "AIzaOLDKEYCHAIN"},
    )

    value = settings.get_gemini_api_key()
    assert value == "AIzaOLDKEYCHAIN"
    assert state["get_calls"] == 1, "Migrace čte keychain právě jednou"
    # Soubor byl vytvořen migrací
    assert (isolated_config / settings._GEMINI_FILE_NAME).is_file()

    # Druhé čtení (po resetu cache) už keychain NESAHÁ — čte ze souboru
    monkeypatch.setattr(settings, "_gemini_cache", settings._UNSET)
    value2 = settings.get_gemini_api_key()
    assert value2 == "AIzaOLDKEYCHAIN"
    assert state["get_calls"] == 1, "Po migraci se keychain už nečte"


def test_gemini_clear_writes_tombstone_no_resurrection(isolated_config, monkeypatch):
    """Po smazání klíče se starý klíč z keychainu nesmí vzkřísit migrací."""
    import app.settings as settings

    state = _install_fake_keyring(
        monkeypatch,
        stored={(settings._KEYRING_SERVICE, settings._KEYRING_USER): "AIzaGHOST"},
    )

    # Uživatel klíč smaže
    settings.set_gemini_api_key("")
    monkeypatch.setattr(settings, "_gemini_cache", settings._UNSET)

    # Soubor existuje (prázdný tombstone) → keychain se nečte → None
    value = settings.get_gemini_api_key()
    assert value is None
    assert state["get_calls"] == 0, "Tombstone soubor zabrání čtení keychainu"


def test_gemini_env_var_wins(isolated_config, monkeypatch):
    import app.settings as settings

    _install_fake_keyring(monkeypatch)
    settings.set_gemini_api_key("AIzaFROMFILE")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaFROMENV")
    monkeypatch.setattr(settings, "_gemini_cache", settings._UNSET)

    assert settings.get_gemini_api_key() == "AIzaFROMENV"


# ---------------------------------------------------------------------------
# Licence
# ---------------------------------------------------------------------------


def test_license_get_reads_file_first_no_keychain(tmp_path, monkeypatch):
    import app.licensing.store as store

    lic_file = tmp_path / ".license"
    lic_file.write_text("S4F1-AAAA-BBBB-CCCC-DDDD", encoding="utf-8")
    monkeypatch.setattr(store, "_fallback_path", lambda: lic_file)

    state = _install_fake_keyring(monkeypatch)
    value = store.get_stored_key()
    assert value == "S4F1-AAAA-BBBB-CCCC-DDDD"
    assert state["get_calls"] == 0, "Když existuje .license soubor, keychain se nesmí číst"


def test_license_migrates_from_keychain_to_file(tmp_path, monkeypatch):
    import app.licensing.store as store

    lic_file = tmp_path / ".license"  # neexistuje
    monkeypatch.setattr(store, "_fallback_path", lambda: lic_file)

    state = _install_fake_keyring(
        monkeypatch,
        stored={(store._KEYRING_SERVICE, store._KEYRING_USER): "s4f1-eeee-ffff-gggg-hhhh"},
    )

    value = store.get_stored_key()
    assert value == "S4F1-EEEE-FFFF-GGGG-HHHH"  # normalizováno na upper
    assert state["get_calls"] == 1
    # Migrace zapsala soubor
    assert lic_file.is_file()
    assert lic_file.read_text(encoding="utf-8").strip().upper() == "S4F1-EEEE-FFFF-GGGG-HHHH"
