"""Testy pro app.core.checkpoint — resume přepisu od místa přerušení.

Klíčové: checkpoint je čistě aditivní — když cokoli nesedí, load() vrátí None
a volající jede plný přepis. Testy ověřují, že invalidace funguje spolehlivě.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core import checkpoint as ckpt


@pytest.fixture
def fake_audio(tmp_path: Path) -> Path:
    p = tmp_path / "prednaska.mp3"
    p.write_bytes(b"AUDIO" * 1000)
    return p


@pytest.fixture(autouse=True)
def isolated_checkpoints(tmp_path: Path):
    """Každý test má vlastní CHECKPOINTS_DIR."""
    cp_dir = tmp_path / "checkpoints"
    cp_dir.mkdir()
    with patch.object(ckpt, "CHECKPOINTS_DIR", cp_dir):
        yield cp_dir


def _segments() -> list[dict]:
    return [
        {"start": 0.0, "end": 5.0, "text": "První věta."},
        {"start": 5.0, "end": 10.0, "text": "Druhá věta."},
    ]


def test_save_and_load_roundtrip(fake_audio: Path) -> None:
    ckpt.save(fake_audio, "small", "cs", _segments(), completed_until_sec=10.0)
    loaded = ckpt.load(fake_audio, "small", "cs")
    assert loaded is not None
    assert loaded.completed_until_sec == 10.0
    assert len(loaded.segments) == 2
    assert loaded.segments[0]["text"] == "První věta."


def test_load_missing_returns_none(fake_audio: Path) -> None:
    assert ckpt.load(fake_audio, "small", "cs") is None


def test_load_different_model_returns_none(fake_audio: Path) -> None:
    ckpt.save(fake_audio, "small", "cs", _segments(), 10.0)
    # Jiný model → segmenty by neseděly → ignorovat
    assert ckpt.load(fake_audio, "medium", "cs") is None


def test_load_different_language_returns_none(fake_audio: Path) -> None:
    ckpt.save(fake_audio, "small", "cs", _segments(), 10.0)
    assert ckpt.load(fake_audio, "small", "en") is None


def test_load_after_file_modified_returns_none(fake_audio: Path) -> None:
    ckpt.save(fake_audio, "small", "cs", _segments(), 10.0)
    # Změníme soubor (jiná velikost/mtime) → fingerprint nesedí
    fake_audio.write_bytes(b"ZMENA" * 2000)
    assert ckpt.load(fake_audio, "small", "cs") is None


def test_load_corrupt_json_returns_none(fake_audio: Path, isolated_checkpoints: Path) -> None:
    ckpt.save(fake_audio, "small", "cs", _segments(), 10.0)
    # Poškodíme checkpoint soubor
    for f in isolated_checkpoints.glob("*.json"):
        f.write_text("{ tohle není validní JSON", encoding="utf-8")
    assert ckpt.load(fake_audio, "small", "cs") is None


def test_delete_removes_checkpoint(fake_audio: Path) -> None:
    ckpt.save(fake_audio, "small", "cs", _segments(), 10.0)
    assert ckpt.load(fake_audio, "small", "cs") is not None
    ckpt.delete(fake_audio, "small", "cs")
    assert ckpt.load(fake_audio, "small", "cs") is None


def test_is_useful_threshold() -> None:
    short = ckpt.TranscriptCheckpoint("fp", "small", "cs", 5.0, _segments())
    assert not short.is_useful()  # jen 5s, pod prahem 30s
    long = ckpt.TranscriptCheckpoint("fp", "small", "cs", 120.0, _segments())
    assert long.is_useful()
    empty = ckpt.TranscriptCheckpoint("fp", "small", "cs", 120.0, [])
    assert not empty.is_useful()  # žádné segmenty


def test_load_invalid_segments_filtered(fake_audio: Path, isolated_checkpoints: Path) -> None:
    """Segmenty bez start/end/text se přeskočí, validní zůstanou."""
    ckpt.save(fake_audio, "small", "cs", _segments(), 10.0)
    # Ručně přidáme nevalidní segment do souboru
    for f in isolated_checkpoints.glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        data["segments"].append({"start": "nope"})  # chybí end/text, špatný typ
        data["segments"].append({"garbage": 1})
        f.write_text(json.dumps(data), encoding="utf-8")
    loaded = ckpt.load(fake_audio, "small", "cs")
    assert loaded is not None
    assert len(loaded.segments) == 2  # nevalidní odfiltrovány


def test_cleanup_old_removes_aged(fake_audio: Path, isolated_checkpoints: Path) -> None:
    import os
    import time

    ckpt.save(fake_audio, "small", "cs", _segments(), 10.0)
    cp_file = next(isolated_checkpoints.glob("*.json"))
    # Posuneme mtime o 8 dní zpět
    old_time = time.time() - 8 * 24 * 3600
    os.utime(cp_file, (old_time, old_time))

    ckpt.cleanup_old()
    assert not cp_file.exists()


def test_cleanup_keeps_recent(fake_audio: Path, isolated_checkpoints: Path) -> None:
    ckpt.save(fake_audio, "small", "cs", _segments(), 10.0)
    ckpt.cleanup_old()  # čerstvý → zůstane
    assert ckpt.load(fake_audio, "small", "cs") is not None


def test_save_is_atomic_no_tmp_left(fake_audio: Path, isolated_checkpoints: Path) -> None:
    ckpt.save(fake_audio, "small", "cs", _segments(), 10.0)
    # Po uložení nesmí zůstat .tmp
    tmp_files = list(isolated_checkpoints.glob("*.tmp"))
    assert tmp_files == []
