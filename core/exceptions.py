"""Exception hierarchy for the Executive Intelligence Copilot.

Every failure mode the system can hit deliberately maps to one of these, so
callers can catch at the granularity they care about: a single agent node can
catch `RetrievalError` without also swallowing configuration bugs.
"""

from __future__ import annotations


class CopilotError(Exception):
    """Base class for every error raised by this application."""


# --- Configuration ----------------------------------------------------------


class ConfigurationError(CopilotError):
    """Application is misconfigured and cannot proceed."""


class MissingAPIKeyError(ConfigurationError):
    """No API key is available for the selected LLM provider."""

    def __init__(self, provider: str, env_var: str) -> None:
        super().__init__(
            f"No API key configured for provider '{provider}'. "
            f"Set {env_var} in your .env file or environment."
        )
        self.provider = provider
        self.env_var = env_var


class UnknownProviderError(ConfigurationError):
    """The configured LLM provider is not one we support."""


class PromptError(ConfigurationError):
    """A prompt template is missing, or was rendered with the wrong values.

    Rendering is strict on purpose: a renamed placeholder used to survive as a
    literal `{{context_blocks}}` in the text sent to the model, which produced a
    confidently wrong brief instead of an error.
    """


# --- Ingestion --------------------------------------------------------------


class IngestionError(CopilotError):
    """A document could not be taken into the system."""


class UnsupportedFileTypeError(IngestionError):
    """The uploaded file extension has no registered parser."""

    def __init__(self, filename: str, supported: tuple[str, ...]) -> None:
        super().__init__(
            f"Cannot parse '{filename}'. Supported types: {', '.join(supported)}."
        )
        self.filename = filename
        self.supported = supported


class EmptyDocumentError(IngestionError):
    """The document parsed successfully but yielded no usable text."""


# --- Storage ----------------------------------------------------------------


class StorageError(CopilotError):
    """A persistence operation failed."""


class MeetingNotFoundError(StorageError):
    """Referenced a meeting id that does not exist."""

    def __init__(self, meeting_id: str) -> None:
        super().__init__(f"No meeting found with id '{meeting_id}'.")
        self.meeting_id = meeting_id


# --- Retrieval --------------------------------------------------------------


class RetrievalError(CopilotError):
    """Semantic search could not be completed."""


class IndexOutOfSyncError(RetrievalError):
    """The vector index and the chunk store disagree about what exists.

    Raised instead of silently returning mismatched text, which is the failure
    mode the previous implementation had.
    """


# --- Synthesis --------------------------------------------------------------


class SynthesisError(CopilotError):
    """The LLM step failed to produce a usable result."""


class InvalidBriefError(SynthesisError):
    """The model returned output that does not satisfy the brief schema."""
