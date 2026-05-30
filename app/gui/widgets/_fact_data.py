"""Kurátorská sada faktů "Než to doběhne" pro FactCard widget.

Source: design_handoff_hlasdotextu/prototype/hdt/running.jsx ř. 8-26.

Student → triviálky + vtipy o VŠ + tipy ke zkoušení (light tone).
Teacher → studie z behaviorální ekonomie a pedagogiky (vědecký tone).

Každý fakt = (category, text). Kategorie se zobrazuje jako uppercase pill,
text je jádro.
"""

from __future__ import annotations

FACTS_STUDENT: list[tuple[str, str]] = [
    (
        "Vtip · Vysoká škola",
        "Kolik vysokoškoláků je potřeba na výměnu žárovky? "
        "Jeden — ale dostane za to 6 kreditů a musí o tom napsat seminárku.",
    ),
    (
        "Věda o učení",
        "Studenti, kteří si píšou poznámky rukou, si látku pamatují líp "
        "než ti na notebooku. (Mueller & Oppenheimer, 2014)",
    ),
    (
        "Vtip · Deadline",
        "Deadline je nejmocnější zdroj energie ve vesmíru. "
        "Vědci ho zatím neumí bezpečně zkrotit.",
    ),
    (
        "Zajímavost",
        "Univerzita Karlova byla založena roku 1348 — je tak o zhruba "
        "400 let starší než brambory v Čechách.",
    ),
    (
        "Tip ke zkoušce",
        "Krátký kvíz hned po přednášce zlepší zapamatování víc než "
        "dvojí přečtení skript.",
    ),
    (
        "Vtip · Menza",
        "Záhada moderní vědy: proč je v pátek v menze kratší fronta "
        "než motivace učit se?",
    ),
    (
        "Zajímavost",
        "Průměrný řečník řekne „eee“ asi pětkrát za minutu. "
        "Whisper je přepíše všechny — i ty tvoje.",
    ),
]

FACTS_TEACHER: list[tuple[str, str]] = [
    (
        "Behaviorální ekonomie",
        "Testing effect: samotné zkoušení učí víc než opakované čtení. "
        "Krátký test po hodině zvedá výsledky u závěrečné písemky. "
        "(Roediger & Karpicke, 2006)",
    ),
    (
        "Studie",
        "Rozložené opakování (spaced repetition) zvyšuje dlouhodobé "
        "zapamatování o desítky procent oproti učení nárazem. "
        "(Cepeda et al., 2006)",
    ),
    (
        "Kognitivní zkreslení",
        "Dunningův–Krugerův efekt: nejméně zdatní svou úroveň přeceňují "
        "nejvíc. Pravidelná konkrétní zpětná vazba to zmírňuje.",
    ),
    (
        "Behaviorální ekonomie",
        "Efekt ukotvení: první číslo, které žák uslyší, ovlivní i jeho "
        "odhady u nesouvisejících otázek. (Tversky & Kahneman, 1974)",
    ),
    (
        "Průzkum",
        "Averze ke ztrátě: ztráta bolí zhruba dvakrát víc, než stejně "
        "velký zisk potěší. Promítá se i do motivace u známkování. "
        "(Kahneman & Tversky, 1979)",
    ),
    (
        "Pedagogika",
        "Goodhartův zákon: jakmile se ukazatel stane cílem, přestává být "
        "dobrým ukazatelem. Pozor na „učení na test“.",
    ),
]


def facts_for_role(role: str) -> list[tuple[str, str]]:
    """Vrátí seznam faktů pro danou roli ("student" / "teacher")."""
    if role == "teacher":
        return FACTS_TEACHER
    return FACTS_STUDENT
