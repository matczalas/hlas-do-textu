"""Hlavní okno aplikace — sestavuje widgety, řídí flow.

Redesign: tři sekce v plynoucím layoutu (Zdroje · Kontext · Spuštění),
globální QSS z app/gui/styles/app.qss, accent #205ca8, čisté typografie.
Business logika nezměněna — všechny signály/sloty/atributy zůstávají.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.core.audio_extract import probe_duration_seconds
from app.core.model_downloader import model_is_cached
from app.core.models import JobConfig, JobMode, SourceFile, SourceKind
from app.core.pipeline import estimate_total_processing_seconds, format_duration_human
from app.gui.widgets.empty_state import EmptyStateWidget
from app.gui.widgets.file_drop_zone import FileDropZone
from app.gui.widgets.first_run_dialog import FirstRunDialog
from app.gui.widgets.icons import icon, icon_size, pixmap
from app.gui.widgets.ollama_status import StatusBar
from app.gui.widgets.progress_panel import ProgressPanel
from app.gui.widgets.prompt_editor import PromptEditor
from app.gui.widgets.settings_dialog import SettingsDialog
from app.gui.widgets.source_table import SourceTable
from app.gui.workers.model_download_worker import ModelDownloadWorker
from app.gui.workers.pipeline_worker import PipelineWorker
from app.gui.workers.regenerate_worker import RegenerateWorker
from app.settings import (
    AppSettings,
    get_gemini_api_key,
    load_settings,
    save_settings,
)

ACCENT = "#205ca8"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _divider() -> QWidget:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("background: palette(midlight); max-height: 1px; border: none;")
    line.setFixedHeight(1)
    return line


# --------------------------------------------------------------------------- #
# MainWindow
# --------------------------------------------------------------------------- #


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Hlas do textu — Safe4Future")
        self.resize(1080, 800)
        self.setMinimumSize(960, 720)

        self._settings: AppSettings = load_settings()
        self._pipeline_worker = PipelineWorker(self)
        self._model_worker = ModelDownloadWorker(self)
        self._regenerate_worker = RegenerateWorker(self)

        from app.gui.workers.update_worker import (
            UpdateCheckWorker,
            UpdateDownloadWorker,
        )
        self._update_check = UpdateCheckWorker(self)
        self._update_download = UpdateDownloadWorker(self)
        self._available_update = None  # UpdateInfo | None
        self._update_installer_path = None  # Path | None

        self._tray = self._init_tray()

        self._load_stylesheet()
        self._build_ui()
        self._wire_signals()

        QTimer.singleShot(50, self._post_show_init)

    # ------ Stylesheet ------

    def _load_stylesheet(self) -> None:
        """Načte globální QSS z app/gui/styles/app.qss."""
        qss_path = Path(__file__).resolve().parent / "styles" / "app.qss"
        try:
            self.setStyleSheet(qss_path.read_text(encoding="utf-8"))
        except OSError as exc:
            logger.warning("Stylesheet nešel načíst ({}): {}", qss_path, exc)

    # ------ System tray ------

    def _init_tray(self) -> QSystemTrayIcon | None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        icon_path = Path(__file__).resolve().parent.parent / "resources" / "icon.png"
        ic = QIcon(str(icon_path)) if icon_path.is_file() else QIcon()
        tray = QSystemTrayIcon(ic, self)
        tray.setToolTip("Hlas do textu")
        tray.show()
        return tray

    def _notify(self, title: str, message: str, is_error: bool = False) -> None:
        if self._tray is None:
            return
        icon_type = (
            QSystemTrayIcon.MessageIcon.Critical
            if is_error
            else QSystemTrayIcon.MessageIcon.Information
        )
        self._tray.showMessage(title, message, icon_type, 8000)

    # ------ UI ------

    def _build_ui(self) -> None:
        central = QWidget(self)
        central.setObjectName("Central")
        central.setStyleSheet(
            "QWidget#Central { background: palette(window); }"
        )
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 20, 28, 22)
        root.setSpacing(14)

        # ---- Header bar -----------------------------------------------
        root.addLayout(self._build_header())

        # ---- Update banner (default skrytý) ---------------------------
        from app.gui.widgets.update_banner import UpdateBanner

        self._update_banner = UpdateBanner()
        self._update_banner.update_requested.connect(self._on_update_requested)
        self._update_banner.restart_requested.connect(self._on_update_restart)
        root.addWidget(self._update_banner)

        # ---- Drop zone (vždy nahoře) ----------------------------------
        self._drop_zone = FileDropZone()
        self._drop_zone.set_last_dir(self._settings.last_used_sources_dir)
        root.addWidget(self._drop_zone)

        # ---- Tabulka / empty state ------------------------------------
        self._table = SourceTable()
        self._empty_state = EmptyStateWidget()
        self._source_stack = QStackedWidget()
        self._source_stack.addWidget(self._empty_state)  # index 0
        self._source_stack.addWidget(self._table)        # index 1
        self._source_stack.setCurrentIndex(0)
        root.addWidget(self._source_stack, 1)

        # ---- Kontext pro AI -------------------------------------------
        self._prompt_editor = PromptEditor()
        root.addWidget(self._prompt_editor)

        # ---- Output + Progress ----------------------------------------
        root.addLayout(self._build_output_row())
        self._progress = ProgressPanel()
        root.addWidget(self._progress, 1)

        # ---- CTA tlačítka ---------------------------------------------
        root.addLayout(self._build_action_row())

        # Backward compatible alias
        self._run_btn = self._run_full_btn

        self._build_menu()

    # ---- Header bar -------------------------------------------------------

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        title = QLabel("Hlas do textu")
        f = QFont()
        f.setPointSize(17)
        f.setWeight(QFont.Weight.DemiBold)
        title.setFont(f)
        row.addWidget(title)

        row.addStretch(1)

        # Status pills
        self._status_bar = StatusBar()
        row.addWidget(self._status_bar)

        # Nastavení tlačítko
        settings_btn = QPushButton("Nastavení")
        settings_btn.setObjectName("Ghost")
        settings_btn.setIcon(icon("settings", size=15, color="#7a7a7a"))
        settings_btn.setIconSize(icon_size(15))
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.clicked.connect(self._open_settings)
        settings_btn.setStyleSheet(
            "QPushButton#Ghost { padding: 7px 12px; border: 1px solid palette(midlight); "
            "border-radius: 8px; color: palette(text); background: palette(base); }"
            "QPushButton#Ghost:hover { background: palette(midlight); border-color: " + ACCENT + "; }"
        )
        row.addWidget(settings_btn)

        return row

    # ---- Output row -------------------------------------------------------

    def _build_output_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        out_icon = QLabel()
        out_icon.setPixmap(pixmap("folder", size=14, color="#7a7a7a"))
        out_icon.setFixedSize(16, 16)
        row.addWidget(out_icon)

        self._output_value = QLabel(self._settings.output_dir)
        self._output_value.setStyleSheet(
            "color: palette(placeholder-text); font-size: 12px;"
        )
        self._output_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self._output_value, 1)

        change_out_btn = QPushButton("Změnit")
        change_out_btn.setObjectName("Link")
        change_out_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        change_out_btn.setStyleSheet(
            "QPushButton#Link { background: transparent; border: none; "
            "color: " + ACCENT + "; padding: 4px 8px; font-weight: 600; }"
            "QPushButton#Link:hover { text-decoration: underline; }"
        )
        change_out_btn.clicked.connect(self._change_output_dir)
        row.addWidget(change_out_btn)

        return row

    # ---- Action row -------------------------------------------------------

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        self._run_transcribe_btn = QPushButton("Přepis")
        self._run_transcribe_btn.setObjectName("Secondary")
        self._run_transcribe_btn.setIcon(icon("document", size=16, color=ACCENT))
        self._run_transcribe_btn.setIconSize(icon_size(16))
        self._run_transcribe_btn.setMinimumHeight(46)
        self._run_transcribe_btn.setMinimumWidth(160)
        self._run_transcribe_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_transcribe_btn.setToolTip(
            "Jen Word s přepisem. Rychlé, offline."
        )

        self._run_full_btn = QPushButton("Přepis + AI body")
        self._run_full_btn.setObjectName("Primary")
        self._run_full_btn.setIcon(icon("sparkles", size=16, color="#ffffff"))
        self._run_full_btn.setIconSize(icon_size(16))
        self._run_full_btn.setMinimumHeight(46)
        self._run_full_btn.setMinimumWidth(200)
        self._run_full_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_full_btn.setToolTip(
            "Přepis + strukturované poznámky od AI."
        )

        row.addStretch(1)
        row.addWidget(self._run_transcribe_btn)
        row.addWidget(self._run_full_btn)
        return row

    # ---- Menu -------------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&Soubor")

        regen_action = QAction("Vytvořit body z existujícího přepisu…", self)
        regen_action.setStatusTip(
            "Použij dříve uložený .txt přepis a vygeneruj nový .docx s body"
        )
        regen_action.triggered.connect(self._regenerate_from_existing)
        file_menu.addAction(regen_action)
        file_menu.addSeparator()

        quit_action = QAction("Konec", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        settings_menu = menubar.addMenu("&Nastavení")
        open_settings = QAction("Otevřít nastavení…", self)
        open_settings.setShortcut(QKeySequence.StandardKey.Preferences)
        open_settings.triggered.connect(self._open_settings)
        settings_menu.addAction(open_settings)

        help_menu = menubar.addMenu("&Nápověda")
        about = QAction("O aplikaci", self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

    # ------ Signals ------

    def _wire_signals(self) -> None:
        self._drop_zone.sources_added.connect(self._on_sources_added)
        self._table.files_changed.connect(self._refresh_run_button)
        self._run_full_btn.clicked.connect(lambda: self._run_pipeline(JobMode.FULL))
        self._run_transcribe_btn.clicked.connect(
            lambda: self._run_pipeline(JobMode.TRANSCRIBE_ONLY)
        )
        self._progress.cancel_button.clicked.connect(self._pipeline_worker.cancel)

        self._pipeline_worker.progress.connect(self._progress.update)
        self._pipeline_worker.transcript_text.connect(self._progress.append_transcript_line)
        self._pipeline_worker.finished_ok.connect(self._on_pipeline_ok)
        self._pipeline_worker.finished_error.connect(self._on_pipeline_error)

        self._model_worker.progress.connect(self._on_model_progress)
        self._model_worker.finished_ok.connect(self._on_model_ready)
        self._model_worker.finished_error.connect(self._on_model_error)

        self._update_check.finished.connect(self._on_update_check_finished)
        self._update_download.progress.connect(self._on_update_progress)
        self._update_download.finished_ok.connect(self._on_update_downloaded)
        self._update_download.finished_error.connect(self._on_update_download_error)

        self._regenerate_worker.progress.connect(self._progress.update)
        self._regenerate_worker.finished_ok.connect(self._on_pipeline_ok)
        self._regenerate_worker.finished_error.connect(
            lambda msg: self._on_pipeline_error(msg, False)
        )

        self._refresh_run_button()

    # ------ Lifecycle ------

    def _post_show_init(self) -> None:
        if not self._settings.first_run_done:
            dlg = FirstRunDialog(self._settings, self)
            dlg.exec()
            save_settings(self._settings)

        self._maybe_offer_model_download()
        self._status_bar.refresh(get_gemini_api_key())

        # Tichá kontrola aktualizace po 5 s — nezdržuje startup ani s pomalou sítí
        QTimer.singleShot(5000, self._silent_update_check)

    def _silent_update_check(self) -> None:
        """Spustí tichou kontrolu update přes GitHub API. Neukáže nic pokud není update."""
        if self._update_check.is_running() or self._update_download.is_running():
            return
        logger.info("Spouštím tichou kontrolu aktualizace…")
        self._update_check.start()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._pipeline_worker.is_running():
            answer = QMessageBox.question(
                self,
                "Zpracování běží",
                "Zpracování ještě běží. Opravdu chcete zavřít aplikaci? Postup se ztratí.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        # Zastavit VŠECHNY background workery — jinak Qt vyhodí fatal abort při
        # destrukci QMainWindow pokud nějaký QThread ještě běží.
        self._stop_all_workers()

        self._settings.last_used_sources_dir = self._drop_zone.last_dir
        save_settings(self._settings)
        event.accept()

    def _stop_all_workers(self) -> None:
        """Bezpečně ukončí všechny QThread workery v aplikaci."""
        for worker_attr in (
            "_pipeline_worker",
            "_model_worker",
            "_regenerate_worker",
            "_update_check",
            "_update_download",
        ):
            w = getattr(self, worker_attr, None)
            if w is not None and hasattr(w, "stop_and_wait"):
                try:
                    w.stop_and_wait()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("stop_and_wait({}) selhalo: {}", worker_attr, exc)

        # Status bar má vlastní QThread
        try:
            if hasattr(self, "_status_bar") and hasattr(self._status_bar, "stop_and_wait"):
                self._status_bar.stop_and_wait()
        except Exception as exc:  # noqa: BLE001
            logger.warning("status_bar stop selhalo: {}", exc)

    # ------ Handlers ------

    def _on_sources_added(self, sources: list[SourceFile]) -> None:
        if not sources:
            return
        self._table.add_sources(sources)
        self._output_value.setText(self._settings.output_dir)

    def _refresh_run_button(self) -> None:
        sources = self._table.sources()
        has_audio = any(s.kind == SourceKind.AUDIO_VIDEO for s in sources)
        has_any = bool(sources)
        running = (
            self._pipeline_worker.is_running()
            or self._regenerate_worker.is_running()
        )

        self._run_transcribe_btn.setEnabled(has_audio and not running)
        self._run_full_btn.setEnabled(has_any and not running)

        self._source_stack.setCurrentIndex(1 if has_any else 0)

    def _change_output_dir(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        chosen = QFileDialog.getExistingDirectory(
            self, "Vyber výstupní složku", self._settings.output_dir
        )
        if chosen:
            self._settings.output_dir = chosen
            self._output_value.setText(chosen)
            save_settings(self._settings)

    def _open_settings(self) -> None:
        previous_model = self._settings.whisper_model
        dlg = SettingsDialog(self._settings, self)
        if dlg.exec():
            save_settings(self._settings)
            self._output_value.setText(self._settings.output_dir)
            self._status_bar.refresh(get_gemini_api_key())
            if self._settings.whisper_model != previous_model:
                self._maybe_offer_model_download()

    # ------ Pipeline ------

    def _run_pipeline(self, mode: JobMode = JobMode.FULL) -> None:
        if self._pipeline_worker.is_running():
            return

        sources = self._table.sources()
        if not sources:
            QMessageBox.information(
                self, "Žádné soubory", "Přidej alespoň jednu nahrávku nebo prezentaci."
            )
            return

        if mode == JobMode.TRANSCRIBE_ONLY:
            if not any(s.kind == SourceKind.AUDIO_VIDEO for s in sources):
                QMessageBox.information(
                    self,
                    "Chybí nahrávka",
                    "Pro 'Jen přepis' potřebuješ přidat alespoň jednu nahrávku "
                    "(mp3/mp4/wav/m4a).",
                )
                return

        api_key = get_gemini_api_key() if mode == JobMode.FULL else None
        if mode == JobMode.FULL:
            if not self._settings.prefer_offline and not api_key:
                answer = QMessageBox.question(
                    self,
                    "Chybí Gemini klíč",
                    "Nemáš nastavený Gemini API klíč. Zkusit pokračovat s lokální "
                    "Ollama? (Pokud Ollama neběží, zpracování selže.)\n\n"
                    "Tip: pokud chceš jen přepis bez AI, zavři tento dialog a klikni "
                    "tlačítko 'Jen přepis'.",
                )
                if answer != QMessageBox.StandardButton.Yes:
                    self._open_settings()
                    return

            if (
                not self._settings.prefer_offline
                and api_key
                and not self._settings.ai_consent_gemini
            ):
                answer = QMessageBox.question(
                    self,
                    "Souhlas s odesláním do Gemini",
                    "Bez souhlasu nelze poslat data do Google Gemini. Otevřít Nastavení?",
                )
                if answer == QMessageBox.StandardButton.Yes:
                    self._open_settings()
                return

        if not model_is_cached(self._settings.whisper_model):
            answer = QMessageBox.question(
                self,
                "Whisper model není stažený",
                f"Model '{self._settings.whisper_model}' není zatím stažený. "
                "Stáhnout ho teď?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self._start_model_download()
            return

        if not self._confirm_time_estimate(sources, mode):
            return

        job = JobConfig(
            sources=sources,
            user_prompt=self._prompt_editor.text(),
            output_dir=Path(self._settings.output_dir),
            mode=mode,
            whisper_model=self._settings.whisper_model,
            language=self._settings.language,
            ai_consent_gemini=self._settings.ai_consent_gemini,
            prefer_offline=self._settings.prefer_offline,
        )

        self._progress.reset()
        self._progress.set_busy(True)
        self._run_btn.setEnabled(False)
        try:
            self._pipeline_worker.start(job, api_key)
        except Exception as exc:  # noqa: BLE001
            self._progress.set_busy(False)
            self._run_btn.setEnabled(True)
            QMessageBox.critical(
                self, "Chyba", f"Nepodařilo se spustit zpracování: {exc}"
            )

    def _on_pipeline_ok(self, result) -> None:
        self._progress.set_busy(False)
        self._refresh_run_button()
        self._progress.append_message(f"✅ Hotovo. Výstup: {result.output_path}")

        summary = self._format_result_summary(result)
        self._notify(
            "Hlas do textu — hotovo ✅",
            f"Soubor: {result.output_path.name}\n{summary}",
        )

        msg = QMessageBox(self)
        msg.setWindowTitle("Hotovo")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(
            f"<b>Studijní materiál uložen.</b><br><br>"
            f"📁 <code>{result.output_path}</code><br><br>"
            f"<b>Souhrn:</b><br>{summary}"
        )
        msg.setTextFormat(Qt.TextFormat.RichText)
        open_doc_btn = msg.addButton("Otevřít dokument", QMessageBox.ButtonRole.AcceptRole)
        open_folder_btn = msg.addButton("Otevřít složku", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("Zavřít", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(open_doc_btn)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked is open_doc_btn:
            self._open_file(result.output_path)
        elif clicked is open_folder_btn:
            self._open_file(result.output_path.parent)

    @staticmethod
    def _format_result_summary(result) -> str:
        material = result.material
        word_count = sum(len(t.text.split()) for t in result.transcripts)
        parts = [
            f"• {len(material.bullets)} hlavních bodů",
            f"• {len(material.terms)} klíčových pojmů",
            f"• {len(material.examples)} příkladů",
        ]
        if material.further_study:
            parts.append(f"• {len(material.further_study)} doporučení k dalšímu studiu")
        if word_count > 0:
            parts.append(f"• přepis cca {word_count:,} slov".replace(",", " "))
        if result.slides:
            slide_total = sum(s.slide_count for s in result.slides)
            parts.append(f"• {slide_total} slidů z prezentací")
        return "<br>".join(parts)

    def _on_pipeline_error(self, message: str, cancelled: bool) -> None:
        self._progress.set_busy(False)
        self._refresh_run_button()
        if cancelled:
            self._progress.append_message("⚠️ Zpracování zrušeno.")
            QMessageBox.information(self, "Zrušeno", "Zpracování bylo zrušeno.")
        else:
            self._progress.append_message(f"❌ {message}")
            self._notify("Hlas do textu — chyba ❌", message[:120], is_error=True)
            QMessageBox.critical(self, "Chyba", message)

    def _regenerate_from_existing(self) -> None:
        if self._pipeline_worker.is_running() or self._regenerate_worker.is_running():
            QMessageBox.information(
                self, "Zpracování běží", "Nejdřív počkej, až doběhne aktuální úloha."
            )
            return

        from PySide6.QtWidgets import QFileDialog, QInputDialog

        start_dir = self._settings.output_dir
        txt_path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Vyber soubor s přepisem",
            start_dir,
            "Textový přepis (*.txt);;Všechny soubory (*)",
        )
        if not txt_path_str:
            return
        txt_path = Path(txt_path_str)

        new_prompt, ok = QInputDialog.getMultiLineText(
            self,
            "Upravit popis pro AI",
            "Můžeš upravit popis / instrukce. Aplikace pak vygeneruje nové body ze "
            "stávajícího přepisu (bez opakovaného přepisování audia).",
            self._prompt_editor.text(),
        )
        if not ok:
            return

        api_key = get_gemini_api_key()
        if (
            not self._settings.prefer_offline
            and api_key
            and not self._settings.ai_consent_gemini
        ):
            QMessageBox.information(
                self,
                "Souhlas s odesláním do Gemini",
                "Bez souhlasu nelze poslat data do Google Gemini. Otevři Nastavení.",
            )
            return

        self._progress.reset()
        self._progress.append_message(f"Regenerace bodů z přepisu: {txt_path.name}")
        self._progress.set_busy(True)
        self._run_btn.setEnabled(False)
        try:
            self._regenerate_worker.start(
                txt_path=txt_path,
                user_prompt=new_prompt,
                output_dir=Path(self._settings.output_dir),
                gemini_api_key=api_key,
                ai_consent_gemini=self._settings.ai_consent_gemini,
                prefer_offline=self._settings.prefer_offline,
            )
        except Exception as exc:  # noqa: BLE001
            self._progress.set_busy(False)
            self._run_btn.setEnabled(True)
            QMessageBox.critical(
                self, "Chyba", f"Nepodařilo se spustit regeneraci: {exc}"
            )

    def _confirm_time_estimate(
        self, sources: list[SourceFile], mode: JobMode = JobMode.FULL
    ) -> bool:
        durations: list[float] = []
        for src in sources:
            if src.kind != SourceKind.AUDIO_VIDEO:
                continue
            d = probe_duration_seconds(src.path) or 0.0
            durations.append(d)
        if not durations:
            return True

        total_audio = sum(durations)
        has_ai = not self._settings.prefer_offline
        transcribe_only = mode == JobMode.TRANSCRIBE_ONLY
        low, high = estimate_total_processing_seconds(
            durations,
            whisper_model=self._settings.whisper_model,
            has_ai=has_ai,
            transcribe_only=transcribe_only,
        )
        audio_label = format_duration_human(total_audio)
        run_label = (
            format_duration_human(high)
            if high - low < 60
            else f"mezi {format_duration_human(low)} a {format_duration_human(high)}"
        )

        mode_label = "Jen přepis" if transcribe_only else "Přepis + body z AI"

        msg = QMessageBox(self)
        msg.setWindowTitle(f"Spustit: {mode_label}?")
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setText(
            f"<b>Režim:</b> {mode_label}<br>"
            f"<b>Celková délka nahrávek:</b> {audio_label}<br>"
            f"<b>Odhadovaná doba zpracování:</b> {run_label}<br><br>"
            "Můžeš mezitím dělat něco jiného — aplikace ti pošle notifikaci, "
            "až bude hotovo.<br><br>Spustit?"
        )
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
        return msg.exec() == QMessageBox.StandardButton.Yes

    # ------ Model download ------

    def _maybe_offer_model_download(self) -> None:
        if model_is_cached(self._settings.whisper_model):
            return
        msg = (
            f"Whisper model '{self._settings.whisper_model}' není zatím stažený.\n"
            f"Velikost ~{self._model_size_hint(self._settings.whisper_model)}. "
            "Stahuje se z Hugging Face do uživatelské složky (jednorázově).\n\n"
            "Stáhnout teď?"
        )
        answer = QMessageBox.question(self, "Stáhnout model", msg)
        if answer == QMessageBox.StandardButton.Yes:
            self._start_model_download()

    def _start_model_download(self) -> None:
        if self._model_worker.is_running():
            return
        self._progress.reset()
        self._progress.append_message(f"Stahuji model {self._settings.whisper_model}…")
        self._progress.set_busy(True)
        self._run_btn.setEnabled(False)
        self._model_worker.start(self._settings.whisper_model)

    def _on_model_progress(self, status: str, fraction: float) -> None:
        if fraction < 0:
            self._progress.append_message(status)
        else:
            self._progress.update(status, fraction)

    def _on_model_ready(self) -> None:
        self._progress.set_busy(False)
        self._progress.append_message("✅ Model připraven.")
        self._refresh_run_button()

    def _on_model_error(self, message: str) -> None:
        self._progress.set_busy(False)
        self._refresh_run_button()
        QMessageBox.critical(self, "Chyba při stahování modelu", message)

    # ------ Utility ------

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "O aplikaci",
            f"<b>Hlas do textu</b><br>Verze {__version__}<br><br>"
            "Vyrobeno pro Safe4Future z. ú.<br>"
            "Whisper (lokálně) + Google Gemini / Ollama.<br><br>"
            "Licence: MIT",
        )

    def _open_file(self, path: Path) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                import subprocess

                subprocess.Popen(["open", str(path)])
            else:
                import subprocess

                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Nepodařilo se otevřít {}: {}", path, exc)

    @staticmethod
    def _model_size_hint(name: str) -> str:
        return {
            "small": "250 MB",
            "medium": "770 MB",
            "large-v3": "1.5 GB",
        }.get(name, "neznámá velikost")

    # ====================================================================
    # Auto-updater handlery
    # ====================================================================

    def _on_update_check_finished(self, info) -> None:
        """Výsledek z UpdateCheckWorker. info = UpdateInfo | None."""
        if info is None:
            logger.info("Update check: žádný update")
            return
        if not info.is_newer_than_current:
            logger.info("Update check: lokální verze je aktuální ({})", info.version)
            return
        logger.info("Update check: dostupná novější verze {}", info.version)
        self._available_update = info
        self._update_banner.show_available(info.version)

    def _on_update_requested(self) -> None:
        """User klikl 'Aktualizovat' v banneru → začneme stahovat."""
        if self._available_update is None:
            return
        if self._update_download.is_running():
            return
        self._update_banner.show_downloading()
        self._update_download.start(self._available_update)

    def _on_update_progress(self, downloaded: int, total: int) -> None:
        self._update_banner.update_progress(downloaded, total)

    def _on_update_downloaded(self, path) -> None:
        from pathlib import Path

        self._update_installer_path = Path(str(path))
        logger.info("Update stažen, čekám na restart: {}", self._update_installer_path)
        self._update_banner.show_ready()
        self._notify(
            "Aktualizace připravena",
            f"Verze {self._available_update.version} je stažená — klikni 'Restartovat'.",
        )

    def _on_update_download_error(self, message: str) -> None:
        logger.error("Update download chyba: {}", message)
        self._update_banner.show_error(message)

    def _on_update_restart(self) -> None:
        """User klikl 'Restartovat a aktualizovat' → spustíme installer + ukončíme app."""
        if self._update_installer_path is None or not self._update_installer_path.is_file():
            self._update_banner.show_error("Soubor instalátoru zmizel — zkus znovu.")
            return

        if self._pipeline_worker.is_running() or self._regenerate_worker.is_running():
            answer = QMessageBox.question(
                self,
                "Zpracování běží",
                "Probíhá zpracování. Pokud aplikaci teď ukončíš, postup se ztratí. Pokračovat?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self._pipeline_worker.stop_and_wait()

        from app.updater import apply_update

        try:
            apply_update(self._update_installer_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("apply_update selhalo: {}", exc)
            self._update_banner.show_error(str(exc))
