"""Rychlý end-to-end smoke test bez GUI.

Použití:
    python scripts/smoke_test.py path/to/audio.mp3 [path/to/slides.pdf]

Vyžaduje nastavený GEMINI_API_KEY v ENV nebo přes UI (keyring).
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.config import DEFAULT_OUTPUT_DIR, ensure_dirs
from app.core.models import JobConfig, SourceFile, SourceKind
from app.core.pipeline import run_pipeline
from app.logging_setup import setup_logging
from app.settings import get_gemini_api_key


def main(argv: list[str]) -> int:
    setup_logging(verbose=True)
    ensure_dirs()

    if len(argv) < 2:
        print("Použití: python scripts/smoke_test.py <audio> [<slides>]")
        return 2

    sources: list[SourceFile] = []
    for arg in argv[1:]:
        p = Path(arg).expanduser().resolve()
        if not p.is_file():
            print(f"Soubor nenalezen: {p}", file=sys.stderr)
            return 2
        ext = p.suffix.lower()
        if ext in (".pdf", ".pptx"):
            sources.append(SourceFile(path=p, kind=SourceKind.PRESENTATION, label=p.stem))
        else:
            sources.append(SourceFile(path=p, kind=SourceKind.AUDIO_VIDEO, label=p.stem))

    api_key = get_gemini_api_key()
    if not api_key:
        print("Pozor: GEMINI_API_KEY není nastaven. Použiji jen Ollama fallback (pokud běží).")

    job = JobConfig(
        sources=sources,
        user_prompt="Smoke test — vytvoř krátké body z přednášky a slidů.",
        output_dir=DEFAULT_OUTPUT_DIR,
        whisper_model="small",  # smoke test = rychlejší model
        ai_consent_gemini=True,
    )

    def report(label: str, fraction: float) -> None:
        bar = "█" * int(fraction * 30) + "░" * (30 - int(fraction * 30))
        print(f"\r[{bar}] {fraction * 100:5.1f}% {label[:60]:<60}", end="", flush=True)

    print("\nSpouštím pipeline…")
    result = run_pipeline(job, gemini_api_key=api_key, progress_cb=report)
    print()  # newline after progress
    print(f"✅ Výstup: {result.output_path}")
    print(f"   Hlavních bodů: {len(result.material.bullets)}")
    print(f"   Pojmů: {len(result.material.terms)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
