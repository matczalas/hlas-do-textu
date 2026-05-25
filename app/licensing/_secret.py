"""HMAC secret pro validaci licenčních klíčů.

Načítá se v tomto pořadí:
1) env var HDT_HMAC_SECRET — používá CI při buildu (přes GitHub Actions Secret)
2) Soubor .env v project rootu — pro lokální dev (gitignored)
3) DEV_FALLBACK — jen pro veřejný kód, klíče vygenerované tímto secretem
   NEFUNGUJÍ na produkční binárce. Slouží jen aby se aplikace dala spustit
   z public repa pro contributory.

V CI buildu Windows .exe se navíc tento soubor přepíše skriptem
`scripts/inject_secret.py`, který hard-coduje production secret do
binárky před PyInstaller stepem.
"""
from __future__ import annotations

import os
from pathlib import Path

KEY_PREFIX: str = "S4F1"

# Tohle JE veřejně viditelné. Klíče vygenerované tímto secretem nebudou
# fungovat s production binárkou — CI ji při buildu přepíše.
_DEV_FALLBACK: bytes = b"DEV_ONLY_SECRET_NOT_FOR_PRODUCTION_USE_xxxxxxxxxxxxxxxxxx"


def _load_dotenv() -> str | None:
    """Lehký .env parser bez závislosti na python-dotenv."""
    root = Path(__file__).resolve().parent.parent.parent
    dotenv = root / ".env"
    if not dotenv.is_file():
        return None
    try:
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "HDT_HMAC_SECRET":
                return value.strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def _resolve_secret() -> bytes:
    env_value = os.environ.get("HDT_HMAC_SECRET", "").strip()
    if env_value:
        return env_value.encode("ascii")

    file_value = _load_dotenv()
    if file_value:
        return file_value.encode("ascii")

    return _DEV_FALLBACK


HMAC_SECRET: bytes = _resolve_secret()
