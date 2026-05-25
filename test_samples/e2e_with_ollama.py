"""End-to-end test s lokálním Ollama: Whisper přepis → Ollama → Word docx.

Vyžaduje:
  - ollama serve běží na localhost:11434
  - `ollama pull llama3.2:3b` (~2 GB)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

from app.config import DEFAULT_OUTPUT_DIR, ensure_dirs
from app.core.ai.ollama import OllamaProvider
from app.core.ai.router import AIRouter, generate_study_material
from app.core.models import Transcript, TranscriptSegment
from app.core.word_export import export_docx, suggested_output_filename
from app.logging_setup import setup_logging


def main() -> int:
    setup_logging()
    ensure_dirs()

    # Kontrola Ollamy
    ollama = OllamaProvider()
    print(">>> Kontroluji Ollama health…")
    if not ollama.health_check():
        print("CHYBA: Ollama neběží nebo model 'llama3.2:3b' není stažený.", file=sys.stderr)
        print("Spusť: ollama serve", file=sys.stderr)
        print("       ollama pull llama3.2:3b", file=sys.stderr)
        return 2

    print(">>> Ollama OK")

    transcript_path = Path("test_samples/whisper_output.txt")
    text = transcript_path.read_text(encoding="utf-8")
    print(f">>> Vstup: {len(text.split())} slov z {transcript_path.name}")

    tr = Transcript(
        source_label="TEDxPrague — Iva Pekárková",
        language="cs",
        duration_sec=180.0,
        text=text,
        segments=[TranscriptSegment(start=0.0, end=180.0, text=text)],
    )

    print(">>> Volám Ollama (llama3.2:3b)…")
    t0 = time.time()
    router = AIRouter(primary=ollama, fallback=None)
    material = generate_study_material(
        router=router,
        transcripts=[tr],
        slides=[],
        user_prompt=(
            "Toto je úryvek z TEDx přednášky o cestování a životě v zahraničí "
            "(řečnice Iva Pekárková). Vytvoř studijní body pro studenta, který si chce "
            "z přednášky odnést hlavní myšlenky a postoje řečnice."
        ),
    )
    elapsed = time.time() - t0
    print(f">>> Ollama hotov za {elapsed:.1f}s")
    print()
    print("=" * 70)
    print(f"TITUL: {material.title}")
    print("=" * 70)
    print()
    print(f"📌 BODY ({len(material.bullets)}):")
    for i, b in enumerate(material.bullets, 1):
        print(f"  {i}. {b}")
    print()
    print(f"🔑 POJMY ({len(material.terms)}):")
    for term, definition in material.terms:
        print(f"  • {term} — {definition}")
    print()
    print(f"📚 PŘÍKLADY ({len(material.examples)}):")
    for i, e in enumerate(material.examples, 1):
        print(f"  {i}. {e}")
    print()
    print(f"➡  DOPORUČENÍ ({len(material.further_study)}):")
    for i, f in enumerate(material.further_study, 1):
        print(f"  {i}. {f}")

    out_path = DEFAULT_OUTPUT_DIR / f"ollama_{suggested_output_filename(material)}"
    print(f"\n>>> Ukládám: {out_path}")
    export_docx(
        output_path=out_path,
        material=material,
        transcripts=[tr],
        slides=[],
        sources=[],
        user_prompt="(test Ollama)",
    )
    print(f">>> Hotovo: {out_path.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
