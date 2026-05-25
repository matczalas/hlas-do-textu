# První spuštění aplikace Hlas do textu

Tento návod tě provede prvním spuštěním aplikace na Windows. Trvá to cca 10 minut.

## 1. Instalace

1. Stáhni si `HlasDoTextu-Setup-X.Y.Z.exe` z [Releases](https://github.com/safe4future/hlas-do-textu/releases).
2. Dvojklikem ho spusť.

### Pokud se objeví hláška "Windows protected your PC"

Tato hláška se objeví u aplikací, které nejsou digitálně podepsané (placený certifikát).
Aplikace je bezpečná — pochází přímo od Safe4Future.

1. Klikni na malé **"More info"** uprostřed dialogu.
2. Klikni na **"Run anyway"** vpravo dole.

Tuto hlášku uvidíš jen jednou — při první instalaci.

## 2. Získej Gemini API klíč (zdarma)

**Nejrychlejší cesta:** v uvítacím dialogu (objeví se při prvním spuštění) klikni na velké modré tlačítko **🔗 Získat API klíč zdarma**. Otevře se ti tvůj prohlížeč přímo na stránce, kde si klíč vytvoříš.

Tlačítko **Získat klíč…** je i v okně **Nastavení** — kdykoliv ho můžeš znovu otevřít.

Detailní postup s obrázky: [ZISKAT_GEMINI_KLIC.md](ZISKAT_GEMINI_KLIC.md).

Klíč vypadá takhle: `AIza...` (asi 40 znaků).

> **Bez klíče** můžeš aplikaci používat jen s lokální Ollama AI — viz [INSTALACE_OLLAMA.md](INSTALACE_OLLAMA.md).

## 3. První spuštění

1. Otevři **Hlas do textu** ze Start menu nebo plochy.
2. Objeví se uvítací dialog. Vlož svůj Gemini klíč a zaškrtni souhlas.
3. Aplikace nabídne stažení Whisper modelu (~770 MB). **Klikni Ano** — stáhne se jen jednou.
   - Stahování trvá podle rychlosti internetu 2-10 minut.
   - Soubor se uloží do `C:\Users\<tvoje jméno>\AppData\Local\HlasDoTextu\models\`.

## 4. Použití

1. **Přidej nahrávku přednášky** — `.mp4`, `.wav`, `.mp3`, `.m4a`. Můžeš přetáhnout do okna nebo použít tlačítko **+ Přidat nahrávku**.
2. **(Volitelně) Přidej prezentaci** — `.pdf` nebo `.pptx`. Tlačítko **+ Přidat slidy**.
3. Můžeš nahrát víc souborů najednou (např. dvě části přednášky + slidy). Aplikace je zpracuje dohromady do jednoho dokumentu.
4. U každého souboru můžeš **upravit štítek** (kliknutím na text ve sloupci "Štítek"). Štítek pomáhá AI propojit nahrávky se slidy.
5. Do políčka **Popis / instrukce pro AI** napiš pár vět:
   - Co je to za přednášku (předmět, téma)
   - Co od materiálu očekáváš (body ke zkoušce? souhrn? definice pojmů?)
6. Klikni **▶ Spustit zpracování**.
7. Postup se zobrazuje v progress baru. Hodina přednášky se přepisuje **60-90 minut** na běžném notebooku (model `medium`).
8. Po dokončení aplikace nabídne **otevřít hotový Word dokument**.

## 5. Kde najdu výsledek?

Default: `C:\Users\<tvoje jméno>\Documents\HlasDoTextu\`

Soubory mají název ve formátu `<titul>_2026-05-25_15-30.docx`.

Cestu změníš v **Nastavení → Výstupní složka**.

## 6. Když něco selže

| Hláška | Co s tím |
|---|---|
| "Chybí API klíč pro Gemini" | Otevři Nastavení a vlož klíč. |
| "Gemini: vyčerpaný limit" | Free tier má 1500 dotazů denně. Počkej do zítřka, nebo si nainstaluj Ollama (viz [INSTALACE_OLLAMA.md](INSTALACE_OLLAMA.md)). |
| "Lokální Ollama není dostupná" | Ollama není nainstalovaná nebo neběží. Buď ji nainstaluj, nebo nech aplikaci používat Gemini. |
| "Málo místa na disku" | Uvolni alespoň 2 GB. |
| "FFmpeg selhal" | Vstupní soubor je poškozený. Otestuj přehráním v jiném playeru. |

## 7. Bezpečnost a soukromí

- **Audio se neodesílá nikam** — přepis probíhá lokálně na tvém PC.
- **Text přepisu se odesílá do Google Gemini** (pokud používáš Gemini). Free tier Gemini používá data k tréninku modelů — pro běžné školní materiály to není problém, ale pro citlivé obsahy (nepublikovaný výzkum, interní podnikové údaje) použij offline Ollama.
- **API klíč** se ukládá bezpečně do Windows Credential Manager — není v textovém souboru.
- **Vygenerované dokumenty** zůstávají na tvém PC.

## 8. Odinstalace — když se aplikace nelíbí

Aplikace jde **snadno smazat**, nezůstanou žádné zbytky:

**Cesta 1 (doporučeno):**
1. Start menu → **Hlas do textu** → **Odinstalovat Hlas do textu**.
2. Objeví se otázka: *"Smazat také tvoje stažené Whisper modely a nastavení?"*
3. Klikni **Ano** — aplikace se kompletně smaže, včetně cca 1 GB modelů v AppData.
4. Hotovo. Disk je čistý, jako by aplikace nikdy neexistovala.

**Cesta 2 (přes Windows Settings):**
1. Win + I → **Apps** → **Installed apps** → **Hlas do textu** → **Uninstall**.
2. Stejný dialog jako výše.

**Co se smaže při kliknutí Ano:**
- Aplikace v `C:\Users\<jméno>\AppData\Local\Programs\HlasDoTextu\`
- Stažené Whisper modely v `C:\Users\<jméno>\AppData\Local\HlasDoTextu\models\`
- Konfigurace (nastavení výstupní složky, model, atd.)
- Logy
- Uložený Gemini API klíč v Windows Credential Manager

**Co se nesmaže:**
- Vygenerované Word dokumenty v `Dokumenty/HlasDoTextu/` — ty máš ve svých souborech, ničí se s nimi.

> Pokud klikneš **Ne** v dotazu o smazání modelů, modely zůstanou — užitečné, kdybys aplikaci chtěla znovu nainstalovat (model už bude na disku).
