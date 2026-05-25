"""Testy parseru .txt přepisu pro regeneraci."""

from __future__ import annotations

from pathlib import Path

from app.core.models import Transcript, TranscriptSegment
from app.core.pipeline import _save_transcript_backup, parse_transcript_backup_file


def test_roundtrip_save_then_parse(tmp_path: Path) -> None:
    """Co `_save_transcript_backup` zapíše, musí `parse_transcript_backup_file` zase načíst."""
    original = [
        Transcript(
            source_label="Kapitola 1",
            language="cs",
            duration_sec=45.0,
            text="První věta. Druhá věta.",
            segments=[
                TranscriptSegment(start=0.0, end=10.0, text="První věta."),
                TranscriptSegment(start=10.0, end=20.0, text="Druhá věta."),
            ],
        ),
        Transcript(
            source_label="Kapitola 2",
            language="cs",
            duration_sec=30.0,
            text="Třetí věta.",
            segments=[
                TranscriptSegment(start=0.0, end=15.0, text="Třetí věta."),
            ],
        ),
    ]

    txt_path = _save_transcript_backup(original, tmp_path)
    assert txt_path is not None

    loaded = parse_transcript_backup_file(txt_path)
    assert len(loaded) == 2
    assert loaded[0].source_label == "Kapitola 1"
    assert "První věta" in loaded[0].text
    assert "Druhá věta" in loaded[0].text
    assert loaded[1].source_label == "Kapitola 2"
    assert "Třetí věta" in loaded[1].text
    # Časové značky se rekonstruovaly
    assert len(loaded[0].segments) == 2
    assert loaded[0].segments[0].start == 0.0
    assert loaded[0].segments[1].start == 10.0


def test_parse_missing_file_raises(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(FileNotFoundError):
        parse_transcript_backup_file(tmp_path / "neexistuje.txt")


def test_parse_handles_hour_timestamps(tmp_path: Path) -> None:
    txt = tmp_path / "long.txt"
    txt.write_text(
        "# Přepis\n\n"
        "=== Dlouhá přednáška ===\n\n"
        "[00:00] Začátek.\n"
        "[01:00:30] Hodina a půl minuty.\n",
        encoding="utf-8",
    )
    loaded = parse_transcript_backup_file(txt)
    assert len(loaded) == 1
    assert len(loaded[0].segments) == 2
    assert loaded[0].segments[1].start == 3630.0  # 1h 0m 30s
