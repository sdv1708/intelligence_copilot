"""Small shared helpers: ID generation and timing.

Configuration and logging live in `core.config` and `core.logging_config`. The
`get_env` / `get_storage_path` / `log_message` shims that used to sit at the
bottom of this module went with their last callers in Chunk 7; there is now one
way to read configuration and one way to log.
"""

from __future__ import annotations

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
