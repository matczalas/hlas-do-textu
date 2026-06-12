"""Dialog pro vytvoření kalendářové pozvánky (.ics) z termínu schůzky.

AI vrací termín jako volný text ("ve čtvrtek v 17:30 u klientů doma") — přesné
datum/čas nejde spolehlivě parsovat z češtiny, takže je potvrdí uživatel.
Text od AI ukážeme nad poli jako vodítko a vložíme do popisu události.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.integrations.calendar_export import write_ics
from app.gui.styles import tokens


class CalendarDialog(QDialog):
    """Potvrzení termínu → zapíše .ics a vrátí jeho cestu přes result_path()."""

    def __init__(
        self,
        *,
        default_summary: str,
        meeting_hint: str,
        output_dir: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Přidat do kalendáře")
        self.setMinimumWidth(460)
        self._output_dir = Path(output_dir)
        self._result_path: Path | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)

        # Vodítko od AI — co v nahrávce zaznělo o termínu
        if meeting_hint:
            hint = QLabel(f"Z nahrávky: „{meeting_hint}“")
            hint.setWordWrap(True)
            hint.setStyleSheet(
                f"background: {tokens.accent_soft(0.10)}; border-radius: 8px; "
                "padding: 10px 12px; font-size: 12.5px; color: palette(text);"
            )
            root.addWidget(hint)

        instr = QLabel("Zkontroluj a uprav datum a čas — AI je z řeči neumí určit přesně.")
        instr.setWordWrap(True)
        instr.setStyleSheet("color: palette(placeholder-text); font-size: 12px;")
        root.addWidget(instr)

        # Název události
        root.addWidget(self._label("Název události"))
        self._summary_edit = QLineEdit(default_summary)
        self._summary_edit.setMinimumHeight(34)
        root.addWidget(self._summary_edit)

        # Datum + čas — default: zítra v 9:00 (rozumný neutrální start)
        root.addWidget(self._label("Datum a čas"))
        self._dt_edit = QDateTimeEdit()
        self._dt_edit.setCalendarPopup(True)
        self._dt_edit.setDisplayFormat("d. M. yyyy  HH:mm")
        self._dt_edit.setMinimumHeight(34)
        default_start = (datetime.now() + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        self._dt_edit.setDateTime(QDateTime(default_start))
        root.addWidget(self._dt_edit)

        # Délka + místo na jednom řádku
        row = QHBoxLayout()
        row.setSpacing(12)
        dur_col = QVBoxLayout()
        dur_col.addWidget(self._label("Délka (min)"))
        self._duration = QSpinBox()
        self._duration.setRange(15, 480)
        self._duration.setSingleStep(15)
        self._duration.setValue(60)
        self._duration.setMinimumHeight(34)
        dur_col.addWidget(self._duration)
        row.addLayout(dur_col)

        loc_col = QVBoxLayout()
        loc_col.addWidget(self._label("Místo (volitelné)"))
        self._location = QLineEdit()
        self._location.setMinimumHeight(34)
        self._location.setPlaceholderText("např. kancelář, online, adresa")
        loc_col.addWidget(self._location)
        row.addLayout(loc_col, 1)
        root.addLayout(row)

        self._meeting_hint = meeting_hint

        # Tlačítka
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel = QPushButton("Zrušit")
        cancel.setMinimumHeight(36)
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        create = QPushButton("Vytvořit pozvánku")
        create.setMinimumHeight(36)
        create.setMinimumWidth(150)
        create.setCursor(Qt.CursorShape.PointingHandCursor)
        create.setDefault(True)
        accent = tokens.accent()
        create.setStyleSheet(
            "QPushButton { "
            f"background: {accent}; color: #ffffff; border: 1px solid {accent}; "
            "border-radius: 8px; padding: 7px 16px; font-weight: 600; }"
            f"QPushButton:hover {{ background: {tokens.accent_strong()}; }}"
        )
        create.clicked.connect(self._on_create)
        btn_row.addWidget(create)
        root.addLayout(btn_row)

    @staticmethod
    def _label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: palette(text);")
        return lbl

    def result_path(self) -> Path | None:
        return self._result_path

    def _on_create(self) -> None:
        summary = self._summary_edit.text().strip() or "Schůzka"
        py_dt = self._dt_edit.dateTime().toPython()
        from app.core.word_export import safe_filename_part

        fname = "Pozvanka_" + safe_filename_part(summary, fallback="schuzka", max_len=40)
        out_path = self._output_dir / f"{fname}.ics"
        try:
            self._result_path = write_ics(
                out_path,
                summary=summary,
                start=py_dt,
                duration_minutes=self._duration.value(),
                location=self._location.text().strip(),
                description=self._meeting_hint,
            )
        except OSError as exc:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Chyba", f"Nepodařilo se vytvořit pozvánku: {exc}")
            return
        self.accept()
