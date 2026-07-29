"""Construction of LangChain chat models, one per supported provider.

What changed from the previous version, and why:

* **Model ids came from memory and had gone stale.** `claude-3-5-sonnet-20241022`
  was retired in October 2025, so the Anthropic path returned a 404 for anyone
  who selected it. Ids now live in `Settings` and default to the current
  generation of each provider.
* **`gpt-4` was configured with `max_tokens=30000`.** That model's output cap is
  8192, so the OpenAI path could never have completed a single request.
* **Sampling parameters are no longer universal.** Claude Opus 4.7 and later,
  and the GPT-5 family, reject `temperature` outright. Sending it is a 400, not
  a warning, so `temperature` is omitted for those models rather than passed
  blindly.
* Provider SDKs are imported inside each branch. Importing this module no
  longer pulls three vendor SDKs into memory to build one client, and a missing
  optional dependency surfaces as an error about the provider you chose.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from core.config import Provider, Settings, get_settings
from core.exceptions import UnknownProviderError
from core.logging_config import get_logger

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.runnables import Runnable

logger = get_logger(__name__)

#: Model families that reject `temperature` / `top_p` / `top_k` with a 400.
#: Matched as prefixes against the configured model id.
NO_SAMPLING_PARAMS: tuple[str, ...] = (
    "claude-opus-5",
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-mythos-5",
    "gpt-5",
)


def supports_sampling_params(model: str) -> bool:
    """Whether `model` accepts `temperature`.

    Prefix matching is deliberate: it covers dated snapshots and `-fast`
    variants of the same family without needing an entry for each.
    """
    return not model.startswith(NO_SAMPLING_PARAMS)


def resolve_provider(provider: Provider | str | None) -> Provider:
    """Coerce a provider name to the enum, raising on anything unsupported."""
    if provider is None:
        return get_settings().llm_provider
    if isinstance(provider, Provider):
        return provider
    try:
        return Provider(str(provider).strip().lower())
    except ValueError as error:
        supported = ", ".join(p.value for p in Provider)
        raise UnknownProviderError(
            f"Unknown LLM provider '{provider}'. Supported providers: {supported}."
        ) from error


def build_chat_model(
    provider: Provider | str | None = None,
    *,
    settings: Settings | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> BaseChatModel:
    """Return a configured chat model for `provider`.

    Raises `MissingAPIKeyError` when the provider has no key, and
    `UnknownProviderError` when the name is not one we support. Both are
    `ConfigurationError`s, so a caller can distinguish "you have not finished
    setting this up" from "the model call failed".
    """
    settings = settings or get_settings()
    chosen = resolve_provider(provider if provider is not None else settings.llm_provider)

    model = model or settings.model_for(chosen)
    max_tokens = max_tokens if max_tokens is not None else settings.llm_max_tokens
    api_key = settings.api_key_for(chosen)  # raises MissingAPIKeyError

    sampling: dict[str, Any] = {}
    requested_temperature = (
        temperature if temperature is not None else settings.llm_temperature
    )
    if supports_sampling_params(model):
        sampling["temperature"] = requested_temperature
    elif temperature is not None:
        logger.info(
            "Ignoring temperature=%s: %s does not accept sampling parameters.",
            temperature,
            model,
        )

    common: dict[str, Any] = {
        "api_key": api_key,
        "timeout": settings.llm_timeout_seconds,
        "max_retries": settings.llm_max_retries,
        **sampling,
    }

    logger.info("Initialising %s chat model %s", chosen.value, model)

    if chosen is Provider.ANTHROPIC:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, max_tokens=max_tokens, **common)

    if chosen is Provider.OPENAI:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, max_tokens=max_tokens, **common)

    if chosen is Provider.GEMINI:
        from langchain_google_genai import ChatGoogleGenerativeAI

        # Gemini spells the output cap differently from the other two.
        return ChatGoogleGenerativeAI(
            model=model, max_output_tokens=max_tokens, **common
        )

    raise UnknownProviderError(f"No chat model wired up for provider '{chosen}'.")


def structured(
    chat_model: BaseChatModel,
    schema: type,
    *,
    include_raw: bool = True,
) -> Runnable:
    """Bind `schema` to `chat_model` so it returns a validated object.

    `include_raw=True` by default: the caller gets `{"raw", "parsed",
    "parsing_error"}` instead of an exception, which means a malformed response
    can be logged as itself rather than as a traceback with no payload.

    OpenAI and Gemini both expose a `method` argument, and OpenAI now defaults
    to strict `json_schema`. Strict mode rejects the numeric and length
    constraints `MeetingBrief` uses (`min_length`, `gt`, `le`), so both are
    pinned to tool calling. Anthropic has no `method` argument and uses tool
    calling already.
    """
    kwargs: dict[str, Any] = {"include_raw": include_raw}
    if "method" in inspect.signature(chat_model.with_structured_output).parameters:
        kwargs["method"] = "function_calling"
    return chat_model.with_structured_output(schema, **kwargs)


def describe(chat_model: BaseChatModel) -> str:
    """Best-effort model id, for logging and for the `briefs.model` column."""
    for attribute in ("model", "model_name"):
        value = getattr(chat_model, attribute, None)
        if isinstance(value, str) and value:
            return value
    return type(chat_model).__name__


def get_llm_provider(provider_name: str | None = None) -> BaseChatModel:
    """Backwards-compatible alias for `build_chat_model`.

    `agents/copilot_orchestrator.py` and `app.py` call this name. It goes away
    with them in Chunk 6.
    """
    return build_chat_model(provider_name)
