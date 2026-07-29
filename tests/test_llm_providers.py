"""Chat model construction: ids, keys, and per-provider quirks.

Nothing here touches the network. Every provider client is constructed with a
dummy key and inspected; not one request is issued.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import Provider, Settings
from core.exceptions import MissingAPIKeyError, UnknownProviderError
from core.llm_providers import (
    NO_SAMPLING_PARAMS,
    build_chat_model,
    describe,
    resolve_provider,
    structured,
    supports_sampling_params,
)
from core.schema import MeetingBrief
from tests.fakes import ScriptedChatModel

# Models retired by the API. A request naming one of these is a 404, which is
# what the pre-overhaul Anthropic default had quietly become.
RETIRED_MODEL_IDS = {
    "claude-3-5-sonnet-20241022",
    "claude-3-5-sonnet-20240620",
    "claude-3-opus-20240229",
    "claude-3-5-haiku-20241022",
    "claude-3-7-sonnet-20250219",
}


@pytest.fixture
def configured(tmp_path: Path) -> Settings:
    """Settings with a usable key for every provider."""
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        llm_provider=Provider.GEMINI,
        gemini_api_key="test-gemini-key",
        openai_api_key="test-openai-key",
        anthropic_api_key="test-anthropic-key",
    )
    settings.prepare_storage()
    return settings


# --- Provider resolution ----------------------------------------------------


def test_resolve_provider_accepts_names_and_enums():
    assert resolve_provider("anthropic") is Provider.ANTHROPIC
    assert resolve_provider("  OpenAI  ") is Provider.OPENAI
    assert resolve_provider(Provider.GEMINI) is Provider.GEMINI


def test_resolve_provider_rejects_anything_else():
    with pytest.raises(UnknownProviderError, match="gemini, openai, anthropic"):
        resolve_provider("llama")


def test_a_missing_key_is_a_configuration_error(tmp_path: Path):
    settings = Settings(
        _env_file=None, data_dir=tmp_path / "data", llm_provider=Provider.ANTHROPIC
    )
    settings.prepare_storage()

    with pytest.raises(MissingAPIKeyError, match="ANTHROPIC_API_KEY"):
        build_chat_model(Provider.ANTHROPIC, settings=settings)


# --- Model ids --------------------------------------------------------------


def test_default_model_ids_are_not_retired(configured: Settings):
    for provider in Provider:
        assert configured.model_for(provider) not in RETIRED_MODEL_IDS


def test_model_id_comes_from_settings(configured: Settings):
    chosen = configured.model_copy(update={"anthropic_model": "claude-sonnet-5"})
    model = build_chat_model(Provider.ANTHROPIC, settings=chosen)
    assert describe(model) == "claude-sonnet-5"


def test_an_explicit_model_overrides_the_configured_one(configured: Settings):
    model = build_chat_model(
        Provider.OPENAI, settings=configured, model="gpt-4o-mini"
    )
    assert describe(model) == "gpt-4o-mini"


# --- Sampling parameters ----------------------------------------------------


@pytest.mark.parametrize(
    "model_id",
    ["claude-opus-5", "claude-sonnet-5", "claude-opus-4-8", "gpt-5", "gpt-5-mini"],
)
def test_models_that_reject_sampling_parameters_are_known(model_id: str):
    assert not supports_sampling_params(model_id)


@pytest.mark.parametrize(
    "model_id", ["gpt-4o", "claude-sonnet-4-6", "gemini-2.5-flash", "claude-haiku-4-5"]
)
def test_models_that_accept_sampling_parameters_are_left_alone(model_id: str):
    assert supports_sampling_params(model_id)


def test_temperature_is_omitted_for_models_that_reject_it(configured: Settings):
    """Sending `temperature` to Opus 4.7+ is a 400, not a warning."""
    chosen = configured.model_copy(update={"anthropic_model": "claude-opus-5"})
    model = build_chat_model(Provider.ANTHROPIC, settings=chosen)
    assert model.temperature is None


def test_temperature_is_sent_to_models_that_accept_it(configured: Settings):
    chosen = configured.model_copy(
        update={"anthropic_model": "claude-sonnet-4-6", "llm_temperature": 0.42}
    )
    model = build_chat_model(Provider.ANTHROPIC, settings=chosen)
    assert model.temperature == pytest.approx(0.42)


def test_no_sampling_list_covers_dated_and_suffixed_variants():
    for family in NO_SAMPLING_PARAMS:
        assert not supports_sampling_params(f"{family}-20260101")


# --- Per-provider wiring ----------------------------------------------------


def test_anthropic_client_carries_the_output_cap(configured: Settings):
    model = build_chat_model(Provider.ANTHROPIC, settings=configured, max_tokens=4096)
    assert model.max_tokens == 4096


def test_openai_client_carries_the_output_cap(configured: Settings):
    """`gpt-4` was configured with max_tokens=30000, above any model's cap."""
    model = build_chat_model(Provider.OPENAI, settings=configured)
    assert model.max_tokens == configured.llm_max_tokens
    assert model.temperature == pytest.approx(configured.llm_temperature)


def test_gemini_client_uses_its_own_spelling_of_the_output_cap(
    configured: Settings,
):
    model = build_chat_model(Provider.GEMINI, settings=configured, max_tokens=2048)
    assert model.max_output_tokens == 2048


def test_timeout_and_retries_come_from_settings(configured: Settings):
    chosen = configured.model_copy(
        update={"llm_timeout_seconds": 45, "llm_max_retries": 5}
    )
    model = build_chat_model(Provider.ANTHROPIC, settings=chosen)
    assert model.default_request_timeout == pytest.approx(45)
    assert model.max_retries == 5


def test_the_provider_defaults_to_the_configured_one(
    configured: Settings, monkeypatch: pytest.MonkeyPatch
):
    """Called with no provider, `build_chat_model` reads `Settings`.

    `CopilotRuntime.build` relies on this, and it is what replaced the
    `get_llm_provider` alias the pre-overhaul UI called.
    """
    monkeypatch.setattr("core.llm_providers.get_settings", lambda: configured)
    assert describe(build_chat_model()).endswith(
        configured.model_for(configured.llm_provider)
    )


# --- Structured output ------------------------------------------------------


def test_structured_pins_tool_calling_where_the_provider_offers_a_choice():
    """OpenAI defaults to strict json_schema, which rejects our constraints."""
    model = ScriptedChatModel([{"meeting_title": "x"}])
    structured(model, MeetingBrief)

    assert model.structured_schemas == [MeetingBrief]
    assert model.structured_kwargs[0]["method"] == "function_calling"
    assert model.structured_kwargs[0]["include_raw"] is True


def test_describe_falls_back_to_the_class_name():
    class Anonymous:
        pass

    assert describe(Anonymous()) == "Anonymous"
