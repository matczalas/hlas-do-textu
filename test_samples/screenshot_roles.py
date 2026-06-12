"""Screenshoty hlavního okna v každé roli — kontrola accent barvy, role čipu,
wordmark subtitle a dropdownu šablon.

Spouštět:  PYTHONPATH=. python test_samples/screenshot_roles.py
Výstup:    /tmp/hdt_role_shots/*.png
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.gui.styles import theme
from app.logging_setup import setup_logging
from app.settings import AppSettings

OUT_DIR = Path("/tmp/hdt_role_shots")
OUT_DIR.mkdir(exist_ok=True)

ROLES = ["hr", "coach", "spolek", "podcast"]


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)

    for i, role in enumerate(ROLES):
        dark = role == "coach"  # jeden vzorek v tmavém režimu
        settings = AppSettings()
        settings.app_role = role
        settings.dark_mode = dark
        settings.first_run_done = True
        theme.apply_theme(app, role=role, dark=dark)

        # MainWindow čte settings přes load_settings — monkeypatchneme
        import app.gui.main_window as mw

        original_load = mw.load_settings
        mw.load_settings = lambda s=settings: s  # type: ignore[assignment]
        try:
            window = mw.MainWindow()
            window.resize(1000, 760)
            # Do editoru (tam je prompt editor s dropdownem šablon)
            window._enter_editor()
            window.show()
            app.processEvents()
            time.sleep(0.5)
            app.processEvents()
            mode = "dark" if dark else "light"
            path = OUT_DIR / f"{i}_{role}_{mode}.png"
            window.grab().save(str(path))
            print(f"  -> {path}")
            window._stop_all_workers()
            window.close()
            app.processEvents()
        finally:
            mw.load_settings = original_load

    print("Hotovo:", OUT_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
