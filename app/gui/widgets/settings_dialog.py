"""Settings — tři sekce, bez hint textů pod každým polem.

Veřejné API: __init__(settings, parent), accept()
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
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
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import GEMINI_API_KEY_URL, WHISPER_MODEL_CHOICES
from app.gui.widgets.icons import icon, icon_size
from app.settings import AppSettings, get_gemini_api_key, set_gemini_api_key

ACCENT = "#205ca8"


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-size: 12.5px; font-weight: 600; color: palette(text);")
    return lbl


def _divider() -> QWidget:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("background: palette(midlight); max-height: 1px; border: none;")
    f.setFixedHeight(1)
    return f


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nastavení")
        self.setMinimumWidth(540)
        self._settings = settings

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(12)

        title = QLabel("Nastavení")
        f = QFont()
        f.setPointSize(17)
        f.setWeight(QFont.Weight.DemiBold)
        title.setFont(f)
        root.addWidget(title)

        root.addWidget(_divider())

        # ----- Gemini -----
        root.addWidget(_field_label("Gemini klíč"))

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

        self._get_key_btn = QPushButton("Získat klíč")
        self._get_key_btn.setIcon(icon("external", size=13, color=ACCENT))
        self._get_key_btn.setIconSize(icon_size(13))
        self._get_key_btn.setStyleSheet(
            "QPushButton { padding: 8px 14px; font-weight: 600; "
            "color: " + ACCENT + "; background: transparent; "
            "border: 1px solid " + ACCENT + "; border-radius: 8px; }"
            "QPushButton:hover { background: rgba(32,92,168,0.08); }"
        )
        self._get_key_btn.clicked.connect(self._open_gemini_keys_page)
        api_row.addWidget(self._get_key_btn)
        root.addLayout(api_row)

        self._consent_cb = QCheckBox("Souhlasím s odesíláním přepisu do Gemini.")
        self._consent_cb.setObjectName("Consent")
        self._consent_cb.setChecked(settings.ai_consent_gemini)
        self._consent_cb.setStyleSheet(
            "QCheckBox#Consent { padding: 11px 14px; "
            "background: rgba(243, 196, 60, 0.16); "
            "border: 1px solid rgba(243, 196, 60, 0.55); "
            "border-radius: 10px; color: palette(text); font-weight: 500; }"
            "QCheckBox#Consent::indicator { width: 18px; height: 18px; }"
        )
        root.addWidget(self._consent_cb)

        self._offline_cb = QCheckBox("Používat offline Ollamu místo Gemini")
        self._offline_cb.setChecked(settings.prefer_offline)
        root.addWidget(self._offline_cb)

        root.addWidget(_divider())

        # ----- Whisper -----
        root.addWidget(_field_label("Kvalita přepisu"))
        self._model_combo = QComboBox()
        self._model_combo.setMinimumHeight(36)
        for m in WHISPER_MODEL_CHOICES:
            self._model_combo.addItem(self._whisper_label(m), userData=m)
        try:
            current_idx = list(WHISPER_MODEL_CHOICES).index(settings.whisper_model)
        except ValueError:
            current_idx = 1
        self._model_combo.setCurrentIndex(max(0, current_idx))
        root.addWidget(self._model_combo)

        root.addWidget(_divider())

        # ----- Output -----
        root.addWidget(_field_label("Výstupní složka"))
        out_row = QHBoxLayout()
        out_row.setSpacing(8)
        self._output_edit = QLineEdit(settings.output_dir)
        self._output_edit.setMinimumHeight(36)
        out_row.addWidget(self._output_edit, 1)

        self._output_browse = QPushButton("Procházet")
        self._output_browse.setIcon(icon("folder", size=14, color="#7a7a7a"))
        self._output_browse.setIconSize(icon_size(14))
        self._output_browse.setMinimumHeight(36)
        self._output_browse.clicked.connect(self._pick_output_dir)
        out_row.addWidget(self._output_browse)
        root.addLayout(out_row)

        root.addStretch(1)

        # ----- Buttons -----
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Uložit")
        ok_btn.setObjectName("Primary")
        ok_btn.setMinimumHeight(38)
        ok_btn.setMinimumWidth(110)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setText("Zrušit")
        cancel_btn.setMinimumHeight(38)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

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
        super().accept()

    def _toggle_api_visibility(self) -> None:
        if self._show_btn.isChecked():
            self._api_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._show_btn.setIcon(icon("eye-off", size=16, color=ACCENT))
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
            "small": "Rychlá  ·  ~250 MB",
            "medium": "Doporučená  ·  ~770 MB",
            "large-v3": "Nejlepší  ·  ~1.5 GB",
        }.get(name, name)
