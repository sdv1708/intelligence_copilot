"""Model validation, including the compatibility shim the legacy UI leans on."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.schema import (
    ActionItem,
    AgendaItem,
    BriefRecord,
    Chunk,
    Evidence,
    Material,
    MeetingBrief,
    NewChunk,
    ScoredChunk,
)


def make_chunk(**overrides) -> Chunk:
    fields = {
        "id": 1,
        "material_id": "material_x",
        "meeting_id": "meeting_x",
        "chunk_index": 0,
        "text": "some text",
        "char_start": 0,
        "char_end": 9,
        "created_at": "2026-07-28T00:00:00+00:00",
    }
    return Chunk(**{**fields, **overrides})


# --- Records ---------------------------------------------------------------


def test_records_support_dict_style_access_for_the_legacy_ui():
    material = Material(
        id="mat1",
        meeting_id="m1",
        filename="notes.txt",
        media_type="txt",
        text="hello",
        created_at="2026-07-28T00:00:00+00:00",
    )
    assert material["filename"] == "notes.txt"
    assert material.get("missing", "fallback") == "fallback"
    assert "media_type" in material
    with pytest.raises(KeyError):
        material["nope"]


def test_records_are_frozen():
    with pytest.raises(ValidationError):
        make_chunk().id = 99


def test_record_text_is_not_stripped():
    """Stripping would desynchronise char offsets from the material body."""
    chunk = make_chunk(text="  padded  ", char_start=0, char_end=10)
    assert chunk.text == "  padded  "


def test_chunk_source_ref_is_the_citation_label():
    assert make_chunk(chunk_index=7).source_ref == "material_x#c7"


def test_chunk_rejects_an_inverted_span():
    with pytest.raises(ValidationError, match="precedes char_start"):
        make_chunk(char_start=50, char_end=10)


def test_chunk_id_must_be_positive():
    """FAISS ids come from this field; 0 and negatives are sentinels there."""
    with pytest.raises(ValidationError):
        make_chunk(id=0)
    with pytest.raises(ValidationError):
        make_chunk(id=-1)


def test_material_char_count_is_derived():
    material = Material(
        id="mat1",
        meeting_id="m1",
        text="12345",
        created_at="2026-07-28T00:00:00+00:00",
    )
    assert material.char_count == 5


def test_meeting_attendee_and_tag_lists_split_and_clean():
    from core.schema import Meeting

    meeting = Meeting(
        id="m1",
        title="Standup",
        attendees="Ada, Grace ,, Alan",
        tags="planning,",
        created_at="2026-07-28T00:00:00+00:00",
    )
    assert meeting.attendee_list == ["Ada", "Grace", "Alan"]
    assert meeting.tag_list == ["planning"]


# --- NewChunk --------------------------------------------------------------


def test_new_chunk_defaults_its_end_offset_from_the_text():
    chunk = NewChunk(chunk_index=0, text="abcdef")
    assert (chunk.char_start, chunk.char_end) == (0, 6)


def test_new_chunk_defaults_end_relative_to_start():
    chunk = NewChunk(chunk_index=3, text="abcdef", char_start=100)
    assert chunk.char_end == 106


def test_new_chunk_keeps_an_explicit_span():
    chunk = NewChunk(chunk_index=0, text="abc", char_start=10, char_end=99)
    assert (chunk.char_start, chunk.char_end) == (10, 99)


def test_new_chunk_rejects_empty_text():
    with pytest.raises(ValidationError):
        NewChunk(chunk_index=0, text="")


# --- ScoredChunk -----------------------------------------------------------


def test_scored_chunk_defaults_to_a_direct_hit():
    scored = ScoredChunk(chunk=make_chunk(), score=0.8)
    assert scored.is_neighbour is False
    assert scored.source_ref == "material_x#c0"


# --- Brief structures ------------------------------------------------------


def test_action_item_normalises_the_statuses_models_actually_emit():
    assert ActionItem(owner="Ada", item="ship", status="Completed").status == "done"
    assert ActionItem(owner="Ada", item="ship", status="IN PROGRESS").status == "open"
    assert ActionItem(owner="Ada", item="ship", status="  open ").status == "open"


def test_action_item_rejects_an_unknown_status():
    with pytest.raises(ValidationError):
        ActionItem(owner="Ada", item="ship", status="maybe")


def test_action_item_due_must_be_an_iso_date():
    assert ActionItem(owner="Ada", item="ship", due="2026-01-31").due == "2026-01-31"
    assert ActionItem(owner="Ada", item="ship", due="  ").due is None
    with pytest.raises(ValidationError, match="YYYY-MM-DD"):
        ActionItem(owner="Ada", item="ship", due="next Tuesday")


def test_agenda_item_requires_a_sane_time_box():
    assert AgendaItem(topic="Roadmap", minutes=15).minutes == 15
    with pytest.raises(ValidationError):
        AgendaItem(topic="Roadmap", minutes=0)
    with pytest.raises(ValidationError):
        AgendaItem(topic="Roadmap", minutes=10_000)


def test_brief_absorbs_nulls_where_lists_are_expected():
    """Models emit `null` for empty sections often enough to be worth handling."""
    brief = MeetingBrief(
        meeting_title="Weekly",
        last_meeting_recap="",
        open_action_items=None,
        key_topics_today=None,
        proposed_agenda=None,
        evidence=None,
    )
    assert brief.open_action_items == []
    assert brief.evidence == []


def test_brief_drops_blank_topics():
    brief = MeetingBrief(meeting_title="Weekly", key_topics_today=["  ", "Hiring", ""])
    assert brief.key_topics_today == ["Hiring"]


def test_brief_validates_the_time_window_format():
    assert MeetingBrief(
        meeting_title="Weekly", time_window="2025-11-10..2025-11-11"
    ).time_window == "2025-11-10..2025-11-11"
    assert MeetingBrief(meeting_title="Weekly", time_window=None).time_window is None
    with pytest.raises(ValidationError, match="time_window"):
        MeetingBrief(meeting_title="Weekly", time_window="last week")


def test_brief_ignores_extra_keys_rather_than_failing():
    brief = MeetingBrief(meeting_title="Weekly", commentary="here you go!")
    assert brief.meeting_title == "Weekly"


def test_brief_requires_a_title():
    with pytest.raises(ValidationError):
        MeetingBrief(meeting_title="")


def test_total_agenda_minutes():
    brief = MeetingBrief(
        meeting_title="Weekly",
        proposed_agenda=[
            AgendaItem(topic="A", minutes=10),
            AgendaItem(topic="B", minutes=20),
        ],
    )
    assert brief.total_agenda_minutes == 30


def test_evidence_carries_an_optional_chunk_id():
    evidence = Evidence(source="mat1#c3", snippet="...", chunk_id=42)
    assert evidence.chunk_id == 42
    assert Evidence(source="mat1#c3", snippet="...").chunk_id is None


def test_brief_record_keeps_the_payload_raw():
    """Old rows must survive a schema tightening; validation is opt-in."""
    record = BriefRecord(
        id="b1",
        meeting_id="m1",
        created_at="2026-07-28T00:00:00+00:00",
        model="gemini",
        brief={"meeting_title": "Weekly", "time_window": "nonsense"},
    )
    assert record["brief"]["time_window"] == "nonsense"
    with pytest.raises(ValidationError):
        record.as_brief()


def test_brief_record_round_trips_a_valid_payload():
    payload = MeetingBrief(meeting_title="Weekly").model_dump()
    record = BriefRecord(
        id="b1",
        meeting_id="m1",
        created_at="2026-07-28T00:00:00+00:00",
        model="gemini",
        brief=payload,
    )
    assert record.as_brief().meeting_title == "Weekly"
