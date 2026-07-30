"""What the UI's status line reads."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter

from api import deps
from api.schemas import Health

router = APIRouter(prefix="/api", tags=["status"])


def _is_temporary(data_dir: Path) -> bool:
    """Whether storage fell back to the system temp directory.

    `Settings.prepare_storage` relocates there when the configured directory is
    unwritable, and says nothing about it. A user whose briefs will not survive
    a restart should be told, so the UI asks.

    The pre-overhaul version of this check was `os.path.exists("/tmp")`, which
    is true on every Unix machine and so warned everybody unconditionally.
    """
    try:
        return Path(data_dir).resolve().is_relative_to(
            Path(tempfile.gettempdir()).resolve()
        )
    except (OSError, ValueError):
        return False


@router.get("/health", response_model=Health)
def health() -> Health:
    settings = deps.settings()
    orchestrator = deps.orchestrator()

    from core.embed import get_device

    return Health(
        provider=orchestrator.provider_name,
        model=orchestrator.model_name,
        device=get_device(),
        supervisor=orchestrator.runtime.plans_with_llm,
        has_api_key=settings.has_api_key(),
        storage_dir=str(settings.data_dir),
        storage_is_temporary=_is_temporary(settings.data_dir),
    )
