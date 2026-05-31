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
  "topic": "obor/předmět jedním až dvěma slovy (např. Fyzika, Dějepis, Marketing) — pro zařazení do složky",
  "title": "stručný název materiálu (max 80 znaků)",
  "bullets": ["hlavní bod k zapamatování (max 30 bodů, prioritní pro zkoušku)"],
  "terms": [["pojem", "definice s kontextem"]],
  "examples": ["konkrétní příklad/případ z přednášky"],
  "further_study": ["doporučení k dalšímu studiu — pojmy k rozšíření, otázky k zamyšlení"],
  "quiz_questions": ["otázka k procvičení nebo ke zkoušení (5-10 otázek různé obtížnosti, ověřují pochopení látky)"]
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
  "topic": "obor/předmět jedním až dvěma slovy (např. Fyzika, Dějepis, Marketing) — pro zařazení do složky",
  "title": "stručný název materiálu (max 80 znaků)",
  "bullets": ["hlavní bod k zapamatování (max 30 bodů, prioritní pro zkoušku)"],
  "terms": [["pojem", "definice s kontextem"]],
  "examples": ["konkrétní příklad/případ z přednášky"],
  "further_study": ["doporučení k dalšímu studiu — pojmy k rozšíření, otázky k zamyšlení"],
  "quiz_questions": ["otázka k procvičení nebo ke zkoušení (5-10 otázek různé obtížnosti, ověřují pochopení látky)"]
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


# ---------------------------------------------------------------------------
# Šablony zadání (předvyplní pole "popis pro AI") — uživatel vybere v UI
# podle toho, co potřebuje vyrobit. `key` se ukládá, `label` se zobrazí,
# `prompt` se vloží do editoru (uživatel může dál upravit).
# ---------------------------------------------------------------------------

PROMPT_TEMPLATES: dict[str, dict[str, str]] = {
    "student": {
        "label": "Studijní materiál pro studenta",
        "prompt": (
            "Jsem student a tohle je záznam přednášky. Vytvoř přehledný studijní "
            "materiál k učení na zkoušku — hlavní body, klíčové pojmy s definicemi, "
            "příklady a otázky k procvičení."
        ),
    },
    "teacher_lesson": {
        "label": "Záznam hodiny pro učitele (poznámky + otázky ke zkoušení)",
        "prompt": (
            "Jsem učitel/ka základní školy a tohle je nahrávka mé vyučovací hodiny. "
            "Vytvoř z ní:\n"
            "1) Přehledné POZNÁMKY co se v hodině probíralo — srozumitelně, bod po bodu, "
            "v pořadí jak látka šla, vhodné jako zápis do třídní knihy nebo pro "
            "nepřítomné žáky.\n"
            "2) Klíčové pojmy a jejich vysvětlení tak, jak byly v hodině podány.\n"
            "3) OTÁZKY KE ZKOUŠENÍ ŽÁKŮ (quiz_questions) — 8-10 otázek různé obtížnosti, "
            "ze kterých můžu žáky ústně nebo písemně vyzkoušet. Od jednoduchých "
            "(zapamatování) po složitější (pochopení a aplikace). Otázky piš jasně, "
            "přiměřeně věku žáků ZŠ."
        ),
    },
    "quiz": {
        "label": "Hlavně otázky k procvičení",
        "prompt": (
            "Z tohoto záznamu vytvoř hlavně sadu otázek k procvičení a ověření "
            "pochopení látky (quiz_questions) — co nejvíc, různé obtížnosti. "
            "Plus stručný přehled probraných bodů."
        ),
    },
    "summary": {
        "label": "Krátké shrnutí (1 strana)",
        "prompt": (
            "Vytvoř stručné shrnutí tohoto záznamu — jen ty nejdůležitější body, "
            "tak aby se vešly na jednu stranu A4. Žádná vata."
        ),
    },
    # --- Učitelské akce (redesign — 3 akční karty) ---
    "teacher_questions_oral": {
        "label": "Otázky vhodné k testu — ústní",
        "prompt": (
            "Z této nahrávky hodiny vytvoř sadu otázek k ÚSTNÍMU ZKOUŠENÍ žáků "
            "(quiz_questions). 8–10 otázek různé obtížnosti — od zapamatování po "
            "pochopení a aplikaci. Krátké, jasné, přiměřené věku žáků ZŠ. "
            "Vhodné pro ústní formu (žák odpovídá souvisle vlastními slovy)."
        ),
    },
    "teacher_questions_written": {
        "label": "Otázky vhodné k testu — písemka",
        "prompt": (
            "Z této nahrávky hodiny vytvoř sadu otázek do PÍSEMNÉ PRÁCE pro žáky "
            "(quiz_questions). 8–10 otázek různé obtížnosti, formulované tak, aby "
            "žák odpověděl 1–3 větami. Připoj i krátkou variantu řešení pro "
            "učitele (jako poznámku v závorce)."
        ),
    },
    "teacher_questions_practice": {
        "label": "Otázky vhodné k testu — procvičování",
        "prompt": (
            "Z této nahrávky hodiny vytvoř sadu otázek k PROCVIČOVÁNÍ doma "
            "(quiz_questions). 10–15 kratších otázek, gradované od jednodušších "
            "k složitějším. Smyslem je opakovat látku, ne hodnotit."
        ),
    },
    "teacher_materials": {
        "label": "Materiály k zaslání pro studenty",
        "prompt": (
            "Z této nahrávky hodiny připrav STUDIJNÍ MATERIÁL pro žáky "
            "(přehledné poznámky + klíčové pojmy s definicemi). Formát: Word/PDF "
            "ke stažení — vhodné pro nepřítomné žáky nebo opakování doma. "
            "Strukturuj v pořadí, jak látka v hodině šla."
        ),
    },
    "teacher_reflection": {
        "label": "Reflexe hodiny — zpětná vazba na projev",
        "prompt": (
            "Tohle je nahrávka mé vyučovací hodiny. Dej mi UPŘÍMNOU ZPĚTNOU VAZBU "
            "k mému učitelskému projevu, ne k obsahu látky: tempo řeči, výplňová "
            "slova, srozumitelnost, dynamika, délka monologů vs. interakce se "
            "žáky. Konkrétní příklady z hodiny, ne obecné rady. Co fungovalo, "
            "co příště zkusit jinak."
        ),
    },
}


def template_prompt(key: str) -> str:
    """Vrátí předvyplněný text zadání pro danou šablonu (nebo prázdný řetězec)."""
    return PROMPT_TEMPLATES.get(key, {}).get("prompt", "")


def templates_for_role(role: str) -> dict[str, dict[str, str]]:
    """Vrátí jen šablony relevantní pro danou roli aplikace.

    - "student": šablony bez prefixu "teacher_" — studijní materiály,
      otázky k procvičení, shrnutí. (Student nevyužije "Reflexe hodiny"
      nebo "Materiály k zaslání pro studenty" — to jsou učitelské akce.)
    - "teacher": všechny šablony včetně teacher_* (učitel je v editoru
      sice vidí přes akční karty, ale prompt_editor je v učitelském
      režimu skrytý; vrátit všechno je tu defenzivní default).
    """
    if role == "teacher":
        return PROMPT_TEMPLATES
    return {
        k: v for k, v in PROMPT_TEMPLATES.items() if not k.startswith("teacher_")
    }
