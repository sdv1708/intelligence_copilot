"""The graphs themselves, and the two functions the rest of the app calls.

```
                       brief graph
    START -> memory -> supervisor -=<  research (xN, parallel)  >=- merge
                                                                     |
                                                        +------------+------------+
                                                        |                         |
                                                   synthesize                   abort
                                                        |                         |
                                                     persist -------------------> END
```

```
                        Q&A graph
    START -> retrieve -=<  answer | no_context  >=- END
```

The shape encodes the decision made at the start of this overhaul: deterministic
edges where the pipeline is fixed, an agent where judgment is needed. Ingesting,
merging, writing and storing happen in that order every time and are wired as
plain edges. The two places the path is genuinely open — *what should we look
for* and *is there anything here to answer from* — are the supervisor node and
the two conditional edges.

Graphs are cached per shape, not per runtime. Building a `StateGraph` and
compiling it is not free, and the runtime is passed at invocation time as
context, so one compiled graph serves every meeting and every user.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from langgraph.graph import END, START, StateGraph

from agents.nodes import (
    abort_node,
    dispatch_research,
    merge_node,
    persist_node,
    plan_node,
    qa_answer_node,
    qa_no_context_node,
    qa_retrieve_node,
    recall_memory,
    research_node,
    route_after_merge,
    route_after_qa_retrieval,
    synthesize_node,
)
from agents.runtime import CopilotRuntime
from agents.state import (
    BriefState,
    Finding,
    QaState,
    ResearchRequest,
    ResearchTask,
)
from core.logging_config import get_logger
from core.schema import MeetingBrief, ScoredChunk
from core.synthesis import BriefSynthesis, QaAnswer

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

logger = get_logger(__name__)


# --- Construction -----------------------------------------------------------


def build_brief_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Compile the brief-generation graph."""
    builder = StateGraph(BriefState, context_schema=CopilotRuntime)

    builder.add_node("memory", recall_memory)
    builder.add_node("supervisor", plan_node)
    # `input_schema` because `Send` replaces this node's input entirely: a
    # specialist receives one task, never the whole plan.
    builder.add_node("research", research_node, input_schema=ResearchRequest)
    builder.add_node("merge", merge_node)
    builder.add_node("synthesize", synthesize_node)
    builder.add_node("persist", persist_node)
    builder.add_node("abort", abort_node)

    builder.add_edge(START, "memory")
    builder.add_edge("memory", "supervisor")
    builder.add_conditional_edges("supervisor", dispatch_research, ["research", "merge"])
    builder.add_edge("research", "merge")
    builder.add_conditional_edges("merge", route_after_merge, ["synthesize", "abort"])
    builder.add_edge("synthesize", "persist")
    builder.add_edge("persist", END)
    builder.add_edge("abort", END)

    return builder.compile(checkpointer=checkpointer, name="meeting_brief")


def build_qa_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Compile the question-answering graph."""
    builder = StateGraph(QaState, context_schema=CopilotRuntime)

    builder.add_node("retrieve", qa_retrieve_node)
    builder.add_node("answer", qa_answer_node)
    builder.add_node("no_context", qa_no_context_node)

    builder.add_edge(START, "retrieve")
    builder.add_conditional_edges(
        "retrieve", route_after_qa_retrieval, ["answer", "no_context"]
    )
    builder.add_edge("answer", END)
    builder.add_edge("no_context", END)

    return builder.compile(checkpointer=checkpointer, name="meeting_qa")


@lru_cache(maxsize=1)
def brief_graph():
    """The process-wide compiled brief graph, without checkpointing."""
    return build_brief_graph()


@lru_cache(maxsize=1)
def qa_graph():
    """The process-wide compiled Q&A graph, without checkpointing."""
    return build_qa_graph()


# --- Results ----------------------------------------------------------------


@dataclass(frozen=True)
class BriefRun:
    """The outcome of one pass through the brief graph.

    `ok` means *a brief exists*, which is not the same as "nothing went wrong":
    a run that generated a brief and then failed to store it is `ok` with an
    `error` set, because throwing the document away would serve nobody.
    """

    synthesis: BriefSynthesis | None = None
    brief_id: str | None = None
    plan: tuple[ResearchTask, ...] = ()
    plan_source: str = ""
    plan_rationale: str = ""
    findings: tuple[Finding, ...] = ()
    results: tuple[ScoredChunk, ...] = ()
    context: str = ""
    notes: tuple[str, ...] = ()
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.synthesis is not None

    @property
    def brief(self) -> MeetingBrief | None:
        return self.synthesis.brief if self.synthesis else None

    @property
    def model(self) -> str:
        return self.synthesis.model if self.synthesis else ""

    @property
    def failed_tasks(self) -> tuple[str, ...]:
        return tuple(f.task.name for f in self.findings if not f.ok)


@dataclass(frozen=True)
class QaRun:
    """The outcome of one pass through the Q&A graph."""

    answer: QaAnswer | None = None
    results: tuple[ScoredChunk, ...] = ()
    notes: tuple[str, ...] = ()
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.answer is not None

    @property
    def text(self) -> str:
        return self.answer.text if self.answer else ""

    @property
    def sources(self) -> tuple[str, ...]:
        return self.answer.sources if self.answer else ()


# --- Invocation -------------------------------------------------------------


def run_brief_graph(
    runtime: CopilotRuntime,
    *,
    meeting_id: str,
    title: str,
    date: str | None = None,
    plan: Sequence[ResearchTask] | None = None,
    graph: Any | None = None,
    thread_id: str | None = None,
) -> BriefRun:
    """Generate one brief.

    `plan` overrides the supervisor. `thread_id` is only meaningful against a
    graph compiled with a checkpointer — pass one from `build_brief_graph` if
    you want the run's intermediate state to survive for inspection or replay.
    """
    compiled = graph if graph is not None else brief_graph()
    state: BriefState = {
        "meeting_id": meeting_id,
        "title": title,
        "date": date,
        "findings": [],
        "notes": [],
    }
    if plan is not None:
        state["plan"] = list(plan)

    started = time.perf_counter()
    final = compiled.invoke(state, context=runtime, config=_config(thread_id))
    elapsed = time.perf_counter() - started

    run = BriefRun(
        synthesis=final.get("synthesis"),
        brief_id=final.get("brief_id"),
        plan=tuple(final.get("plan") or ()),
        plan_source=final.get("plan_source", ""),
        plan_rationale=final.get("plan_rationale", ""),
        findings=tuple(final.get("findings") or ()),
        results=tuple(final.get("results") or ()),
        context=final.get("context", ""),
        notes=tuple(final.get("notes") or ()),
        error=final.get("error"),
    )
    logger.info(
        "Brief run for '%s' in %.2fs: ok=%s plan=%s(%d tasks) chunks=%d",
        title,
        elapsed,
        run.ok,
        run.plan_source,
        len(run.plan),
        len(run.results),
    )
    return run


def run_qa_graph(
    runtime: CopilotRuntime,
    *,
    meeting_id: str,
    question: str,
    graph: Any | None = None,
    thread_id: str | None = None,
) -> QaRun:
    """Answer one question about one meeting."""
    compiled = graph if graph is not None else qa_graph()
    state: QaState = {"meeting_id": meeting_id, "question": question, "notes": []}
    final = compiled.invoke(state, context=runtime, config=_config(thread_id))

    return QaRun(
        answer=final.get("answer"),
        results=tuple(final.get("results") or ()),
        notes=tuple(final.get("notes") or ()),
        error=final.get("error"),
    )


def _config(thread_id: str | None) -> dict[str, Any] | None:
    """LangGraph rejects a thread-less config on a checkpointed graph, and
    ignores a thread id on one without a checkpointer, so only send it when the
    caller asked for it."""
    return {"configurable": {"thread_id": thread_id}} if thread_id else None
