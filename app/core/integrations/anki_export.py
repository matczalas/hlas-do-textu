"""Export karet na učení do Anki balíčku (.apkg).

Karty se sbírají ze sekcí typu `definitions` (pojem → definice) a `qa`
(otázka → odpověď) — funguje tedy pro šablonu student_flashcards i pro
jakýkoli materiál s pojmy/otázkami (studijní materiál, hodina, kvíz).

Závislost: genanki (pure-python). Import je lazy — bez genanki spadne až
samotný export, ne celá appka.
"""

from __future__ import annotations

import zlib
from pathlib import Path

from app.core.models import (
    SECTION_KIND_DEFINITIONS,
    SECTION_KIND_QA,
    StudyMaterial,
)


def collect_cards(material: StudyMaterial) -> list[tuple[str, str]]:
    """Vrátí (přední, zadní) dvojice ze všech definitions/qa sekcí.

    Karty bez zadní strany (prázdná definice / chybějící vzorová odpověď)
    se vynechávají — v Anki by byly k ničemu.
    """
    cards: list[tuple[str, str]] = []
    for section in material.iter_sections():
        if section.kind not in (SECTION_KIND_DEFINITIONS, SECTION_KIND_QA):
            continue
        for item in section.items:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            front = str(item[0]).strip()
            back = str(item[1]).strip()
            if front and back:
                cards.append((front, back))
    return cards


def has_cards(material: StudyMaterial) -> bool:
    """True, pokud má materiál aspoň jednu exportovatelnou kartu."""
    return bool(collect_cards(material))


def _stable_id(name: str) -> int:
    """Deterministické 31bit ID z názvu — stejný balíček = stejné ID.

    Anki používá ID k rozpoznání existujícího decku/modelu při re-importu;
    náhodná ID by při každém exportu vyrobila duplikátní decky.
    """
    return zlib.crc32(name.encode("utf-8")) & 0x7FFFFFFF or 1


def export_apkg(material: StudyMaterial, output_path: Path) -> int:
    """Vytvoří .apkg soubor. Vrací počet exportovaných karet.

    Raises:
        ValueError: materiál nemá žádné karty.
        ImportError: chybí genanki.
    """
    cards = collect_cards(material)
    if not cards:
        raise ValueError("Materiál neobsahuje žádné karty (pojmy ani otázky s odpověďmi).")

    import genanki  # lazy — viz docstring modulu

    deck_name = (material.title or "Hlas do textu").strip()[:80]
    model = genanki.Model(
        _stable_id("HlasDoTextu::ZakladniModel"),
        "Hlas do textu — základní",
        fields=[{"name": "Front"}, {"name": "Back"}],
        templates=[
            {
                "name": "Karta",
                "qfmt": "{{Front}}",
                "afmt": "{{FrontSide}}<hr id=answer>{{Back}}",
            }
        ],
    )
    deck = genanki.Deck(_stable_id(f"HlasDoTextu::{deck_name}"), deck_name)
    for front, back in cards:
        deck.add_note(genanki.Note(model=model, fields=[front, back]))

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    genanki.Package(deck).write_to_file(str(output_path))
    return len(cards)
