"""Testy pro app.core.transcribe_gemini.

Bez síťových volání — Gemini Client se mockuje. Pokrytí:
- parsing JSON odpovědi (čistá, s markdown wrapperem, alternativní názvy polí)
- mime detection
- error mapping (auth, rate limit, network)
- estimate funkce
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core import transcribe_gemini
from app.core.ai.base import AIAuthError, AIError, AINetworkError, AIRateLimitError


@pytest.fixture
def fake_mp3(tmp_path: Path) -> Path:
    p = tmp_path / "lecture.mp3"
    p.write_bytes(b"ID3" + b"\x00" * 1024)  # 1 KB pseudo-MP3
    return p


def test_detect_mime() -> None:
    assert transcribe_gemini._detect_mime(Path("a.mp3")) == "audio/mp3"
    assert transcribe_gemini._detect_mime(Path("a.wav")) == "audio/wav"
    assert transcribe_gemini._detect_mime(Path("a.m4a")) == "audio/mp4"
    assert transcribe_gemini._detect_mime(Path("a.flac")) == "audio/flac"
    # Neznámá přípona → konzervativní wav
    assert transcribe_gemini._detect_mime(Path("a.xyz")) == "audio/wav"


def test_parse_response_clean_json() -> None:
    raw = '{"segments": [{"start_sec": 0, "end_sec": 5, "text": "Ahoj"}, {"start_sec": 5, "end_sec": 10, "text": "světe"}]}'
    segments, text, duration = transcribe_gemini._parse_response(raw)
    assert len(segments) == 2
    assert segments[0].text == "Ahoj"
    assert segments[1].start == 5.0
    assert duration == 10.0
    assert text == "Ahoj světe"


def test_parse_response_markdown_wrapped() -> None:
    raw = '```json\n{"segments": [{"start_sec": 0, "end_sec": 3, "text": "Test"}]}\n```'
    segments, text, _ = transcribe_gemini._parse_response(raw)
    assert len(segments) == 1
    assert segments[0].text == "Test"
    assert text == "Test"


def test_parse_response_alternative_field_names() -> None:
    raw = '{"transcript": [{"start": 1.5, "end": 4.2, "content": "Pozdrav"}]}'
    segments, text, _ = transcribe_gemini._parse_response(raw)
    assert len(segments) == 1
    assert segments[0].start == 1.5
    assert segments[0].end == 4.2
    assert segments[0].text == "Pozdrav"


def test_parse_response_invalid_json_returns_empty() -> None:
    segments, text, duration = transcribe_gemini._parse_response("nope, not json")
    assert segments == []
    assert duration == 0.0
    # Text se vrátí jako fallback raw (tester to vidí v `text`)
    assert text == "nope, not json"


def test_parse_response_missing_segments() -> None:
    raw = '{"other_field": "xyz"}'
    segments, _, _ = transcribe_gemini._parse_response(raw)
    assert segments == []


def test_reraise_as_ai_error_auth() -> None:
    with pytest.raises(AIAuthError):
        transcribe_gemini._reraise_as_ai_error(Exception("API key invalid (401)"))


def test_reraise_as_ai_error_rate_limit() -> None:
    with pytest.raises(AIRateLimitError):
        transcribe_gemini._reraise_as_ai_error(Exception("429 quota exceeded"))


def test_reraise_as_ai_error_network() -> None:
    with pytest.raises(AINetworkError):
        transcribe_gemini._reraise_as_ai_error(Exception("connection timeout"))


def test_reraise_as_ai_error_generic() -> None:
    with pytest.raises(AIError):
        transcribe_gemini._reraise_as_ai_error(Exception("něco pomalého"))


def test_transcribe_missing_api_key_raises(fake_mp3: Path) -> None:
    with pytest.raises(AIAuthError):
        transcribe_gemini.transcribe_audio_via_gemini(
            fake_mp3, source_label="Lekce", api_key=""
        )


def test_transcribe_missing_file_raises(tmp_path: Path) -> None:
    bogus = tmp_path / "missing.mp3"
    with pytest.raises(AIError):
        transcribe_gemini.transcribe_audio_via_gemini(
            bogus, source_label="L", api_key="sk-fake"
        )


def test_transcribe_inline_happy_path(fake_mp3: Path) -> None:
    fake_response = MagicMock()
    fake_response.text = (
        '{"segments": [{"start_sec": 0, "end_sec": 2, "text": "Dobrý den"}, '
        '{"start_sec": 2, "end_sec": 5, "text": "vítám vás"}]}'
    )

    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    fake_genai = MagicMock()
    fake_genai.Client.return_value = fake_client
    fake_types = MagicMock()
    # Vrátíme reálný objekt, ne MagicMock, ať get_attr nepřekvapí
    fake_types.Part.from_bytes.return_value = object()
    fake_types.GenerateContentConfig.return_value = object()

    progress_calls: list[float] = []

    with patch.dict(
        "sys.modules",
        {"google": MagicMock(genai=fake_genai), "google.genai": fake_genai,
         "google.genai.types": fake_types},
    ):
        # Trochu cheating: musíme zajistit, že `from google import genai` uvnitř funkce
        # najde naše fake_genai. patch.dict toho dosáhne.
        result = transcribe_gemini.transcribe_audio_via_gemini(
            fake_mp3,
            source_label="Přednáška 1",
            api_key="sk-test",
            language="cs",
            progress_cb=progress_calls.append,
        )

    assert result.source_label == "Přednáška 1"
    assert result.language == "cs"
    assert result.duration_sec == 5.0
    assert len(result.segments) == 2
    assert result.text == "Dobrý den vítám vás"
    # Progress callback byl volaný (start, mid, end)
    assert progress_calls
    assert progress_calls[-1] == 1.0


def test_transcribe_cancel_before_request(fake_mp3: Path) -> None:
    cancel = threading.Event()
    cancel.set()

    fake_genai = MagicMock()
    fake_genai.Client.return_value = MagicMock()
    fake_types = MagicMock()

    with patch.dict(
        "sys.modules",
        {"google": MagicMock(genai=fake_genai), "google.genai": fake_genai,
         "google.genai.types": fake_types},
    ):
        with pytest.raises(transcribe_gemini.TranscribeGeminiCancelled):
            transcribe_gemini.transcribe_audio_via_gemini(
                fake_mp3,
                source_label="X",
                api_key="sk-test",
                cancel_event=cancel,
            )


def test_transcribe_propagates_gemini_quota_error(fake_mp3: Path) -> None:
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = Exception(
        "429 RESOURCE_EXHAUSTED quota"
    )

    fake_genai = MagicMock()
    fake_genai.Client.return_value = fake_client
    fake_types = MagicMock()
    fake_types.Part.from_bytes.return_value = object()
    fake_types.GenerateContentConfig.return_value = object()

    with patch.dict(
        "sys.modules",
        {"google": MagicMock(genai=fake_genai), "google.genai": fake_genai,
         "google.genai.types": fake_types},
    ):
        with pytest.raises(AIRateLimitError):
            transcribe_gemini.transcribe_audio_via_gemini(
                fake_mp3, source_label="X", api_key="sk-test"
            )


def test_estimate_gemini_seconds_grows_with_audio_length() -> None:
    short = transcribe_gemini.estimate_gemini_transcribe_seconds(60)  # 1 min
    long = transcribe_gemini.estimate_gemini_transcribe_seconds(3600)  # 1 hod
    assert long > short
    # Minimální floor pro krátké audio
    assert short >= 15.0  # 5 upload + 10 response


def test_build_prompt_czech_has_diacritics_hint() -> None:
    prompt = transcribe_gemini._build_prompt("cs")
    assert "diakritik" in prompt.lower()
    assert "JSON" in prompt


def test_build_prompt_english_no_czech_hint() -> None:
    prompt = transcribe_gemini._build_prompt("en")
    assert "diakritik" not in prompt.lower()
