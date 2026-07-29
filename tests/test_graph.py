"""The graphs end to end, against a real database, index and retriever.

Only the encoder and the chat model are doubles. Everything else — chunking,
FAISS, the chunk store, citation resolution, persistence — is the production
code path, so these tests fail if the pipeline breaks anywhere along it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.graph import (
    build_brief_graph,
    build_qa_graph,
    run_brief_graph,
    run_qa_graph,
)
from agents.nodes import NO_CONTEXT_ANSWER
from agents.planner import DEFAULT_ROSTER
from agents.state import ResearchTask
from core.config import Settings
from core.exceptions import RetrievalError
from tests.agentworld import TITLE, brief_payload, build_world, runtime_for
from tests.fakes import HashingEmbedder

# Paragraph -> chunk index, as `tests.agentworld` ingests them. Pinned here so a
# test can name the chunk it expects a specialist to find.
ACTION_ITEMS_CHUNK = 1
RISKS_CHUNK = 2
TIMELINE_CHUNK = 3


@pytest.fixture
def world(tmp_path: Path, settings: Settings, embedder: HashingEmbedder):
    return build_world(tmp_path, settings, embedder)


@pytest.fixture
def isolated(world):
    """Settings with neighbour expansion off.

    Neighbours deliberately overlap, which is the point of them — but it makes
    "only this specialist found that chunk" impossible to state. Tests that
    assert on which specialist found what turn them off.
    """
    return world.settings.model_copy(update={"neighbour_radius": 0})


def brief_run(world, runtime, **kwargs):
    return run_brief_graph(
        runtime,
        meeting_id=world.meeting_id,
        title=TITLE,
        date="2026-07-28",
        **kwargs,
    )


# --- The happy path ---------------------------------------------------------


def test_a_brief_is_generated_stored_and_reported(world):
    runtime = runtime_for(
        world, responses=[brief_payload(world, sources=[world.source_ref(RISKS_CHUNK)])]
    )

    run = brief_run(world, runtime)

    assert run.ok
    assert run.error is None
    assert run.brief.meeting_title == TITLE
    assert run.brief_id
    stored = world.db.get_latest_brief(world.meeting_id)
    assert stored is not None
    assert stored.brief["meeting_title"] == TITLE


def test_the_standing_roster_runs_when_no_supervisor_is_configured(world):
    runtime = runtime_for(world, responses=[brief_payload(world)])

    run = brief_run(world, runtime)

    assert run.plan_source == "default"
    assert [task.name for task in run.plan] == [t.name for t in DEFAULT_ROSTER]
    assert len(run.findings) == len(DEFAULT_ROSTER)


def test_every_planned_query_is_actually_issued(world):
    """Chunk 3 left retrieval being called with an empty query and nothing else.

    The specialists exist to fix that, so the test is that the real queries
    reach the embedder rather than that the graph merely ran.
    """
    runtime = runtime_for(world, responses=[brief_payload(world)])

    brief_run(world, runtime)

    encoded = world.embedder.encoded_texts
    for task in DEFAULT_ROSTER:
        if task.is_sweep:
            continue
        assert task.query in encoded, f"{task.name} never reached retrieval"


def test_the_trace_records_what_each_step_did(world):
    runtime = runtime_for(world, responses=[brief_payload(world)])

    run = brief_run(world, runtime)

    joined = "\n".join(run.notes)
    assert "memory:" in joined
    assert "supervisor:" in joined
    assert "merge:" in joined
    assert "synthesis:" in joined
    assert "persistence:" in joined


# --- Citations across the merge ---------------------------------------------


def test_a_citation_only_one_specialist_found_survives_the_merge(world, isolated):
    """The reason `resolve_evidence` runs after the merge and not per branch.

    The risks specialist is the only one that retrieves the risks paragraph. If
    citation resolution ran against a single branch's chunks, a perfectly good
    citation would be discarded as fabricated.
    """
    risks_ref = world.source_ref(RISKS_CHUNK)
    runtime = runtime_for(
        world,
        responses=[brief_payload(world, sources=[risks_ref])],
        settings=isolated,
    )

    run = brief_run(
        world,
        runtime,
        plan=[
            ResearchTask(name="action_items", query="outstanding action items owner", k=1),
            ResearchTask(name="risks", query="risks blockers concerns pushback", k=1),
        ],
    )

    assert run.ok
    assert run.synthesis.dropped_sources == ()
    [evidence] = run.brief.evidence
    assert evidence.source == risks_ref
    # Resolved to a real row, not merely echoed back.
    assert evidence.chunk_id is not None
    assert world.db.get_chunk(evidence.chunk_id).chunk_index == RISKS_CHUNK


def test_that_same_citation_is_dropped_when_nobody_retrieved_it(world, isolated):
    """The other half of the previous test: resolution is a lookup, not a rubber stamp."""
    runtime = runtime_for(
        world,
        responses=[brief_payload(world, sources=[world.source_ref(RISKS_CHUNK)])],
        settings=isolated,
    )

    run = brief_run(
        world,
        runtime,
        plan=[
            ResearchTask(name="action_items", query="outstanding action items owner", k=1)
        ],
    )

    assert run.ok
    assert run.brief.evidence == []
    assert run.synthesis.dropped_sources == (world.source_ref(RISKS_CHUNK),)


def test_an_invented_citation_is_still_dropped(world):
    runtime = runtime_for(
        world, responses=[brief_payload(world, sources=["fabricated#c99"])]
    )

    run = brief_run(world, runtime)

    assert run.ok
    assert run.brief.evidence == []
    assert run.synthesis.dropped_sources == ("fabricated#c99",)


# --- Degradation ------------------------------------------------------------


def test_one_failing_specialist_costs_a_line_of_enquiry_not_the_run(world, monkeypatch):
    """The reason the specialists fan out rather than run in sequence."""
    runtime = runtime_for(world, responses=[brief_payload(world)])
    real_recall = runtime.retriever.recall

    def flaky(meeting_id, query="", k=None, **kwargs):
        if "risks" in query:
            raise RetrievalError("index unreadable")
        return real_recall(meeting_id, query=query, k=k, **kwargs)

    monkeypatch.setattr(runtime.retriever, "recall", flaky)

    run = brief_run(world, runtime)

    assert run.ok
    assert run.failed_tasks == ("risks",)
    assert any("risks: failed" in note for note in run.notes)
    assert len(run.results) > 0


def test_a_meeting_with_nothing_in_it_aborts_without_calling_the_model(
    world, tmp_path, settings, embedder
):
    """`Synthesizer.brief` refuses ungrounded generation; the graph stops earlier.

    The scripted model has no responses configured, so it raises if invoked.
    Reaching the end without that exception is the assertion.
    """
    empty_meeting = world.db.create_meeting("Empty Meeting")
    runtime = runtime_for(world, responses=[])

    run = run_brief_graph(
        runtime, meeting_id=empty_meeting, title="Empty Meeting", date=None
    )

    assert not run.ok
    assert run.brief is None
    assert run.brief_id is None
    assert "nothing to ground it in" in run.error
    assert any("aborted" in note for note in run.notes)


def test_a_brief_that_cannot_be_stored_is_still_returned(world, monkeypatch):
    from core.exceptions import StorageError

    runtime = runtime_for(world, responses=[brief_payload(world)])

    def refuse(**kwargs):
        raise StorageError("database is locked")

    monkeypatch.setattr(runtime.db, "save_brief", refuse)

    run = brief_run(world, runtime)

    assert run.ok  # the document exists
    assert run.brief_id is None
    assert "could not be stored" in run.error


def test_a_model_that_returns_prose_instead_of_a_brief_fails_loudly(world):
    runtime = runtime_for(world, responses=["Here is your brief, in Markdown!"])

    run = brief_run(world, runtime)

    assert not run.ok
    assert run.error
    assert run.brief_id is None


# --- Plans ------------------------------------------------------------------


def test_the_caller_can_pin_the_plan(world):
    runtime = runtime_for(world, responses=[brief_payload(world)])

    run = brief_run(
        world, runtime, plan=[ResearchTask(name="only_this", query="migration decision")]
    )

    assert run.plan_source == "caller"
    assert [finding.task.name for finding in run.findings] == ["only_this"]


def test_a_supervisors_plan_drives_the_specialists(world):
    runtime = runtime_for(
        world,
        responses=[brief_payload(world)],
        planner_responses=[
            {
                "name": "ResearchPlan",
                "args": {
                    "tasks": [
                        {"name": "overview", "query": ""},
                        {"name": "migration", "query": "managed database migration"},
                    ],
                    "rationale": "The minutes turn on the migration decision.",
                },
            }
        ],
    )

    run = brief_run(world, runtime)

    assert run.plan_source == "supervisor"
    assert sorted(finding.task.name for finding in run.findings) == [
        "migration",
        "overview",
    ]
    assert "migration" in run.plan_rationale
    assert "managed database migration" in world.embedder.encoded_texts


def test_the_merged_context_is_capped(world):
    runtime = runtime_for(
        world,
        responses=[brief_payload(world)],
        settings=world.settings.model_copy(update={"brief_max_chunks": 2}),
    )

    run = brief_run(world, runtime)

    assert len(run.results) == 2


# --- Cross-meeting memory ---------------------------------------------------


def test_a_previous_brief_reaches_the_writer(tmp_path, settings, embedder):
    """The memory node's output has to arrive in the prompt, not just in state."""
    world = build_world(tmp_path, settings, embedder)
    earlier = world.db.create_meeting(TITLE, date="2026-07-01")
    world.db.save_brief(
        meeting_id=earlier,
        model="m",
        brief_dict={
            "meeting_title": TITLE,
            "last_meeting_recap": "We deferred the observability spend.",
        },
    )

    runtime = runtime_for(world, responses=[brief_payload(world)])
    run = brief_run(world, runtime)

    assert run.ok
    prompt = runtime.synthesizer.chat_model.last_prompt_text
    assert "We deferred the observability spend." in prompt
    assert any("carried context" in note for note in run.notes)


def test_a_first_meeting_says_so_rather_than_inventing_history(world):
    runtime = runtime_for(world, responses=[brief_payload(world)])

    run = brief_run(world, runtime)

    prompt = runtime.synthesizer.chat_model.last_prompt_text
    assert "No previous meeting on record" in prompt
    assert any("no previous meeting" in note for note in run.notes)


# --- Question answering -----------------------------------------------------


def test_a_question_is_answered_from_the_retrieved_passages(world):
    runtime = runtime_for(world, responses=["Priya owns the capacity model."])

    run = run_qa_graph(
        runtime, meeting_id=world.meeting_id, question="Who owns the capacity model?"
    )

    assert run.ok
    assert run.text == "Priya owns the capacity model."
    assert run.sources
    assert all("#c" in source for source in run.sources)


def test_the_question_reaches_the_model_with_its_context(world):
    runtime = runtime_for(world, responses=["An answer."])

    run_qa_graph(
        runtime, meeting_id=world.meeting_id, question="What are the open risks?"
    )

    prompt = runtime.synthesizer.chat_model.last_prompt_text
    assert "What are the open risks?" in prompt
    assert "Source:" in prompt


def test_a_question_about_an_empty_meeting_does_not_reach_the_model(world):
    empty = world.db.create_meeting("Empty Meeting")
    runtime = runtime_for(world, responses=[])  # any model call raises

    run = run_qa_graph(runtime, meeting_id=empty, question="What happened?")

    assert run.ok
    assert run.text == NO_CONTEXT_ANSWER
    assert run.sources == ()


def test_an_empty_question_is_refused_before_retrieval(world):
    runtime = runtime_for(world, responses=[])

    run = run_qa_graph(runtime, meeting_id=world.meeting_id, question="   ")

    assert run.error == "Cannot answer an empty question."
    assert run.text == NO_CONTEXT_ANSWER


# --- Compilation and checkpointing ------------------------------------------


def test_the_brief_graph_has_the_shape_it_claims():
    graph = build_brief_graph().get_graph()
    nodes = set(graph.nodes)

    assert {
        "memory",
        "supervisor",
        "research",
        "merge",
        "synthesize",
        "persist",
        "abort",
    } <= nodes


def test_a_checkpointed_run_leaves_its_state_under_the_thread_id(world):
    from langgraph.checkpoint.memory import InMemorySaver

    graph = build_brief_graph(checkpointer=InMemorySaver())
    runtime = runtime_for(world, responses=[brief_payload(world)])

    run = brief_run(world, runtime, graph=graph, thread_id="thread-1")
    assert run.ok

    saved = graph.get_state({"configurable": {"thread_id": "thread-1"}})
    assert saved.values["brief_id"] == run.brief_id
    assert len(saved.values["findings"]) == len(DEFAULT_ROSTER)


def test_separate_threads_do_not_share_state(world):
    from langgraph.checkpoint.memory import InMemorySaver

    graph = build_qa_graph(checkpointer=InMemorySaver())
    runtime = runtime_for(world, responses=["First answer.", "Second answer."])

    run_qa_graph(
        runtime,
        meeting_id=world.meeting_id,
        question="Who owns the capacity model?",
        graph=graph,
        thread_id="a",
    )
    run_qa_graph(
        runtime,
        meeting_id=world.meeting_id,
        question="What is the deadline?",
        graph=graph,
        thread_id="b",
    )

    first = graph.get_state({"configurable": {"thread_id": "a"}})
    second = graph.get_state({"configurable": {"thread_id": "b"}})

    assert first.values["question"] == "Who owns the capacity model?"
    assert second.values["question"] == "What is the deadline?"


def test_an_uncheckpointed_graph_keeps_nothing_between_runs(world):
    """The default graph is shared process-wide, so it must be stateless."""
    runtime = runtime_for(
        world, responses=[brief_payload(world), brief_payload(world)]
    )

    first = brief_run(world, runtime)
    second = brief_run(world, runtime)

    assert len(first.findings) == len(DEFAULT_ROSTER)
    assert len(second.findings) == len(DEFAULT_ROSTER)
