"""The process-wide singletons, and the lock that makes them safe to share.

Streamlit got this for free from `st.cache_resource`: one embedder, one chat
client, one database handle per session. Under an ASGI server the equivalent is
built once during startup and handed to every request, which is strictly better
— the model load happens at boot rather than on whoever's first request loses.

## Why there is a lock

FastAPI runs plain `def` endpoints on a threadpool, so two requests really can
be inside the orchestrator at once. `Database` is fine with that: it opens a
connection per call and never shares one across threads. The FAISS index is not.

`index_material`, `delete_material_everywhere` and — less obviously —
`Retriever.recall` all write `settings.index_path(meeting_id)`; recall does
because it calls `ensure_meeting_indexed` and will backfill anything missing.
Two of those at once on the same meeting is a corrupt index file.

The lock is therefore **per meeting**, not global. Two uploads to the same
meeting serialize; an upload to one meeting and a 40-second brief generation on
another do not block each other, which they would under a single global lock.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager

from agents.copilot_orchestrator import CopilotOrchestrator
from core.config import Settings, get_settings
from core.db import Database
from core.logging_config import get_logger

logger = get_logger(__name__)

_settings: Settings | None = None
_database: Database | None = None
_orchestrator: CopilotOrchestrator | None = None

# `defaultdict` under its own lock: two threads asking for the lock of a meeting
# neither has seen must not each create one.
_meeting_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)
_locks_guard = threading.Lock()


def startup() -> None:
    """Build everything once, before the first request arrives."""
    global _settings, _database, _orchestrator

    _settings = get_settings()
    _settings.prepare_storage()
    _database = Database(_settings.db_path)
    _database.init_db()
    _orchestrator = CopilotOrchestrator(provider=_settings.llm_provider.value)

    # Load the embedding model now. It is ~90MB off disk and the first request
    # to trigger it would otherwise pay several seconds for everyone else.
    from core.embed import get_embedder

    embedder = get_embedder(_settings)
    embedder.model  # noqa: B018 — the point is the side effect: load it now.
    logger.info(
        "API ready on %s (%s, %s)",
        _settings.data_dir,
        _orchestrator.model_name,
        embedder.device,
    )


def shutdown() -> None:
    global _settings, _database, _orchestrator
    _settings = _database = _orchestrator = None


def settings() -> Settings:
    if _settings is None:
        raise RuntimeError("Settings requested before startup")
    return _settings


def database() -> Database:
    if _database is None:
        raise RuntimeError("Database requested before startup")
    return _database


def orchestrator() -> CopilotOrchestrator:
    if _orchestrator is None:
        raise RuntimeError("Orchestrator requested before startup")
    return _orchestrator


@contextmanager
def meeting_lock(meeting_id: str) -> Iterator[None]:
    """Hold the write lock for one meeting's index."""
    with _locks_guard:
        lock = _meeting_locks[meeting_id]
    with lock:
        yield
