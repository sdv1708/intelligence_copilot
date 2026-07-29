"""Logging setup.

Replaces the previous `log_message("INFO", ...)` string-dispatch helper with
standard library loggers, so log records carry module names, support `exc_info`,
and can be filtered per-package.
"""

from __future__ import annotations

import logging
import sys
from typing import Literal

_PLAIN_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
_DATE_FORMAT = "%H:%M:%S"

_configured = False


def configure_logging(
    level: str | int = "INFO",
    fmt: Literal["plain", "json"] = "plain",
    *,
    force: bool = False,
) -> None:
    """Install a root handler. Idempotent unless `force` is set.

    Streamlit re-executes the script on every interaction, so this must be safe
    to call repeatedly without stacking duplicate handlers.
    """
    global _configured
    if _configured and not force:
        return

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)

    handler = logging.StreamHandler(sys.stderr)
    if fmt == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_PLAIN_FORMAT, datefmt=_DATE_FORMAT))

    root.addHandler(handler)
    root.setLevel(level)

    # These are chatty at INFO and drown out our own records.
    for noisy in (
        "httpx",
        "httpcore",
        "urllib3",
        "sentence_transformers",
        "google_genai",
        "openai",
        "anthropic",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a module logger. Use `get_logger(__name__)` at module scope."""
    return logging.getLogger(name)


class _JsonFormatter(logging.Formatter):
    """Minimal JSON lines formatter for deployments that ship logs."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)
