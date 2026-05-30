"""Nastavení — tabbed sidebar layout dle redesign handoff.

Čtyři taby:
  - AI       — Gemini klíč, souhlas, offline Ollama, .md export, AI služba, role + tmavý
  - Přepis   — backend (lokálně/cloud), Whisper model
  - Výstup   — výstupní složka
  - Licence  — info o aktivaci

Vlevo sidebar s ikonami, vpravo content stack. Bottom bar s Uložit/Zrušit.

Veřejné API: __init__(settings, parent), accept()
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import GEMINI_API_KEY_URL, WHISPER_MODEL_CHOICES
from app.gui.styles import tokens
from app.gui.widgets.icons import icon, icon_size
from app.settings import AppSettings, get_gemini_api_key, set_gemini_api_key

# --------------------------------------------------------------------------- #
# Pomocné helpers
# --------------------------------------------------------------------------- #


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-size: 12.5px; font-weight: 600; color: palette(text);")
    return lbl


def _section_divider() -> QWidget:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("background: palette(midlight); max-height: 1px; border: none;")
    f.setFixedHeight(1)
    return f


# --------------------------------------------------------------------------- #
# Sidebar tabs widget
# --------------------------------------------------------------------------- #


class _SettingsSidebar(QListWidget):
    """Vertikální sidebar s ikonami + textem pro přepínání tabů.

    Položky jsou klikatelné, vybraná dostane accent border (přes QSS objectName).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsSidebar")
        self.setFixedWidth(180)
        self.setSpacing(2)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setIconSize(QSize(18, 18))
        self.setStyleSheet(
            "QListWidget#SettingsSidebar {"
            "  background: palette(alternate-base);"
            "  border-right: 1px solid palette(midlight);"
            "  border-top-left-radius: 12px; border-bottom-left-radius: 12px;"
            "  padding: 12px 8px;"
            "  font-size: 13px;"
            "}"
            "QListWidget#SettingsSidebar::item {"
            "  padding: 9px 10px;"
            "  border-radius: 8px;"
            "  color: palette(text);"
            "}"
            "QListWidget#SettingsSidebar::item:hover {"
            "  background: palette(midlight);"
            "}"
            f"QListWidget#SettingsSidebar::item:selected {{"
            f"  background: {tokens.accent_soft(0.12)};"
            f"  color: {tokens.accent()};"
            f"  font-weight: 700;"
            f"}}"
        )

    def add_tab(self, label: str, icon_name: str) -> None:
        item = QListWidgetItem(icon(icon_name, size=18, color=tokens.accent()), label)
        item.setSizeHint(QSize(0, 36))
        self.addItem(item)


# --------------------------------------------------------------------------- #
# SettingsDialog
# --------------------------------------------------------------------------- #


class SettingsDialog(QDialog):
    """Tabbed Settings dialog dle redesignu (sidebar + content stack)."""

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nastavení")
        self.setMinimumSize(820, 560)
        self._settings = settings

        # Outer layout: header + body (sidebar + stack) + footer
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ----- Header (titulek) ------------------------------------------
        header = QWidget()
        header.setStyleSheet(
            "background: palette(base); "
            "border-bottom: 1px solid palette(midlight); "
            "border-top-left-radius: 12px; border-top-right-radius: 12px;"
        )
        header_lay = QVBoxLayout(header)
        header_lay.setContentsMargins(28, 18, 28, 14)
        title = QLabel("Nastavení")
        f = QFont()
        f.setPointSize(18)
        f.setWeight(QFont.Weight.DemiBold)
        title.setFont(f)
        header_lay.addWidget(title)
        outer.addWidget(header)

        # ----- Body: sidebar | stack -------------------------------------
        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        self._sidebar = _SettingsSidebar()
        self._sidebar.add_tab("AI",      "sparkles")
        self._sidebar.add_tab("Přepis",  "audio")
        self._sidebar.add_tab("Výstup",  "folder")
        self._sidebar.add_tab("Licence", "shield")
        self._sidebar.setCurrentRow(0)
        body_lay.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        self._stack.setObjectName("SettingsStack")
        self._stack.setStyleSheet(
            "QStackedWidget#SettingsStack { background: palette(base); }"
        )
        body_lay.addWidget(self._stack, 1)

        # Build content pages
        self._stack.addWidget(self._build_ai_page())
        self._stack.addWidget(self._build_transcribe_page())
        self._stack.addWidget(self._build_output_page())
        self._stack.addWidget(self._build_license_page())

        self._sidebar.currentRowChanged.connect(self._stack.setCurrentIndex)
        outer.addWidget(body, 1)

        # ----- Footer (Zrušit / Uložit) ----------------------------------
        footer = QWidget()
        footer.setStyleSheet(
            "background: palette(base); "
            "border-top: 1px solid palette(midlight); "
            "border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;"
        )
        footer_lay = QHBoxLayout(footer)
        footer_lay.setContentsMargins(28, 14, 28, 14)
        footer_lay.addStretch(1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Uložit")
        ok_btn.setObjectName("Primary")
        ok_btn.setMinimumHeight(38)
        ok_btn.setMinimumWidth(120)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setText("Zrušit")
        cancel_btn.setMinimumHeight(38)
        cancel_btn.setMinimumWidth(96)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        footer_lay.addWidget(buttons)
        outer.addWidget(footer)

    # ====================================================================
    # Tab content builders
    # ====================================================================

    def _page_container(self) -> tuple[QWidget, QVBoxLayout]:
        """Vrátí scrollovatelný container pro tab content + jeho layout."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(12)
        return page, lay

    # ---- AI tab ---------------------------------------------------------

    def _build_ai_page(self) -> QWidget:
        page, lay = self._page_container()

        # ----- Gemini klíč -----
        lay.addWidget(_field_label("Gemini klíč"))

        api_row = QHBoxLayout()
        api_row.setSpacing(8)
        self._api_edit = QLineEdit(get_gemini_api_key() or "")
        self._api_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_edit.setPlaceholderText("Vlož klíč")
        self._api_edit.setMinimumHeight(36)
        api_row.addWidget(self._api_edit, 1)

        self._show_btn = QPushButton()
        self._show_btn.setCheckable(True)
        self._show_btn.setIcon(icon("eye", size=16, color="#7a7a7a"))
        self._show_btn.setIconSize(icon_size(16))
        self._show_btn.setFixedSize(36, 36)
        self._show_btn.setToolTip("Zobrazit klíč")
        self._show_btn.clicked.connect(self._toggle_api_visibility)
        api_row.addWidget(self._show_btn)

        accent = tokens.accent()
        self._get_key_btn = QPushButton("Získat klíč")
        self._get_key_btn.setIcon(icon("external", size=13, color=accent))
        self._get_key_btn.setIconSize(icon_size(13))
        self._get_key_btn.setStyleSheet(
            "QPushButton { padding: 8px 14px; font-weight: 600; "
            f"color: {accent}; background: transparent; "
            f"border: 1px solid {accent}; border-radius: 8px; }}"
            f"QPushButton:hover {{ background: {tokens.accent_soft(0.08)}; }}"
        )
        self._get_key_btn.clicked.connect(self._open_gemini_keys_page)
        api_row.addWidget(self._get_key_btn)
        lay.addLayout(api_row)

        # ----- Souhlas s odesíláním -----
        self._consent_cb = QCheckBox(
            "Souhlasím s odesíláním přepisu a audia do Gemini Free. "
            "Free tier používá texty k tréninku modelů."
        )
        self._consent_cb.setObjectName("Consent")
        self._consent_cb.setChecked(self._settings.ai_consent_gemini)
        self._consent_cb.setStyleSheet(
            "QCheckBox#Consent { padding: 11px 14px; "
            "background: rgba(243, 196, 60, 0.16); "
            "border: 1px solid rgba(243, 196, 60, 0.55); "
            "border-radius: 10px; color: palette(text); font-weight: 500; }"
            "QCheckBox#Consent::indicator { width: 18px; height: 18px; }"
        )
        lay.addWidget(self._consent_cb)

        # ----- Offline Ollama -----
        self._offline_cb = QCheckBox("Používat offline Ollamu místo Gemini")
        self._offline_cb.setChecked(self._settings.prefer_offline)
        lay.addWidget(self._offline_cb)

        # ----- .md export -----
        self._md_cb = QCheckBox(
            "Učit se z přednášky přes AI — uložit i .md soubor (prompt pro AI)"
        )
        self._md_cb.setChecked(self._settings.create_md_export)
        self._md_cb.setToolTip(
            "Vyrobí Markdown soubor s přepisem připravený jako prompt pro "
            "ChatGPT/Claude/Gemini. Otevři ho v AI a získej studijní materiál na míru."
        )
        lay.addWidget(self._md_cb)

        # ----- AI služba (chip-style row) -----
        ai_row = QHBoxLayout()
        ai_row.setSpacing(8)
        ai_row.addWidget(_field_label("AI služba"))
        self._ai_service_combo = QComboBox()
        self._ai_service_combo.setMinimumHeight(32)
        self._ai_service_combo.addItem("Žádná", userData="none")
        self._ai_service_combo.addItem("ChatGPT", userData="chatgpt")
        self._ai_service_combo.addItem("Claude", userData="claude")
        self._ai_service_combo.addItem("Gemini", userData="gemini")
        self._ai_service_combo.addItem("Jiná", userData="other")
        for i in range(self._ai_service_combo.count()):
            if self._ai_service_combo.itemData(i) == self._settings.user_ai_service:
                self._ai_service_combo.setCurrentIndex(i)
                break
        ai_row.addWidget(self._ai_service_combo, 1)
        lay.addLayout(ai_row)

        lay.addWidget(_section_divider())

        # ----- Role + tmavý režim (vzhled) -----
        lay.addWidget(_field_label("Role aplikace"))
        self._role_combo = QComboBox()
        self._role_combo.setMinimumHeight(36)
        self._role_combo.addItem("Student / žák (Safe4Future modrá)", userData="student")
        self._role_combo.addItem("Učitel/ka (Original Teal)", userData="teacher")
        for i in range(self._role_combo.count()):
            if self._role_combo.itemData(i) == self._settings.app_role:
                self._role_combo.setCurrentIndex(i)
                break
        self._role_combo.setToolTip(
            "Učitelský režim přidá visačku v hlavičce a teal barvu místo "
            "Safe4Future modré. Změna se projeví hned po Uložit (drop zone "
            "a flow ikony mohou vyžadovat restart pro plnou aktualizaci)."
        )
        lay.addWidget(self._role_combo)

        self._dark_cb = QCheckBox("Tmavý režim")
        self._dark_cb.setChecked(self._settings.dark_mode)
        self._dark_cb.setToolTip(
            "Přepne paletu na tmavé pozadí (Deep Ink). Některé inline-stylované "
            "widgety mohou vyžadovat restart pro plný efekt."
        )
        lay.addWidget(self._dark_cb)

        lay.addStretch(1)
        return page

    # ---- Přepis tab -----------------------------------------------------

    def _build_transcribe_page(self) -> QWidget:
        page, lay = self._page_container()

        lay.addWidget(_field_label("Způsob přepisu"))
        self._backend_combo = QComboBox()
        self._backend_combo.setMinimumHeight(36)
        self._backend_combo.addItem(
            "Lokálně (offline, pomalejší)", userData="local_whisper"
        )
        self._backend_combo.addItem(
            "Rychlý cloud (Gemini, vyžaduje internet)", userData="cloud_gemini"
        )
        for i in range(self._backend_combo.count()):
            if self._backend_combo.itemData(i) == self._settings.transcribe_backend:
                self._backend_combo.setCurrentIndex(i)
                break
        self._backend_combo.setToolTip(
            "Lokálně: faster-whisper na CPU, plně offline, 5–15 min na 15 min audia.\n"
            "Cloud: pošle audio Googlu (Gemini), ~1 min na 15 min audia. "
            "Vyžaduje API klíč v záložce AI a souhlas s odesíláním dat."
        )
        lay.addWidget(self._backend_combo)

        lay.addWidget(_section_divider())

        lay.addWidget(_field_label("Kvalita lokálního přepisu (Whisper model)"))
        self._model_combo = QComboBox()
        self._model_combo.setMinimumHeight(36)
        for m in WHISPER_MODEL_CHOICES:
            self._model_combo.addItem(self._whisper_label(m), userData=m)
        try:
            current_idx = list(WHISPER_MODEL_CHOICES).index(self._settings.whisper_model)
        except ValueError:
            current_idx = 1
        self._model_combo.setCurrentIndex(max(0, current_idx))
        lay.addWidget(self._model_combo)

        hint = QLabel(
            "Rychlá ~250 MB je doporučená pro běžné použití. Střední ~770 MB "
            "vyžaduje 16 GB RAM. Nejlepší ~1,5 GB má nejvyšší kvalitu, ale přepis "
            "trvá několikanásobně déle."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(placeholder-text); font-size: 11.5px;")
        lay.addWidget(hint)

        lay.addStretch(1)
        return page

    # ---- Výstup tab -----------------------------------------------------

    def _build_output_page(self) -> QWidget:
        page, lay = self._page_container()

        lay.addWidget(_field_label("Výstupní složka"))
        out_row = QHBoxLayout()
        out_row.setSpacing(8)
        self._output_edit = QLineEdit(self._settings.output_dir)
        self._output_edit.setMinimumHeight(36)
        out_row.addWidget(self._output_edit, 1)

        self._output_browse = QPushButton("Procházet")
        self._output_browse.setIcon(icon("folder", size=14, color="#7a7a7a"))
        self._output_browse.setIconSize(icon_size(14))
        self._output_browse.setMinimumHeight(36)
        self._output_browse.clicked.connect(self._pick_output_dir)
        out_row.addWidget(self._output_browse)
        lay.addLayout(out_row)

        hint = QLabel(
            "Sem se ukládají hotové .docx dokumenty se studijními body. "
            "Soubory se roztřídí podle tématu do podsložek."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(placeholder-text); font-size: 11.5px;")
        lay.addWidget(hint)

        lay.addStretch(1)
        return page

    # ---- Licence tab ----------------------------------------------------

    def _build_license_page(self) -> QWidget:
        page, lay = self._page_container()

        from app.licensing import get_activation_info

        info = get_activation_info()
        if info:
            # Hezky strukturovaná tabulka s aktivačními údaji
            activated = info.get("activated_at", "?")
            if activated and "T" in activated:
                try:
                    from datetime import datetime

                    dt = datetime.fromisoformat(activated)
                    activated = dt.strftime("%d. %m. %Y v %H:%M")
                except (ValueError, TypeError):
                    pass
            machine = info.get("machine_display", "?")
            fingerprint = info.get("machine_fingerprint", "")[:8]

            box = QFrame()
            box.setObjectName("LicenseInfoBox")
            box.setStyleSheet(
                "QFrame#LicenseInfoBox { "
                "background: palette(alternate-base); "
                "border: 1px solid palette(midlight); "
                "border-radius: 10px; padding: 6px; }"
            )
            box_lay = QVBoxLayout(box)
            box_lay.setSpacing(8)
            box_lay.setContentsMargins(16, 14, 16, 14)

            for label_text, value_text in [
                ("Stav", "✓ Aktivováno"),
                ("Aktivováno", activated),
                ("Zařízení", f"{machine} (ID: {fingerprint})"),
            ]:
                row = QHBoxLayout()
                row.setSpacing(8)
                k = QLabel(label_text)
                k.setFixedWidth(110)
                k.setStyleSheet(
                    "color: palette(placeholder-text); font-size: 12.5px; font-weight: 500;"
                )
                row.addWidget(k)
                v = QLabel(value_text)
                v.setStyleSheet("color: palette(text); font-size: 12.5px;")
                v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                row.addWidget(v, 1)
                box_lay.addLayout(row)

            lay.addWidget(box)

            note = QLabel(
                "Klíč je uložený bezpečně v systémovém trezoru "
                "(macOS Keychain / Windows Credential Manager). "
                "Není v žádném textovém souboru."
            )
            note.setWordWrap(True)
            note.setStyleSheet(
                "color: palette(placeholder-text); font-size: 11.5px; padding-top: 4px;"
            )
            lay.addWidget(note)
        else:
            no_info = QLabel("Informace o aktivaci nejsou dostupné.")
            no_info.setStyleSheet("color: palette(placeholder-text);")
            lay.addWidget(no_info)

        lay.addStretch(1)
        return page

    # ====================================================================
    # Lifecycle
    # ====================================================================

    def accept(self) -> None:  # type: ignore[override]
        new_key = self._api_edit.text().strip()
        try:
            set_gemini_api_key(new_key)
        except Exception:
            pass

        self._settings.whisper_model = self._model_combo.currentData()
        self._settings.output_dir = self._output_edit.text().strip() or self._settings.output_dir
        self._settings.ai_consent_gemini = self._consent_cb.isChecked()
        self._settings.prefer_offline = self._offline_cb.isChecked()
        self._settings.create_md_export = self._md_cb.isChecked()
        self._settings.user_ai_service = self._ai_service_combo.currentData() or "none"
        self._settings.transcribe_backend = (
            self._backend_combo.currentData() or "local_whisper"
        )

        # Role + dark mode — pokud se změnily, aplikuj theme znovu (live switch).
        new_role = self._role_combo.currentData() or "student"
        new_dark = self._dark_cb.isChecked()
        role_changed = new_role != self._settings.app_role
        dark_changed = new_dark != self._settings.dark_mode
        self._settings.app_role = new_role
        self._settings.dark_mode = new_dark
        if role_changed or dark_changed:
            from PySide6.QtWidgets import QApplication

            from app.gui.styles import theme

            qapp = QApplication.instance()
            if qapp is not None:
                theme.apply_theme(qapp, role=new_role, dark=new_dark)
        super().accept()

    def _toggle_api_visibility(self) -> None:
        if self._show_btn.isChecked():
            self._api_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._show_btn.setIcon(icon("eye-off", size=16, color=tokens.accent()))
        else:
            self._api_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._show_btn.setIcon(icon("eye", size=16, color="#7a7a7a"))

    @staticmethod
    def _open_gemini_keys_page() -> None:
        QDesktopServices.openUrl(QUrl(GEMINI_API_KEY_URL))

    def _pick_output_dir(self) -> None:
        start = self._output_edit.text() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Vyber složku", start)
        if chosen:
            self._output_edit.setText(chosen)

    @staticmethod
    def _whisper_label(name: str) -> str:
        return {
            "small": "Rychlá  ·  ~250 MB  ·  doporučená",
            "medium": "Střední  ·  ~770 MB",
            "large-v3": "Nejlepší  ·  ~1.5 GB  ·  trvá fakt dlouho",
        }.get(name, name)
