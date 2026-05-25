"""Testy pro tiktoken-based chunker."""

from __future__ import annotations

from app.core.ai.chunker import count_tokens, split_into_chunks


def test_count_tokens_basic():
    assert count_tokens("") == 0
    assert count_tokens("ahoj světe") > 0


def test_short_text_returns_single_chunk():
    text = "Krátký text bez potřeby rozdělení."
    chunks = split_into_chunks(text, target_tokens=1000)
    assert chunks == [text]


def test_long_text_splits_by_paragraphs():
    paragraphs = ["Odstavec " + str(i) + ": " + ("slovo " * 200) for i in range(10)]
    text = "\n\n".join(paragraphs)
    chunks = split_into_chunks(text, target_tokens=500)
    assert len(chunks) > 1
    # Žádný chunk by neměl být extrémně přes target
    for chunk in chunks:
        assert count_tokens(chunk) <= 1200  # tolerance pro neoddělitelné odstavce


def test_empty_paragraphs_skipped():
    text = "\n\n\n\nNěco\n\n\n\n"
    chunks = split_into_chunks(text, target_tokens=100)
    assert chunks == ["Něco"]
