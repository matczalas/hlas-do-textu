"""Token-aware chunking pomocí tiktoken.

Gemini má vlastní tokenizer, ale tiktoken `cl100k_base` je dost dobrý odhad
(rozdíly <10 %) a vyhneme se závislosti na cloud tokenizer endpointu."""

from __future__ import annotations

from loguru import logger

from app.config import MAP_CHUNK_TOKENS

_ENCODER = None
_ENCODER_FAILED = False


class _FallbackEncoder:
    """Náhrada za tiktoken, když selže (chybějící data v PyInstaller bundle).

    Hrubý odhad ~4 znaky / token. Není přesné, ale chunking dál funguje —
    lepší než shodit celou AI vrstvu. encode() vrací list správné délky,
    takže `len(enc.encode(text))` dá odhad počtu tokenů.
    """

    @staticmethod
    def encode(text: str) -> list[int]:
        return [0] * (max(len(text), 1) // 4 + 1)


def _get_encoder():
    global _ENCODER, _ENCODER_FAILED
    if _ENCODER is not None:
        return _ENCODER
    if _ENCODER_FAILED:
        return _FallbackEncoder()
    try:
        import tiktoken

        _ENCODER = tiktoken.get_encoding("cl100k_base")
    except Exception as exc:  # noqa: BLE001 — tiktoken může selhat v bundlu
        logger.warning(
            "tiktoken nedostupný ({}), používám hrubý odhad tokenů (~4 znaky/token)",
            exc,
        )
        _ENCODER_FAILED = True
        return _FallbackEncoder()
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
        # Pojistka: jediná "věta" delší než target (text bez interpunkce/mezer —
        # slepený OCR, base64, dlouhá URL). Bez hard-splitu by vznikl jeden
        # obří chunk přetékající kontext modelu. Rozsekáme ji natvrdo po znacích.
        if s_tokens > target_tokens:
            if buf:
                out.append(" ".join(buf))
                buf = []
                buf_tokens = 0
            out.extend(_hard_split_by_chars(sent, target_tokens, enc))
            continue
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


def _hard_split_by_chars(text: str, target_tokens: int, enc) -> list[str]:
    """Poslední záchrana: rozseká text podle počtu znaků na kusy pod limitem.

    Odhad znaků na chunk z aktuálního poměru znaky/token daného textu.
    """
    token_count = max(len(enc.encode(text)), 1)
    chars_per_token = max(len(text) // token_count, 1)
    chunk_chars = max(target_tokens * chars_per_token, 1)
    return [text[i : i + chunk_chars] for i in range(0, len(text), chunk_chars)]


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
