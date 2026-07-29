"""The node bodies. One function per step, each a pure function of state.

Nodes take `(state, runtime)` and return a **partial** state update; LangGraph
merges it. None of them mutate what they are handed, and none of them build
their own collaborators — everything comes off `runtime.context`, which is what
makes the whole pipeline drivable against a temporary database and a scripted
model.

The error convention throughout: a *domain* failure (`CopilotError` and its
subclasses) is caught and written into state, because the graph knows how to
continue or stop deliberately. Anything else propagates — a `TypeError` in this
module is a bug in this module, and swallowing it into `state["error"]` would
turn it into a support ticket about the model.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from langgraph.runtime import Runtime
from langgraph.types import Send

from agents.planner import default_plan, plan_research
from agents.runtime import CopilotRuntime
from agents.state import (
    BriefState,
    Finding,
    QaState,
    ResearchRequest,
    ResearchTask,
    describe_plan,
    note,
)
from core.db import Database
from core.exceptions import CopilotError
from core.logging_config import get_logger
from core.recall import format_context_blocks
from core.schema import ScoredChunk

logger = get_logger(__name__)

NO_CONTEXT_ANSWER = (
    "I could not find relevant information in the documents to answer this question."
)


# --- Memory -----------------------------------------------------------------


def previous_brief_for_title(
    db: Database, meeting_id: str, title: str
) -> dict[str, Any] | None:
    """The stored brief from the most recent other meeting with this title.

    Cross-meeting memory for recurring meetings, matched on title because that
    is the only thing the app asks a user to keep consistent. Returns the raw
    stored dict: `BriefRecord.brief` is deliberately not validated on read (a
    brief written years ago need not satisfy today's schema to be useful
    context), and rendering it for a prompt is `format_previous_brief`'s job.
    """
    wanted = title.lower().strip()
    if not wanted:
        return None

    candidates = [
        meeting
        for meeting in db.list_meetings()
        if meeting.title.lower().strip() == wanted and meeting.id != meeting_id
    ]
    if not candidates:
        return None

    most_recent = max(candidates, key=lambda meeting: meeting.created_at)
    record = db.get_latest_brief(most_recent.id)
    return record.brief if record else None


def recall_memory(state: BriefState, runtime: Runtime[CopilotRuntime]) -> dict[str, Any]:
    """Look for a previous brief on the same meeting title."""
    context = runtime.context
    title = state.get("title", "")

    try:
        previous = previous_brief_for_title(context.db, state["meeting_id"], title)
    except CopilotError as error:
        logger.warning("Could not load previous brief for '%s': %s", title, error)
        return {"previous_brief": None, **note(f"memory: unavailable ({error})")}

    if previous is None:
        return {"previous_brief": None, **note("memory: no previous meeting on record")}
    return {
        "previous_brief": previous,
        **note("memory: carried context from the previous meeting on this title"),
    }


# --- Supervisor -------------------------------------------------------------


def plan_node(state: BriefState, runtime: Runtime[CopilotRuntime]) -> dict[str, Any]:
    """Decide what to research.

    A plan supplied by the caller wins: `run_brief_graph(plan=...)` is how a
    test pins the research, and how the UI will offer "re-run, but ask this
    instead" in Chunk 8.
    """
    context = runtime.context
    supplied = state.get("plan")
    if supplied:
        return {
            "plan": list(supplied),
            "plan_source": "caller",
            "plan_rationale": "",
            **note(f"supervisor: using the caller's plan ({describe_plan(supplied)})"),
        }

    tasks, source, rationale = plan_research(
        context,
        meeting_id=state["meeting_id"],
        title=state.get("title", ""),
        date=state.get("date"),
        previous_brief=state.get("previous_brief"),
    )

    label = "supervisor planned" if source == "supervisor" else "standing roster"
    return {
        "plan": tasks,
        "plan_source": source,
        "plan_rationale": rationale,
        **note(f"supervisor: {label} -> {describe_plan(tasks)}"),
    }


def dispatch_research(state: BriefState) -> list[Send] | str:
    """Fan out: one specialist branch per task.

    This is a conditional edge rather than a node because `Send` is how
    LangGraph starts parallel branches, and each branch needs its own input
    rather than a slice of the shared state.
    """
    tasks = state.get("plan") or []
    if not tasks:
        return "merge"
    return [
        Send("research", ResearchRequest(meeting_id=state["meeting_id"], task=task))
        for task in tasks
    ]


# --- Specialists ------------------------------------------------------------


def research_node(
    request: ResearchRequest, runtime: Runtime[CopilotRuntime]
) -> dict[str, Any]:
    """Carry out one line of enquiry.

    One branch failing is one `Finding` carrying an error, not an exception:
    losing the risks query should cost the brief its risk evidence, not the
    other four searches that already succeeded.
    """
    context = runtime.context
    task = request["task"]
    k = task.k or context.settings.research_k

    try:
        results = context.retriever.recall(request["meeting_id"], query=task.query, k=k)
    except CopilotError as error:
        logger.warning("Specialist '%s' failed: %s", task.name, error)
        finding = Finding(task=task, error=str(error))
    else:
        finding = Finding(task=task, results=tuple(results))

    return {"findings": [finding], **note(finding.describe())}


# --- Merge ------------------------------------------------------------------


def merge_node(state: BriefState, runtime: Runtime[CopilotRuntime]) -> dict[str, Any]:
    """Fold every specialist's results into one body of evidence.

    Doing this before synthesis is what makes citation resolution correct.
    `resolve_evidence` drops any citation it cannot find among the chunks it was
    given, so if the writer quoted a passage the risks specialist retrieved, the
    risks specialist's chunks had better be in the set handed to it — otherwise
    a perfectly good citation is discarded as fabricated.
    """
    context = runtime.context
    findings = state.get("findings") or []
    results = merge_findings(findings, limit=context.settings.brief_max_chunks)

    failures = [finding for finding in findings if not finding.ok]

    if not results:
        detail = (
            f"all {len(failures)} search(es) failed"
            if failures and len(failures) == len(findings)
            else "the materials returned nothing"
        )
        return {
            "results": [],
            "context": "",
            "error": (
                f"No context could be retrieved for this meeting: {detail}. "
                f"Refusing to generate a brief with nothing to ground it in."
            ),
            **note("merge: no evidence retrieved; stopping"),
        }

    hits = sum(1 for scored in results if not scored.is_neighbour)
    rendered = context.retriever.format_context(results, state["meeting_id"])

    trace = (
        f"merge: {len(results)} chunk(s) from {len(findings)} search(es) "
        f"({hits} hit(s), {len(results) - hits} neighbour(s))"
    )
    if failures:
        trace += f"; {len(failures)} search(es) failed"

    return {"results": results, "context": rendered, **note(trace)}


def merge_findings(
    findings: Iterable[Finding], *, limit: int
) -> list[ScoredChunk]:
    """Union the findings, de-duplicated, capped, and in reading order.

    Three rules, each earning its place:

    * **A chunk retrieved by two specialists appears once.** Duplicated context
      does not make a fact truer, it just costs tokens.
    * **A hit outranks a neighbour.** The same chunk can arrive as a strong
      match for one query and as filler beside another; the prompt should not
      label a real match "(surrounding context)".
    * **The output is in document order, not rank order.** For a brief the model
      reads the whole set, so a coherent run of the meeting beats a ranked
      shuffle of fragments. Rank still decides what survives `limit`.
    """
    best: dict[int, ScoredChunk] = {}

    for finding in findings:
        for scored in finding.results:
            existing = best.get(scored.chunk.id)
            if existing is None or _outranks(scored, existing):
                best[scored.chunk.id] = scored

    ranked = sorted(
        best.values(), key=lambda s: (s.is_neighbour, -s.score, s.chunk.id)
    )
    kept = ranked[:limit]
    kept.sort(key=lambda s: (s.chunk.material_id, s.chunk.chunk_index))
    return kept


def _outranks(candidate: ScoredChunk, incumbent: ScoredChunk) -> bool:
    if candidate.is_neighbour != incumbent.is_neighbour:
        return incumbent.is_neighbour
    return candidate.score > incumbent.score


def route_after_merge(state: BriefState) -> str:
    """Stop rather than write an ungrounded brief."""
    return "abort" if state.get("error") else "synthesize"


# --- Synthesis and persistence ----------------------------------------------


def synthesize_node(
    state: BriefState, runtime: Runtime[CopilotRuntime]
) -> dict[str, Any]:
    """Write the brief from the merged evidence."""
    context = runtime.context
    try:
        synthesis = context.synthesizer.brief(
            title=state.get("title", ""),
            date=state.get("date"),
            results=state.get("results") or [],
            context=state.get("context"),
            previous_brief=state.get("previous_brief"),
        )
    except CopilotError as error:
        logger.error("Synthesis failed: %s", error)
        return {"error": str(error), **note(f"synthesis: failed ({error})")}

    trace = (
        f"synthesis: {len(synthesis.brief.open_action_items)} action item(s), "
        f"{len(synthesis.brief.key_topics_today)} topic(s), "
        f"{synthesis.citation_count} citation(s) resolved"
    )
    if synthesis.dropped_sources:
        trace += f", {len(synthesis.dropped_sources)} citation(s) dropped as unmatched"

    return {"synthesis": synthesis, **note(trace)}


def persist_node(state: BriefState, runtime: Runtime[CopilotRuntime]) -> dict[str, Any]:
    """Store the brief.

    A storage failure is reported but does not discard the brief: the caller
    already has a usable document, and losing it because SQLite was locked would
    be a worse outcome than telling the user it was not saved.
    """
    context = runtime.context
    synthesis = state.get("synthesis")
    if synthesis is None:
        return {}

    try:
        brief_id = context.db.save_brief(
            meeting_id=state["meeting_id"],
            model=synthesis.model,
            brief_dict=synthesis.brief.model_dump(),
        )
    except CopilotError as error:
        logger.error("Could not store brief: %s", error)
        return {
            "error": f"The brief was generated but could not be stored: {error}",
            **note(f"persistence: failed ({error})"),
        }

    return {"brief_id": brief_id, **note(f"persistence: stored as {brief_id}")}


def abort_node(state: BriefState, runtime: Runtime[CopilotRuntime]) -> dict[str, Any]:
    """Terminal node for a run that cannot produce a grounded brief."""
    return note("aborted: nothing to synthesise from")


# --- Question answering -----------------------------------------------------


def qa_retrieve_node(state: QaState, runtime: Runtime[CopilotRuntime]) -> dict[str, Any]:
    """Retrieve the passages relevant to one question."""
    context = runtime.context
    question = state.get("question", "").strip()
    if not question:
        return {"error": "Cannot answer an empty question.", **note("qa: empty question")}

    try:
        results = context.retriever.recall(
            state["meeting_id"],
            query=question,
            k=context.settings.qa_retrieval_k,
        )
    except CopilotError as error:
        logger.warning("Q&A retrieval failed: %s", error)
        return {"error": str(error), **note(f"qa: retrieval failed ({error})")}

    if not results:
        return {"results": [], "context": "", **note("qa: nothing matched the question")}

    hits = sum(1 for scored in results if not scored.is_neighbour)
    return {
        "results": results,
        "context": context.retriever.format_context(results, state["meeting_id"]),
        **note(f"qa: retrieved {len(results)} chunk(s) ({hits} hit(s))"),
    }


def route_after_qa_retrieval(state: QaState) -> str:
    """Skip the model entirely when there is nothing to answer from.

    Asking a grounded-QA model to answer with no context is asking it to make
    something up, and paying for the privilege.
    """
    if state.get("error"):
        return "no_context"
    return "answer" if state.get("results") else "no_context"


def qa_answer_node(state: QaState, runtime: Runtime[CopilotRuntime]) -> dict[str, Any]:
    """Answer the question against the retrieved passages."""
    context = runtime.context
    try:
        answer = context.synthesizer.answer(
            question=state["question"],
            results=state.get("results") or [],
            context=state.get("context"),
        )
    except CopilotError as error:
        logger.error("Q&A synthesis failed: %s", error)
        return {"error": str(error), **note(f"qa: answering failed ({error})")}

    return {"answer": answer, **note(f"qa: answered from {len(answer.sources)} source(s)")}


def qa_no_context_node(
    state: QaState, runtime: Runtime[CopilotRuntime]
) -> dict[str, Any]:
    """Say so, rather than inventing an answer."""
    from core.synthesis import QaAnswer

    context = runtime.context
    return {
        "answer": QaAnswer(
            text=NO_CONTEXT_ANSWER,
            model=context.synthesizer.model_name,
            provider=context.synthesizer.provider,
        ),
        **note("qa: answered without calling the model (no context)"),
    }


# --- Shared -----------------------------------------------------------------


def render_context(results: Sequence[ScoredChunk]) -> str:
    """Render results without database access, for callers that lack a runtime."""
    return format_context_blocks(results)


__all__ = [
    "NO_CONTEXT_ANSWER",
    "ResearchTask",
    "abort_node",
    "default_plan",
    "dispatch_research",
    "merge_findings",
    "merge_node",
    "persist_node",
    "plan_node",
    "previous_brief_for_title",
    "qa_answer_node",
    "qa_no_context_node",
    "qa_retrieve_node",
    "recall_memory",
    "render_context",
    "research_node",
    "route_after_merge",
    "route_after_qa_retrieval",
    "synthesize_node",
]
