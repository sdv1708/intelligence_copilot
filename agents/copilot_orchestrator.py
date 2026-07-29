"""The pre-overhaul surface, kept as a facade over the LangGraph pipeline.

`app.py` calls five methods on this class. They still exist, still take the same
arguments, and still return the same dictionaries — but nothing here does any
work of its own any more. `generate_brief` and `answer_question` invoke
`run_brief_graph` / `run_qa_graph`; the steps they used to run inline (recall
previous brief, retrieve, synthesise, store) are nodes of those graphs.

What is left in this module is the boundary translation, and it is worth being
explicit about the two places it is lossy:

* **`success` is not "nothing went wrong".** `BriefRun.ok` means *a brief
  exists*. A run that produced a brief and then failed to store it comes back
  `success=True` with `error` set, because discarding a usable document because
  SQLite was locked serves nobody. Callers that only check `success` will miss
  that; `app.py` reads both.
* **Q&A is stricter.** The graph answers "I could not find relevant
  information" without calling the model when nothing was retrieved, which is a
  successful run. But a retrieval *failure* also lands on that node, and
  reporting a real error as a polite non-answer would hide it — so
  `answer_question` reports `success=False` whenever `error` is set.

One `CopilotRuntime` is built in `__init__` and shared by every call, which is
what makes a single chat client and a single loaded embedder serve the whole
session. Tests pass a runtime in directly rather than letting one be built.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from agents.graph import BriefRun, QaRun, run_brief_graph, run_qa_graph
from agents.runtime import CopilotRuntime
from core.db import Database
from core.exceptions import CopilotError, InvalidBriefError
from core.indexing import delete_material_everywhere, index_material
from core.logging_config import get_logger
from core.parsing import parse_file
from core.recall import Retriever
from core.schema import MeetingBrief
from core.synthesis import Synthesizer

logger = get_logger(__name__)


class CopilotOrchestrator:
    """Entry point for the UI: ingestion, brief generation, and Q&A."""

    def __init__(
        self,
        provider: str = "gemini",
        *,
        runtime: CopilotRuntime | None = None,
    ) -> None:
        """Build the shared runtime, or adopt one that was handed in.

        `runtime` is how the tests drive this class against a throwaway database
        and a scripted model; production passes only `provider`.
        """
        self.runtime = runtime if runtime is not None else CopilotRuntime.build(
            provider=provider
        )
        logger.info(
            "Orchestrator ready: provider=%s model=%s supervisor=%s",
            self.provider_name,
            self.model_name,
            "on" if self.runtime.plans_with_llm else "off",
        )

    # --- Shared collaborators ----------------------------------------------

    @property
    def db(self) -> Database:
        return self.runtime.db

    @property
    def retriever(self) -> Retriever:
        return self.runtime.retriever

    @property
    def synthesizer(self) -> Synthesizer:
        return self.runtime.synthesizer

    @property
    def provider_name(self) -> str:
        return self.runtime.provider

    @property
    def model_name(self) -> str:
        return self.runtime.synthesizer.model_name

    # --- Ingestion ----------------------------------------------------------

    def ingest_material(
        self,
        file_bytes: bytes,
        filename: str,
        meeting_id: str,
        *,
        media_type: str | None = None,
    ) -> dict[str, Any]:
        """Parse, store, chunk, embed and index one document.

        This is the whole write path in one call, which is the point: there is
        no way to reach it that stores a material without also indexing it.
        `app.py` used to add the row itself and then call this to index, so
        every file was parsed twice and every re-upload of the same filename
        left a second copy of the document in the index.
        """
        try:
            text, detected_type = parse_file(file_bytes, filename)
            if not text.strip():
                logger.warning("No text could be read out of %s", filename)
                return {
                    "success": False,
                    "error": f"No readable text could be extracted from '{filename}'.",
                }

            material_id = self._store_material(
                meeting_id, filename, media_type or detected_type, text
            )

            # The runtime's embedder, not a fresh one: this is the model that is
            # already loaded, and in tests it is the one that is not real.
            chunk_ids = index_material(
                self.db,
                material_id,
                embedder=self.retriever.embedder,
                settings=self.runtime.settings,
            )
            if not chunk_ids:
                return {
                    "success": False,
                    "material_id": material_id,
                    "error": f"'{filename}' produced no chunks to index.",
                }

            logger.info("Ingested %s as %s (%d chunks)", filename, material_id, len(chunk_ids))
            return {
                "success": True,
                "material_id": material_id,
                "chunks": len(chunk_ids),
                "characters": len(text),
            }

        except CopilotError as error:
            logger.error("Could not ingest %s: %s", filename, error)
            return {"success": False, "error": str(error)}

    def _store_material(
        self, meeting_id: str, filename: str, media_type: str, text: str
    ) -> str:
        """Return the material id this text should be stored under.

        Uploading the same filename twice is a normal thing to do — a corrected
        deck, a longer transcript — and it must not leave the meeting holding
        two copies of the document. An existing row with identical text is
        reused and re-indexed; one whose text has changed is deleted along with
        its chunks and vectors before the new version is added.
        """
        unchanged: str | None = None

        for existing in self.db.get_materials(meeting_id):
            if existing.filename != filename:
                continue
            stored = self.db.get_material(existing.id)
            if unchanged is None and stored is not None and stored.text == text:
                unchanged = existing.id
                continue
            logger.info(
                "Replacing material %s: '%s' was re-uploaded with different content",
                existing.id,
                filename,
            )
            delete_material_everywhere(
                self.db, existing.id, settings=self.runtime.settings
            )

        if unchanged is not None:
            return unchanged

        return self.db.add_material(
            meeting_id=meeting_id,
            filename=filename,
            media_type=media_type,
            text=text,
        )

    # --- Retrieval ----------------------------------------------------------

    def recall_context_tool(self, meeting_id: str, k: int = 8) -> dict[str, Any]:
        """Retrieve context for a meeting and render it as prompt blocks."""
        try:
            results = self.retriever.recall(meeting_id, k=k)
        except CopilotError as error:
            logger.error("Recall failed for %s: %s", meeting_id, error)
            return {"success": False, "chunks": 0, "context_blocks": "", "error": str(error)}

        if not results:
            return {"success": False, "chunks": 0, "context_blocks": ""}

        return {
            "success": True,
            "chunks": len(results),
            "context_blocks": self.retriever.format_context(results, meeting_id),
            "sources": [scored.source_ref for scored in results],
        }

    # --- Brief generation ---------------------------------------------------

    def generate_brief(self, meeting_id: str, title: str, date: str) -> dict[str, Any]:
        """Run the brief graph for one meeting."""
        run = run_brief_graph(
            self.runtime, meeting_id=meeting_id, title=title, date=date
        )
        return self._brief_result(run)

    def _brief_result(self, run: BriefRun) -> dict[str, Any]:
        """Flatten a `BriefRun` into the dictionary `app.py` reads.

        `run` itself is carried along under its own key. Everything the UI shows
        today is in the flat fields, but the trace, the plan and the findings
        are what Chunk 8 renders, and re-deriving them from a dict would be
        worse than passing the object.
        """
        return {
            "success": run.ok,
            "brief": run.brief,
            "brief_id": run.brief_id,
            "provider": self.provider_name,
            "model": run.model or self.model_name,
            "error": run.error,
            "notes": list(run.notes),
            "plan": [task.name for task in run.plan],
            "plan_source": run.plan_source,
            "plan_rationale": run.plan_rationale,
            "failed_tasks": list(run.failed_tasks),
            "chunks": len(run.results),
            "run": run,
        }

    # --- Question answering -------------------------------------------------

    def answer_question(self, meeting_id: str, question: str) -> dict[str, Any]:
        """Run the Q&A graph for one question."""
        run = run_qa_graph(self.runtime, meeting_id=meeting_id, question=question)
        return self._qa_result(run)

    def _qa_result(self, run: QaRun) -> dict[str, Any]:
        return {
            # Unlike a brief, an answer that arrived alongside an error is not
            # worth keeping: the text in that case is the "nothing retrieved"
            # boilerplate, and showing it would disguise the failure.
            "success": run.ok and run.error is None,
            "answer": run.text,
            "sources": list(run.sources),
            "provider": self.provider_name,
            "model": run.answer.model if run.answer else self.model_name,
            "error": run.error,
            "notes": list(run.notes),
            "chunks": len(run.results),
            "run": run,
        }

    # --- Memory -------------------------------------------------------------

    def recall_previous_brief(self, meeting_id: str) -> MeetingBrief | None:
        """The most recent stored brief for this meeting, or `None`.

        Briefs are persisted as raw dicts on purpose (see `BriefRecord`), so a
        row written before a schema change can fail to validate. That is worth
        reporting rather than presenting as "no previous brief".
        """
        record = self.db.get_latest_brief(meeting_id)
        if record is None:
            return None

        try:
            return record.as_brief()
        except ValidationError as error:
            raise InvalidBriefError(
                f"Stored brief {record.id} does not satisfy the current schema: {error}"
            ) from error
