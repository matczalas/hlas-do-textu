"""Testy integrací vlny 1: kalendář (.ics), e-mail (mailto), Anki (.apkg), watch folder."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from app.core.integrations import anki_export, calendar_export, email_export
from app.core.models import (
    SECTION_KIND_DEFINITIONS,
    SECTION_KIND_PARAGRAPH,
    SECTION_KIND_QA,
    StudyMaterial,
    StudySection,
)

# ---------------------------------------------------------------------------
# Kalendář (.ics)
# ---------------------------------------------------------------------------


def test_find_meeting_text_extracts_paragraph():
    mat = StudyMaterial(
        title="Schůzka",
        sections=[
            StudySection("Termín další schůzky", SECTION_KIND_PARAGRAPH,
                         ["Příští čtvrtek v 17:30 u klienta doma."]),
        ],
    )
    assert calendar_export.find_meeting_text(mat) == "Příští čtvrtek v 17:30 u klienta doma."


def test_find_meeting_text_none_when_not_agreed():
    mat = StudyMaterial(
        title="Schůzka",
        sections=[
            StudySection("Termín další schůzky", SECTION_KIND_PARAGRAPH,
                         ["Termín další schůzky nebyl dohodnut."]),
        ],
    )
    assert calendar_export.find_meeting_text(mat) is None


def test_find_meeting_text_none_when_section_missing():
    mat = StudyMaterial(title="X", sections=[
        StudySection("Hlavní body", "bullets", ["a", "b"]),
    ])
    assert calendar_export.find_meeting_text(mat) is None


def test_build_ics_structure():
    ics = calendar_export.build_ics(
        summary="Schůzka s panem Novákem",
        start=datetime(2026, 6, 18, 17, 30, 0),
        duration_minutes=60,
        location="U klienta",
        description="Příští čtvrtek v 17:30",
        uid="fixed-uid@test",
        stamp=datetime(2026, 6, 12, 10, 0, 0),
    )
    assert "BEGIN:VCALENDAR" in ics and "END:VCALENDAR" in ics
    assert "BEGIN:VEVENT" in ics
    assert "DTSTART:20260618T173000" in ics
    assert "DTEND:20260618T183000" in ics  # +60 min
    assert "SUMMARY:Schůzka s panem Novákem" in ics
    assert "LOCATION:U klienta" in ics
    assert "UID:fixed-uid@test" in ics
    # CRLF řádky dle RFC
    assert "\r\n" in ics


def test_build_ics_escapes_special_chars():
    ics = calendar_export.build_ics(
        summary="Test; s čárkou, a středníkem",
        start=datetime(2026, 1, 1, 9, 0, 0),
    )
    assert "Test\\; s čárkou\\, a středníkem" in ics


def test_write_ics_creates_file(tmp_path: Path):
    out = tmp_path / "pozvanka.ics"
    result = calendar_export.write_ics(
        out, summary="Schůzka", start=datetime(2026, 6, 18, 17, 30)
    )
    assert result == out
    assert out.is_file()
    assert "BEGIN:VEVENT" in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# E-mail (mailto)
# ---------------------------------------------------------------------------


def test_extract_email_finds_subject_and_body():
    mat = StudyMaterial(
        title="Follow-up",
        sections=[
            StudySection("Předmět e-mailu", SECTION_KIND_PARAGRAPH,
                         ["Shrnutí naší schůzky a další kroky"]),
            StudySection("Tělo e-mailu", SECTION_KIND_PARAGRAPH,
                         ["Dobrý den, pane Nováku,", "děkuji za schůzku.", "S pozdravem"]),
        ],
    )
    result = email_export.extract_email(mat)
    assert result is not None
    subject, body = result
    assert subject == "Shrnutí naší schůzky a další kroky"
    assert body.startswith("Dobrý den, pane Nováku,")
    assert "\n\n" in body  # odstavce oddělené prázdným řádkem


def test_extract_email_none_without_body():
    mat = StudyMaterial(title="X", sections=[
        StudySection("Hlavní body", "bullets", ["a"]),
    ])
    assert email_export.extract_email(mat) is None


def test_build_mailto_encodes():
    url = email_export.build_mailto("Před & mět", "Tělo s diakritikou ěščř")
    assert url.startswith("mailto:?")
    assert "subject=" in url and "body=" in url
    assert "%26" in url  # & zakódováno
    assert " " not in url  # mezery zakódované


# ---------------------------------------------------------------------------
# Anki (.apkg)
# ---------------------------------------------------------------------------


def _flashcard_material() -> StudyMaterial:
    return StudyMaterial(
        title="Pasivní investování",
        sections=[
            StudySection("Pojmové karty", SECTION_KIND_DEFINITIONS,
                         [("TER", "Celkový roční poplatek fondu"), ("ETF", "Burzovně obchodovaný fond")]),
            StudySection("Otázkové karty", SECTION_KIND_QA,
                         [("Co je index?", "Koš akcií reprezentující trh"), ("Bez odpovědi", "")]),
        ],
    )


def test_collect_cards_skips_empty_back():
    cards = anki_export.collect_cards(_flashcard_material())
    fronts = [c[0] for c in cards]
    assert "TER" in fronts and "ETF" in fronts and "Co je index?" in fronts
    assert "Bez odpovědi" not in fronts  # prázdná zadní strana se vynechá
    assert len(cards) == 3


def test_has_cards():
    assert anki_export.has_cards(_flashcard_material())
    assert not anki_export.has_cards(
        StudyMaterial(title="X", sections=[StudySection("Body", "bullets", ["a"])])
    )


def test_export_apkg_creates_file(tmp_path: Path):
    out = tmp_path / "karty.apkg"
    count = anki_export.export_apkg(_flashcard_material(), out)
    assert count == 3
    assert out.is_file()
    assert out.stat().st_size > 1000  # apkg je sqlite zip, nějaký objem


def test_export_apkg_raises_without_cards(tmp_path: Path):
    mat = StudyMaterial(title="X", sections=[StudySection("Body", "bullets", ["a"])])
    with pytest.raises(ValueError):
        anki_export.export_apkg(mat, tmp_path / "x.apkg")


def test_export_apkg_stable_ids(tmp_path: Path):
    """Dva exporty stejného materiálu → stejná deck/model ID (žádné duplikáty v Anki)."""
    a = anki_export._stable_id("HlasDoTextu::Test")
    b = anki_export._stable_id("HlasDoTextu::Test")
    assert a == b and a > 0


# ---------------------------------------------------------------------------
# Watch folder
# ---------------------------------------------------------------------------


def _scanner(tmp_path: Path):
    from app.core.watch_folder import WatchScanner

    return WatchScanner(state_path=tmp_path / "state.json")


def test_watch_requires_stability_between_scans(tmp_path: Path):
    """Soubor je 'ready' až když je mezi dvěma skeny stabilní."""
    folder = tmp_path / "watch"
    folder.mkdir()
    rec = folder / "nahravka.mp3"
    rec.write_bytes(b"x" * 1000)

    sc = _scanner(tmp_path)
    # První sken: soubor je nový → ještě ne ready (čeká na stabilitu)
    assert sc.scan(folder) == []
    # Druhý sken: beze změny → ready
    ready = sc.scan(folder)
    assert ready == [rec]


def test_watch_ignores_unsupported(tmp_path: Path):
    folder = tmp_path / "watch"
    folder.mkdir()
    (folder / "dokument.pdf").write_bytes(b"x" * 1000)  # prezentace, ne nahrávka
    (folder / "poznamka.txt").write_text("x")

    sc = _scanner(tmp_path)
    sc.scan(folder)
    assert sc.scan(folder) == []  # nic audio/video


def test_watch_skips_processed(tmp_path: Path):
    folder = tmp_path / "watch"
    folder.mkdir()
    rec = folder / "a.m4a"
    rec.write_bytes(b"x" * 1000)

    sc = _scanner(tmp_path)
    sc.scan(folder)
    assert sc.scan(folder) == [rec]
    sc.mark_processed(rec)
    # Po označení už se znovu nenabídne
    assert sc.scan(folder) == []


def test_watch_state_persists(tmp_path: Path):
    folder = tmp_path / "watch"
    folder.mkdir()
    rec = folder / "a.m4a"
    rec.write_bytes(b"x" * 1000)

    sc = _scanner(tmp_path)
    sc.mark_processed(rec)

    # Nový scanner načte stav z disku → soubor je pořád "zpracovaný"
    sc2 = _scanner(tmp_path)
    sc2.load()
    sc2.scan(folder)
    assert sc2.scan(folder) == []


def test_watch_reprocesses_changed_file(tmp_path: Path):
    """Když uživatel nahrávku přepíše (jiná velikost), zpracuje se znovu."""
    folder = tmp_path / "watch"
    folder.mkdir()
    rec = folder / "a.m4a"
    rec.write_bytes(b"x" * 1000)

    sc = _scanner(tmp_path)
    sc.scan(folder)
    sc.scan(folder)
    sc.mark_processed(rec)
    assert sc.scan(folder) == []

    # Přepsání souboru (nová velikost) → znovu projde stabilizací a nabídne se
    rec.write_bytes(b"y" * 2000)
    sc.scan(folder)  # nová signatura, čeká na stabilitu
    assert sc.scan(folder) == [rec]
