"""Guards on the test harness itself.

If these fail, other tests may be silently reading the developer's real
credentials and passing for the wrong reason.
"""

from __future__ import annotations

from core.config import Settings


def test_settings_built_without_arguments_ignore_the_real_dotenv() -> None:
    """A bare Settings() inside code under test must not see the real .env."""
    settings = Settings()

    assert settings.gemini_api_key is None
    assert settings.openai_api_key is None
    assert settings.anthropic_api_key is None


def test_provider_falls_back_to_the_declared_default() -> None:
    assert Settings().llm_provider.value == "gemini"
