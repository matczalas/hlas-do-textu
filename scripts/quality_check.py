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
    SECTION_KIND_DEFINITIONS,
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


# --- Podcast: segmenty s časem (kapitoly/citáty potřebují [mm:ss]) ----------
PODCAST_SEGMENTS: list[tuple[float, str, str]] = [
    (0, "Mluvčí 1", "Vítejte u podcastu Hlavou napřed. Dneska je mým hostem Petra Línková, která vede neziskovku Druhý břeh a deset let pracovala v korporátu."),
    (18, "Mluvčí 2", "Díky za pozvání. Jo, deset let v bance, pak jsem to celé otočila."),
    (35, "Mluvčí 1", "Pojďme rovnou k tomu zlomu. Co se stalo?"),
    (48, "Mluvčí 2", "Vyhořela jsem. A nejhorší na tom bylo, že jsem to půl roku nikomu neřekla. Dneska vím, že mlčení je u vyhoření to nejdražší rozhodnutí."),
    (95, "Mluvčí 1", "Mlčení je nejdražší rozhodnutí — to je silná věta."),
    (110, "Mluvčí 2", "Je to tak. Spočítala jsem si pak, že mě těch šest měsíců stálo víc než celá terapie potom."),
    (150, "Mluvčí 1", "Jak ses dostala k neziskovce?"),
    (165, "Mluvčí 2", "Přes dobrovolničení. Začala jsem o sobotách doučovat děti z dětského domova matematiku. A poprvé po letech jsem v neděli večer neměla úzkost."),
    (230, "Mluvčí 1", "Druhý břeh dneska pomáhá dětem z dětských domovů s přechodem do dospělosti. Kolik vás je?"),
    (245, "Mluvčí 2", "Šest zaměstnanců, čtyřicet dobrovolníků. A letos jsme doprovodili sto dvacet dětí."),
    (290, "Mluvčí 1", "Co bys poradila lidem, kteří cítí, že jsou tam, kde jsi byla ty v té bance?"),
    (310, "Mluvčí 2", "Neskákejte hned. Začněte malým krokem vedle práce — dobrovolničení je nejlevnější způsob, jak si vyzkoušet jiný život. A řekněte to nahlas někomu blízkému."),
    (370, "Mluvčí 1", "Kde vás lidi najdou?"),
    (380, "Mluvčí 2", "Druhybreh.cz, a hledáme teď dobrovolníky v Brně a Ostravě."),
    (400, "Mluvčí 1", "Petro, díky moc. A vám díky za poslech, odebírejte nás kdekoli posloucháte podcasty."),
]

TEAM_TRANSCRIPT = """\
Mluvčí 1: Tak, pondělní porada. Lukáši, začni ty — jak vypadá web?
Mluvčí 2: Nová verze je na testu. Zbývá opravit formulář, mám to do středy. Ale potřebuju od Báry finální texty.
Mluvčí 3: Texty pošlu zítra dopoledne, zbývá mi poslední stránka. Jinak hlásím, že newsletter měl otevíranost třicet dva procent, nejvíc letos.
Mluvčí 1: Super. Já jsem včera mluvil s tiskárnou — letáky budou o týden později, až dvacátého. Musíme posunout rozvoz.
Mluvčí 2: To je problém, dvacátého je akce v Plzni.
Mluvčí 1: Dobře, tak rozhodneme: na Plzeň vytiskneme sto kusů nouzově na naší tiskárně a zbytek počká na zásilku. Souhlas?
Mluvčí 3: Souhlas.
Mluvčí 2: Jo.
Mluvčí 1: Bára zařídí nouzový tisk do pátku. A poslední věc — rozpočet na příští rok. To dneska nestihneme, dáme si na to samostatnou schůzku příští úterý ve dvě.
Mluvčí 3: Ještě rychle — ozvala se ta firma ohledně sponzoringu, chtějí schůzku. Pošlu vám termíny.
Mluvčí 1: Dobře, to si vezmu já. Díky, končíme.
"""

WORKSHOP_TRANSCRIPT = """\
Lektor: Dobrý den, vítejte na školení Canva pro neziskovky. Dnes se naučíte tři věci: šablony, brand kit a plánování příspěvků.
Lektor: Začneme šablonami. Krok jedna — v levém menu kliknete na Šablony. Krok dva — do vyhledávání napište třeba „instagram post nonprofit". Krok tři — vyberete šablonu a kliknete Přizpůsobit.
Lektor: Důležité pravidlo: nikdy neměňte víc než dvě věci najednou — barvu a text. Když změníte i font a rozložení, ztratí to konzistenci.
Účastník 1: A co když nám šablona nesedí barevně k logu?
Lektor: Skvělá otázka — na to je brand kit. V nastavení nahrajete logo a definujete dvě hlavní barvy a jeden font. Canva pak šablony automaticky přebarvuje. Pozor, brand kit je v placené verzi, ale neziskovky mají Canva Pro zdarma — žádost se podává přes canva.com/canva-for-nonprofits, schválení trvá asi týden.
Účastník 2: Jak dlouho dopředu plánovat příspěvky?
Lektor: Doporučuji dva týdny. V Canvě je na to Content Planner — tlačítko kalendáře vlevo. Nastavíte datum, čas a síť. A poslední tip: exportujte vždycky v PNG, ne JPG, texty jsou pak ostřejší.
Lektor: Domácí úkol: založte brand kit a naplánujte tři příspěvky. Materiály vám pošlu mailem, je tam i odkaz na můj návod na YouTube — kanál Grafika pro dobro.
"""

PHONE_TRANSCRIPT = """\
Mluvčí 1: Dobrý den, pane Dvořáku, tady Novotná z pojišťovny. Volám kvůli té nabídce životního pojištění, co jsem vám posílala minulý týden.
Mluvčí 2: Dobrý den. Jo, koukal jsem na to. Ta varianta za dvanáct set měsíčně vypadá rozumně, ale chtěl bych vědět, co přesně kryje ta invalidita.
Mluvčí 1: Invalidita je krytá od druhého stupně, plnění milion dvě stě. Můžu vám poslat tabulku s detaily.
Mluvčí 2: Pošlete. A ještě — kdybych to podepsal, od kdy by to platilo?
Mluvčí 1: Od prvního dne dalšího měsíce, takže od prvního července. Pošlu vám tabulku dnes a zavolám v pátek dopoledne, jestli vám to bude dávat smysl?
Mluvčí 2: Pátek dopoledne je dobrý, ale až po desáté.
Mluvčí 1: Domluveno, v pátek po desáté. Děkuju, mějte se hezky.
"""

PARENT_TRANSCRIPT = """\
Mluvčí 1: Dobrý den, paní Horáková, děkuju, že jste přišla. Chtěla jsem s vámi probrat Matěje — poslední dva měsíce se zhoršil v matematice a párkrát nepřinesl úkol.
Mluvčí 2: Dobrý den. Já vím, doma je to teď složitější, s manželem jsme se rozešli a Matěj to nese špatně.
Mluvčí 1: To mě mrzí, děkuju za otevřenost. Ve škole je jinak v pohodě, s dětmi vychází. Jen ta matematika — navrhuju doučování, máme ho ve čtvrtek po vyučování zdarma.
Mluvčí 2: To by mohl zvládnout, čtvrtky má volné. Promluvím s ním.
Mluvčí 1: Skvělé. Já dám vědět kolegyni, která doučování vede, že Matěj přijde. A domluvme se, že si zavoláme za měsíc, jak to jde — kolem patnáctého ledna?
Mluvčí 2: Ano, klidně. A kdyby něco, můžu napsat přes Bakaláře?
Mluvčí 1: Určitě, odpovídám do druhého dne. A Matějovi prosím zatím neříkejte, že jsme řešily i tu situaci doma — řekla jsem mu jen, že jde o matematiku.
"""

HR_INTERVIEW_TRANSCRIPT = """\
Mluvčí 1: Dobrý den, Tomáši, posaďte se. Já jsem Lenka z HR a tohle je pohovor na pozici provozního koordinátora.
Mluvčí 2: Dobrý den, děkuju za pozvání.
Mluvčí 1: Začneme zkušenostmi. Co jste dělal poslední tři roky?
Mluvčí 2: Koordinoval jsem logistiku v e-shopu Zelená bedýnka. Měl jsem na starost sklad, tři kurýry a plánování rozvozů. Když jsem nastoupil, rozvozy nabíraly hodinová zpoždění, zavedl jsem nové plánování tras a do půl roku jsme jeli na devadesát osm procent včasnosti.
Mluvčí 1: Jak jste to konkrétně udělal?
Mluvčí 2: Přešli jsme z ručního plánování na Routigo a změnil jsem rozvozová okna z hodinových na dvouhodinová. Kurýrům se uvolnily ruce a zákazníkům to nevadilo, měřili jsme spokojenost.
Mluvčí 1: Proč odcházíte?
Mluvčí 2: Firma se stěhuje do Kolína a to už nedojedu. Jinak bych zůstal.
Mluvčí 1: U nás byste měl na starost i rozpočet, asi dva miliony ročně. Máte zkušenost s penězi?
Mluvčí 2: Přiznám se, že rozpočet jsem nikdy celý nedržel, jen jsem schvaloval faktury do dvaceti tisíc. Tam bych se potřeboval zaučit.
Mluvčí 1: Dobře, to je fér. Jaká je vaše představa o nástupu a penězích?
Mluvčí 2: Nástup můžu od září, výpovědní lhůta mi končí v srpnu. Představa je čtyřicet pět tisíc hrubého.
Mluvčí 1: Rozumím. Další kolo by bylo s provozním ředitelem, ozveme se do týdne. Připravte si prosím krátkou ukázku, jak byste naplánoval rozvozový den u nás.
"""

HR_REVIEW_TRANSCRIPT = """\
Mluvčí 1: Aničko, pojďme na roční hodnocení. Jak bys sama zhodnotila letošek?
Mluvčí 2: Povedl se mi web — nová verze byla včas a návštěvnost vzrostla o čtvrtinu. Co se nepovedlo, je dokumentace, tu jsem flákala, přiznávám.
Mluvčí 1: Souhlasím s obojím. Web hodnotím jako tvůj největší úspěch, klient byl nadšený. K dokumentaci — vadí mi to hlavně proto, že po tobě nikdo nemůže převzít projekt. Příští rok chci, aby každý projekt měl aspoň základní readme do týdne od předání.
Mluvčí 2: To je fér. Já bych za sebe chtěla víc designové práce, baví mě to víc než kódování.
Mluvčí 1: Dobře, domluvme se: od ledna ti dám design menších zakázek, začneme jednou za měsíc. A pošlu tě na kurz UX, ten dvoudenní od Czechitas, zaplatíme.
Mluvčí 2: Super, díky. A plat?
Mluvčí 1: Od ledna ti zvedám o tři tisíce. A když dotáhneš tu dokumentaci za první kvartál, v dubnu se pobavíme znovu.
"""

HR_EXIT_TRANSCRIPT = """\
Mluvčí 1: Marku, díky, že sis udělal čas na exit pohovor. Proč odcházíš?
Mluvčí 2: Hlavní důvod jsou peníze — dostal jsem nabídku o patnáct tisíc vyšší. Ale upřímně, kdyby to bylo jen o penězích, asi bych vyjednával. Druhá věc je, že jsem se rok nikam neposunul. Sliboval se mi seniorní projekt a pořád jsem dělal údržbu.
Mluvčí 1: Co u nás fungovalo?
Mluvčí 2: Tým je skvělý, atmosféra taky. A oceňuju flexibilitu, když syn marodil, nikdy s tím nebyl problém.
Mluvčí 1: A co bys změnil?
Mluvčí 2: Plánování. Priority se mění každý týden a člověk nikdy nedodělá věc do konce. A jak říkám — kariérní růst. Po dvou letech nevím, co mám udělat, abych se posunul. To bych na vašem místě řešil první.
Mluvčí 1: Co předáváš a komu?
Mluvčí 2: Server módu předám Filipovi, máme sraz ve čtvrtek. Dokumentaci k API jsem dopsal minulý týden. Zbývá přístupová hesla — předám je IT poslední den.
"""

HR_ONE_ON_ONE_TRANSCRIPT = """\
Mluvčí 1: Tak co, Katko, jak bylo tenhle měsíc?
Mluvčí 2: Celkem dobře, kampaň jsme stihli. Ale potřebuju si postěžovat na schvalování — čekám na tebe někdy i tři dny a pak hořím.
Mluvčí 1: Fér. Domluvme se, že věci do pěti tisíc schvaluješ sama a já jen velké věci, do druhého dne. Zkusíme měsíc?
Mluvčí 2: To by hodně pomohlo. A ještě — chtěla bych na konferenci Marketing Festival, je v listopadu, lístek stojí osm tisíc.
Mluvčí 1: Schvaluju, objednej si. Já mám jednu věc — příští týden přebíráš stážistku, provedeš ji prvním týdnem. Připrav jí prosím plán na první tři dny.
Mluvčí 2: Dobře, připravím do pátku.
"""

COACH_TRANSCRIPT = """\
Mluvčí 1: Dobrý den, Jano. Tohle je naše první sezení, tak mi řekněte — s čím přicházíte?
Mluvčí 2: Potřebuju se rozhodnout, jestli vzít nabídku na vedoucí pozici. Mám z toho strach, ale zároveň cítím, že když ji nevezmu, budu litovat.
Mluvčí 1: Co konkrétně vás na té pozici láká?
Mluvčí 2: Možnost věci měnit. Šest let koukám, jak se rozhoduje špatně, a říkám si, že bych to uměla líp. A taky peníze, samozřejmě.
Mluvčí 1: A ten strach — z čeho přesně je?
Mluvčí 2: Že zklamu. Že na to nemám. Hlavně vedení lidí — nikdy jsem nikoho nevedla a teď bych měla osm lidí, včetně dvou kolegů, co jsou starší než já... Vlastně když to říkám nahlas, tak ten strach není z práce, ale z toho, co si o mně pomyslí ostatní.
Mluvčí 1: To je důležité rozlišení. Kdybyste si měla představit sebe za rok v té roli a daří se vám — jak to vypadá?
Mluvčí 2: Tým funguje, lidi za mnou chodí pro radu, a já večer nemyslím na práci. To poslední je vlastně podmínka.
Mluvčí 1: Dobře. Co byste potřebovala vědět nebo udělat, abyste se rozhodla do konce měsíce?
Mluvčí 2: Promluvit si s těmi dvěma staršími kolegy. Jejich reakce je můj největší strašák. A zeptat se šéfa, jestli můžu dostat mentora na vedení lidí.
Mluvčí 1: Takže dva kroky do příštího sezení — rozhovor s kolegy a otázka na mentoring. Souhlasí?
Mluvčí 2: Souhlasí. Sejdeme se za čtrnáct dní.
Mluvčí 1: A budeme pokračovat každé dva týdny, online, padesát minut, jak jsme se domluvili v mailu.
"""

SPOLEK_TRANSCRIPT = """\
Mluvčí 1: Zahajuji výroční členskou schůzi spolku Zelený vnitroblok. Přítomno je čtrnáct členů z dvaceti dvou, schůze je usnášeníschopná. Zapisovatelkou navrhujeme Moniku. Kdo je pro? Čtrnáct pro, nikdo proti. Schváleno.
Mluvčí 1: Bod jedna — zpráva o činnosti. Letos jsme uspořádali šest brigád, vysadili dvanáct stromů a obnovili dětské hřiště. Sousedské slavnosti se zúčastnilo asi dvě stě lidí.
Mluvčí 2: K hřišti — dostali jsme dotaci od městské části sedmdesát tisíc, celkové náklady byly devadesát pět tisíc, zbytek šel z členských příspěvků.
Mluvčí 1: Děkuji. Bod dva — hospodaření. Příjmy letos sto čtyřicet tisíc, výdaje sto dvacet tisíc, zůstatek na účtu osmdesát tři tisíce.
Mluvčí 3: Mám dotaz — kolik z výdajů byla ta slavnost?
Mluvčí 2: Osmnáct tisíc, z toho deset pokrylo vstupné z bazaru.
Mluvčí 1: Hlasujeme o schválení hospodaření. Pro třináct, proti nikdo, zdržel se jeden. Usnesení přijato.
Mluvčí 1: Bod tři — plán na příští rok. Navrhujeme: jarní výsadbu květinových záhonů, opravu laviček a žádost o grant na komunitní kompostér. Hlasujeme. Pro čtrnáct, jednohlasně přijato.
Mluvčí 3: Ještě navrhuju zvýšit členský příspěvek z tří set na čtyři sta korun.
Mluvčí 1: Hlasujeme o zvýšení příspěvku. Pro osm, proti pět, zdržel se jeden. Usnesení přijato těsnou většinou.
Mluvčí 1: Úkoly: Monika podá žádost o grant na kompostér do konce ledna. Pavel zajistí cenové nabídky na opravu laviček do příští schůze. Příští schůze bude v březnu, termín upřesníme mailem. Děkuji, končím schůzi.
"""

REALTY_VIEWING_TRANSCRIPT = """\
Mluvčí 1: Dobrý den, vítejte. Tak tohle je ten byt tři plus jedna na Vinohradech, čtvrté patro s výtahem, sedmdesát osm metrů.
Mluvčí 2: Dobrý den. Hezky vysoké stropy. Manželka se ptala — okna jsou do ulice, nebo do dvora?
Mluvčí 1: Ložnice a dětský pokoj do dvora, obývák do ulice. Ulice je ale klidná, jednosměrka.
Mluvčí 2: Kuchyň je menší, než vypadala na fotkách. A koupelna — to je původní jádro?
Mluvčí 1: Ano, jádro je původní, s tím počítá i cena. Rekonstrukce jádra vyjde zhruba na čtyři sta tisíc.
Mluvčí 2: Hm. A jak je to s vytápěním? Viděl jsem v inzerátu dálkové.
Mluvčí 1: Ano, dálkové, náklady asi dva a půl tisíce měsíčně i s ohřevem vody. Fond oprav je třináct set.
Mluvčí 2: Cena je devět dvě stě? Při tom stavu jádra bych čekal devět rovných... Jinak se mi byt líbí, dispozice je super a lokalita přesně ta, co hledáme.
Mluvčí 1: Rozumím. Majitel je na jednání o ceně připravený, ale spíš v řádu nižších desítek tisíc. Doporučuju: přijďte se podívat ještě jednou s manželkou, klidně tento týden, a pak se pobavíme o nabídce.
Mluvčí 2: Dobře, zkusím čtvrtek odpoledne. A poslal byste mi prohlášení vlastníka a poslední vyúčtování?
Mluvčí 1: Pošlu dnes večer mailem. Čtvrtek v pět by šel?
Mluvčí 2: Platí.
"""

REALTY_LISTING_TRANSCRIPT = """\
Mluvčí 1: Tak, paní Beránková, projdeme si byt kvůli inzerátu. Diktuju si: dva plus kk, Brno-Žabovřesky, ulice Minská, třetí patro bez výtahu, padesát čtyři metrů, balkon tři metry, sklep.
Mluvčí 2: Ano. A loni jsme měnili okna, to tam napište, plastová s trojsklem.
Mluvčí 1: Píšu. Kuchyň je z roku dvacet dvacet, vestavěné spotřebiče. Koupelna po rekonstrukci?
Mluvčí 2: Koupelna před pěti lety, sprchový kout. Topení je plynový kotel, vlastní, tři roky starý.
Mluvčí 1: Vlastnictví osobní, bez hypotéky?
Mluvčí 2: Osobní. Hypotéka tam je, zbývá osm set tisíc, ale chceme ji doplatit z prodeje.
Mluvčí 1: To je běžné, vyřešíme přes úschovu. Cenu jsme říkali šest milionů čtyři sta. Já doporučuju nasadit šest pět a nechat prostor na jednání.
Mluvčí 2: Dobře, věřím vám. Ale nechci to prodávat déle než do léta.
Mluvčí 1: Rozumím, do léta je realistické. Exkluzivitu podepíšeme na tři měsíce, provize tři procenta včetně právního servisu, jak jsme se bavili po telefonu.
Mluvčí 2: Ano, s tím počítám.
Mluvčí 1: Budu potřebovat: průkaz energetické náročnosti — zařídím já, vyúčtování energií za loňský rok a od vás dvě hodiny na focení, ideálně příští týden dopoledne. A ukliďte prosím balkon, fotí se i ten.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_transcript(
    label: str,
    text: str,
    segments: list[tuple[float, str, str]] | None = None,
) -> Transcript:
    """Vyrobí Transcript ze statického textu.

    `segments` = list (start_sec, speaker, text) — nutné pro šablony s časovými
    značkami (podcast_chapters/quotes), kde router vkládá [mm:ss] z segmentů.
    Bez segmentů vznikne jediný segment na 0 s.
    """
    if segments:
        segs = [
            TranscriptSegment(start=s, end=s + 5.0, text=t, speaker=sp)
            for s, sp, t in segments
        ]
        duration = max(s for s, _, _ in segments) + 30.0
        full_text = "\n".join(
            (f"{sp}: {t}" if sp else t) for _, sp, t in segments
        )
        return Transcript(
            source_label=label, language="cs", duration_sec=duration,
            text=full_text, segments=segs,
        )
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
    parser.add_argument(
        "--only",
        choices=("sales", "teacher", "student", "v112", "v113", "all", "new"),
        default="all",
        help="'new' = v112+v113 (šablony zatím neověřené živým testem)",
    )
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

    # --- v1.12: podcast + univerzální/rolové přídavky ---
    if args.only in ("v112", "new", "all"):
        podcast_tr = make_transcript("Podcast — Petra Línková", "", segments=PODCAST_SEGMENTS)
        team_tr = make_transcript("Pondělní porada", TEAM_TRANSCRIPT)
        workshop_tr = make_transcript("Školení Canva", WORKSHOP_TRANSCRIPT)
        phone_tr = make_transcript("Telefonát — pojištění", PHONE_TRANSCRIPT)
        parent_tr = make_transcript("Konzultace — Matěj", PARENT_TRANSCRIPT)
        jobs += [
            ("podcast", podcast_tr, "podcast_shownotes"),
            ("podcast", podcast_tr, "podcast_chapters"),
            ("podcast", podcast_tr, "podcast_quotes"),
            ("podcast", podcast_tr, "podcast_article"),
            ("podcast", podcast_tr, "podcast_interview_qa"),
            ("team", team_tr, "team_meeting"),
            ("workshop", workshop_tr, "workshop_training"),
            ("phone", phone_tr, "sales_phone_call"),
            ("parent", parent_tr, "teacher_parent_meeting"),
        ]

    # --- v1.13: HR, kouč, spolky, realitky ---
    if args.only in ("v113", "new", "all"):
        hr_int_tr = make_transcript("Pohovor — koordinátor", HR_INTERVIEW_TRANSCRIPT)
        hr_rev_tr = make_transcript("Roční hodnocení — Anička", HR_REVIEW_TRANSCRIPT)
        hr_exit_tr = make_transcript("Exit — Marek", HR_EXIT_TRANSCRIPT)
        hr_oo_tr = make_transcript("1:1 — Katka", HR_ONE_ON_ONE_TRANSCRIPT)
        coach_tr = make_transcript("Koučink — Jana, vstupní", COACH_TRANSCRIPT)
        spolek_tr = make_transcript("Výroční schůze — Zelený vnitroblok", SPOLEK_TRANSCRIPT)
        view_tr = make_transcript("Prohlídka — Vinohrady 3+1", REALTY_VIEWING_TRANSCRIPT)
        list_tr = make_transcript("Náběr — Žabovřesky 2+kk", REALTY_LISTING_TRANSCRIPT)
        jobs += [
            ("hr", hr_int_tr, "hr_interview"),
            ("hr", hr_rev_tr, "hr_performance_review"),
            ("hr", hr_exit_tr, "hr_exit_interview"),
            ("hr", hr_oo_tr, "hr_one_on_one"),
            ("coach", coach_tr, "coach_session"),
            ("coach", coach_tr, "coach_first_session"),
            ("coach", coach_tr, "coach_next_prep"),
            ("spolek", spolek_tr, "spolek_meeting"),
            ("spolek", spolek_tr, "spolek_agenda"),
            ("spolek", spolek_tr, "spolek_annual_report"),
            ("realty", view_tr, "sales_property_viewing"),
            ("realty", list_tr, "sales_property_listing"),
        ]

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
