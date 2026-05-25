"""Modální dialog pro Nastavení: API klíč, Whisper model, výstupní složka, GDPR souhlas."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import GEMINI_API_KEY_URL, WHISPER_MODEL_CHOICES
from app.settings import AppSettings, get_gemini_api_key, set_gemini_api_key


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nastavení")
        self.setMinimumWidth(520)
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # API klíč
        self._api_edit = QLineEdit(get_gemini_api_key() or "")
        self._api_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_edit.setPlaceholderText("Vlož klíč z aistudio.google.com (zdarma)")
        self._show_btn = QPushButton("👁")
        self._show_btn.setCheckable(True)
        self._show_btn.setFixedWidth(40)
        self._show_btn.clicked.connect(self._toggle_api_visibility)
        self._get_key_btn = QPushButton("Získat klíč…")
        self._get_key_btn.setToolTip("Otevře v prohlížeči stránku Google AI Studio, kde si vytvoříš klíč zdarma")
        self._get_key_btn.clicked.connect(self._open_gemini_keys_page)
        api_row = QHBoxLayout()
        api_row.addWidget(self._api_edit, 1)
        api_row.addWidget(self._show_btn)
        api_row.addWidget(self._get_key_btn)
        api_wrap = QWidget()
        api_wrap.setLayout(api_row)
        form.addRow("Gemini API klíč:", api_wrap)

        # Whisper model
        self._model_combo = QComboBox()
        for m in WHISPER_MODEL_CHOICES:
            self._model_combo.addItem(self._whisper_label(m), userData=m)
        current_idx = max(0, list(WHISPER_MODEL_CHOICES).index(settings.whisper_model) if settings.whisper_model in WHISPER_MODEL_CHOICES else 1)
        self._model_combo.setCurrentIndex(current_idx)
        form.addRow("Whisper model:", self._model_combo)

        # Výstupní složka
        self._output_edit = QLineEdit(settings.output_dir)
        self._output_browse = QPushButton("Procházet…")
        self._output_browse.clicked.connect(self._pick_output_dir)
        out_row = QHBoxLayout()
        out_row.addWidget(self._output_edit, 1)
        out_row.addWidget(self._output_browse)
        out_wrap = QWidget()
        out_wrap.setLayout(out_row)
        form.addRow("Výstupní složka:", out_wrap)

        layout.addLayout(form)

        # GDPR/data souhlas
        self._consent_cb = QCheckBox(
            "Souhlasím s odesíláním textu přepisu do Google Gemini API.\n"
            "Free tier Gemini používá texty k tréninku modelů (viz ai.google.dev/gemini-api/terms)."
        )
        self._consent_cb.setChecked(settings.ai_consent_gemini)
        self._consent_cb.setStyleSheet(
            "QCheckBox { padding: 10px; background-color: #fff8d8; color: #333; "
            "border: 1px solid #d4c97a; border-radius: 4px; font-weight: 500; }"
            "QCheckBox::indicator { width: 18px; height: 18px; }"
        )
        self._consent_cb.setWordWrap(True) if hasattr(self._consent_cb, "setWordWrap") else None
        layout.addWidget(self._consent_cb)

        # Prefer offline
        self._offline_cb = QCheckBox("Vždy používat lokální Ollama (přeskočit Gemini)")
        self._offline_cb.setChecked(settings.prefer_offline)
        layout.addWidget(self._offline_cb)

        # Info label
        info = QLabel(
            "API klíč se ukládá bezpečně do Windows Credential Manager / macOS Keychain. "
            "Není v žádném textovém souboru."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(info)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:  # type: ignore[override]
        # Uložit klíč přes keyring
        new_key = self._api_edit.text().strip()
        try:
            set_gemini_api_key(new_key)
        except Exception:
            # I když keyring selže, neblokuj uživatele
            pass

        self._settings.whisper_model = self._model_combo.currentData()
        self._settings.output_dir = self._output_edit.text().strip() or self._settings.output_dir
        self._settings.ai_consent_gemini = self._consent_cb.isChecked()
        self._settings.prefer_offline = self._offline_cb.isChecked()
        super().accept()

    def _toggle_api_visibility(self) -> None:
        mode = QLineEdit.EchoMode.Normal if self._show_btn.isChecked() else QLineEdit.EchoMode.Password
        self._api_edit.setEchoMode(mode)

    @staticmethod
    def _open_gemini_keys_page() -> None:
        QDesktopServices.openUrl(QUrl(GEMINI_API_KEY_URL))

    def _pick_output_dir(self) -> None:
        start = self._output_edit.text() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Vyber výstupní složku", start)
        if chosen:
            self._output_edit.setText(chosen)

    @staticmethod
    def _whisper_label(name: str) -> str:
        descriptions = {
            "small": "small — rychlejší, slabší čeština (~250 MB)",
            "medium": "medium — doporučeno, dobrá čeština (~770 MB)",
            "large-v3": "large-v3 — nejlepší kvalita, pomalé (~1.5 GB)",
        }
        return descriptions.get(name, name)
