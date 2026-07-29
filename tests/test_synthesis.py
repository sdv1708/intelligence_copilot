"""Synthesis: structured briefs, grounded answers, and citation integrity."""

from __future__ import annotations

import pytest

from core.config import Settings
from core.exceptions import InvalidBriefError, SynthesisError
from core.schema import Chunk, Evidence, MeetingBrief, ScoredChunk
from core.synthesis import Synthesizer, format_previous_brief, resolve_evidence
from core.utils import utc_now_iso
from tests.fakes import ScriptedChatModel

MEETING_ID = "meet_1"


def make_chunk(chunk_id: int, material: str, index: int, text: str) -> Chunk:
    return Chunk(
        id=chunk_id,
        material_id=material,
        meeting_id=MEETING_ID,
        chunk_index=index,
        text=text,
        char_start=index * 100,
        char_end=index * 100 + len(text),
        created_at=utc_now_iso(),
    )


@pytest.fixture
def results() -> list[ScoredChunk]:
    """Two hits from one material, one from another, plus a neighbour."""
    return [
        ScoredChunk(
            chunk=make_chunk(11, "mat_a", 0, "Revenue grew 12% in Q3."), score=0.81
        ),
        ScoredChunk(
            chunk=make_chunk(12, "mat_a", 1, "Hiring is paused until January."),
            score=0.74,
            is_neighbour=True,
        ),
        ScoredChunk(
            chunk=make_chunk(20, "mat_b", 4, "The vendor contract expires in March."),
            score=0.66,
        ),
    ]


VALID_BRIEF = {
    "meeting_title": "Q3 Review",
    "time_window": "2026-07-01..2026-07-28",
    "last_meeting_recap": "Revenue was up and hiring was frozen.",
    "open_action_items": [
        {"owner": "Dana", "item": "Renegotiate the vendor contract", "status": "open"}
    ],
    "key_topics_today": ["Vendor renewal: the contract expires in March."],
    "proposed_agenda": [{"topic": "Vendor renewal", "minutes": 20, "owner": "Dana"}],
    "evidence": [
        {"source": "mat_a#c0", "snippet": "Revenue grew 12% in Q3."},
        {"source": "mat_b#c4", "snippet": "The vendor contract expires in March."},
    ],
}


def synthesizer(responses, settings: Settings) -> Synthesizer:
    return Synthesizer(ScriptedChatModel(responses), provider="gemini", settings=settings)


# --- Brief generation -------------------------------------------------------


def test_a_structured_response_becomes_a_validated_brief(results, settings):
    synth = synthesizer([VALID_BRIEF], settings)

    result = synth.brief(title="Q3 Review", date="2026-07-28", results=results)

    assert isinstance(result.brief, MeetingBrief)
    assert result.brief.meeting_title == "Q3 Review"
    assert result.brief.open_action_items[0].owner == "Dana"
    assert result.model == "scripted-test-model"
    assert result.provider == "gemini"


def test_the_model_is_asked_for_a_meeting_brief_not_for_prose(results, settings):
    """The whole point of the chunk: the schema is bound, not described."""
    model = ScriptedChatModel([VALID_BRIEF])
    Synthesizer(model, provider="gemini", settings=settings).brief(
        title="Q3 Review", date="2026-07-28", results=results
    )

    assert model.structured_schemas == [MeetingBrief]


def test_a_json_string_response_is_still_accepted(results, settings):
    """Providers that answer in JSON mode rather than with a tool call."""
    import json

    synth = synthesizer([json.dumps(VALID_BRIEF)], settings)
    result = synth.brief(title="Q3 Review", date="2026-07-28", results=results)

    assert result.brief.meeting_title == "Q3 Review"


def test_prose_wrapped_in_a_markdown_fence_is_a_failure_not_a_repair(
    results, settings
):
    """The old code stripped fences, repaired commas, and counted braces.

    None of that is needed once the schema is bound, and none of it should come
    back: a response this far off the contract is a real failure.
    """
    synth = synthesizer(["```json\n{\"meeting_title\": \"Q3\",}\n```"], settings)

    with pytest.raises(InvalidBriefError):
        synth.brief(title="Q3 Review", date="2026-07-28", results=results)


def test_a_missing_meeting_title_is_filled_from_the_caller(results, settings):
    """The one repair worth making: a required field we already know."""
    payload = {key: value for key, value in VALID_BRIEF.items() if key != "meeting_title"}
    synth = synthesizer([payload], settings)

    result = synth.brief(title="Q3 Review", date="2026-07-28", results=results)

    assert result.brief.meeting_title == "Q3 Review"


def test_an_unusable_response_raises_rather_than_returning_half_a_brief(
    results, settings
):
    synth = synthesizer(["I'm afraid I can't help with that."], settings)

    with pytest.raises(InvalidBriefError):
        synth.brief(title="Q3 Review", date="2026-07-28", results=results)


def test_generating_without_context_is_refused(settings):
    synth = synthesizer([VALID_BRIEF], settings)

    with pytest.raises(SynthesisError, match="No context"):
        synth.brief(title="Q3 Review", date="2026-07-28", results=[])


# --- Citation integrity -----------------------------------------------------


def test_citations_are_resolved_to_chunk_ids(results, settings):
    """`Evidence.chunk_id` is populated from the chunks actually retrieved."""
    synth = synthesizer([VALID_BRIEF], settings)

    result = synth.brief(title="Q3 Review", date="2026-07-28", results=results)

    assert [item.chunk_id for item in result.brief.evidence] == [11, 20]
    assert result.cited_chunk_ids == (11, 20)
    assert result.dropped_sources == ()


def test_a_fabricated_citation_is_dropped(results, settings):
    """A source that was never retrieved cannot be verified, so it goes."""
    payload = dict(VALID_BRIEF)
    payload["evidence"] = [
        {"source": "mat_a#c0", "snippet": "Revenue grew 12% in Q3."},
        {"source": "mat_z#c99", "snippet": "Margins doubled."},
    ]
    synth = synthesizer([payload], settings)

    result = synth.brief(title="Q3 Review", date="2026-07-28", results=results)

    assert [item.source for item in result.brief.evidence] == ["mat_a#c0"]
    assert result.dropped_sources == ("mat_z#c99",)


def test_a_decorated_citation_is_canonicalised(results, settings):
    payload = dict(VALID_BRIEF)
    payload["evidence"] = [
        {"source": "[2] mat_b#c4 (transcript)", "snippet": "Contract expires."}
    ]
    synth = synthesizer([payload], settings)

    result = synth.brief(title="Q3 Review", date="2026-07-28", results=results)

    assert result.brief.evidence[0].source == "mat_b#c4"
    assert result.brief.evidence[0].chunk_id == 20


def test_resolve_evidence_can_cite_a_neighbour(results):
    """Neighbours are real retrieved text; they are quotable."""
    resolved, dropped = resolve_evidence(
        [Evidence(source="mat_a#c1", snippet="Hiring is paused until January.")],
        results,
    )

    assert dropped == []
    assert resolved[0].chunk_id == 12


def test_resolve_evidence_is_not_fooled_by_a_matching_index_in_another_material():
    """The defect class this overhaul exists to kill, at citation level."""
    results = [
        ScoredChunk(chunk=make_chunk(5, "mat_a", 3, "Real text."), score=0.9),
    ]

    resolved, dropped = resolve_evidence(
        [Evidence(source="mat_b#c3", snippet="Different material, same index.")],
        results,
    )

    assert resolved == []
    assert dropped == ["mat_b#c3"]


# --- Prompt construction ----------------------------------------------------


def test_the_prompt_carries_the_context_and_the_meeting_details(results, settings):
    model = ScriptedChatModel([VALID_BRIEF])
    Synthesizer(model, provider="gemini", settings=settings).brief(
        title="Q3 Review",
        date="2026-07-28",
        results=results,
        context="=== Material: mat_a ===\n[1] Source: mat_a#c0\nRevenue grew 12%.",
    )

    prompt = model.last_prompt_text
    assert "Q3 Review" in prompt
    assert "2026-07-28" in prompt
    assert "Source: mat_a#c0" in prompt
    assert "{{" not in prompt


def test_a_previous_brief_is_carried_into_the_prompt(results, settings):
    model = ScriptedChatModel([VALID_BRIEF])
    Synthesizer(model, provider="gemini", settings=settings).brief(
        title="Q3 Review",
        date="2026-07-28",
        results=results,
        previous_brief={
            "meeting_title": "Q2 Review",
            "last_meeting_recap": "We agreed to revisit the vendor contract.",
            "open_action_items": [
                {"owner": "Dana", "item": "Get vendor quotes", "status": "open"}
            ],
        },
    )

    prompt = model.last_prompt_text
    assert "PREVIOUS MEETING" in prompt
    assert "revisit the vendor contract" in prompt
    assert "Get vendor quotes" in prompt


def test_no_previous_brief_leaves_a_marker_not_an_empty_hole(results, settings):
    model = ScriptedChatModel([VALID_BRIEF])
    Synthesizer(model, provider="gemini", settings=settings).brief(
        title="Q3 Review", date="2026-07-28", results=results
    )

    assert "No previous meeting" in model.last_prompt_text


def test_format_previous_brief_accepts_a_typed_brief():
    rendered = format_previous_brief(MeetingBrief.model_validate(VALID_BRIEF))

    assert "Q3 Review" in rendered
    assert "Renegotiate the vendor contract" in rendered


def test_format_previous_brief_handles_none():
    assert "No previous meeting" in format_previous_brief(None)


def test_format_previous_brief_survives_a_sparse_legacy_row():
    """Stored briefs are raw dicts and need not satisfy today's schema."""
    rendered = format_previous_brief({"last_meeting_recap": ""})

    assert "none recorded" in rendered


# --- Question answering -----------------------------------------------------


def test_an_answer_is_grounded_in_the_retrieved_sources(results, settings):
    synth = synthesizer(["Revenue grew 12% in Q3."], settings)

    answer = synth.answer(question="How did revenue do?", results=results)

    assert answer.text == "Revenue grew 12% in Q3."
    assert answer.model == "scripted-test-model"


def test_answer_sources_are_the_hits_not_the_neighbours(results, settings):
    """The old regex over the prompt text always returned nothing."""
    synth = synthesizer(["An answer."], settings)

    answer = synth.answer(question="What is happening?", results=results)

    assert answer.sources == ("mat_a#c0", "mat_b#c4")
    assert answer.chunk_ids == (11, 20)


def test_the_question_reaches_the_prompt(results, settings):
    model = ScriptedChatModel(["An answer."])
    Synthesizer(model, provider="gemini", settings=settings).answer(
        question="When does the vendor contract expire?", results=results
    )

    prompt = model.last_prompt_text
    assert "When does the vendor contract expire?" in prompt
    assert "{{" not in prompt


def test_block_style_content_is_flattened_and_thinking_is_skipped(results, settings):
    """Reasoning models return a list of typed blocks, not a string."""
    synth = synthesizer(
        [
            [
                {"type": "thinking", "thinking": "Let me check the contract dates."},
                {"type": "text", "text": "It expires in March."},
            ]
        ],
        settings,
    )

    answer = synth.answer(question="When does it expire?", results=results)

    assert answer.text == "It expires in March."


def test_an_empty_question_is_refused(results, settings):
    synth = synthesizer(["unused"], settings)

    with pytest.raises(SynthesisError, match="empty question"):
        synth.answer(question="   ", results=results)


def test_an_empty_answer_is_refused(results, settings):
    synth = synthesizer([""], settings)

    with pytest.raises(SynthesisError, match="empty answer"):
        synth.answer(question="Anything?", results=results)
