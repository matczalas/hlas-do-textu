"""Testy generování a validace licenčních klíčů."""

from __future__ import annotations

from app.licensing import generate_key, is_valid_format, validate_key
from app.licensing.keys import normalize_key


def test_generate_key_format():
    key = generate_key()
    assert key.startswith("S4F1-")
    assert len(key) == 24  # S4F1- + 4 groups of 4 + 3 dashes
    parts = key.split("-")
    assert len(parts) == 5
    assert parts[0] == "S4F1"
    for p in parts[1:]:
        assert len(p) == 4


def test_generate_key_passes_validation():
    for _ in range(20):
        key = generate_key()
        assert validate_key(key), f"Generated key failed validation: {key}"


def test_generate_key_is_unique():
    keys = {generate_key() for _ in range(50)}
    assert len(keys) == 50, "Generator produced duplicates"


def test_validate_rejects_empty():
    assert not validate_key("")
    assert not validate_key("   ")


def test_validate_rejects_wrong_prefix():
    valid = generate_key()
    bad = "XXXX-" + valid.split("-", 1)[1]
    assert not validate_key(bad)


def test_validate_rejects_wrong_checksum():
    valid = generate_key()
    parts = valid.split("-")
    # Změň jeden znak ve checksum části (poslední skupina)
    last = parts[-1]
    modified = last[:-1] + ("A" if last[-1] != "A" else "B")
    bad = "-".join(parts[:-1] + [modified])
    assert not validate_key(bad)


def test_validate_rejects_wrong_length():
    assert not validate_key("S4F1-AAAA-BBBB-CCCC")  # missing one group
    assert not validate_key("S4F1-AAAA-BBBB-CCCC-DDDD-EEEE")  # extra group


def test_validate_rejects_lowercase_letters_after_normalize():
    """Klíče interně jsou uppercase, ale uživatel může napsat malá písmena."""
    valid = generate_key()
    assert validate_key(valid.lower())  # validate normalizuje na uppercase
    assert validate_key(valid.upper())


def test_is_valid_format_levny_check():
    """Format check je levný — neměl by computovat HMAC."""
    valid = generate_key()
    assert is_valid_format(valid)
    assert not is_valid_format("nesmyl")
    # Crockford alphabet vynechá I, L, O, U — kontrola že je odmítne
    assert not is_valid_format("S4F1-IIII-IIII-IIII-IIII")
    assert not is_valid_format("S4F1-LLLL-LLLL-LLLL-LLLL")
    assert not is_valid_format("S4F1-OOOO-OOOO-OOOO-OOOO")


def test_normalize_key_raises_on_invalid():
    import pytest

    with pytest.raises(ValueError):
        normalize_key("S4F1-IIII-IIII-IIII-IIII")  # I není v alphabet


def test_normalize_returns_uppercase():
    valid = generate_key().lower()
    normalized = normalize_key(valid)
    assert normalized == valid.upper()
    assert normalized.startswith("S4F1-")
