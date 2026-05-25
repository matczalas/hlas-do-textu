"""Spustí aplikaci a po načtení udělá screenshot hlavního okna + dialogu.

Spouštět:
    python test_samples/screenshot_ui.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.core.models import SourceFile, SourceKind
from app.gui.main_window import MainWindow
from app.gui.widgets.first_run_dialog import FirstRunDialog
from app.gui.widgets.settings_dialog import SettingsDialog
from app.logging_setup import setup_logging
from app.settings import AppSettings

OUT_DIR = Path("/tmp/hdt_shots")
OUT_DIR.mkdir(exist_ok=True)


def shot(widget, name: str) -> Path:
    """Uloží screenshot widgetu (přes Qt grab — nezávisí na window manageru)."""
    path = OUT_DIR / f"{name}.png"
    widget.grab().save(str(path))
    print(f"  -> {path} ({path.stat().st_size // 1024} KB)")
    return path


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Hlas do textu")

    # 1) First-run dialog
    print("[1/4] First-run dialog…")
    settings = AppSettings()
    dlg = FirstRunDialog(settings)
    dlg.show()
    app.processEvents()
    time.sleep(0.3)
    shot(dlg, "01_first_run")
    dlg.close()

    # 2) Hlavní okno — empty state
    print("[2/4] Empty state…")
    window = MainWindow()
    window.resize(960, 760)
    window.show()
    app.processEvents()
    time.sleep(0.5)
    shot(window, "02_empty_state")

    # 3) Hlavní okno se 3 importovanými soubory
    print("[3/4] S importovanými soubory…")
    sources = [
        SourceFile(path=Path("/Users/student/Downloads/prednaska_uvod.mp4"),
                   kind=SourceKind.AUDIO_VIDEO, label="Část 1: Úvod"),
        SourceFile(path=Path("/Users/student/Downloads/prednaska_pokrocile.m4a"),
                   kind=SourceKind.AUDIO_VIDEO, label="Část 2: Pokročilé"),
        SourceFile(path=Path("/Users/student/Documents/slidy_kurz.pdf"),
                   kind=SourceKind.PRESENTATION, label="Slidy ke kurzu"),
    ]
    window._table.add_sources(sources)
    window._prompt_editor.set_text(
        "Kurz Úvod do makroekonomie, semestr jaro 2026, prof. Novotný. "
        "Téma: monetární politika ČNB. Chci body ke zkoušce + definice klíčových pojmů."
    )
    app.processEvents()
    time.sleep(0.3)
    shot(window, "03_with_sources")

    # 4) Settings dialog
    print("[4/4] Settings dialog…")
    settings_dlg = SettingsDialog(settings, window)
    settings_dlg.show()
    app.processEvents()
    time.sleep(0.3)
    shot(settings_dlg, "04_settings")
    settings_dlg.close()

    QTimer.singleShot(200, app.quit)
    app.exec()
    print("Hotovo. Soubory v:", OUT_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
