"""The compatibility facade: the surface `api/` calls.

`tests/test_graph.py` covers the pipeline. What is left to pin here is the
translation at the boundary — which `BriefRun` fields become which dictionary
keys, and the two places where "did it work" is not a single boolean:

* a brief that was generated but not stored is a **success with an error**
* an answer produced after a retrieval failure is a **failure**, even though
  the graph has an answer object for it

Both were decided in Chunk 5 and are easy to erase by accident, so they get a
test each rather than a comment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.copilot_orchestrator import CopilotOrchestrator
from agents.nodes import NO_CONTEXT_ANSWER
from agents.planner import DEFAULT_ROSTER
from core.config import Settings
from core.exceptions import InvalidBriefError, RetrievalError, StorageError
from tests.agentworld import TITLE, brief_payload, build_world, runtime_for
from tests.fakes import HashingEmbedder


@pytest.fixture
def world(tmp_path: Path, settings: Settings, embedder: HashingEmbedder):
    return build_world(tmp_path, settings, embedder)


def orchestrator_for(world, **kwargs) -> CopilotOrchestrator:
    """A facade wired to a throwaway world, with no model or network behind it."""
    return CopilotOrchestrator(runtime=runtime_for(world, **kwargs))


# --- Construction -----------------------------------------------------------


def test_the_facade_shares_one_runtime_with_every_call(world):
    copilot = orchestrator_for(world, responses=[brief_payload(world)])

    assert copilot.db is copilot.runtime.db
    assert copilot.retriever is copilot.runtime.retriever
    assert copilot.synthesizer is copilot.runtime.synthesizer
    assert copilot.provider_name == "gemini"
    assert copilot.model_name == "scripted-test-model"


# --- Brief generation -------------------------------------------------------


def test_generate_brief_returns_the_dictionary_the_ui_reads(world):
    copilot = orchestrator_for(world, responses=[brief_payload(world)])

    result = copilot.generate_brief(world.meeting_id, TITLE, "2026-07-28")

    assert result["success"] is True
    assert result["error"] is None
    assert result["brief"].meeting_title == TITLE
    assert result["brief_id"]
    assert result["provider"] == "gemini"
    assert result["model"] == "scripted-test-model"


def test_the_trace_comes_back_with_the_brief(world):
    """The trace is the replacement for the `log_message` calls nobody saw."""
    copilot = orchestrator_for(world, responses=[brief_payload(world)])

    result = copilot.generate_brief(world.meeting_id, TITLE, "2026-07-28")

    joined = "\n".join(result["notes"])
    for step in ("memory:", "supervisor:", "merge:", "synthesis:", "persistence:"):
        assert step in joined
    assert result["plan"] == [task.name for task in DEFAULT_ROSTER]
    assert result["plan_source"] == "default"
    assert result["chunks"] > 0


def test_a_brief_that_could_not_be_stored_is_a_success_with_an_error(world, monkeypatch):
    """`success` means a brief exists. Callers must read `error` too."""
    copilot = orchestrator_for(world, responses=[brief_payload(world)])

    def refuse(**kwargs):
        raise StorageError("database is locked")

    monkeypatch.setattr(copilot.db, "save_brief", refuse)

    result = copilot.generate_brief(world.meeting_id, TITLE, "2026-07-28")

    assert result["success"] is True
    assert result["brief"] is not None
    assert result["brief_id"] is None
    assert "could not be stored" in result["error"]


def test_a_meeting_with_no_materials_fails_without_calling_the_model(world):
    """No responses are scripted, so any model call raises."""
    empty = world.db.create_meeting("Empty Meeting")
    copilot = orchestrator_for(world, responses=[])

    result = copilot.generate_brief(empty, "Empty Meeting", "2026-07-28")

    assert result["success"] is False
    assert result["brief"] is None
    assert "nothing to ground it in" in result["error"]


def test_a_failed_specialist_is_named_in_the_result(world, monkeypatch):
    copilot = orchestrator_for(world, responses=[brief_payload(world)])
    real_recall = copilot.retriever.recall

    def flaky(meeting_id, query="", k=None, **kwargs):
        if "risks" in query:
            raise RetrievalError("index unreadable")
        return real_recall(meeting_id, query=query, k=k, **kwargs)

    monkeypatch.setattr(copilot.retriever, "recall", flaky)

    result = copilot.generate_brief(world.meeting_id, TITLE, "2026-07-28")

    assert result["success"] is True
    assert result["failed_tasks"] == ["risks"]


# --- Question answering -----------------------------------------------------


def test_answer_question_returns_the_answer_and_its_sources(world):
    copilot = orchestrator_for(world, responses=["Priya owns the capacity model."])

    result = copilot.answer_question(world.meeting_id, "Who owns the capacity model?")

    assert result["success"] is True
    assert result["answer"] == "Priya owns the capacity model."
    assert result["sources"]
    assert all("#c" in source for source in result["sources"])
    assert result["error"] is None


def test_a_question_with_nothing_to_answer_from_still_succeeds(world):
    """Nothing retrieved is a real answer, not an error — and costs no model call."""
    empty = world.db.create_meeting("Empty Meeting")
    copilot = orchestrator_for(world, responses=[])

    result = copilot.answer_question(empty, "What happened?")

    assert result["success"] is True
    assert result["answer"] == NO_CONTEXT_ANSWER
    assert result["sources"] == []


def test_a_retrieval_failure_is_reported_rather_than_dressed_as_no_answer(
    world, monkeypatch
):
    """The graph answers from the `no_context` node either way; the facade does not."""
    copilot = orchestrator_for(world, responses=[])

    def broken(*args, **kwargs):
        raise RetrievalError("index unreadable")

    monkeypatch.setattr(copilot.retriever, "recall", broken)

    result = copilot.answer_question(world.meeting_id, "What are the risks?")

    assert result["success"] is False
    assert result["error"] == "index unreadable"


def test_an_empty_question_is_refused(world):
    copilot = orchestrator_for(world, responses=[])

    result = copilot.answer_question(world.meeting_id, "   ")

    assert result["success"] is False
    assert result["error"] == "Cannot answer an empty question."


# --- Ingestion --------------------------------------------------------------


def test_ingesting_a_document_stores_chunks_and_indexes_them(world):
    copilot = orchestrator_for(world, responses=[])
    meeting_id = world.db.create_meeting("Fresh Meeting")

    result = copilot.ingest_material(
        b"The budget was approved and the launch date is in March.",
        "notes.txt",
        meeting_id,
    )

    assert result["success"] is True
    assert result["chunks"] > 0
    assert world.db.count_chunks(meeting_id) == result["chunks"]
    # Indexed, not merely stored: the text is searchable straight away.
    assert copilot.retriever.recall(meeting_id, query="launch date", k=2)


def test_re_uploading_the_same_file_replaces_it_rather_than_duplicating_it(world):
    """The Streamlit UI used to add the row itself and then ask for indexing
    separately, so a second upload left two copies of the document."""
    copilot = orchestrator_for(world, responses=[])
    meeting_id = world.db.create_meeting("Fresh Meeting")
    payload = b"The budget was approved."

    first = copilot.ingest_material(payload, "notes.txt", meeting_id)
    second = copilot.ingest_material(payload, "notes.txt", meeting_id)

    assert first["material_id"] == second["material_id"]
    assert len(world.db.get_materials(meeting_id)) == 1
    assert world.db.count_chunks(meeting_id) == second["chunks"]


def test_a_changed_file_replaces_the_old_text_and_its_vectors(world):
    copilot = orchestrator_for(world, responses=[])
    meeting_id = world.db.create_meeting("Fresh Meeting")

    copilot.ingest_material(b"The budget was approved.", "notes.txt", meeting_id)
    copilot.ingest_material(
        b"The budget was rejected and the project is paused.", "notes.txt", meeting_id
    )

    materials = world.db.get_materials(meeting_id)
    assert len(materials) == 1
    assert "rejected" in world.db.get_material(materials[0].id).text

    chunks = world.db.get_chunks_for_meeting(meeting_id)
    assert all("approved" not in chunk.text for chunk in chunks)
    # The superseded vectors went with the chunks, so the index still matches
    # the store and retrieval does not raise.
    assert copilot.retriever.recall(meeting_id, query="budget", k=2)


def test_an_unreadable_file_is_reported_not_stored(world):
    copilot = orchestrator_for(world, responses=[])
    meeting_id = world.db.create_meeting("Fresh Meeting")

    result = copilot.ingest_material(b"\x00\x01", "mystery.xyz", meeting_id)

    assert result["success"] is False
    assert "No readable text" in result["error"]
    assert world.db.get_materials(meeting_id) == []


def test_ingesting_into_a_meeting_that_does_not_exist_is_an_error_not_a_crash(world):
    copilot = orchestrator_for(world, responses=[])

    result = copilot.ingest_material(b"Some notes.", "notes.txt", "meeting_nonexistent")

    assert result["success"] is False
    assert "meeting_nonexistent" in result["error"]


# --- Retrieval and memory ---------------------------------------------------


def test_recall_context_tool_renders_the_prompt_blocks(world):
    copilot = orchestrator_for(world, responses=[])

    result = copilot.recall_context_tool(world.meeting_id, k=3)

    assert result["success"] is True
    assert result["chunks"] > 0
    assert "Source:" in result["context_blocks"]
    assert all("#c" in ref for ref in result["sources"])


def test_recall_context_tool_on_an_empty_meeting_is_unsuccessful_but_not_an_error(world):
    copilot = orchestrator_for(world, responses=[])
    empty = world.db.create_meeting("Empty Meeting")

    result = copilot.recall_context_tool(empty)

    assert result["success"] is False
    assert result["chunks"] == 0


def test_recall_previous_brief_returns_the_stored_brief(world):
    copilot = orchestrator_for(world, responses=[brief_payload(world)])
    copilot.generate_brief(world.meeting_id, TITLE, "2026-07-28")

    recalled = copilot.recall_previous_brief(world.meeting_id)

    assert recalled is not None
    assert recalled.meeting_title == TITLE


def test_recall_previous_brief_is_none_when_there_is_no_history(world):
    copilot = orchestrator_for(world, responses=[])

    assert copilot.recall_previous_brief(world.meeting_id) is None


def test_a_stored_brief_that_no_longer_validates_says_so(world):
    """Briefs are persisted as raw dicts, so history can outlive a schema.

    Reporting that is better than returning `None`, which the UI shows as "no
    previous brief found" — a different and misleading statement.
    """
    copilot = orchestrator_for(world, responses=[])
    world.db.save_brief(
        meeting_id=world.meeting_id, model="m", brief_dict={"meeting_title": ""}
    )

    with pytest.raises(InvalidBriefError, match="does not satisfy"):
        copilot.recall_previous_brief(world.meeting_id)
