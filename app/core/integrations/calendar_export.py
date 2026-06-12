"""Export termínu schůzky do .ics kalendářové pozvánky.

Čistě stdlib (žádná závislost) — ICS je textový formát. Generujeme "floating"
lokální čas bez timezone, což je pro pozvánky v rámci ČR správné chování
(Outlook/Apple/Google je interpretují v lokální zóně příjemce).

AI vrací termín jako volný text ("ve čtvrtek v 17:30 u klientů doma") —
spolehlivý parser českých dat neexistuje, proto datum/čas potvrzuje uživatel
v dialogu (GUI) a text od AI jde do popisu události jako kontext.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path

from app.core.models import SECTION_KIND_PARAGRAPH, StudyMaterial

# Tituly sekcí, ve kterých šablony nesou termín dalšího setkání
_MEETING_TITLE_HINTS = ("termín", "další schůz", "další setkání", "další kontakt", "příští schůz")

# Fráze znamenající "termín nepadl" — pozvánku nenabízet
_NO_MEETING_HINTS = ("nebyl dohodnut", "nebyl stanoven", "neuvedeno", "nebyla dohodnuta")


def find_meeting_text(material: StudyMaterial) -> str | None:
    """Najde text sekce s termínem další schůzky.

    Vrací spojený text sekce, nebo None, když sekce chybí, je prázdná,
    nebo říká, že termín nebyl dohodnut (pak pozvánka nedává smysl).
    """
    for section in material.iter_sections():
        title = section.title.lower()
        if not any(h in title for h in _MEETING_TITLE_HINTS):
            continue
        if section.kind != SECTION_KIND_PARAGRAPH:
            continue
        text = " ".join(str(i).strip() for i in section.items if str(i).strip()).strip()
        if not text:
            continue
        if any(h in text.lower() for h in _NO_MEETING_HINTS):
            return None
        return text
    return None


def _escape(value: str) -> str:
    """Escapování dle RFC 5545: backslash, středník, čárka, newline."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545 line folding — řádky max 75 oktetů, pokračování s mezerou.

    Počítáme konzervativně znaky (UTF-8 čeština má 2B znaky, 60 znaků < 75 B
    u běžného textu nemusí platit — proto lámeme po 60 znacích, což je
    bezpečně pod limitem i pro plně diakritický text… 60×2=120 > 75!
    Správně: lámat po bajtech."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    out: list[str] = []
    chunk: list[str] = []
    size = 0
    limit = 73  # rezerva na vodicí mezeru pokračovacího řádku
    for ch in line:
        ch_len = len(ch.encode("utf-8"))
        if size + ch_len > limit and chunk:
            out.append("".join(chunk))
            chunk = [ch]
            size = ch_len
        else:
            chunk.append(ch)
            size += ch_len
    if chunk:
        out.append("".join(chunk))
    return "\r\n ".join(out)


def build_ics(
    *,
    summary: str,
    start: datetime,
    duration_minutes: int = 60,
    location: str = "",
    description: str = "",
    uid: str | None = None,
    stamp: datetime | None = None,
) -> str:
    """Sestaví obsah .ics souboru s jednou událostí (floating lokální čas)."""
    end = start + timedelta(minutes=max(duration_minutes, 5))
    uid = uid or f"{uuid.uuid4()}@hlasdotextu"
    stamp = stamp or datetime.now()

    def dt(value: datetime) -> str:
        return value.strftime("%Y%m%dT%H%M%S")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Safe4Future//HlasDoTextu//CS",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dt(stamp)}",
        f"DTSTART:{dt(start)}",
        f"DTEND:{dt(end)}",
        f"SUMMARY:{_escape(summary)}",
    ]
    if location.strip():
        lines.append(f"LOCATION:{_escape(location.strip())}")
    if description.strip():
        lines.append(f"DESCRIPTION:{_escape(description.strip())}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def write_ics(
    output_path: Path,
    *,
    summary: str,
    start: datetime,
    duration_minutes: int = 60,
    location: str = "",
    description: str = "",
) -> Path:
    """Zapíše .ics na disk a vrátí cestu."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = build_ics(
        summary=summary,
        start=start,
        duration_minutes=duration_minutes,
        location=location,
        description=description,
    )
    output_path.write_text(content, encoding="utf-8")
    return output_path
