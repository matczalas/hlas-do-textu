# Testovací skripty pro Whisper + AI vrstvu

Skripty v této složce slouží k ověření, že přepis a generování bodů reálně fungují.
Audio sample a YouTube titulky se **nečekají v repu** (gitignored kvůli copyrightu).

## Reprodukce testu

### 1. Stažení testovacího audio

```bash
yt-dlp -x --audio-format mp3 -o "iva_pekarkova_full.%(ext)s" \
       "https://www.youtube.com/watch?v=JfWtWnHTzIk"

ffmpeg -y -i iva_pekarkova_full.mp3 -ss 00:00:00 -t 180 -acodec copy \
       iva_pekarkova_3min.mp3
```

### 2. Stažení titulků (ground truth)

```bash
yt-dlp --skip-download --write-auto-sub --sub-lang cs \
       "https://www.youtube.com/watch?v=JfWtWnHTzIk"

python extract_ground_truth.py "Neřest jménem cestování*.cs.vtt" > ground_truth_3min.txt
```

### 3. Spuštění Whisper přepisu

```bash
cd ..  # do project rootu
python -c "
from pathlib import Path
from app.core.audio_extract import extract_to_wav
from app.core.transcribe import transcribe_audio
extract_to_wav(Path('test_samples/iva_pekarkova_3min.mp3'),
               Path('test_samples/iva_pekarkova_3min.wav'))
tr = transcribe_audio(Path('test_samples/iva_pekarkova_3min.wav'),
                     source_label='TEDx', model_size='medium', language='cs')
Path('test_samples/whisper_output.txt').write_text(tr.text, encoding='utf-8')
"
```

### 4. Porovnání kvality

```bash
python test_samples/compare.py test_samples/ground_truth_3min.txt \
                                test_samples/whisper_output.txt
```

### 5. AI generování (Gemini)

```bash
GEMINI_API_KEY="..." python test_samples/e2e_with_gemini.py
```

### 6. AI generování (Ollama offline)

```bash
# nejprve nainstaluj a spusť Ollama, stáhni model:
brew install ollama
ollama serve &
ollama pull llama3.2:3b

python test_samples/e2e_with_ollama.py
```

### 7. Side-by-side porovnání Gemini vs Ollama

```bash
python test_samples/compare_outputs.py \
    ~/Documents/HlasDoTextu/TEDxPrague_*.docx \
    ~/Documents/HlasDoTextu/ollama_*.docx
```

## Naměřené výsledky (květen 2026, macOS M-series, CPU only)

| Metrika | Hodnota |
|---|---|
| **Whisper `medium` WER** | 24,0 % (s diakritikou) |
| **Whisper RTF** | 1,88× (macOS CPU) |
| **Gemini `flash-latest`** | 17 s, 6 bodů + 3 pojmy s definicí |
| **Ollama `llama3.2:3b`** | 43 s, 4 body bez kvalitních definic |

Plné porovnání viz [docs/INSTALACE_OLLAMA.md](../docs/INSTALACE_OLLAMA.md).
