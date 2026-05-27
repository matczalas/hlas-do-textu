# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Co to je

Desktopová aplikace (Python + PySide6) pro studenty a učitele: z nahrávky přednášky/hodiny
vyrobí Word dokument se studijními body, pojmy a otázkami ke zkoušení. Lokální Whisper přepis
nebo rychlý cloud (Gemini Audio), AI zpracování přes Gemini/Ollama. Komerční produkt s
licenčními klíči, distribuovaný jako `.exe` (Windows, Inno Setup) a `.dmg` (macOS).

Komunikace, commit messages, UI texty i komentáře jsou **česky**.

## Příkazy

```bash
# Setup (Python 3.11+; testy běží i na 3.13)
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python -m app                          # spustit GUI

pytest                                 # všechny testy
pytest tests/test_checkpoint.py        # jeden soubor
pytest -k licensing                    # podle jména
pytest tests/test_chat.py::test_parse_text_only_response_no_proposal  # jeden test

ruff check app/ tests/                 # lint (musí projít čistě)
ruff check . --fix                     # auto-fix

python scripts/make_key.py --count 10  # vygenerovat licenční klíče (admin)
python scripts/generate_icon.py        # přegenerovat ikonu (PNG/ICO/ICNS)
```

Build `.exe`/`.dmg` se **nedělá lokálně** — dělají ho GitHub Actions (viz Release flow).

## Architektura — to podstatné

**Core je Qt-free.** Vše v `app/core/` (pipeline, transcribe, AI, export) musí jít importovat
bez PySide6 — je to testovatelné a běží to ve workerech. GUI (`app/gui/`) je tenká vrstva nad
core. Když přidáváš logiku, patří do core, ne do widgetu.

**Pipeline je orchestrátor** (`core/pipeline.py`, funkce `run_pipeline`): audio extract →
transkripce → čtení slidů → AI body → Word/MD export. Komunikuje s UI jen přes callbacky
(`progress_cb`, `transcript_text_cb`, `cloud_fallback_cb`) a `cancel_event`. Jeden job =
jeden výstupní dokument.

**Dva přepisové backendy, routing s fallbackem** (`_run_transcribe` v pipeline):
- `core/transcribe.py` — lokální faster-whisper (CPU, `beam_size=1`, offline)
- `core/transcribe_gemini.py` — cloud Gemini Audio (rychlé, vyžaduje klíč + souhlas)
- Když cloud selže (kvóta/síť/auth), **automaticky** spadne na lokální Whisper a oznámí to
  přes `cloud_fallback_cb`. Cloud chyba nikdy neshodí celé zpracování.

**AI vrstva** (`core/ai/`): `AIRouter` dělá failover Gemini → Ollama. Dlouhé přepisy jdou
map-reduce strategií (`chunker.py` + `prompts.py`), kratší single-shot. Výstup je vždy JSON
parsovaný do `StudyMaterial` (`router._parse_study_material`) — parsing je tolerantní
(markdown wrappery, alt. názvy polí, prázdné pojistky).

**Workers jsou QThread obaly** (`app/gui/workers/`): každá déletrvající operace (pipeline,
model download, YouTube fetch, chat, update) má worker, který emituje Qt signály. Vzor:
veřejný `Worker` obal drží `QThread` + `_Runner(QObject)`. **Při zavírání okna se VŠECHNY
workery musí zastavit** (`MainWindow._stop_all_workers`) — jinak Qt spadne při destrukci okna,
pokud nějaký QThread běží.

**Dávková fronta žije v `MainWindow`, ne v pipeline.** Když uživatel zvolí "každé video
zvlášť", main_window rozdělí zdroje (`pipeline.split_sources_for_batch`) na N jobů a spouští
je sekvenčně přes pipeline_worker. Pipeline zůstává "jeden job → jeden výstup".

**Checkpoint/resume** (`core/checkpoint.py`): dlouhý lokální přepis se průběžně ukládá; po
přerušení (cancel/crash) naváže od poslední pozice (ořeže audio přes `audio_extract.trim_wav`,
posune časy, spojí segmenty). **Je to čistě aditivní vrstva** — při jakékoli nesrovnalosti
(jiný soubor/model, corrupt) se tiše jede plný přepis. Nikdy nezhorší výsledek.

**Licensing** (`app/licensing/`): HMAC-SHA256 klíče formátu `S4F1-XXXX-XXXX-XXXX-XXXX`.
Secret je v `_secret.py`, který v pořadí hledá: env `HDT_HMAC_SECRET` → `.env` v project rootu
→ dev fallback (neplatí pro produkci). CI při buildu `_secret.py` přepíše production secretem.
Klíče v keyringu (macOS Keychain / Windows Credential Manager) pod service `HlasDoTextu.gemini`
a `HlasDoTextu.license`.

**Updater** (`app/updater/client.py`): tichá kontrola GitHub Releases → banner → download
(atomic `.part` → ověření velikosti → rename) → `apply_update`. Per-platform:
- Windows: installer přes `ShellExecuteW` + `ping` delay v `.bat` wrapperu. **NEpoužívat
  `timeout`** (vyžaduje konzoli, padá se stdin=DEVNULL) **ani `CREATE_BREAKAWAY_FROM_JOB`**
  (padá "Access denied" v Job Objectu). Inno Setup `CloseApplications=yes` + `AppMutex` zavře
  běžící app.
- macOS: jen otevře `.dmg`, app se NEukončí (uživatel přetáhne `.app` ručně).

## Kritické konvence (jinak se to rozbije)

- **Verze na dvou místech musí být synchronní:** `app/__init__.py` (`__version__`) a
  `installer/HlasDoTextu.iss` (`MyAppVersion`). Při bumpu měň obě.
- **`.env` s `HDT_HMAC_SECRET` musí být v rootu repa.** Při práci v git worktree tam chybí →
  licenční klíče se vyhodnotí jako neplatné. Řešení: `ln -sf <hlavní-repo>/.env <worktree>/.env`.
- **PyInstaller bundling** (oba `.github/workflows/build-*.yml`): nový balík s lazy plugin
  loadingem nebo data soubory musí mít explicit `--collect-all` / `--hidden-import` / `--add-data`.
  Už takto řešené: `tiktoken_ext.openai_public`, `app/gui/styles` (qss), `yt_dlp`. Bez toho
  to funguje v dev, ale spadne v `.exe`/`.app` bundlu.
- **Nové GUI dialogy s workerem** musí v `closeEvent`/`reject` počkat na doběhnutí workeru
  (viz `ChatDialog`) — jinak signál dorazí na zničený widget a app spadne.

## Release flow

1. Bump verzi v `app/__init__.py` + `installer/HlasDoTextu.iss`
2. PR → merge do `main` (rebase)
3. `git tag vX.Y.Z && git push origin vX.Y.Z`
4. Oba workflow (`build-windows.yml`, `build-macos.yml`) reagují na `tags: v*` → vyrobí
   instalátory a publikují GitHub Release.

**Auto-update gotcha:** oprava `apply_update` se projeví až v *následujícím* updatu — kdo má
verzi se starým buggy updaterem, musí novou stáhnout ručně. Windows build je vždy pomalejší
než macOS, takže krátce po tagu existuje release jen s `.dmg`, než doběhne `.exe`.

## Stav předávaný mezi sessions

`private_docs/HANDOFF.md` (gitignored) drží aktuální stav, otevřené bugy a další kroky.
Při startu nové session ho čti jako první, pokud existuje.
