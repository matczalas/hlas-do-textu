"""Sledovaná složka — jádro bez Qt (GUI volá přes QTimer).

Princip: periodický sken složky. Soubor je "připravený", když má podporovanou
příponu, mezi dvěma skeny se nezměnila velikost ani mtime (= dokopírovaný,
diktafon/AirDrop/sync ho už nezapisuje) a ještě nebyl zpracovaný.

Zpracované soubory se evidují v JSON state souboru (cesta + velikost + mtime),
takže přežijí restart aplikace. Soubor se značí jako zpracovaný v okamžiku
PŘEDÁNÍ do pipeline (ne po dokončení) — vadná nahrávka tak nezpůsobí
nekonečnou smyčku pokusů.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from app.config import AUDIO_VIDEO_EXTENSIONS, USER_DATA_DIR

WATCH_STATE_FILE: Path = USER_DATA_DIR / "watch_state.json"


@dataclass(slots=True)
class WatchScanner:
    """Drží stav mezi skeny: co je zpracované (persistované) a co se sleduje.

    `pending` žije jen v paměti — stabilita souboru se měří mezi dvěma
    po sobě jdoucími skeny běžící aplikace.
    """

    state_path: Path = WATCH_STATE_FILE
    processed: dict[str, list] = field(default_factory=dict)  # path -> [size, mtime]
    pending: dict[str, tuple[int, float]] = field(default_factory=dict)

    # ------ Persistence ------

    def load(self) -> None:
        try:
            if self.state_path.is_file():
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.processed = {
                        str(k): list(v)
                        for k, v in data.items()
                        if isinstance(v, (list, tuple)) and len(v) == 2
                    }
        except (OSError, ValueError) as exc:
            logger.warning("Watch state nelze načíst ({}) — začínám s čistým", exc)
            self.processed = {}

    def save(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(self.processed, ensure_ascii=False), encoding="utf-8"
            )
            tmp.replace(self.state_path)
        except OSError as exc:
            logger.warning("Watch state nelze uložit: {}", exc)

    # ------ Scan ------

    def scan(self, folder: Path) -> list[Path]:
        """Jeden průchod složkou. Vrátí soubory připravené ke zpracování.

        Soubor je připravený, když byl viděn v minulém skenu se stejnou
        velikostí a mtime (stabilní) a není ve `processed` se stejnou
        signaturou. Změněný soubor (nová velikost/mtime) se zpracuje znovu —
        uživatel mohl nahrávku přepsat novou verzí.
        """
        folder = Path(folder)
        if not folder.is_dir():
            return []

        ready: list[Path] = []
        seen_now: dict[str, tuple[int, float]] = {}

        try:
            entries = sorted(folder.iterdir())
        except OSError as exc:
            logger.warning("Watch: složku nelze číst: {}", exc)
            return []

        for p in entries:
            try:
                if not p.is_file() or p.suffix.lower() not in AUDIO_VIDEO_EXTENSIONS:
                    continue
                stat = p.stat()
            except OSError:
                continue  # soubor zmizel mezi iterdir a stat

            sig = (stat.st_size, stat.st_mtime)
            key = str(p)
            seen_now[key] = sig

            done = self.processed.get(key)
            if done is not None and tuple(done) == sig:
                continue  # už zpracováno v této podobě

            previous = self.pending.get(key)
            if previous == sig and stat.st_size > 0:
                ready.append(p)
            # jinak: nový/změněný soubor — počká na další sken (stabilita)

        self.pending = seen_now
        return ready

    def mark_processed(self, path: Path) -> None:
        """Označí soubor jako zpracovaný (volat při předání do pipeline) a uloží."""
        try:
            stat = Path(path).stat()
            self.processed[str(path)] = [stat.st_size, stat.st_mtime]
        except OSError:
            self.processed[str(path)] = [0, 0.0]
        self.save()
