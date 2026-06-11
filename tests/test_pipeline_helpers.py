"""Testy pomocných funkcí v pipeline (humanize_error, format_duration_human, backup)."""

from __future__ import annotations

from pathlib import Path

import httpx

from app.core.pipeline import (
    _save_transcript_backup,
    estimate_total_processing_seconds,
    format_duration_human,
    humanize_error,
)


def test_format_duration_seconds():
    assert format_duration_human(30) == "cca 30 sekund"


def test_format_duration_minutes_singular():
    assert format_duration_human(60) == "cca 1 minutu"


def test_format_duration_minutes_few():
    assert format_duration_human(180) == "cca 3 minuty"


def test_format_duration_minutes_many():
    assert format_duration_human(600) == "cca 10 minut"


def test_format_duration_hours_only():
    assert format_duration_human(3600) == "cca 1 hodinu"


def test_format_duration_hours_with_minutes():
    result = format_duration_human(3900)  # 1h 5 min
    assert "hodinu" in result
    assert "5 min" in result


def test_estimate_total_processing_returns_low_high():
    low, high = estimate_total_processing_seconds([600.0], whisper_model="medium", has_ai=True)
    assert low < high
    assert low > 0


def test_estimate_scales_with_cpu_speed_factor():
    """Pomalejší počítač (factor > 1) → vyšší odhad; rychlejší → nižší."""
    base_low, base_high = estimate_total_processing_seconds(
        [600.0], whisper_model="small", cpu_speed_factor=1.0
    )
    slow_low, slow_high = estimate_total_processing_seconds(
        [600.0], whisper_model="small", cpu_speed_factor=3.0
    )
    fast_low, fast_high = estimate_total_processing_seconds(
        [600.0], whisper_model="small", cpu_speed_factor=0.5
    )
    assert slow_high > base_high
    assert fast_high < base_high


def test_estimate_factor_clamped_to_sane_range():
    """Extrémní factor (např. z divného běhu) se ořízne, ať odhad není absurdní."""
    huge_low, huge_high = estimate_total_processing_seconds(
        [600.0], whisper_model="small", cpu_speed_factor=999.0
    )
    clamped_low, clamped_high = estimate_total_processing_seconds(
        [600.0], whisper_model="small", cpu_speed_factor=5.0
    )
    assert huge_high == clamped_high  # 999 se ořízne na 5.0


def test_humanize_error_permission():
    msg = humanize_error(PermissionError("/some/protected/path"))
    assert "oprávnění" in msg.lower()


def test_humanize_error_file_not_found():
    msg = humanize_error(FileNotFoundError("missing.mp3"))
    assert "nenalezen" in msg.lower()


def test_humanize_error_connect():
    msg = humanize_error(httpx.ConnectError("DNS"))
    assert "připojení" in msg.lower() or "internet" in msg.lower()


def test_humanize_error_oom_text():
    msg = humanize_error(RuntimeError("CUDA out of memory"))
    assert "paměti" in msg.lower() or "model" in msg.lower()


def test_save_transcript_backup_writes_file(tmp_path: Path):
    from app.core.models import Transcript, TranscriptSegment

    transcripts = [
        Transcript(
            source_label="Část A",
            language="cs",
            duration_sec=120.0,
            text="Plný text přepisu.",
            segments=[
                TranscriptSegment(start=0.0, end=10.0, text="Plný text"),
                TranscriptSegment(start=10.0, end=20.0, text="přepisu."),
            ],
        )
    ]
    path = _save_transcript_backup(transcripts, tmp_path)
    assert path is not None
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "Část A" in content
    assert "Plný text" in content
    assert "[00:00]" in content  # časová značka


def test_save_transcript_backup_empty_returns_none(tmp_path: Path):
    assert _save_transcript_backup([], tmp_path) is None


def test_save_transcript_backup_includes_speakers(tmp_path: Path):
    """Diarizovaný přepis: .txt záloha nese označení mluvčích u replik."""
    from app.core.models import Transcript, TranscriptSegment

    transcripts = [
        Transcript(
            source_label="Schůzka",
            language="cs",
            duration_sec=20.0,
            text="Mluvčí 1: Dobrý den.\nMluvčí 2: Zdravím.",
            segments=[
                TranscriptSegment(start=0.0, end=5.0, text="Dobrý den.", speaker="Mluvčí 1"),
                TranscriptSegment(start=5.0, end=10.0, text="Zdravím.", speaker="Mluvčí 2"),
            ],
        )
    ]
    path = _save_transcript_backup(transcripts, tmp_path)
    assert path is not None
    content = path.read_text(encoding="utf-8")
    assert "Mluvčí 1: Dobrý den." in content
    assert "Mluvčí 2: Zdravím." in content


def test_save_transcript_backup_goes_to_prepisy_subfolder(tmp_path: Path):
    """Přepis se ukládá do podsložky Přepisy/, ne do kořene output složky."""
    from app.core.models import Transcript

    transcripts = [
        Transcript(source_label="Přednáška X", language="cs", duration_sec=10.0,
                   text="text", segments=[]),
    ]
    path = _save_transcript_backup(transcripts, tmp_path)
    assert path is not None
    assert path.parent == tmp_path / "Přepisy"
    # Kořen output složky neobsahuje žádný .txt
    assert list(tmp_path.glob("*.txt")) == []
    # Název obsahuje sanitizovaný štítek zdroje
    assert "Přednáška-X" in path.stem
    assert path.stem.startswith("Prepis_")


def test_save_transcript_backup_multiple_recordings_label(tmp_path: Path):
    """Víc nahrávek → název odráží počet, ne jen jeden štítek."""
    from app.core.models import Transcript

    transcripts = [
        Transcript(source_label="A", language="cs", duration_sec=1.0, text="a", segments=[]),
        Transcript(source_label="B", language="cs", duration_sec=1.0, text="b", segments=[]),
    ]
    path = _save_transcript_backup(transcripts, tmp_path)
    assert path is not None
    assert "2-nahravek" in path.stem
