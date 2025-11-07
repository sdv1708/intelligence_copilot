"""Utility functions: config, logging, ID generation, timers."""

import os
import logging
import uuid
import time
from datetime import datetime
from functools import wraps
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_env(key: str, default: str = None) -> str:
    """Safely fetch environment variable."""
    value = os.getenv(key, default)
    if value is None:
        logger.warning(f"Environment variable {key} not set")
    return value


def generate_id(prefix: str = "") -> str:
    """Generate a unique ID with optional prefix."""
    unique_part = str(uuid.uuid4())[:8]
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    if prefix:
        return f"{prefix}_{timestamp}_{unique_part}"
    return f"{timestamp}_{unique_part}"


def timer(func):
    """Decorator to time function execution."""
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        logger.info(f"{func.__name__} took {elapsed:.2f}s")
        return result
    return wrapper


def log_message(level: str, message: str):
    """Log a message at the specified level."""
    if level.upper() == "INFO":
        logger.info(message)
    elif level.upper() == "WARNING":
        logger.warning(message)
    elif level.upper() == "ERROR":
        logger.error(message)
    elif level.upper() == "DEBUG":
        logger.debug(message)

