# API Constraints — co MUSÍ zůstat zachované

Toto jsou veřejné kontrakty mezi `gui/` a zbytkem aplikace. Pokud změníš
jména signálů/slotů/veřejných metod, **rozbije se to a buildy začnou padat**.

## `app/gui/widgets/file_drop_zone.py` — class `FileDropZone(QFrame)`

```python
sources_added = Signal(list)          # list[SourceFile]
def set_last_dir(self, path: str) -> None: ...
@property
def last_dir(self) -> str: ...
```

## `app/gui/widgets/source_table.py` — class `SourceTable(QTableWidget)`

```python
files_changed = Signal()
def add_sources(self, sources: list[SourceFile]) -> None: ...
def sources(self) -> list[SourceFile]: ...
def clear_all(self) -> None: ...
```

## `app/gui/widgets/prompt_editor.py` — class `PromptEditor(QGroupBox)`

```python
def text(self) -> str: ...
def set_text(self, value: str) -> None: ...
```

## `app/gui/widgets/progress_panel.py` — class `ProgressPanel(QGroupBox)`

```python
@property
def cancel_button(self) -> QPushButton: ...
def set_busy(self, busy: bool) -> None: ...
def update(self, label: str, fraction: float) -> None: ...
def reset(self) -> None: ...
def append_message(self, msg: str) -> None: ...
def append_transcript_line(self, seconds: float, label: str, text: str) -> None: ...
```

## `app/gui/widgets/ollama_status.py` — class `StatusBar(QWidget)`

```python
def refresh(self, gemini_api_key: str | None) -> None: ...
```

## `app/gui/widgets/empty_state.py` — class `EmptyStateWidget(QWidget)`

Žádné veřejné API kromě `__init__(parent)`. Můžeš úplně přepsat.

## `app/gui/widgets/settings_dialog.py` — class `SettingsDialog(QDialog)`

```python
def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None: ...
def accept(self) -> None:  # uloží do settings + keyring; už hotovo
```

## `app/gui/widgets/first_run_dialog.py` — class `FirstRunDialog(QDialog)`

```python
def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None: ...
def accept(self) -> None: ...
```

## `app/gui/main_window.py` — class `MainWindow(QMainWindow)`

V `MainWindow.__init__` se očekávají tyto instance attributes (workers se na ně připojí):
- `self._drop_zone` — `FileDropZone`
- `self._table` — `SourceTable`
- `self._prompt_editor` — `PromptEditor`
- `self._progress` — `ProgressPanel`
- `self._status_bar` — `StatusBar`
- `self._source_stack` — `QStackedWidget` (přepínání mezi empty state a tabulkou)
- `self._empty_state` — `EmptyStateWidget`
- `self._run_full_btn` — `QPushButton` (primární CTA, modrý)
- `self._run_transcribe_btn` — `QPushButton` (sekundární)
- `self._run_btn` — alias na `self._run_full_btn` (backward compat)
- `self._output_value` — `QLabel` zobrazující cestu

A tyto metody (volané z workers / menu actions):
- `_post_show_init()` — first-run dialog + model download offer
- `_change_output_dir()` — file dialog pro output dir
- `_open_settings()` — settings dialog
- `_run_pipeline(mode: JobMode)` — start pipeline workeru
- `_regenerate_from_existing()` — regenerace z .txt přepisu
- `_open_file(path)` — otevře soubor v default app
- `closeEvent(event)` — cleanup + persist

## Imports které smíš použít

```python
from PySide6.QtCore import ...       # ANO
from PySide6.QtGui import ...        # ANO
from PySide6.QtWidgets import ...    # ANO
from loguru import logger            # ANO
from app.config import ...           # ANO (jen konstanty)
from app.core.models import ...      # ANO (dataclasses)
from app.settings import ...         # ANO
```

**NIKDY** neimportuj nic z `app.core.ai/`, `app.core.transcribe`, `app.core.pipeline` atd. — to je business logika a leze do GUI jen přes workers, kteří už existují.
