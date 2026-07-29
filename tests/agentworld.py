"""A small, real world for the agent tests to run against.

Everything here is genuine except the model and the encoder: a real SQLite file
under `tmp_path`, real chunking, a real FAISS index, real retrieval. Only the
embedder (`HashingEmbedder`, lexical and deterministic) and the chat models are
doubles, which is what keeps the graph tests hermetic without reducing them to
mock choreography.

The corpus is written so the standing roster's queries land on *different*
paragraphs — the risks query finds the risks paragraph and not the budget one.
That is what makes it possible to assert on the interesting property: that
evidence citing a chunk only one specialist retrieved still resolves after the
merge.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.runtime import CopilotRuntime
from core.config import Settings
from core.db import Database
from core.indexing import index_material
from core.recall import Retriever
from core.synthesis import Synthesizer
from tests.fakes import HashingEmbedder, ScriptedChatModel, ScriptedToolCallingModel

TITLE = "Platform Steering Committee"

#: One paragraph per line of enquiry, each carrying the vocabulary that the
#: matching roster query searches for.
PARAGRAPHS = (
    "Attendance and apologies were noted, and the chair opened by restating the "
    "committee's remit for the coming quarter.",
    "The committee agreed to go with the managed database option and approved "
    "the migration; that decision was signed off unanimously and the chosen "
    "approach is now settled.",
    "Outstanding action items remain: Priya still owns the capacity model and "
    "has yet to follow up, while Marcus is responsible for the vendor "
    "assessment that was assigned to him and is still to do.",
    "Several risks and blockers were raised. The main concern is a dependency "
    "on the platform team, and there was pushback about delays; the issues "
    "raised around observability remain unresolved problems.",
    "On timeline: the migration deadline is the end of the quarter, the due "
    "date for the capacity model is next Friday, and the next meeting is "
    "scheduled for the following month with a launch date to be confirmed.",
    "Under any other business the committee thanked the retiring secretary and "
    "closed after fifty minutes.",
)

MATERIAL_TEXT = "\n\n".join(PARAGRAPHS)


@dataclass
class World:
    """A meeting that has been ingested, chunked and indexed."""

    db: Database
    settings: Settings
    embedder: HashingEmbedder
    meeting_id: str
    material_id: str

    def source_ref(self, chunk_index: int) -> str:
        """The citation label for one chunk of the material."""
        return f"{self.material_id}#c{chunk_index}"

    def chunk_count(self) -> int:
        return self.db.count_chunks(self.meeting_id)


def build_world(
    tmp_path: Path,
    settings: Settings,
    embedder: HashingEmbedder,
    *,
    title: str = TITLE,
    text: str = MATERIAL_TEXT,
    filename: str = "minutes.txt",
) -> World:
    """Ingest one material into a throwaway database and index it.

    `chunk_size` is set small enough that each paragraph becomes its own chunk,
    so a test can reason about which chunk a query should match. The similarity
    floor is dropped to zero because `HashingEmbedder`'s scores are lexical
    overlap, not the calibrated cosines the real model produces.
    """
    tuned = settings.model_copy(
        update={"chunk_size": 280, "chunk_overlap": 0, "min_similarity": 0.0}
    )
    db = Database(tmp_path / "agents.db", settings=tuned)
    meeting_id = db.create_meeting(title, date="2026-07-28")
    material_id = db.add_material(meeting_id, filename, "txt", text)
    index_material(db, material_id, embedder=embedder, settings=tuned)

    return World(
        db=db,
        settings=tuned,
        embedder=embedder,
        meeting_id=meeting_id,
        material_id=material_id,
    )


def runtime_for(
    world: World,
    *,
    responses: Sequence[Any] = (),
    planner_responses: Sequence[Any] | None = None,
    auto_repair: bool = True,
    settings: Settings | None = None,
) -> CopilotRuntime:
    """Wire a runtime around a world.

    `planner_responses=None` means no supervisor — the standing roster runs, and
    the model is never asked to plan. Supplying a script switches the supervisor
    on and pins what it decides.
    """
    tuned = settings or world.settings
    chat = ScriptedChatModel(list(responses))
    planner = (
        ScriptedToolCallingModel(responses=list(planner_responses))
        if planner_responses is not None
        else None
    )

    return CopilotRuntime(
        db=world.db,
        settings=tuned,
        retriever=Retriever(
            world.db, embedder=world.embedder, settings=tuned, auto_repair=auto_repair
        ),
        synthesizer=Synthesizer(chat, provider="gemini", settings=tuned),
        planner_model=planner,
        provider="gemini",
        planner_max_tasks=tuned.planner_max_tasks,
    )


def brief_payload(world: World, *, sources: Sequence[str] = ()) -> dict[str, Any]:
    """A valid `MeetingBrief` body citing the given source refs."""
    return {
        "meeting_title": TITLE,
        "time_window": "2026-07-01..2026-07-28",
        "last_meeting_recap": "The managed database option was approved.",
        "open_action_items": [
            {"owner": "Priya", "item": "Finish the capacity model", "status": "open"},
            {"owner": "Marcus", "item": "Vendor assessment", "status": "blocked"},
        ],
        "key_topics_today": [
            "Migration timeline: the deadline is the end of the quarter."
        ],
        "proposed_agenda": [{"topic": "Migration", "minutes": 20, "owner": "Priya"}],
        "evidence": [
            {"source": source, "snippet": f"Cited text for {source}."}
            for source in sources
        ],
    }
