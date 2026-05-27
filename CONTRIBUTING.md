# Contributing — Hlas do textu

Vítej. Tady je vše co potřebuješ vědět než si projekt projdeš nebo přispěješ.

## Setup vývojářského prostředí

### Prerekvizity

- **Python 3.11+** (testováno na 3.11 a 3.13)
- **FFmpeg** dostupný v PATH
  - macOS: `brew install ffmpeg`
  - Ubuntu: `sudo apt install ffmpeg`
  - Windows: `choco install ffmpeg` nebo stáhnout z [ffmpeg.org](https://ffmpeg.org)
- **git**

### Instalace

```bash
git clone https://github.com/matczalas/hlas-do-textu.git
cd hlas-do-textu

python3.11 -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

To je vše. `pip install -e ".[dev]"` nainstaluje aplikaci v editable módu
plus dev nástroje (pytest, pyinstaller, ruff, reportlab, Pillow).

## Spuštění aplikace

```bash
python -m app
```

Při prvním spuštění uvidíš **aktivační dialog**. Repo neobsahuje production
HMAC secret (ten má jen vlastník projektu), takže nemůžeš ověřit produkční
klíče. Pro dev používej **dev klíče**:

```bash
python scripts/make_key.py --count 3 --customer "Local dev"
# Vygeneruje 3 dev klíče. Jeden z nich vlož při spuštění.
```

> ⚠️ Dev klíče **NEFUNGUJÍ** s `.exe` z GitHub Releases. To je správně —
> chrání produkční distribuci. Pokud máš jen dev klíče, musíš si build
> .exe vyrobit sám (viz níže), aby použil DEV_FALLBACK secret stejný jako
> tvůj klíč.

## Testy

```bash
pytest                        # všechny testy (126)
pytest tests/test_chunker.py  # konkrétní soubor
pytest -v -k licensing        # podle jména
pytest tests/test_chat.py::test_parse_text_only_response_no_proposal  # jeden test
```

Lint:

```bash
ruff check app/ tests/
ruff check . --fix            # auto-fix
```

> **Worktree gotcha:** při práci v git worktree tam chybí `.env` s HMAC
> secretem → licenční klíče se vyhodnotí jako neplatné. Řešení:
> `ln -sf <hlavní-repo>/.env <worktree>/.env`.

## Struktura projektu

```
app/
├── __main__.py              # entry point
├── config.py                # konstanty, paths
├── settings.py              # AppSettings persistence
├── logging_setup.py         # loguru config
├── core/                    # business logika (NO Qt imports here!)
│   ├── pipeline.py          # orchestrátor + dávkové rozdělení
│   ├── transcribe.py        # lokální Whisper wrapper + resume
│   ├── transcribe_gemini.py # cloud Gemini Audio přepis
│   ├── checkpoint.py        # resume přepisu od místa přerušení
│   ├── audio_extract.py     # FFmpeg (extract + trim)
│   ├── youtube_fetch.py     # stahování audia z URL (yt-dlp)
│   ├── pdf_extract.py / pptx_extract.py
│   ├── word_export.py / md_export.py
│   ├── model_downloader.py
│   └── ai/                  # Gemini + Ollama + router + chat + prompts
├── gui/                     # PySide6 (Qt UI)
│   ├── main_window.py       # + dávková fronta, kalibrace, recents
│   ├── widgets/             # dialogy, tabulky, panely
│   └── workers/             # QThread runners (pipeline/model/youtube/chat/update)
├── licensing/               # license key validation (HMAC)
└── updater/                 # GitHub Releases auto-update

tests/                       # pytest
scripts/                     # CLI utilities (make_key, generate_icon, build, ffmpeg)
installer/                   # Inno Setup .iss
docs/                        # uživatelská dokumentace
.github/workflows/           # CI: Windows + macOS build pipeline
```

Architektonické detaily, konvence a gotchas viz [CLAUDE.md](CLAUDE.md).

## Pravidla

### Architektura

- **`core/` nesmí importovat `PySide6`.** Business logika musí být GUI-free
  (snadné testovat, snadno přenositelné).
- **`gui/` smí importovat `core/`.** GUI workery volají core přes QThread.
- **Žádné nové dependence** bez konzultace v issue. PyInstaller bundle už
  má 200 MB; každá nová knihovna ho zvětší.

### Styl kódu

- **PEP 8** + ruff. Konfigurace v `pyproject.toml`.
- **Type hints** všude (`def foo(x: int) -> str`).
- **Docstringy** u veřejných funkcí. Stručné, věcné.
- **f-stringy** pro interpolaci. `loguru.logger` pro logování (ne `print`).

### Commit messages

Stručný subject + tělo s "co a proč":

```
Fix Whisper download — žádný progress feedback v UI

snapshot_download() vrátí až po hotovo, uživatel viděl jen
'Stahuji…' několik minut. Refaktor na httpx.stream s real-time
byte-level progress callbackem.

Soubory v Systran/faster-whisper-* repo: config.json, model.bin,
tokenizer.json, vocabulary.txt — stahujeme postupně, hlásíme % .
```

### Co se nemění bez diskuse

- **HMAC secret v `app/licensing/_secret.py`** — produkční je v GitHub Actions Secret
- **Klíčový formát `S4F1-XXXX-XXXX-XXXX-XXXX`** — změna by zneplatnila všechny vydané klíče
- **JobMode enum** — používá ho persistence
- **API kontrakty signálů ve `gui/widgets/`** — používají workers

## Vývoj — typický flow

```bash
git checkout -b moje-fica/whatever
# kód
ruff check . --fix
pytest tests/
python -m app                # ruční smoke test
git add -p && git commit -m "Stručný subject"
git push -u origin moje-fica/whatever
gh pr create --title "..." --body "..."
```

## Vlastní Windows build

```bash
# 1. Stáhni FFmpeg pro Windows do app/vendor/ffmpeg/win64/
python scripts/download_ffmpeg_windows.py    # na Win runneru

# 2. Vygeneruj ikonu
python scripts/generate_icon.py

# 3. PyInstaller bundle
#    Hidden importy a --collect-* musí přesně odpovídat .github/workflows/
#    build-windows.yml — jsou tam záměrně (jinak to padá až v .exe, ne v dev):
pyinstaller --noconfirm --clean \
  --onedir --windowed --name HlasDoTextu \
  --icon app/resources/icon.ico \
  --add-data "app/vendor/ffmpeg/win64;vendor/ffmpeg/win64" \
  --add-data "app/resources;resources" \
  --add-data "app/gui/styles;app/gui/styles" \
  --collect-all ctranslate2 \
  --collect-all faster_whisper \
  --collect-all tiktoken \
  --collect-all tiktoken_ext \
  --hidden-import=tiktoken_ext.openai_public \
  --collect-all yt_dlp \
  --collect-data certifi \
  app/__main__.py

# 4. Inno Setup .exe (vyžaduje Windows + Inno Setup nainstalované)
iscc installer\HlasDoTextu.iss
```

> Build flags jsou source of truth v `.github/workflows/build-*.yml` — když
> přidáš dependenci s lazy plugin loadingem nebo data soubory, aktualizuj
> oba workflow (Windows i macOS) i tento příkaz.

Cross-compile z macOS / Linux **nefunguje**. Buď použij Windows VM
(Parallels / VMware), nebo nech to dělat GitHub Actions (workflow
`build-windows.yml` / `build-macos.yml` reagují na push do `main` a na tagy `v*`).

## Verifikace před PR

Kontrolní seznam:

- [ ] `ruff check app/ tests/` — žádné varování
- [ ] `pytest` — všechny testy projdou
- [ ] `python -m app` — GUI startne, žádný crash, žádné runtime warning
- [ ] Pro nové widgety: ruční ověření na macOS i Windows (CI runneru)

## Otázky

- **Otevřít issue na GitHubu** s popisem
- **Email**: `matej.rada@safe4future.cz`
