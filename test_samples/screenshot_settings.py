"""Screenshoty dialogu Nastavení — světlý i tmavý režim, všechny taby.

Spouštět:  python test_samples/screenshot_settings.py
Výstup:    /tmp/hdt_settings_shots/*.png
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.gui.styles import theme
from app.gui.widgets.settings_dialog import SettingsDialog
from app.logging_setup import setup_logging
from app.settings import AppSettings

OUT_DIR = Path("/tmp/hdt_settings_shots")
OUT_DIR.mkdir(exist_ok=True)


def shot(widget, name: str) -> None:
    path = OUT_DIR / f"{name}.png"
    widget.grab().save(str(path))
    print(f"  -> {path}")


def capture_all_tabs(app: QApplication, dark: bool, label: str) -> None:
    settings = AppSettings()
    settings.dark_mode = dark
    theme.apply_theme(app, role=settings.app_role, dark=dark)

    dlg = SettingsDialog(settings)
    dlg.show()
    app.processEvents()
    time.sleep(0.4)
    app.processEvents()

    tab_names = ["ai", "prepis", "vystup", "licence"]
    for i, tab in enumerate(tab_names):
        dlg._sidebar.setCurrentRow(i)
        app.processEvents()
        time.sleep(0.15)
        app.processEvents()
        shot(dlg, f"{label}_{i}_{tab}")

    # Malé okno — ověřit, že footer (Uložit) nezmizí na malém monitoru
    dlg.resize(640, 500)
    dlg._sidebar.setCurrentRow(0)
    app.processEvents()
    time.sleep(0.15)
    app.processEvents()
    shot(dlg, f"{label}_small_640x500")

    dlg.close()
    app.processEvents()


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    print("[1/2] Světlý režim…")
    capture_all_tabs(app, dark=False, label="light")
    print("[2/2] Tmavý režim…")
    capture_all_tabs(app, dark=True, label="dark")
    print("Hotovo:", OUT_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
