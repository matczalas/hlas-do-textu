# Design Brief — Hlas do textu

## 1) Co tohle je

Desktopová Windows aplikace pro **české studenty**. Studentka nahraje záznam přednášky (audio nebo video) a aplikace z toho:

1. Vyrobí **přepis** mluveného slova (lokálně, Whisper)
2. Pomocí **AI (Gemini)** z přepisu udělá strukturované **studijní body**
3. Uloží do **Word dokumentu** (.docx)

**Cílový uživatel:** mladá vysokoškolská studentka, není technicky zdatná, používá Windows notebook. Aplikace má být na první pohled jasná, hezká, příjemná. Není to "pro vývojáře", je to **pro studenta**.

**Stack:** Python 3.11 + PySide6 (Qt 6). Spouští se jako `.exe` na Windows.

## 2) Co od tebe chceme

**Předělej UI tak, aby vypadalo moderně a přátelsky** — místo aktuálního utilitárního Qt-default vzhledu. Inspirace:

- **Notion, Linear, ChatGPT desktop, Cursor** — čisté, prostorové, dobré typografie
- **Vibrant accent color** — modrá Safe4Future #205ca8 jako primární
- **Native dark mode podpora** — palette(text/window/...) Qt rolí
- **Velkorysé padding, jasná hierarchie**
- **Žádné staré Windows-styled controls**

**Konkrétně máme tyto views (viz screenshoty):**

1. **First-run welcome dialog** (`first_run_dialog.py`) — uvítací modal s nabídkou Gemini klíče
2. **Empty state** (`empty_state.py`) — 4-step tutoriál když ještě nic není nahrané
3. **Hlavní okno** (`main_window.py`) — drop zóna, tabulka souborů, popis, status, progress, dva spouštěcí tlačítka
4. **Settings dialog** (`settings_dialog.py`) — API klíč, model, output složka, souhlasy
5. **Source table** (`source_table.py`) — tabulka 5 sloupců (#, soubor, typ, štítek, odebrat)
6. **Progress panel** (`progress_panel.py`) — status label + progress bar + log s živým přepisem

## 3) Tvrdá pravidla — TOHLE NEMĚŇ

- ❌ **Žádné nové dependence** — drž se `PySide6`, `loguru`, žádné `qtawesome`, `qfluentwidgets`, atd. (ovlivnilo by to PyInstaller velikost)
- ❌ **Neměň business logiku** v `core/` — to není v briefu
- ❌ **Neměň názvy Signal/Slot ani veřejných metod** widgetů (např. `FileDropZone.sources_added`, `SourceTable.files_changed`, `ProgressPanel.cancel_button` musí zůstat)
- ❌ **Neměň entry point** `main_window.MainWindow.__init__()` chování — settings, workers atd. už jsou napojené
- ❌ **Žádné `setStyleSheet` v `core/`** — jen v `gui/`
- ❌ **Drž se palette() v stylesheets** kde to jde — aby fungovalo dark i light mode
- ❌ **Žádné absolute size** — používej layouts a stretch factory

## 4) Co můžeš měnit

- ✅ Styly (QSS, palette tweaks), font sizes, paddings, marginy, barvy
- ✅ Strukturu uvnitř widgetů — nové sub-widgety, kontejnery, layouts
- ✅ Vlastní `QPainter` paint events pokud chceš
- ✅ Animace (QPropertyAnimation) — pokud nebudou ztěžovat ovládání
- ✅ Vlastní ikony — pouze pokud je nakreslíš v Pythonu (např. přes `QPainter` nebo SVG inline string)
- ✅ Nové helper třídy v `gui/widgets/` — když pomůžou
- ✅ Můžeš přidat **`gui/styles/app.qss`** s globálním stylem (už existuje placeholder)

## 5) Detaily, které máš zachovat

### Texty
**Vše musí být česky.** Existující texty (např. "Sem přetáhni nahrávky nebo prezentace", "Jak začít", "Přidat nahrávku") můžeš upravit pro jasnější vyznění, ale **musí zůstat česky** a pro studentku srozumitelné.

### Tlačítka v hlavním okně
Dvě spouštěcí tlačítka mají různé sémantické významy:
- **Jen přepis** = rychlé, offline, výstup = jen Word s plným přepisem. Zvýrazni jako sekundární akci.
- **Přepis + body z AI** = plný flow s AI. Primární CTA. Modré.

### Status indikátory
`StatusBar` ukazuje 2 řádky: **Gemini:** ✅/❌ a **Ollama:** ✅/❌. Když je některý nedostupný, mělo by být jasné že to je OK / má alternativu.

### Drop zóna
Vizuálně musí být jasné že **lze přetáhnout soubor**. Aktivní state (když user tahá soubor) má visuálně zvýraznit, že "tady to pusť".

### GDPR checkbox (žlutý box)
Když uživatel souhlasí s odesláním textu do Gemini → souhlas musí být **vědomě zaškrtnutý**, ne lehce přehlédnutelný. Žlutá barva pozadí je OK, ale text musí být čitelný.

### Tutoriál (empty state)
Když není žádný soubor nahraný, ukázat 4 kroky:
1. Přidej nahrávku
2. Přidej slidy (volitelné)
3. Napiš popis (jen pro AI režim)
4. Vyber režim a spusť

Tohle je první co studentka uvidí. Mělo by ji to **vést za ruku**.

## 6) Soubory v této složce

- `BRIEF.md` ← jsi tady
- `CONSTRAINTS.md` — detailní seznam API kontraktů (signály/sloty/veřejné metody)
- `screenshots/` — 4 PNG screenshoty aktuálního UI
- `current_code/` — Python soubory widgetů, které máš redesignovat

## 7) Co od tebe chci jako výstup

**Pro každý widget, který upravuješ:**
- Vytvoř **artifact** s celým novým souborem (ne diff, kompletní obsah `.py`)
- Pojmenuj artifact stejně jako původní soubor: `empty_state.py`, `main_window.py`, atd.
- Pokud přidáš nový widget, dej mu samostatný artifact

**Po všech artifactech přidej krátký souhrn:**
- Co jsi změnil a proč (1-2 odstavce na widget)
- Pokud jsi přidal nový soubor, jak ho zařadit
- Pokud potřebuješ změnu v `pyproject.toml` nebo někde jinde, zmínit (i když by to mělo být ne)

## 8) Volný prostor pro tebe

**Jestli máš nápad na něco co tady není zmíněno** (lepší animace, nový widget, micro-interakce, lepší typografie, jiná organizace layoutu), **prosím navrhni**. Jsi v roli senior designerky která rozumí UX. Já jsem programátorka která tě naslouchá.

Hlavní princip: **študentka tu aplikaci uvidí v dlouhé minuty když přepisuje hodinovou přednášku. Ať se na to ráda dívá.**
