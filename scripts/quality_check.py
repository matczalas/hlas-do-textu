"""End-to-end quality check AI pipeline — reálné Gemini volání pro každou šablonu.

Spustí pipeline pro 6-8 reprezentativních (use-case × šablona) kombinací
a vypíše strukturu vygenerovaných .docx + ukázky obsahu + detekované problémy.

Vyžaduje GEMINI_API_KEY (env nebo keychain). Spotřebovává Gemini Free kvótu —
typicky 7-10 volání.

Spuštění:
    python scripts/quality_check.py [--only sales|teacher|student]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

# Cesta k repo rootu (skript běží odkudkoli)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.ai.gemini import GeminiProvider  # noqa: E402
from app.core.ai.router import AIRouter, generate_study_material  # noqa: E402
from app.core.models import (  # noqa: E402
    SECTION_KIND_BULLETS,
    SECTION_KIND_DEFINITIONS,
    SECTION_KIND_KEY_VALUE,
    SECTION_KIND_PARAGRAPH,
    SECTION_KIND_QA,
    StudyMaterial,
    Transcript,
    TranscriptSegment,
)
from app.core.word_export import export_docx  # noqa: E402
from app.settings import get_gemini_api_key  # noqa: E402

# ---------------------------------------------------------------------------
# Fake přepisy (realistické, krátké — drží Gemini kvótu nízko)
# ---------------------------------------------------------------------------

SALES_TRANSCRIPT = """\
Poradce: Dobrý den, pane Nováku, posaďte se. Tak co vás dnes ke mně přivedlo?

Klient: Dobrý den. Manželka mi pořád říká, že bychom měli začít víc spořit. Je nám
oběma 42, máme dvě děti, holku Aničku jí je 11 a kluka Tomáše osm. Máme hypotéku
osmnáct tisíc měsíčně, splácet máme ještě patnáct let. Já dělám projektového
manažera, beru čistého šedesát pět tisíc, manželka v marketingu kolem
čtyřiceti.

Poradce: Aha, takže rodinný příjem zhruba sto pět tisíc čistého. Máte něco
naspořeného nebo nějaké investice?

Klient: Spořící účet kolem dvou set tisíc, pak v penzijku doplňkovém asi šedesát
tisíc každý. Nic jiného. A teď slyším od kamarádů o akciích, kryptech, fondech,
ale úplně se v tom ztrácím.

Poradce: Jaký máte horizont? Co byste chtěli mít vyřešené?

Klient: Hlavně dvě věci. Důchod, abychom nebyli odkázáni na to penzijní zhroucení.
A pak vzdělání dětí — když by chtěla Anička jít na vysokou do Prahy, nebo třeba
do zahraničí, ať jí to můžeme zaplatit. To je asi za osm let u ní.

Poradce: Rozumím. A jaký máte vztah k riziku? Když by váš spoření kolísalo,
třeba minus dvacet procent v jednom roce, jak byste reagoval?

Klient: To bych asi panikařil, no. Bratranec před třemi lety přišel o čtvrtinu
peněz na nějaké pyramidě, od té doby jsem opatrný. Nechci nic riskovat.

Poradce: To beru. Pojďme to udělat takhle — připravím vám srovnání tří
konzervativnějších portfolií, kde je riziko nízké až střední. Plus návrh
spoření přímo na vzdělání Aničky s osmiletým horizontem. Pošlu vám to do
pátku e-mailem. A poprosil bych vás, jestli byste mi do středy poslal výpis
z vaší banky za poslední tři měsíce a kopii poslední splátkové tabulky
hypotéky — ať vidím přesné cash-flow.

Klient: Jasně, to udělám. A ještě jedna věc — chci, aby u toho byla manželka,
takže ta další schůzka by mohla být po práci?

Poradce: Domluvíme se na čtvrtek za čtrnáct dní, ten čtvrtek osmnáctého
v půl šesté večer u vás doma? Vyhovuje to oběma?

Klient: Jo, to by šlo. Domluvíme to.

Poradce: Skvělé. Já vám pošlu to srovnání ještě než přijdu, ať se na to
můžete v klidu podívat. A klidně mi pak před schůzkou napište otázky, ať
se na ně připravím.

Klient: Díky moc. A jak to bude s vaší odměnou? Kolik to bude stát?

Poradce: První konzultace zdarma, jako jsme se domluvili. Pokud byste se
rozhodli pro spoření přes nás, tak je to provize ze správcovských poplatků
fondu, nic neplatíte navíc. Detaily probereme v té další schůzce.
"""

TEACHER_TRANSCRIPT = """\
Učitel: Tak, dobrý den všem, dnes si povíme o příčinách první světové války.
Tomáši, můžeš mi říct, který rok začala?

Žák: Devatenáct set čtrnáct.

Učitel: Správně, devatenáct set čtrnáct. Konkrétně sedmadvacátého července
osmadvacátého. Ale aby to mohlo začít, muselo se stát něco důležitého
předtím. Kdo ví co?

Žákyně: Atentát na Františka Ferdinanda?

Učitel: Přesně tak. Sarajevský atentát. Osmadvacátého června devatenáct
set čtrnáct. Kdo ho zastřelil? Někdo si vzpomene na jméno?

Žák: Princip… Gavrilo Princip?

Učitel: Výborně. Gavrilo Princip, srbský student. Bylo mu devatenáct let.
A teď pozor — proč to vedlo k světové válce? Tady přichází druhá důležitá
věc, a tou je systém aliancí. Před válkou byla Evropa rozdělená do dvou
táborů. Trojspolek, to je Německo, Rakousko-Uhersko a Itálie. A Dohoda,
to je Francie, Rusko a Británie. Když začala válka mezi Rakouskem
a Srbskem, kvůli aliancím se v ní postupně ocitla celá Evropa.

Žákyně: A Itálie tam pak nebyla, ne? My jsme si o tom četli.

Učitel: Přesně, Lucie, dobře sis to zapamatovala. Itálie přešla na druhou
stranu v patnáctém roce. Ale to budeme probírat za týden. Dnes ještě
důležitý pojem — mobilizace. Kdo by mi vlastními slovy řekl, co to je?

Žák: Že jako svolají vojáky?

Učitel: Skoro. Mobilizace znamená povolat všechny vojáky a připravit
armádu na válku. Když Rakousko-Uhersko vyhlásilo Srbsku válku, Rusko
začalo mobilizovat na podporu Srbska, Německo se kvůli tomu cítilo
ohrožené a vyhlásilo válku Rusku — a tak to celé spustilo. Takže si
zapamatujte: atentát byl spouštěč, ale skutečné příčiny byly hlubší.
Alianční systém, soupeření o kolonie a zbrojení.

Učitel: Teď uděláme krátké cvičení. Otevřete si sešity, nakreslíme si
časovou osu od dvacátého osmého června do osmadvacátého července. Každý
den, kdy se něco důležitého stalo, si tam vyznačíme. Máte deset minut.

(o pár minut později)

Učitel: Tak jak vám to jde? Jirko, ukaž mi.

Žák: Já jsem si tam dal jen ten atentát a vyhlášení války.

Učitel: To je málo. Mezitím se stalo strašně moc věcí. Třeba osmnáctého
července Rakousko-Uhersko poslalo Srbsku ultimátum. To je důležitý
bod. Doplň si to. A pětadvacátého července Srbsko ultimátum téměř
přijalo, ale jednu věc odmítlo, a to byl důvod, proč Rakousko vyhlásilo
válku.

Učitel: Dobře, dochází nám čas. Na příští hodinu si přečtěte v učebnici
kapitolu dvacet jedna o průběhu války v patnáctém roce. A kdo má chuť,
ať si pustí dokumentární seriál Čtrnáct osmnáct na Stream.cz. Pomůže
vám to vidět to v souvislostech. Hezký den, na shledanou.
"""

# Krátká přednáška o ekonomické gramotnosti pro studenty
LECTURE_TRANSCRIPT = """\
Přednášející: Dobrý večer všem. Dnešní přednáška je o pasivním investování
a o tom, proč by mohlo být zajímavé pro každého z vás, kdo má před sebou
horizont aspoň deset let.

Začneme základní myšlenkou. Aktivní správa fondu znamená, že manažer
vybírá konkrétní akcie a snaží se porazit trh. Pasivní investování
naopak znamená, že koupíte celý index — třeba S&P 500 — a držíte ho.
Žádný stress, žádné rozhodování, jen sledujete celý trh.

Co je na tom zajímavé? Statistika z amerických dat za posledních dvacet
let ukazuje, že přes devadesát procent aktivně spravovaných fondů
nedokáže dlouhodobě porazit index. Hlavním důvodem jsou poplatky.
Aktivní fond má často poplatky kolem jednoho a půl procenta ročně,
pasivní ETF kolem nula celá tří procent. Na dlouhém horizontu — třeba
třiceti let — ten rozdíl je v desítkách procent celkového výnosu.

Pojem, který si zapamatujte: TER, total expense ratio. To je celkový
roční poplatek fondu. Když vidíte TER nula celá nula sedm, jako u
známého S&P 500 ETF od Vanguardu, je to extrémně nízké. Když vidíte
TER dvě procenta, utíkejte.

Ještě jeden pojem, který je důležitý — diverzifikace. To znamená
rozkládání rizika přes mnoho různých aktiv. Když koupíte jednu akcii
a ta zbankrotuje, přijdete o všechno. Když koupíte index s pěti sty
akciemi, jeden bankrot vám sebere maximálně jedno promile portfolia.

Příklad z praxe — Warren Buffett, jeden z nejlepších investorů
historie, ve svém testamentu napsal, že peníze pro jeho ženu mají
být investovány z devadesáti procent do S&P 500 ETF a deseti procent
do krátkodobých státních dluhopisů. Sám tedy doporučuje pasivní
přístup, i když je sám aktivní investor.

Otázka, kterou často dostávám — co když přijde krize? Krize přijde,
to garantuju. V osmém roce trh klesl o víc než padesát procent.
V dvacátém roce kvůli pandemii o třicet procent v měsíci. Ale kdo
v ten moment neprodal a držel dál, do dvou let byl zpátky v plusu.
Klíčem je horizont a klid. Pokud máte horizont alespoň deset let,
nehleďte na výkyvy.

Závěrem — pasivní investování není zázrak, je to jen statisticky
nejlepší volba pro většinu lidí, kteří se nechtějí dennodenně
zabývat trhem. Pokud vás to zajímá víc, doporučuju knihu Common Sense
on Mutual Funds od Johna Bogla, zakladatele Vanguardu. Děkuji.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_transcript(label: str, text: str) -> Transcript:
    """Vyrobí Transcript ze statického textu (s jediným segmentem na 0s)."""
    return Transcript(
        source_label=label,
        language="cs",
        duration_sec=300.0,
        text=text,
        segments=[TranscriptSegment(start=0.0, end=300.0, text=text)],
    )


@dataclass
class RunResult:
    label: str
    template_key: str
    material: StudyMaterial
    docx_path: Path
    elapsed_sec: float
    warnings: list[str]


def run_one(api_key: str, label: str, transcript: Transcript, template_key: str, out_dir: Path) -> RunResult:
    """Jedno volání AI + export do .docx. Bezpečné k běhu paralelně."""
    router = AIRouter(primary=GeminiProvider(api_key=api_key), fallback=None)
    started = time.time()
    material = generate_study_material(
        router=router,
        transcripts=[transcript],
        slides=[],
        user_prompt="",
        template_key=template_key,
    )
    elapsed = time.time() - started

    out_path = out_dir / f"{label}__{template_key}.docx"
    export_docx(output_path=out_path, material=material, sources=[], user_prompt=None)

    warnings = _audit(material, template_key)
    return RunResult(
        label=label,
        template_key=template_key,
        material=material,
        docx_path=out_path,
        elapsed_sec=elapsed,
        warnings=warnings,
    )


def _audit(material: StudyMaterial, template_key: str) -> list[str]:
    """Detekce zjevných problémů ve výstupu."""
    from app.core.ai.prompts import sections_for_template

    warnings: list[str] = []
    expected_specs = sections_for_template(template_key)
    expected_titles = [s.title for s in expected_specs]
    actual_titles = [s.title for s in material.sections]

    # 1) Žádná sekce nemá obsah?
    sections_with_content = [s for s in material.sections if s.items]
    if not sections_with_content:
        warnings.append("VŠECHNY sekce jsou prázdné")

    # 2) Které očekávané sekce úplně chybí?
    missing = [t for t in expected_titles if t not in actual_titles]
    if missing:
        warnings.append(f"Chybí očekávané sekce: {missing}")

    # 3) Extra (neočekávané) sekce — AI si vymyslela vlastní
    extra = [t for t in actual_titles if t not in expected_titles]
    if extra:
        warnings.append(f"AI přidala neočekávané sekce: {extra}")

    # 4) Sekce, které mají vrátit pár položek (qa/definitions) jsou skoro prázdné
    for sec in material.sections:
        if sec.kind in (SECTION_KIND_QA, SECTION_KIND_DEFINITIONS) and sec.items and len(sec.items) < 2:
            warnings.append(f"Sekce „{sec.title}“ ({sec.kind}) má jen {len(sec.items)} položku")

    # 5) Příliš krátká paragraph (1 slovo)
    for sec in material.sections:
        if sec.kind == SECTION_KIND_PARAGRAPH:
            for item in sec.items:
                if isinstance(item, str) and len(item.split()) < 3:
                    warnings.append(
                        f"Sekce „{sec.title}“ (paragraph) má podezřele krátký odstavec: {item!r}"
                    )

    # 6) Topic prázdný
    if not material.topic:
        warnings.append("Topic je prázdný (nebude se třídit do podsložky)")

    # 7) Title triviální
    if not material.title or material.title in ("Studijní materiál", "Materiál"):
        warnings.append(f"Title vypadá generický: {material.title!r}")

    return warnings


def print_report(results: list[RunResult]) -> None:
    print("\n" + "=" * 78)
    print(" QUALITY CHECK REPORT")
    print("=" * 78)

    for res in results:
        print("\n" + "─" * 78)
        print(f" {res.label}  ×  {res.template_key}   ({res.elapsed_sec:.1f}s)")
        print("─" * 78)
        print(f"  Titul: {res.material.title}")
        print(f"  Téma:  {res.material.topic or '(prázdné)'}")
        print(f"  Sekcí: {len(res.material.sections)}   .docx: {res.docx_path.name}")

        if res.warnings:
            print("\n  ⚠  PROBLÉMY:")
            for w in res.warnings:
                print(f"     • {w}")

        print("\n  STRUKTURA:")
        for sec in res.material.iter_sections():
            print(f"    ▸ [{sec.kind}] „{sec.title}“ — {len(sec.items)} položek")
            for i, item in enumerate(sec.items[:3]):
                preview = _format_item_preview(item)
                # Trunc na 100 znaků
                if len(preview) > 110:
                    preview = preview[:107] + "…"
                print(f"        {i + 1}. {preview}")
            if len(sec.items) > 3:
                print(f"        … ({len(sec.items) - 3} dalších)")

    # Shrnutí
    print("\n" + "=" * 78)
    print(" SHRNUTÍ")
    print("=" * 78)
    total = len(results)
    with_warnings = sum(1 for r in results if r.warnings)
    print(f"  Volání AI:     {total}")
    print(f"  S problémy:    {with_warnings}/{total}")
    print(f"  Celkový čas:   {sum(r.elapsed_sec for r in results):.1f}s")
    if with_warnings == 0:
        print("\n  ✓ Vše OK — žádné detekované problémy.")
    else:
        print(
            f"\n  ⚠  {with_warnings} běh(ů) mělo varování. Doporučuju ručně zkontrolovat příslušné .docx."
        )


def _format_item_preview(item) -> str:
    if isinstance(item, list | tuple):
        if len(item) >= 2:
            return f"{item[0]} → {item[1]}"
        if item:
            return str(item[0])
        return "(prázdné)"
    return str(item)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=("sales", "teacher", "student", "all"), default="all")
    parser.add_argument("--out", type=Path, default=None, help="Výstupní složka (default = tmp)")
    args = parser.parse_args()

    api_key = get_gemini_api_key()
    if not api_key:
        print("CHYBA: Chybí Gemini API klíč (env GEMINI_API_KEY nebo keychain)")
        return 1

    out_dir = args.out or Path(tempfile.mkdtemp(prefix="hdt_qcheck_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Výstupní složka: {out_dir}")

    sales_tr = make_transcript("Schůzka s panem Novákem", SALES_TRANSCRIPT)
    teacher_tr = make_transcript("Dějepis, 8. třída — 1. světová válka", TEACHER_TRANSCRIPT)
    lecture_tr = make_transcript("Pasivní investování — přednáška", LECTURE_TRANSCRIPT)

    jobs: list[tuple[str, Transcript, str]] = []
    if args.only in ("sales", "all"):
        jobs += [
            ("sales", sales_tr, "sales_meeting"),
            ("sales", sales_tr, "sales_followup_email"),
            ("sales", sales_tr, "sales_objection_log"),
        ]
    if args.only in ("teacher", "all"):
        jobs += [
            ("teacher", teacher_tr, "teacher_lesson"),
            ("teacher", teacher_tr, "teacher_parent_summary"),
            ("teacher", teacher_tr, "teacher_next_lesson_plan"),
        ]
    if args.only in ("student", "all"):
        jobs += [
            ("lecture", lecture_tr, "student"),
            ("lecture", lecture_tr, "student_flashcards"),
            ("lecture", lecture_tr, "summary"),
        ]
    # Edge case — univerzální zápis aplikovaný na sales (ne TEDx — ten je monolog
    # a zápis by neměl smysl). Sales schůzka je víc-strannější interakce,
    # takže meeting_minutes by ji měl umět.
    if args.only == "all":
        jobs.append(("sales-as-meeting", sales_tr, "meeting_minutes"))

    # Gemini Free Tier má limit 5 req/min/model. Dávkujeme po 4, pauza 65 s.
    BATCH_SIZE = 4
    BATCH_PAUSE_SEC = 65
    results: list[RunResult] = []
    batches = [jobs[i : i + BATCH_SIZE] for i in range(0, len(jobs), BATCH_SIZE)]
    print(
        f"Spouštím {len(jobs)} AI volání v {len(batches)} dávkách po {BATCH_SIZE} "
        f"(Gemini Free Tier limit = 5/min)…"
    )

    for batch_idx, batch in enumerate(batches, start=1):
        if batch_idx > 1:
            print(f"\n  …pauza {BATCH_PAUSE_SEC} s kvůli rate-limitu Free Tier…")
            time.sleep(BATCH_PAUSE_SEC)
        print(f"\nDávka {batch_idx}/{len(batches)} ({len(batch)} volání):")
        with ThreadPoolExecutor(max_workers=len(batch)) as ex:
            future_map = {
                ex.submit(run_one, api_key, label, transcript, template_key, out_dir): (
                    label,
                    template_key,
                )
                for label, transcript, template_key in batch
            }
            for fut in as_completed(future_map):
                label, template_key = future_map[fut]
                try:
                    results.append(fut.result())
                    print(f"  ✓ {label} × {template_key}")
                except Exception as exc:
                    print(f"  ✗ {label} × {template_key}: {exc}")
                    results.append(
                        RunResult(
                            label=label,
                            template_key=template_key,
                            material=StudyMaterial(title="(selhalo)"),
                            docx_path=Path("/dev/null"),
                            elapsed_sec=0.0,
                            warnings=[f"AI volání selhalo: {exc}"],
                        )
                    )

    # Seřadit podle (label, template_key) pro stabilní výpis
    results.sort(key=lambda r: (r.label, r.template_key))
    print_report(results)

    # Také dump JSON pro programatický check
    json_path = out_dir / "_report.json"
    json_path.write_text(
        json.dumps(
            [
                {
                    "label": r.label,
                    "template_key": r.template_key,
                    "title": r.material.title,
                    "topic": r.material.topic,
                    "sections": [
                        {"title": s.title, "kind": s.kind, "items_count": len(s.items)}
                        for s in r.material.iter_sections()
                    ],
                    "warnings": r.warnings,
                    "elapsed_sec": r.elapsed_sec,
                    "docx": str(r.docx_path),
                }
                for r in results
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nJSON raport: {json_path}")
    return 0 if all(not r.warnings for r in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
