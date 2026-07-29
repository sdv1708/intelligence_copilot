"""Turning a `BriefRun` / `QaRun` into the wire format.

The orchestrator's flat result dicts carry a `"run"` key holding the whole run
object, and that is what these functions read. The flat siblings — `notes`,
`plan`, `failed_tasks`, `chunks` — were only ever there so the pre-overhaul
Streamlit UI kept working, and nothing reads them any more.

One asymmetry survives from the facade and is worth restating, because it is the
difference between the two functions below: for a brief, `ok` means *a document
exists*, and an error alongside it is a warning. For an answer, an error means
the run failed, because the text in that case is the "nothing retrieved"
boilerplate and returning it as an answer would disguise a real failure.
"""

from __future__ import annotations

from typing import Any

from agents.graph import BriefRun, QaRun
from api.schemas import BriefResponse, FindingOut, QaResponse, TaskOut, Trace


def brief_trace(run: BriefRun) -> Trace:
    return Trace(
        notes=list(run.notes),
        plan=[
            TaskOut(
                name=task.name,
                query=task.query,
                rationale=task.rationale,
                is_sweep=task.is_sweep,
            )
            for task in run.plan
        ],
        plan_source=run.plan_source,
        plan_rationale=run.plan_rationale,
        findings=[
            FindingOut(
                name=finding.task.name,
                query=finding.task.query,
                ok=finding.ok,
                hits=len(finding.hits),
                # A neighbour is a chunk retrieved for context because it sits
                # beside a hit; counting it as a hit would overstate the search.
                neighbours=len(finding.results) - len(finding.hits),
                error=finding.error,
            )
            for finding in run.findings
        ],
        chunks=len(run.results),
    )


def brief_response(result: dict[str, Any]) -> BriefResponse:
    """Translate `CopilotOrchestrator.generate_brief`'s result."""
    run: BriefRun = result["run"]
    return BriefResponse(
        ok=run.ok,
        brief=run.brief,
        brief_id=run.brief_id,
        provider=result.get("provider", ""),
        model=run.model or result.get("model", ""),
        warning=run.error,
        failed_tasks=list(run.failed_tasks),
        trace=brief_trace(run),
    )


def qa_response(result: dict[str, Any]) -> QaResponse:
    """Translate `CopilotOrchestrator.answer_question`'s result."""
    run: QaRun = result["run"]
    return QaResponse(
        ok=run.ok and run.error is None,
        answer=run.text,
        sources=list(run.sources),
        provider=result.get("provider", ""),
        model=run.answer.model if run.answer else result.get("model", ""),
        error=run.error,
        trace=Trace(notes=list(run.notes), chunks=len(run.results)),
    )
