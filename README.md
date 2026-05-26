# Hlas do textu

> Desktop aplikace pro studenty — z nahrávky přednášky vyrobí Word dokument
> s body pro učení.

[![Build](https://github.com/matczalas/hlas-do-textu/actions/workflows/build-windows.yml/badge.svg)](https://github.com/matczalas/hlas-do-textu/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)
[![PySide6](https://img.shields.io/badge/Qt-PySide6-41cd52.svg)](https://www.qt.io)

![Hlavní okno](docs/screenshots/02_empty_state.png)

## Co umí

- **Lokální přepis** mluveného slova v češtině (Whisper, offline)
- **Rychlý cloud přepis** přes Gemini Audio (~1 min na 15 min audia) — volitelné
- **AI body pro učení** přes Google Gemini (free tier)
- **Chat o dokumentu** — po vyrobení můžeš AI požádat o úpravy ("stručněji", "vyrob otázky")
- **Vstup odkudkoli** — drag & drop, YouTube/Vimeo/podcast URL
- **Offline fallback** přes Ollama (bez internetu)
- **Markdown export** připravený jako prompt pro ChatGPT / Claude / Gemini
- **Dva režimy:** rychlý jen-přepis, nebo plný studijní materiál s AI
- **Auto-update** přes GitHub Releases — nová verze sama naskočí

## Instalace

### Windows

1. Stáhni `HlasDoTextu-Setup-X.Y.Z.exe` z [Releases](https://github.com/matczalas/hlas-do-textu/releases)
2. Dvojklik. Při SmartScreen warning → *More info* → *Run anyway*
3. Klikej *Next* / *Install* (~30 s)
4. Spusť aplikaci, vlož aktivační klíč (formátu `S4F1-XXXX-XXXX-XXXX-XXXX`)
5. V uvítacím dialogu klikni *"Získat API klíč zdarma"* a vlož ho

### macOS

1. Stáhni `HlasDoTextu-X.Y.Z.dmg` z [Releases](https://github.com/matczalas/hlas-do-textu/releases)
2. Otevři DMG → přetáhni **Hlas do textu** do složky **Aplikace**
3. **První spuštění obejde Gatekeeper** (aplikace není notarizovaná u Apple — není to virus, jen za "ověření" Apple chce placený účet):

   **macOS 13–14 (Ventura, Sonoma):**
   - Pravým klikem na ikonu aplikace → **Otevřít** → v dialogu znovu **Otevřít**

   **macOS 15 (Sequoia) — pravý klik už nestačí:**
   - Dvojklik (objeví se varování "nebyl otevřen") → klikni **Hotovo**
   - Otevři **Systémové nastavení → Soukromí a zabezpečení**
   - Sjeď dolů → u hlášky o HlasDoTextu klikni **"Přesto otevřít"**

   **Když nic z toho nefunguje (jistý způsob přes Terminál):**
   ```bash
   xattr -dr com.apple.quarantine /Applications/HlasDoTextu.app
   ```
   Pak už jde aplikace otevřít normálně dvojklikem.
4. Vlož aktivační klíč

Toto varování uvidíš **jen jednou** — po prvním otevření si macOS aplikaci zapamatuje.

Detailní návod: [docs/PRVNI_SPUSTENI.md](docs/PRVNI_SPUSTENI.md)

## Použití

| | |
|---|---|
| ![](docs/screenshots/03_with_sources.png) | Přetáhni nahrávku (mp3/mp4/wav/m4a) a volitelně slidy (PDF/PPTX). Vyber režim a klikni Spustit. Hodinová přednáška = 60–90 min zpracování. Aplikace pošle notifikaci až bude hotovo. |

**Výstup:** Word dokument v `Dokumenty\HlasDoTextu\` s hlavními body, klíčovými
pojmy, příklady a plným přepisem. Volitelně i `.md` připravený jako prompt
pro AI.

## Architektura

- **Python 3.11** + **PySide6** (Qt 6) GUI
- **faster-whisper** (lokální Whisper, jazyk `cs`)
- **google-genai** (Gemini 2.5 Flash přes free tier)
- **Ollama** klient (offline fallback)
- **python-docx** Word export
- **PyInstaller** + **Inno Setup** Windows distribuce
- **GitHub Actions** CI (Windows runner)

Detailní popis: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Pro vývojáře

Chceš přispět nebo si projekt projít? Začni v [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
git clone https://github.com/matczalas/hlas-do-textu.git
cd hlas-do-textu
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m app                  # GUI
pytest tests/                  # 82 testů
```

## Licence

Aplikace je distribuovaná pod proprietary licencí (viz
[installer/LICENSE_cs.txt](installer/LICENSE_cs.txt)). Použití vyžaduje
platný aktivační klíč. Maximálně 2 zařízení na klíč.

Zdrojový kód obsahuje open-source knihovny, jejichž licence jsou
respektovány (viz [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)).

## Kontakt

Vyrobeno pro **Safe4Future z. ú.** — `matej.rada@safe4future.cz`
