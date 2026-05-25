"""Prompt šablony v češtině pro map (per-chunk) a reduce (finální syntéza) fázi.

Vstupy se škálují, ale šablona zůstává stejná. Output JSON je validován v ai/router.
"""

from __future__ import annotations

SYSTEM_PROMPT_CS = (
    "Jsi asistent pro českou studentku, která potřebuje studijní materiál z přednášky. "
    "Píšeš stručně, přesně a v češtině s diakritikou. Nevymýšlej si fakta — drž se zdroje. "
    "Pokud něco není v přepisu jasné, napiš to."
)


MAP_PROMPT_TEMPLATE = """Z následujícího úryvku přepisu přednášky vytáhni:

1. **Body k zapamatování** — krátké, konkrétní (1 věta každý). Max 8 bodů.
2. **Klíčové pojmy** — vždy ve formátu "POJEM – krátká definice z přepisu".
3. **Příklady** — pokud přednášející zmiňuje konkrétní příklady nebo případy.

Vrať validní JSON ve formátu:
```json
{{
  "bullets": ["bod 1", "bod 2"],
  "terms": [["pojem", "definice"], ["pojem", "definice"]],
  "examples": ["příklad 1"]
}}
```

Bez dalšího komentáře. Pokud chunk neobsahuje nic užitečného, vrať prázdné seznamy.

ČÁST PŘEPISU (štítek: "{label}"):
\"\"\"
{chunk}
\"\"\"
"""


REDUCE_PROMPT_TEMPLATE = """Toto je studentka kurzu. Tady je její popis materiálů:

> {user_prompt}

Z následujících zdrojů vytvoř finální studijní materiál pro učení.

═══════════════════════════════════════════════════════════════
PŘEDZPRACOVANÉ BODY Z PŘEPISU (z map fáze):
{mapped_summary}

═══════════════════════════════════════════════════════════════
TEXT Z PREZENTACÍ (slidy):
{slides_text}

═══════════════════════════════════════════════════════════════

Vytvoř strukturovaný výstup ve formě validního JSON:

```json
{{
  "title": "stručný název materiálu (max 80 znaků)",
  "bullets": ["hlavní bod k zapamatování (max 30 bodů, prioritní pro zkoušku)"],
  "terms": [["pojem", "definice s kontextem"]],
  "examples": ["konkrétní příklad/případ z přednášky"],
  "further_study": ["doporučení k dalšímu studiu — pojmy k rozšíření, otázky k zamyšlení"]
}}
```

Pravidla:
- Propoj přepis se slidy (slidy mají často strukturu — používej je pro orientaci).
- Body piš tak, aby z nich studentka mohla rovnou tahat ke zkoušce.
- Definice pojmů piš v jejím kontextu, ne obecně z internetu.
- Bez dalšího textu mimo JSON. JSON musí být validní.
"""


SINGLE_SHOT_PROMPT_TEMPLATE = """Toto je studentka kurzu. Tady je její popis materiálů:

> {user_prompt}

Z následujícího přepisu přednášky a obsahu prezentací vytvoř finální studijní materiál.

═══════════════════════════════════════════════════════════════
PŘEPIS PŘEDNÁŠKY:
{transcript}

═══════════════════════════════════════════════════════════════
TEXT Z PREZENTACÍ (slidy):
{slides_text}

═══════════════════════════════════════════════════════════════

Vytvoř strukturovaný výstup ve formě validního JSON:

```json
{{
  "title": "stručný název materiálu (max 80 znaků)",
  "bullets": ["hlavní bod k zapamatování (max 30 bodů, prioritní pro zkoušku)"],
  "terms": [["pojem", "definice s kontextem"]],
  "examples": ["konkrétní příklad/případ z přednášky"],
  "further_study": ["doporučení k dalšímu studiu — pojmy k rozšíření, otázky k zamyšlení"]
}}
```

Pravidla:
- Propoj přepis se slidy (slidy mají často strukturu — používej je pro orientaci).
- Body piš tak, aby z nich studentka mohla rovnou tahat ke zkoušce.
- Definice pojmů piš v jejím kontextu, ne obecně z internetu.
- Bez dalšího textu mimo JSON. JSON musí být validní.
"""


def build_map_prompt(chunk: str, label: str) -> str:
    return MAP_PROMPT_TEMPLATE.format(chunk=chunk, label=label)


def build_reduce_prompt(user_prompt: str, mapped_summary: str, slides_text: str) -> str:
    return REDUCE_PROMPT_TEMPLATE.format(
        user_prompt=user_prompt or "(uživatel nezadal popis)",
        mapped_summary=mapped_summary or "(žádné body)",
        slides_text=slides_text or "(žádné slidy)",
    )


def build_single_shot_prompt(user_prompt: str, transcript: str, slides_text: str) -> str:
    return SINGLE_SHOT_PROMPT_TEMPLATE.format(
        user_prompt=user_prompt or "(uživatel nezadal popis)",
        transcript=transcript,
        slides_text=slides_text or "(žádné slidy)",
    )
