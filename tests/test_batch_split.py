"""Testy pro dávkové rozdělení zdrojů (v0.8.0 batch fronta)."""

from __future__ import annotations

from pathlib import Path

from app.core.models import SourceFile, SourceKind
from app.core.pipeline import split_sources_for_batch


def _audio(name: str) -> SourceFile:
    return SourceFile(path=Path(f"/tmp/{name}.mp3"), kind=SourceKind.AUDIO_VIDEO, label=name)


def _slide(name: str) -> SourceFile:
    return SourceFile(path=Path(f"/tmp/{name}.pdf"), kind=SourceKind.PRESENTATION, label=name)


def test_merge_keeps_everything_in_one_group():
    sources = [_audio("a"), _audio("b"), _slide("s")]
    groups = split_sources_for_batch(sources, "merge")
    assert len(groups) == 1
    assert len(groups[0]) == 3


def test_separate_one_group_per_audio():
    sources = [_audio("a"), _audio("b"), _audio("c")]
    groups = split_sources_for_batch(sources, "separate")
    assert len(groups) == 3
    for g in groups:
        assert len(g) == 1
        assert g[0].kind == SourceKind.AUDIO_VIDEO


def test_separate_attaches_slides_to_each():
    sources = [_audio("a"), _audio("b"), _slide("slides")]
    groups = split_sources_for_batch(sources, "separate")
    assert len(groups) == 2  # dvě audia → dva joby
    for g in groups:
        kinds = [s.kind for s in g]
        assert SourceKind.AUDIO_VIDEO in kinds
        assert SourceKind.PRESENTATION in kinds  # slidy přiloženy ke každému
        assert len(g) == 2


def test_separate_with_single_audio_one_job():
    groups = split_sources_for_batch([_audio("a")], "separate")
    assert len(groups) == 1
    assert len(groups[0]) == 1


def test_separate_only_slides_no_audio_one_job():
    # Jen prezentace bez audia — nedává smysl dělit
    sources = [_slide("s1"), _slide("s2")]
    groups = split_sources_for_batch(sources, "separate")
    assert len(groups) == 1
    assert len(groups[0]) == 2


def test_empty_returns_empty():
    assert split_sources_for_batch([], "separate") == []
    assert split_sources_for_batch([], "merge") == []


def test_merge_preserves_order():
    sources = [_audio("first"), _audio("second")]
    groups = split_sources_for_batch(sources, "merge")
    assert [s.label for s in groups[0]] == ["first", "second"]
