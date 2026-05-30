"""Aktivační dialog — zobrazí se před prvním spuštěním aplikace.

Bez platného klíče se aplikace nedostane k MainWindow.
Klíč se ukládá v keyring (resp. fallback file).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.gui.styles import tokens
from app.licensing import is_valid_format, store_key, validate_key


class ActivationDialog(QDialog):
    """Modal dialog který vyžaduje platný klíč. Bez něj aplikace nepokračuje."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Aktivace — Hlas do textu")
        self.setMinimumWidth(520)
        self.setModal(True)
        # Bez křížku v rohu — nedá se zavřít bez aktivace nebo cancel
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(16)

        # ----- Titulek -----
        title = QLabel("Aktivace aplikace")
        f = QFont()
        f.setPointSize(18)
        f.setWeight(QFont.Weight.DemiBold)
        title.setFont(f)
        root.addWidget(title)

        subtitle = QLabel(
            "Pro spuštění aplikace vlož aktivační klíč, který jsi dostal/a od autora."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: palette(text); font-size: 13px;")
        root.addWidget(subtitle)

        root.addWidget(self._divider())

        # ----- Pole pro klíč -----
        label = QLabel("Aktivační klíč")
        label.setStyleSheet("font-size: 12.5px; font-weight: 600; color: palette(text);")
        root.addWidget(label)

        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText("S4F1-XXXX-XXXX-XXXX-XXXX")
        self._key_edit.setMinimumHeight(44)
        mono_font = QFont()
        mono_font.setFamilies(["Menlo", "Consolas", "SF Mono", "monospace"])
        mono_font.setPointSize(13)
        mono_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        self._key_edit.setFont(mono_font)
        accent = tokens.accent()
        accent_strong = tokens.accent_strong()
        self._key_edit.setStyleSheet(
            "QLineEdit { background: palette(base); "
            "border: 1.5px solid palette(midlight); border-radius: 10px; "
            "padding: 10px 14px; }"
            f"QLineEdit:focus {{ border-color: {accent}; }}"
        )
        self._key_edit.textChanged.connect(self._on_text_changed)
        root.addWidget(self._key_edit)

        self._feedback = QLabel("")
        self._feedback.setWordWrap(True)
        self._feedback.setStyleSheet("font-size: 12px; min-height: 18px;")
        root.addWidget(self._feedback)

        root.addStretch(1)

        # ----- Bottom buttons -----
        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        quit_btn = QPushButton("Ukončit aplikaci")
        quit_btn.setMinimumHeight(40)
        quit_btn.setStyleSheet(
            "QPushButton { background: transparent; color: palette(text); "
            "border: 1px solid palette(midlight); border-radius: 8px; padding: 8px 18px; }"
            "QPushButton:hover { background: palette(alternate-base); }"
        )
        quit_btn.clicked.connect(self.reject)

        self._activate_btn = QPushButton("Aktivovat")
        self._activate_btn.setMinimumHeight(40)
        self._activate_btn.setEnabled(False)
        self._activate_btn.setDefault(True)
        self._activate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._activate_btn.setStyleSheet(
            f"QPushButton {{ background: {accent}; color: white; border: none; "
            "border-radius: 8px; padding: 8px 24px; font-weight: 600; font-size: 13px; }"
            f"QPushButton:hover {{ background: {accent_strong}; }}"
            "QPushButton:disabled { background: #5a7595; color: rgba(255,255,255,150); }"
        )
        self._activate_btn.clicked.connect(self._try_activate)

        button_row.addWidget(quit_btn)
        button_row.addStretch(1)
        button_row.addWidget(self._activate_btn)
        root.addLayout(button_row)

        # Info pod buttons
        info = QLabel(
            "Klíč můžeš získat od autora aplikace. Po aktivaci se uloží "
            "bezpečně do Windows Credential Manager a už se na něj nebudeš ptát."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: palette(mid); font-size: 11px; padding-top: 8px;")
        root.addWidget(info)

    # ------ Logic ------

    def _on_text_changed(self, text: str) -> None:
        # Aktivuj button jen pokud formát klíče je správný
        valid_format = is_valid_format(text)
        self._activate_btn.setEnabled(valid_format)
        if not text.strip():
            self._feedback.setText("")
            self._feedback.setStyleSheet("font-size: 12px; min-height: 18px;")
        elif valid_format:
            self._feedback.setText("Formát klíče vypadá správně. Klikni Aktivovat.")
            self._feedback.setStyleSheet(
                "font-size: 12px; min-height: 18px; color: #2a7a3a;"
            )
        else:
            self._feedback.setText(
                "Klíč musí být ve formátu S4F1-XXXX-XXXX-XXXX-XXXX (20 znaků + 4 pomlčky)."
            )
            self._feedback.setStyleSheet(
                "font-size: 12px; min-height: 18px; color: #b04040;"
            )

    def _try_activate(self) -> None:
        key = self._key_edit.text().strip().upper()
        if not validate_key(key):
            self._feedback.setText(
                "Tento klíč není platný. Zkontroluj, jestli jsi ho opsal/a správně, "
                "nebo se obrať na autora aplikace."
            )
            self._feedback.setStyleSheet(
                "font-size: 12px; min-height: 18px; color: #b04040; font-weight: 600;"
            )
            return

        try:
            store_key(key)
        except Exception as exc:  # noqa: BLE001
            self._feedback.setText(f"Klíč je platný, ale uložení selhalo: {exc}")
            self._feedback.setStyleSheet(
                "font-size: 12px; min-height: 18px; color: #b04040;"
            )
            return

        self.accept()

    @staticmethod
    def _divider() -> QWidget:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet("background: palette(midlight); max-height: 1px; border: none;")
        f.setFixedHeight(1)
        return f
