"""Sdílený parser AI výstupu — tolerantní převod JSON dictu na StudySection / StudyMaterial.

Modely vrací sekce v různých drobných variacích (klíče česky/anglicky, items
jako list of dictů místo párů, …). Tady to zarovnáváme do předvídatelné
struktury, kterou používá `router.generate_study_material` i `chat.ChatSession`.
"""

from __future__ import annotations

from app.core.models import (
    SECTION_KIND_BULLETS,
    SECTION_KIND_DEFINITIONS,
    SECTION_KIND_KEY_VALUE,
    SECTION_KIND_PARAGRAPH,
    SECTION_KIND_QA,
    StudyMaterial,
    StudySection,
)

_PAIR_KINDS = frozenset(
    {SECTION_KIND_DEFINITIONS, SECTION_KIND_QA, SECTION_KIND_KEY_VALUE}
)


def parse_sections(raw_sections: list) -> list[StudySection]:
    """Tolerantní převod list-of-dictů na list[StudySection].

    Pro neznámý `kind` spadne na bullets (StudySection.__post_init__).
    Pro `items` se snaží zachránit i nestandardní tvary.
    """
    out: list[StudySection] = []
    for entry in raw_sections:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip() or "(bez nadpisu)"
        kind = str(entry.get("kind") or SECTION_KIND_BULLETS).strip().lower()
        raw_items = entry.get("items") or []
        if not isinstance(raw_items, list):
            raw_items = [raw_items]

        items: list = []
        if kind in _PAIR_KINDS:
            for it in raw_items:
                pair = coerce_pair(it, kind)
                if pair is not None:
                    items.append(pair)
        else:
            for it in raw_items:
                text = coerce_text(it)
                if text:
                    items.append(text)

        out.append(StudySection(title=title, kind=kind, items=items))

    return out


def coerce_text(value) -> str:
    """Vytáhne text z položky bullets/paragraph: str / dict / číslo / None."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("text", "content", "value", "item"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return " — ".join(str(v).strip() for v in value.values() if str(v).strip())
    return str(value).strip()


def coerce_pair(value, kind: str) -> tuple[str, str] | None:
    """Vytáhne (key, value) pár pro definitions/qa/key_value sekce."""
    if value is None:
        return None
    if isinstance(value, list | tuple):
        if len(value) == 0:
            return None
        if len(value) == 1:
            text = str(value[0]).strip()
            return (text, "") if text else None
        key = str(value[0]).strip()
        val = str(value[1]).strip()
        if not key and not val:
            return None
        return (key, val)
    if isinstance(value, dict):
        if kind == SECTION_KIND_DEFINITIONS:
            key_keys = ("term", "pojem", "key", "name")
            val_keys = ("definition", "definice", "value", "desc", "text")
        elif kind == SECTION_KIND_QA:
            key_keys = ("question", "otázka", "otazka", "q", "key")
            val_keys = ("answer", "odpověď", "odpoved", "a", "value", "text")
        else:
            key_keys = ("key", "klíč", "klic", "label", "name")
            val_keys = ("value", "hodnota", "val", "text", "answer")

        key = ""
        val = ""
        for k in key_keys:
            cand = value.get(k)
            if isinstance(cand, str) and cand.strip():
                key = cand.strip()
                break
        for k in val_keys:
            cand = value.get(k)
            if cand is None:
                continue
            val = (cand.strip() if isinstance(cand, str) else str(cand).strip())
            if val:
                break
        if not key and not val:
            string_values = [str(v).strip() for v in value.values() if str(v).strip()]
            if len(string_values) >= 2:
                return (string_values[0], string_values[1])
            if len(string_values) == 1:
                return (string_values[0], "")
            return None
        return (key, val) if key else None
    text = str(value).strip()
    return (text, "") if text else None


def populate_legacy_aliases(material: StudyMaterial) -> None:
    """Z `material.sections` naplní legacy pole (`bullets`, `terms`, …).

    Slouží jen zpětně — starý chat parser a starý exportér čtou legacy
    pole. Nový word_export jede přes `iter_sections()`.

    Heuristika:
      - definitions → `terms`
      - qa → `quiz_questions` (jen otázky; vzorové odpovědi se ztratí
        v aliasu, ale `sections` je má — chat/export je vidí tam)
      - key_value → `bullets` ve formátu „klíč: hodnota“ s prefixem titulu
      - bullets / paragraph s titulem obsahujícím „příklad“ → `examples`
      - bullets / paragraph s titulem obsahujícím „další studium“ /
        „doporučení“ → `further_study`
      - ostatní bullets / paragraph → `bullets`
    """
    bullets: list[str] = []
    terms: list[tuple[str, str]] = []
    examples: list[str] = []
    quiz: list[str] = []
    further: list[str] = []

    for section in material.sections:
        title_lower = section.title.lower()
        if section.kind == SECTION_KIND_DEFINITIONS:
            for pair in section.items:
                term, definition = _pair_or_empty(pair)
                if term:
                    terms.append((term, definition))
        elif section.kind == SECTION_KIND_QA:
            for pair in section.items:
                question, _answer = _pair_or_empty(pair)
                if question:
                    quiz.append(question)
        elif section.kind == SECTION_KIND_KEY_VALUE:
            for pair in section.items:
                key, val = _pair_or_empty(pair)
                if key and val:
                    bullets.append(f"{section.title} — {key}: {val}")
                elif key:
                    bullets.append(f"{section.title} — {key}")
        elif section.kind in (SECTION_KIND_BULLETS, SECTION_KIND_PARAGRAPH):
            if "příklad" in title_lower:
                target = examples
            elif "další" in title_lower or "doporučení" in title_lower:
                target = further
            else:
                target = bullets
            for item in section.items:
                text = str(item).strip()
                if text:
                    target.append(text)

    if bullets:
        material.bullets = bullets
    if terms:
        material.terms = terms
    if examples:
        material.examples = examples
    if quiz:
        material.quiz_questions = quiz
    if further:
        material.further_study = further


def _pair_or_empty(value) -> tuple[str, str]:
    """Bezpečné rozbalení (k, v) — pro položky, které prošly parse_sections."""
    if isinstance(value, list | tuple):
        if len(value) == 0:
            return ("", "")
        if len(value) == 1:
            return (str(value[0]).strip(), "")
        return (str(value[0]).strip(), str(value[1]).strip())
    return (str(value).strip(), "")
