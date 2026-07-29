"""The supervisor: what it plans, and what happens when it does not.

The load-bearing property here is not that the agent plans well — that is the
model's job — but that it is **never load-bearing**. Every path through
`plan_research` returns a usable plan, because a briefing tool that stops
working when the planning call times out is worse than one that never planned.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.planner import (
    DEFAULT_ROSTER,
    _usable_tasks,
    default_plan,
    plan_research,
)
from agents.state import ResearchTask
from core.config import Settings
from tests.agentworld import build_world, runtime_for
from tests.fakes import HashingEmbedder


@pytest.fixture
def world(tmp_path: Path, settings: Settings, embedder: HashingEmbedder):
    return build_world(tmp_path, settings, embedder)


def plan_call(runtime, world):
    return plan_research(
        runtime, meeting_id=world.meeting_id, title="Platform Steering Committee"
    )


# --- The standing roster ----------------------------------------------------


def test_the_roster_contains_exactly_one_coverage_sweep():
    """More than one sweep is the same whole-meeting sample, paid for twice."""
    sweeps = [task for task in DEFAULT_ROSTER if task.is_sweep]
    assert len(sweeps) == 1
    assert sweeps[0].name == "overview"


def test_the_roster_asks_distinct_questions():
    names = [task.name for task in DEFAULT_ROSTER]
    queries = [task.query for task in DEFAULT_ROSTER if task.query]
    assert len(set(names)) == len(names)
    assert len(set(queries)) == len(queries)


def test_default_plan_hands_back_a_copy_callers_can_reorder():
    first = default_plan()
    first.reverse()
    assert [task.name for task in default_plan()] == [t.name for t in DEFAULT_ROSTER]


def test_default_plan_can_override_the_hit_budget():
    assert all(task.k == 3 for task in default_plan(k=3))


# --- Plan hygiene -----------------------------------------------------------


def test_two_tasks_with_the_same_query_become_one():
    kept = _usable_tasks(
        [
            ResearchTask(name="a", query="open risks"),
            ResearchTask(name="b", query="OPEN   RISKS"),
        ],
        limit=10,
    )
    assert [task.name for task in kept] == ["a"]


def test_a_second_coverage_sweep_is_dropped():
    kept = _usable_tasks(
        [
            ResearchTask(name="sweep_one", query=""),
            ResearchTask(name="sweep_two", query="  "),
            ResearchTask(name="risks", query="risks"),
        ],
        limit=10,
    )
    assert [task.name for task in kept] == ["sweep_one", "risks"]


def test_an_over_eager_plan_is_truncated_not_rejected():
    proposed = [ResearchTask(name=f"t{i}", query=f"query {i}") for i in range(20)]
    assert len(_usable_tasks(proposed, limit=4)) == 4


def test_repeated_names_are_disambiguated_so_findings_stay_distinguishable():
    kept = _usable_tasks(
        [
            ResearchTask(name="risks", query="delivery risk"),
            ResearchTask(name="risks", query="financial risk"),
        ],
        limit=10,
    )
    assert [task.name for task in kept] == ["risks", "risks_2"]


def test_an_unnamed_task_is_given_a_name():
    kept = _usable_tasks([ResearchTask(name="  ", query="anything")], limit=10)
    assert kept[0].name == "task_1"


# --- The agent path ---------------------------------------------------------


PLAN_CALL = {
    "name": "ResearchPlan",
    "args": {
        "tasks": [
            {"name": "overview", "query": "", "rationale": "sweep"},
            {"name": "migration", "query": "database migration cutover"},
        ],
        "rationale": "The minutes are dominated by the migration decision.",
    },
}


def test_the_supervisor_is_given_the_tools_it_needs_to_look_first(world):
    runtime = runtime_for(
        world, planner_responses=[{"name": "list_materials", "args": {}}, PLAN_CALL]
    )

    plan_call(runtime, world)

    assert "list_materials" in runtime.planner_model.bound_tool_names
    assert "search_meeting" in runtime.planner_model.bound_tool_names


def test_a_supervisor_plan_replaces_the_roster(world):
    runtime = runtime_for(world, planner_responses=[PLAN_CALL])

    tasks, source, rationale = plan_call(runtime, world)

    assert source == "supervisor"
    assert [task.name for task in tasks] == ["overview", "migration"]
    assert "migration" in rationale


def test_the_supervisor_can_probe_before_committing(world):
    runtime = runtime_for(
        world,
        planner_responses=[
            {"name": "search_meeting", "args": {"query": "risks and blockers"}},
            PLAN_CALL,
        ],
    )

    _, source, _ = plan_call(runtime, world)

    assert source == "supervisor"
    # Two model turns: the probe, then the plan.
    assert runtime.planner_model.call_count == 2


def test_a_supervisor_that_raises_falls_back_to_the_roster(world):
    # An empty script exhausts on the first call, which is a stand-in for any
    # provider failure: the run must still produce a plan.
    runtime = runtime_for(world, planner_responses=[])

    tasks, source, rationale = plan_call(runtime, world)

    assert source == "default"
    assert [task.name for task in tasks] == [t.name for t in DEFAULT_ROSTER]
    assert "failed" in rationale.lower()


def test_a_supervisor_that_plans_nothing_falls_back_to_the_roster(world):
    runtime = runtime_for(
        world,
        planner_responses=[{"name": "ResearchPlan", "args": {"tasks": [], "rationale": ""}}],
    )

    tasks, source, _ = plan_call(runtime, world)

    assert source == "default"
    assert len(tasks) == len(DEFAULT_ROSTER)


def test_a_supervisor_plan_is_capped_at_the_configured_ceiling(world):
    runtime = runtime_for(
        world,
        planner_responses=[
            {
                "name": "ResearchPlan",
                "args": {
                    "tasks": [
                        {"name": f"t{i}", "query": f"topic number {i}"}
                        for i in range(30)
                    ]
                },
            }
        ],
    )
    runtime.planner_max_tasks = 3

    tasks, source, _ = plan_call(runtime, world)

    assert source == "supervisor"
    assert len(tasks) == 3


def test_with_the_supervisor_switched_off_no_model_is_consulted(world):
    runtime = runtime_for(world)  # planner_responses omitted -> no planner

    tasks, source, rationale = plan_call(runtime, world)

    assert runtime.planner_model is None
    assert source == "default"
    assert [task.name for task in tasks] == [t.name for t in DEFAULT_ROSTER]
    assert "disabled" in rationale.lower()


# --- Runtime assembly -------------------------------------------------------


def build_runtime(world, embedder, *, settings=None, **kwargs):
    from agents.runtime import CopilotRuntime
    from tests.fakes import ScriptedChatModel

    return CopilotRuntime.build(
        db=world.db,
        settings=settings or world.settings,
        chat_model=ScriptedChatModel([]),
        embedder=embedder,
        **kwargs,
    )


def test_the_supervisor_shares_the_writers_client_by_default(world, embedder):
    """One provider connection per run, which is why `Synthesizer` takes a model."""
    runtime = build_runtime(world, embedder)

    assert runtime.plans_with_llm
    assert runtime.planner_model is runtime.synthesizer.chat_model


def test_plan_with_llm_false_leaves_no_planner_to_call(world, embedder):
    runtime = build_runtime(world, embedder, plan_with_llm=False)

    assert runtime.planner_model is None
    assert not runtime.plans_with_llm


def test_the_setting_decides_when_the_caller_does_not(world, embedder):
    runtime = build_runtime(
        world, embedder, settings=world.settings.model_copy(update={"plan_with_llm": False})
    )
    assert runtime.planner_model is None


def test_a_separate_planner_model_can_be_supplied(world, embedder):
    from tests.fakes import ScriptedToolCallingModel

    cheap = ScriptedToolCallingModel(responses=[])
    runtime = build_runtime(world, embedder, planner_model=cheap)

    assert runtime.planner_model is cheap
    assert runtime.synthesizer.chat_model is not cheap
