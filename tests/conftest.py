"""Sdílené pytest fixtures."""

from __future__ import annotations

import struct
import wave
from pathlib import Path

import pytest


@pytest.fixture
def sample_wav(tmp_path: Path) -> Path:
    """Vytvoří krátký 1s ticho WAV (16 kHz mono) — bez závislosti na ffmpeg."""
    path = tmp_path / "silence_1s.wav"
    sample_rate = 16000
    duration_sec = 1
    num_samples = sample_rate * duration_sec
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # 1s ticha (PCM 16-bit zeros)
        wf.writeframes(struct.pack("<" + "h" * num_samples, *([0] * num_samples)))
    return path
