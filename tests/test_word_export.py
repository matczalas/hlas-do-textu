"""Smoke test exportu do Wordu."""

from __future__ import annotations

from pathlib import Path

from app.core.models import (
    SlideText,
    SourceFile,
    SourceKind,
    StudyMaterial,
    Transcript,
    TranscriptSegment,
)
from app.core.word_export import export_docx, suggested_output_filename


def test_export_docx_creates_valid_file(tmp_path: Path) -> None:
    material = StudyMaterial(
        title="Testovací materiál",
        bullets=["První bod", "Druhý bod"],
        terms=[("pojem A", "definice A"), ("pojem B", "definice B")],
        examples=["Příklad 1"],
        further_study=["Dočti kapitolu 5"],
    )
    transcripts = [
        Transcript(
            source_label="Část 1",
            language="cs",
            duration_sec=120.0,
            text="Toto je testovací přepis přednášky.",
            segments=[
                TranscriptSegment(start=0.0, end=10.0, text="Toto je testovací"),
                TranscriptSegment(start=10.0, end=20.0, text="přepis přednášky."),
            ],
        )
    ]
    slides = [SlideText(source_label="Slidy 1", text="[Slide 1]\nNějaký text", slide_count=1)]
    sources = [
        SourceFile(path=tmp_path / "fake.mp3", kind=SourceKind.AUDIO_VIDEO, label="Část 1"),
    ]

    out = tmp_path / "test.docx"
    result = export_docx(
        output_path=out,
        material=material,
        transcripts=transcripts,
        slides=slides,
        sources=sources,
        user_prompt="Test prompt",
    )

    assert result == out
    assert out.exists()
    assert out.stat().st_size > 1000  # docx má nějaký rozumný objem


def test_suggested_filename_safe():
    material = StudyMaterial(title="Test / Materiál * 2026")
    name = suggested_output_filename(material)
    assert name.endswith(".docx")
    # žádné nelegální Windows znaky
    for forbidden in ("/", "\\", ":", "*", "?", '"', "<", ">", "|"):
        assert forbidden not in name


def test_suggested_filename_empty_title_fallback():
    material = StudyMaterial(title="")
    name = suggested_output_filename(material)
    assert name.endswith(".docx")
    assert len(name) > 5


def test_export_docx_survives_control_characters(tmp_path: Path) -> None:
    """Control znaky (\\x00, \\x0b...) z Whisper/PDF nesmí shodit export —
    python-docx by jinak vyhodil ValueError a ztratila by se celá práce."""
    material = StudyMaterial(
        title="Mat\x00eriál\x0b s control znaky",
        bullets=["Bod s\x00 NULL", "Normální bod"],
        terms=[("po\x0cjem", "defi\x1fnice")],
        examples=["Příklad\x08"],
        further_study=["Zdroj\x0e"],
    )
    transcripts = [
        Transcript(
            source_label="Část\x00 1",
            language="cs",
            duration_sec=10.0,
            text="Přepis\x00 s control\x0b znakem.",
            segments=[TranscriptSegment(start=0.0, end=5.0, text="Přepis\x00 s control\x0b znakem.")],
        )
    ]
    out = tmp_path / "ctrl.docx"
    # Nesmí vyhodit ValueError
    result = export_docx(
        output_path=out,
        material=material,
        transcripts=transcripts,
        slides=[],
        sources=[],
        user_prompt="Prompt\x00 s NULL",
    )
    assert result.exists()
    assert out.stat().st_size > 1000
