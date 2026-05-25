"""Generování a validace licenčních klíčů.

Formát: ``PREFIX-XXXX-XXXX-XXXX-XXXX`` (20 znaků + 4 dashes = 24).

Detail:
- ``PREFIX`` = ``S4F1`` (Safe4Future v1)
- 8 znaků payload — náhodný customer ID v Crockford base32 (bez I, L, O, U)
- 8 znaků HMAC checksum (truncated SHA-256 base32) přes prefix + payload

Validace = recompute HMAC + porovnání s checksumem.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from app.licensing._secret import HMAC_SECRET, KEY_PREFIX

# Crockford base32 abeceda — vynechává I/L/O/U aby se vyhnula záměnám
# se znaky 1/0 a vulgarismy. 32 znaků celkem.
_ALPHABET: str = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ALPHABET_SET: frozenset = frozenset(_ALPHABET)

_PAYLOAD_LEN: int = 8
_CHECKSUM_LEN: int = 8
_KEY_FORMAT_LEN: int = len(KEY_PREFIX) + 1 + 4 + 1 + 4 + 1 + 4 + 1 + 4  # = 24


def _to_alphabet(data: bytes, length: int) -> str:
    """Převede bytes na string v naší base32 abecedě, délky `length`."""
    out: list[str] = []
    num = int.from_bytes(data, "big")
    for _ in range(length):
        out.append(_ALPHABET[num & 0x1F])
        num >>= 5
    return "".join(reversed(out))


def _compute_checksum(prefix: str, payload: str) -> str:
    """Spočítá HMAC-SHA256 ze 'prefix:payload' a vrátí prvních `_CHECKSUM_LEN` znaků."""
    message = f"{prefix}:{payload}".encode("ascii")
    digest = hmac.new(HMAC_SECRET, message, hashlib.sha256).digest()
    return _to_alphabet(digest, _CHECKSUM_LEN)


def _format_groups(s: str) -> str:
    """Rozdělí 16-znakový string na 4 čtveřice oddělené pomlčkami."""
    if len(s) != 16:
        raise ValueError(f"Očekáváno 16 znaků, máme {len(s)}")
    return "-".join(s[i : i + 4] for i in range(0, 16, 4))


def generate_key() -> str:
    """Vygeneruje nový validní licenční klíč.

    Volá se z scripts/make_key.py — admin tool pro správce.
    """
    random_bytes = secrets.token_bytes(5)  # 5 bajtů → 8 base32 znaků
    payload = _to_alphabet(random_bytes, _PAYLOAD_LEN)
    checksum = _compute_checksum(KEY_PREFIX, payload)
    combined = payload + checksum
    return f"{KEY_PREFIX}-{_format_groups(combined)}"


def is_valid_format(key: str) -> bool:
    """Levný předkontrol — bez výpočtu HMAC. Použiju v UI pro instant feedback."""
    if not key:
        return False
    key = key.strip().upper()
    if len(key) != _KEY_FORMAT_LEN:
        return False
    if not key.startswith(f"{KEY_PREFIX}-"):
        return False
    # 5 groups separated by 4 dashes
    groups = key.split("-")
    if len(groups) != 5:
        return False
    if groups[0] != KEY_PREFIX:
        return False
    for g in groups[1:]:
        if len(g) != 4:
            return False
        if not all(c in _ALPHABET_SET for c in g):
            return False
    return True


def validate_key(key: str) -> bool:
    """Plná validace s HMAC. Volá se před uložením klíče.

    Vrátí False pro:
    - špatný formát (prefix, délka, znaky mimo abecedu)
    - správný formát ale chybný HMAC checksum
    """
    if not is_valid_format(key):
        return False

    normalized = key.strip().upper()
    groups = normalized.split("-")
    payload = groups[1] + groups[2]  # prvních 8 znaků
    expected_checksum = groups[3] + groups[4]  # posledních 8 znaků
    actual_checksum = _compute_checksum(KEY_PREFIX, payload)

    # Constant-time porovnání (nezáleží na časové analýze, ale dobrá praxe)
    return hmac.compare_digest(expected_checksum, actual_checksum)


def normalize_key(key: str) -> str:
    """Vrátí klíč v kanonické formě (uppercase, trimmed) pokud je validní."""
    if not validate_key(key):
        raise ValueError("Neplatný licenční klíč")
    return key.strip().upper()
