"""The dependencies every node needs, passed as LangGraph context.

Nodes take `(state, runtime)` and read their collaborators off
`runtime.context`. Nothing in `agents/` constructs a database, an embedder, or
an LLM client on its own, which is what lets the whole graph be driven in tests
with a throwaway SQLite file, `HashingEmbedder`, and a scripted model — no
network, no downloads.

It is also why one chat client is shared across the run. `Synthesizer` was
written in Chunk 4 to accept a model rather than build one precisely so a graph
could do this: the supervisor and the writer talk to the same client instead of
opening a connection per node.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.config import Provider, Settings, get_settings
from core.db import Database
from core.embed import Embedder
from core.llm_providers import build_chat_model
from core.logging_config import get_logger
from core.recall import Retriever
from core.synthesis import Synthesizer

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = get_logger(__name__)


@dataclass
class CopilotRuntime:
    """Collaborators shared by every node of every graph.

    Built once per process — `api/deps.py` does it at startup — and passed to
    `graph.invoke(..., context=runtime)`.
    """

    db: Database
    settings: Settings
    retriever: Retriever
    synthesizer: Synthesizer
    #: Model the supervisor plans with. `None` means the default roster runs
    #: unconditionally — the graph still works, it just stops asking.
    planner_model: Any | None = None
    provider: str = ""
    #: Ceiling on how many tasks a supervisor's plan may contain. A plan longer
    #: than this is truncated rather than rejected: an over-eager supervisor
    #: should cost context, not the run.
    planner_max_tasks: int = 8

    @property
    def plans_with_llm(self) -> bool:
        return self.planner_model is not None

    @classmethod
    def build(
        cls,
        *,
        db: Database | None = None,
        settings: Settings | None = None,
        provider: Provider | str | None = None,
        chat_model: BaseChatModel | None = None,
        planner_model: BaseChatModel | None = None,
        embedder: Embedder | None = None,
        plan_with_llm: bool | None = None,
        auto_repair: bool = True,
    ) -> CopilotRuntime:
        """Assemble a runtime, building whatever was not supplied.

        `chat_model` is the writer. `planner_model` defaults to the same client:
        planning and writing are the same kind of call to the same provider, and
        sharing the client is the point of taking one as an argument. Pass
        `plan_with_llm=False` to run the deterministic roster instead.
        """
        settings = settings or get_settings()
        database = db or Database(settings.db_path, settings=settings)
        model = (
            chat_model
            if chat_model is not None
            else build_chat_model(provider, settings=settings)
        )

        wants_planner = (
            settings.plan_with_llm if plan_with_llm is None else plan_with_llm
        )
        planner = planner_model if planner_model is not None else model
        if not wants_planner:
            planner = None

        return cls(
            db=database,
            settings=settings,
            retriever=Retriever(
                database,
                embedder=embedder,
                settings=settings,
                auto_repair=auto_repair,
            ),
            synthesizer=Synthesizer(model, provider=provider, settings=settings),
            planner_model=planner,
            provider=str(provider or settings.llm_provider),
            planner_max_tasks=settings.planner_max_tasks,
        )
