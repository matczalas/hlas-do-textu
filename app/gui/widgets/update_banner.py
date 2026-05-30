"""Update banner — nenápadný proužek nahoře v hlavním okně.

Tří stavy:
1. Hidden (default) — když není update
2. Available — 'Nová verze X.Y.Z → Aktualizovat'
3. Downloading — progress bar s procenty
4. Ready — 'Restartovat a aktualizovat'
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QWidget,
)

from app.gui.styles import tokens


class UpdateBanner(QFrame):
    """Proužek nad hlavním obsahem. Default skrytý, ukazuje se jen při update."""

    # Emituje když uživatel klikne 'Aktualizovat'
    update_requested = Signal()
    # Emituje když uživatel klikne 'Restartovat'
    restart_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        accent = tokens.accent()
        accent_strong = tokens.accent_strong()
        soft_10 = tokens.accent_soft(0.10)
        soft_30 = tokens.accent_soft(0.30)
        soft_40 = tokens.accent_soft(0.40)

        self.setObjectName("UpdateBanner")
        self.setStyleSheet(
            f"QFrame#UpdateBanner {{ background: {soft_10}; "
            f"border: 1px solid {soft_30}; border-radius: 10px; }}"
        )
        self.setFixedHeight(56)
        self.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 12, 8)
        layout.setSpacing(12)

        self._icon = QLabel("✨")
        self._icon.setStyleSheet("font-size: 18px;")
        layout.addWidget(self._icon)

        self._message = QLabel("")
        self._message.setStyleSheet(
            f"color: {accent}; font-size: 13px; font-weight: 500;"
        )
        self._message.setWordWrap(False)
        layout.addWidget(self._message, 1)

        self._progress = QProgressBar()
        self._progress.setFixedWidth(160)
        self._progress.setTextVisible(True)
        self._progress.setRange(0, 100)
        self._progress.setStyleSheet(
            f"QProgressBar {{ border: 1px solid {soft_40}; border-radius: 6px; "
            "background: rgba(255,255,255,0.5); text-align: center; font-size: 11px; }"
            f"QProgressBar::chunk {{ background: {accent}; border-radius: 5px; }}"
        )
        self._progress.hide()
        layout.addWidget(self._progress)

        self._action_btn = QPushButton("Aktualizovat")
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.setMinimumHeight(34)
        self._action_btn.setStyleSheet(
            f"QPushButton {{ background: {accent}; color: white; border: none; "
            "border-radius: 8px; padding: 6px 16px; font-weight: 600; font-size: 12.5px; }}"
            f"QPushButton:hover {{ background: {accent_strong}; }}"
            "QPushButton:disabled { background: #8a9fb8; color: rgba(255,255,255,150); }"
        )
        self._action_btn.clicked.connect(self._on_action_clicked)
        layout.addWidget(self._action_btn)

        self._state: str = "hidden"  # hidden | available | downloading | ready

    # ------ Public API ------

    def show_available(self, version: str) -> None:
        self._state = "available"
        self._icon.setText("✨")
        self._message.setText(f"Nová verze {version} je k dispozici")
        self._progress.hide()
        self._action_btn.setText("Aktualizovat")
        self._action_btn.setEnabled(True)
        self.show()

    def show_downloading(self) -> None:
        self._state = "downloading"
        self._icon.setText("⬇")
        self._message.setText("Stahuji aktualizaci…")
        self._progress.setValue(0)
        self._progress.show()
        self._action_btn.setEnabled(False)
        self._action_btn.setText("Stahuji…")
        self.show()

    def update_progress(self, downloaded: int, total: int) -> None:
        if total <= 0:
            return
        pct = int(downloaded * 100 / total)
        self._progress.setValue(pct)
        mb_down = downloaded / 1024 / 1024
        mb_total = total / 1024 / 1024
        self._message.setText(
            f"Stahuji aktualizaci… ({mb_down:.0f} / {mb_total:.0f} MB)"
        )

    def show_ready(self) -> None:
        self._state = "ready"
        self._icon.setText("✅")
        self._message.setText("Aktualizace stažena — restartuj pro instalaci")
        self._progress.hide()
        self._action_btn.setEnabled(True)
        self._action_btn.setText("Restartovat a aktualizovat")
        self.show()

    def show_installing(self) -> None:
        self._state = "installing"
        self._icon.setText("⏳")
        self._message.setText("Spouštím instalátor — aplikace se za chvíli ukončí…")
        self._progress.hide()
        self._action_btn.setEnabled(False)
        self._action_btn.setText("Spouštím…")
        self.show()

    def show_macos_manual(self) -> None:
        """macOS: DMG otevřeno, čeká se na ruční přetažení uživatelem."""
        self._state = "macos_manual"
        self._icon.setText("📦")
        self._message.setText("Přetáhni novou verzi do Aplikací a restartuj appku")
        self._progress.hide()
        self._action_btn.setEnabled(False)
        self._action_btn.setText("Čeká na tebe…")
        self.show()

    def show_error(self, message: str) -> None:
        self._state = "available"  # zpět na available pro retry
        self._icon.setText("⚠")
        self._message.setText(f"Aktualizace selhala: {message[:80]}")
        self._progress.hide()
        self._action_btn.setEnabled(True)
        self._action_btn.setText("Zkusit znovu")
        self.show()

    def hide_banner(self) -> None:
        self._state = "hidden"
        self.hide()

    # ------ Internal ------

    def _on_action_clicked(self) -> None:
        if self._state == "available":
            self.update_requested.emit()
        elif self._state == "ready":
            self.restart_requested.emit()
