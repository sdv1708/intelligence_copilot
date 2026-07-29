"""Node-level behaviour: merging, memory, and the two routing decisions.

These are the parts of the graph that are pure functions, so they are tested
directly rather than through an invocation. `test_graph.py` covers the wiring.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.nodes import (
    dispatch_research,
    merge_findings,
    previous_brief_for_title,
    route_after_merge,
    route_after_qa_retrieval,
)
from agents.state import Finding, ResearchTask
from core.db import Database
from core.schema import Chunk, ScoredChunk
from core.utils import utc_now_iso

MEETING = "meet_1"


def chunk(chunk_id: int, index: int, material: str = "mat_a") -> Chunk:
    text = f"Paragraph {index} of {material}."
    return Chunk(
        id=chunk_id,
        material_id=material,
        meeting_id=MEETING,
        chunk_index=index,
        text=text,
        char_start=index * 100,
        char_end=index * 100 + len(text),
        created_at=utc_now_iso(),
    )


def finding(name: str, *scored: ScoredChunk) -> Finding:
    return Finding(task=ResearchTask(name=name, query=name), results=tuple(scored))


# --- Merging ----------------------------------------------------------------


def test_a_chunk_two_specialists_both_found_appears_once():
    shared = ScoredChunk(chunk=chunk(1, 0), score=0.5)
    merged = merge_findings(
        [finding("risks", shared), finding("timeline", shared)], limit=50
    )
    assert [scored.chunk.id for scored in merged] == [1]


def test_a_hit_beats_the_same_chunk_arriving_as_a_neighbour():
    """The prompt must not label a real match '(surrounding context)'."""
    as_neighbour = ScoredChunk(chunk=chunk(1, 0), score=0.9, is_neighbour=True)
    as_hit = ScoredChunk(chunk=chunk(1, 0), score=0.3)

    merged = merge_findings(
        [finding("timeline", as_neighbour), finding("risks", as_hit)], limit=50
    )

    assert len(merged) == 1
    assert merged[0].is_neighbour is False
    # Even though the neighbour carried the higher score: being a hit wins
    # first, and only then does score break the tie.
    assert merged[0].score == pytest.approx(0.3)


def test_the_higher_score_survives_when_both_are_hits():
    merged = merge_findings(
        [
            finding("a", ScoredChunk(chunk=chunk(1, 0), score=0.2)),
            finding("b", ScoredChunk(chunk=chunk(1, 0), score=0.8)),
        ],
        limit=50,
    )
    assert merged[0].score == pytest.approx(0.8)


def test_the_merged_context_reads_in_document_order_not_rank_order():
    """A brief is read whole, so coherent runs beat a ranked shuffle."""
    merged = merge_findings(
        [
            finding("late", ScoredChunk(chunk=chunk(3, 7), score=0.9)),
            finding("early", ScoredChunk(chunk=chunk(1, 1), score=0.2)),
            finding("middle", ScoredChunk(chunk=chunk(2, 4), score=0.5)),
        ],
        limit=50,
    )
    assert [scored.chunk.chunk_index for scored in merged] == [1, 4, 7]


def test_materials_are_kept_together():
    merged = merge_findings(
        [
            finding("a", ScoredChunk(chunk=chunk(1, 0, "mat_b"), score=0.9)),
            finding("b", ScoredChunk(chunk=chunk(2, 0, "mat_a"), score=0.8)),
            finding("c", ScoredChunk(chunk=chunk(3, 1, "mat_b"), score=0.7)),
        ],
        limit=50,
    )
    assert [scored.chunk.material_id for scored in merged] == [
        "mat_a",
        "mat_b",
        "mat_b",
    ]


def test_the_cap_discards_neighbours_before_it_discards_hits():
    neighbours = [
        ScoredChunk(chunk=chunk(10 + i, 10 + i), score=0.99, is_neighbour=True)
        for i in range(5)
    ]
    hits = [ScoredChunk(chunk=chunk(i, i), score=0.1) for i in range(1, 4)]

    merged = merge_findings(
        [finding("filler", *neighbours), finding("real", *hits)], limit=3
    )

    assert len(merged) == 3
    assert all(not scored.is_neighbour for scored in merged)


def test_a_failed_specialist_contributes_nothing_and_breaks_nothing():
    broken = Finding(
        task=ResearchTask(name="risks", query="risks"), error="index unreadable"
    )
    merged = merge_findings(
        [broken, finding("timeline", ScoredChunk(chunk=chunk(1, 0), score=0.5))],
        limit=50,
    )
    assert [scored.chunk.id for scored in merged] == [1]
    assert broken.ok is False


def test_merging_nothing_yields_nothing():
    assert merge_findings([], limit=50) == []


# --- Routing ----------------------------------------------------------------


def test_a_merge_that_found_nothing_routes_to_abort():
    assert route_after_merge({"error": "no context"}) == "abort"


def test_a_merge_with_evidence_routes_to_synthesis():
    assert route_after_merge({"results": [1]}) == "synthesize"


def test_a_question_with_no_matches_never_reaches_the_model():
    assert route_after_qa_retrieval({"results": []}) == "no_context"


def test_a_failed_retrieval_never_reaches_the_model():
    assert route_after_qa_retrieval({"error": "boom", "results": [1]}) == "no_context"


def test_a_question_with_matches_is_answered():
    assert route_after_qa_retrieval({"results": [1]}) == "answer"


# --- Fan-out ----------------------------------------------------------------


def test_each_task_is_dispatched_to_its_own_branch():
    sends = dispatch_research(
        {
            "meeting_id": MEETING,
            "plan": [ResearchTask(name="a", query="x"), ResearchTask(name="b")],
        }
    )
    assert [send.node for send in sends] == ["research", "research"]
    assert [send.arg["task"].name for send in sends] == ["a", "b"]
    assert all(send.arg["meeting_id"] == MEETING for send in sends)


def test_an_empty_plan_skips_straight_to_the_merge():
    assert dispatch_research({"meeting_id": MEETING, "plan": []}) == "merge"


# --- Cross-meeting memory ---------------------------------------------------


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "memory.db")


def make_brief(title: str) -> dict:
    return {"meeting_title": title, "key_topics_today": ["carried over"]}


def test_the_previous_meeting_with_the_same_title_is_found(db: Database):
    old = db.create_meeting("Weekly Sync", date="2026-07-01")
    db.save_brief(meeting_id=old, model="m", brief_dict=make_brief("Weekly Sync"))
    current = db.create_meeting("Weekly Sync", date="2026-07-08")

    found = previous_brief_for_title(db, current, "Weekly Sync")

    assert found is not None
    assert found["key_topics_today"] == ["carried over"]


def test_the_meeting_being_briefed_is_not_its_own_history(db: Database):
    current = db.create_meeting("Weekly Sync")
    db.save_brief(meeting_id=current, model="m", brief_dict=make_brief("Weekly Sync"))

    assert previous_brief_for_title(db, current, "Weekly Sync") is None


def test_a_different_title_is_a_different_series(db: Database):
    old = db.create_meeting("Board Review")
    db.save_brief(meeting_id=old, model="m", brief_dict=make_brief("Board Review"))
    current = db.create_meeting("Weekly Sync")

    assert previous_brief_for_title(db, current, "Weekly Sync") is None


def test_title_matching_ignores_case_and_surrounding_space(db: Database):
    old = db.create_meeting("  weekly SYNC ")
    db.save_brief(meeting_id=old, model="m", brief_dict=make_brief("Weekly Sync"))
    current = db.create_meeting("Weekly Sync")

    assert previous_brief_for_title(db, current, "Weekly Sync") is not None


def test_a_previous_meeting_that_was_never_briefed_yields_nothing(db: Database):
    db.create_meeting("Weekly Sync", date="2026-07-01")
    current = db.create_meeting("Weekly Sync", date="2026-07-08")

    assert previous_brief_for_title(db, current, "Weekly Sync") is None


def test_the_most_recent_previous_meeting_wins(db: Database):
    for index in range(3):
        past = db.create_meeting("Weekly Sync", date=f"2026-07-0{index + 1}")
        db.save_brief(
            meeting_id=past, model="m", brief_dict={"meeting_title": f"run {index}"}
        )
    current = db.create_meeting("Weekly Sync", date="2026-07-08")

    found = previous_brief_for_title(db, current, "Weekly Sync")

    assert found is not None
    assert found["meeting_title"] == "run 2"


def test_an_untitled_lookup_is_not_a_wildcard(db: Database):
    """Matching on '' would make every untitled meeting share a history."""
    old = db.create_meeting("Weekly Sync")
    db.save_brief(meeting_id=old, model="m", brief_dict=make_brief("Weekly Sync"))

    assert previous_brief_for_title(db, "meet_x", "   ") is None
