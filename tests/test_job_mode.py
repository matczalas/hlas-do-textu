"""Testy pro JobMode enum a větvení pipeline."""

from __future__ import annotations

from pathlib import Path

from app.core.models import JobConfig, JobMode, SourceFile, SourceKind
from app.core.pipeline import estimate_total_processing_seconds


def test_default_job_mode_is_full():
    job = JobConfig(
        sources=[],
        user_prompt="",
        output_dir=Path("/tmp"),
    )
    assert job.mode == JobMode.FULL


def test_job_mode_transcribe_only_assignable():
    job = JobConfig(
        sources=[SourceFile(path=Path("/tmp/x.mp3"), kind=SourceKind.AUDIO_VIDEO, label="x")],
        user_prompt="",
        output_dir=Path("/tmp"),
        mode=JobMode.TRANSCRIBE_ONLY,
    )
    assert job.mode == JobMode.TRANSCRIBE_ONLY


def test_estimate_transcribe_only_shorter_than_full():
    durations = [600.0, 900.0]
    full_low, full_high = estimate_total_processing_seconds(durations, has_ai=True, transcribe_only=False)
    only_low, only_high = estimate_total_processing_seconds(durations, has_ai=True, transcribe_only=True)
    # Transcribe-only nemá AI fázi → musí být kratší
    assert only_low < full_low
    assert only_high < full_high


def test_estimate_with_short_audio_realistic():
    """3 minutové audio na medium model — odhad by neměl být šílený."""
    low, high = estimate_total_processing_seconds([180.0], whisper_model="medium")
    # Mělo by být řádově minuty (na CPU bez GPU)
    assert 60 <= low <= 600
    assert 60 <= high <= 600
