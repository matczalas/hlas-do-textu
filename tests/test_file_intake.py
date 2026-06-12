"""Testy klasifikace vstupních souborů (drop zone) a md_exportu s mluvčími.

`_classify_paths` je @staticmethod bez Qt závislostí na instanci — testujeme
přímo přes třídu, bez QApplication.
"""

from __future__ import annotations

from pathlib import Path

from app.core.md_export import export_markdown
from app.core.models import SourceKind, Transcript, TranscriptSegment


def _classify(paths: list[Path]):
    from app.gui.widgets.file_drop_zone import FileDropZone

    return FileDropZone._classify_paths(paths)


def test_classify_supported_files(tmp_path: Path) -> None:
    audio = tmp_path / "nahravka.mp3"
    audio.touch()
    slides = tmp_path / "slidy.pdf"
    slides.touch()

    sources, skipped = _classify([audio, slides])
    assert len(sources) == 2
    assert sources[0].kind == SourceKind.AUDIO_VIDEO
    assert sources[1].kind == SourceKind.PRESENTATION
    assert skipped == []


def test_classify_unsupported_reported_not_silent(tmp_path: Path) -> None:
    """Nepodporovaný soubor nesmí zmizet tiše — jde do skipped."""
    doc = tmp_path / "poznamky.docx"
    doc.touch()
    txt = tmp_path / "prepis.txt"
    txt.touch()

    sources, skipped = _classify([doc, txt])
    assert sources == []
    assert "poznamky.docx" in skipped
    assert "prepis.txt" in skipped


def test_classify_folder_expands_supported_files(tmp_path: Path) -> None:
    """Drop celé složky → vezmou se podporované soubory v ní (hromadné zadávání)."""
    folder = tmp_path / "nahravky"
    folder.mkdir()
    (folder / "a.mp3").touch()
    (folder / "b.m4a").touch()
    (folder / "ignorovat.docx").touch()

    sources, skipped = _classify([folder])
    labels = sorted(s.label for s in sources)
    assert labels == ["a", "b"]
    assert all(s.kind == SourceKind.AUDIO_VIDEO for s in sources)
    # .docx uvnitř složky se nehlásí jako skipped (bereme jen podporované),
    # ale složka samotná taky ne — našla aspoň jeden použitelný soubor
    assert skipped == []


def test_classify_folder_without_supported_files_reported(tmp_path: Path) -> None:
    folder = tmp_path / "dokumenty"
    folder.mkdir()
    (folder / "x.docx").touch()

    sources, skipped = _classify([folder])
    assert sources == []
    assert any("dokumenty" in s for s in skipped)


def test_md_export_preserves_speakers(tmp_path: Path) -> None:
    """Diarizovaný přepis: .md export nese označení mluvčích."""
    tr = Transcript(
        source_label="Schůzka",
        language="cs",
        duration_sec=20.0,
        text="Mluvčí 1: Dobrý den.\nMluvčí 2: Zdravím.",
        segments=[
            TranscriptSegment(start=0.0, end=5.0, text="Dobrý den.", speaker="Mluvčí 1"),
            TranscriptSegment(start=5.0, end=10.0, text="Zdravím.", speaker="Mluvčí 2"),
        ],
    )
    out = tmp_path / "prepis.md"
    export_markdown(output_path=out, transcripts=[tr])
    content = out.read_text(encoding="utf-8")
    assert "Mluvčí 1: Dobrý den." in content
    assert "Mluvčí 2: Zdravím." in content


def test_md_export_without_speakers_unchanged(tmp_path: Path) -> None:
    tr = Transcript(
        source_label="Přednáška",
        language="cs",
        duration_sec=10.0,
        text="Text bez mluvčích.",
        segments=[TranscriptSegment(start=0.0, end=5.0, text="Text bez mluvčích.")],
    )
    out = tmp_path / "prepis.md"
    export_markdown(output_path=out, transcripts=[tr])
    content = out.read_text(encoding="utf-8")
    assert "Text bez mluvčích." in content
    assert "Mluvčí" not in content
