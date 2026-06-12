"""Otevření follow-up e-mailu v poštovním klientovi přes mailto: URL.

Šablona sales_followup_email vyrábí sekce „Předmět e-mailu" a „Tělo e-mailu" —
tady je najdeme a složíme mailto: odkaz. Tělo zároveň GUI kopíruje do schránky,
protože některé klienty (hlavně Outlook na Windows) mailto tělo ořezávají.
"""

from __future__ import annotations

from urllib.parse import quote

from app.core.models import SECTION_KIND_PARAGRAPH, StudyMaterial

_SUBJECT_HINTS = ("předmět",)
_BODY_HINTS = ("tělo e-mailu", "tělo emailu", "text e-mailu")


def extract_email(material: StudyMaterial) -> tuple[str, str] | None:
    """Vrátí (předmět, tělo) z materiálu, nebo None když e-mail sekce chybí.

    Tělo = odstavce sekce spojené prázdným řádkem (jak je psal AI).
    """
    subject = ""
    body = ""
    for section in material.iter_sections():
        title = section.title.lower()
        if section.kind != SECTION_KIND_PARAGRAPH:
            continue
        text_items = [str(i).strip() for i in section.items if str(i).strip()]
        if not text_items:
            continue
        if not subject and any(h in title for h in _SUBJECT_HINTS):
            subject = text_items[0]
        elif not body and any(h in title for h in _BODY_HINTS):
            body = "\n\n".join(text_items)
    if not body:
        return None
    return (subject or "Shrnutí naší schůzky", body)


def build_mailto(subject: str, body: str, to: str = "") -> str:
    """Sestaví mailto: URL s URL-encodovaným předmětem a tělem."""
    params = f"subject={quote(subject)}&body={quote(body)}"
    return f"mailto:{quote(to)}?{params}"
