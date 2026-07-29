"""The HTTP layer over the facade.

`tests/test_orchestrator.py` pins what the facade returns; this pins what the
wire sees. The three things worth testing here are the ones that exist only at
this boundary and have no representation below it:

* **the status table** in `api/errors.py` — it is ordered, and a subclass that
  drifts below its base silently stops being reachable
* **the partial-failure path** in a multi-file upload — a bad file among good
  ones must cost you the bad file and nothing else
* **the `ok`/`warning` asymmetry** in `api/translate.py` — a brief that was
  generated but not stored is a success with a warning; an answer produced
  after a retrieval failure is a failure

Everything runs against a throwaway world: a real SQLite file, real chunking, a
real FAISS index, `HashingEmbedder` and a scripted chat model. No network, no
model download, no `.env`.
"""

from __future__ import annotations

import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agents.copilot_orchestrator import CopilotOrchestrator
from agents.graph import BriefRun
from agents.planner import DEFAULT_ROSTER
from agents.state import Finding, ResearchTask
from api import deps
from api.errors import status_for
from api.main import app, serves_index
from api.routes import materials as materials_route
from api.routes.status import _is_temporary
from api.translate import brief_trace
from core.config import Settings
from core.exceptions import (
    ConfigurationError,
    CopilotError,
    EmptyDocumentError,
    IndexOutOfSyncError,
    IngestionError,
    InvalidBriefError,
    MeetingNotFoundError,
    MissingAPIKeyError,
    PromptError,
    RetrievalError,
    StorageError,
    SynthesisError,
    UnknownProviderError,
    UnsupportedFileTypeError,
)
from core.schema import Chunk, ScoredChunk
from tests.agentworld import TITLE, World, brief_payload, build_world, runtime_for
from tests.fakes import HashingEmbedder


def _scored(chunk_id: int, *, is_neighbour: bool) -> ScoredChunk:
    """One retrieved chunk, with only the fields the translation reads."""
    return ScoredChunk(
        chunk=Chunk(
            id=chunk_id,
            material_id="material_1",
            meeting_id="meeting_1",
            chunk_index=chunk_id - 1,
            text="Some retrieved text.",
            char_start=0,
            char_end=20,
            created_at="2026-07-29T00:00:00Z",
        ),
        score=0.5,
        is_neighbour=is_neighbour,
    )


@pytest.fixture
def world(tmp_path: Path, settings: Settings, embedder: HashingEmbedder) -> World:
    return build_world(tmp_path, settings, embedder)


@pytest.fixture
def wire(world: World, monkeypatch: pytest.MonkeyPatch):
    """Install a throwaway world as the API's process-wide singletons.

    `api.deps` normally builds those in the lifespan, which loads the real
    embedding model and reads the real provider config. The `TestClient` below
    is deliberately *not* used as a context manager, so the lifespan never runs
    and these are the only singletons a route can reach.
    """

    def install(**kwargs) -> TestClient:
        copilot = CopilotOrchestrator(runtime=runtime_for(world, **kwargs))
        monkeypatch.setattr(deps, "_settings", world.settings)
        monkeypatch.setattr(deps, "_database", world.db)
        monkeypatch.setattr(deps, "_orchestrator", copilot)
        return TestClient(app)

    return install


@pytest.fixture
def client(wire) -> TestClient:
    """A client with nothing scripted, so any model call raises."""
    return wire(responses=[])


def upload(name: str, body: bytes) -> tuple[str, tuple[str, bytes, str]]:
    return ("files", (name, body, "text/plain"))


# --- Singletons -------------------------------------------------------------


def test_asking_for_a_singleton_before_startup_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Better than the `AttributeError` on `None` a bare global would give."""
    monkeypatch.setattr(deps, "_settings", None)
    monkeypatch.setattr(deps, "_database", None)
    monkeypatch.setattr(deps, "_orchestrator", None)

    for accessor in (deps.settings, deps.database, deps.orchestrator):
        with pytest.raises(RuntimeError, match="before startup"):
            accessor()


def test_shutdown_drops_the_singletons(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(deps, "_database", world.db)

    deps.shutdown()

    with pytest.raises(RuntimeError):
        deps.database()


# --- Health -----------------------------------------------------------------


def test_health_reports_what_the_status_line_shows(client: TestClient) -> None:
    body = client.get("/api/health").json()

    assert body["provider"] == "gemini"
    assert body["model"] == "scripted-test-model"
    assert body["has_api_key"] is True
    # No planner model was wired, so the standing roster runs instead.
    assert body["supervisor"] is False
    assert body["device"]
    assert isinstance(body["storage_is_temporary"], bool)


def test_storage_under_the_system_temp_directory_is_flagged() -> None:
    """`prepare_storage` relocates there silently when the real location fails.

    The pre-overhaul check was `os.path.exists("/tmp")`, which is true on every
    Unix machine, so it warned everybody unconditionally.
    """
    assert _is_temporary(Path(tempfile.gettempdir()) / "copilot") is True
    assert _is_temporary(Path.cwd()) is False


# --- Meetings ---------------------------------------------------------------


def test_the_meeting_list_carries_its_counts(client: TestClient, world: World) -> None:
    body = client.get("/api/meetings").json()

    assert len(body) == 1
    assert body[0]["id"] == world.meeting_id
    assert body[0]["title"] == TITLE
    assert body[0]["material_count"] == 1
    assert body[0]["brief_count"] == 0


def test_creating_a_meeting_splits_attendees_back_out(client: TestClient) -> None:
    """The column stores one comma-joined string; the wire format is arrays."""
    response = client.post(
        "/api/meetings",
        json={
            "title": "Quarterly review",
            "date": "2026-08-01",
            "attendees": ["Priya", "Marcus"],
            "tags": ["planning"],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["attendees"] == ["Priya", "Marcus"]
    assert body["tags"] == ["planning"]
    assert client.get(f"/api/meetings/{body['id']}").json()["attendees"] == [
        "Priya",
        "Marcus",
    ]


def test_blank_attendees_come_back_as_an_empty_list_not_one_empty_string(
    client: TestClient,
) -> None:
    """`", ".join` on stripped-to-nothing input would store a lone comma."""
    body = client.post(
        "/api/meetings", json={"title": "Standup", "attendees": ["", "  "], "tags": []}
    ).json()

    assert body["attendees"] == []
    assert body["tags"] == []


def test_a_meeting_needs_a_title(client: TestClient) -> None:
    assert client.post("/api/meetings", json={"title": "   "}).status_code == 422


def test_an_unknown_meeting_is_a_404(client: TestClient) -> None:
    response = client.get("/api/meetings/meeting_nonexistent")

    assert response.status_code == 404
    assert response.json()["kind"] == "MeetingNotFoundError"


def test_deleting_a_meeting_takes_everything_under_it(
    client: TestClient, world: World
) -> None:
    assert client.delete(f"/api/meetings/{world.meeting_id}").status_code == 204

    assert client.get(f"/api/meetings/{world.meeting_id}").status_code == 404
    assert client.get("/api/meetings").json() == []
    assert world.db.count_chunks(world.meeting_id) == 0
    assert not world.settings.index_path(world.meeting_id).exists()


def test_deleting_a_meeting_twice_is_a_404_the_second_time(
    client: TestClient, world: World
) -> None:
    client.delete(f"/api/meetings/{world.meeting_id}")

    assert client.delete(f"/api/meetings/{world.meeting_id}").status_code == 404


# --- Materials --------------------------------------------------------------


def test_materials_are_listed_without_their_text(
    client: TestClient, world: World
) -> None:
    body = client.get(f"/api/meetings/{world.meeting_id}/materials").json()

    assert len(body) == 1
    assert body[0]["filename"] == "minutes.txt"
    assert body[0]["char_count"] > 0
    assert "text" not in body[0]


def test_a_material_with_no_filename_is_given_one(
    client: TestClient, world: World
) -> None:
    """Both columns are nullable and real rows in `data/briefs.db` have them null."""
    world.db.add_material(world.meeting_id, None, None, "Some notes.")

    body = client.get(f"/api/meetings/{world.meeting_id}/materials").json()

    assert {"Untitled", "minutes.txt"} == {row["filename"] for row in body}
    assert "unknown" in {row["media_type"] for row in body}


def test_listing_materials_for_an_unknown_meeting_is_a_404(client: TestClient) -> None:
    assert (
        client.get("/api/meetings/meeting_nonexistent/materials").status_code == 404
    )


def test_uploading_a_file_indexes_it_as_well_as_storing_it(
    client: TestClient, world: World
) -> None:
    meeting_id = world.db.create_meeting("Fresh Meeting")

    body = client.post(
        f"/api/meetings/{meeting_id}/materials",
        files=[upload("notes.txt", b"The budget was approved and launch is in March.")],
    ).json()

    assert body["ingested"] == 1
    assert body["failed"] == 0
    assert body["results"][0]["chunks"] > 0
    # Indexed, not merely stored: searchable straight away.
    assert deps.orchestrator().retriever.recall(meeting_id, query="launch", k=2)


def test_one_bad_file_among_good_ones_costs_only_the_bad_file(
    client: TestClient, world: World
) -> None:
    """A multi-file upload is deliberately not all-or-nothing."""
    meeting_id = world.db.create_meeting("Fresh Meeting")

    body = client.post(
        f"/api/meetings/{meeting_id}/materials",
        files=[
            upload("good.txt", b"The migration deadline is the end of the quarter."),
            upload("empty.txt", b"   "),
            upload("also-good.txt", b"Priya owns the capacity model."),
        ],
    ).json()

    assert body["ingested"] == 2
    assert body["failed"] == 1
    outcomes = {row["filename"]: row for row in body["results"]}
    assert outcomes["empty.txt"]["success"] is False
    assert outcomes["empty.txt"]["error"]
    assert outcomes["empty.txt"]["material_id"] is None
    assert outcomes["good.txt"]["success"] is True
    # The failure did not roll the good ones back.
    assert len(world.db.get_materials(meeting_id)) == 2


def test_an_oversize_file_is_refused_without_reaching_the_parser(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(materials_route, "MAX_UPLOAD_BYTES", 32)
    meeting_id = world.db.create_meeting("Fresh Meeting")

    body = client.post(
        f"/api/meetings/{meeting_id}/materials",
        files=[
            upload("huge.txt", b"x" * 64),
            upload("small.txt", b"The budget was approved."),
        ],
    ).json()

    outcomes = {row["filename"]: row for row in body["results"]}
    assert outcomes["huge.txt"]["success"] is False
    assert "limit" in outcomes["huge.txt"]["error"]
    assert outcomes["small.txt"]["success"] is True
    assert body["ingested"] == 1


def test_uploading_to_an_unknown_meeting_is_a_404(client: TestClient) -> None:
    response = client.post(
        "/api/meetings/meeting_nonexistent/materials",
        files=[upload("notes.txt", b"Some notes.")],
    )

    assert response.status_code == 404


def test_pasted_text_is_marked_as_pasted(client: TestClient, world: World) -> None:
    """So the materials list can tell a pasted note from an uploaded `.txt`."""
    meeting_id = world.db.create_meeting("Fresh Meeting")

    body = client.post(
        f"/api/meetings/{meeting_id}/materials/text",
        json={"text": "The vendor assessment is still open.", "filename": "note.txt"},
    ).json()

    assert body["success"] is True
    assert body["characters"] == len("The vendor assessment is still open.")

    listed = client.get(f"/api/meetings/{meeting_id}/materials").json()
    assert listed[0]["media_type"] == "pasted"


def test_pasting_nothing_is_refused(client: TestClient, world: World) -> None:
    response = client.post(
        f"/api/meetings/{world.meeting_id}/materials/text", json={"text": ""}
    )

    assert response.status_code == 422


def test_deleting_a_material_takes_its_vectors_with_it(
    client: TestClient, world: World
) -> None:
    """Deleting the row alone would leave the document turning up in search."""
    assert client.delete(f"/api/materials/{world.material_id}").status_code == 204

    assert client.get(f"/api/meetings/{world.meeting_id}/materials").json() == []
    assert world.db.count_chunks(world.meeting_id) == 0
    # The index and the chunk store still agree, so retrieval does not raise.
    assert deps.orchestrator().retriever.recall(world.meeting_id, query="budget") == []


def test_deleting_an_unknown_material_is_a_404(client: TestClient) -> None:
    response = client.delete("/api/materials/material_nonexistent")

    assert response.status_code == 404
    assert "material_nonexistent" in response.json()["detail"]


# --- Briefs -----------------------------------------------------------------


def test_generating_a_brief_returns_the_document_and_its_trace(
    wire, world: World
) -> None:
    client = wire(responses=[brief_payload(world)])

    body = client.post(f"/api/meetings/{world.meeting_id}/brief").json()

    assert body["ok"] is True
    assert body["warning"] is None
    assert body["brief"]["meeting_title"] == TITLE
    assert body["brief_id"]
    assert body["provider"] == "gemini"
    assert body["model"] == "scripted-test-model"
    # `null` here is the value that means "not stored", so a brief that reached
    # the database has to carry the timestamp the database gave it.
    assert body["stored_at"] == world.db.get_brief_by_id(body["brief_id"]).created_at

    trace = body["trace"]
    assert [task["name"] for task in trace["plan"]] == [t.name for t in DEFAULT_ROSTER]
    assert trace["plan_source"] == "default"
    assert trace["chunks"] > 0
    assert trace["findings"]
    assert all(finding["ok"] for finding in trace["findings"])
    assert any(finding["hits"] > 0 for finding in trace["findings"])
    assert "\n".join(trace["notes"])


def test_hits_and_neighbours_are_counted_separately() -> None:
    """A neighbour was pulled in for context, not because it matched.

    Counting it as a hit would overstate how much the search actually found —
    a finding with one real match and four neighbours would read as five.
    Tested against a hand-built `Finding` because the corpus in
    `tests.agentworld` is small enough that every neighbour is already
    somebody's hit, so a run through the graph cannot exercise the subtraction.
    """
    finding = Finding(
        task=ResearchTask(name="risks", query="risks and blockers"),
        results=(_scored(1, is_neighbour=False), _scored(2, is_neighbour=True)),
    )
    run = BriefRun(findings=(finding,))

    out = brief_trace(run).findings[0]

    assert (out.hits, out.neighbours) == (1, 1)
    assert out.ok is True
    assert out.error is None


def test_a_failed_finding_counts_nothing_rather_than_going_negative() -> None:
    """`neighbours` is a subtraction, and an errored finding has no results."""
    run = BriefRun(
        findings=(
            Finding(
                task=ResearchTask(name="risks", query="risks"),
                error="index unreadable",
            ),
        )
    )

    out = brief_trace(run).findings[0]

    assert (out.hits, out.neighbours) == (0, 0)
    assert out.ok is False
    assert out.error == "index unreadable"


def test_a_brief_that_could_not_be_stored_is_a_success_with_a_warning(
    wire, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ok` means *a brief exists*. Throwing a usable document away serves nobody."""
    client = wire(responses=[brief_payload(world)])

    def refuse(**kwargs):
        raise StorageError("database is locked")

    monkeypatch.setattr(world.db, "save_brief", refuse)

    response = client.post(f"/api/meetings/{world.meeting_id}/brief")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["brief"] is not None
    assert body["brief_id"] is None
    assert body["stored_at"] is None
    assert "could not be stored" in body["warning"]


def test_a_failed_specialist_is_named_without_failing_the_brief(
    wire, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = wire(responses=[brief_payload(world)])
    retriever = deps.orchestrator().retriever
    real_recall = retriever.recall

    def flaky(meeting_id, query="", k=None, **kwargs):
        if "risks" in query:
            raise RetrievalError("index unreadable")
        return real_recall(meeting_id, query=query, k=k, **kwargs)

    monkeypatch.setattr(retriever, "recall", flaky)

    body = client.post(f"/api/meetings/{world.meeting_id}/brief").json()

    assert body["ok"] is True
    assert body["failed_tasks"] == ["risks"]
    failed = [f for f in body["trace"]["findings"] if not f["ok"]]
    assert [f["name"] for f in failed] == ["risks"]
    assert failed[0]["error"] == "index unreadable"


def test_a_meeting_with_no_materials_is_refused_before_the_graph_runs(
    client: TestClient, world: World
) -> None:
    """A precondition, not a run outcome — and no responses are scripted, so
    reaching the model would raise rather than return a 422."""
    empty = world.db.create_meeting("Empty Meeting")

    response = client.post(f"/api/meetings/{empty}/brief")

    assert response.status_code == 422
    assert "Upload at least one document" in response.json()["detail"]


def test_briefing_an_unknown_meeting_is_a_404(client: TestClient) -> None:
    assert client.post("/api/meetings/meeting_nonexistent/brief").status_code == 404


def test_brief_history_lists_every_version(wire, world: World) -> None:
    client = wire(responses=[brief_payload(world), brief_payload(world)])
    client.post(f"/api/meetings/{world.meeting_id}/brief")
    client.post(f"/api/meetings/{world.meeting_id}/brief")

    history = client.get(f"/api/meetings/{world.meeting_id}/briefs").json()

    assert len(history) == 2
    assert all(row["model"] == "scripted-test-model" for row in history)
    assert all(row["meeting_id"] == world.meeting_id for row in history)


def test_a_recalled_brief_has_no_trace(wire, world: World) -> None:
    """`None` rather than an empty `Trace`, so the UI can tell recalled from
    generated-with-nothing-found."""
    client = wire(responses=[brief_payload(world)])
    generated = client.post(f"/api/meetings/{world.meeting_id}/brief").json()

    body = client.get(f"/api/briefs/{generated['brief_id']}").json()

    assert body["ok"] is True
    assert body["trace"] is None
    assert body["stored_at"]
    assert body["brief"]["meeting_title"] == TITLE


def test_the_latest_brief_is_a_404_until_one_exists(wire, world: World) -> None:
    client = wire(responses=[brief_payload(world)])

    assert client.get(f"/api/meetings/{world.meeting_id}/brief/latest").status_code == 404

    client.post(f"/api/meetings/{world.meeting_id}/brief")

    assert client.get(f"/api/meetings/{world.meeting_id}/brief/latest").status_code == 200


def test_an_unknown_brief_id_is_a_404(client: TestClient) -> None:
    assert client.get("/api/briefs/brief_nonexistent").status_code == 404


def test_a_stored_brief_that_no_longer_validates_is_a_422_not_a_404(
    client: TestClient, world: World
) -> None:
    """Briefs are persisted as raw dicts, so history can outlive a schema.

    Reporting it as "no brief found" would hide a real and different situation.
    """
    brief_id = world.db.save_brief(
        meeting_id=world.meeting_id, model="m", brief_dict={"meeting_title": ""}
    )

    for path in (f"/api/briefs/{brief_id}", f"/api/meetings/{world.meeting_id}/brief/latest"):
        response = client.get(path)
        assert response.status_code == 422
        assert response.json()["kind"] == "InvalidBriefError"


# --- Q&A --------------------------------------------------------------------


def test_an_answer_comes_back_with_its_sources(wire, world: World) -> None:
    client = wire(responses=["Priya owns the capacity model."])

    body = client.post(
        f"/api/meetings/{world.meeting_id}/qa",
        json={"question": "Who owns the capacity model?"},
    ).json()

    assert body["ok"] is True
    assert body["answer"] == "Priya owns the capacity model."
    assert body["sources"]
    assert all("#c" in source for source in body["sources"])
    assert body["error"] is None
    assert body["trace"]["chunks"] > 0
    # A Q&A run has no plan behind it, so those fields stay empty.
    assert body["trace"]["plan"] == []


def test_a_retrieval_failure_is_reported_rather_than_dressed_as_no_answer(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The graph answers from the same node either way; the wire format does not.

    This is the counterpart to the brief's `ok`-with-a-warning: for an answer,
    the text alongside an error is the "nothing retrieved" boilerplate, and
    returning it as an answer would disguise a broken index.
    """

    def broken(*args, **kwargs):
        raise RetrievalError("index unreadable")

    monkeypatch.setattr(deps.orchestrator().retriever, "recall", broken)

    response = client.post(
        f"/api/meetings/{world.meeting_id}/qa", json={"question": "What are the risks?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error"] == "index unreadable"


def test_asking_about_a_meeting_with_no_materials_is_refused(
    client: TestClient, world: World
) -> None:
    empty = world.db.create_meeting("Empty Meeting")

    response = client.post(f"/api/meetings/{empty}/qa", json={"question": "What?"})

    assert response.status_code == 422
    assert "Upload at least one document" in response.json()["detail"]


def test_an_empty_question_never_reaches_the_graph(
    client: TestClient, world: World
) -> None:
    response = client.post(
        f"/api/meetings/{world.meeting_id}/qa", json={"question": "   "}
    )

    assert response.status_code == 422


def test_asking_about_an_unknown_meeting_is_a_404(client: TestClient) -> None:
    response = client.post(
        "/api/meetings/meeting_nonexistent/qa", json={"question": "What?"}
    )

    assert response.status_code == 404


# --- The status table -------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (MeetingNotFoundError("m1"), 404),
        (UnsupportedFileTypeError("deck.xyz", (".txt",)), 415),
        (EmptyDocumentError("nothing readable"), 422),
        (IngestionError("malformed"), 400),
        (InvalidBriefError("does not validate"), 422),
        (SynthesisError("upstream timed out"), 502),
        (MissingAPIKeyError("gemini", "GEMINI_API_KEY"), 503),
        (UnknownProviderError("who?"), 503),
        (PromptError("template missing"), 503),
        (ConfigurationError("misconfigured"), 503),
        (IndexOutOfSyncError("index and store disagree"), 500),
        (RetrievalError("index unreadable"), 500),
        (StorageError("database is locked"), 500),
        (CopilotError("something else"), 500),
    ],
    ids=lambda value: type(value).__name__ if isinstance(value, Exception) else str(value),
)
def test_every_error_maps_to_its_status(error: CopilotError, expected: int) -> None:
    """The table is ordered and subclasses must precede their bases.

    Each of the 4xx entries here is a subclass of something that maps
    elsewhere: move `InvalidBriefError` below `SynthesisError` and it becomes a
    502, move `MeetingNotFoundError` below `StorageError` and a typo'd id
    becomes a 500. The distinct expectations are what catch that.
    """
    assert status_for(error) == expected


def test_an_error_from_a_route_carries_its_class_name(
    wire, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`kind` is what lets the UI say "no API key" rather than "request failed"."""
    client = wire(responses=[])

    def no_key(**kwargs):
        raise MissingAPIKeyError("gemini", "GEMINI_API_KEY")

    monkeypatch.setattr(deps.orchestrator(), "generate_brief", no_key)

    response = client.post(f"/api/meetings/{world.meeting_id}/brief")

    assert response.status_code == 503
    assert response.json()["kind"] == "MissingAPIKeyError"
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_an_unknown_api_route_stays_a_json_404(client: TestClient) -> None:
    response = client.get("/api/nope")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


# --- The SPA fallback's scoping ---------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "status_code", "expected"),
    [
        ("GET", "/meetings/meeting_1", 404, True),
        ("GET", "/", 404, True),
        # An unknown API route must not return the HTML shell, or every
        # frontend typo would look like a successful request returning nonsense.
        ("GET", "/api/nope", 404, False),
        ("POST", "/meetings", 404, False),
        ("GET", "/meetings", 405, False),
        ("GET", "/meetings", 500, False),
    ],
)
def test_only_unmatched_page_requests_get_the_html_shell(
    method: str, path: str, status_code: int, expected: bool
) -> None:
    assert serves_index(method, path, status_code) is expected


# --- The per-meeting lock ---------------------------------------------------


def test_two_requests_on_one_meeting_serialize() -> None:
    """`Retriever.recall` writes the index when it backfills, so reads contend too."""
    entered, release, second = (threading.Event() for _ in range(3))

    def hold() -> None:
        with deps.meeting_lock("meeting_lock_same"):
            entered.set()
            release.wait(timeout=5)

    def contend() -> None:
        with deps.meeting_lock("meeting_lock_same"):
            second.set()

    holder = threading.Thread(target=hold)
    holder.start()
    assert entered.wait(timeout=5)

    contender = threading.Thread(target=contend)
    contender.start()
    assert not second.wait(timeout=0.25)

    release.set()
    assert second.wait(timeout=5)
    holder.join(timeout=5)
    contender.join(timeout=5)


def test_a_lock_on_one_meeting_does_not_block_another() -> None:
    """The whole reason the lock is per meeting: a 40-second brief on one
    meeting must not stall an upload to a different one."""
    done = threading.Event()

    def other() -> None:
        with deps.meeting_lock("meeting_lock_b"):
            done.set()

    with deps.meeting_lock("meeting_lock_a"):
        thread = threading.Thread(target=other)
        thread.start()
        assert done.wait(timeout=5)

    thread.join(timeout=5)


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/api/meetings/{id}/brief", None),
        ("POST", "/api/meetings/{id}/qa", {"question": "What are the risks?"}),
        ("POST", "/api/meetings/{id}/materials/text", {"text": "A pasted note."}),
        ("DELETE", "/api/meetings/{id}", None),
    ],
)
def test_every_index_writing_route_takes_the_meetings_lock(
    wire, world: World, monkeypatch: pytest.MonkeyPatch, method, path, body
) -> None:
    taken: list[str] = []

    @contextmanager
    def recording(meeting_id: str) -> Iterator[None]:
        taken.append(meeting_id)
        yield

    monkeypatch.setattr(deps, "meeting_lock", recording)
    client = wire(responses=[brief_payload(world), "Dependency on the platform team."])

    client.request(method, path.format(id=world.meeting_id), json=body)

    assert taken == [world.meeting_id]


def test_an_upload_takes_the_lock_once_per_file_that_reaches_the_parser(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per file rather than once for the batch, because the body read in
    between is I/O: holding a meeting's index lock across it would serialize
    uploads on the network instead of on the index. A file rejected for its
    size never reaches the index, so it never takes the lock either."""
    taken: list[str] = []

    @contextmanager
    def recording(meeting_id: str) -> Iterator[None]:
        taken.append(meeting_id)
        yield

    monkeypatch.setattr(deps, "meeting_lock", recording)
    monkeypatch.setattr(materials_route, "MAX_UPLOAD_BYTES", 32)
    meeting_id = world.db.create_meeting("Fresh Meeting")

    client.post(
        f"/api/meetings/{meeting_id}/materials",
        files=[
            upload("one.txt", b"The budget was approved."),
            upload("huge.txt", b"x" * 64),
            upload("two.txt", b"Priya owns the capacity model."),
        ],
    )

    assert taken == [meeting_id, meeting_id]


def test_deleting_a_material_locks_its_meeting_not_the_material(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    taken: list[str] = []

    @contextmanager
    def recording(meeting_id: str) -> Iterator[None]:
        taken.append(meeting_id)
        yield

    monkeypatch.setattr(deps, "meeting_lock", recording)

    client.delete(f"/api/materials/{world.material_id}")

    assert taken == [world.meeting_id]
