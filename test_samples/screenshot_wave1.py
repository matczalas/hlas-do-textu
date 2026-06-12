"""Screenshoty vlny 1: dialog s akčními tlačítky + Nastavení s watch sekcí + kalendářový dialog."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.core.models import SECTION_KIND_KEY_VALUE, SECTION_KIND_PARAGRAPH, StudyMaterial, StudySection
from app.gui.styles import theme
from app.gui.widgets.calendar_dialog import CalendarDialog
from app.gui.widgets.settings_dialog import SettingsDialog
from app.logging_setup import setup_logging
from app.settings import AppSettings

OUT = Path("/tmp/hdt_wave1_shots")
OUT.mkdir(exist_ok=True)


def shot(w, name):
    p = OUT / f"{name}.png"
    w.grab().save(str(p))
    print(f"  -> {p}")


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    theme.apply_theme(app, role="sales", dark=False)

    # Nastavení — tab Výstup s watch sekcí
    s = AppSettings()
    s.app_role = "sales"
    s.watch_enabled = True
    s.watch_folder = "/Users/macbook/Nahrávky"
    dlg = SettingsDialog(s)
    dlg._sidebar.setCurrentRow(2)  # Výstup
    dlg.show(); app.processEvents(); time.sleep(0.4); app.processEvents()
    shot(dlg, "settings_watch")
    dlg.close()

    # Kalendářový dialog
    cal = CalendarDialog(
        default_summary="Schůzka s panem Novákem",
        meeting_hint="Příští čtvrtek v 17:30 u klienta doma, za účasti manželky.",
        output_dir=OUT,
    )
    cal.show(); app.processEvents(); time.sleep(0.3); app.processEvents()
    shot(cal, "calendar_dialog")
    cal.close()
    print("Hotovo:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
