"""Welcome dialog — Ahoj, vlož klíč, souhlas, start. Konec.

Veřejné API: __init__(settings, parent), accept()
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import GEMINI_API_KEY_URL
from app.gui.widgets.icons import icon, icon_size, pixmap
from app.settings import AppSettings, set_gemini_api_key

ACCENT = "#205ca8"


class FirstRunDialog(QDialog):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Vítej")
        self.setMinimumWidth(480)
        self._settings = settings

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(14)

        # Hero
        hero = QHBoxLayout()
        hero.setSpacing(14)
        avatar = QLabel()
        avatar.setPixmap(pixmap("graduation", size=28, color=ACCENT))
        avatar.setFixedSize(52, 52)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            "QLabel { background: rgba(32,92,168,0.10); border-radius: 13px; }"
        )
        hero.addWidget(avatar)

        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel("Ahoj 👋")
        f = QFont()
        f.setPointSize(18)
        f.setWeight(QFont.Weight.DemiBold)
        title.setFont(f)
        col.addWidget(title)
        sub = QLabel("Z přednášek uděláme studijní poznámky.")
        sub.setStyleSheet("color: palette(placeholder-text); font-size: 13px;")
        col.addWidget(sub)
        hero.addLayout(col, 1)
        root.addLayout(hero)

        root.addSpacing(8)

        # Klíč
        explain = QLabel("Pro AI poznámky potřebuješ klíč od Googlu — zdarma, 2 minuty.")
        explain.setWordWrap(True)
        explain.setStyleSheet("font-size: 13px; color: palette(text);")
        root.addWidget(explain)

        get_key_btn = QPushButton("Získat klíč")
        get_key_btn.setObjectName("Primary")
        get_key_btn.setIcon(icon("external", size=15, color="#ffffff"))
        get_key_btn.setIconSize(icon_size(15))
        get_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        get_key_btn.clicked.connect(self._open_gemini_keys_page)
        get_key_btn.setStyleSheet(
            "QPushButton#Primary { background:" + ACCENT + "; color:white; "
            "border:1px solid " + ACCENT + "; border-radius:8px; "
            "padding:10px 18px; font-weight:600; }"
            "QPushButton#Primary:hover { background:#1a4d8f; }"
        )
        root.addWidget(get_key_btn)

        self._api_edit = QLineEdit()
        self._api_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_edit.setPlaceholderText("Vlož klíč sem")
        self._api_edit.setMinimumHeight(38)
        root.addWidget(self._api_edit)

        # Souhlas
        self._consent_cb = QCheckBox("Souhlasím s odesíláním přepisu do Gemini.")
        self._consent_cb.setObjectName("Consent")
        self._consent_cb.setStyleSheet(
            "QCheckBox#Consent { padding: 12px 14px; "
            "background: rgba(243, 196, 60, 0.16); "
            "border: 1px solid rgba(243, 196, 60, 0.55); "
            "border-radius: 10px; color: palette(text); font-weight: 500; }"
            "QCheckBox#Consent::indicator { width: 18px; height: 18px; }"
        )
        root.addWidget(self._consent_cb)

        # Skip note
        skip = QLabel("Klíč můžeš přidat i později v Nastavení.")
        skip.setStyleSheet("color: palette(placeholder-text); font-size: 11.5px;")
        skip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(skip)

        # CTA
        ok_btn = QPushButton("Začít")
        ok_btn.setObjectName("Primary")
        ok_btn.setMinimumHeight(40)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        root.addWidget(ok_btn)

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
