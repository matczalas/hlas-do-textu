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

FACTS_SALES: list[tuple[str, str]] = [
    (
        "Behaviorální finance",
        "Lidé preferují jistou ztrátu před nejistým ziskem stejné velikosti — "
        "averze ke ztrátě. Promítá se do volby konzervativních produktů. "
        "(Kahneman & Tversky, 1979)",
    ),
    (
        "Psychologie klienta",
        "Klient, který sám popíše svou situaci, si lépe pamatuje doporučení. "
        "Říká se tomu „efekt vlastní produkce“ — necháš ho mluvit, drží mu to "
        "lépe v hlavě.",
    ),
    (
        "Studie",
        "85 % schůzek, kde poradce mluví víc než 60 % času, končí bez prodeje. "
        "(Gong.io research, 2019)",
    ),
    (
        "Efekt ukotvení",
        "První číslo na schůzce ovlivňuje všechny další úvahy. Když dáš příklad "
        "300 000 Kč horizont, klient pak hodnotí každou alternativu vůči téhle "
        "kotvě. (Tversky & Kahneman)",
    ),
    (
        "Praktický tip",
        "Otázka „Co tě motivuje“ vrátí floskule. Otázka „Jak bys poznal, že "
        "už to máš vyřešené?“ vrátí konkrétní cíl, na který se dá navázat.",
    ),
    (
        "Compliance",
        "ZČOP §117c (KYC): u nového klienta musíš zaznamenat investiční profil "
        "a poznat jeho zkušenosti a cíle ještě před nabídkou produktu. Tahle "
        "appka ti to z přepisu vytáhne automaticky.",
    ),
    (
        "Sales lore",
        "„Lidi nekupují produkty, kupují příběh proč to potřebují.“ — Když "
        "klient v zápisu mluví víc o budoucnosti než o cifrách, jdeš správně.",
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
    """Vrátí seznam faktů pro danou roli ("student" / "teacher" / "sales")."""
    if role == "teacher":
        return FACTS_TEACHER
    if role == "sales":
        return FACTS_SALES
    return FACTS_STUDENT
