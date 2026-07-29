"""The supervisor: a tool-calling agent that decides what to research.

This is the one node where a model is asked for judgment rather than prose. It
probes the materials with `agents.tools`, then returns a `ResearchPlan` — the
set of questions the specialist nodes will each carry out in parallel.

**It is never load-bearing.** `DEFAULT_ROSTER` below is a complete plan on its
own, and every failure path in `plan_research` returns it. A supervisor that
times out, returns nothing usable, or is simply switched off costs the brief its
tailoring, not its existence. That is deliberate: the previous version of this
codebase had no planning step at all and still produced briefs, so a planner
that can fail the run would be a regression dressed as an upgrade.

Why the roster looks like this: `Retriever.recall` treats an empty query as a
coverage sweep across the whole meeting, which is what Chunk 3 built in place of
the old "return the entire document" short-circuit. That sweep is what keeps the
recap grounded in the meeting as a whole. The four targeted queries around it
are the sections `prompts/user_prompt.txt` actually asks the writer to fill in —
plan and prompt are meant to be read together.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from agents.state import ResearchPlan, ResearchTask
from agents.tools import research_tools
from core.logging_config import get_logger
from core.prompts import PLANNER_SYSTEM, PLANNER_USER, render_prompt
from core.synthesis import format_previous_brief

if TYPE_CHECKING:
    from agents.runtime import CopilotRuntime

logger = get_logger(__name__)


#: The plan that runs when nobody plans. Ordered sweep-first so that if the
#: merge cap ever bites, the coverage of the meeting is what survives.
DEFAULT_ROSTER: tuple[ResearchTask, ...] = (
    ResearchTask(
        name="overview",
        query="",
        rationale="Coverage sweep across the whole meeting, so the recap is not "
        "built only from what the targeted questions happened to match.",
    ),
    ResearchTask(
        name="action_items",
        query=(
            "open action items, outstanding tasks, who is responsible, owner, "
            "assigned to, follow up, still to do"
        ),
        rationale="Section 2 of the brief is the outstanding work and its owners.",
    ),
    ResearchTask(
        name="decisions",
        query=(
            "decisions made, agreed, we will go with, approved, signed off, "
            "conclusion reached, chosen approach"
        ),
        rationale="The recap turns on what was actually settled last time.",
    ),
    ResearchTask(
        name="risks",
        query=(
            "risks, blockers, concerns, problems, dependencies, delays, "
            "issues raised, disagreement, pushback"
        ),
        rationale="An executive reads a brief for what might go wrong; these "
        "are also the claims the writer is told to evidence hardest.",
    ),
    ResearchTask(
        name="timeline",
        query=(
            "deadline, due date, milestone, schedule, timeline, next meeting, "
            "by end of week, target date, launch date"
        ),
        rationale="Populates action-item due dates and the brief's time window.",
    ),
)


def default_plan(*, k: int | None = None) -> list[ResearchTask]:
    """A fresh copy of the standing roster."""
    if k is None:
        return list(DEFAULT_ROSTER)
    return [task.model_copy(update={"k": k}) for task in DEFAULT_ROSTER]


def plan_research(
    runtime: CopilotRuntime,
    *,
    meeting_id: str,
    title: str,
    date: str | None = None,
    previous_brief: Any | None = None,
) -> tuple[list[ResearchTask], str, str]:
    """Decide what to research for this meeting.

    Returns `(tasks, source, rationale)` where `source` is `"supervisor"` or
    `"default"`. Never raises: every failure degrades to the roster, with the
    reason recorded in `rationale` so the trace says what happened rather than
    silently looking like a deliberate choice.
    """
    roster = default_plan()
    if runtime.planner_model is None:
        return roster, "default", "Supervisor disabled; ran the standing roster."

    try:
        plan = _invoke_supervisor(
            runtime,
            meeting_id=meeting_id,
            title=title,
            date=date,
            previous_brief=previous_brief,
        )
    except Exception as error:  # provider errors, tool errors, malformed plans
        logger.warning(
            "Supervisor failed to plan research for '%s' (%s); "
            "falling back to the standing roster.",
            title,
            error,
        )
        return roster, "default", f"Supervisor failed ({error}); ran the standing roster."

    tasks = _usable_tasks(plan.tasks, limit=runtime.planner_max_tasks)
    if not tasks:
        logger.warning(
            "Supervisor returned no usable tasks for '%s'; using the roster.", title
        )
        return roster, "default", "Supervisor returned no usable tasks."

    return tasks, "supervisor", plan.rationale


# --- Internals --------------------------------------------------------------


def _invoke_supervisor(
    runtime: CopilotRuntime,
    *,
    meeting_id: str,
    title: str,
    date: str | None,
    previous_brief: Any | None,
) -> ResearchPlan:
    """Run the agent and return whatever plan it produced."""
    from langchain.agents import create_agent
    from langchain_core.messages import HumanMessage

    agent = create_agent(
        runtime.planner_model,
        research_tools(runtime, meeting_id),
        system_prompt=render_prompt(PLANNER_SYSTEM),
        response_format=ResearchPlan,
        name="research_supervisor",
    )

    user_prompt = render_prompt(
        PLANNER_USER,
        title=title,
        date=date or "Not specified",
        materials=_material_summary(runtime, meeting_id),
        previous_meeting=format_previous_brief(previous_brief),
        default_tasks=_roster_summary(),
    )

    result = agent.invoke({"messages": [HumanMessage(content=user_prompt)]})
    plan = result.get("structured_response") if isinstance(result, dict) else None
    if not isinstance(plan, ResearchPlan):
        raise TypeError(
            f"Supervisor returned {type(plan).__name__} rather than a ResearchPlan."
        )
    return plan


def _usable_tasks(
    tasks: Sequence[ResearchTask], *, limit: int
) -> list[ResearchTask]:
    """Drop the duplicates and the noise out of a proposed plan.

    Two tasks with the same query return the same passages, so the second one
    buys nothing and costs a retrieval. More than one sweep is the same problem
    in a more expensive form: each sweep samples the entire meeting.
    """
    kept: list[ResearchTask] = []
    seen_queries: set[str] = set()
    seen_names: set[str] = set()
    has_sweep = False

    for task in tasks:
        if len(kept) >= limit:
            break

        name = task.name.strip() or f"task_{len(kept) + 1}"
        query = " ".join(task.query.split())

        if not query:
            if has_sweep:
                continue
            has_sweep = True
        elif query.lower() in seen_queries:
            continue
        else:
            seen_queries.add(query.lower())

        if name in seen_names:
            name = f"{name}_{len(kept) + 1}"
        seen_names.add(name)

        kept.append(task.model_copy(update={"name": name, "query": query}))

    return kept


def _material_summary(runtime: CopilotRuntime, meeting_id: str) -> str:
    """The materials list, inlined into the prompt.

    The supervisor also has `list_materials` as a tool, but giving it the answer
    up front means a competent model can skip a round trip, and a meeting with
    no materials is visible without one.
    """
    materials = runtime.db.get_materials(meeting_id)
    if not materials:
        return "(none attached to this meeting)"
    return "\n".join(
        f"- {m.filename or m.id} [{m.media_type or 'unknown'}] "
        f"({m.char_count:,} characters)"
        for m in materials
    )


def _roster_summary() -> str:
    return "\n".join(
        f"- {task.name}: {task.query or '(coverage sweep, no query)'}"
        for task in DEFAULT_ROSTER
    )
