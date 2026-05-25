"""První spuštění: krátký welcome dialog s API klíčem a souhlasy."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import GEMINI_API_KEY_URL
from app.settings import AppSettings, set_gemini_api_key


class FirstRunDialog(QDialog):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Vítejte v Hlas do textu")
        self.setMinimumWidth(560)
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Vítej! 🎓")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)

        intro = QLabel(
            "Aplikace přepíše tvoji přednášku a vytvoří strukturované body pro učení.\n\n"
            "Pro generování bodů využívá zdarma službu Google Gemini.\n"
            "Pokud klíč ještě nemáš, klikni na tlačítko níže — otevře se ti stránka,\n"
            "kde si ho během 2 minut vytvoříš (stačí Google účet)."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        get_key_btn = QPushButton("🔗 Získat API klíč zdarma (otevře se v prohlížeči)")
        get_key_btn.setMinimumHeight(36)
        get_key_btn.setStyleSheet(
            "QPushButton { background-color: #205ca8; color: white; border-radius: 4px; "
            "padding: 8px 16px; font-weight: 600; }"
            "QPushButton:hover { background-color: #1a4d8f; }"
        )
        get_key_btn.clicked.connect(self._open_gemini_keys_page)
        layout.addWidget(get_key_btn)

        layout.addWidget(self._horiz_separator())

        api_label = QLabel("Vlož Gemini API klíč (lze i později v Nastavení):")
        layout.addWidget(api_label)

        self._api_edit = QLineEdit()
        self._api_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_edit.setPlaceholderText("AIza… (klíč začíná na AIza, končí ~40 znaků)")
        layout.addWidget(self._api_edit)

        self._consent_cb = QCheckBox(
            "Souhlasím s odesíláním textu přepisu do Google Gemini API.\n"
            "Free tier používá data k tréninku modelů."
        )
        self._consent_cb.setStyleSheet("padding: 8px; background-color: #fff8d8; border-radius: 4px;")
        layout.addWidget(self._consent_cb)

        offline_note = QLabel(
            "Pokud zatím nechceš zadávat klíč, můžeš použít lokální offline AI (Ollama). "
            "V tom případě klikni Pokračovat bez zadání klíče a v Nastavení zaškrtni 'Vždy používat lokální Ollama'."
        )
        offline_note.setWordWrap(True)
        offline_note.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(offline_note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Pokračovat")
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons, alignment=Qt.AlignmentFlag.AlignRight)

    def accept(self) -> None:  # type: ignore[override]
        key = self._api_edit.text().strip()
        if key:
            try:
                set_gemini_api_key(key)
            except Exception:
                pass
        self._settings.ai_consent_gemini = self._consent_cb.isChecked()
        self._settings.first_run_done = True
        super().accept()

    @staticmethod
    def _open_gemini_keys_page() -> None:
        QDesktopServices.openUrl(QUrl(GEMINI_API_KEY_URL))

    @staticmethod
    def _horiz_separator() -> QWidget:
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #ddd;")
        return sep
