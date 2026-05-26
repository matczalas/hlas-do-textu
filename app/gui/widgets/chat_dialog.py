"""Modální dialog 'Chat s dokumentem'.

Bez perzistence — po zavření zmizí historie. Pokud uživatel klikne 'Aplikovat'
na navrženou změnu, dialog emituje signál `material_changed(StudyMaterial)`
a hlavní okno regeneruje .docx.

Layout:

    ┌────────────────────────────────────────────────┐
    │ Chat s dokumentem                       [×]    │
    │ Filozofie_2026-05-26.docx                      │
    ├────────────────────────────────────────────────┤
    │ Historie zpráv (scrollable)                    │
    │                                                │
    │  [Ty]  Stručněji, 5 bodů                       │
    │  [AI]  Hotovo, body zkráceny na 5.             │
    │        ┌──────────┐ ┌─────────┐                │
    │        │ Aplikovat │ │ Zrušit  │                │
    │        └──────────┘ └─────────┘                │
    │                                                │
    ├────────────────────────────────────────────────┤
    │ [Tvoje zpráva...]                  [Poslat]    │
    └────────────────────────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.ai.chat import ChatProposal, ChatResponse, ChatSession
from app.core.models import StudyMaterial


class _MessageBubble(QFrame):
    """Jedna zpráva v historii (user nebo AI), volitelně s tlačítky Aplikovat/Zrušit."""

    apply_clicked = Signal(object)  # ChatProposal
    cancel_clicked = Signal()

    def __init__(
        self,
        role: str,
        text: str,
        *,
        proposal: ChatProposal | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("MessageBubble")
        is_user = role == "user"

        bg = "rgba(32,92,168,0.10)" if is_user else "rgba(120,120,120,0.10)"
        border = "rgba(32,92,168,0.30)" if is_user else "rgba(120,120,120,0.30)"
        self.setStyleSheet(
            f"QFrame#MessageBubble {{ background: {bg}; "
            f"border: 1px solid {border}; border-radius: 10px; padding: 4px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        label = QLabel("Ty" if is_user else "Asistent")
        label.setStyleSheet(
            "font-size: 11px; font-weight: 600; "
            f"color: {'#205ca8' if is_user else '#6a6a6a'};"
        )
        layout.addWidget(label)

        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet("font-size: 13px; color: palette(text);")
        layout.addWidget(body)

        if proposal is not None:
            btn_row = QHBoxLayout()
            btn_row.setSpacing(8)
            btn_row.setContentsMargins(0, 4, 0, 0)

            apply_btn = QPushButton("Aplikovat změnu")
            apply_btn.setObjectName("Primary")
            apply_btn.setMinimumHeight(30)
            apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            apply_btn.setStyleSheet(
                "QPushButton#Primary { background: #205ca8; color: white; "
                "border: none; border-radius: 7px; padding: 4px 12px; "
                "font-weight: 600; font-size: 12px; }"
                "QPushButton#Primary:hover { background: #1a4d8f; }"
                "QPushButton#Primary:disabled { background: #8a9fb8; }"
            )
            apply_btn.clicked.connect(lambda: self._on_apply(proposal, apply_btn, cancel_btn))
            btn_row.addWidget(apply_btn)

            cancel_btn = QPushButton("Zrušit")
            cancel_btn.setMinimumHeight(30)
            cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cancel_btn.clicked.connect(lambda: self._on_cancel(apply_btn, cancel_btn))
            btn_row.addWidget(cancel_btn)

            btn_row.addStretch(1)
            layout.addLayout(btn_row)

    def _on_apply(self, proposal: ChatProposal, apply_btn: QPushButton, cancel_btn: QPushButton) -> None:
        apply_btn.setEnabled(False)
        cancel_btn.setEnabled(False)
        apply_btn.setText("Aplikováno ✓")
        self.apply_clicked.emit(proposal)

    def _on_cancel(self, apply_btn: QPushButton, cancel_btn: QPushButton) -> None:
        apply_btn.setEnabled(False)
        cancel_btn.setEnabled(False)
        cancel_btn.setText("Zrušeno")
        self.cancel_clicked.emit()


class ChatDialog(QDialog):
    """Hlavní dialog pro chat s dokumentem."""

    material_changed = Signal(object)  # StudyMaterial — caller regeneruje .docx

    def __init__(
        self,
        session: ChatSession,
        document_path: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._document_path = document_path
        self._chat_worker = None  # importovat až tady, ať dialog jde použít z testu
        self._latest_material: StudyMaterial = session.current_material

        self.setWindowTitle("Chat s dokumentem")
        self.setMinimumSize(720, 600)

        self._build_ui()

    def _build_ui(self) -> None:
        from app.gui.workers.chat_worker import ChatWorker

        self._chat_worker = ChatWorker(self)
        self._chat_worker.finished_ok.connect(self._on_response_ok)
        self._chat_worker.finished_error.connect(self._on_response_error)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        # Hlavička s názvem dokumentu
        header = QLabel(f"Pracuji s: <b>{self._document_path.name}</b>")
        header.setStyleSheet("font-size: 13px; color: palette(text);")
        root.addWidget(header)

        hint = QLabel(
            "Napiš, co změnit nebo doplnit — třeba „Stručněji, 5 bodů\", "
            "„Přidej otázky k procvičení\", „Vysvětli pojem fenomenologie\"."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid); font-size: 12px;")
        root.addWidget(hint)

        # Scrollable historie
        self._messages_layout = QVBoxLayout()
        self._messages_layout.setSpacing(8)
        self._messages_layout.addStretch(1)

        messages_container = QWidget()
        messages_container.setLayout(self._messages_layout)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(messages_container)
        self._scroll.setStyleSheet(
            "QScrollArea { border: 1px solid palette(midlight); border-radius: 8px; "
            "background: palette(base); }"
        )
        root.addWidget(self._scroll, 1)

        # Vstupní pole + Poslat
        self._input = QPlainTextEdit()
        self._input.setMinimumHeight(60)
        self._input.setMaximumHeight(120)
        self._input.setPlaceholderText("Tvoje zpráva (Ctrl+Enter pošle)…")
        root.addWidget(self._input)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self._status = QLabel("")
        self._status.setStyleSheet("color: palette(mid); font-size: 12px;")
        btn_row.addWidget(self._status)

        self._send_btn = QPushButton("Poslat")
        self._send_btn.setObjectName("Primary")
        self._send_btn.setMinimumHeight(34)
        self._send_btn.setMinimumWidth(120)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setStyleSheet(
            "QPushButton#Primary { background: #205ca8; color: white; "
            "border: none; border-radius: 8px; padding: 6px 16px; "
            "font-weight: 600; font-size: 13px; }"
            "QPushButton#Primary:hover { background: #1a4d8f; }"
            "QPushButton#Primary:disabled { background: #8a9fb8; }"
        )
        self._send_btn.clicked.connect(self._on_send)
        btn_row.addWidget(self._send_btn)

        close_btn = QPushButton("Zavřít")
        close_btn.setMinimumHeight(34)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        # Klávesnice Ctrl+Enter pošle zprávu
        send_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        send_shortcut.activated.connect(self._on_send)
        send_shortcut2 = QShortcut(QKeySequence("Ctrl+Enter"), self)
        send_shortcut2.activated.connect(self._on_send)

    def _on_send(self) -> None:
        if self._chat_worker is None or self._chat_worker.is_running():
            return
        text = self._input.toPlainText().strip()
        if not text:
            return

        self._append_message("user", text)
        self._input.clear()
        self._send_btn.setEnabled(False)
        self._send_btn.setText("Posílám…")
        self._status.setText("Asistent přemýšlí…")

        try:
            self._chat_worker.send(self._session, text)
        except Exception as exc:  # noqa: BLE001
            self._on_response_error(str(exc))

    def _on_response_ok(self, response: ChatResponse) -> None:
        self._send_btn.setEnabled(True)
        self._send_btn.setText("Poslat")
        self._status.setText("")
        self._append_message(
            "assistant",
            response.text,
            proposal=response.proposal,
        )

    def _on_response_error(self, message: str) -> None:
        self._send_btn.setEnabled(True)
        self._send_btn.setText("Poslat")
        self._status.setText(f"Chyba: {message}")
        self._append_message(
            "assistant",
            f"⚠ Nepodařilo se získat odpověď: {message}",
        )

    def _append_message(
        self,
        role: str,
        text: str,
        *,
        proposal: ChatProposal | None = None,
    ) -> None:
        bubble = _MessageBubble(role, text, proposal=proposal)
        if proposal is not None:
            bubble.apply_clicked.connect(self._on_apply_proposal)
        # Vložíme PŘED addStretch(1), který drží zprávy nahoře
        self._messages_layout.insertWidget(self._messages_layout.count() - 1, bubble)
        # Scroll na konec
        scroll_bar = self._scroll.verticalScrollBar()
        if scroll_bar is not None:
            scroll_bar.setValue(scroll_bar.maximum())

    def _on_apply_proposal(self, proposal: ChatProposal) -> None:
        self._session.apply_proposal(proposal)
        self._latest_material = proposal.updated_material
        self.material_changed.emit(proposal.updated_material)
        self._status.setText("✓ Změna aplikována, .docx se přegeneruje.")

    def latest_material(self) -> StudyMaterial:
        return self._latest_material

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Pokud běží request, počkáme až doběhne — jinak by worker thread
        emitoval signál na zničený dialog a aplikace by spadla.

        Disconnect signálů PŘED čekáním zamezí volání slotů (které sahají na
        widgets v destrukci). Po wait() je už OK destrukci dokončit.
        """
        if self._chat_worker is not None and self._chat_worker.is_running():
            try:
                self._chat_worker.finished_ok.disconnect()
                self._chat_worker.finished_error.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._chat_worker.stop_and_wait(timeout_ms=3000)
        super().closeEvent(event)

    def reject(self) -> None:  # type: ignore[override]
        # `reject` se volá při Esc / [×]. Stejný cleanup.
        if self._chat_worker is not None and self._chat_worker.is_running():
            try:
                self._chat_worker.finished_ok.disconnect()
                self._chat_worker.finished_error.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._chat_worker.stop_and_wait(timeout_ms=3000)
        super().reject()
