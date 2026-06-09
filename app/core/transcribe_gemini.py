"""Speech-to-text přes Google Gemini Audio API.

Alternativa k `transcribe.py` (lokální faster-whisper). Pro Windows uživatele bez
GPU je řádově rychlejší — hodinová přednáška ~30-60 s místo desítek minut.

Strategie nahrávání:
- audio do 9 MB: inline `Part.from_bytes` (jeden request)
- audio nad 9 MB: File API (`client.files.upload`) — tam končí limit kontextu
  až 9.5 h audia v jednom prompt

Výstup: parsed JSON segments s časovými značkami. Gemini se vyzve, aby vracel
strukturu `{"segments": [{"start_sec": 0, "end_sec": 5.2, "text": "..."}]}` —
tím získáme TranscriptSegment list pro stejný `Transcript` formát jako Whisper.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from app.config import DEFAULT_GEMINI_MODEL, DEFAULT_LANGUAGE
from app.core.ai.base import AIAuthError, AIError, AINetworkError, AIRateLimitError
from app.core.models import Transcript, TranscriptSegment

# Hranice pro inline upload (Gemini limit pro inline data ~20 MB, ale request
# má vlastní overhead — držíme se konzervativně níž).
_INLINE_MAX_BYTES: int = 9 * 1024 * 1024  # 9 MB

# Max čas, jak dlouho čekat na File API processing (uploaded file musí být ACTIVE
# než ho můžeme použít v generate_content).
_FILE_PROCESSING_TIMEOUT_SEC: float = 180.0


class TranscribeGeminiCancelled(RuntimeError):
    """Vyhozeno když cancel_event proběhne během uploadu nebo čekání."""


# Mime type podle přípony — Gemini Audio podporuje wav/mp3/aac/ogg/flac.
_MIME_BY_EXT: dict[str, str] = {
    ".wav": "audio/wav",
    ".mp3": "audio/mp3",
    ".mpeg": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
}


def _detect_mime(path: Path) -> str:
    return _MIME_BY_EXT.get(path.suffix.lower(), "audio/wav")


_PROMPT_TEMPLATE = """Přepiš následující {lang_label} audio nahrávku přesně podle toho, co je řečeno.

Pravidla:
- Vrať JSON ve formátu: {{"segments": [{{"start_sec": float, "end_sec": float, "text": "..."}}]}}
- Každý segment ~5-15 sekund, končící na konci věty nebo přirozené pauzy.
- Nepřidávej komentáře, hlavičky, ani jiné texty mimo JSON.
- Žádné výplňové fráze typu "Tady je přepis:" — vrať jen JSON.
- Pokud zazní rozpoznatelný název / cizí slovo, ponech ho ve správném tvaru.{language_specific}
"""

# Varianta s diarizací — Gemini rozliší mluvčí a označí je "Mluvčí 1/2/...".
_PROMPT_TEMPLATE_DIARIZE = """Přepiš následující {lang_label} audio nahrávku přesně podle toho, co je řečeno, a rozliš jednotlivé mluvčí.

Pravidla:
- Vrať JSON ve formátu: {{"segments": [{{"start_sec": float, "end_sec": float, "speaker": "Mluvčí 1", "text": "..."}}]}}
- Rozpoznej, kolik je v nahrávce mluvčích, a každému přiřaď STÁLÉ označení
  "Mluvčí 1", "Mluvčí 2", … podle pořadí, v jakém se poprvé ozvali.
- Stejný člověk musí mít stejné označení v CELÉ nahrávce.
- Nový segment začni vždy, když se vystřídá mluvčí (i kratší než 5 s).
- Jinak segment ~5-15 sekund, končící na konci věty nebo přirozené pauzy.
- Nepřidávej komentáře, hlavičky, ani jiné texty mimo JSON.
- Žádné výplňové fráze typu "Tady je přepis:" — vrať jen JSON.
- Pokud zazní rozpoznatelný název / cizí slovo, ponech ho ve správném tvaru.{language_specific}
"""

_CZECH_HINT = (
    "\n- Jazyk je čeština: dbej pečlivě na diakritiku (á, č, ď, é, ě, í, ň, ó, ř, š, ť, ú, ů, ý, ž) "
    "a přirozený český slovosled."
)


def _build_prompt(language: str, diarize: bool = False) -> str:
    lang_label = {"cs": "českou", "sk": "slovenskou", "en": "anglickou"}.get(
        language.lower(), "tuto"
    )
    language_specific = _CZECH_HINT if language.lower() == "cs" else ""
    template = _PROMPT_TEMPLATE_DIARIZE if diarize else _PROMPT_TEMPLATE
    return template.format(
        lang_label=lang_label,
        language_specific=language_specific,
    )


def transcribe_audio_via_gemini(
    audio_path: Path,
    *,
    source_label: str,
    api_key: str,
    model: str = DEFAULT_GEMINI_MODEL,
    language: str = DEFAULT_LANGUAGE,
    diarize: bool = False,
    progress_cb: Callable[[float], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> Transcript:
    """Přepíše `audio_path` přes Gemini Audio API.

    Parametry:
        audio_path: cesta k audio souboru (WAV/MP3/M4A/...). Nemusí být 16 kHz mono.
        source_label: editovatelný štítek od uživatele.
        api_key: Gemini API klíč (validní).
        model: Gemini model, default z config (gemini-flash-latest).
        language: ISO kód jazyka (cs/sk/en).
        progress_cb: callback(0.0–1.0). Pseudo-progres: 0.1 upload, 0.5 čeká na response,
                     1.0 hotovo. Není to skutečný stream.
        cancel_event: pokud nastaven, vyhodí TranscribeGeminiCancelled při uploadu.

    Raises:
        AIAuthError: neplatný klíč.
        AIRateLimitError: vyčerpaná kvóta.
        AINetworkError: bez internetu.
        AIError: ostatní (např. soubor nepodporovaný formát).
    """
    if not api_key or not api_key.strip():
        raise AIAuthError("Chybí API klíč pro Gemini Audio")

    audio_path = Path(audio_path)
    if not audio_path.is_file():
        raise AIError(f"Audio nenalezeno: {audio_path}")

    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError as exc:
        raise AIError(
            "Knihovna google-genai není nainstalovaná. Spusť `pip install google-genai`."
        ) from exc

    client = genai.Client(api_key=api_key)

    _raise_if_cancelled(cancel_event)
    if progress_cb is not None:
        progress_cb(0.05)

    size_bytes = audio_path.stat().st_size
    logger.info(
        "Gemini transcribe: {} ({:.1f} MB, mime={})",
        audio_path.name,
        size_bytes / 1024 / 1024,
        _detect_mime(audio_path),
    )

    # Inline pro malé soubory, File API pro velké.
    if size_bytes <= _INLINE_MAX_BYTES:
        audio_part = _build_inline_part(audio_path, genai_types)
        uploaded_file = None
    else:
        uploaded_file = _upload_via_file_api(
            client, audio_path, cancel_event=cancel_event, progress_cb=progress_cb
        )
        audio_part = uploaded_file

    if progress_cb is not None:
        progress_cb(0.40)
    _raise_if_cancelled(cancel_event)

    prompt = _build_prompt(language, diarize=diarize)

    try:
        response = client.models.generate_content(
            model=model,
            contents=[audio_part, prompt],
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
    except Exception as exc:  # noqa: BLE001 — SDK má vlastní hierarchii
        _reraise_as_ai_error(exc)
    finally:
        # File API soubory mažeme manuálně (limit 20 GB / projekt).
        if uploaded_file is not None:
            _safe_delete_file(client, uploaded_file)

    if progress_cb is not None:
        progress_cb(0.90)

    raw = (getattr(response, "text", None) or "").strip()
    if not raw:
        raise AIError("Gemini vrátil prázdnou odpověď")

    segments, full_text, duration_sec = _parse_response(raw)
    if not segments:
        # Fallback: vrátíme jeden segment s celým textem
        logger.warning("Gemini neposlal segments, beru jen raw text")
        segments = [TranscriptSegment(start=0.0, end=0.0, text=full_text)]

    if progress_cb is not None:
        progress_cb(1.0)

    logger.info(
        "Gemini transcribe hotov: {} segmentů, ~{:.0f}s, {} znaků",
        len(segments),
        duration_sec,
        len(full_text),
    )

    return Transcript(
        source_label=source_label,
        language=language,
        duration_sec=duration_sec,
        text=full_text,
        segments=segments,
    )


# ---------------------------------------------------------------------------
# Upload paths
# ---------------------------------------------------------------------------


def _build_inline_part(audio_path: Path, genai_types) -> object:
    data = audio_path.read_bytes()
    return genai_types.Part.from_bytes(data=data, mime_type=_detect_mime(audio_path))


def _upload_via_file_api(
    client,
    audio_path: Path,
    *,
    cancel_event: threading.Event | None,
    progress_cb: Callable[[float], None] | None,
):
    """Uploadne velký soubor a počká, až ho server přepne na ACTIVE."""
    logger.info("Velký soubor — používám Gemini File API")
    try:
        uploaded = client.files.upload(
            file=str(audio_path),
            config={"mime_type": _detect_mime(audio_path)},
        )
    except Exception as exc:  # noqa: BLE001
        _reraise_as_ai_error(exc)

    if progress_cb is not None:
        progress_cb(0.20)

    # Poll na ACTIVE state.
    started = time.monotonic()
    while True:
        _raise_if_cancelled(cancel_event)
        try:
            state = getattr(getattr(uploaded, "state", None), "name", None) or str(
                getattr(uploaded, "state", "")
            )
        except Exception:  # noqa: BLE001
            state = ""

        if state.upper() == "ACTIVE":
            break
        if state.upper() == "FAILED":
            raise AIError(f"Gemini odmítl soubor: {uploaded.name}")

        if time.monotonic() - started > _FILE_PROCESSING_TIMEOUT_SEC:
            raise AIError(
                f"Gemini neaktivoval upload do {int(_FILE_PROCESSING_TIMEOUT_SEC)} s "
                f"(soubor: {audio_path.name})"
            )

        time.sleep(2.0)
        try:
            uploaded = client.files.get(name=uploaded.name)
        except Exception as exc:  # noqa: BLE001
            _reraise_as_ai_error(exc)

    return uploaded


def _safe_delete_file(client, uploaded_file) -> None:
    try:
        client.files.delete(name=uploaded_file.name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Nepodařilo se smazat upload {}: {}", uploaded_file.name, exc)


# ---------------------------------------------------------------------------
# Parsování odpovědi
# ---------------------------------------------------------------------------


def _parse_response(raw: str) -> tuple[list[TranscriptSegment], str, float]:
    """Z Gemini JSON odpovědi vytáhne segmenty + celkový text + délku.

    Tolerantní k formátu — Gemini občas přidá markdown wrapper ```json``` nebo
    pole se jmenuje `transcript` místo `segments`.
    """
    payload = _extract_json(raw)
    if not isinstance(payload, dict):
        return [], raw, 0.0

    raw_segments = (
        payload.get("segments")
        or payload.get("transcript")
        or payload.get("data")
        or []
    )
    if not isinstance(raw_segments, list):
        return [], raw, 0.0

    segments: list[TranscriptSegment] = []
    text_parts: list[str] = []
    duration = 0.0
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        start = _as_float(item.get("start_sec"), item.get("start"), item.get("from"))
        end = _as_float(item.get("end_sec"), item.get("end"), item.get("to"))
        text = (item.get("text") or item.get("content") or "").strip()
        if not text:
            continue
        speaker = str(item.get("speaker") or item.get("mluvci") or "").strip()
        effective_end = end if end > 0 else start
        segments.append(
            TranscriptSegment(start=start, end=effective_end, text=text, speaker=speaker)
        )
        text_parts.append(text)
        # Duration je nejvyšší koncový timestamp ze všech segmentů.
        # Když model vrátí jen `start_sec` (chybí `end_sec`), použijeme `start`.
        if effective_end > duration:
            duration = effective_end

    full_text = _build_full_text(segments)
    return segments, full_text, duration


def _build_full_text(segments: list[TranscriptSegment]) -> str:
    """Sestaví souvislý text. Když segmenty nesou mluvčí (diarizace), prefixuje
    každou repliku označením ("Mluvčí 1: …") na vlastním řádku — díky tomu AI
    i .txt vidí, kdo co řekl. Bez mluvčích spojí věty mezerou jako dřív.
    """
    if any(seg.speaker for seg in segments):
        lines: list[str] = []
        for seg in segments:
            if seg.speaker:
                lines.append(f"{seg.speaker}: {seg.text}")
            else:
                lines.append(seg.text)
        return "\n".join(lines).strip()
    return " ".join(seg.text for seg in segments).strip()


def _extract_json(raw: str):
    """Najde JSON v textu, který Gemini mohl obalit kódovou značkou."""
    stripped = raw.strip()
    if stripped.startswith("```"):
        # ```json\n...\n```
        match = re.search(r"```(?:json)?\s*(.+?)```", stripped, re.DOTALL)
        if match:
            stripped = match.group(1).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        # Najdi nejdelší {...} blok
        first = stripped.find("{")
        last = stripped.rfind("}")
        if first >= 0 and last > first:
            try:
                return json.loads(stripped[first : last + 1])
            except json.JSONDecodeError:
                return None
        return None


def _as_float(*candidates) -> float:
    for c in candidates:
        if c is None:
            continue
        try:
            return float(c)
        except (TypeError, ValueError):
            continue
    return 0.0


# ---------------------------------------------------------------------------
# Error & cancel helpers
# ---------------------------------------------------------------------------


def _raise_if_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise TranscribeGeminiCancelled("Přepis zrušen uživatelem")


def _reraise_as_ai_error(exc: Exception) -> None:
    """Sjednotíme SDK chyby na naši hierarchii (stejně jako gemini.py).

    Klasifikace je nutně heuristická (google-genai nemá stabilní exception
    typy pro free tier). Hledáme stringy v nižším měřítku, aby se snížila
    false-positive klasifikace nesouvisejících chyb (např. permission denied
    na lokálním filesystému):

    - Auth: výslovně zmiňující "api key" / "401" / "403" / "unauthorized"
    - Rate limit: "quota" / "rate limit" / "429" / "resource_exhausted"
    - Network: "connect" / "timeout" / "network" / "dns" / "ssl" / "503"
    """
    message = str(exc).lower()
    if any(k in message for k in ("api key", "api_key", "unauthorized", "401", "403")):
        raise AIAuthError(f"Gemini: neplatný API klíč ({exc})") from exc
    if any(k in message for k in ("quota", "rate limit", "429", "resource_exhausted")):
        raise AIRateLimitError(f"Gemini: vyčerpaný limit ({exc})") from exc
    if any(k in message for k in ("connect", "timeout", "network", "dns", "ssl", "503")):
        raise AINetworkError(f"Gemini: síťová chyba ({exc})") from exc
    raise AIError(f"Gemini Audio: {exc}") from exc


def estimate_gemini_transcribe_seconds(media_duration_sec: float) -> float:
    """Hrubý odhad času pro UI hint.

    Gemini Flash audio response time je cca 30-60 s na hodinu audia + upload.
    Pro 15min audio ~10-15 s response + ~5 s upload = ~20 s.
    """
    upload_sec = max(5.0, media_duration_sec * 0.02)  # cca 2% real-time
    response_sec = max(10.0, media_duration_sec * 0.05)  # cca 5% real-time
    return upload_sec + response_sec
