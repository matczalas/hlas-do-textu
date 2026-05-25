"""Entry point: `python -m app` nebo PyInstaller exe."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _install_crash_handler() -> None:
    """Globální hook pro neošetřené výjimky.

    Bez něj se PyInstaller .exe občas zavře beze stopy ('Python script přestal fungovat').
    S hookem všechno skončí v logu + uživatel vidí messagebox se zprávou.
    """
    def _excepthook(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        formatted = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))

        # Zápis do log souboru (i kdyby loguru ještě nebylo nastaveno)
        try:
            from app.config import LOGS_DIR, ensure_dirs

            ensure_dirs()
            crash_file = LOGS_DIR / "crash.log"
            with crash_file.open("a", encoding="utf-8") as fh:
                fh.write("\n" + "=" * 80 + "\n")
                fh.write(formatted)
        except Exception:
            crash_file = None  # noqa: F841

        # GUI messagebox (pokud Qt už běží)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            app = QApplication.instance()
            if app is not None:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Icon.Critical)
                msg.setWindowTitle("Hlas do textu — neočekávaná chyba")
                msg.setText(
                    "Bohužel došlo k neočekávané chybě a aplikace se může nečekaně zavřít.\n\n"
                    f"Detail: {exc_type.__name__}: {exc_value}\n\n"
                    "Detailní log najdeš v: %LOCALAPPDATA%\\HlasDoTextu\\logs\\crash.log\n"
                    "Můžeš ho přiložit při hlášení problému."
                )
                msg.setDetailedText(formatted)
                msg.exec()
        except Exception:
            pass

        # Pro jistotu i do stderr (vidět při spuštění z terminálu) — ale jen pokud existuje
        if sys.stderr is not None:
            try:
                print(formatted, file=sys.stderr)
            except Exception:
                pass

    sys.excepthook = _excepthook


def main() -> int:
    _install_crash_handler()

    # Musí se nastavit PŘED QApplication
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtWidgets import QApplication

        from app.config import ensure_dirs
        from app.gui.main_window import MainWindow
        from app.logging_setup import setup_logging
    except Exception as exc:
        # Předčasná chyba (chybí dependency) — zkus alespoň napsat do souboru
        crash_path = Path.home() / "HlasDoTextu-crash.txt"
        try:
            crash_path.write_text(
                f"Při startu se nepodařilo načíst závislosti:\n{type(exc).__name__}: {exc}\n\n"
                + traceback.format_exc(),
                encoding="utf-8",
            )
        except Exception:
            pass
        if sys.stderr is not None:
            try:
                print(f"FATAL: {exc}", file=sys.stderr)
                print(f"Detail uložen do: {crash_path}", file=sys.stderr)
            except Exception:
                pass
        return 2

    setup_logging(verbose=os.environ.get("HDT_DEBUG") == "1")

    from loguru import logger

    logger.info("Spouštím Hlas do textu na platform={} python={}", sys.platform, sys.version.split()[0])

    try:
        ensure_dirs()
    except Exception as exc:
        logger.exception("Selhalo ensure_dirs(): {}", exc)
        # Pokračujeme — bude nahlášeno přes excepthook pokud znova pad

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setApplicationName("Hlas do textu")
    app.setOrganizationName("Safe4Future z. ú.")

    # License gate — bez platného klíče se nikam nedostaneme
    from app.licensing import is_activated

    if not is_activated():
        from app.gui.widgets.activation_dialog import ActivationDialog

        logger.info("Aplikace není aktivovaná, zobrazuji ActivationDialog")
        activation = ActivationDialog()
        if activation.exec() != activation.DialogCode.Accepted:
            logger.info("Aktivace zamítnuta uživatelem, končím")
            return 0
        logger.info("Aktivace úspěšná")

    try:
        window = MainWindow()
        window.show()
    except Exception as exc:
        logger.exception("Selhala inicializace hlavního okna: {}", exc)
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(
            None,
            "Chyba při startu",
            f"Aplikaci se nepodařilo otevřít:\n\n{type(exc).__name__}: {exc}\n\n"
            "Detail v %LOCALAPPDATA%\\HlasDoTextu\\logs\\app.log",
        )
        return 3

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
