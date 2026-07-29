"""Tools the supervisor uses to look before it plans.

These are the only genuinely agentic surface in the system, and they exist for
one reason: a plan written without seeing the materials is a guess. Given
`list_materials` and `search_meeting`, the supervisor can find out that a
meeting has one 268k-character transcript and no deck, that "vendor" appears
nowhere in it, and that budget figures do — and then commission the questions
that will actually return something.

They are built as closures over a runtime and a meeting id rather than reading
either from LangGraph's context. The supervisor runs as its own compiled agent,
so the brief graph's context does not reach it, and a closure is both simpler
and easier to point at a throwaway database in a test.

Every tool returns a string. Tool results go back to the model as message text,
so structured returns would only be serialised anyway, and shaping them here
keeps the token cost visible at the point it is incurred.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.exceptions import CopilotError
from core.logging_config import get_logger

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from agents.runtime import CopilotRuntime

logger = get_logger(__name__)

#: Characters of each hit shown to the supervisor. Enough to judge whether a
#: line of enquiry is live; short enough that probing four times does not spend
#: the context the brief itself needs.
PROBE_SNIPPET_CHARS = 240

#: Hits per probe. The supervisor is sampling, not retrieving.
PROBE_K = 4


def research_tools(runtime: CopilotRuntime, meeting_id: str) -> list[BaseTool]:
    """Tools scoped to one meeting, for the supervisor agent."""
    from langchain_core.tools import tool

    @tool
    def list_materials() -> str:
        """List the documents attached to this meeting, with their sizes.

        Use this first. It tells you what kind of meeting you are planning for:
        a transcript reads differently from a slide deck, and a meeting with no
        prior documents cannot support questions about history.
        """
        try:
            materials = runtime.db.get_materials(meeting_id)
        except CopilotError as error:
            return f"Could not list materials: {error}"

        if not materials:
            return "This meeting has no materials attached."

        lines = [f"{len(materials)} material(s):"]
        for material in materials:
            lines.append(
                f"- {material.filename or material.id} "
                f"[{material.media_type or 'unknown'}] "
                f"({material.char_count:,} characters, id {material.id})"
            )
        return "\n".join(lines)

    @tool
    def search_meeting(query: str) -> str:
        """Run a trial semantic search over this meeting's materials.

        Use it to check whether a line of enquiry has anything behind it before
        you commit a specialist to it. The excerpts come back truncated — you
        are sampling to decide what to ask, not gathering evidence.
        """
        if not query.strip():
            return (
                "Provide a query. An empty query is a coverage sweep, which is "
                "something to put in the plan, not something to probe with."
            )

        try:
            results = runtime.retriever.recall(
                meeting_id, query=query, k=PROBE_K, neighbour_radius=0
            )
        except CopilotError as error:
            logger.warning("Supervisor probe failed for %r: %s", query, error)
            return f"Search failed: {error}"

        if not results:
            return (
                f"No passages matched '{query}'. Nothing in the materials "
                f"supports this line of enquiry."
            )

        lines = [f"{len(results)} passage(s) matched '{query}':"]
        for scored in results:
            text = " ".join(scored.chunk.text.split())
            if len(text) > PROBE_SNIPPET_CHARS:
                text = text[:PROBE_SNIPPET_CHARS].rstrip() + "..."
            lines.append(f"- [{scored.score:.2f}] {scored.source_ref}: {text}")
        return "\n".join(lines)

    return [list_materials, search_meeting]
