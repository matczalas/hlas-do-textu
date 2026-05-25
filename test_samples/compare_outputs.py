"""Porovná dva .docx výstupy (Gemini vs Ollama) — vytáhne body, pojmy, atd."""
from __future__ import annotations

import sys
from pathlib import Path

from docx import Document


def extract_sections(docx_path: Path) -> dict[str, list[str]]:
    """Vrátí dict {section_name: [items]} podle Heading 1 nadpisů."""
    doc = Document(str(docx_path))
    out: dict[str, list[str]] = {}
    current = None
    for p in doc.paragraphs:
        style = p.style.name
        text = p.text.strip()
        if not text:
            continue
        if style.startswith("Heading 1"):
            current = text
            out[current] = []
        elif current is not None and "List" in style:
            out[current].append(text)
    return out


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: compare_outputs.py <gemini.docx> <ollama.docx>", file=sys.stderr)
        return 2

    gemini_path = Path(sys.argv[1])
    ollama_path = Path(sys.argv[2])

    g = extract_sections(gemini_path)
    o = extract_sections(ollama_path)

    sections = sorted(set(g.keys()) | set(o.keys()))
    for sec in sections:
        g_items = g.get(sec, [])
        o_items = o.get(sec, [])
        print(f"\n{'=' * 80}")
        print(f"SEKCE: {sec}")
        print(f"   Gemini: {len(g_items)}   Ollama: {len(o_items)}")
        print("=" * 80)
        max_n = max(len(g_items), len(o_items))
        for i in range(max_n):
            g_item = g_items[i] if i < len(g_items) else "—"
            o_item = o_items[i] if i < len(o_items) else "—"
            print(f"\n[{i + 1}] GEMINI:  {g_item[:200]}")
            print(f"    OLLAMA:  {o_item[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
