"""Prompt šablony v češtině pro map (per-chunk) a reduce (finální syntéza) fázi.

Architektura: každá uživatelská šablona (`student`, `teacher_lesson`, `sales_meeting`, …)
má vlastní seznam sekcí, které AI v outputu vyrobí. Tím odpadá rigidní schéma
"vrať pět polí" — sales schůzka má jiné sekce než hodina chemie.

Output JSON je validován v `app/core/ai/router.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.models import (
    SECTION_KIND_BULLETS,
    SECTION_KIND_DEFINITIONS,
    SECTION_KIND_KEY_VALUE,
    SECTION_KIND_PARAGRAPH,
    SECTION_KIND_QA,
)

SectionKind = Literal[
    "bullets",
    "definitions",
    "qa",
    "key_value",
    "paragraph",
]


SYSTEM_PROMPT_CS = (
    "Jsi pečlivý český asistent pro tvorbu studijních a profesních materiálů "
    "z přepisů (přednášky, hodiny, schůzky). Píšeš česky s diakritikou, "
    "konkrétně a věcně.\n\n"
    "ZÁKLADNÍ PRAVIDLA:\n"
    "1) Drž se výhradně zdrojového přepisu a slidů. Nic si nevymýšlej.\n"
    "2) Buď konkrétní: cituj jména, čísla, data, termíny, příklady ze zdroje. "
    "Vyhýbej se obecným frázím („je důležité dobře se učit“) a vatě.\n"
    "3) Když data v přepisu chybí, napiš „neuvedeno“ — neimprovizuj.\n"
    "4) Výstup je VŽDY validní JSON ve formátu, který ti instrukce v promptu "
    "popíše. Žádný text mimo JSON, žádné poznámky modelu k sobě samému.\n"
    "5) Český jazyk, diakritika, plné věty u definic a otázek.\n"
    "6) MLUVČÍ: pokud přepis obsahuje označení mluvčích („Mluvčí 1“, „Mluvčí 2“…) "
    "a z kontextu spolehlivě poznáš, kdo to je — podle role (poradce, učitel, "
    "klient, žák) nebo podle jména, které v hovoru zaznělo (např. se představí "
    "nebo ho někdo osloví) — používej ve výstupu toto rozpoznané označení "
    "(např. „Poradce“, „Klient Novák“). Když si jistý nejsi, ponech „Mluvčí N“. "
    "Jména si NIKDY nevymýšlej — použij jen ta, která v nahrávce skutečně padla."
)


# Samostatný system prompt pro brainstorming/reflexi: na rozdíl od ostatních
# šablon AI ZÁMĚRNĚ smí mít vlastní názor, kritizovat a navrhovat nové věci.
# Pořád ale nesmí vymýšlet smyšlená fakta o lidech/firmě — jen myšlenky a názory.
SYSTEM_PROMPT_BRAINSTORM_CS = (
    "Jsi zkušený, kriticky uvažující poradce (strategie, obsah, byznys). "
    "Posloucháš záznam brainstormingu / pracovní debaty a tvým úkolem je dát "
    "UPŘÍMNOU, věcnou zpětnou vazbu — ne jen přepsat, co padlo.\n\n"
    "PRAVIDLA:\n"
    "1) Jasně odděluj DVĚ věci: (a) co skutečně v nahrávce zaznělo, (b) tvůj "
    "vlastní názor a návrhy. Svůj vstup uvozuj formulacemi „Myslím, že…“, "
    "„Doporučuji…“, „Riziko:…“, „Zvážil bych…“. Nevydávej vlastní nápady za to, "
    "co řekli účastníci.\n"
    "2) Buď konkrétní a upřímný. Když je nápad slabý, riskantní nebo nedotažený, "
    "řekni to — slušně, ale bez vaty. Nelichoť, nechval plané. Tvoje hodnota je "
    "v poctivém pohledu, ne v potvrzování.\n"
    "3) U efektivity schůzky buď přímý: jestli debata odbíhala od tématu, neměla "
    "závěr, opakovala se nebo trvala dýl, než musela — napiš to a navrhni, jak "
    "příště líp.\n"
    "4) Nevymýšlej si fakta o lidech, firmě ani číslech, která v nahrávce "
    "nezazněla. Vlastní NÁPADY a NÁZORY ano; smyšlené SKUTEČNOSTI ne.\n"
    "5) Výstup je VŽDY validní JSON ve formátu z promptu. Česky, s diakritikou.\n"
    "6) Pokud přepis rozlišuje mluvčí (Mluvčí 1/2…) a poznáš z kontextu, kdo to "
    "je, klidně to využij („Mluvčí 1 navrhl…“). Jména si nevymýšlej."
)


# Šablony s vlastním system promptem (jinak se použije SYSTEM_PROMPT_CS).
_SYSTEM_PROMPT_OVERRIDES: dict[str, str] = {
    "brainstorm": SYSTEM_PROMPT_BRAINSTORM_CS,
}


def system_prompt_for_template(template_key: str) -> str:
    """Vrátí system prompt pro danou šablonu.

    Většina šablon používá faithful `SYSTEM_PROMPT_CS` (drž se přepisu,
    nevymýšlej si). Brainstorming má vlastní, který AI dovoluje názor a kritiku.
    """
    return _SYSTEM_PROMPT_OVERRIDES.get(template_key, SYSTEM_PROMPT_CS)


# ---------------------------------------------------------------------------
# Schéma sekcí pro každou šablonu
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SectionSpec:
    """Jedna sekce v očekávaném výstupu AI.

    `kind` musí odpovídat hodnotám SECTION_KIND_* v `models.py`.
    `instruction` je instrukce AI, co konkrétně do sekce dát (v češtině).
    `target_count` je textový hint na množství („8-12“, „1-3 odstavce“, …).
    """

    title: str
    kind: str
    instruction: str
    target_count: str = ""

    @property
    def items_hint(self) -> str:
        """Lidsky čitelný popis tvaru `items` pro JSON skeleton."""
        if self.kind == SECTION_KIND_DEFINITIONS:
            return '[["pojem", "definice z přepisu"], ...]'
        if self.kind == SECTION_KIND_QA:
            return '[["otázka", "vzorová odpověď nebo prázdný řetězec"], ...]'
        if self.kind == SECTION_KIND_KEY_VALUE:
            return '[["klíč", "hodnota"], ...]'
        # bullets, paragraph
        return '["řádek 1", "řádek 2", ...]'


# Sekce sdílené napříč studentskými šablonami
_STUDENT_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Stručné shrnutí",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "1-2 odstavce, které řeknou, o čem přednáška celkově byla a "
            "jaká byla její hlavní linka. Konkrétně — žádné fráze."
        ),
        target_count="1-2 odstavce",
    ),
    SectionSpec(
        title="Hlavní body k zapamatování",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Konkrétní, samostatně srozumitelné body, ze kterých může student "
            "tahat ke zkoušce. Každý bod = 1 věta s konkrétním obsahem "
            "(definice, vztah, číselný údaj, příklad). Vyber to NEJDŮLEŽITĚJŠÍ "
            "z přednášky — věci, které přednášející zdůraznil, opakoval, nebo "
            "ke kterým uváděl konkrétní příklady. Vyhni se obecným tezím."
        ),
        target_count="15-25 bodů",
    ),
    SectionSpec(
        title="Klíčové pojmy",
        kind=SECTION_KIND_DEFINITIONS,
        instruction=(
            "Pojem = krátký termín (jedno slovo nebo krátké slovní spojení). "
            "Definice = jak ji přednášející podal, ne obecná wikipediová formulace. "
            "Pokud byl pojem zmíněn jen letmo bez vysvětlení, vynech ho."
        ),
        target_count="5-15 pojmů",
    ),
    SectionSpec(
        title="Příklady a případové studie",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Konkrétní příklady, příběhy, čísla, historické případy, experimenty, "
            "které přednášející uvedl pro ilustraci. Cituj je věrně. Pokud žádné "
            "nebyly, vrať prázdný seznam."
        ),
        target_count="0-10 položek",
    ),
    SectionSpec(
        title="Otázky k procvičení a zkoušení",
        kind=SECTION_KIND_QA,
        instruction=(
            "Otázky různé obtížnosti — od zapamatování po pochopení a aplikaci. "
            "Ke každé otázce přidej krátkou vzorovou odpověď (1-3 věty), "
            "ať si student může sám ověřit, jestli ji ví."
        ),
        target_count="6-10 otázek",
    ),
    SectionSpec(
        title="Doporučení k dalšímu studiu",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Konkrétní pojmy, knihy, autoři, oblasti, na které navázat. "
            "Pokud přednášející sám zmiňoval zdroje, dej je sem. Plus 1-2 "
            "vlastní otázky k zamyšlení, které vychází z probrané látky."
        ),
        target_count="3-7 položek",
    ),
)


_TEACHER_LESSON_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Co jsme v hodině probrali",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Bod po bodu, v pořadí, jak látka v hodině šla. Tak, aby chybějící "
            "žák podle toho pochopil, o čem hodina byla. Konkrétně — žádné "
            "obecné popisy typu „bavili jsme se o XY“."
        ),
        target_count="8-15 bodů",
    ),
    SectionSpec(
        title="Klíčové pojmy a jejich vysvětlení",
        kind=SECTION_KIND_DEFINITIONS,
        instruction=(
            "Pojem a jeho vysvětlení tak, jak ho učitel/ka v hodině podal/a "
            "(přiměřeně věku žáků). Pokud učitelka uvedla příklad k pojmu, "
            "dej ho do definice."
        ),
        target_count="4-12 pojmů",
    ),
    SectionSpec(
        title="Otázky ke zkoušení žáků",
        kind=SECTION_KIND_QA,
        instruction=(
            "8-10 otázek různé obtížnosti — od jednoduchých (zapamatování) po "
            "složitější (pochopení a aplikace). Ke každé krátká vzorová odpověď "
            "v závorce za otázkou (1-2 věty). Otázky jasné, přiměřené věku ZŠ."
        ),
        target_count="8-10 otázek",
    ),
    SectionSpec(
        title="Doporučené aktivity pro opakování",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "2-5 konkrétních aktivit, kterými si žáci mohou látku procvičit doma "
            "(úloha, čtení, shrnutí, kresba schématu, …). Konkrétně."
        ),
        target_count="2-5 položek",
    ),
)


_TEACHER_QUESTIONS_ORAL: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Otázky k ústnímu zkoušení",
        kind=SECTION_KIND_QA,
        instruction=(
            "8-10 otázek různé obtížnosti, formulovaných tak, aby žák odpovídal "
            "souvisle vlastními slovy. Ke každé krátké vodítko / vzorová odpověď "
            "pro učitele (1-2 věty)."
        ),
        target_count="8-10 otázek",
    ),
    SectionSpec(
        title="Doporučení k vedení ústní zkoušky",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "2-4 krátké tipy: na co se zaměřit, jaké navazující otázky položit, "
            "kde žáci typicky chybují. Konkrétně k této látce, ne obecné rady."
        ),
        target_count="2-4 položky",
    ),
)


_TEACHER_QUESTIONS_WRITTEN: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Otázky do písemné práce",
        kind=SECTION_KIND_QA,
        instruction=(
            "8-10 otázek do testu / písemky, formulovaných tak, že žák odpoví "
            "1-3 větami. Vzorová odpověď pro učitele jako vodítko k opravě."
        ),
        target_count="8-10 otázek",
    ),
    SectionSpec(
        title="Poznámky pro učitele k hodnocení",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Pár krátkých bodů — co bude pro žáky pravděpodobně nejtěžší, na co "
            "si dát pozor při opravě, jak rozlišit částečně správnou odpověď."
        ),
        target_count="2-4 položky",
    ),
)


_TEACHER_QUESTIONS_PRACTICE: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Otázky k procvičování — snadné",
        kind=SECTION_KIND_QA,
        instruction=(
            "Otázky na zapamatování faktů a základních pojmů. Vzorová odpověď "
            "1 věta. Krátké, žák si je zvládne sám zkontrolovat."
        ),
        target_count="5-7 otázek",
    ),
    SectionSpec(
        title="Otázky k procvičování — střední",
        kind=SECTION_KIND_QA,
        instruction=(
            "Otázky vyžadující pochopení (vlastní vysvětlení, propojení dvou "
            "informací). Vzorová odpověď 1-2 věty."
        ),
        target_count="5-7 otázek",
    ),
    SectionSpec(
        title="Otázky k procvičování — těžší",
        kind=SECTION_KIND_QA,
        instruction=(
            "Otázky vyžadující aplikaci, srovnání, vlastní úvahu. Vzorová odpověď "
            "2-3 věty. Žádné chyták-otázky — cílem je opakování, ne hodnocení."
        ),
        target_count="3-5 otázek",
    ),
)


_TEACHER_MATERIALS_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="O čem byla dnešní hodina",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "1-2 odstavce — souhrnný úvod pro žáka, který v hodině nebyl. "
            "Konkrétně, ne obecně."
        ),
        target_count="1-2 odstavce",
    ),
    SectionSpec(
        title="Hlavní body",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Bod po bodu, v pořadí, jak látka v hodině šla. Každý bod = jedna "
            "myšlenka. Žák podle nich pochopí, co bylo důležité."
        ),
        target_count="8-12 bodů",
    ),
    SectionSpec(
        title="Klíčové pojmy",
        kind=SECTION_KIND_DEFINITIONS,
        instruction=(
            "Pojmy s vysvětlením tak, jak je učitel/ka v hodině podal/a, "
            "přiměřeně věku."
        ),
        target_count="4-10 pojmů",
    ),
    SectionSpec(
        title="Příklady z hodiny",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Konkrétní příklady, příběhy, úlohy, schémata, která v hodině padla. "
            "Pokud žádné, vrať prázdný seznam."
        ),
        target_count="0-6 položek",
    ),
    SectionSpec(
        title="Otázky k opakování",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Krátké otázky pro samostatné opakování doma — bez odpovědí (žák si "
            "má sám ověřit, jestli ví)."
        ),
        target_count="3-6 položek",
    ),
)


_TEACHER_REFLECTION_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Celkový dojem z hodiny",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "1-2 odstavce — co učitel/ka dělal/a dobře, co bylo slabší místo, "
            "jaký byl celkový dojem. Konkrétně — odkazuj na konkrétní momenty "
            "z hodiny, ne obecné dojmy."
        ),
        target_count="1-2 odstavce",
    ),
    SectionSpec(
        title="Tempo a rytmus",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Konkrétní pozorování o tempu řeči, pauzách, přechodech mezi tématy. "
            "Pokud bylo v hodině místo, kde to bylo příliš rychlé / pomalé, řekni "
            "kdy (čas v přepisu nebo téma)."
        ),
        target_count="3-6 bodů",
    ),
    SectionSpec(
        title="Srozumitelnost a struktura",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Jak byla látka strukturovaná, co bylo dobře vysvětlené, kde žáci "
            "pravděpodobně tápali. Konkrétní příklady — žádné obecné rady."
        ),
        target_count="3-6 bodů",
    ),
    SectionSpec(
        title="Interakce se žáky",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Jak učitel/ka pracoval/a s otázkami, zapojením, mlčením žáků. "
            "Délka monologů vs. interakce. Konkrétně z přepisu."
        ),
        target_count="3-6 bodů",
    ),
    SectionSpec(
        title="Výplňová slova a verbální nedostatky",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Konkrétně: která výplňová slova zaznívala („jakoby“, „prostě“, "
            "„ehm“…) a přibližná frekvence. Také opakované obraty, gramatické "
            "vsuvky. Citace z přepisu, ne paušál."
        ),
        target_count="3-6 bodů",
    ),
    SectionSpec(
        title="Co příště zkusit jinak",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "3-5 konkrétních, akčních doporučení — co příště změnit. Každé "
            "doporučení napojené na konkrétní moment z hodiny, ne obecná rada."
        ),
        target_count="3-5 bodů",
    ),
)


_SALES_MEETING_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Úkoly pro mě",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Co MÁM JÁ udělat po této schůzce. Klíč = krátký popis úkolu "
            "(„Připravit srovnání tří fondů“). Hodnota = deadline (datum nebo "
            "„neuvedeno“). Pokud zazněl termín („do pátku“, „do konce týdne“), "
            "uveď ho přesně tak, jak padl."
        ),
        target_count="podle schůzky",
    ),
    SectionSpec(
        title="Úkoly pro klienta",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Co má udělat KLIENT — co má dodat, jaké podklady poslat. "
            "Klíč = úkol, hodnota = deadline (nebo „neuvedeno“)."
        ),
        target_count="podle schůzky",
    ),
    SectionSpec(
        title="Profil klienta — co dnes řekl",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Všechny konkrétní údaje, které klient sdělil. Klíč = oblast "
            "(„Věk“, „Děti“, „Měsíční příjem“, „Hypotéka“, „Cíle“, „Horizont“…), "
            "hodnota = co klient řekl. Když data chybí, daný řádek prostě vynech "
            "— nevypisuj „neuvedeno“ pro každou oblast."
        ),
        target_count="podle schůzky",
    ),
    SectionSpec(
        title="Termín další schůzky",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "1 krátký odstavec: kdy a kde, případně před / po jaké události. "
            "Pokud termín nepadl, napiš jedno: „Termín další schůzky nebyl "
            "dohodnut.“"
        ),
        target_count="1 odstavec",
    ),
    SectionSpec(
        title="Další poznámky",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Cokoli důležitého, co nepatří výše: klientův tón, neformální "
            "postřehy, otázky k vyjasnění u kolegů, signály o rozhodování. "
            "Pokud nic, prázdný seznam."
        ),
        target_count="0-8 položek",
    ),
)


_SALES_ACTIONS_ONLY_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Termín další schůzky",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "1 krátký odstavec, nebo „Termín další schůzky nebyl dohodnut.“"
        ),
        target_count="1 odstavec",
    ),
    SectionSpec(
        title="Úkoly pro mě (poradce)",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Co dělám JÁ. Klíč = úkol, hodnota = deadline (nebo „neuvedeno“)."
        ),
        target_count="podle schůzky",
    ),
    SectionSpec(
        title="Úkoly pro klienta",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Co dělá KLIENT. Klíč = úkol, hodnota = deadline (nebo „neuvedeno“)."
        ),
        target_count="podle schůzky",
    ),
)


_SALES_CLIENT_PROFILE_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Osobní",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Klíče typu: Věk, Rodinný stav, Děti (počet a věk), Zaměstnání, "
            "Lokalita. Jen co skutečně zaznělo."
        ),
        target_count="podle schůzky",
    ),
    SectionSpec(
        title="Finanční situace",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Klíče typu: Měsíční příjem, Roční příjem, Měsíční výdaje, "
            "Hypotéka / úvěry, Úspory, Investice (typ a výše), Pojištění. "
            "Konkrétní čísla, jak klient řekl. Když chybí, vynech řádek."
        ),
        target_count="podle schůzky",
    ),
    SectionSpec(
        title="Životní cíle a horizonty",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Klíč = cíl („Důchod“, „Koupě bytu“, „Vzdělání dětí“…), hodnota = "
            "horizont a forma („za 15 let, hypotéka 3 mil.“). Co klient sám "
            "uvedl, ne odhad."
        ),
        target_count="podle schůzky",
    ),
    SectionSpec(
        title="Postoj k riziku",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "1 odstavec — co klient řekl o své toleranci ke kolísání, "
            "preferenci jistoty vs. výnosu. Pokud nic, „neuvedeno“."
        ),
        target_count="1 odstavec",
    ),
    SectionSpec(
        title="Ostatní",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Současné produkty, vztah s předchozím poradcem, preference "
            "komunikace, kontaktní okno. Volné klíče podle toho, co padlo."
        ),
        target_count="podle schůzky",
    ),
)


_QUIZ_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Stručný přehled tématu",
        kind=SECTION_KIND_PARAGRAPH,
        instruction="1 krátký odstavec, který shrne, o čem se ptáme.",
        target_count="1 odstavec",
    ),
    SectionSpec(
        title="Otázky — snadné",
        kind=SECTION_KIND_QA,
        instruction=(
            "Otázky na zapamatování faktů a pojmů. Vzorová odpověď 1 věta."
        ),
        target_count="4-6 otázek",
    ),
    SectionSpec(
        title="Otázky — střední",
        kind=SECTION_KIND_QA,
        instruction=(
            "Otázky na pochopení a propojení. Vzorová odpověď 1-2 věty."
        ),
        target_count="4-6 otázek",
    ),
    SectionSpec(
        title="Otázky — těžké",
        kind=SECTION_KIND_QA,
        instruction=(
            "Otázky na aplikaci a vlastní úvahu. Vzorová odpověď 2-3 věty."
        ),
        target_count="3-5 otázek",
    ),
)


_SUMMARY_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Krátké shrnutí",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "1 odstavec, 3-5 vět. O čem to bylo, jaký byl hlavní závěr. "
            "Bez vaty, bez obecných frází."
        ),
        target_count="1 odstavec (3-5 vět)",
    ),
    SectionSpec(
        title="Nejdůležitější body",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Jen to skutečně nejdůležitější. Žádné podružnosti. "
            "Pokud něco bylo „důležité“ jen z formy (přednášející řekl "
            "„důležité“), ale obsahově to jsou plytké teze, vynech to."
        ),
        target_count="5-7 bodů",
    ),
)


# ---------------------------------------------------------------------------
# Univerzální + rolově-specifické přídavky (nové šablony)
# ---------------------------------------------------------------------------


_MEETING_MINUTES_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Základní informace",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Klíče typu: Datum (jen pokud zaznělo), Místo, Účastníci (jmenovitě), "
            "Téma / účel schůzky. Když údaj nepadl, vynech řádek."
        ),
        target_count="podle schůzky",
    ),
    SectionSpec(
        title="Probrané body",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "V pořadí, jak šly. Každý bod = 1 srozumitelná věta. "
            "Konkrétně — co padlo, ne jen téma „bavili jsme se o XY“."
        ),
        target_count="5-15 bodů",
    ),
    SectionSpec(
        title="Rozhodnutí",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Co jsme rozhodli, schválili, na čem se shodli. Jen explicitní "
            "rozhodnutí, ne diskuze. Pokud nepadlo žádné, prázdný seznam."
        ),
        target_count="0-8 položek",
    ),
    SectionSpec(
        title="Akce a úkoly",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Klíč = popis úkolu, hodnota = „kdo, do kdy“ (např. „Jana, do 15. 6.“). "
            "Pokud kdo nebo kdy chybí, napiš „neuvedeno“ na to místo."
        ),
        target_count="podle schůzky",
    ),
    SectionSpec(
        title="Termín dalšího setkání",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "1 krátká věta. Pokud nepadl, napiš „Termín nebyl dohodnut.“"
        ),
        target_count="1 věta",
    ),
)


_SALES_FOLLOWUP_EMAIL_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Předmět e-mailu",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "1 řádek — krátký, konkrétní (např. „Shrnutí naší dnešní schůzky a "
            "další kroky“). Žádné fráze typu „Re: schůzka“."
        ),
        target_count="1 řádek",
    ),
    SectionSpec(
        title="Tělo e-mailu",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "Hotový text, který poradce zkopíruje a pošle. Začni oslovením "
            "(„Dobrý den, pane / paní [jméno klienta z přepisu]“), pak 3-5 "
            "odstavců: krátké poděkování za schůzku, shrnutí klíčových bodů, "
            "dohodnuté další kroky s deadliny, případně termín další schůzky. "
            "Závěr slušný a profesionální („S pozdravem, [tvoje jméno]“). "
            "Tón profesionální, vstřícný, ne korporátně tuhý. Žádné výmysly — "
            "drž se toho, co skutečně padlo."
        ),
        target_count="3-5 odstavců",
    ),
    SectionSpec(
        title="Volitelná příloha k zaslání",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Pokud poradce klientovi slíbil poslat dokumenty (smlouva, nabídka, "
            "kalkulace, srovnání), vypiš je sem jako bullet. Když nic, prázdný "
            "seznam."
        ),
        target_count="0-5 položek",
    ),
)


_SALES_OBJECTION_LOG_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Námitky klienta a moje reakce",
        kind=SECTION_KIND_QA,
        instruction=(
            "Klíč = námitka, kterou klient vznesl (jeho slovy nebo přesná "
            "parafráze). Hodnota = jak na ni poradce reagoval. Vypiš všechny "
            "skutečné námitky — i ty, kde reakce nebyla ideální."
        ),
        target_count="podle schůzky (typicky 3-8)",
    ),
    SectionSpec(
        title="Co fungovalo",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Reakce, formulace nebo argumenty, které měly evidentně dobrý efekt "
            "(klient se uklidnil, posunul se dál, souhlasil). Konkrétně — "
            "cituj z přepisu."
        ),
        target_count="2-5 bodů",
    ),
    SectionSpec(
        title="Co příště zkusit jinak",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Reakce, kde se poradce zasekl, opakoval se, nebo nedal jasnou "
            "odpověď. Pro každou navrhni krátkou lepší formulaci."
        ),
        target_count="2-5 bodů",
    ),
    SectionSpec(
        title="Nezodpovězené nebo problematické body",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Otázky / námitky, na které poradce neuměl odpovědět a slíbil "
            "vrátit se k nim. Důležité — tyhle pak musí dořešit. "
            "Pokud žádné, prázdný seznam."
        ),
        target_count="0-5 bodů",
    ),
)


_STUDENT_FLASHCARDS_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Pojmové karty (pojem → definice)",
        kind=SECTION_KIND_DEFINITIONS,
        instruction=(
            "Co nejvíc krátkých dvojic „pojem → definice“. Definice 1 věta, "
            "vlastními slovy z přepisu. Cíl: import do Anki / Quizlet — formát "
            "musí být atomický (jedna karta = jeden pojem)."
        ),
        target_count="10-30 karet",
    ),
    SectionSpec(
        title="Otázkové karty (otázka → odpověď)",
        kind=SECTION_KIND_QA,
        instruction=(
            "Krátké otázky a krátké odpovědi. Žádné dlouhé eseje — karta musí "
            "jít projít za 5 sekund. Otázky pokrývají fakta, vztahy, příčiny, "
            "dáty, jména."
        ),
        target_count="10-30 karet",
    ),
)


_STUDENT_LANGUAGE_VOCAB_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Slovní zásoba",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Klíč = slovo v cizím jazyce (jak padlo v hodině), hodnota = "
            "překlad + ukázková věta v závorce (např. „abstract = abstraktní; "
            "An abstract concept is hard to grasp.“). Cíl: žák se podle toho "
            "naučí slovíčka i kontextové použití."
        ),
        target_count="10-30 položek",
    ),
    SectionSpec(
        title="Gramatika z hodiny",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Gramatické jevy, které učitel vysvětloval (čas, vazba, výjimka). "
            "Každý bod = krátké pravidlo + 1 příklad. Pokud žádná gramatika "
            "nepadla, prázdný seznam."
        ),
        target_count="0-8 položek",
    ),
    SectionSpec(
        title="Užitečné fráze a obraty",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Celé fráze (ne jednotlivá slova) — to, co se hodí v běžné "
            "konverzaci. Vždy s českým překladem v závorce."
        ),
        target_count="3-10 položek",
    ),
)


_TEACHER_PARENT_SUMMARY_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Pozdrav a úvod",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "1 krátký, přívětivý odstavec — oslovení („Vážení rodiče,“) a věta "
            "o tom, co dnes v hodině probíhalo (téma). Tón vlídný, ne formálně "
            "úřednický."
        ),
        target_count="1 odstavec",
    ),
    SectionSpec(
        title="Co jsme dnes probrali",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Bod po bodu, srozumitelně pro rodiče-neodborníky (vyhni se "
            "odbornému žargonu, vysvětli pojmy, pokud jsou jiné než běžně "
            "známé). Konkrétně — co dítě v hodině vidělo a slyšelo."
        ),
        target_count="5-10 bodů",
    ),
    SectionSpec(
        title="Jak reagovali žáci",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "1-2 odstavce — kolektivně, anonymně (žádná jména konkrétních "
            "žáků). Co bylo zajímavé, kde žáci tápali, co je bavilo, jak "
            "se zapojovali."
        ),
        target_count="1-2 odstavce",
    ),
    SectionSpec(
        title="Domácí příprava",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Co dítě má udělat doma (úkol, čtení, opakování). Konkrétně. "
            "Pokud nic, vynech sekci (prázdný seznam)."
        ),
        target_count="0-5 položek",
    ),
    SectionSpec(
        title="Závěr",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "1 krátký odstavec — pozvánka k případným dotazům, kontakt nebo "
            "„s pozdravem“. Vlídně."
        ),
        target_count="1 odstavec",
    ),
)


_TEACHER_NEXT_LESSON_PLAN_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Na čem dnes skončili",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "1 odstavec — kde hodina skončila, co bylo poslední téma. Aby "
            "učitel věděl, kam navázat."
        ),
        target_count="1 odstavec",
    ),
    SectionSpec(
        title="Co opakovat na začátku další hodiny",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Body, kde žáci pravděpodobně tápou nebo které jsou zásadní pro "
            "návaznost. Konkrétně — pojem, vztah, příklad."
        ),
        target_count="3-6 bodů",
    ),
    SectionSpec(
        title="Návrh struktury další hodiny",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Kroky další hodiny v pořadí (např. „1) Krátké opakování. "
            "2) Nová látka — X. 3) Procvičení Y. 4) Shrnutí.“). Časový odhad "
            "v závorce u každého kroku."
        ),
        target_count="4-8 kroků",
    ),
    SectionSpec(
        title="Materiály, které připravit",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Co musí učitel přinést / vytisknout / nachystat (pracovní list, "
            "schéma, video, pomůcka). Konkrétně. Pokud nic, prázdný seznam."
        ),
        target_count="0-6 položek",
    ),
    SectionSpec(
        title="Předpokládané obtíže žáků",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Kde žáci pravděpodobně budou tápat (na základě toho, jak "
            "reagovali v dnešní hodině). Pro každou obtíž krátký tip, jak na "
            "to."
        ),
        target_count="2-4 bodů",
    ),
)


_BRAINSTORM_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="O čem jste se bavili",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "1-2 odstavce — věrné, stručné shrnutí toho, co v debatě padlo a "
            "jaké nápady se řešily. TADY se drž přepisu, žádný vlastní názor."
        ),
        target_count="1-2 odstavce",
    ),
    SectionSpec(
        title="Co si o tom myslím",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Tvůj upřímný názor na probírané nápady. Ke každému hlavnímu nápadu "
            "1 bod: dává smysl? co je na něm dobré, co zajímavé? Začni „Myslím, "
            "že…“ / „Líbí se mi…“. Konkrétně, ne obecné fráze. Tohle je TVŮJ "
            "pohled, ne přepis."
        ),
        target_count="3-6 bodů",
    ),
    SectionSpec(
        title="Kritika a slabá místa",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Co je na nápadech slabé, riskantní, nedotažené nebo co se přehlédlo. "
            "Buď přímý a konkrétní — radši upřímná kritika než zdvořilé nic. "
            "Ke každému bodu krátké zdůvodnění proč."
        ),
        target_count="3-6 bodů",
    ),
    SectionSpec(
        title="Moje návrhy a nové směry",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Konkrétní návrhy: jak nápady vylepšit, co zkusit jinak, jaké nové "
            "nápady nebo směry tě napadají NAD RÁMEC toho, co zaznělo. Označuj "
            "je jako svůj návrh („Doporučuji…“, „Zvážil bych…“)."
        ),
        target_count="4-8 bodů",
    ),
    SectionSpec(
        title="Hodnocení efektivity schůzky",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Upřímné zhodnocení, jak schůzka probíhala: Měla jasný cíl a závěr? "
            "Odbíhalo se od tématu? Opakovaly se věci? Trvala přiměřeně? Padlo "
            "konkrétní rozhodnutí, nebo to vyšumělo? Ke každému postřehu konkrétní "
            "příklad z nahrávky + tip, jak příště líp. Buď přímý — pokud schůzka "
            "efektivní nebyla, jasně to napiš (uživatel to chce vědět)."
        ),
        target_count="3-6 bodů",
    ),
)


_SALES_PHONE_CALL_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Důvod a výsledek hovoru",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "1 krátký odstavec: kdo volal komu, proč, a jak hovor dopadl "
            "(dohoda / odmítnutí / odloženo). Telefonát je krátký — zápis taky."
        ),
        target_count="1 odstavec",
    ),
    SectionSpec(
        title="Co zaznělo",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Klíčové body hovoru v pořadí. Jen podstatné — žádné zdvořilostní "
            "fráze. Čísla, termíny a jména přesně."
        ),
        target_count="3-8 bodů",
    ),
    SectionSpec(
        title="Dohodnuté kroky",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Klíč = úkol, hodnota = kdo + do kdy (nebo „neuvedeno“). "
            "Včetně slibů typu „pošlu vám e-mail s podklady“."
        ),
        target_count="podle hovoru",
    ),
    SectionSpec(
        title="Další kontakt",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "Kdy a jak proběhne další kontakt (telefonát/schůzka/e-mail). "
            "Pokud nepadlo, napiš „Další kontakt nebyl dohodnut.“"
        ),
        target_count="1 věta",
    ),
)


_TEACHER_PARENT_MEETING_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Účastníci a důvod konzultace",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Klíče: Účastníci (kdo se sešel — role, jména jen pokud zazněla), "
            "Důvod (proč konzultace proběhla), Datum (jen pokud zaznělo)."
        ),
        target_count="2-3 řádky",
    ),
    SectionSpec(
        title="Co bylo probráno",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Věcně a neutrálně — prospěch, chování, situace dítěte, postoje "
            "obou stran. U citlivých témat (zdraví, rodinná situace) formuluj "
            "opatrně a věcně, bez hodnocení. Tohle je dokument, který může "
            "číst i druhá strana."
        ),
        target_count="4-10 bodů",
    ),
    SectionSpec(
        title="Dohodnuté kroky",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Klíč = krok/opatření, hodnota = kdo ho udělá + do kdy. Rozlišuj, "
            "co dělá škola, co rodič, co dítě."
        ),
        target_count="podle konzultace",
    ),
    SectionSpec(
        title="Termín další konzultace nebo kontroly",
        kind=SECTION_KIND_PARAGRAPH,
        instruction="1 věta. Pokud nepadl, napiš „Termín nebyl dohodnut.“",
        target_count="1 věta",
    ),
)


_TEAM_MEETING_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Základní informace",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Klíče: Účastníci (jmenovitě, jak zazněli), Téma / účel porady, "
            "Datum (jen pokud zaznělo)."
        ),
        target_count="2-3 řádky",
    ),
    SectionSpec(
        title="Co kdo reportoval",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Klíč = osoba (jméno nebo „Mluvčí N“), hodnota = stručné shrnutí "
            "jejího vstupu (1-2 věty). Jen členové, kteří něco reportovali."
        ),
        target_count="podle porady",
    ),
    SectionSpec(
        title="Rozhodnutí",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Explicitní rozhodnutí a shody. Ne diskuze — jen to, na čem se tým "
            "skutečně dohodl. Pokud nic, prázdný seznam."
        ),
        target_count="0-8 položek",
    ),
    SectionSpec(
        title="Úkoly",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Klíč = úkol, hodnota = kdo + do kdy (nebo „neuvedeno“). "
            "Každý úkol musí mít vlastníka, pokud z debaty plyne."
        ),
        target_count="podle porady",
    ),
    SectionSpec(
        title="Odloženo na příště",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Témata, která se otevřela, ale nedořešila („parkoviště“). "
            "Pokud nic, prázdný seznam."
        ),
        target_count="0-5 položek",
    ),
)


_WORKSHOP_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="O čem školení bylo",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "1-2 odstavce: téma, lektor (pokud zazněl), pro koho a s jakým cílem."
        ),
        target_count="1-2 odstavce",
    ),
    SectionSpec(
        title="Hlavní poznatky",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Nejdůležitější věci, které si účastník má odnést. Konkrétně — "
            "postupy, pravidla, čísla, doporučení lektora."
        ),
        target_count="6-12 bodů",
    ),
    SectionSpec(
        title="Postupy krok za krokem",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Pokud lektor předváděl postup (nástroj, metodu, proces), rozepiš "
            "ho do číslovaných kroků tak, aby ho šlo zopakovat. Pokud žádný "
            "postup nezazněl, prázdný seznam."
        ),
        target_count="0-10 kroků",
    ),
    SectionSpec(
        title="Otázky účastníků a odpovědi",
        kind=SECTION_KIND_QA,
        instruction=(
            "Otázky z publika a odpovědi lektora — často nejcennější část "
            "školení. Pokud žádné nepadly, prázdný seznam."
        ),
        target_count="0-8 dvojic",
    ),
    SectionSpec(
        title="Zmíněné materiály a zdroje",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Knihy, weby, nástroje, šablony, kontakty, které lektor zmínil. "
            "Přesně jak zazněly."
        ),
        target_count="0-8 položek",
    ),
)


# ---------------------------------------------------------------------------
# Podcast / rozhovory — role "podcast"
# ---------------------------------------------------------------------------


_PODCAST_SHOWNOTES_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Anotace epizody",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "2-3 věty, které prodají epizodu posluchači — co se dozví a proč "
            "poslouchat. Žádné klišé („v dnešní epizodě se podíváme na…“), "
            "začni od nejzajímavějšího."
        ),
        target_count="1 odstavec (2-3 věty)",
    ),
    SectionSpec(
        title="O hostovi",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "Krátké představení hosta — jen z toho, co v nahrávce skutečně "
            "zaznělo (kdo je, co dělá, čím je zajímavý). Pokud epizoda hosta "
            "nemá, napiš „Epizoda bez hosta.“"
        ),
        target_count="1 odstavec",
    ),
    SectionSpec(
        title="Hlavní témata",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Témata epizody v pořadí, jak šla. Každý bod konkrétní — ne "
            "„povídání o kariéře“, ale co konkrétně o ní zaznělo."
        ),
        target_count="5-10 bodů",
    ),
    SectionSpec(
        title="Zmíněná jména, odkazy a zdroje",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Lidé, firmy, knihy, filmy, nástroje, weby — vše, co v epizodě "
            "padlo a posluchač by to mohl chtít dohledat."
        ),
        target_count="0-12 položek",
    ),
    SectionSpec(
        title="Popis pro platformy (copy-paste)",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "Hotový popis epizody pro Spotify/Apple Podcasts: anotace + "
            "odrážky témat + výzva k odběru. Připravené ke zkopírování."
        ),
        target_count="1 blok",
    ),
)


_PODCAST_CHAPTERS_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Kapitoly",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Klíč = časová značka začátku kapitoly přesně ve formátu mm:ss "
            "(nebo hh:mm:ss u delších nahrávek) podle značek v přepisu. "
            "Hodnota = krátký název kapitoly (3-6 slov). Kapitola = tematický "
            "blok, ne každá výměna. První kapitola vždy 00:00."
        ),
        target_count="6-15 kapitol",
    ),
    SectionSpec(
        title="Nejsilnější momenty",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Klíč = časová značka, hodnota = co se v tom místě stalo a proč "
            "stojí za pozornost (vtipný moment, silné tvrzení, zvrat). "
            "Pro výběr klipů a teaserů."
        ),
        target_count="3-6 momentů",
    ),
)


_PODCAST_QUOTES_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Citáty pro sociální sítě",
        kind=SECTION_KIND_KEY_VALUE,
        instruction=(
            "Klíč = časová značka (mm:ss dle přepisu), hodnota = doslovný citát "
            "(1-3 věty) + v závorce kdo ho řekl. Vybírej výroky, které fungují "
            "samostatně bez kontextu — silné, vtipné, kontroverzní, citovatelné. "
            "NEUPRAVUJ znění, jen očisti od „ehm“ a přeřeků."
        ),
        target_count="6-12 citátů",
    ),
    SectionSpec(
        title="Návrhy textů k postům",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "Ke 3-5 nejlepším citátům napiš krátký doprovodný text postu "
            "(1-2 věty + otázka pro engagement). Označ, ke kterému citátu patří."
        ),
        target_count="3-5 návrhů",
    ),
)


_PODCAST_ARTICLE_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Titulek",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "1 řádek — novinářský titulek článku. Konkrétní, ne clickbait. "
            "Ideálně s citátem nebo silným tvrzením z rozhovoru."
        ),
        target_count="1 řádek",
    ),
    SectionSpec(
        title="Perex",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "2-3 věty — úvod článku, který vtáhne čtenáře. Kdo mluví, "
            "o čem a co nejzajímavějšího řekl."
        ),
        target_count="1 odstavec",
    ),
    SectionSpec(
        title="Tělo článku",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "Souvislý článek z rozhovoru (4-8 odstavců). Parafráze prokládej "
            "přímými citacemi v uvozovkách. Piš žurnalisticky — třetí osoba, "
            "spád, fakta z rozhovoru. Nevymýšlej si nic, co nezaznělo."
        ),
        target_count="4-8 odstavců",
    ),
    SectionSpec(
        title="Vybrané citáty (boxy)",
        kind=SECTION_KIND_BULLETS,
        instruction=(
            "2-4 výrazné citáty vhodné jako zvýrazněné boxy v článku."
        ),
        target_count="2-4 citáty",
    ),
)


_PODCAST_INTERVIEW_QA_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        title="Úvod",
        kind=SECTION_KIND_PARAGRAPH,
        instruction=(
            "Krátký úvodní odstavec před rozhovorem — kdo je host a o čem se "
            "mluvilo. Jen z informací v nahrávce."
        ),
        target_count="1 odstavec",
    ),
    SectionSpec(
        title="Rozhovor",
        kind=SECTION_KIND_QA,
        instruction=(
            "Celý rozhovor jako dvojice otázka → odpověď, jazykově učesaný "
            "pro publikaci: pryč výplňová slova, přeřeky a opakování, ale "
            "ZACHOVEJ hlas a styl mluvčích i pořadí. Odpovědi můžeš mírně "
            "zkrátit, ne přepsat. Otázky zestručni na podstatu."
        ),
        target_count="10-25 dvojic",
    ),
)


# Mapování klíče šablony → schéma sekcí
SECTION_SCHEMAS: dict[str, tuple[SectionSpec, ...]] = {
    # Studentské
    "student": _STUDENT_SECTIONS,
    "student_flashcards": _STUDENT_FLASHCARDS_SECTIONS,
    "student_language_vocab": _STUDENT_LANGUAGE_VOCAB_SECTIONS,
    # Učitelské
    "teacher_lesson": _TEACHER_LESSON_SECTIONS,
    "teacher_questions_oral": _TEACHER_QUESTIONS_ORAL,
    "teacher_questions_written": _TEACHER_QUESTIONS_WRITTEN,
    "teacher_questions_practice": _TEACHER_QUESTIONS_PRACTICE,
    "teacher_materials": _TEACHER_MATERIALS_SECTIONS,
    "teacher_reflection": _TEACHER_REFLECTION_SECTIONS,
    "teacher_parent_summary": _TEACHER_PARENT_SUMMARY_SECTIONS,
    "teacher_next_lesson_plan": _TEACHER_NEXT_LESSON_PLAN_SECTIONS,
    # Sales / finanční poradenství
    "sales_meeting": _SALES_MEETING_SECTIONS,
    "sales_actions_only": _SALES_ACTIONS_ONLY_SECTIONS,
    "sales_client_profile": _SALES_CLIENT_PROFILE_SECTIONS,
    "sales_followup_email": _SALES_FOLLOWUP_EMAIL_SECTIONS,
    "sales_objection_log": _SALES_OBJECTION_LOG_SECTIONS,
    "sales_phone_call": _SALES_PHONE_CALL_SECTIONS,
    # Učitelské přídavky
    "teacher_parent_meeting": _TEACHER_PARENT_MEETING_SECTIONS,
    # Podcast / rozhovory
    "podcast_shownotes": _PODCAST_SHOWNOTES_SECTIONS,
    "podcast_chapters": _PODCAST_CHAPTERS_SECTIONS,
    "podcast_quotes": _PODCAST_QUOTES_SECTIONS,
    "podcast_article": _PODCAST_ARTICLE_SECTIONS,
    "podcast_interview_qa": _PODCAST_INTERVIEW_QA_SECTIONS,
    # Univerzální
    "quiz": _QUIZ_SECTIONS,
    "summary": _SUMMARY_SECTIONS,
    "meeting_minutes": _MEETING_MINUTES_SECTIONS,
    "brainstorm": _BRAINSTORM_SECTIONS,
    "team_meeting": _TEAM_MEETING_SECTIONS,
    "workshop_training": _WORKSHOP_SECTIONS,
}


def sections_for_template(template_key: str) -> tuple[SectionSpec, ...]:
    """Vrátí schéma sekcí pro daný klíč. Fallback = student schéma."""
    return SECTION_SCHEMAS.get(template_key) or _STUDENT_SECTIONS


# ---------------------------------------------------------------------------
# Builder promptů
# ---------------------------------------------------------------------------


MAP_PROMPT_TEMPLATE = """Z následujícího úryvku přepisu vytáhni jen syrový materiál:

1) BODY — konkrétní fakta, čísla, jména, vztahy, příklady (1 věta každý).
2) POJMY — odborné termíny a jejich definice tak, jak je řečník použil
   (formát "POJEM – definice z přepisu"). Když není pojem v přepisu
   vysvětlený, vynech ho.
3) PŘÍKLADY / PŘÍBĚHY — konkrétní ilustrace, případy, historky.
4) DŮLEŽITÉ ÚDAJE — termíny, čísla, datumy, jména, akce, závazky.

Vrať validní JSON:
```json
{{
  "bullets": ["bod 1", "bod 2"],
  "terms": [["pojem", "definice"], ["pojem", "definice"]],
  "examples": ["příklad 1"],
  "facts": ["konkrétní údaj 1"]
}}
```

Bez dalšího komentáře. Pokud chunk neobsahuje nic užitečného, vrať prázdné
seznamy. Nevymýšlej si — drž se přepisu.

ČÁST PŘEPISU (štítek: "{label}"):
\"\"\"
{chunk}
\"\"\"
"""


def build_map_prompt(chunk: str, label: str) -> str:
    return MAP_PROMPT_TEMPLATE.format(chunk=chunk, label=label)


def _format_section_spec(idx: int, spec: SectionSpec) -> str:
    """Lidsky čitelný popis jedné sekce pro vložení do promptu."""
    parts = [f"{idx}) „{spec.title}“  —  kind: \"{spec.kind}\""]
    if spec.target_count:
        parts.append(f"   Rozsah: {spec.target_count}")
    parts.append(f"   Co tam dát: {spec.instruction}")
    parts.append(f"   Tvar items: {spec.items_hint}")
    return "\n".join(parts)


def _format_sections_block(specs: tuple[SectionSpec, ...]) -> str:
    blocks = [_format_section_spec(i, s) for i, s in enumerate(specs, start=1)]
    return "\n\n".join(blocks)


def _format_output_skeleton(specs: tuple[SectionSpec, ...]) -> str:
    """JSON skeleton, který má AI naplnit konkrétními daty."""
    items_examples: dict[str, str] = {
        SECTION_KIND_BULLETS: '["…", "…"]',
        SECTION_KIND_PARAGRAPH: '["první odstavec …", "případně druhý …"]',
        SECTION_KIND_DEFINITIONS: '[["pojem", "definice"], ["pojem", "definice"]]',
        SECTION_KIND_QA: '[["otázka", "vzorová odpověď"], ["otázka", ""]]',
        SECTION_KIND_KEY_VALUE: '[["klíč", "hodnota"], ["klíč", "hodnota"]]',
    }
    sections_json_parts: list[str] = []
    for spec in specs:
        items_example = items_examples.get(spec.kind, '["…"]')
        sections_json_parts.append(
            "    {\n"
            f'      "title": "{spec.title}",\n'
            f'      "kind": "{spec.kind}",\n'
            f'      "items": {items_example}\n'
            "    }"
        )
    return (
        "{\n"
        '  "title": "stručný název materiálu (max 80 znaků)",\n'
        '  "topic": "obor/předmět 1-2 slovy pro zařazení do složky '
        '(např. „Fyzika“, „Marketing“, „Finance“)",\n'
        '  "sections": [\n' + ",\n".join(sections_json_parts) + "\n  ]\n"
        "}"
    )


_QUALITY_RULES = """\
KVALITATIVNÍ PRAVIDLA (nepřeskakuj):
• Drž se přepisu. Nepřidávej fakta zvenčí. Když údaj chybí, napiš „neuvedeno“.
• Konkrétně. Cituj čísla, jména, data, místa, příklady. Žádná vata typu
  „je důležité dobře se připravit“ — to ze zápisu nikomu nic nedá.
• Vyzdvihni důležité. Pokud řečník něco opakuje, zdůrazňuje („tohle si "
zapamatujte“, „klíčové je…“), dej tomu prostor a označ jako prioritní bod.
• Žádná duplicita mezi sekcemi. Pokud něco patří do více sekcí, vlož to do
  té nejvhodnější (typicky té, která vyžaduje nejvíc kontextu).
• Nezahrnuj prázdnou sekci. Pokud opravdu není co napsat, vrať pro ni
  `"items": []` — ale jen výjimečně. Když je sekce prázdná opakovaně, je to
  signál, že schéma šablony nesedí na obsah; ber to jako varování pro sebe
  a alespoň jedna sekce musí mít položky.
• JSON je striktní: žádný text před/za, žádné komentáře v JSONu, validní UTF-8."""


# Pravidla pro brainstorming/reflexi — AI tu SMÍ přidávat vlastní názor a nápady.
_QUALITY_RULES_BRAINSTORM = """\
KVALITATIVNÍ PRAVIDLA (nepřeskakuj):
• Tahle úloha je VÝJIMKA: kromě věrného shrnutí se od tebe čeká vlastní názor,
  kritika a nové návrhy. Sekce to řeknou jasně — řiď se jejich popisem.
• Odděluj „co padlo“ od „co si myslím já“. Vlastní vstup uvozuj („Myslím…“,
  „Doporučuji…“, „Riziko:…“). Nevydávej své nápady za slova účastníků.
• Buď upřímný a konkrétní. Slabý nebo riskantní nápad pojmenuj. Nelichoť, vata
  typu „skvělý nápad, jen tak dál“ nemá hodnotu — řekni PROČ a CO s tím.
• U efektivity schůzky buď přímý: odbíhání, žádný závěr, opakování, zbytečná
  délka — napiš to a navrhni konkrétní zlepšení.
• Nevymýšlej si SKUTEČNOSTI (jména, čísla, fakta o firmě), které nezazněly.
  Vlastní názory a nápady ano, smyšlená fakta ne.
• JSON je striktní: žádný text před/za, žádné komentáře v JSONu, validní UTF-8."""


_QUALITY_RULES_OVERRIDES: dict[str, str] = {
    "brainstorm": _QUALITY_RULES_BRAINSTORM,
}


def _quality_rules_for(template_key: str) -> str:
    """Vrátí kvalitativní pravidla pro danou šablonu (brainstorm má vlastní)."""
    return _QUALITY_RULES_OVERRIDES.get(template_key, _QUALITY_RULES)


_REDUCE_PROMPT_TEMPLATE = """Toto je zadání od uživatele:

> {user_prompt}

Z následujících zdrojů vytvoř finální materiál podle níže popsané struktury.

═══════════════════════════════════════════════════════════════
PŘEDZPRACOVANÉ BODY Z PŘEPISU (z map fáze):
{mapped_summary}

═══════════════════════════════════════════════════════════════
TEXT Z PREZENTACÍ (slidy):
{slides_text}

═══════════════════════════════════════════════════════════════

POŽADOVANÁ STRUKTURA VÝSTUPU — sekce, které MUSÍ být v JSON.sections (v tomto
pořadí, tituly přesně tak, jak jsou níže):

{sections_block}

═══════════════════════════════════════════════════════════════

OUTPUT FORMÁT (validní JSON, nic mimo):
```json
{output_skeleton}
```

{quality_rules}
"""


_SINGLE_SHOT_PROMPT_TEMPLATE = """Toto je zadání od uživatele:

> {user_prompt}

Z následujícího přepisu a obsahu prezentací vyrob finální materiál podle níže
popsané struktury.

═══════════════════════════════════════════════════════════════
PŘEPIS:
{transcript}

═══════════════════════════════════════════════════════════════
TEXT Z PREZENTACÍ (slidy):
{slides_text}

═══════════════════════════════════════════════════════════════

POŽADOVANÁ STRUKTURA VÝSTUPU — sekce, které MUSÍ být v JSON.sections (v tomto
pořadí, tituly přesně tak, jak jsou níže):

{sections_block}

═══════════════════════════════════════════════════════════════

OUTPUT FORMÁT (validní JSON, nic mimo):
```json
{output_skeleton}
```

{quality_rules}
"""


def build_reduce_prompt(
    user_prompt: str,
    mapped_summary: str,
    slides_text: str,
    *,
    template_key: str = "student",
) -> str:
    specs = sections_for_template(template_key)
    return _REDUCE_PROMPT_TEMPLATE.format(
        user_prompt=user_prompt or "(uživatel nezadal popis)",
        mapped_summary=mapped_summary or "(žádné body)",
        slides_text=slides_text or "(žádné slidy)",
        sections_block=_format_sections_block(specs),
        output_skeleton=_format_output_skeleton(specs),
        quality_rules=_quality_rules_for(template_key),
    )


def build_single_shot_prompt(
    user_prompt: str,
    transcript: str,
    slides_text: str,
    *,
    template_key: str = "student",
) -> str:
    specs = sections_for_template(template_key)
    return _SINGLE_SHOT_PROMPT_TEMPLATE.format(
        user_prompt=user_prompt or "(uživatel nezadal popis)",
        transcript=transcript,
        slides_text=slides_text or "(žádné slidy)",
        sections_block=_format_sections_block(specs),
        output_skeleton=_format_output_skeleton(specs),
        quality_rules=_quality_rules_for(template_key),
    )


# ---------------------------------------------------------------------------
# Šablony zadání (předvyplní pole "popis pro AI") — uživatel vybere v UI
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
            "Vytvoř z ní přehledné poznámky o tom, co se v hodině probíralo (bod po "
            "bodu, v pořadí), klíčové pojmy s vysvětlením a otázky ke zkoušení žáků "
            "různé obtížnosti."
        ),
    },
    "quiz": {
        "label": "Hlavně otázky k procvičení",
        "prompt": (
            "Z tohoto záznamu vytvoř hlavně sadu otázek k procvičení a ověření "
            "pochopení látky — co nejvíc, různé obtížnosti. Plus stručný přehled "
            "probraných bodů."
        ),
    },
    "summary": {
        "label": "Krátké shrnutí (1 strana)",
        "prompt": (
            "Vytvoř stručné shrnutí tohoto záznamu — jen ty nejdůležitější body, "
            "tak aby se vešly na jednu stranu A4. Žádná vata."
        ),
    },
    # --- Učitelské akce ---
    "teacher_questions_oral": {
        "label": "Otázky vhodné k testu — ústní",
        "prompt": (
            "Z této nahrávky hodiny vytvoř sadu otázek k ÚSTNÍMU ZKOUŠENÍ žáků. "
            "Otázky vhodné pro souvislou odpověď žáka vlastními slovy, různé "
            "obtížnosti, přiměřené věku ZŠ."
        ),
    },
    "teacher_questions_written": {
        "label": "Otázky vhodné k testu — písemka",
        "prompt": (
            "Z této nahrávky hodiny vytvoř sadu otázek do PÍSEMNÉ PRÁCE pro žáky — "
            "formulované tak, aby žák odpověděl 1-3 větami. Připoj i vzorové "
            "odpovědi a krátké poznámky k hodnocení."
        ),
    },
    "teacher_questions_practice": {
        "label": "Otázky vhodné k testu — procvičování",
        "prompt": (
            "Z této nahrávky hodiny vytvoř sadu otázek k PROCVIČOVÁNÍ doma — "
            "gradovaně od snadných po těžší. Cílem je opakování látky, ne hodnocení."
        ),
    },
    "teacher_materials": {
        "label": "Materiály k zaslání pro studenty",
        "prompt": (
            "Z této nahrávky hodiny připrav STUDIJNÍ MATERIÁL pro žáky — přehledné "
            "poznámky, klíčové pojmy s definicemi, příklady a otázky k opakování. "
            "Vhodné pro nepřítomné žáky."
        ),
    },
    "teacher_reflection": {
        "label": "Reflexe hodiny — zpětná vazba na projev",
        "prompt": (
            "Tohle je nahrávka mé vyučovací hodiny. Dej mi UPŘÍMNOU ZPĚTNOU VAZBU "
            "k mému učitelskému projevu, ne k obsahu látky: tempo, výplňová slova, "
            "srozumitelnost, interakce, struktura, co příště zkusit jinak. Konkrétně, "
            "s odkazy na konkrétní momenty z hodiny."
        ),
    },
    # --- Sales / finanční poradce ---
    "sales_meeting": {
        "label": "Kompletní zápis ze schůzky s klientem",
        "prompt": (
            "Jsem finanční poradce a tohle je nahrávka schůzky s klientem. Vytvoř "
            "strukturovaný zápis: úkoly pro mě (s deadliny), úkoly pro klienta, "
            "profil klienta (vše co o sobě řekl), termín další schůzky a další "
            "poznámky. Buď konkrétní, věrný, žádné fráze."
        ),
    },
    "sales_actions_only": {
        "label": "Jen akční úkoly (TODO list)",
        "prompt": (
            "Z této schůzky vypiš JEN konkrétní akční položky pro obě strany — "
            "s deadliny, pokud zazněly. Plus termín další schůzky, pokud byl dohodnut."
        ),
    },
    "sales_client_profile": {
        "label": "Profil klienta (data ze schůzky)",
        "prompt": (
            "Extrahuj ze schůzky všechna konkrétní data o klientovi do strukturovaného "
            "profilu: osobní údaje, finanční situace, životní cíle a horizonty, "
            "postoj k riziku, současné produkty a preference komunikace. Jen co "
            "skutečně padlo — když data chybí, vynech řádek."
        ),
    },
    "sales_followup_email": {
        "label": "Follow-up e-mail klientovi",
        "prompt": (
            "Z této schůzky vyrob HOTOVÝ E-MAIL, který poradce zkopíruje a "
            "pošle klientovi. Předmět, oslovení, krátké poděkování, shrnutí "
            "klíčových bodů, dohodnuté další kroky s termíny, závěr a podpis. "
            "Tón profesionální, vstřícný. Nic si nevymýšlej — drž se přepisu."
        ),
    },
    "sales_objection_log": {
        "label": "Námitky klienta + moje reakce (kouč. zápis)",
        "prompt": (
            "Vytáhni ze schůzky všechny námitky, které klient vznesl, a jak "
            "jsem na ně reagoval. Označ, co fungovalo a co příště zkusit "
            "jinak. Sloužit jako podklad pro koučing a moje učení."
        ),
    },
    # --- Studentské přídavky ---
    "student_flashcards": {
        "label": "Karty na učení (Anki / Quizlet)",
        "prompt": (
            "Z této přednášky vyrob atomické karty na učení: krátké dvojice "
            "„pojem → definice“ a „otázka → odpověď“. Cíl: import do Anki "
            "nebo Quizlet. Každá karta musí být samostatně srozumitelná."
        ),
    },
    "student_language_vocab": {
        "label": "Slovíčka a fráze z hodiny jazyka",
        "prompt": (
            "Z této nahrávky hodiny cizího jazyka vytáhni slovní zásobu "
            "(slovo → překlad + ukázková věta), gramatické jevy s krátkým "
            "pravidlem a užitečné fráze pro běžnou konverzaci."
        ),
    },
    # --- Učitelské přídavky ---
    "teacher_parent_summary": {
        "label": "Souhrn pro rodiče",
        "prompt": (
            "Z této hodiny připrav KRÁTKÝ A VLÍDNÝ souhrn pro rodiče: co "
            "jsme dnes probrali (srozumitelně, bez odborného žargonu), jak "
            "reagovali žáci kolektivně (žádná jména), případná domácí "
            "příprava. Tón přívětivý."
        ),
    },
    "teacher_next_lesson_plan": {
        "label": "Plán navazující hodiny",
        "prompt": (
            "Z této hodiny mi navrhni STRUKTURU NAVAZUJÍCÍ HODINY: na čem "
            "dnes skončili, co opakovat na začátku, jaká nová látka přijde "
            "v jakém pořadí (s časovým odhadem), jaké materiály připravit, "
            "kde žáci pravděpodobně budou tápat."
        ),
    },
    # --- Univerzální ---
    "meeting_minutes": {
        "label": "Univerzální zápis ze schůzky (interní)",
        "prompt": (
            "Z této nahrávky pracovní schůzky vyrob klasický strukturovaný "
            "zápis: základní informace (datum, místo, účastníci, téma), "
            "probrané body, rozhodnutí, akce a úkoly (kdo + do kdy), termín "
            "dalšího setkání. Vhodné pro interní distribuci."
        ),
    },
    "brainstorm": {
        "label": "Brainstorming — názor a kritika od AI",
        "prompt": (
            "Tohle je záznam brainstormingu / pracovní debaty. Chci od tebe "
            "UPŘÍMNOU zpětnou vazbu, ne jen přepis: co si reálně myslíš o "
            "probíraných nápadech, kritiku a slabá místa, vlastní návrhy a nové "
            "směry. A taky upřímně zhodnoť, jestli byla schůzka efektivní — "
            "jestli ne, řekni to."
        ),
    },
    "team_meeting": {
        "label": "Porada týmu (kdo co reportoval + úkoly)",
        "prompt": (
            "Tohle je nahrávka týmové porady. Vyrob zápis: kdo co reportoval, "
            "jaká padla rozhodnutí, úkoly s vlastníky a termíny, a co se "
            "odložilo na příště."
        ),
    },
    "workshop_training": {
        "label": "Workshop / školení (poznatky + postupy)",
        "prompt": (
            "Tohle je nahrávka workshopu/školení. Vytáhni hlavní poznatky, "
            "postupy krok za krokem (aby šly zopakovat), otázky účastníků "
            "s odpověďmi lektora a zmíněné materiály."
        ),
    },
    # --- Sales přídavky ---
    "sales_phone_call": {
        "label": "Telefonát s klientem (krátký zápis)",
        "prompt": (
            "Tohle je nahrávka telefonátu s klientem. Vyrob KRÁTKÝ zápis: "
            "důvod a výsledek hovoru, co zaznělo, dohodnuté kroky s termíny "
            "a kdy proběhne další kontakt."
        ),
    },
    # --- Učitelské přídavky ---
    "teacher_parent_meeting": {
        "label": "Konzultace s rodičem (zápis)",
        "prompt": (
            "Tohle je nahrávka konzultace s rodičem žáka. Vyrob věcný, "
            "neutrální zápis: účastníci a důvod, co bylo probráno, dohodnuté "
            "kroky (kdo + do kdy) a termín další konzultace. Formuluj tak, "
            "aby zápis mohla číst i druhá strana."
        ),
    },
    # --- Podcast / rozhovory ---
    "podcast_shownotes": {
        "label": "Show notes — popis epizody",
        "prompt": (
            "Tohle je nahrávka epizody podcastu/rozhovoru. Vyrob show notes: "
            "anotaci, představení hosta, hlavní témata, zmíněné odkazy a "
            "hotový popis pro Spotify/Apple Podcasts."
        ),
    },
    "podcast_chapters": {
        "label": "Kapitoly s časovými značkami",
        "prompt": (
            "Z této nahrávky vyrob kapitoly s časovými značkami (pro YouTube/"
            "Spotify) a vytipuj nejsilnější momenty pro klipy. Časy ber přesně "
            "ze značek v přepisu."
        ),
    },
    "podcast_quotes": {
        "label": "Citáty pro sociální sítě",
        "prompt": (
            "Z této nahrávky vytáhni nejsilnější doslovné citáty s časovými "
            "značkami (pro střih klipů) a navrhni texty k postům na sociální "
            "sítě."
        ),
    },
    "podcast_article": {
        "label": "Článek z rozhovoru (blog)",
        "prompt": (
            "Z tohoto rozhovoru napiš publikovatelný článek: titulek, perex, "
            "tělo s citacemi a vybrané citáty do boxů. Žurnalisticky, věrně "
            "obsahu."
        ),
    },
    "podcast_interview_qa": {
        "label": "Rozhovor k publikaci (otázka–odpověď)",
        "prompt": (
            "Z této nahrávky vyrob rozhovor ve formátu otázka–odpověď "
            "připravený k publikaci: jazykově učesaný (bez výplňových slov "
            "a přeřeků), ale se zachovaným hlasem mluvčích."
        ),
    },
}


def template_prompt(key: str) -> str:
    """Vrátí předvyplněný text zadání pro danou šablonu (nebo prázdný řetězec)."""
    return PROMPT_TEMPLATES.get(key, {}).get("prompt", "")


# Šablony bez prefixu, které dávají smysl všem rolím (zobrazí se v každém dropdown).
# Pozn.: "student" je sice student-specifická, ale klíč nemá prefix `student_` —
# proto je explicitně vyloučená z teacher/sales/podcast dropdownu níže.
_UNIVERSAL_KEYS: frozenset[str] = frozenset(
    {"quiz", "summary", "meeting_minutes", "brainstorm", "team_meeting", "workshop_training"}
)

# Prefixy rolových šablon — pro filtr "co NEpatří studentovi".
_ROLE_PREFIXES = ("teacher_", "sales_", "podcast_")


def templates_for_role(role: str) -> dict[str, dict[str, str]]:
    """Vrátí jen šablony relevantní pro danou roli aplikace.

    - "student": šablony bez rolových prefixů (= student + student_* + univerzální)
    - "teacher": teacher_* + univerzální
    - "sales":   sales_* + univerzální
    - "podcast": podcast_* + univerzální
    """
    if role in ("teacher", "sales", "podcast"):
        prefix = f"{role}_"
        return {
            k: v
            for k, v in PROMPT_TEMPLATES.items()
            if k.startswith(prefix) or k in _UNIVERSAL_KEYS
        }
    # student (default)
    return {
        k: v
        for k, v in PROMPT_TEMPLATES.items()
        if not any(k.startswith(p) for p in _ROLE_PREFIXES)
    }


# Šablony s dialogem více osob — tam má smysl rozlišovat mluvčí (diarizace).
# Přednáška/studijní materiál je monolog → diarizace by jen přidávala šum.
CONVERSATION_TEMPLATE_KEYS: frozenset[str] = frozenset(
    {k for k in PROMPT_TEMPLATES if k.startswith(("sales_", "podcast_"))}
    | {
        "meeting_minutes",
        "brainstorm",
        "team_meeting",
        "workshop_training",
        "teacher_parent_meeting",
    }
)


def is_conversation_template(template_key: str) -> bool:
    """True pro šablony s dialogem více osob (sales schůzka, zápis ze schůzky).

    Používá GUI k automatickému zapnutí diarizace (rozlišování mluvčích) — ta
    má smysl jen u dialogu, ne u přednášky s jedním mluvčím.
    """
    return template_key in CONVERSATION_TEMPLATE_KEYS


# Šablony, které potřebují ČASOVÉ ZNAČKY v textu přepisu pro AI — kapitoly
# a citáty pro střih klipů bez časů nedávají smysl. Router pro ně vloží
# [mm:ss] značky do textu poslaného AI.
TIMESTAMPED_TEMPLATE_KEYS: frozenset[str] = frozenset(
    {"podcast_chapters", "podcast_quotes"}
)


def needs_timestamps(template_key: str) -> bool:
    """True pro šablony, jejichž výstup pracuje s časovými značkami."""
    return template_key in TIMESTAMPED_TEMPLATE_KEYS
