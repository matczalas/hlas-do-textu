"""Checkpoint přepisu — umožňuje navázat dlouhý přepis od místa přerušení.

Lokální Whisper přepis hodinové přednášky trvá minuty. Když ho uživatel zruší,
spadne mu PC, nebo zavře aplikaci, bez checkpointu začíná od nuly. Tento modul
průběžně ukládá hotové segmenty do JSON souboru v CHECKPOINTS_DIR (přežívá
restart, na rozdíl od dočasného workspace).

Identita checkpointu = fingerprint audio souboru + model + jazyk. Když se
COKOLIV z toho změní (jiný soubor, upravený soubor, jiný model), fingerprint
nesedí → checkpoint se ignoruje a přepis začne od nuly. Tím je resume bezpečný:
nikdy nenaváže na nesouvisející data.

DŮLEŽITÉ — design pro "bez bugů":
- Checkpoint je čistě ADITIVNÍ. Když cokoli selže (chybí, corrupt, mismatch),
  `load()` vrátí None a volající jede normální plný přepis. Resume nikdy
  nezpůsobí horší výsledek než žádný resume.
- Ukládá se atomicky (.tmp → replace), takže crash uprostřed zápisu nenechá
  poškozený checkpoint.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from app.config import CHECKPOINTS_DIR

# Formát checkpointu — verze pro případnou budoucí migraci.
_CHECKPOINT_VERSION = 1
# Checkpointy starší než tohle se při cleanupu smažou (osiřelé z dávných běhů).
_MAX_AGE_SECONDS = 7 * 24 * 3600  # 7 dní


@dataclass(slots=True)
class TranscriptCheckpoint:
    audio_fingerprint: str
    model_size: str
    language: str
    completed_until_sec: float
    segments: list[dict] = field(default_factory=list)  # [{start, end, text}]

    def is_useful(self, *, min_seconds: float = 30.0) -> bool:
        """Má smysl z tohoto checkpointu resumovat? (ne když jsme sotva začali)"""
        return self.completed_until_sec >= min_seconds and bool(self.segments)


def _fingerprint(audio_path: Path) -> str:
    """Stabilní otisk audio souboru: cesta + velikost + mtime.

    Nečteme obsah (mohlo by být GB) — kombinace velikosti a mtime spolehlivě
    odhalí změnu souboru. Když uživatel soubor upraví/přepíše, mtime se změní
    → jiný fingerprint → starý checkpoint se ignoruje.
    """
    audio_path = Path(audio_path)
    try:
        st = audio_path.stat()
        raw = f"{audio_path.resolve()}|{st.st_size}|{int(st.st_mtime)}"
    except OSError:
        # Soubor nedostupný — fingerprint jen z cesty (resume se stejně neaktivuje)
        raw = str(audio_path)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _checkpoint_file(fingerprint: str) -> Path:
    return CHECKPOINTS_DIR / f"{fingerprint}.json"


def load(audio_path: Path, model_size: str, language: str) -> TranscriptCheckpoint | None:
    """Načte checkpoint pro daný soubor+model+jazyk. None když neexistuje,
    je corrupt, nebo nesedí (jiný model/jazyk/soubor)."""
    fp = _fingerprint(audio_path)
    path = _checkpoint_file(fp)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Checkpoint {} nečitelný ({}), ignoruji", path.name, exc)
        return None

    if not isinstance(data, dict):
        return None
    if data.get("version") != _CHECKPOINT_VERSION:
        logger.info("Checkpoint má jinou verzi, ignoruji")
        return None
    # Model + jazyk se musí shodovat — jinak by segmenty neseděly
    if data.get("model_size") != model_size or data.get("language") != language:
        logger.info("Checkpoint je pro jiný model/jazyk, ignoruji")
        return None
    if data.get("audio_fingerprint") != fp:
        # Teoreticky nemožné (jméno souboru = fp), ale pro jistotu
        return None

    segments = data.get("segments")
    if not isinstance(segments, list):
        return None
    # Validace segmentů — každý musí mít start/end/text
    clean_segments: list[dict] = []
    for s in segments:
        if not isinstance(s, dict):
            continue
        try:
            clean_segments.append({
                "start": float(s["start"]),
                "end": float(s["end"]),
                "text": str(s["text"]),
            })
        except (KeyError, TypeError, ValueError):
            continue

    completed = data.get("completed_until_sec")
    try:
        completed = float(completed)
    except (TypeError, ValueError):
        return None

    logger.info(
        "Načten checkpoint: {} segmentů, hotovo do {:.0f}s ({})",
        len(clean_segments), completed, path.name,
    )
    return TranscriptCheckpoint(
        audio_fingerprint=fp,
        model_size=model_size,
        language=language,
        completed_until_sec=completed,
        segments=clean_segments,
    )


def save(
    audio_path: Path,
    model_size: str,
    language: str,
    segments: list[dict],
    completed_until_sec: float,
) -> None:
    """Atomicky uloží checkpoint. Selhání jen zaloguje (není fatální)."""
    try:
        CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
        fp = _fingerprint(audio_path)
        path = _checkpoint_file(fp)
        payload = {
            "version": _CHECKPOINT_VERSION,
            "audio_fingerprint": fp,
            "model_size": model_size,
            "language": language,
            "completed_until_sec": completed_until_sec,
            "saved_at": time.time(),
            "segments": segments,
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.warning("Nepodařilo se uložit checkpoint: {}", exc)


def delete(audio_path: Path, model_size: str, language: str) -> None:
    """Smaže checkpoint (po úspěšném dokončení přepisu)."""
    try:
        fp = _fingerprint(audio_path)
        _checkpoint_file(fp).unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Nepodařilo se smazat checkpoint: {}", exc)


def cleanup_old(max_age_seconds: float = _MAX_AGE_SECONDS) -> None:
    """Smaže osiřelé checkpointy starší než max_age (volá se při startu app)."""
    if not CHECKPOINTS_DIR.is_dir():
        return
    now = time.time()
    for f in CHECKPOINTS_DIR.glob("*.json"):
        try:
            if now - f.stat().st_mtime > max_age_seconds:
                f.unlink()
                logger.info("Smazán starý checkpoint: {}", f.name)
        except OSError:
            continue
