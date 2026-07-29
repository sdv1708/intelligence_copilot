"""The LangGraph multi-agent core.

`graph.py` is the entry point: `run_brief_graph` and `run_qa_graph`, both taking
a `CopilotRuntime` holding the database, retriever and synthesizer they should
work through. `CopilotOrchestrator` is the pre-overhaul surface `app.py` still
calls; Chunk 6 turns it into a facade over these graphs.

Imported lazily through `__getattr__` because `agents.graph` pulls in LangGraph
and, through the synthesizer, a provider SDK. `import agents` should stay cheap
enough for a Streamlit rerun.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # names re-exported lazily by __getattr__ below
    from agents.copilot_orchestrator import CopilotOrchestrator
    from agents.graph import (
        BriefRun,
        QaRun,
        brief_graph,
        build_brief_graph,
        build_qa_graph,
        qa_graph,
        run_brief_graph,
        run_qa_graph,
    )
    from agents.planner import DEFAULT_ROSTER, default_plan
    from agents.runtime import CopilotRuntime
    from agents.state import Finding, ResearchPlan, ResearchTask

_EXPORTS: dict[str, str] = {
    "BriefRun": "agents.graph",
    "QaRun": "agents.graph",
    "brief_graph": "agents.graph",
    "build_brief_graph": "agents.graph",
    "build_qa_graph": "agents.graph",
    "qa_graph": "agents.graph",
    "run_brief_graph": "agents.graph",
    "run_qa_graph": "agents.graph",
    "CopilotRuntime": "agents.runtime",
    "DEFAULT_ROSTER": "agents.planner",
    "default_plan": "agents.planner",
    "Finding": "agents.state",
    "ResearchPlan": "agents.state",
    "ResearchTask": "agents.state",
    "CopilotOrchestrator": "agents.copilot_orchestrator",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module 'agents' has no attribute {name!r}")

    from importlib import import_module

    return getattr(import_module(module_name), name)


def __dir__() -> list[str]:
    return __all__
