"""Generátor Wordového dokumentu (.docx) z StudyMaterial + transkriptů + slidů.

Struktura:
    Nadpis 1 — Titul studijního materiálu
    Datum, zdroje
    Nadpis 1 — Hlavní body k zapamatování (bulleted list)
    Nadpis 1 — Klíčové pojmy (definice list)
    Nadpis 1 — Příklady z přednášky
    Nadpis 1 — Doporučení k dalšímu studiu
    [page break]
    Nadpis 1 — Plný přepis
        Nadpis 2 — {label_n}
            tělo přepisu se značkami "[mm:ss]" každých ~30s
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from loguru import logger

from app.core.models import SlideText, SourceFile, StudyMaterial, Transcript

# python-docx (resp. lxml) odmítne uložit XML s control znaky a vyhodí
# ValueError "All strings must be XML compatible: Unicode or ASCII, no NULL
# bytes or control characters". Whisper, Gemini i extrakce z PDF/PPTX občas
# takový znak protlačí (\x00, \x0b, \x0c z naskenovaného PDF nebo vadného
# audia). Bez sanitizace by spadl celý export NA KONCI pipeline — uživatel
# by ztratil hodiny přepisu. Povolujeme jen tab/newline/carriage-return.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _clean(text: str | None) -> str:
    """Odstraní XML-nekompatibilní control znaky. None → ''."""
    if not text:
        return ""
    return _CONTROL_CHARS_RE.sub("", text)


def export_docx(
    *,
    output_path: Path,
    material: StudyMaterial,
    transcripts: list[Transcript],
    slides: list[SlideText],
    sources: list[SourceFile],
    user_prompt: str | None,
) -> Path:
    """Vytvoří .docx soubor na `output_path`. Vrací cestu k němu."""
    from docx import Document  # lazy
    from docx.enum.text import WD_BREAK
    from docx.shared import Pt

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = Document()

    # Default styling
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # ----- Titul + metadata -----
    title = _clean(material.title).strip() or "Studijní materiál"
    doc.add_heading(title, level=0)

    meta = doc.add_paragraph()
    meta.add_run(f"Vygenerováno: {datetime.now().strftime('%d. %m. %Y %H:%M')}\n").italic = True
    if sources:
        meta.add_run("Zdroje:\n").bold = True
        for src in sources:
            meta.add_run(f"  • {_clean(src.label)} ({_clean(src.path.name)})\n")
    if user_prompt:
        meta.add_run("\nPopis od studenta:\n").bold = True
        meta.add_run(_clean(user_prompt) + "\n")

    # ----- Hlavní body -----
    if material.bullets:
        doc.add_heading("Hlavní body k zapamatování", level=1)
        for bullet in material.bullets:
            doc.add_paragraph(_clean(bullet), style="List Bullet")

    # ----- Klíčové pojmy -----
    if material.terms:
        doc.add_heading("Klíčové pojmy", level=1)
        for term, definition in material.terms:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(_clean(term)).bold = True
            if definition:
                p.add_run(f" — {_clean(definition)}")

    # ----- Příklady -----
    if material.examples:
        doc.add_heading("Příklady z přednášky", level=1)
        for ex in material.examples:
            doc.add_paragraph(_clean(ex), style="List Bullet")

    # ----- Otázky k procvičení / ke zkoušení -----
    if material.quiz_questions:
        doc.add_heading("Otázky k procvičení a zkoušení", level=1)
        for i, q in enumerate(material.quiz_questions, start=1):
            doc.add_paragraph(f"{i}. {_clean(q)}", style="List Number")

    # ----- Doporučení k dalšímu studiu -----
    if material.further_study:
        doc.add_heading("Doporučení k dalšímu studiu", level=1)
        for f in material.further_study:
            doc.add_paragraph(_clean(f), style="List Bullet")

    # ----- Page break -----
    if transcripts or slides:
        p = doc.add_paragraph()
        p.add_run().add_break(WD_BREAK.PAGE)

    # ----- Plný přepis -----
    if transcripts:
        doc.add_heading("Plný přepis přednášky", level=1)
        for tr in transcripts:
            doc.add_heading(_clean(tr.source_label), level=2)
            body = _format_transcript_with_timestamps(tr)
            for paragraph in body.split("\n\n"):
                if paragraph.strip():
                    doc.add_paragraph(_clean(paragraph.strip()))

    # ----- Plný text slidů -----
    if any(sl.text for sl in slides):
        doc.add_heading("Obsah prezentací", level=1)
        for sl in slides:
            if not sl.text:
                continue
            doc.add_heading(_clean(sl.source_label), level=2)
            for block in sl.text.split("\n\n"):
                if block.strip():
                    doc.add_paragraph(_clean(block.strip()))

    doc.save(str(output_path))
    logger.info("Uloženo: {} ({:.1f} KB)", output_path, output_path.stat().st_size / 1024)
    return output_path


def _format_transcript_with_timestamps(tr: Transcript, interval_sec: float = 30.0) -> str:
    """Vsadí značky [mm:ss] do textu každých ~`interval_sec` sekund."""
    if not tr.segments:
        return tr.text

    out: list[str] = []
    next_marker = 0.0
    current_paragraph: list[str] = []

    for seg in tr.segments:
        if seg.start >= next_marker:
            if current_paragraph:
                out.append(" ".join(current_paragraph))
                current_paragraph = []
            out.append(f"\n[{_format_time(seg.start)}]")
            next_marker = seg.start + interval_sec
        current_paragraph.append(seg.text)

    if current_paragraph:
        out.append(" ".join(current_paragraph))

    # spojit do paragraphs oddělených \n\n (přechody mezi blocky)
    raw = " ".join(out)
    # Před každou značkou vložit \n\n pro lepší členění
    raw = raw.replace(" \n[", "\n\n[")
    return raw.strip()


def _format_time(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def suggested_output_filename(material: StudyMaterial) -> str:
    """Vrátí název souboru ve tvaru `Studijni-material_YYYY-MM-DD-HHMM.docx`."""
    safe_title = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in material.title).strip()
    if not safe_title:
        safe_title = "Studijni-material"
    safe_title = safe_title.replace(" ", "-")[:60]
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    return f"{safe_title}_{timestamp}.docx"


def topic_folder_name(material: StudyMaterial) -> str:
    """Vrátí bezpečný název složky podle tématu, nebo "" když téma chybí.

    Téma navrhne AI (např. "Fyzika", "Dějepis"). Sanitizujeme na název složky
    bezpečný napříč Windows/macOS — bez `\\ / : * ? " < > |`, bez tečky na konci
    (Windows), max 40 znaků. Když je téma prázdné, vrátíme "" (export jde do
    kořenové výstupní složky jako dosud).
    """
    topic = (material.topic or "").strip()
    if not topic:
        return ""
    # Povolíme písmena, čísla, mezery, pomlčky, podtržítka; zbytek pryč
    safe = "".join(c if c.isalnum() or c in (" ", "-", "_") else " " for c in topic)
    safe = " ".join(safe.split())  # zkolabovat vícenásobné mezery
    safe = safe.strip(" .")[:40].strip()
    return safe
