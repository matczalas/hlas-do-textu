# Hlas do textu

Windows desktopová aplikace pro studenty — z nahrávky přednášky (a volitelně prezentace) vytvoří strukturované body pro učení ve Wordu.

## Co umí

- Nahraje libovolný počet audio/video souborů (mp4, wav, mp3, m4a) a prezentací (PDF, PPTX)
- Lokálně přepíše mluvené slovo do češtiny pomocí **faster-whisper** (default `medium` model)
- Pošle přepis + obsah prezentace do **Google Gemini 2.0 Flash** (free tier) a získá studijní body
- Pokud Gemini nedostupný / vyčerpaný free tier, použije lokální **Ollama** jako fallback
- Výstup: Word `.docx` s body pro učení + plným přepisem v příloze

## Pro vývoj na macOS / Linuxu

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m app                  # spustí GUI
python scripts/smoke_test.py   # end-to-end smoke test
pytest tests/                  # unit testy
```

## Pro koncové uživatele (Windows)

Stáhněte `HlasDoTextu-Setup-X.Y.Z.exe` z [Releases](https://github.com/safe4future/hlas-do-textu/releases), spusťte instalátor a postupujte podle průvodce.

Návody:
- [První spuštění](docs/PRVNI_SPUSTENI.md)
- [Jak získat Gemini API klíč zdarma](docs/ZISKAT_GEMINI_KLIC.md)
- [Volitelná instalace Ollamy pro offline režim](docs/INSTALACE_OLLAMA.md)

## Licence

MIT — Safe4Future z. ú.
