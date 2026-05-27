"""Testy parseru JSON odpovědí z AI."""

from __future__ import annotations

from app.core.ai.router import _parse_study_material, _safe_parse_json


def test_parse_clean_json():
    raw = '{"title": "Test", "bullets": ["a", "b"], "terms": [["pojem", "definice"]], "examples": [], "further_study": []}'
    mat = _parse_study_material(raw)
    assert mat.title == "Test"
    assert mat.bullets == ["a", "b"]
    assert mat.terms == [("pojem", "definice")]


def test_parse_extracts_topic():
    raw = '{"topic": "Fyzika", "title": "Newton", "bullets": ["a"]}'
    mat = _parse_study_material(raw)
    assert mat.topic == "Fyzika"
    assert mat.title == "Newton"


def test_parse_missing_topic_defaults_empty():
    raw = '{"title": "X", "bullets": ["a"]}'
    mat = _parse_study_material(raw)
    assert mat.topic == ""


def test_parse_markdown_fenced_json():
    raw = "Zde je tvůj výstup:\n```json\n{\"title\": \"T\", \"bullets\": [\"x\"]}\n```\nHotovo."
    mat = _parse_study_material(raw)
    assert mat.title == "T"
    assert mat.bullets == ["x"]


def test_parse_terms_dict_form():
    raw = '{"title": "T", "terms": [{"pojem": "A", "definice": "B"}]}'
    mat = _parse_study_material(raw)
    assert mat.terms == [("A", "B")]


def test_safe_parse_returns_none_for_garbage():
    assert _safe_parse_json("zcela nestrukturovaný text bez JSON") is None
    assert _safe_parse_json("") is None


def test_parse_fallback_when_no_json():
    """Když AI vrátí nestrukturovaný text, dáme ho do bullets."""
    raw = "Nějaký dlouhý text bez JSON struktury."
    mat = _parse_study_material(raw)
    assert mat.bullets == [raw.strip()[:1000]]
    assert mat.title  # nějaký default titul
