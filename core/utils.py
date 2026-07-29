"""Small shared helpers: ID generation and timing.

Configuration and logging have moved to `core.config` and `core.logging_config`.
The `get_env` / `get_storage_path` / `log_message` functions below are
transitional shims kept only so the not-yet-migrated modules (`db`, `embed`,
`document_handler`, `parsing`, the old orchestrator) keep running while the
overhaul proceeds. They are removed once those modules are rewritten.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Any, TypeVar

from core.logging_config import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def generate_id(prefix: str = "") -> str:
    """Generate a sortable, unique identifier.

    The timestamp leads so IDs sort chronologically as strings, which several
    queries and the brief history UI rely on.
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    unique = uuid.uuid4().hex[:8]
    return f"{prefix}_{timestamp}_{unique}" if prefix else f"{timestamp}_{unique}"


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string, for persisted timestamps."""
    return datetime.now(UTC).isoformat()


def timer(func: F) -> F:
    """Log how long a function took. Useful on the slow pipeline stages."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            logger.debug("%s took %.2fs", func.__qualname__, time.perf_counter() - start)

    return wrapper  # type: ignore[return-value]


# --- Transitional shims -----------------------------------------------------


def get_env(key: str, default: str | None = None) -> str | None:
    """Deprecated. Use `core.config.get_settings()`."""
    return os.getenv(key, default)


def get_storage_path(path_type: str = "data") -> str:
    """Deprecated. Use `core.config.get_settings()` paths."""
    from core.config import get_settings

    settings = get_settings()
    match path_type:
        case "faiss":
            path = settings.faiss_dir
        case "db":
            return str(settings.db_path)
        case "raw":
            path = settings.raw_dir
        case _:
            path = settings.data_dir
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


_LEVELS = {"INFO": 20, "WARNING": 30, "ERROR": 40, "DEBUG": 10}


def log_message(level: str, message: str) -> None:
    """Deprecated. Use a module logger from `core.logging_config.get_logger`."""
    logger.log(_LEVELS.get(level.upper(), 20), message)
