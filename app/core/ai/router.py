"""Orchestrace AI volání: chunking + map-reduce + Gemini ↔ Ollama failover."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed

from loguru import logger

from app.config import MAP_REDUCE_THRESHOLD_TOKENS, MAX_PARALLEL_AI_REQUESTS
from app.core.ai.base import (
    AIAuthError,
    AIError,
    AINetworkError,
    AIProvider,
    AIRateLimitError,
)
from app.core.ai.chunker import count_tokens, split_into_chunks
from app.core.ai.prompts import (
    SYSTEM_PROMPT_CS,
    build_map_prompt,
    build_reduce_prompt,
    build_single_shot_prompt,
)
from app.core.models import SlideText, StudyMaterial, Transcript


class AIRouter:
    """Failover chain: zkusí `primary`, při určitých chybách spadne na `fallback`."""

    def __init__(self, primary: AIProvider | None, fallback: AIProvider | None) -> None:
        if primary is None and fallback is None:
            raise ValueError("AIRouter potřebuje aspoň jednoho providera")
        self._primary = primary
        self._fallback = fallback

    def generate_with_failover(self, prompt: str, *, system: str | None = None) -> str:
        last_error: AIError | None = None
        for provider in self._providers():
            try:
                logger.info("AI generate přes '{}'", provider.name)
                return provider.generate(prompt, system=system)
            except AIAuthError as exc:
                # Špatný klíč u primárního → zkusit fallback
                logger.warning("Provider '{}' auth chyba: {}", provider.name, exc)
                last_error = exc
            except AIRateLimitError as exc:
                logger.warning("Provider '{}' rate limit: {}", provider.name, exc)
                last_error = exc
            except AINetworkError as exc:
                logger.warning("Provider '{}' síťová chyba: {}", provider.name, exc)
                last_error = exc
            except AIError as exc:
                logger.error("Provider '{}' selhal: {}", provider.name, exc)
                last_error = exc

        assert last_error is not None
        raise last_error

    def _providers(self) -> Iterable[AIProvider]:
        for p in (self._primary, self._fallback):
            if p is not None:
                yield p


# ---------------------------------------------------------------------------
# Map-reduce orchestrace nad transkripty + slidy
# ---------------------------------------------------------------------------


def generate_study_material(
    *,
    router: AIRouter,
    transcripts: list[Transcript],
    slides: list[SlideText],
    user_prompt: str,
) -> StudyMaterial:
    """Spustí adaptivní map-reduce → vrátí StudyMaterial."""
    if not transcripts and not slides:
        raise ValueError("Nejsou k dispozici žádné zdroje")

    full_transcript_text = _combine_transcripts(transcripts)
    slides_text = _combine_slides(slides)

    total_tokens = count_tokens(full_transcript_text) + count_tokens(slides_text)
    logger.info("Celkové vstupní tokeny: ~{}", total_tokens)

    # Rozhodnutí single-shot vs map-reduce musí počítat CELKOVÝ vstup
    # (přepis + slidy). Dřív se koukalo jen na přepis — velký transcript pod
    # thresholdem + obří prezentace pak přetekly kontext modelu v single-shotu.
    if total_tokens <= MAP_REDUCE_THRESHOLD_TOKENS:
        logger.info("Single-shot strategie (pod thresholdem)")
        prompt = build_single_shot_prompt(user_prompt, full_transcript_text, slides_text)
        raw = router.generate_with_failover(prompt, system=SYSTEM_PROMPT_CS)
    else:
        logger.info("Map-reduce strategie (nad thresholdem)")
        mapped = _map_phase(router, transcripts)
        prompt = build_reduce_prompt(user_prompt, mapped, slides_text)
        raw = router.generate_with_failover(prompt, system=SYSTEM_PROMPT_CS)

    return _parse_study_material(raw)


def _map_phase(router: AIRouter, transcripts: list[Transcript]) -> str:
    """Vrátí konsolidovaný textový souhrn map fáze (pro vstup do reduce)."""
    tasks: list[tuple[str, str]] = []  # (label, chunk)
    for tr in transcripts:
        chunks = split_into_chunks(tr.text)
        for chunk in chunks:
            tasks.append((tr.source_label, chunk))

    logger.info("Map fáze: {} chunků", len(tasks))

    results: list[str] = [""] * len(tasks)

    def _run(idx: int, label: str, chunk: str) -> tuple[int, str]:
        prompt = build_map_prompt(chunk, label)
        try:
            raw = router.generate_with_failover(prompt, system=SYSTEM_PROMPT_CS)
            parsed = _safe_parse_json(raw) or {}
            bullets = parsed.get("bullets") or []
            terms = parsed.get("terms") or []
            examples = parsed.get("examples") or []
            block = [f"### {label} (chunk {idx + 1})"]
            if bullets:
                block.append("Body: " + "; ".join(str(b) for b in bullets))
            if terms:
                block.append("Pojmy: " + "; ".join(f"{t[0]} – {t[1]}" if isinstance(t, list) and len(t) == 2 else str(t) for t in terms))
            if examples:
                block.append("Příklady: " + "; ".join(str(e) for e in examples))
            return idx, "\n".join(block)
        except AIError as exc:
            logger.error("Map chunk {} ({}) selhal: {}", idx, label, exc)
            return idx, f"### {label} (chunk {idx + 1})\n[chyba: {exc}]"

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_AI_REQUESTS) as ex:
        futures = [ex.submit(_run, i, label, chunk) for i, (label, chunk) in enumerate(tasks)]
        for fut in as_completed(futures):
            idx, block = fut.result()
            results[idx] = block

    return "\n\n".join(b for b in results if b)


def _combine_transcripts(transcripts: list[Transcript]) -> str:
    parts: list[str] = []
    for tr in transcripts:
        parts.append(f"=== [{tr.source_label}] ===\n{tr.text}")
    return "\n\n".join(parts)


def _combine_slides(slides: list[SlideText]) -> str:
    parts: list[str] = []
    for sl in slides:
        if not sl.text:
            continue
        parts.append(f"=== [{sl.source_label}] ===\n{sl.text}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# JSON parser tolerantní k Markdown wrapperům a komentářům modelu
# ---------------------------------------------------------------------------


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL)


def _safe_parse_json(raw: str) -> dict | None:
    if not raw:
        return None
    candidate = raw.strip()
    fence = _JSON_FENCE.search(candidate)
    if fence:
        candidate = fence.group(1).strip()
    # Některé modely občas přidají úvodní text — najdi první {
    first_brace = candidate.find("{")
    last_brace = candidate.rfind("}")
    if first_brace == -1 or last_brace == -1 or last_brace < first_brace:
        return None
    candidate = candidate[first_brace : last_brace + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        logger.warning("JSON parse failed: {}; raw[:200]={!r}", exc, candidate[:200])
        return None


def _parse_study_material(raw: str) -> StudyMaterial:
    data = _safe_parse_json(raw)
    if data is None:
        # poslední záchrana: dej celý text jako bullet
        return StudyMaterial(
            title="Studijní materiál (nestrukturovaný)",
            bullets=[raw.strip()[:1000]],
        )

    title = str(data.get("title") or "Studijní materiál").strip()
    topic = str(data.get("topic") or "").strip()
    bullets = [str(b).strip() for b in (data.get("bullets") or []) if str(b).strip()]
    examples = [str(e).strip() for e in (data.get("examples") or []) if str(e).strip()]
    further = [str(f).strip() for f in (data.get("further_study") or []) if str(f).strip()]
    terms: list[tuple[str, str]] = []
    for item in data.get("terms") or []:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            term, definition = str(item[0]).strip(), str(item[1]).strip()
            if term:
                terms.append((term, definition))
        elif isinstance(item, dict):
            term = str(item.get("term") or item.get("pojem") or "").strip()
            definition = str(item.get("definition") or item.get("definice") or "").strip()
            if term:
                terms.append((term, definition))

    # Pojistka: AI vrátila validní JSON, ale všechna pole prázdná → výsledný
    # .docx by byl prázdný a uživatel by nevěděl proč. Vložíme aspoň
    # informativní bod, ať je zřejmé, že AI nic nevytěžila.
    if not bullets and not terms and not examples and not further:
        logger.warning("AI vrátila prázdný StudyMaterial (raw: {}…)", raw.strip()[:160])
        bullets = [
            "AI z přepisu nevytěžila strukturované body. Zkus to znovu, "
            "uprav popis zadání, nebo použij chat o dokumentu."
        ]

    return StudyMaterial(
        title=title,
        bullets=bullets,
        terms=terms,
        examples=examples,
        further_study=further,
        topic=topic,
    )
