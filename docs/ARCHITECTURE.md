# Architektura — Hlas do textu

Vnitřní dokument pro vývojáře. Pro uživatelský návod viz [PRVNI_SPUSTENI.md](PRVNI_SPUSTENI.md).

## Vrstvy

```
┌──────────────────────────────────────────────────────────────┐
│  app/gui/  — PySide6, QThread workers                         │
│  Main window, widgety, signál routing                         │
└──────────────────────────────────────────────────────────────┘
                       │ (worker → core, ne naopak)
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  app/core/  — business logika, BEZ Qt importů                 │
│                                                                │
│  pipeline.run_pipeline()                                       │
│    ├─ audio_extract.extract_to_wav()    [FFmpeg]              │
│    ├─ transcribe.transcribe_audio()     [faster-whisper]      │
│    ├─ pdf_extract.extract_pdf_text()    [pdfplumber]          │
│    ├─ pptx_extract.extract_pptx_text()  [python-pptx]         │
│    ├─ ai.router.generate_study_material()                     │
│    │    ├─ chunker.split_into_chunks()  [tiktoken]            │
│    │    ├─ ai.gemini.GeminiProvider     [google-genai]        │
│    │    └─ ai.ollama.OllamaProvider     [httpx]               │
│    └─ word_export.export_docx()         [python-docx]         │
└──────────────────────────────────────────────────────────────┘
```

## Klíčová pravidla

- **Žádný Qt import v `core/`.** Core musí být testovatelný bez display serveru.
- **Lazy importy těžkých knihoven** (faster-whisper, pdfplumber, python-pptx, google-genai) — drží startup pod 1 s.
- **Cesty:** `pathlib.Path` všude. Cesty s diakritikou (Tereza Čapková) musí fungovat.
- **Pipeline běží v `QThread`.** GUI ne-blocking. Cancel přes `threading.Event`.
- **API klíče přes `keyring`** (Windows Credential Manager / macOS Keychain). Žádné plaintext klíče v `config.json`.
- **Logy:** loguru, rotace 5 MB × 5 souborů, v `USER_DATA_DIR/logs/app.log`.

## Datové struktury

| Třída | Kde | Účel |
|---|---|---|
| `SourceFile` | `core/models.py` | Jeden importovaný soubor (audio nebo prezentace) |
| `Transcript` | `core/models.py` | Výstup faster-whisper pro 1 audio |
| `SlideText` | `core/models.py` | Plain text z PDF/PPTX |
| `StudyMaterial` | `core/models.py` | Strukturovaný JSON z AI (title, bullets, terms, examples, further_study) |
| `JobConfig` | `core/models.py` | Vstup do pipeline (sources, prompt, output_dir, settings) |

## Map-reduce strategie

- Default: `MAP_REDUCE_THRESHOLD_TOKENS = 8000` v `config.py`.
- Pod thresholdem: jeden `single_shot_prompt` s celým transkriptem.
- Nad: každý transkript se rozseče chunkerem na ~3000 tokenů, paralelně poslán do Gemini (max 4 souběžně kvůli rate limitu 15 RPM), výsledky se konsolidují do `mapped_summary` a posílají do reduce promptu.

## AI Failover

`AIRouter` (`core/ai/router.py`) má `primary` (Gemini) a `fallback` (Ollama). Selhání primárního na `AIAuthError`, `AIRateLimitError`, `AINetworkError` nebo obecný `AIError` → automatický pokus o fallback.

Failover **se neaktivuje** pro `ValueError` a další non-AI chyby — ty bublají ven jako bug v aplikaci.

## Whisper konfigurace

Default model `medium`, jazyk `cs`. Soubory cachovány v `USER_DATA_DIR/models/faster-whisper-<size>/`. Repo Systran/faster-whisper-* (oficiální faster-whisper weighty).

Důležité parametry v `core/transcribe.py`:
- `device="cpu"`, `compute_type="int8"` — funguje všude
- `vad_filter=True` — odstraní ticha
- `beam_size=5` — kvalita vs. rychlost
- `word_timestamps=False` — pro studijní body nepotřebujeme

## Windows build

GitHub Actions `windows-latest` runner. PyInstaller `--onedir` + Inno Setup. FFmpeg vendorovaný (BtbN release). Klíčové PyInstaller flagy:

```
--collect-all ctranslate2
--collect-all faster_whisper
--collect-data certifi
--collect-data tiktoken
--add-data "app/vendor/ffmpeg/win64;vendor/ffmpeg/win64"
```

Bez `--collect-all ctranslate2` aplikace na Windows spadne při importu faster-whisper (chybějící DLL).

## Z čeho lze rozšiřovat

- **Multimodální AI** (Gemini Vision): slidy jako obrázky → fotky grafů a diagramů. Vyžaduje upload do Gemini File API.
- **OCR pro scanned PDF**: Tesseract integration → další ~150 MB instalátoru.
- **Code signing**: Sectigo / DigiCert (~150 EUR/rok), odstraní SmartScreen warning.
- **Streamování přepisu**: faster-whisper podporuje streaming, GUI by mohlo zobrazovat částečný transkript v reálném čase.
- **Více providerů**: OpenAI, Anthropic, Mistral — přidání `Provider` třídy v `core/ai/`.
