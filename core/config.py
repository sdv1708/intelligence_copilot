"""Typed application configuration.

Replaces the scattered `os.getenv` calls and the `os.path.exists("/tmp")`
heuristic that previously decided where data lived. Storage location is now an
explicit setting with a writability check, so a read-only deployment degrades
loudly rather than silently relocating the user's database.
"""

from __future__ import annotations

import tempfile
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.exceptions import MissingAPIKeyError
from core.logging_config import get_logger

logger = get_logger(__name__)


class Provider(StrEnum):
    """Supported LLM providers."""

    GEMINI = "gemini"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


_API_KEY_ENV_VARS: dict[Provider, str] = {
    Provider.GEMINI: "GEMINI_API_KEY",
    Provider.OPENAI: "OPENAI_API_KEY",
    Provider.ANTHROPIC: "ANTHROPIC_API_KEY",
}


class Settings(BaseSettings):
    """All runtime configuration, loaded from environment and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LLM ---------------------------------------------------------------

    llm_provider: Provider = Provider.GEMINI
    gemini_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None

    # Model ids are configuration, not constants: they change faster than this
    # codebase does. The defaults are the current generation of each provider;
    # override with ANTHROPIC_MODEL / OPENAI_MODEL / GEMINI_MODEL.
    anthropic_model: str = "claude-opus-5"
    openai_model: str = "gpt-4o"
    gemini_model: str = "gemini-2.5-flash"

    llm_temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    # A brief is a few thousand tokens of JSON, but reasoning models spend
    # output budget on thinking before they emit any of it, and the cap covers
    # both. 16k leaves room without risking an HTTP timeout on a non-streaming
    # request; every model in the defaults above allows at least that much.
    llm_max_tokens: int = Field(default=16000, gt=0)
    llm_timeout_seconds: int = Field(default=120, gt=0)
    llm_max_retries: int = Field(default=2, ge=0)

    # --- Storage -----------------------------------------------------------

    data_dir: Path = Path("data")

    # Explicit overrides. Aliases keep the old DB_PATH / FAISS_PATH env names
    # working for anyone with an existing .env.
    db_path_override: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("db_path_override", "db_path"),
    )
    faiss_dir_override: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("faiss_dir_override", "faiss_dir", "faiss_path"),
    )
    raw_dir_override: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("raw_dir_override", "raw_dir", "raw_path"),
    )

    # --- Embeddings --------------------------------------------------------

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = Field(default=384, gt=0)
    embedding_device: Literal["auto", "cpu", "cuda"] = "auto"
    embedding_batch_size: int | None = Field(default=None, gt=0)

    # --- Chunking and retrieval -------------------------------------------
    #
    # all-MiniLM-L6-v2 truncates input at 256 word-pieces (roughly 1000
    # characters of English). Chunks larger than that are silently cut off
    # before embedding, making their tails invisible to search -- which is why
    # the previous 4000-character chunks retrieved so poorly. Embed small,
    # then widen the LLM's view with neighbour expansion at retrieval time.

    chunk_size: int = Field(default=900, gt=0)
    chunk_overlap: int = Field(default=150, ge=0)
    retrieval_k: int = Field(default=8, gt=0)
    qa_retrieval_k: int = Field(default=12, gt=0)
    neighbour_radius: int = Field(default=1, ge=0)
    min_similarity: float = Field(default=0.15, ge=-1.0, le=1.0)

    # --- Observability -----------------------------------------------------

    log_level: str = "INFO"
    log_format: Literal["plain", "json"] = "plain"

    # --- Derived paths -----------------------------------------------------

    @property
    def db_path(self) -> Path:
        return self.db_path_override or self.data_dir / "briefs.db"

    @property
    def faiss_dir(self) -> Path:
        return self.faiss_dir_override or self.data_dir / "faiss"

    @property
    def raw_dir(self) -> Path:
        return self.raw_dir_override or self.data_dir / "raw"

    def index_path(self, meeting_id: str) -> Path:
        """Filesystem location of one meeting's vector index."""
        return self.faiss_dir / f"{meeting_id}.faiss"

    # --- Validation --------------------------------------------------------

    @model_validator(mode="after")
    def _check_overlap(self) -> Settings:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be smaller than "
                f"chunk_size ({self.chunk_size}); otherwise chunking cannot advance."
            )
        return self

    # --- Behaviour ---------------------------------------------------------

    def api_key_for(self, provider: Provider | None = None) -> str:
        """Return the API key for `provider`, raising if it is absent."""
        provider = provider or self.llm_provider
        secret = {
            Provider.GEMINI: self.gemini_api_key,
            Provider.OPENAI: self.openai_api_key,
            Provider.ANTHROPIC: self.anthropic_api_key,
        }[provider]

        if secret is None or not secret.get_secret_value().strip():
            raise MissingAPIKeyError(provider.value, _API_KEY_ENV_VARS[provider])
        return secret.get_secret_value()

    def model_for(self, provider: Provider | None = None) -> str:
        """Return the configured model id for `provider`."""
        provider = provider or self.llm_provider
        return {
            Provider.GEMINI: self.gemini_model,
            Provider.OPENAI: self.openai_model,
            Provider.ANTHROPIC: self.anthropic_model,
        }[provider]

    def has_api_key(self, provider: Provider | None = None) -> bool:
        """Check for a usable key without raising. For UI status display."""
        try:
            self.api_key_for(provider)
        except MissingAPIKeyError:
            return False
        return True

    def prepare_storage(self) -> None:
        """Create the data directories, falling back to temp if unwritable.

        Mutates `data_dir` in place when the configured location is read-only,
        which keeps the app usable on ephemeral hosts. Unlike the previous
        `/tmp` sniffing, this only happens on actual failure and is logged.
        """
        if not _is_writable(self.data_dir):
            fallback = Path(tempfile.gettempdir()) / "intelligence_copilot"
            logger.warning(
                "Data directory %s is not writable; falling back to %s. "
                "Data will not persist across restarts. Set DATA_DIR to a "
                "writable location to fix this.",
                self.data_dir,
                fallback,
            )
            self.data_dir = fallback

        for directory in (self.data_dir, self.faiss_dir, self.raw_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


def _is_writable(path: Path) -> bool:
    """Probe whether we can actually create files under `path`."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False
    return True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, configuring logging and storage once."""
    settings = Settings()
    configure_from(settings)
    return settings


def configure_from(settings: Settings) -> None:
    """Apply side effects a `Settings` instance implies."""
    from core.logging_config import configure_logging

    configure_logging(level=settings.log_level, fmt=settings.log_format)
    settings.prepare_storage()
    logger.info(
        "Configured: provider=%s data_dir=%s embeddings=%s",
        settings.llm_provider.value,
        settings.data_dir,
        settings.embedding_model,
    )


def reset_settings_cache() -> None:
    """Clear the cached settings. Used by tests."""
    get_settings.cache_clear()
