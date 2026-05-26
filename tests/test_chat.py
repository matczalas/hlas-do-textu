"""Testy pro app.core.ai.chat — parsing odpovědí, build_chat_prompt, ChatSession."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.core.ai.chat import (
    ChatMessage,
    build_chat_prompt,
    parse_chat_response,
)
from app.core.models import SlideText, StudyMaterial, Transcript


def _make_material() -> StudyMaterial:
    return StudyMaterial(
        title="Test",
        bullets=["bod 1", "bod 2"],
        terms=[("pojem", "definice")],
        examples=["příklad"],
        further_study=["zdroj"],
    )


def test_parse_text_only_response_no_proposal() -> None:
    response = parse_chat_response(
        "Toto je obyčejná odpověď bez návrhu změny.",
        fallback_material=_make_material(),
    )
    assert response.proposal is None
    assert "obyčejná odpověď" in response.text


def test_parse_response_with_markdown_json_proposal() -> None:
    raw = (
        '```json\n'
        '{\n'
        '  "summary": "Zkrátil jsem body na 5.",\n'
        '  "updated_material": {\n'
        '    "title": "Filozofie 1",\n'
        '    "bullets": ["a", "b", "c", "d", "e"],\n'
        '    "terms": [["fenomenologie", "studium fenoménů"]],\n'
        '    "examples": [],\n'
        '    "further_study": []\n'
        '  }\n'
        '}\n'
        '```'
    )
    response = parse_chat_response(raw, fallback_material=_make_material())
    assert response.proposal is not None
    assert response.proposal.summary == "Zkrátil jsem body na 5."
    assert len(response.proposal.updated_material.bullets) == 5
    assert response.proposal.updated_material.terms == [
        ("fenomenologie", "studium fenoménů")
    ]


def test_parse_response_with_bare_json_proposal() -> None:
    raw = (
        '{"summary": "Hotovo.", '
        '"updated_material": {"title": "T", "bullets": ["x"], '
        '"terms": [], "examples": [], "further_study": []}}'
    )
    response = parse_chat_response(raw, fallback_material=_make_material())
    assert response.proposal is not None
    assert response.proposal.updated_material.bullets == ["x"]


def test_parse_response_terms_as_dicts() -> None:
    """Model občas vrátí terms jako {term: ..., definition: ...} místo tuplu."""
    raw = (
        '{"summary": "OK", "updated_material": {'
        '"title": "T", "bullets": [], '
        '"terms": [{"term": "alfa", "definition": "první"}, '
        '          {"pojem": "beta", "definice": "druhý"}], '
        '"examples": [], "further_study": []}}'
    )
    response = parse_chat_response(raw, fallback_material=_make_material())
    assert response.proposal is not None
    terms = response.proposal.updated_material.terms
    assert ("alfa", "první") in terms
    assert ("beta", "druhý") in terms


def test_parse_invalid_json_falls_back_to_text() -> None:
    response = parse_chat_response(
        "Tady má být JSON ale není { tohle není valid",
        fallback_material=_make_material(),
    )
    assert response.proposal is None
    assert "Tady má být JSON" in response.text


def test_parse_response_missing_updated_material() -> None:
    """JSON existuje, ale nemá updated_material → není to proposal."""
    raw = '{"summary": "jen summary"}'
    response = parse_chat_response(raw, fallback_material=_make_material())
    assert response.proposal is None


def test_build_chat_prompt_includes_all_context() -> None:
    transcripts = [
        Transcript(
            source_label="Část 1",
            language="cs",
            duration_sec=60.0,
            text="Husserl rozvíjí fenomenologii.",
            segments=[],
        )
    ]
    slides = [SlideText(source_label="Slidy.pdf", text="Fenomenologie - úvod", slide_count=5)]
    material = _make_material()
    history = [
        ChatMessage(role="user", content="ahoj"),
        ChatMessage(role="assistant", content="zdravím"),
    ]

    prompt = build_chat_prompt(
        user_message="Stručněji",
        history=history,
        transcripts=transcripts,
        slides=slides,
        current_material=material,
    )
    assert "Husserl" in prompt
    assert "Fenomenologie - úvod" in prompt
    assert "Stručněji" in prompt
    assert "bod 1" in prompt  # current material
    assert "ahoj" in prompt  # history
    assert "zdravím" in prompt


def test_build_chat_prompt_without_slides_omits_section() -> None:
    prompt = build_chat_prompt(
        user_message="?",
        history=[],
        transcripts=[
            Transcript(source_label="X", language="cs", duration_sec=1.0, text="x", segments=[])
        ],
        slides=[],
        current_material=_make_material(),
    )
    assert "SLIDY Z PREZENTACE" not in prompt


def test_chat_session_send_updates_history_and_calls_router() -> None:
    from app.core.ai.chat import ChatSession

    fake_router = MagicMock()
    fake_router.generate_with_failover.return_value = (
        "Toto je odpověď bez návrhu."
    )

    session = ChatSession(
        router=fake_router,
        transcripts=[
            Transcript(source_label="X", language="cs", duration_sec=1.0, text="x", segments=[])
        ],
        slides=[],
        current_material=_make_material(),
    )

    response = session.send("Ahoj")
    assert response.proposal is None
    assert response.text == "Toto je odpověď bez návrhu."
    assert len(session.history) == 2
    assert session.history[0].role == "user"
    assert session.history[1].role == "assistant"
    fake_router.generate_with_failover.assert_called_once()


def test_parse_response_preserves_preamble_before_json() -> None:
    """Modely často píší 'Tady je úprava:\\n```json\\n{...}\\n```' — text před JSON
    by se měl objevit v zobrazené odpovědi, ne se ztratit."""
    raw = (
        "Tady je upravená verze podle tvého požadavku:\n\n"
        "```json\n"
        '{"summary": "Body zkráceny na 3.", '
        '"updated_material": {"title": "X", "bullets": ["a","b","c"], '
        '"terms": [], "examples": [], "further_study": []}}\n'
        "```"
    )
    response = parse_chat_response(raw, fallback_material=_make_material())
    assert response.proposal is not None
    # Text musí obsahovat jak preamble, tak summary
    assert "Tady je upravená verze" in response.text
    assert "Body zkráceny na 3." in response.text


def test_chat_session_rolls_back_user_message_on_router_error() -> None:
    """Když router selže, user zpráva nesmí zůstat v history bez assistant odpovědi —
    jinak by další volání sestavilo nekonzistentní prompt."""
    from app.core.ai.chat import ChatSession

    fake_router = MagicMock()
    fake_router.generate_with_failover.side_effect = RuntimeError("network down")

    session = ChatSession(
        router=fake_router,
        transcripts=[],
        slides=[],
        current_material=_make_material(),
    )

    try:
        session.send("Ahoj")
    except RuntimeError:
        pass

    # User message nezůstala v history — rollback proběhl
    assert session.history == []


def test_chat_session_apply_proposal_replaces_material() -> None:
    from app.core.ai.chat import ChatProposal, ChatSession

    fake_router = MagicMock()
    new_material = StudyMaterial(title="Nový", bullets=["A"], terms=[], examples=[], further_study=[])
    proposal = ChatProposal(summary="Změna", updated_material=new_material)

    session = ChatSession(
        router=fake_router,
        transcripts=[],
        slides=[],
        current_material=_make_material(),
    )
    session.apply_proposal(proposal)
    assert session.current_material is new_material
    assert session.current_material.title == "Nový"
