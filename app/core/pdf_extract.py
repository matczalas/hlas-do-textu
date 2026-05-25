"""Extrakce textu z PDF prezentací přes pdfplumber.

Pokud PDF obsahuje jen obrázky (scanned), `extract_text` vrátí prázdno —
volající dostane `SlideText` s prázdným textem a má informovat uživatele.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from app.core.models import SlideText


class PdfExtractError(RuntimeError):
    pass


def extract_pdf_text(pdf_path: Path, source_label: str) -> SlideText:
    """Zploštěný text z PDF — slidy oddělené dvěma řádky a hlavičkou."""
    import pdfplumber  # lazy import

    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise PdfExtractError(f"PDF nenalezen: {pdf_path}")

    parts: list[str] = []
    slide_count = 0
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for idx, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                page_text = page_text.strip()
                if page_text:
                    parts.append(f"[Slide {idx}]\n{page_text}")
                slide_count = idx
    except Exception as exc:  # pragma: no cover
        raise PdfExtractError(f"Chyba při čtení PDF {pdf_path.name}: {exc}") from exc

    text = "\n\n".join(parts)
    if not text:
        logger.warning("PDF {} neobsahuje extrahovatelný text (možná naskenovaný)", pdf_path.name)
    else:
        logger.info("PDF {}: {} slidů, {} znaků", pdf_path.name, slide_count, len(text))

    return SlideText(source_label=source_label, text=text, slide_count=slide_count)
