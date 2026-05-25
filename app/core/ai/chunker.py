"""Token-aware chunking pomocí tiktoken.

Gemini má vlastní tokenizer, ale tiktoken `cl100k_base` je dost dobrý odhad
(rozdíly <10 %) a vyhneme se závislosti na cloud tokenizer endpointu."""

from __future__ import annotations

from app.config import MAP_CHUNK_TOKENS

_ENCODER = None


def _get_encoder():
    global _ENCODER
    if _ENCODER is None:
        import tiktoken

        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return _ENCODER


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_get_encoder().encode(text))


def split_into_chunks(text: str, target_tokens: int = MAP_CHUNK_TOKENS) -> list[str]:
    """Rozdělí `text` na chunky ~target_tokens.

    Snaží se nesekat věty: nejprve podle dvojitých newlines, pak podle teček.
    Trimuje whitespace na obou koncích jednotlivých chunků.
    """
    stripped = text.strip()
    if not stripped:
        return []
    if count_tokens(stripped) <= target_tokens:
        return [stripped]

    enc = _get_encoder()
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = len(enc.encode(para))
        if para_tokens > target_tokens:
            # paragraf sám je moc velký — split podle vět
            for sentence_chunk in _split_long_paragraph(para, target_tokens, enc):
                _maybe_flush(chunks, current, current_tokens, target_tokens)
                chunks.append(sentence_chunk)
            current = []
            current_tokens = 0
            continue

        if current_tokens + para_tokens > target_tokens and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_tokens = para_tokens
        else:
            current.append(para)
            current_tokens += para_tokens

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _split_long_paragraph(para: str, target_tokens: int, enc) -> list[str]:
    sentences = _split_sentences(para)
    out: list[str] = []
    buf: list[str] = []
    buf_tokens = 0
    for sent in sentences:
        s_tokens = len(enc.encode(sent))
        if buf_tokens + s_tokens > target_tokens and buf:
            out.append(" ".join(buf))
            buf = [sent]
            buf_tokens = s_tokens
        else:
            buf.append(sent)
            buf_tokens += s_tokens
    if buf:
        out.append(" ".join(buf))
    return out


def _split_sentences(text: str) -> list[str]:
    """Lehký větný splitter (čeština/angličtina). Neimplementuje pravou NLP segmentaci."""
    out: list[str] = []
    current: list[str] = []
    for token in text.replace("\n", " ").split(" "):
        if not token:
            continue
        current.append(token)
        if token.endswith((".", "!", "?")) and len(current) > 2:
            out.append(" ".join(current))
            current = []
    if current:
        out.append(" ".join(current))
    return out


def _maybe_flush(chunks: list[str], current: list[str], current_tokens: int, target_tokens: int) -> None:
    if current:
        chunks.append("\n\n".join(current))
