"""Testy parseru JSON odpovědí z AI."""

from __future__ import annotations

from app.core.ai.router import _parse_study_material, _safe_parse_json
from app.core.models import (
    SECTION_KIND_BULLETS,
    SECTION_KIND_DEFINITIONS,
    SECTION_KIND_KEY_VALUE,
    SECTION_KIND_QA,
)

# ---------------------------------------------------------------------------
# Starý plochý formát (backward compat)
# ---------------------------------------------------------------------------


def test_parse_clean_json():
    raw = '{"title": "Test", "bullets": ["a", "b"], "terms": [["pojem", "definice"]], "examples": [], "further_study": []}'
    mat = _parse_study_material(raw)
    assert mat.title == "Test"
    assert mat.bullets == ["a", "b"]
    assert mat.terms == [("pojem", "definice")]


def test_parse_extracts_topic():
    raw = '{"topic": "Fyzika", "title": "Newton", "bullets": ["a"]}'
    mat = _parse_study_material(raw)
    assert mat.topic == "Fyzika"
    assert mat.title == "Newton"


def test_parse_missing_topic_defaults_empty():
    raw = '{"title": "X", "bullets": ["a"]}'
    mat = _parse_study_material(raw)
    assert mat.topic == ""


def test_parse_extracts_quiz_questions():
    raw = '{"title": "X", "bullets": ["a"], "quiz_questions": ["Co je Newton?", "Vysvětli sílu."]}'
    mat = _parse_study_material(raw)
    assert mat.quiz_questions == ["Co je Newton?", "Vysvětli sílu."]


def test_parse_quiz_only_not_treated_as_empty():
    # Výstup jen s otázkami (učitelská šablona) nesmí spadnout do prázdné pojistky
    raw = '{"title": "X", "quiz_questions": ["Otázka 1?", "Otázka 2?"]}'
    mat = _parse_study_material(raw)
    assert mat.quiz_questions == ["Otázka 1?", "Otázka 2?"]
    assert mat.bullets == []  # žádná informativní pojistka


def test_template_prompts_exist():
    from app.core.ai.prompts import PROMPT_TEMPLATES, template_prompt

    assert "teacher_lesson" in PROMPT_TEMPLATES
    teacher = template_prompt("teacher_lesson")
    assert "učitel" in teacher.lower()
    assert "zkoušení" in teacher.lower() or "vyzkoušet" in teacher.lower()
    # Neznámý klíč → prázdný řetězec
    assert template_prompt("neexistuje") == ""


def test_parse_markdown_fenced_json():
    raw = "Zde je tvůj výstup:\n```json\n{\"title\": \"T\", \"bullets\": [\"x\"]}\n```\nHotovo."
    mat = _parse_study_material(raw)
    assert mat.title == "T"
    assert mat.bullets == ["x"]


def test_parse_terms_dict_form():
    raw = '{"title": "T", "terms": [{"pojem": "A", "definice": "B"}]}'
    mat = _parse_study_material(raw)
    assert mat.terms == [("A", "B")]


def test_safe_parse_returns_none_for_garbage():
    assert _safe_parse_json("zcela nestrukturovaný text bez JSON") is None
    assert _safe_parse_json("") is None


def test_parse_fallback_when_no_json():
    """Když AI vrátí nestrukturovaný text, dáme ho jako jednu bullet sekci."""
    raw = "Nějaký dlouhý text bez JSON struktury."
    mat = _parse_study_material(raw)
    # Text musí být dosažitelný přes iter_sections
    rendered = [it for sec in mat.iter_sections() for it in sec.items]
    assert raw in rendered
    assert mat.title  # nějaký default titul


# ---------------------------------------------------------------------------
# Nový sekce-aware formát
# ---------------------------------------------------------------------------


def test_parse_sections_basic():
    raw = """{
        "title": "Sales schůzka",
        "topic": "Finance",
        "sections": [
            {"title": "Úkoly pro mě", "kind": "key_value",
             "items": [["Připravit nabídku", "do pátku"], ["Zavolat klientovi", "neuvedeno"]]},
            {"title": "Profil klienta", "kind": "key_value",
             "items": [["Věk", "42"], ["Děti", "2"]]}
        ]
    }"""
    mat = _parse_study_material(raw)
    assert mat.title == "Sales schůzka"
    assert mat.topic == "Finance"
    assert len(mat.sections) == 2
    assert mat.sections[0].title == "Úkoly pro mě"
    assert mat.sections[0].kind == SECTION_KIND_KEY_VALUE
    assert mat.sections[0].items == [
        ("Připravit nabídku", "do pátku"),
        ("Zavolat klientovi", "neuvedeno"),
    ]


def test_parse_sections_all_kinds():
    raw = """{
        "title": "Test všech kindů",
        "sections": [
            {"title": "Body", "kind": "bullets", "items": ["a", "b"]},
            {"title": "Pojmy", "kind": "definitions", "items": [["X", "význam X"]]},
            {"title": "Otázky", "kind": "qa", "items": [["Co?", "Odpověď."]]},
            {"title": "Klíče", "kind": "key_value", "items": [["k", "v"]]},
            {"title": "Odstavec", "kind": "paragraph", "items": ["první odstavec"]}
        ]
    }"""
    mat = _parse_study_material(raw)
    assert len(mat.sections) == 5
    assert [s.kind for s in mat.sections] == [
        "bullets",
        "definitions",
        "qa",
        "key_value",
        "paragraph",
    ]


def test_parse_sections_tolerates_dict_items():
    """Model může vrátit položky jako dict — parser je zploští na tuple."""
    raw = """{
        "title": "T",
        "sections": [
            {"title": "Pojmy", "kind": "definitions",
             "items": [{"pojem": "alfa", "definice": "první"},
                       {"term": "beta", "definition": "druhý"}]},
            {"title": "Otázky", "kind": "qa",
             "items": [{"question": "Q?", "answer": "A."},
                       {"otázka": "Co?", "odpověď": "tak."}]}
        ]
    }"""
    mat = _parse_study_material(raw)
    defs = mat.sections[0]
    assert defs.items == [("alfa", "první"), ("beta", "druhý")]
    qa = mat.sections[1]
    assert qa.items == [("Q?", "A."), ("Co?", "tak.")]


def test_parse_sections_unknown_kind_falls_to_bullets():
    raw = """{
        "title": "T",
        "sections": [
            {"title": "Cokoli", "kind": "neexistuje_kind", "items": ["a", "b"]}
        ]
    }"""
    mat = _parse_study_material(raw)
    # __post_init__ normalizuje neznámý kind na bullets
    assert mat.sections[0].kind == SECTION_KIND_BULLETS
    assert mat.sections[0].items == ["a", "b"]


def test_parse_sections_skips_empty_items():
    """Prázdné items (např. {} v listu) se nevypíší do sekce."""
    raw = """{
        "title": "T",
        "sections": [
            {"title": "Body", "kind": "bullets", "items": ["valid", "", null]},
            {"title": "Pojmy", "kind": "definitions", "items": [["", ""], ["A", "B"]]}
        ]
    }"""
    mat = _parse_study_material(raw)
    assert mat.sections[0].items == ["valid"]
    # ("", "") odfiltruje coerce_pair (návrat None)
    assert mat.sections[1].items == [("A", "B")]


def test_parse_sections_populates_legacy_aliases():
    """Sekce-aware výstup naplní i legacy `terms`/`quiz_questions` (kvůli chatu)."""
    raw = """{
        "title": "T",
        "sections": [
            {"title": "Klíčové pojmy", "kind": "definitions",
             "items": [["foton", "kvant světla"]]},
            {"title": "Otázky", "kind": "qa",
             "items": [["Co je foton?", "Kvant elektromagnetického pole."]]}
        ]
    }"""
    mat = _parse_study_material(raw)
    assert mat.terms == [("foton", "kvant světla")]
    assert mat.quiz_questions == ["Co je foton?"]


def test_parse_empty_sections_fallback_to_notice():
    """Sections array prázdný / všechny sekce bez items → informativní poznámka."""
    raw = '{"title": "T", "sections": [{"title": "X", "kind": "bullets", "items": []}]}'
    mat = _parse_study_material(raw)
    # iter_sections musí vrátit aspoň informativní poznámku
    items = [it for sec in mat.iter_sections() for it in sec.items]
    assert items, "Fallback poznámka musí být přítomná"


def test_parse_sections_with_qa_question_only():
    """QA s prázdnou vzorovou odpovědí — má mít prázdný string místo errored hodnoty."""
    raw = """{
        "title": "T",
        "sections": [
            {"title": "Otázky", "kind": "qa",
             "items": [["Co je síla?", ""]]}
        ]
    }"""
    mat = _parse_study_material(raw)
    assert mat.sections[0].items == [("Co je síla?", "")]


# ---------------------------------------------------------------------------
# Schémata sekcí jsou definovaná pro všechny šablony
# ---------------------------------------------------------------------------


def test_section_schemas_cover_all_templates():
    """Každá šablona v PROMPT_TEMPLATES má vlastní schéma sekcí."""
    from app.core.ai.prompts import PROMPT_TEMPLATES, SECTION_SCHEMAS

    for key in PROMPT_TEMPLATES:
        assert key in SECTION_SCHEMAS, (
            f"Šablona '{key}' nemá schéma sekcí v SECTION_SCHEMAS"
        )
        assert SECTION_SCHEMAS[key], f"Schéma pro '{key}' je prázdné"


def test_sales_schema_uses_key_value_and_paragraph():
    """Sales schůzka má smysl jen s key_value a paragraph — žádné quiz/definice."""
    from app.core.ai.prompts import SECTION_SCHEMAS

    specs = SECTION_SCHEMAS["sales_meeting"]
    kinds = {spec.kind for spec in specs}
    # Musí být alespoň jedna key_value sekce a alespoň jedna paragraph
    assert SECTION_KIND_KEY_VALUE in kinds
    assert "paragraph" in kinds
    # A naopak — pro sales nedává smysl QA/definice
    assert SECTION_KIND_QA not in kinds
    assert SECTION_KIND_DEFINITIONS not in kinds


def test_build_reduce_prompt_includes_template_sections():
    """Reduce prompt pro sales_meeting obsahuje sales-specifické sekce, ne studentské."""
    from app.core.ai.prompts import build_reduce_prompt

    prompt = build_reduce_prompt(
        "test",
        "mapped",
        "slidy",
        template_key="sales_meeting",
    )
    assert "Úkoly pro mě" in prompt
    assert "Profil klienta" in prompt
    # Studentské sekce tam být nesmí
    assert "Hlavní body k zapamatování" not in prompt


# ---------------------------------------------------------------------------
# Nové šablony — pokrytí jejich schémat
# ---------------------------------------------------------------------------


def test_new_templates_have_schemas():
    """Nové šablony (v1.7) mají vlastní schéma sekcí."""
    from app.core.ai.prompts import PROMPT_TEMPLATES, SECTION_SCHEMAS

    new_keys = (
        "sales_followup_email",
        "sales_objection_log",
        "student_flashcards",
        "student_language_vocab",
        "teacher_parent_summary",
        "teacher_next_lesson_plan",
        "meeting_minutes",
    )
    for key in new_keys:
        assert key in PROMPT_TEMPLATES, f"Šablona '{key}' chybí v PROMPT_TEMPLATES"
        assert key in SECTION_SCHEMAS, f"Schéma pro '{key}' chybí"
        assert SECTION_SCHEMAS[key], f"Schéma pro '{key}' je prázdné"


def test_sales_followup_email_has_email_structure():
    """Follow-up e-mail musí mít předmět, tělo a přílohu."""
    from app.core.ai.prompts import SECTION_SCHEMAS

    titles = [s.title for s in SECTION_SCHEMAS["sales_followup_email"]]
    assert any("předmět" in t.lower() for t in titles)
    assert any("tělo" in t.lower() for t in titles)


def test_student_flashcards_uses_definitions_and_qa():
    """Karty na učení musí mít definice (pojem→def) i Q/A — pro Anki/Quizlet."""
    from app.core.ai.prompts import SECTION_SCHEMAS
    from app.core.models import SECTION_KIND_DEFINITIONS, SECTION_KIND_QA

    kinds = {s.kind for s in SECTION_SCHEMAS["student_flashcards"]}
    assert SECTION_KIND_DEFINITIONS in kinds
    assert SECTION_KIND_QA in kinds


def test_meeting_minutes_has_decisions_and_actions():
    """Univerzální zápis musí mít rozhodnutí a akce/úkoly."""
    from app.core.ai.prompts import SECTION_SCHEMAS

    titles = [s.title.lower() for s in SECTION_SCHEMAS["meeting_minutes"]]
    assert any("rozhodnut" in t for t in titles)
    assert any("akce" in t or "úkol" in t for t in titles)


# ---------------------------------------------------------------------------
# templates_for_role — univerzální klíče (meeting_minutes) ve všech rolích
# ---------------------------------------------------------------------------


def test_templates_for_role_student_includes_universal():
    from app.core.ai.prompts import templates_for_role

    tpl = templates_for_role("student")
    assert "student" in tpl
    assert "student_flashcards" in tpl
    assert "student_language_vocab" in tpl
    assert "meeting_minutes" in tpl
    assert "quiz" in tpl
    assert "summary" in tpl
    # Učitelské a sales šablony se studentovi nezobrazí
    assert "teacher_lesson" not in tpl
    assert "sales_meeting" not in tpl


def test_templates_for_role_teacher_includes_universal_and_new():
    from app.core.ai.prompts import templates_for_role

    tpl = templates_for_role("teacher")
    assert "teacher_lesson" in tpl
    assert "teacher_parent_summary" in tpl
    assert "teacher_next_lesson_plan" in tpl
    assert "meeting_minutes" in tpl
    assert "summary" in tpl
    # Sales šablony se učiteli nezobrazí
    assert "sales_meeting" not in tpl
    assert "sales_followup_email" not in tpl
    # A „student“ (student-specifická) taky ne
    assert "student" not in tpl


def test_templates_for_role_sales_includes_universal_and_new():
    from app.core.ai.prompts import templates_for_role

    tpl = templates_for_role("sales")
    assert "sales_meeting" in tpl
    assert "sales_followup_email" in tpl
    assert "sales_objection_log" in tpl
    assert "meeting_minutes" in tpl
    assert "summary" in tpl
    # Teacher a student šablony se prodejci nezobrazí
    assert "teacher_lesson" not in tpl
    assert "student" not in tpl
    assert "student_flashcards" not in tpl


# ---------------------------------------------------------------------------
# Diarizace — které šablony jsou "konverzační" (rozlišovat mluvčí)
# ---------------------------------------------------------------------------


def test_is_conversation_template():
    from app.core.ai.prompts import is_conversation_template

    # Dialog více osob → ano
    assert is_conversation_template("sales_meeting")
    assert is_conversation_template("sales_followup_email")
    assert is_conversation_template("sales_objection_log")
    assert is_conversation_template("meeting_minutes")
    # Monolog → ne
    assert not is_conversation_template("student")
    assert not is_conversation_template("teacher_lesson")
    assert not is_conversation_template("summary")
    assert not is_conversation_template("student_flashcards")


def test_system_prompt_mentions_speaker_mapping():
    """System prompt učí AI mapovat Mluvčí N → role/jméno z kontextu."""
    from app.core.ai.prompts import SYSTEM_PROMPT_CS

    assert "Mluvčí" in SYSTEM_PROMPT_CS
    # A varuje před vymýšlením jmen
    assert "nevymýšlej" in SYSTEM_PROMPT_CS.lower()


# ---------------------------------------------------------------------------
# Brainstorming šablona — AI smí mít názor (výjimka z faithful pravidel)
# ---------------------------------------------------------------------------


def test_brainstorm_template_registered():
    from app.core.ai.prompts import PROMPT_TEMPLATES, SECTION_SCHEMAS

    assert "brainstorm" in PROMPT_TEMPLATES
    assert "brainstorm" in SECTION_SCHEMAS
    titles = [s.title.lower() for s in SECTION_SCHEMAS["brainstorm"]]
    # Pokrývá vše, co uživatel chtěl: názor, kritika, návrhy, efektivita
    assert any("myslím" in t for t in titles)
    assert any("kritika" in t for t in titles)
    assert any("návrh" in t for t in titles)
    assert any("efektiv" in t for t in titles)


def test_brainstorm_has_own_system_prompt():
    """Brainstorming má vlastní system prompt, ostatní šablony faithful."""
    from app.core.ai.prompts import (
        SYSTEM_PROMPT_BRAINSTORM_CS,
        SYSTEM_PROMPT_CS,
        system_prompt_for_template,
    )

    assert system_prompt_for_template("brainstorm") == SYSTEM_PROMPT_BRAINSTORM_CS
    assert system_prompt_for_template("sales_meeting") == SYSTEM_PROMPT_CS
    assert system_prompt_for_template("student") == SYSTEM_PROMPT_CS
    # Brainstorm prompt dovoluje názor/kritiku
    low = SYSTEM_PROMPT_BRAINSTORM_CS.lower()
    assert "názor" in low or "upřímn" in low
    assert "kriti" in low or "riziko" in low


def test_brainstorm_quality_rules_differ():
    """Brainstorm prompt používá uvolněná pravidla (smí přidávat názor)."""
    from app.core.ai.prompts import build_single_shot_prompt

    brainstorm = build_single_shot_prompt("", "Mluvčí 1: nápad…", "", template_key="brainstorm")
    student = build_single_shot_prompt("", "text", "", template_key="student")
    # Brainstorm zmiňuje vlastní názor; faithful student "nepřidávej fakta zvenčí"
    assert "názor" in brainstorm.lower()
    assert "Nepřidávej fakta zvenčí" in student
    assert "Nepřidávej fakta zvenčí" not in brainstorm


def test_brainstorm_is_universal_and_conversation():
    from app.core.ai.prompts import (
        is_conversation_template,
        templates_for_role,
    )

    # Univerzální → ve všech rolích
    for role in ("student", "teacher", "sales"):
        assert "brainstorm" in templates_for_role(role)
    # Konverzační → diarizace se u něj zapne
    assert is_conversation_template("brainstorm")


# ---------------------------------------------------------------------------
# Role podcast + šablony v1.12 (telefonát, rodič, porada, workshop, podcast_*)
# ---------------------------------------------------------------------------


def test_v112_templates_have_schemas():
    from app.core.ai.prompts import PROMPT_TEMPLATES, SECTION_SCHEMAS

    new_keys = (
        "sales_phone_call",
        "teacher_parent_meeting",
        "team_meeting",
        "workshop_training",
        "podcast_shownotes",
        "podcast_chapters",
        "podcast_quotes",
        "podcast_article",
        "podcast_interview_qa",
    )
    for key in new_keys:
        assert key in PROMPT_TEMPLATES, f"'{key}' chybí v PROMPT_TEMPLATES"
        assert key in SECTION_SCHEMAS, f"schéma pro '{key}' chybí"
        assert SECTION_SCHEMAS[key], f"schéma pro '{key}' je prázdné"


def test_templates_for_role_podcast():
    from app.core.ai.prompts import templates_for_role

    tpl = templates_for_role("podcast")
    # Podcast šablony + univerzální
    for key in ("podcast_shownotes", "podcast_chapters", "podcast_quotes",
                "podcast_article", "podcast_interview_qa",
                "summary", "brainstorm", "meeting_minutes",
                "team_meeting", "workshop_training"):
        assert key in tpl, f"'{key}' chybí v podcast roli"
    # Cizí rolové šablony ne
    assert "sales_meeting" not in tpl
    assert "teacher_lesson" not in tpl
    assert "student" not in tpl


def test_student_role_excludes_podcast_templates():
    from app.core.ai.prompts import templates_for_role

    tpl = templates_for_role("student")
    assert "podcast_shownotes" not in tpl
    assert "team_meeting" in tpl  # univerzální zůstávají


def test_new_conversation_templates():
    from app.core.ai.prompts import is_conversation_template

    for key in ("podcast_shownotes", "podcast_interview_qa", "team_meeting",
                "workshop_training", "teacher_parent_meeting", "sales_phone_call"):
        assert is_conversation_template(key), f"'{key}' má být konverzační"


def test_needs_timestamps_only_for_chapters_and_quotes():
    from app.core.ai.prompts import needs_timestamps

    assert needs_timestamps("podcast_chapters")
    assert needs_timestamps("podcast_quotes")
    assert not needs_timestamps("podcast_shownotes")
    assert not needs_timestamps("student")


def test_combine_transcripts_with_timestamps():
    """Router vkládá [mm:ss] značky (+ mluvčí), když to šablona potřebuje."""
    from app.core.ai.router import _combine_transcripts
    from app.core.models import Transcript, TranscriptSegment

    tr = Transcript(
        source_label="Epizoda 1",
        language="cs",
        duration_sec=120.0,
        text="Ahoj. Vítejte.",
        segments=[
            TranscriptSegment(start=0.0, end=4.0, text="Ahoj.", speaker="Mluvčí 1"),
            TranscriptSegment(start=65.0, end=70.0, text="Vítejte.", speaker=""),
        ],
    )
    with_ts = _combine_transcripts([tr], with_timestamps=True)
    assert "[00:00] Mluvčí 1: Ahoj." in with_ts
    assert "[01:05] Vítejte." in with_ts
    # Bez timestamps → plain text
    plain = _combine_transcripts([tr], with_timestamps=False)
    assert "[00:00]" not in plain


def test_tokens_set_role_podcast():
    from app.gui.styles import tokens

    tokens.set_role("podcast")
    try:
        assert tokens.accent() == tokens.PODCAST_ACCENT
    finally:
        tokens.set_role("student")  # úklid pro ostatní testy


# ---------------------------------------------------------------------------
# Role v1.13: HR, kouč, spolky + realitky pod sales
# ---------------------------------------------------------------------------


def test_v113_templates_have_schemas():
    from app.core.ai.prompts import PROMPT_TEMPLATES, SECTION_SCHEMAS

    new_keys = (
        "hr_interview", "hr_performance_review", "hr_exit_interview", "hr_one_on_one",
        "coach_session", "coach_first_session", "coach_next_prep",
        "spolek_meeting", "spolek_agenda", "spolek_annual_report",
        "sales_property_viewing", "sales_property_listing",
    )
    for key in new_keys:
        assert key in PROMPT_TEMPLATES, f"'{key}' chybí v PROMPT_TEMPLATES"
        assert key in SECTION_SCHEMAS, f"schéma pro '{key}' chybí"
        assert SECTION_SCHEMAS[key], f"schéma pro '{key}' je prázdné"


def test_templates_for_role_hr_coach_spolek():
    from app.core.ai.prompts import templates_for_role

    hr = templates_for_role("hr")
    assert "hr_interview" in hr and "hr_exit_interview" in hr
    assert "summary" in hr and "team_meeting" in hr  # univerzální
    assert "sales_meeting" not in hr and "coach_session" not in hr

    coach = templates_for_role("coach")
    assert "coach_session" in coach and "coach_next_prep" in coach
    assert "brainstorm" in coach
    assert "hr_interview" not in coach

    spolek = templates_for_role("spolek")
    assert "spolek_meeting" in spolek and "spolek_agenda" in spolek
    assert "meeting_minutes" in spolek
    assert "podcast_shownotes" not in spolek


def test_realty_templates_under_sales():
    """Realitky jsou šablony pod sales rolí, ne samostatná role."""
    from app.core.ai.prompts import templates_for_role

    sales = templates_for_role("sales")
    assert "sales_property_viewing" in sales
    assert "sales_property_listing" in sales
    # Student je nevidí
    assert "sales_property_viewing" not in templates_for_role("student")


def test_student_excludes_new_role_templates():
    from app.core.ai.prompts import templates_for_role

    student = templates_for_role("student")
    for key in ("hr_interview", "coach_session", "spolek_meeting"):
        assert key not in student


def test_new_roles_are_conversation_templates():
    from app.core.ai.prompts import is_conversation_template

    for key in ("hr_interview", "hr_one_on_one", "coach_session",
                "spolek_meeting", "sales_property_viewing"):
        assert is_conversation_template(key), f"'{key}' má být konverzační"


def test_spolek_meeting_has_usneseni():
    """Zápis ze schůze musí mít sekci usnesení — to je jeho smysl."""
    from app.core.ai.prompts import SECTION_SCHEMAS

    titles = [s.title.lower() for s in SECTION_SCHEMAS["spolek_meeting"]]
    assert any("usnesení" in t for t in titles)


def test_tokens_new_roles():
    from app.gui.styles import tokens

    for role, expected in (
        ("hr", tokens.HR_ACCENT),
        ("coach", tokens.COACH_ACCENT),
        ("spolek", tokens.SPOLEK_ACCENT),
    ):
        tokens.set_role(role)
        try:
            assert tokens.accent() == expected, f"role {role}"
        finally:
            tokens.set_role("student")
