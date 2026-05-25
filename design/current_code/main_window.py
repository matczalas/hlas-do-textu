"""Hlavní okno aplikace — sestavuje widgety, řídí flow."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Hlas do textu — Safe4Future ({__version__})")
        self.resize(960, 720)

        self._settings: AppSettings = load_settings()
        self._pipeline_worker = PipelineWorker(self)
        self._model_worker = ModelDownloadWorker(self)
        self._regenerate_worker = RegenerateWorker(self)
        self._tray = self._init_tray()

        self._build_ui()
        self._wire_signals()

        # Po načtení UI: first-run + model check + status refresh
        QTimer.singleShot(50, self._post_show_init)

    def _init_tray(self) -> QSystemTrayIcon | None:
        """Inicializuje system tray icon pro notifikace (Win/macOS/Linux)."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        icon_path = Path(__file__).resolve().parent.parent / "resources" / "icon.png"
        icon = QIcon(str(icon_path)) if icon_path.is_file() else QIcon()
        tray = QSystemTrayIcon(icon, self)
        tray.setToolTip("Hlas do textu")
        tray.show()
        return tray

    def _notify(self, title: str, message: str, is_error: bool = False) -> None:
        if self._tray is None:
            return
        icon_type = QSystemTrayIcon.MessageIcon.Critical if is_error else QSystemTrayIcon.MessageIcon.Information
        self._tray.showMessage(title, message, icon_type, 8000)

    # ------ UI ------

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Drop zone (tlačítka + drag-drop)
        self._drop_zone = FileDropZone()
        self._drop_zone.set_last_dir(self._settings.last_used_sources_dir)
        root.addWidget(self._drop_zone)

        # Tabulka souborů + empty state (přepínáme přes QStackedWidget)
        self._table = SourceTable()
        self._empty_state = EmptyStateWidget()
        self._source_stack = QStackedWidget()
        self._source_stack.addWidget(self._empty_state)  # index 0
        self._source_stack.addWidget(self._table)        # index 1
        self._source_stack.setCurrentIndex(0)
        root.addWidget(self._source_stack, 1)

        # Popis / instrukce
        self._prompt_editor = PromptEditor()
        root.addWidget(self._prompt_editor)

        # Output cesta + nastavení tlačítko
        out_row = QHBoxLayout()
        out_row.setSpacing(8)
        out_label = QLabel("Výstup:")
        self._output_value = QLabel(self._settings.output_dir)
        self._output_value.setStyleSheet("color: #444;")
        change_out_btn = QPushButton("Změnit…")
        change_out_btn.clicked.connect(self._change_output_dir)
        settings_btn = QPushButton("⚙ Nastavení")
        settings_btn.clicked.connect(self._open_settings)
        out_row.addWidget(out_label)
        out_row.addWidget(self._output_value, 1)
        out_row.addWidget(change_out_btn)
        out_row.addWidget(settings_btn)
        root.addLayout(out_row)

        # Status bar (Gemini / Ollama)
        self._status_bar = StatusBar()
        root.addWidget(self._status_bar)

        # Progress panel
        self._progress = ProgressPanel()
        root.addWidget(self._progress, 1)

        # Akční tlačítka — dvě volby režimu
        action_row = QHBoxLayout()
        action_row.setSpacing(12)

        self._run_transcribe_btn = QPushButton("📝  Jen přepis")
        self._run_transcribe_btn.setMinimumHeight(52)
        self._run_transcribe_btn.setMinimumWidth(200)
        self._run_transcribe_btn.setToolTip(
            "Rychlejší. Vytvoří Word dokument s plným přepisem mluveného slova "
            "(bez AI bodů). Funguje i bez internetu."
        )
        self._run_transcribe_btn.setStyleSheet(
            "QPushButton { background-color: #3a8a3a; color: white; border: none; "
            "border-radius: 6px; padding: 10px 18px; font-size: 14px; font-weight: 600; }"
            "QPushButton:hover { background-color: #2d6e2d; }"
            "QPushButton:disabled { color: rgba(255,255,255,120); background-color: #5a7a5a; }"
        )

        self._run_full_btn = QPushButton("🤖  Přepis + body z AI")
        self._run_full_btn.setMinimumHeight(52)
        self._run_full_btn.setMinimumWidth(200)
        self._run_full_btn.setToolTip(
            "Vytvoří plný studijní materiál: hlavní body, klíčové pojmy, příklady "
            "a doporučení k dalšímu studiu. Potřebuje Gemini klíč nebo Ollama."
        )
        self._run_full_btn.setStyleSheet(
            "QPushButton { background-color: #205ca8; color: white; border: none; "
            "border-radius: 6px; padding: 10px 18px; font-size: 14px; font-weight: 600; }"
            "QPushButton:hover { background-color: #1a4d8f; }"
            "QPushButton:disabled { color: rgba(255,255,255,120); background-color: #5a7595; }"
        )

        action_row.addStretch(1)
        action_row.addWidget(self._run_transcribe_btn)
        action_row.addWidget(self._run_full_btn)
        root.addLayout(action_row)

        # Kompatibilita: některý existující kód odkazuje na _run_btn
        self._run_btn = self._run_full_btn

        # Menu bar (mac uvítá Cmd+,)
        self._build_menu()

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&Soubor")

        regen_action = QAction("Vytvořit body z existujícího přepisu…", self)
        regen_action.setStatusTip("Použij dříve uložený .txt přepis a vygeneruj nový .docx s body")
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
        self._run_transcribe_btn.clicked.connect(lambda: self._run_pipeline(JobMode.TRANSCRIBE_ONLY))
        self._progress.cancel_button.clicked.connect(self._pipeline_worker.cancel)

        self._pipeline_worker.progress.connect(self._progress.update)
        self._pipeline_worker.transcript_text.connect(self._progress.append_transcript_line)
        self._pipeline_worker.finished_ok.connect(self._on_pipeline_ok)
        self._pipeline_worker.finished_error.connect(self._on_pipeline_error)

        self._model_worker.progress.connect(self._on_model_progress)
        self._model_worker.finished_ok.connect(self._on_model_ready)
        self._model_worker.finished_error.connect(self._on_model_error)

        self._regenerate_worker.progress.connect(self._progress.update)
        self._regenerate_worker.finished_ok.connect(self._on_pipeline_ok)
        self._regenerate_worker.finished_error.connect(lambda msg: self._on_pipeline_error(msg, False))

        self._refresh_run_button()

    # ------ Lifecycle ------

    def _post_show_init(self) -> None:
        if not self._settings.first_run_done:
            dlg = FirstRunDialog(self._settings, self)
            dlg.exec()
            save_settings(self._settings)

        # Check model availability — nabídnout download dialog
        self._maybe_offer_model_download()

        # Health-check Gemini / Ollama
        self._status_bar.refresh(get_gemini_api_key())

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
            self._pipeline_worker.stop_and_wait()

        # Persist last used dir
        self._settings.last_used_sources_dir = self._drop_zone.last_dir
        save_settings(self._settings)
        event.accept()

    # ------ Handlers ------

    def _on_sources_added(self, sources: list[SourceFile]) -> None:
        if not sources:
            return
        self._table.add_sources(sources)
        # Auto-update output value (uživatel mohl změnit přes settings)
        self._output_value.setText(self._settings.output_dir)

    def _refresh_run_button(self) -> None:
        sources = self._table.sources()
        has_audio = any(s.kind == SourceKind.AUDIO_VIDEO for s in sources)
        has_any = bool(sources)
        running = self._pipeline_worker.is_running() or self._regenerate_worker.is_running()

        # 'Jen přepis' vyžaduje audio
        self._run_transcribe_btn.setEnabled(has_audio and not running)
        # 'Přepis + AI' funguje i s pouhými slidy (AI shrne slidy)
        self._run_full_btn.setEnabled(has_any and not running)

        # Empty state / tabulka switch
        self._source_stack.setCurrentIndex(1 if has_any else 0)

    def _change_output_dir(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        chosen = QFileDialog.getExistingDirectory(self, "Vyber výstupní složku", self._settings.output_dir)
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
            # Model download offer jen pokud se model změnil (jinak otravné)
            if self._settings.whisper_model != previous_model:
                self._maybe_offer_model_download()

    # ------ Pipeline ------

    def _run_pipeline(self, mode: JobMode = JobMode.FULL) -> None:
        if self._pipeline_worker.is_running():
            return

        sources = self._table.sources()
        if not sources:
            QMessageBox.information(self, "Žádné soubory", "Přidej alespoň jednu nahrávku nebo prezentaci.")
            return

        # 'Jen přepis' vyžaduje aspoň 1 audio (slidy bez AI nedávají smysl)
        if mode == JobMode.TRANSCRIBE_ONLY:
            if not any(s.kind == SourceKind.AUDIO_VIDEO for s in sources):
                QMessageBox.information(
                    self,
                    "Chybí nahrávka",
                    "Pro 'Jen přepis' potřebuješ přidat alespoň jednu nahrávku (mp3/mp4/wav/m4a).",
                )
                return

        # AI validace jen pro FULL režim — TRANSCRIBE_ONLY nepotřebuje internet/klíč
        api_key = get_gemini_api_key() if mode == JobMode.FULL else None
        if mode == JobMode.FULL:
            if not self._settings.prefer_offline and not api_key:
                answer = QMessageBox.question(
                    self,
                    "Chybí Gemini klíč",
                    "Nemáš nastavený Gemini API klíč. Zkusit pokračovat s lokální Ollama? "
                    "(Pokud Ollama neběží, zpracování selže.)\n\n"
                    "Tip: pokud chceš jen přepis bez AI, zavři tento dialog a klikni "
                    "tlačítko 'Jen přepis'.",
                )
                if answer != QMessageBox.StandardButton.Yes:
                    self._open_settings()
                    return

            if not self._settings.prefer_offline and api_key and not self._settings.ai_consent_gemini:
                answer = QMessageBox.question(
                    self,
                    "Souhlas s odesláním do Gemini",
                    "Bez souhlasu nelze poslat data do Google Gemini. Otevřít Nastavení?",
                )
                if answer == QMessageBox.StandardButton.Yes:
                    self._open_settings()
                return

        # Validace modelu (potřeba pro oba režimy)
        if not model_is_cached(self._settings.whisper_model):
            answer = QMessageBox.question(
                self,
                "Whisper model není stažený",
                f"Model '{self._settings.whisper_model}' není zatím stažený. Stáhnout ho teď?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self._start_model_download()
            return

        # Odhad času před startem — kamarádka ví do čeho jde
        if not self._confirm_time_estimate(sources, mode):
            return

        # Spuštění
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
            QMessageBox.critical(self, "Chyba", f"Nepodařilo se spustit zpracování: {exc}")

    def _on_pipeline_ok(self, result) -> None:
        self._progress.set_busy(False)
        self._refresh_run_button()
        self._progress.append_message(f"✅ Hotovo. Výstup: {result.output_path}")

        summary = self._format_result_summary(result)
        self._notify("Hlas do textu — hotovo ✅", f"Soubor: {result.output_path.name}\n{summary}")

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
            QMessageBox.information(self, "Zpracování běží", "Nejdřív počkej, až doběhne aktuální úloha.")
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

        # Nabídnout zachování / úpravu popisu — kamarádka chce nový pokus s lepším promptem
        new_prompt, ok = QInputDialog.getMultiLineText(
            self,
            "Upravit popis pro AI",
            "Můžeš upravit popis / instrukce. Aplikace pak vygeneruje nové body ze stávajícího přepisu (bez opakovaného přepisování audia).",
            self._prompt_editor.text(),
        )
        if not ok:
            return

        # Validace AI providers (stejně jako v _run_pipeline)
        api_key = get_gemini_api_key()
        if not self._settings.prefer_offline and api_key and not self._settings.ai_consent_gemini:
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
            QMessageBox.critical(self, "Chyba", f"Nepodařilo se spustit regeneraci: {exc}")

    def _confirm_time_estimate(self, sources: list[SourceFile], mode: JobMode = JobMode.FULL) -> bool:
        """Pre-start dialog s odhadem doby zpracování. Vrátí True pro pokračování."""
        durations: list[float] = []
        for src in sources:
            if src.kind != SourceKind.AUDIO_VIDEO:
                continue
            d = probe_duration_seconds(src.path) or 0.0
            durations.append(d)
        if not durations:
            return True  # bez audio = jen slidy, žádný dlouhý běh

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
            "Můžeš mezitím dělat něco jiného — aplikace ti pošle notifikaci, až bude hotovo.<br><br>"
            "Spustit?"
        )
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
        return msg.exec() == QMessageBox.StandardButton.Yes

    # ------ Model download ------

    def _maybe_offer_model_download(self) -> None:
        if model_is_cached(self._settings.whisper_model):
            return
        msg = (
            f"Whisper model '{self._settings.whisper_model}' není zatím stažený.\n"
            f"Velikost ~{self._model_size_hint(self._settings.whisper_model)}. "
            "Stahuje se z Hugging Face do uživatelské složky (jednorázově).\n\nStáhnout teď?"
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
