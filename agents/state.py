"""What flows between the nodes of the brief and Q&A graphs.

The shape here is the whole reason this is a graph rather than a method. A brief
is assembled from several independent lines of enquiry that have no reason to
run in sequence, and `findings` is annotated with a reducer so those branches
can fan out, complete in any order, and merge without stepping on each other.

Two conventions worth knowing before reading the nodes:

* **A failed branch is data, not an exception.** A `Finding` carries an `error`
  instead of results when its search failed, so one specialist hitting a broken
  index costs the brief one line of enquiry rather than the whole run.
* **`notes` is the trace.** Nodes append a human-readable line describing what
  they did. It is what the UI shows instead of the old `log_message("[Step 2]")`
  calls, and what a test asserts against when the interesting behaviour is
  "which path did the graph take".
"""

from __future__ import annotations

import operator
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypedDict

from core.schema import ScoredChunk
from core.synthesis import BriefSynthesis, QaAnswer

# --- The supervisor's output ------------------------------------------------


class ResearchTask(BaseModel):
    """One specialist's assignment: a name, and the question it asks retrieval.

    This doubles as part of the supervisor agent's structured output, so the
    field descriptions are load-bearing — they are what the planning model reads
    to understand what it is being asked for.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    name: str = Field(
        description="Short slug identifying this line of enquiry, e.g. 'action_items'."
    )
    query: str = Field(
        default="",
        description=(
            "Natural-language description of the information wanted, phrased in "
            "the vocabulary the documents themselves would use. Leave empty to "
            "request a coverage sweep of the whole meeting instead of a search."
        ),
    )
    k: int | None = Field(
        default=None,
        description="How many hits to retrieve. Omit to use the configured default.",
    )
    rationale: str = Field(
        default="", description="Why this meeting warrants this line of enquiry."
    )

    @property
    def is_sweep(self) -> bool:
        """Whether this task asks for coverage rather than relevance.

        An empty query is not a degenerate search; `Retriever.recall` treats it
        as "no particular question" and samples across the meeting.
        """
        return not self.query.strip()


class ResearchPlan(BaseModel):
    """The set of enquiries to run for one brief."""

    model_config = ConfigDict(extra="ignore")

    tasks: list[ResearchTask] = Field(
        default_factory=list,
        description="Three to six distinct tasks, exactly one of them a coverage sweep.",
    )
    rationale: str = Field(
        default="", description="One or two sentences on why this plan fits this meeting."
    )


# --- What a specialist brings back ------------------------------------------


@dataclass(frozen=True)
class Finding:
    """The outcome of one specialist's search.

    `results` and `error` are mutually exclusive in practice but neither is
    required: a task that ran fine and matched nothing is an empty `results`
    with no error, which is a real and different answer from a task that blew
    up.
    """

    task: ResearchTask
    results: tuple[ScoredChunk, ...] = ()
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def hits(self) -> tuple[ScoredChunk, ...]:
        return tuple(scored for scored in self.results if not scored.is_neighbour)

    def describe(self) -> str:
        if self.error:
            return f"{self.task.name}: failed ({self.error})"
        kind = "swept" if self.task.is_sweep else f"searched '{self.task.query[:60]}'"
        return (
            f"{self.task.name}: {kind} -> "
            f"{len(self.hits)} hit(s), {len(self.results) - len(self.hits)} neighbour(s)"
        )


# --- Graph state ------------------------------------------------------------


class BriefState(TypedDict, total=False):
    """Everything the brief graph reads and writes.

    `total=False` throughout: LangGraph hands each node the accumulated state,
    and a node that has not run yet has contributed no keys. Nodes read with
    `.get`.
    """

    # Inputs.
    meeting_id: str
    title: str
    date: str | None

    # Memory node.
    previous_brief: dict[str, Any] | None

    # Supervisor node.
    plan: list[ResearchTask]
    plan_source: str  # "caller" | "supervisor" | "default"
    plan_rationale: str

    # Specialist fan-out. The reducer is what makes parallel branches legal:
    # each one returns a single-element list and LangGraph concatenates them.
    findings: Annotated[list[Finding], operator.add]

    # Merge node.
    results: list[ScoredChunk]
    context: str

    # Synthesis and persistence.
    synthesis: BriefSynthesis | None
    brief_id: str | None

    notes: Annotated[list[str], operator.add]
    error: str | None


class ResearchRequest(TypedDict):
    """The payload one specialist branch is dispatched with.

    Declared separately from `BriefState` because `Send` replaces a node's input
    entirely, and a specialist needs exactly one task rather than the list of
    all of them.
    """

    meeting_id: str
    task: ResearchTask


class QaState(TypedDict, total=False):
    """State for the question-answering graph."""

    meeting_id: str
    question: str
    results: list[ScoredChunk]
    context: str
    answer: QaAnswer | None
    notes: Annotated[list[str], operator.add]
    error: str | None


# --- Helpers ----------------------------------------------------------------


def note(message: str) -> dict[str, list[str]]:
    """A state update carrying one trace line. Merged by the `notes` reducer."""
    return {"notes": [message]}


def describe_plan(tasks: Sequence[ResearchTask]) -> str:
    """One-line summary of a plan, for logs and traces."""
    return ", ".join(task.name for task in tasks) or "(empty)"
