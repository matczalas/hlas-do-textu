"""Chat session pro iterativní úpravu studijního materiálu.

Bez perzistence — historie žije jen po dobu otevřeného dialogu. Po zavření
zapomeneme všechno. Pokud uživatel "Aplikuje" navrženou změnu, regenerujeme
`.docx` v hlavním okně.

Architektura volně:

    ChatSession                                  ┌─────────────────┐
    ├─ transcripts (immutable)                   │   AIRouter      │
    ├─ slides (immutable)                        │ (Gemini Free →  │
    ├─ current_material (mutable po Apply)       │  Ollama lokálně)│
    ├─ history: list[ChatMessage]                └─────────────────┘
    └─ send(user_message) → ChatResponse              ↑
                                                      │
              build_chat_prompt(...)  ──────────────  │

Klíčové: full transcript + current material posíláme **v každé zprávě**
(Gemini má 1M kontext, takže to zvládne). Tím nepotřebujeme udržovat
server-side stav.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal

from loguru import logger

from app.core.ai.parsing import parse_sections, populate_legacy_aliases
from app.core.ai.router import AIRouter
from app.core.models import SlideText, StudyMaterial, StudySection, Transcript

# ---------------------------------------------------------------------------
# Datové struktury
# ---------------------------------------------------------------------------

Role = Literal["user", "assistant"]


@dataclass(slots=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(slots=True)
class ChatProposal:
    """Když AI navrhuje úpravu dokumentu.

    `summary` je 1-věta vysvětlení, co se změní (zobrazí se uživateli).
    `updated_material` je kompletní nová verze StudyMaterial — neaplikuje se
    automaticky, uživatel musí kliknout "Aplikovat".
    """

    summary: str
    updated_material: StudyMaterial


@dataclass(slots=True)
class ChatResponse:
    """Odpověď AI. Buď jen text (info), nebo text + návrh změny."""

    text: str
    proposal: ChatProposal | None = None


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

CHAT_SYSTEM_PROMPT = (
    "Jsi asistent, který pomáhá uživateli upravovat strukturovaný materiál "
    "(studijní zápis, zápis ze schůzky, otázky ke zkoušení, reflexi hodiny). "
    "V každé zprávě máš plný přepis zdroje, slidy (pokud byly) a aktuální "
    "verzi materiálu rozdělenou do pojmenovaných sekcí.\n\n"
    "Materiál má strukturu:\n"
    '  - "title": název materiálu\n'
    '  - "topic": téma (1-2 slova)\n'
    '  - "sections": pole sekcí, každá má "title", "kind" a "items"\n\n'
    "Možné hodnoty kind a tvary items:\n"
    '  - "bullets"     → items = ["řádek 1", "řádek 2", ...]\n'
    '  - "paragraph"   → items = ["odstavec 1", "odstavec 2", ...]\n'
    '  - "definitions" → items = [["pojem", "definice"], ...]\n'
    '  - "qa"          → items = [["otázka", "vzorová odpověď"], ...]\n'
    '  - "key_value"   → items = [["klíč", "hodnota"], ...]\n\n'
    "Odpovídej dvěma způsoby:\n\n"
    "1) **Jen text** — když se uživatel ptá nebo diskutuje. Žádný JSON, jen "
    "normální česká věta(y).\n\n"
    "2) **Návrh změny dokumentu** — když uživatel žádá úpravu („přidej sekci“, "
    "„zkrať body“, „doplň otázky“). Vrať odpověď VÝHRADNĚ ve formátu:\n\n"
    "```json\n"
    "{\n"
    '  "summary": "Co konkrétně se změnilo (1 česká věta).",\n'
    '  "updated_material": {\n'
    '    "title": "...",\n'
    '    "topic": "...",\n'
    '    "sections": [\n'
    '      { "title": "...", "kind": "bullets", "items": ["..."] }\n'
    "    ]\n"
    "  }\n"
    "}\n"
    "```\n\n"
    "Vrať **buď text NEBO JSON**, nikdy obojí naráz. JSON musí být validní, "
    "jinak ho uživatel neuvidí. Drž se přepisu, nevymýšlej si fakta. "
    "Píšeš česky s diakritikou, stručně a věcně."
)


# ---------------------------------------------------------------------------
# ChatSession — držitel kontextu
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ChatSession:
    router: AIRouter
    transcripts: list[Transcript]
    slides: list[SlideText]
    current_material: StudyMaterial
    history: list[ChatMessage] = field(default_factory=list)

    def send(self, user_message: str) -> ChatResponse:
        """Pošle zprávu AI, vrátí ChatResponse. Aktualizuje history.

        Pozn.: `current_material` se neaplikuje automaticky — aplikování dělá
        caller (po uživatelově "Aplikovat") přes `apply_proposal()`.

        Pokud router vyhodí chybu, history je vrácena do původního stavu,
        ať další volání nezačíná s osamělou user zprávou bez odpovědi.
        """
        if not user_message.strip():
            raise ValueError("Prázdná zpráva")

        user_msg = ChatMessage(role="user", content=user_message)
        self.history.append(user_msg)

        prompt = build_chat_prompt(
            user_message=user_message,
            history=self.history[:-1],  # bez aktuální (je už v promptu)
            transcripts=self.transcripts,
            slides=self.slides,
            current_material=self.current_material,
        )

        try:
            raw = self.router.generate_with_failover(prompt, system=CHAT_SYSTEM_PROMPT)
        except Exception:
            # Rollback user zprávy, ať příští volání nemá nekonzistentní stav
            if self.history and self.history[-1] is user_msg:
                self.history.pop()
            raise

        response = parse_chat_response(raw, fallback_material=self.current_material)
        self.history.append(ChatMessage(role="assistant", content=response.text))
        return response

    def apply_proposal(self, proposal: ChatProposal) -> None:
        """Po klik 'Aplikovat' nahradí current_material novým. Další zprávy budou
        pracovat s aktualizovaným materiálem."""
        self.current_material = proposal.updated_material
        logger.info("Chat: applied proposal — {}", proposal.summary)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def build_chat_prompt(
    *,
    user_message: str,
    history: list[ChatMessage],
    transcripts: list[Transcript],
    slides: list[SlideText],
    current_material: StudyMaterial,
) -> str:
    transcript_text = "\n\n".join(
        f"=== {tr.source_label} ===\n{tr.text}" for tr in transcripts
    ).strip() or "(žádný přepis)"
    slides_text = "\n\n".join(
        f"=== {s.source_label} ({s.slide_count} slidů) ===\n{s.text}" for s in slides
    ).strip()

    material_json = json.dumps(
        _material_to_payload(current_material),
        ensure_ascii=False,
        indent=2,
    )

    history_text = ""
    if history:
        lines: list[str] = []
        for msg in history[-10:]:  # posledních 10 zpráv jako kontext
            label = "Uživatelka" if msg.role == "user" else "Ty"
            lines.append(f"{label}: {msg.content}")
        history_text = "\n\nDosavadní konverzace:\n" + "\n".join(lines)

    parts = [
        "AKTUÁLNÍ STUDIJNÍ MATERIÁL (JSON):",
        "```json",
        material_json,
        "```",
        "",
        "PŘEPIS PŘEDNÁŠKY:",
        '"""',
        transcript_text,
        '"""',
    ]
    if slides_text:
        parts += ["", "SLIDY Z PREZENTACE:", '"""', slides_text, '"""']
    if history_text:
        parts.append(history_text)
    parts += ["", "NOVÝ POŽADAVEK UŽIVATELKY:", user_message]
    return "\n".join(parts)


def _material_to_payload(material: StudyMaterial) -> dict:
    """Seriálizuje material pro vložení do promptu — preferuje sections."""
    sections_payload: list[dict] = []
    for section in material.iter_sections():
        sections_payload.append(
            {
                "title": section.title,
                "kind": section.kind,
                "items": [list(it) if isinstance(it, tuple) else it for it in section.items],
            }
        )
    return {
        "title": material.title,
        "topic": material.topic,
        "sections": sections_payload,
    }


# ---------------------------------------------------------------------------
# Parsování odpovědi
# ---------------------------------------------------------------------------


def parse_chat_response(raw: str, *, fallback_material: StudyMaterial) -> ChatResponse:
    """Z raw AI odpovědi extrahuje text + případnou proposal.

    Strategie:
    1) Najít JSON blok (s `summary` + `updated_material`)
    2) Pokud existuje, zachovat i případný text PŘED JSON (preamble) —
       modely často píší "Tady je úprava:" před JSON blokem
    3) Pokud JSON není, celý raw text je čistá odpověď
    """
    raw = raw.strip()
    if not raw:
        return ChatResponse(text="(prázdná odpověď)")

    extracted = _extract_proposal_json(raw)
    if extracted is None:
        return ChatResponse(text=raw)

    payload, preamble = extracted

    summary = str(payload.get("summary") or "").strip()
    updated = payload.get("updated_material")
    if not isinstance(updated, dict):
        logger.warning("Chat proposal bez updated_material: {}", raw[:200])
        return ChatResponse(text=raw)

    try:
        new_material = _parse_material(updated, fallback=fallback_material)
    except (ValueError, TypeError) as exc:
        logger.warning("Chat proposal: nevalidní material ({}): {}", exc, raw[:200])
        return ChatResponse(text=raw)

    # Sestavíme zobrazený text: preamble (text před JSON) + summary
    pieces: list[str] = []
    if preamble:
        pieces.append(preamble.strip())
    if summary:
        pieces.append(summary)
    if not pieces:
        pieces.append("Návrh úpravy dokumentu připraven.")
    response_text = "\n\n".join(pieces)

    return ChatResponse(
        text=response_text,
        proposal=ChatProposal(summary=summary or response_text, updated_material=new_material),
    )


def _extract_proposal_json(raw: str):
    """Najde JSON blok v odpovědi, který obsahuje `updated_material`.

    Vrací tuple `(payload, preamble)` nebo None.
    - payload: parsovaný dict s `updated_material`
    - preamble: text PŘED JSON blokem (nebo prázdný řetězec)
    """
    candidates: list[tuple[str, str]] = []  # (json_str, preamble)

    # 1) Markdown ```json ... ``` blok přednostně
    match = re.search(r"```(?:json)?\s*(\{.+?\})\s*```", raw, re.DOTALL)
    if match:
        preamble = raw[: match.start()].strip()
        candidates.append((match.group(1), preamble))

    # 2) Celý raw jako JSON (žádný preamble)
    candidates.append((raw, ""))

    # 3) Greedy {...} fallback
    first = raw.find("{")
    last = raw.rfind("}")
    if first >= 0 and last > first:
        preamble = raw[:first].strip()
        candidates.append((raw[first : last + 1], preamble))

    for json_str, preamble in candidates:
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "updated_material" in data:
            return data, preamble
    return None


def _parse_material(data: dict, *, fallback: StudyMaterial) -> StudyMaterial:
    """Z dict (jak vrátil model) vyrobí StudyMaterial.

    Akceptuje nový sekce-aware formát i starý plochý formát s bullets/terms.
    Tolerantní k chybějícím polím.
    """
    title = str(data.get("title") or fallback.title or "Studijní materiál").strip()
    topic = str(data.get("topic") or fallback.topic or "").strip()

    # Nový sekce formát?
    sections_raw = data.get("sections")
    if isinstance(sections_raw, list) and sections_raw:
        sections = parse_sections(sections_raw)
        material = StudyMaterial(title=title, topic=topic, sections=sections)
        populate_legacy_aliases(material)
        return material

    # Starý plochý formát (zachováno kvůli backward compat — model může
    # odpovědět starým schématem, zejména menší lokální modely).
    bullets_raw = data.get("bullets") or []
    bullets = [str(b).strip() for b in bullets_raw if str(b).strip()]

    terms_raw = data.get("terms") or []
    terms: list[tuple[str, str]] = []
    for item in terms_raw:
        if isinstance(item, list | tuple) and len(item) >= 2:
            terms.append((str(item[0]).strip(), str(item[1]).strip()))
        elif isinstance(item, dict):
            term = str(item.get("term") or item.get("pojem") or "").strip()
            definition = str(
                item.get("definition") or item.get("definice") or item.get("desc") or ""
            ).strip()
            if term:
                terms.append((term, definition))

    examples_raw = data.get("examples") or []
    examples = [str(e).strip() for e in examples_raw if str(e).strip()]

    further_raw = data.get("further_study") or []
    further = [str(f).strip() for f in further_raw if str(f).strip()]

    quiz_raw = data.get("quiz_questions") or []
    quiz = [str(q).strip() for q in quiz_raw if str(q).strip()]
    # Pokud chat quiz nevrátil, zachováme původní (uživatel jen upravoval body)
    if not quiz:
        quiz = list(fallback.quiz_questions)

    return StudyMaterial(
        title=title,
        topic=topic,
        bullets=bullets,
        terms=terms,
        examples=examples,
        further_study=further,
        quiz_questions=quiz,
    )


# Re-export pro testy
__all__ = [
    "ChatMessage",
    "ChatProposal",
    "ChatResponse",
    "ChatSession",
    "StudySection",
    "build_chat_prompt",
    "parse_chat_response",
]
