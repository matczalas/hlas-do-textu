# Jak používat design/ složku — pro Matěje

Tato složka obsahuje **kompletní balíček**, který předáš externímu designerovi (např. Claude.ai). Designer dostane všechno potřebné a vrátí ti nový Python kód, který sem hodím a pustím přes CI.

---

## Krok 1: Otevři Claude.ai

1. Jdi na **https://claude.ai**
2. Přihlas se (Google účet stačí pro Pro plán)
3. **Vyber model "Claude Sonnet 4.6"** (vpravo nahoře u jména modelu) — pro design je Sonnet lepší než Haiku
4. **Klikni "New chat"**

## Krok 2: Přilož všechny soubory z této složky

V chat okně najdeš **📎 ikonu** (přiložit). Klikni a vyber:

**Z `design/`:**
- `BRIEF.md`
- `CONSTRAINTS.md`

**Ze `design/screenshots/`:**
- `01_first_run.png`
- `02_empty_state.png`
- `03_with_sources.png`
- `04_settings.png`

**Ze `design/current_code/`:**
- `empty_state.py`
- `file_drop_zone.py`
- `first_run_dialog.py`
- `main_window.py`
- `ollama_status.py`
- `progress_panel.py`
- `prompt_editor.py`
- `settings_dialog.py`
- `source_table.py`

Celkem **15 souborů**. Claude.ai zvládá tohle hravě (200k token context).

## Krok 3: Napiš úvodní zprávu

Doslovně tohle zkopíruj do chat:

```
Ahoj. Přiložil jsem ti BRIEF.md, CONSTRAINTS.md, čtyři screenshoty
aktuálního UI a všechny zdrojové soubory PySide6 widgetů.

Prosím přečti si BRIEF.md a CONSTRAINTS.md.

Pak chci, abys udělal kompletní redesign UI podle briefu.
Pro každý widget, který upravíš, vyrob samostatný artifact
s celým novým souborem (.py). Pojmenuj artifact stejně jako
původní soubor.

Na konci přidej souhrn co jsi změnil a proč.

Drž se PySide6 (žádné nové dependence) a kontraktů z CONSTRAINTS.md.
```

## Krok 4: Claude.ai vrátí artifacty

Vpravo se ti začnou objevovat **boxy s názvy `empty_state.py`, `main_window.py`** atd. Každý je celé Python soubor.

V každém artefaktu je vpravo nahoře tlačítko **"Copy"** — klikni a celý soubor je v clipboardu.

## Krok 5: Pošli mi výsledky

V chatu se mnou (Claude Code) napiš:
```
Tady je nový empty_state.py:
<paste celý kód>

Tady je nový main_window.py:
<paste celý kód>
... atd
```

Já každý soubor uložím na správné místo (`app/gui/widgets/empty_state.py` atd.), spustím testy, commitnu a pošlu na GitHub. CI build se sám spustí a za ~8 minut budeme mít nový `.exe`.

## Krok 6: Iterace

Pokud se ti něco nelíbí:
- **V Claude.ai přímo** — napiš mu "ten progress_panel udělej radši takhle..." a vrátí ti upravenou verzi
- **Nebo přes mě** — pošli mi screenshot výsledku, řekni co se nelíbí, já buď upravím sám, nebo ti připravím follow-up prompt pro Claude.ai

---

## Tipy

**Co Claude.ai dělá rád:**
- Komplexní designové úkoly (artifacts mu jdou)
- Konkrétní brief s constraints
- Vidět existující kód, ne psát od nuly

**Co mu nejde:**
- Kreslit obrázky / ikony — drž se Qt built-in ikon nebo emoji v textu
- Mít zápal pro funkce které nezná — pokud chceš animaci, řekni přímo "použij QPropertyAnimation na opacity"
- Dlouhé Python soubory bez context — proto mu dáváme všechno najednou

**Co dělej:**
- ✅ Buď konkrétní v briefu ("modrá #205ca8 jako accent")
- ✅ Iteruj — první verze nebude perfektní, druhá kolo je často nejlepší
- ✅ Zkontroluj v Claude.ai sám jestli artifact obsahuje **celý** soubor (na začátku má `from __future__ import annotations`, na konci celá poslední metoda)

**Co nedělej:**
- ❌ Nepouštěj kód z Claude.ai naslepo do produkce — pošli mi ho přes Claude Code abych spustil testy
- ❌ Nedávej Claude.ai změnit `core/` (business logiku) — to není v jeho briefu
- ❌ Neignoruj `CONSTRAINTS.md` — pokud Claude.ai přejmenuje signál `sources_added` na něco jiného, rozbijou se workery

---

## Co když Claude.ai vyrobí něco co nefunguje?

1. Zkopíruješ stejně, pošleš mi
2. Já spustím `pytest tests/` a `python -m app` na macOS
3. Pokud něco selže, řeknu ti přesnou chybu
4. Buď opravím sám, nebo ti řeknu **přesný diff promptu**, který chceš poslat zpátky do Claude.ai

---

## Velikost balíčku

| Soubor | Velikost |
|---|---|
| BRIEF.md | ~6 KB |
| CONSTRAINTS.md | ~3 KB |
| 4 screenshoty (PNG) | ~500 KB |
| 9 Python souborů | ~30 KB |
| **Celkem** | ~540 KB |

Claude.ai limit pro přílohy je 30 MB / chat. Místa je dost.
