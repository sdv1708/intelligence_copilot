"""Shared pytest fixtures.

Everything here is hermetic: no `.env` is read, no network is touched, and all
state lives under pytest's `tmp_path`. Tests that need the real embedding model
must be marked `@pytest.mark.slow`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import Provider, Settings, reset_settings_cache
from tests.fakes import HashingEmbedder, ScriptedChatModel


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop ambient env vars and the developer's real .env leaking into tests.

    The `env_file` override is the important one: without it any `Settings()`
    built inside the code under test picks up the developer's real API keys and
    provider choice, so the suite would pass locally and fail in CI.
    """
    monkeypatch.setitem(Settings.model_config, "env_file", None)

    for var in (
        "LLM_PROVIDER",
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DATA_DIR",
        "DB_PATH",
        "FAISS_PATH",
        "FAISS_DIR",
        "RAW_PATH",
        "LOG_LEVEL",
    ):
        monkeypatch.delenv(var, raising=False)
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings rooted at a throwaway directory, with a dummy key present."""
    configured = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        llm_provider=Provider.GEMINI,
        gemini_api_key="test-key-not-real",
    )
    configured.prepare_storage()
    return configured


@pytest.fixture
def embedder() -> HashingEmbedder:
    """Deterministic stand-in for the SentenceTransformer encoder."""
    return HashingEmbedder(dim=384)


@pytest.fixture
def scripted_llm() -> type[ScriptedChatModel]:
    """The class itself; tests construct it with their own canned responses."""
    return ScriptedChatModel
