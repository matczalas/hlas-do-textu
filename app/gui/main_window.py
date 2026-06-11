"""Hlavní okno aplikace — sestavuje widgety, řídí flow.

Redesign: tři sekce v plynoucím layoutu (Zdroje · Kontext · Spuštění),
globální QSS z app/gui/styles/app.qss načtený přes theme.apply_theme()
(role-aware: student modrá / učitel teal). Business logika nezměněna —
všechny signály/sloty/atributy zůstávají.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
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
from app.config import AUDIO_VIDEO_EXTENSIONS, PRESENTATION_EXTENSIONS
from app.core.audio_extract import probe_duration_seconds
from app.core.model_downloader import model_is_cached
from app.core.models import JobConfig, JobMode, SourceFile, SourceKind, TranscribeBackend
from app.core.pipeline import estimate_total_processing_seconds, format_duration_human
from app.gui.styles import tokens
from app.gui.widgets.empty_state import EmptyStateWidget
from app.gui.widgets.file_drop_zone import FileDropZone
from app.gui.widgets.icons import icon, icon_size, pixmap
from app.gui.widgets.ollama_status import StatusBar
from app.gui.widgets.progress_panel import ProgressPanel
from app.gui.widgets.prompt_editor import PromptEditor
from app.gui.widgets.settings_dialog import SettingsDialog
from app.gui.widgets.source_table import SourceTable
from app.gui.widgets.wordmark import Wordmark
from app.gui.workers.model_download_worker import ModelDownloadWorker
from app.gui.workers.pipeline_worker import PipelineWorker
from app.gui.workers.regenerate_worker import RegenerateWorker
from app.settings import (
    AppSettings,
    get_gemini_api_key,
    load_settings,
    save_settings,
)

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
        # Min size sníženo v1.5.0, aby aplikace fungovala na 13" MacBooku
        # při split-screen (zhruba 720×600). Vnitřní QScrollArea zaručí,
        # že content nikdy nevypadne za viewport.
        self.setMinimumSize(720, 560)
        # Drop zóna je explicitní v UI, ale uživatelé instinktivně přetahují
        # soubor kamkoliv. Akceptujeme drop i mimo zóny — pak je předáme
        # standardní cestou přes _on_sources_added.
        self.setAcceptDrops(True)

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
        self._last_result = None  # PipelineResult | None — pro chat o dokumentu
        self._youtube_worker = None  # YouTubeFetchWorker | None — líně v _open_youtube_dialog
        # Self-kalibrace odhadu času
        self._pipeline_start_monotonic = None
        self._pipeline_audio_seconds = 0.0
        self._pipeline_backend_used = None
        # Fronta dávkového zpracování (víc nahrávek "každou zvlášť")
        self._job_queue: list = []
        self._queue_total = 0
        self._queue_index = 0
        self._queue_results: list = []
        self._queue_api_key = None
        # Paralelní list job_id v JobQueueControlleru — pro každý JobConfig
        # existuje jedno id, které controller drží jako JobState.
        self._job_queue_ids: list[str] = []
        # ID právě běžícího jobu (None pokud žádný neběží)
        self._current_queue_job_id: str | None = None

        # Queue controller — passive tracker pro QueuePanel UI.
        # Nehne pipeline business logikou, jen sleduje stavy přes add_job/
        # start_job/update_progress/finish_job/error_job.
        from app.gui.job_queue import JobQueueController

        self._job_controller = JobQueueController(self)

        self._tray = self._init_tray()

        # QSS je globální (theme.apply_theme() v entrypointu) — žádný per-window
        # setStyleSheet, protože by přebil sentinely a accent by zůstal nevyplněný.
        self._build_ui()
        self._wire_signals()

        QTimer.singleShot(50, self._post_show_init)

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

        # ---- Stack: Projects home (page 0) + Editor (page 1) ---------
        # Vstupní bod aplikace je Projects home — uživatel vidí svoje
        # dříve vyrobené projekty a má důvod se vrátit. "Nový projekt"
        # nebo klik na existující projekt přepne na editor.
        from app.gui.widgets.projects_home import ProjectsHome

        self._page_stack = QStackedWidget()

        self._projects_home = ProjectsHome()
        self._projects_home.new_project_requested.connect(self._enter_editor)
        self._projects_home.project_opened.connect(self._open_file)
        self._page_stack.addWidget(self._projects_home)  # index 0

        # Editor page je QScrollArea obalující skutečný content — když má
        # okno menší výšku než content (typicky učitel režim se 3 kartami
        # + queue panel), uživatel může scrollovat. Bez tohoto se content
        # ořeže a tlačítka pod fold nejsou dostupná.
        from PySide6.QtWidgets import QScrollArea

        self._editor_page = QWidget()
        editor_outer = QVBoxLayout(self._editor_page)
        editor_outer.setContentsMargins(0, 0, 0, 0)
        editor_outer.setSpacing(0)

        self._editor_scroll = QScrollArea()
        self._editor_scroll.setWidgetResizable(True)
        self._editor_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._editor_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._editor_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )

        editor_content = QWidget()
        editor_root = QVBoxLayout(editor_content)
        editor_root.setContentsMargins(0, 0, 4, 0)  # +4 right pro scrollbar
        editor_root.setSpacing(14)

        self._editor_scroll.setWidget(editor_content)
        editor_outer.addWidget(self._editor_scroll, 1)

        self._page_stack.addWidget(self._editor_page)  # index 1

        root.addWidget(self._page_stack, 1)

        # Default na home — refresh načte recent_outputs.
        self._page_stack.setCurrentIndex(0)
        self._projects_home.refresh(self._settings.recent_outputs)

        # Použít alias 'root' pro zbytek build_ui (přesměrováno na editor_root)
        root = editor_root

        # ---- Učitel: section label "1 · Nahrávka hodiny" --------------
        # V učitel módu se nad drop zone přidá očíslovaný section label
        # (sekce 1). Sekce 2 a 3 jsou pod source_stack jako TeacherActions.
        self._section_1_label = QLabel("1 · Nahrávka hodiny")
        self._section_1_label.setObjectName("SectionLabel")
        self._section_1_label.setVisible(self._settings.app_role == "teacher")
        root.addWidget(self._section_1_label)

        # ---- Drop zone (vždy nahoře v editoru) ------------------------
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

        # ---- Učitel: 3 akční karty + segmented "Režim testu" ---------
        # Vyrobí se vždy, ale pod source_stack a viditelnost se řídí podle
        # role. Klik na kartu vyemituje prompt_key, MainWindow z něj
        # předvyplní prompt_editor a spustí pipeline.
        from app.gui.widgets.teacher_actions import TeacherActionsWidget

        self._teacher_actions = TeacherActionsWidget()
        self._teacher_actions.action_requested.connect(self._on_teacher_action)
        self._teacher_actions.setVisible(self._settings.app_role == "teacher")
        root.addWidget(self._teacher_actions)

        # ---- Kontext pro AI -------------------------------------------
        # V učitel módu skrýt — kartám stačí vestavěné šablony promptů.
        # Předáme role, ať dropdown "Co vyrobit" obsahuje jen relevantní
        # šablony (student nevidí teacher_* prompts).
        self._prompt_editor = PromptEditor(role=self._settings.app_role)
        self._prompt_editor.setVisible(self._settings.app_role != "teacher")
        root.addWidget(self._prompt_editor)

        # ---- Output + Progress ----------------------------------------
        root.addLayout(self._build_output_row())
        self._progress = ProgressPanel()
        root.addWidget(self._progress, 1)

        # ---- Queue panel (sekvenční fronta dávkových jobů) -------------
        # Zobrazí se sám, když controller.jobs() není prázdný. Pro single
        # job je skrytý (ProgressPanel vyše stačí).
        from app.gui.widgets.queue_panel import QueuePanel

        self._queue_panel = QueuePanel(self._job_controller)
        self._queue_panel.cancel_requested.connect(self._on_queue_cancel)
        self._queue_panel.open_requested.connect(self._open_file)
        root.addWidget(self._queue_panel)

        # ---- Fact card "Než to doběhne" — viditelná během běhu pipeline -
        from app.gui.widgets.fact_card import FactCard

        self._fact_card = FactCard(role=self._settings.app_role)
        self._fact_card.hide()
        root.addWidget(self._fact_card)

        # ---- CTA tlačítka ---------------------------------------------
        # V učitel módu skrýt — akce se spouští z karet.
        # Wrapped do QFrame#ActionBar (border-top + padding) dle prototypu.
        self._action_row_widget = QFrame()
        self._action_row_widget.setObjectName("ActionBar")
        action_outer = QVBoxLayout(self._action_row_widget)
        action_outer.setContentsMargins(0, 10, 0, 0)
        action_outer.setSpacing(0)
        action_outer.addLayout(self._build_action_row())
        self._action_row_widget.setVisible(self._settings.app_role != "teacher")
        root.addWidget(self._action_row_widget)

        # Backward compatible alias
        self._run_btn = self._run_full_btn

        self._build_menu()

    # ---- Header bar -------------------------------------------------------

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        # Back tlačítko "← Moje projekty" — viditelné jen v editoru.
        self._back_btn = QPushButton("←  Moje projekty")
        self._back_btn.setObjectName("Back")
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.clicked.connect(self._back_to_home)
        self._back_btn.hide()  # výchozí page je home, back nepotřebujeme
        row.addWidget(self._back_btn)

        # Wordmark — glyph + (volitelně) textový pár.
        # Compact mode (jen glyph) v editoru, full s subtitle na Projects home.
        # Subtitle se mění dle role v _refresh_role_visuals().
        self._wordmark = Wordmark(
            subtitle=self._wordmark_subtitle_for_role(),
            compact=False,  # výchozí page je home → ukázat full
        )
        row.addWidget(self._wordmark)

        # Role badge "Učitelský režim" — viditelný jen v teacher módu.
        # Stylováno přes objectName="RoleBadge" v app.qss (role-aware).
        self._role_badge = QLabel("Učitelský režim")
        self._role_badge.setObjectName("RoleBadge")
        self._role_badge.setVisible(self._settings.app_role == "teacher")
        row.addWidget(self._role_badge)

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
            f"QPushButton#Ghost:hover {{ background: palette(midlight); border-color: {tokens.accent()}; }}"
        )
        row.addWidget(settings_btn)

        return row

    def _refresh_role_badge(self) -> None:
        """Synchronizuje role-závislé UI prvky se settings.app_role.

        Při přepnutí role v Settings projeví okamžitě: badge, section label
        nad drop zone, učitelské karty, prompt editor a action row.
        """
        is_teacher = self._settings.app_role == "teacher"
        if hasattr(self, "_role_badge"):
            self._role_badge.setVisible(is_teacher)
        if hasattr(self, "_section_1_label"):
            self._section_1_label.setVisible(is_teacher)
        if hasattr(self, "_teacher_actions"):
            self._teacher_actions.setVisible(is_teacher)
        if hasattr(self, "_prompt_editor"):
            self._prompt_editor.setVisible(not is_teacher)
        if hasattr(self, "_action_row_widget"):
            self._action_row_widget.setVisible(not is_teacher)

    def _wordmark_subtitle_for_role(self) -> str:
        """Vrátí subtitle pro Wordmark dle aktuální role."""
        if self._settings.app_role == "teacher":
            return "Pedagogický nástroj"
        if self._settings.app_role == "sales":
            return "Poznámky ze schůzek s klienty"
        return "Studijní poznámky z přednášek"

    def _show_fact_card_during_pipeline(self, running: bool) -> None:
        """Zobrazí/skryje FactCard při startu / konci pipeline.

        Volá se z _set_pipeline_running() — viditelná když pipeline běží
        a uživatel čeká. Timer rotace se pauzuje sám přes showEvent/hideEvent.
        """
        if hasattr(self, "_fact_card"):
            self._fact_card.setVisible(running)

    def _refresh_role_visuals(self) -> None:
        """Po přepnutí role v Settings projeví accent change i u inline-stylovaných
        widgetů (FileDropZone, EmptyState, UpdateBanner, PromptEditor, ProgressPanel,
        atd.). Iteruje child widgety, hledá refresh_accent() metodu a volá ji.

        Toto je tady, protože některé widgety mají inline setStyleSheet s natvrdo
        zapsaným accentem cache-nutým v __init__. Globální QSS po theme.apply_theme()
        už je aktuální, ale inline styly potřebují manuální refresh.
        """
        self._refresh_role_badge()
        # Subtitle Wordmarku se mění dle role
        if hasattr(self, "_wordmark"):
            self._wordmark.set_subtitle(self._wordmark_subtitle_for_role())
        # FactCard se přepne na role-specific faktové pole
        if hasattr(self, "_fact_card"):
            self._fact_card.set_role(self._settings.app_role)
        # Prompt editor přefiltruje dropdown podle role
        if hasattr(self, "_prompt_editor"):
            self._prompt_editor.set_role(self._settings.app_role)
        for widget in self.findChildren(QWidget):
            refresh_fn = getattr(widget, "refresh_accent", None)
            if callable(refresh_fn):
                try:
                    refresh_fn()
                except Exception as exc:  # noqa: BLE001 — refresh nesmí položit appku
                    logger.warning("refresh_accent failed for {}: {}", type(widget).__name__, exc)

    def _on_teacher_action(self, prompt_key: str) -> None:
        """Spustí pipeline s předvyplněnou šablonou promptu z dané karty."""
        from app.core.ai.prompts import template_prompt

        prompt_text = template_prompt(prompt_key)
        if prompt_text:
            self._prompt_editor.set_text(prompt_text)
        # Plný režim — přepis + AI body podle vybrané šablony
        self._run_pipeline(JobMode.FULL)

    # ------ Navigace mezi home a editorem ------

    def _enter_editor(self) -> None:
        """Přepne na editor (Projects home → editor). Vyresetuje zdroje."""
        # Čistý projekt — uživatel právě klikl 'Nový projekt'
        self._table.clear_all()
        if self._page_stack.currentIndex() != 1:
            self._page_stack.setCurrentIndex(1)
        self._back_btn.show()
        # Wordmark v editoru compact (jen glyph)
        if hasattr(self, "_wordmark"):
            self._wordmark.set_compact(True)

    def _back_to_home(self) -> None:
        """Návrat na Projects home — uloží stav a aktualizuje seznam."""
        # Pokud běží pipeline, ptáme se uživatele (jinak by se job ztratil
        # ze zobrazení, ale stále by běžel na pozadí — matoucí UX).
        if self._pipeline_worker.is_running():
            reply = QMessageBox.question(
                self,
                "Zpracování stále běží",
                "Pipeline ještě běží. Vrátit se na seznam projektů?\n"
                "Zpracování pokračuje dál, hotový dokument se objeví "
                "v seznamu projektů.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._page_stack.setCurrentIndex(0)
        self._back_btn.hide()
        # Wordmark zpět do full módu s subtitle
        if hasattr(self, "_wordmark"):
            self._wordmark.set_compact(False)
        # Refresh recent_outputs (mohlo přibýt po dokončení pipeline)
        self._projects_home.refresh(self._settings.recent_outputs)

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
            f"color: {tokens.accent()}; padding: 4px 8px; font-weight: 600; }}"
            "QPushButton#Link:hover { text-decoration: underline; }"
        )
        change_out_btn.clicked.connect(self._change_output_dir)
        row.addWidget(change_out_btn)

        return row

    # ---- Action row -------------------------------------------------------

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        row.setContentsMargins(0, 0, 0, 0)

        # Hint vlevo — vysvětluje rozdíl mezi dvěma tlačítky (dle prototypu).
        hint_wrap = QHBoxLayout()
        hint_wrap.setSpacing(8)
        hint_icon = QLabel()
        hint_icon.setPixmap(pixmap("info", size=14, color="#9aa7b6"))
        hint_icon.setFixedSize(16, 16)
        hint_wrap.addWidget(hint_icon)

        hint_text = QLabel(
            "„Jen přepis\" je rychlý a offline. „Body z AI\" vytvoří strukturované poznámky."
        )
        hint_text.setObjectName("ActionBarHint")
        hint_text.setWordWrap(True)
        hint_wrap.addWidget(hint_text, 1)
        row.addLayout(hint_wrap, 1)

        self._run_transcribe_btn = QPushButton("Přepis")
        self._run_transcribe_btn.setObjectName("Secondary")
        self._run_transcribe_btn.setIcon(icon("document", size=16, color=tokens.accent()))
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

        row.addWidget(self._run_transcribe_btn)
        row.addWidget(self._run_full_btn)
        return row

    # ---- Menu -------------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&Soubor")

        open_action = QAction("Otevřít soubor…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.setStatusTip("Vybrat audio / video / prezentaci na disku")
        open_action.triggered.connect(self._open_file_dialog)
        file_menu.addAction(open_action)

        url_action = QAction("Přepis z YouTube / URL…", self)
        url_action.setShortcut(QKeySequence("Ctrl+U"))
        url_action.setStatusTip("Stáhnout audio z YouTube, Vimeo, podcastu…")
        url_action.triggered.connect(self._open_youtube_dialog)
        file_menu.addAction(url_action)

        file_menu.addSeparator()

        # Recent výstupy — submenu, naplní se v _refresh_recent_menu
        self._recent_menu = file_menu.addMenu("Naposledy vyrobené")
        self._refresh_recent_menu()

        file_menu.addSeparator()

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

        # Run / cancel zkratky — bez menu, jen klávesy
        run_full_sc = QAction(self)
        run_full_sc.setShortcut(QKeySequence("Ctrl+R"))
        run_full_sc.triggered.connect(lambda: self._run_pipeline(JobMode.FULL))
        self.addAction(run_full_sc)

        run_transcribe_sc = QAction(self)
        run_transcribe_sc.setShortcut(QKeySequence("Ctrl+Shift+R"))
        run_transcribe_sc.triggered.connect(
            lambda: self._run_pipeline(JobMode.TRANSCRIBE_ONLY)
        )
        self.addAction(run_transcribe_sc)

        help_menu = menubar.addMenu("&Nápověda")
        about = QAction("O aplikaci", self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

        help_menu.addSeparator()
        uninstall = QAction("Odinstalovat / smazat data…", self)
        uninstall.setStatusTip(
            "Smaže stažené modely, nastavení a uložené klíče z tohoto počítače"
        )
        uninstall.triggered.connect(self._on_uninstall_requested)
        help_menu.addAction(uninstall)

    # ------ Signals ------

    def _wire_signals(self) -> None:
        self._drop_zone.sources_added.connect(self._on_sources_added)
        self._table.files_changed.connect(self._refresh_run_button)
        self._run_full_btn.clicked.connect(lambda: self._run_pipeline(JobMode.FULL))
        self._run_transcribe_btn.clicked.connect(
            lambda: self._run_pipeline(JobMode.TRANSCRIBE_ONLY)
        )
        self._progress.cancel_button.clicked.connect(self._on_cancel_clicked)

        self._pipeline_worker.progress.connect(self._on_pipeline_progress)
        self._pipeline_worker.transcript_text.connect(self._progress.append_transcript_line)
        self._pipeline_worker.cloud_fallback.connect(self._on_cloud_fallback)
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
        # Role picker + first-run jsou teď v entrypointu (app/__main__.py)
        # PŘED konstrukcí MainWindow. Tady už jen pokračujeme s další logikou.
        self._maybe_offer_model_download()
        self._status_bar.refresh(get_gemini_api_key())

        # Úklid osiřelých checkpointů (>7 dní) — z dávno opuštěných přepisů
        try:
            from app.core import checkpoint as _ckpt

            _ckpt.cleanup_old()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cleanup checkpointů selhal: {}", exc)

        # Tichá kontrola aktualizace po 5 s — nezdržuje startup ani s pomalou sítí
        QTimer.singleShot(5000, self._silent_update_check)

    def _silent_update_check(self) -> None:
        """Spustí tichou kontrolu update přes GitHub API. Neukáže nic pokud není update."""
        if self._update_check.is_running() or self._update_download.is_running():
            return
        logger.info("Spouštím tichou kontrolu aktualizace…")
        self._update_check.start()

    def closeEvent(self, event) -> None:  # noqa: N802
        # Varujeme u libovolné déletrvající práce, ne jen pipeline — model
        # download i YouTube fetch stojí za potvrzení (ztratí se postup).
        busy = any(
            getattr(self, attr, None) is not None
            and getattr(self, attr).is_running()
            for attr in ("_pipeline_worker", "_model_worker", "_regenerate_worker", "_youtube_worker")
        )
        if busy:
            answer = QMessageBox.question(
                self,
                "Zpracování běží",
                "Něco se ještě zpracovává (přepis, stahování modelu nebo videa). "
                "Opravdu chcete zavřít aplikaci? Postup se ztratí.",
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
            "_youtube_worker",  # líně vytvořený v _open_youtube_dialog — taky musí stop
            "_chat_worker",     # může existovat z chat dialogu
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

    # ------ Otevřít soubor (klávesovka Cmd+O / Ctrl+O) ------

    def _open_file_dialog(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        supported = AUDIO_VIDEO_EXTENSIONS + PRESENTATION_EXTENSIONS
        filter_str = "Podporované soubory (" + " ".join(f"*{e}" for e in supported) + ")"
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Vyber audio nebo prezentaci",
            self._settings.last_used_sources_dir,
            filter_str,
        )
        if not files:
            return

        new_sources: list[SourceFile] = []
        for f in files:
            path = Path(f)
            suffix = path.suffix.lower()
            if suffix in AUDIO_VIDEO_EXTENSIONS:
                kind = SourceKind.AUDIO_VIDEO
            elif suffix in PRESENTATION_EXTENSIONS:
                kind = SourceKind.PRESENTATION
            else:
                continue
            new_sources.append(SourceFile(path=path, kind=kind, label=path.stem))

        if new_sources:
            self._settings.last_used_sources_dir = str(new_sources[0].path.parent)
            save_settings(self._settings)
            self._on_sources_added(new_sources)

    # ------ Recent výstupy (File menu → Naposledy vyrobené) ------

    def _refresh_recent_menu(self) -> None:
        if not hasattr(self, "_recent_menu") or self._recent_menu is None:
            return
        self._recent_menu.clear()
        recents = [Path(p) for p in (self._settings.recent_outputs or [])]
        # Filtrujem ty, co fyzicky existují
        recents = [p for p in recents if p.is_file()]
        if not recents:
            placeholder = self._recent_menu.addAction("(Žádné soubory zatím)")
            placeholder.setEnabled(False)
            return
        for path in recents[:10]:
            act = QAction(path.name, self)
            act.setStatusTip(str(path))
            act.triggered.connect(lambda _checked=False, p=path: self._open_file(p))
            self._recent_menu.addAction(act)
        self._recent_menu.addSeparator()
        clear = QAction("Vyčistit seznam", self)
        clear.triggered.connect(self._clear_recent_outputs)
        self._recent_menu.addAction(clear)

    def _add_to_recents(self, path: Path) -> None:
        path_str = str(path)
        recents = [p for p in (self._settings.recent_outputs or []) if p != path_str]
        recents.insert(0, path_str)
        self._settings.recent_outputs = recents[:10]
        save_settings(self._settings)
        self._refresh_recent_menu()
        # Refresh projektů na home — nový dokument se hned objeví v seznamu.
        if hasattr(self, "_projects_home"):
            self._projects_home.refresh(self._settings.recent_outputs)

    def _clear_recent_outputs(self) -> None:
        self._settings.recent_outputs = []
        save_settings(self._settings)
        self._refresh_recent_menu()

    # ------ YouTube / URL stahování ------

    def _open_youtube_dialog(self) -> None:
        from app.gui.widgets.youtube_dialog import YouTubeUrlDialog
        from app.gui.workers.youtube_worker import YouTubeFetchWorker

        if getattr(self, "_youtube_worker", None) is not None and self._youtube_worker.is_running():
            QMessageBox.information(
                self, "Stahování běží",
                "Předchozí URL se ještě stahuje. Počkej, prosím."
            )
            return

        if not hasattr(self, "_youtube_worker") or self._youtube_worker is None:
            self._youtube_worker = YouTubeFetchWorker(self)

        dlg = YouTubeUrlDialog(self)
        # Stav: True = uživatel zavřel dialog před dokončením stahování.
        # Pak ignorujeme finished_ok callback, aby se soubor nepřidal proti jeho vůli.
        dialog_state = {"cancelled": False}

        def _on_progress(fraction: float, status: str) -> None:
            if dialog_state["cancelled"]:
                return
            try:
                dlg.set_progress(fraction, status)
            except RuntimeError:
                pass  # dialog už zničený

        def _on_ok(source) -> None:
            if dialog_state["cancelled"]:
                logger.info("YouTube fetch dokončen, ale uživatel mezitím zrušil — soubor zahazuji")
                return
            try:
                dlg.set_status(f"Hotovo: {source.label}. Zavírám dialog…")
            except RuntimeError:
                pass
            self._on_sources_added([source])
            # Zavřeme dialog přímo přes Qt accept (ne monkey-patched verzí)
            QTimer.singleShot(400, lambda: QDialog.accept(dlg) if not dialog_state["cancelled"] else None)

        def _on_error(message: str) -> None:
            if dialog_state["cancelled"]:
                return
            try:
                dlg.set_status(f"Chyba: {message}")
            except RuntimeError:
                pass
            QMessageBox.warning(self, "Stahování selhalo", message)

        # Odpojit staré handlery pro případ, že user otevírá dialog opakovaně
        try:
            self._youtube_worker.progress.disconnect()
            self._youtube_worker.finished_ok.disconnect()
            self._youtube_worker.finished_error.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._youtube_worker.progress.connect(_on_progress)
        self._youtube_worker.finished_ok.connect(_on_ok)
        self._youtube_worker.finished_error.connect(_on_error)

        # OK button v dialogu má vlastní accept signál — kontrolujeme přes
        # Qt accepted signal místo monkey-patche metody.
        def _on_ok_clicked() -> None:
            url = dlg.url()
            if not url:
                return
            dlg.lock_for_download()
            try:
                self._youtube_worker.start(url)
            except RuntimeError as exc:
                # Předchozí stahování ještě běží
                QMessageBox.warning(dlg, "Stahování běží", str(exc))

        dlg.set_download_handler(_on_ok_clicked)

        result = dlg.exec()
        # Pokud user zavřel dialog před tím, než stahování doběhlo, nastavíme flag
        if result != QDialog.DialogCode.Accepted and self._youtube_worker.is_running():
            dialog_state["cancelled"] = True
            logger.info("YouTube dialog zavřen během stahování — výsledek bude zahozen")

    # ------ Drag & drop kdekoli v okně ------

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        mime = event.mimeData()
        if not mime.hasUrls():
            event.ignore()
            return
        # Akceptujeme jen pokud aspoň jeden soubor má podporovanou příponu
        supported = AUDIO_VIDEO_EXTENSIONS + PRESENTATION_EXTENSIONS
        for url in mime.urls():
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in supported:
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        mime = event.mimeData()
        if not mime.hasUrls():
            return

        new_sources: list[SourceFile] = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            suffix = path.suffix.lower()
            if suffix in AUDIO_VIDEO_EXTENSIONS:
                kind = SourceKind.AUDIO_VIDEO
            elif suffix in PRESENTATION_EXTENSIONS:
                kind = SourceKind.PRESENTATION
            else:
                continue
            new_sources.append(SourceFile(path=path, kind=kind, label=path.stem))

        if new_sources:
            event.acceptProposedAction()
            self._on_sources_added(new_sources)

    def _refresh_run_button(self) -> None:
        sources = self._table.sources()
        has_audio = any(s.kind == SourceKind.AUDIO_VIDEO for s in sources)
        has_any = bool(sources)
        # I model download blokuje spuštění — jinak by `files_changed` událost
        # uprostřed stahování modelu tlačítka znovu povolila a uživatel by
        # spustil pipeline souběžně se stahováním téhož modelu (konflikt o cache).
        running = (
            self._pipeline_worker.is_running()
            or self._regenerate_worker.is_running()
            or self._model_worker.is_running()
        )

        self._run_transcribe_btn.setEnabled(has_audio and not running)
        self._run_full_btn.setEnabled(has_any and not running)

        self._source_stack.setCurrentIndex(1 if has_any else 0)

        # Učitelské akční karty: aktivní jen když je v zdrojích nahrávka.
        if hasattr(self, "_teacher_actions"):
            self._teacher_actions.set_has_recording(has_audio and not running)

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
            # Role mohla být změněna v Settings → projeví se v badge + refresh inline
            # widgety (drop zone, flow ikony, banner, prompt editor, progress panel).
            self._refresh_role_visuals()
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

        # Když je víc nahrávek, zeptáme se: spojit do jednoho dokumentu, nebo
        # zpracovat každou zvlášť (dávka → N dokumentů).
        audio_count = sum(1 for s in sources if s.kind == SourceKind.AUDIO_VIDEO)
        batch_mode = self._ask_batch_mode(audio_count)
        if batch_mode is None:
            return  # uživatel zrušil

        if not self._confirm_time_estimate(sources, mode):
            return

        # Sestavíme frontu jobů. "merge" = jeden job se vším. "separate" =
        # jeden job na každou nahrávku (slidy se přiloží ke každé).
        self._build_job_queue(sources, mode, batch_mode)
        self._queue_api_key = get_gemini_api_key() if mode == JobMode.FULL else None
        self._start_next_job()

    def _ask_batch_mode(self, audio_count: int) -> str | None:
        """Vrátí 'merge' / 'separate' / None (zrušeno). Při <=1 nahrávce 'merge'."""
        if audio_count <= 1:
            return "merge"
        msg = QMessageBox(self)
        msg.setWindowTitle("Více nahrávek")
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setText(
            f"Přidal jsi {audio_count} nahrávek. Jak je mám zpracovat?"
        )
        msg.setInformativeText(
            "• Spojit = jedna přednáška → jeden dokument\n"
            "• Každou zvlášť = samostatný dokument pro každou nahrávku"
        )
        merge_btn = msg.addButton("Spojit do jednoho", QMessageBox.ButtonRole.AcceptRole)
        sep_btn = msg.addButton(
            f"Každou zvlášť ({audio_count} dokumentů)", QMessageBox.ButtonRole.AcceptRole
        )
        msg.addButton("Zrušit", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(merge_btn)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked is merge_btn:
            return "merge"
        if clicked is sep_btn:
            return "separate"
        return None

    def _build_job_queue(self, sources, mode: JobMode, batch_mode: str) -> None:
        """Naplní self._job_queue podle batch módu + paralelně controller IDs."""
        # Klíč šablony rozhoduje, jaké sekce AI vyrobí. Když si uživatel vybral
        # konkrétní šablonu ("sales_meeting", "teacher_reflection", …), schéma
        # výstupu sedne na to, co zadání slibuje. "" = vlastní zadání → student.
        template_key = self._prompt_editor.current_template_key() or "student"
        backend = _parse_backend(self._settings.transcribe_backend)
        # Rozlišování mluvčích (diarizace) zapneme automaticky u konverzačních
        # šablon (sales, zápis ze schůzky) — ale jen u cloud Gemini přepisu,
        # lokální Whisper to neumí. U přednášky (monolog) zůstává vypnuté.
        from app.core.ai.prompts import is_conversation_template

        diarize = (
            backend == TranscribeBackend.CLOUD_GEMINI
            and is_conversation_template(template_key)
        )
        common = dict(
            user_prompt=self._prompt_editor.text(),
            output_dir=Path(self._settings.output_dir),
            mode=mode,
            whisper_model=self._settings.whisper_model,
            language=self._settings.language,
            ai_consent_gemini=self._settings.ai_consent_gemini,
            prefer_offline=self._settings.prefer_offline,
            create_md_export=self._settings.create_md_export,
            user_ai_service=self._settings.user_ai_service,
            transcribe_backend=backend,
            prompt_template_key=template_key,
            diarize=diarize,
        )
        from app.core.pipeline import split_sources_for_batch

        groups = split_sources_for_batch(list(sources), batch_mode)
        self._job_queue = [JobConfig(sources=g, **common) for g in groups]
        self._queue_total = len(self._job_queue)
        self._queue_index = 0
        self._queue_results = []

        # Vyčistit předchozí "done" stavy v controlleru, ať nezůstávají v panelu
        # mezi runy.
        self._job_controller.clear_done()
        # Pro každý JobConfig přidat record do controlleru (status="queued")
        self._job_queue_ids = []
        for job in self._job_queue:
            # Label = první source (pro batch "jedna nahrávka = jeden job")
            label = job.sources[0].label if job.sources else "Projekt"
            file_path = job.sources[0].path if job.sources else Path("")
            # Detekce reuse: existuje-li již .txt přepis vedle plánovaného .docx,
            # můžeme pipeline jen regenerovat AI body (kratší, levnější).
            # Pro v1.3.0 jen značíme — pipeline.py reuse zatím sám neimplementuje.
            cached = self._detect_cached_transcript(file_path)
            job_id = self._job_controller.add_job(label, file_path, cached=cached)
            self._job_queue_ids.append(job_id)

    def _start_next_job(self) -> None:
        """Spustí další job z fronty, nebo finalizuje, když je prázdná."""
        if not self._job_queue:
            return
        job = self._job_queue.pop(0)
        # Z paralelního listu vytáhnout odpovídající controller id
        self._current_queue_job_id = (
            self._job_queue_ids.pop(0) if self._job_queue_ids else None
        )
        self._queue_index += 1
        if self._queue_total > 1:
            self._progress.append_message(
                f"▶ Zpracovávám {self._queue_index}/{self._queue_total}: "
                f"{job.sources[0].label if job.sources else '?'}"
            )
        self._progress.reset()
        self._progress.set_batch_position(self._queue_index, self._queue_total)
        self._progress.set_busy(True)
        self._show_fact_card_during_pipeline(True)
        if self._current_queue_job_id:
            self._job_controller.start_job(self._current_queue_job_id)
        self._run_btn.setEnabled(False)
        self._run_current_job(job)

    def _run_current_job(self, job: JobConfig) -> None:
        # Pro self-kalibraci odhadu: zapamatujeme start + celkovou délku audia
        import time as _time

        sources = job.sources
        api_key = self._queue_api_key

        self._pipeline_start_monotonic = _time.monotonic()
        self._pipeline_audio_seconds = sum(
            probe_duration_seconds(s.path) or 0.0
            for s in sources
            if s.kind == SourceKind.AUDIO_VIDEO
        )
        self._pipeline_backend_used = job.transcribe_backend
        try:
            self._pipeline_worker.start(job, api_key)
        except Exception as exc:  # noqa: BLE001
            self._progress.set_busy(False)
            self._run_btn.setEnabled(True)
            QMessageBox.critical(
                self, "Chyba", f"Nepodařilo se spustit zpracování: {exc}"
            )

    def _on_cancel_clicked(self) -> None:
        """Uživatel klikl Zrušit. Nastavíme cancel_event a HNED dáme vizuální
        zpětnou vazbu — Whisper kontroluje zrušení až na hranici segmentu,
        takže reálné zastavení může pár sekund trvat. Bez feedbacku to vypadá,
        že klik nic neudělal a uživatel klikne znovu."""
        self._pipeline_worker.cancel()
        # Pokud běží dávka, zahodíme i zbytek fronty
        self._job_queue = []
        self._progress.set_cancelling()

    def _on_cloud_fallback(self, reason: str) -> None:
        """Pipeline nás informuje, že cloud přepis selhal a přepojuje na lokální."""
        logger.warning("Cloud fallback aktivován: {}", reason)
        self._progress.append_message(
            f"⚠ Cloud přepis selhal: {reason} Pokračuji s lokálním Whisperem (déle)."
        )
        if self._tray is not None:
            self._tray.showMessage(
                "Cloud přepis nedostupný",
                f"{reason}\nPokračuji lokálně přes Whisper (pomalejší, ale spolehlivé).",
                QSystemTrayIcon.MessageIcon.Warning,
                8000,
            )

    def _on_pipeline_progress(self, status: str, fraction: float) -> None:
        """Wrapper progress → ProgressPanel + JobQueueController."""
        self._progress.update(status, fraction)
        if self._current_queue_job_id:
            self._job_controller.update_progress(
                self._current_queue_job_id, status, fraction
            )

    def _on_queue_cancel(self, job_id: str) -> None:
        """Klik na X v QueueItem — buď zruší running job, nebo odebere z fronty."""
        # Pokud je to právě běžící job → cancel přes pipeline_worker
        if job_id == self._current_queue_job_id:
            self._on_cancel_clicked()
            return
        # Jinak hledat v queued/budoucích jobech a odebrat
        if job_id in self._job_queue_ids:
            idx = self._job_queue_ids.index(job_id)
            # Synchronní pop z obou paralelních listů
            self._job_queue_ids.pop(idx)
            if idx < len(self._job_queue):
                self._job_queue.pop(idx)
            # Update queue_total aby ProgressPanel ukazoval správně "X/N"
            self._queue_total = max(0, self._queue_total - 1)
        self._job_controller.cancel_job(job_id)

    def _detect_cached_transcript(self, file_path: Path) -> bool:
        """Heuristika: zkontroluje, jestli existuje .txt přepis z předchozího
        runu pro tenhle zdroj. Když ano, mohli bychom v budoucnu pipeline
        zkrátit. Pro teď jen indikace v UI.

        Hledá v podsložce `Přepisy/` (nové umístění) i v kořeni (staré runy).
        Porovnává sanitizovaně, protože přepis je pojmenovaný `Prepis_<štítek>_…`.
        """
        try:
            from app.core.word_export import safe_filename_part

            output_dir = Path(self._settings.output_dir)
            if not output_dir.is_dir():
                return False
            needle = safe_filename_part(file_path.stem, fallback="", max_len=40)
            if not needle:
                return False
            search_dirs = [output_dir, output_dir / "Přepisy"]
            for d in search_dirs:
                if not d.is_dir():
                    continue
                for candidate in d.glob("*.txt"):
                    if needle in candidate.stem:
                        return True
        except OSError:
            pass
        return False

    def _on_pipeline_ok(self, result) -> None:
        self._progress.set_busy(False)
        self._show_fact_card_during_pipeline(False)
        self._refresh_run_button()
        # Označit aktuální controller job jako done
        if self._current_queue_job_id:
            self._job_controller.finish_job(
                self._current_queue_job_id, result.output_path
            )
            self._current_queue_job_id = None
        self._progress.append_message(f"✅ Hotovo. Výstup: {result.output_path}")
        self._add_to_recents(result.output_path)
        # Uložíme si poslední výsledek pro chat (potřebuje plný kontext).
        self._last_result = result
        # Self-kalibrace odhadu — jen pro lokální přepis (cloud má jinou dynamiku)
        self._calibrate_speed_factor(result)
        self._queue_results.append(result)

        # Dávka (víc jobů) — nepřerušujeme blokujícím dialogem, jen tichá
        # notifikace a pokračujeme dalším jobem. Souhrn až na konci fronty.
        if self._job_queue:
            self._notify(
                "Hlas do textu",
                f"Hotovo {self._queue_index}/{self._queue_total}: {result.output_path.name}",
            )
            self._start_next_job()
            return

        # Poslední / jediný job — souhrnný dialog
        if self._queue_total > 1:
            self._show_batch_summary()
            return

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
        chat_btn = msg.addButton("Chatovat o dokumentu", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("Zavřít", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(open_doc_btn)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked is open_doc_btn:
            self._open_file(result.output_path)
        elif clicked is open_folder_btn:
            self._open_file(result.output_path.parent)
        elif clicked is chat_btn:
            self._open_chat_dialog(result)

    def _show_batch_summary(self) -> None:
        """Souhrnný dialog po dokončení celé dávky."""
        n = len(self._queue_results)
        first_dir = self._queue_results[0].output_path.parent if self._queue_results else None
        self._notify("Hlas do textu — dávka hotová ✅", f"Vyrobeno {n} dokumentů.")
        msg = QMessageBox(self)
        msg.setWindowTitle("Dávka dokončena")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(
            f"<b>Hotovo — vyrobeno {n} dokumentů.</b><br><br>"
            "Najdeš je roztříděné podle tématu ve výstupní složce."
        )
        msg.setTextFormat(Qt.TextFormat.RichText)
        open_btn = msg.addButton("Otevřít složku", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Zavřít", QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        if msg.clickedButton() is open_btn and first_dir is not None:
            # Otevřeme kořenovou výstupní složku (ne téma-podsložku konkrétního jobu)
            self._open_file(Path(self._settings.output_dir))

    def _open_chat_dialog(self, result) -> None:
        """Otevře chat dialog pro aktuální PipelineResult."""
        from app.core.ai.chat import ChatSession
        from app.core.ai.router import AIRouter
        from app.gui.widgets.chat_dialog import ChatDialog

        # Postavíme router (stejně jako v pipeline) — Gemini Free → Ollama.
        # Wrap v try/except: pokud konstrukce selže (např. Ollama provider
        # vyhodí při inicializaci), nechceme padat tiše do logu.
        pseudo_job = JobConfig(
            sources=[],
            user_prompt="",
            output_dir=Path(self._settings.output_dir),
            ai_consent_gemini=self._settings.ai_consent_gemini,
            prefer_offline=self._settings.prefer_offline,
        )
        from app.core.pipeline import _build_router  # interní helper

        try:
            router = _build_router(pseudo_job, get_gemini_api_key())
        except Exception as exc:  # noqa: BLE001
            logger.exception("Chat: nepodařilo se postavit AIRouter")
            QMessageBox.warning(
                self,
                "Chat nelze otevřít",
                f"Nepodařilo se připravit AI: {exc}\n\n"
                "Zkontroluj Gemini API klíč v Nastavení nebo zkus to později.",
            )
            return
        if not isinstance(router, AIRouter):
            QMessageBox.warning(
                self,
                "Chat nelze otevřít",
                "Žádný AI provider není dostupný. Nastav Gemini klíč v Nastavení.",
            )
            return

        session = ChatSession(
            router=router,
            transcripts=list(result.transcripts),
            slides=list(result.slides),
            current_material=result.material,
        )
        dialog = ChatDialog(session, result.output_path, parent=self)
        dialog.material_changed.connect(
            lambda new_material, r=result, d=dialog: self._on_chat_material_changed(
                new_material, r, d
            )
        )
        dialog.exec()

    def _on_chat_material_changed(self, new_material, result, dialog) -> None:
        """Přegeneruje .docx s novým materiálem (po Apply v chatu)."""
        from app.core.word_export import export_docx

        try:
            export_docx(
                output_path=result.output_path,
                material=new_material,
                transcripts=result.transcripts,
                slides=result.slides,
                sources=[],  # už jsme v post-pipeline kontextu
                user_prompt=None,
            )
            # Update result objektu, aby další chat zprávy viděly nový materiál
            result.material = new_material
            self._progress.append_message(
                f"✏ Dokument upraven podle chatu: {result.output_path.name}"
            )
            self._notify(
                "Dokument upraven",
                f"Aplikoval jsem změnu navrženou v chatu: {result.output_path.name}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Re-export po chatu selhal: {}", exc)
            QMessageBox.warning(
                dialog, "Re-export selhal",
                f"Nepodařilo se přegenerovat dokument: {exc}",
            )

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
        self._show_fact_card_during_pipeline(False)
        self._refresh_run_button()
        # Označit aktuální controller job jako error / cancelled
        if self._current_queue_job_id:
            if cancelled:
                self._job_controller.cancel_job(self._current_queue_job_id)
            else:
                self._job_controller.error_job(self._current_queue_job_id, message)
            self._current_queue_job_id = None
        # Pokud user zrušil dávku, označit i zbytek queued jobů jako cancelled
        if cancelled:
            for jid in self._job_queue_ids:
                self._job_controller.cancel_job(jid)
            self._job_queue_ids = []

        # Cancel zastaví celou dávku (uživatel to chtěl).
        if cancelled:
            self._job_queue = []  # zahodit zbytek fronty
            self._progress.append_message("⚠️ Zpracování zrušeno.")
            QMessageBox.information(self, "Zrušeno", "Zpracování bylo zrušeno.")
            return

        # Chyba JEDNOHO jobu v dávce nezastaví ostatní — zalogujeme a jedeme dál.
        if self._job_queue:
            self._progress.append_message(
                f"❌ {self._queue_index}/{self._queue_total} selhalo: {message[:100]}. "
                "Pokračuji dalším."
            )
            self._notify("Hlas do textu", "Jedna nahrávka selhala, pokračuji dál.", is_error=True)
            self._start_next_job()
            return

        # Poslední/jediný job
        if self._queue_total > 1:
            # Konec dávky — část mohla projít
            done = len(self._queue_results)
            self._progress.append_message(f"❌ Poslední selhalo: {message[:100]}")
            QMessageBox.warning(
                self, "Dávka dokončena s chybou",
                f"Hotovo {done} z {self._queue_total}. Poslední selhalo:\n{message[:200]}",
            )
            return

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
                template_key=self._prompt_editor.current_template_key() or "student",
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
            transcribe_backend=self._settings.transcribe_backend,
            cpu_speed_factor=self._settings.cpu_speed_factor,
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
        # Redesign v1.1.2: vlastní dialog místo QMessageBox.
        # Zeptáme se, jestli stáhnout teď, a pak otevřeme standalone download dialog.
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
        # Spustí worker a otevře standalone dialog s 3-krokovým progressem.
        # Dialog je modal — uživatel může počkat nebo zavřít (stopne worker).
        from app.gui.widgets.model_download_dialog import ModelDownloadDialog

        self._model_worker.start(self._settings.whisper_model)
        self._run_btn.setEnabled(False)
        dlg = ModelDownloadDialog(
            self._settings.whisper_model,
            self._model_worker,
            self,
        )
        dlg.exec()
        self._refresh_run_button()

    def _on_model_progress(self, status: str, fraction: float) -> None:
        if fraction < 0:
            self._progress.append_message(status)
        else:
            self._progress.update(status, fraction)

    def _on_model_ready(self) -> None:
        self._progress.set_busy(False)
        self._progress.append_message("✅ Model připraven.")
        self._refresh_run_button()
        # Tray notifikace — stahování může trvat minuty, uživatel mohl
        # mezitím přepnout do jiné aplikace
        self._notify(
            "Whisper model stažen",
            f"Model {self._settings.whisper_model} je připraven — můžeš spustit přepis.",
        )

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

        self._update_banner.show_installing()
        try:
            apply_update(self._update_installer_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("apply_update selhalo: {}", exc)
            self._update_banner.show_error(str(exc))
            return

        # Na Windows apply_update aplikaci sama ukončí (installer doběhne
        # po 3s delayi). Na macOS jen otevře DMG a app běží dál — uživatel
        # musí ručně přetáhnout novou verzi do Aplikací. Ukážeme mu instrukci.
        if sys.platform == "darwin":
            self._update_banner.show_macos_manual()
            QMessageBox.information(
                self,
                "Dokončení aktualizace",
                "Otevřel jsem okno s novou verzí.\n\n"
                "1. Přetáhni ikonu Hlas do textu do složky Aplikace "
                "(přepiš stávající).\n"
                "2. Zavři tuto aplikaci.\n"
                "3. Spusť novou verzi z Aplikací.",
            )


    def _calibrate_speed_factor(self, result) -> None:
        """Po lokálním přepisu změří skutečnou rychlost a upraví odhad pro příště.

        speed_factor = skutečné_RTF / tabulkové_RTF. Vyhladíme EMA, ať jeden
        atypický běh odhad nerozhodí. Cloud běhy ignorujeme (jiná dynamika).
        """
        from app.core.models import TranscribeBackend

        if getattr(self, "_pipeline_backend_used", None) == TranscribeBackend.CLOUD_GEMINI:
            return
        start = getattr(self, "_pipeline_start_monotonic", None)
        audio_sec = getattr(self, "_pipeline_audio_seconds", 0.0)
        if start is None or audio_sec < 30:
            return  # krátké audio = nespolehlivé měření

        import time as _time

        from app.core.transcribe import estimate_transcribe_seconds

        elapsed = _time.monotonic() - start
        actual_rtf = elapsed / audio_sec
        # tabulkové RTF pro tento model (bez kalibrace)
        table_rtf = estimate_transcribe_seconds(audio_sec, self._settings.whisper_model) / audio_sec
        if table_rtf <= 0:
            return
        observed_factor = actual_rtf / table_rtf

        old = self._settings.cpu_speed_factor or 1.0
        # EMA: 40 % nový, 60 % historie
        new_factor = 0.4 * observed_factor + 0.6 * old
        self._settings.cpu_speed_factor = max(0.3, min(5.0, new_factor))
        save_settings(self._settings)
        logger.info(
            "Kalibrace odhadu: actual_rtf={:.2f}, factor {:.2f} → {:.2f}",
            actual_rtf, old, self._settings.cpu_speed_factor,
        )

    def _on_uninstall_requested(self) -> None:
        """Smaže user data + uložené klíče. Pak dá platform-specific instrukci
        k dokončení (přetáhnout .app do koše / Ovládací panely)."""
        from app.config import USER_CONFIG_DIR, USER_DATA_DIR

        answer = QMessageBox.warning(
            self,
            "Odinstalovat / smazat data",
            "Tímto smažu z tohoto počítače:\n"
            "• stažené Whisper modely (0,5–1,5 GB)\n"
            "• nastavení a logy\n"
            "• uložený Gemini klíč a aktivační klíč\n\n"
            "Samotnou aplikaci pak odstraníš ručně (řeknu jak). Pokračovat?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        errors: list[str] = []

        # 1) Smazat uložené klíče (keyring: gemini + licence)
        try:
            from app.settings import set_gemini_api_key

            set_gemini_api_key("")  # prázdný = delete z keyringu
        except Exception as exc:  # noqa: BLE001
            logger.warning("Mazání Gemini klíče selhalo: {}", exc)
            errors.append(f"Gemini klíč: {exc}")
        try:
            from app.licensing.store import clear_stored_key

            clear_stored_key()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Mazání licenčního klíče selhalo: {}", exc)
            errors.append(f"Licenční klíč: {exc}")

        # 2) Smazat user data adresáře (modely, config, logy)
        import shutil

        for d in {USER_DATA_DIR, USER_CONFIG_DIR}:
            try:
                if d.exists():
                    shutil.rmtree(d, ignore_errors=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Mazání {} selhalo: {}", d, exc)
                errors.append(f"{d}: {exc}")

        # 3) Platform-specific instrukce k dokončení
        if sys.platform == "darwin":
            finish = (
                "Data smazána. Pro úplné odstranění přetáhni aplikaci "
                "Hlas do textu ze složky Aplikace do Koše."
            )
        elif sys.platform == "win32":
            finish = (
                "Data smazána. Pro odebrání samotné aplikace jdi do "
                "Nastavení → Aplikace → Hlas do textu → Odinstalovat."
            )
        else:
            finish = "Data smazána. Aplikaci odeber podle svého systému."

        if errors:
            finish += "\n\nPoznámka: některé položky se nepodařilo smazat:\n" + "\n".join(errors)

        QMessageBox.information(self, "Hotovo", finish)
        logger.info("Uživatel spustil odinstalaci dat (chyby: {})", len(errors))
        # Aplikaci ukončíme — bez dat by stejně nefungovala
        self.close()


def _parse_backend(raw: str | None) -> TranscribeBackend:
    """Tolerantní mapování AppSettings.transcribe_backend (str) → enum."""
    if raw == TranscribeBackend.CLOUD_GEMINI.value:
        return TranscribeBackend.CLOUD_GEMINI
    return TranscribeBackend.LOCAL_WHISPER
