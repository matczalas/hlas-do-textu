"""Testy pro robustní načítání settings (audit 2 — ne-dict JSON, špatné typy)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from app import settings as settings_mod


def _load_with_config(tmp_path: Path, content: str):
    cfg = tmp_path / "config.json"
    cfg.write_text(content, encoding="utf-8")
    with patch.object(settings_mod, "CONFIG_FILE", cfg):
        return settings_mod.load_settings()


def test_load_settings_non_dict_json_falls_back_to_defaults(tmp_path: Path) -> None:
    # config.json je validní JSON, ale ne objekt (po ruční editaci / bugu)
    for bad in ("[]", "null", "123", '"text"'):
        s = _load_with_config(tmp_path, bad)
        # Nesmí spadnout, vrátí defaulty
        assert s.transcribe_backend == "local_whisper"


def test_load_settings_corrupt_json_falls_back(tmp_path: Path) -> None:
    s = _load_with_config(tmp_path, "{ tohle není validní JSON")
    assert s.whisper_model  # nějaký default


def test_load_settings_wrong_field_type_uses_default(tmp_path: Path) -> None:
    # recent_outputs má být list, ale je string → nesmí projít jako string
    data = json.dumps({"recent_outputs": "x", "whisper_model": 123, "ai_consent_gemini": "yes"})
    s = _load_with_config(tmp_path, data)
    assert isinstance(s.recent_outputs, list)
    assert s.recent_outputs == []  # špatný typ → default
    assert isinstance(s.whisper_model, str)  # 123 → default (string)


def test_load_settings_valid_values_preserved(tmp_path: Path) -> None:
    data = json.dumps({
        "transcribe_backend": "cloud_gemini",
        "recent_outputs": ["/a/b.docx", "/c/d.docx"],
        "ai_consent_gemini": True,
    })
    s = _load_with_config(tmp_path, data)
    assert s.transcribe_backend == "cloud_gemini"
    assert s.recent_outputs == ["/a/b.docx", "/c/d.docx"]
    assert s.ai_consent_gemini is True


def test_load_settings_bool_from_int(tmp_path: Path) -> None:
    # JSON bool jako 0/1 → coerce na bool
    data = json.dumps({"ai_consent_gemini": 1, "prefer_offline": 0})
    s = _load_with_config(tmp_path, data)
    assert s.ai_consent_gemini is True
    assert s.prefer_offline is False
