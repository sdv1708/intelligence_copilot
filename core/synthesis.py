"""The synthesis step: retrieved chunks in, a validated brief or answer out.

This module replaces roughly 150 lines of defensive string handling in
`agents/copilot_orchestrator.py` — markdown fence stripping, regex removal of
trailing commas and comments, brace counting to close truncated objects, and a
`json.loads` wrapped in a debug-file dump. All of that existed because nothing
ever *asked* the model for structured output; it asked for prose and hoped.

`BaseChatModel.with_structured_output` binds `MeetingBrief` to the model as a
tool schema, so the provider constrains the generation. There is no fence to
strip, and a response that still fails validation is a real failure worth
raising rather than repairing by counting braces.

The second thing this module owns is **citation integrity**. Retrieval now
returns chunk row ids, so a `Source: mat_x#c7` the model quotes back can be
looked up rather than trusted. Evidence that resolves gets `chunk_id` set;
evidence that resolves to nothing is dropped, because a citation pointing at
text that was never retrieved is worse than no citation at all.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from core.config import Provider, Settings, get_settings
from core.exceptions import InvalidBriefError, SynthesisError
from core.llm_providers import build_chat_model, describe, structured
from core.logging_config import get_logger
from core.prompts import BRIEF_SYSTEM, BRIEF_USER, QA_SYSTEM, QA_USER, render_prompt
from core.recall import format_context_blocks
from core.schema import Evidence, MeetingBrief, ScoredChunk

logger = get_logger(__name__)

# `material_id#c12`, however the model chose to wrap it.
_SOURCE_REF = re.compile(r"([A-Za-z0-9][A-Za-z0-9_\-]*)#c(\d+)")

_NO_PREVIOUS_MEETING = "(No previous meeting on record for this title.)"


@dataclass(frozen=True)
class BriefSynthesis:
    """A generated brief, plus what happened to its citations."""

    brief: MeetingBrief
    model: str
    provider: str
    cited_chunk_ids: tuple[int, ...] = ()
    dropped_sources: tuple[str, ...] = ()

    @property
    def citation_count(self) -> int:
        return len(self.brief.evidence)


@dataclass(frozen=True)
class QaAnswer:
    """An answer to one question, with the sources it was grounded in."""

    text: str
    model: str
    provider: str
    sources: tuple[str, ...] = ()
    chunk_ids: tuple[int, ...] = ()


class Synthesizer:
    """Turns retrieved context into a brief or an answer.

    Takes a chat model rather than building one when given, so tests can drive
    it with `tests.fakes.ScriptedChatModel` and Chunk 5's agent nodes can share
    a single client across a graph run.
    """

    def __init__(
        self,
        chat_model: Any | None = None,
        *,
        provider: Provider | str | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = str(provider or self.settings.llm_provider)
        self.chat_model = (
            chat_model
            if chat_model is not None
            else build_chat_model(provider, settings=self.settings)
        )
        self.model_name = describe(self.chat_model)

    # --- Brief generation ---------------------------------------------------

    def brief(
        self,
        *,
        title: str,
        date: str | None,
        results: Sequence[ScoredChunk],
        context: str | None = None,
        previous_brief: MeetingBrief | Mapping[str, Any] | None = None,
    ) -> BriefSynthesis:
        """Generate one executive brief.

        `results` is what retrieval returned; `context` is its rendered form,
        which the caller may supply pre-formatted (the `Retriever` labels
        materials by filename, which needs database access this module does not
        want). Both are needed: the text goes to the model, the objects resolve
        the citations that come back.
        """
        if not results:
            raise SynthesisError(
                f"No context retrieved for '{title}'; refusing to generate a "
                f"brief with nothing to ground it in."
            )

        system_prompt = render_prompt(BRIEF_SYSTEM)
        user_prompt = render_prompt(
            BRIEF_USER,
            title=title,
            date=date or "Not specified",
            context_blocks=context if context is not None else format_context_blocks(results),
            previous_meeting=format_previous_brief(previous_brief),
        )

        payload = self._invoke_structured(system_prompt, user_prompt)
        brief = _validate_brief(payload, title=title)

        evidence, dropped = resolve_evidence(brief.evidence, results)
        brief = brief.model_copy(update={"evidence": evidence})

        if dropped:
            logger.warning(
                "Dropped %d evidence item(s) citing sources that were never "
                "retrieved: %s",
                len(dropped),
                ", ".join(dropped[:5]),
            )
        logger.info(
            "Synthesised brief for '%s': %d action items, %d topics, %d citations",
            title,
            len(brief.open_action_items),
            len(brief.key_topics_today),
            len(brief.evidence),
        )

        return BriefSynthesis(
            brief=brief,
            model=self.model_name,
            provider=self.provider,
            cited_chunk_ids=tuple(
                item.chunk_id for item in brief.evidence if item.chunk_id is not None
            ),
            dropped_sources=tuple(dropped),
        )

    # --- Question answering -------------------------------------------------

    def answer(
        self,
        *,
        question: str,
        results: Sequence[ScoredChunk],
        context: str | None = None,
    ) -> QaAnswer:
        """Answer one question against the retrieved context."""
        if not question.strip():
            raise SynthesisError("Cannot answer an empty question.")

        system_prompt = render_prompt(QA_SYSTEM)
        user_prompt = render_prompt(
            QA_USER,
            question=question.strip(),
            context_blocks=context if context is not None else format_context_blocks(results),
        )

        response = self.chat_model.invoke(
            _messages(system_prompt, user_prompt)
        )
        text = _text_of(response)
        if not text.strip():
            raise SynthesisError("The model returned an empty answer.")

        hits = [scored for scored in results if not scored.is_neighbour]
        return QaAnswer(
            text=text.strip(),
            model=self.model_name,
            provider=self.provider,
            sources=tuple(dict.fromkeys(scored.source_ref for scored in hits)),
            chunk_ids=tuple(scored.chunk.id for scored in hits),
        )

    # --- Internals ----------------------------------------------------------

    def _invoke_structured(self, system_prompt: str, user_prompt: str) -> Any:
        """Ask for a `MeetingBrief` and return whatever came back to validate."""
        runnable = structured(self.chat_model, MeetingBrief)
        try:
            result = runnable.invoke(_messages(system_prompt, user_prompt))
        except Exception as error:  # provider errors, timeouts, rate limits
            raise SynthesisError(f"Brief generation failed: {error}") from error

        # `include_raw=True` yields {"raw", "parsed", "parsing_error"}; a model
        # bound without it returns the parsed object directly.
        if not isinstance(result, Mapping):
            return result

        parsed = result.get("parsed")
        if parsed is not None:
            return parsed

        raw = result.get("raw")
        recovered = _payload_from_raw(raw)
        if recovered is None:
            raise InvalidBriefError(
                f"The model did not return a usable brief "
                f"({result.get('parsing_error')}). Response began: "
                f"{_text_of(raw)[:200]!r}"
            )
        logger.warning(
            "Structured parse failed (%s); recovered the raw tool arguments.",
            result.get("parsing_error"),
        )
        return recovered


# --- Validation and repair --------------------------------------------------


def _validate_brief(payload: Any, *, title: str) -> MeetingBrief:
    """Coerce whatever the model produced into a `MeetingBrief`.

    The one repair applied is supplying `meeting_title` from the caller when the
    model omitted it — a required field we already know the answer to. Anything
    else that fails validation is raised, because inventing content to satisfy a
    schema is how a brief ends up looking complete while being wrong.
    """
    if isinstance(payload, MeetingBrief):
        return payload

    if not isinstance(payload, Mapping):
        raise InvalidBriefError(
            f"Expected a brief object, got {type(payload).__name__}."
        )

    data = dict(payload)
    if not str(data.get("meeting_title") or "").strip():
        data["meeting_title"] = title

    try:
        return MeetingBrief.model_validate(data)
    except Exception as error:
        raise InvalidBriefError(
            f"The model's brief did not satisfy the schema: {error}"
        ) from error


def _payload_from_raw(raw: Any) -> Mapping[str, Any] | None:
    """Pull the brief payload out of a response the parser rejected.

    Tool-call arguments first, since that is the shape structured output uses;
    then a bare JSON body, for a provider that answered in JSON mode. No fence
    stripping and no brace balancing — if the response is not one of those two
    shapes, it is a failure to report, not a string to repair.
    """
    if raw is None:
        return None

    tool_calls = getattr(raw, "tool_calls", None) or []
    for call in tool_calls:
        args = call.get("args") if isinstance(call, Mapping) else None
        if isinstance(args, Mapping) and args:
            return args

    text = _text_of(raw).strip()
    if text.startswith("{"):
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(loaded, Mapping):
            return loaded
    return None


# --- Citation integrity -----------------------------------------------------


def resolve_evidence(
    evidence: Sequence[Evidence],
    results: Sequence[ScoredChunk],
) -> tuple[list[Evidence], list[str]]:
    """Bind each citation to the chunk row it names.

    Returns the evidence that resolved (with `chunk_id` populated) and the raw
    `source` strings of the entries that did not. Retrieval hands back real row
    ids, so this is a lookup rather than an act of faith: a citation the model
    invented resolves to nothing and is reported.
    """
    by_ref = {scored.source_ref: scored.chunk.id for scored in results}

    resolved: list[Evidence] = []
    dropped: list[str] = []

    for item in evidence:
        source = item.source.strip()
        chunk_id = by_ref.get(source)

        if chunk_id is None:
            # Models decorate the identifier: "[3] mat_x#c7 (transcript)".
            match = _SOURCE_REF.search(source)
            if match:
                canonical = f"{match.group(1)}#c{match.group(2)}"
                chunk_id = by_ref.get(canonical)
                if chunk_id is not None:
                    source = canonical

        if chunk_id is None:
            dropped.append(item.source)
            continue

        resolved.append(item.model_copy(update={"source": source, "chunk_id": chunk_id}))

    return resolved, dropped


# --- Prompt fragments -------------------------------------------------------


def format_previous_brief(
    previous: MeetingBrief | Mapping[str, Any] | None,
    *,
    max_action_items: int = 5,
    max_topics: int = 3,
) -> str:
    """Render the prior meeting's brief as a prompt section.

    Accepts a `MeetingBrief` or the raw dict stored in `briefs.brief`, because
    history is persisted as a dict on purpose (see `BriefRecord`) and old rows
    need not satisfy today's schema to be useful context.
    """
    if previous is None:
        return _NO_PREVIOUS_MEETING

    data = (
        previous.model_dump() if isinstance(previous, MeetingBrief) else dict(previous)
    )

    lines = ["PREVIOUS MEETING ON THIS TITLE", "=" * 30]

    heading = str(data.get("meeting_title") or "").strip()
    if heading:
        lines.append(f"Title: {heading}")
    window = str(data.get("time_window") or "").strip()
    if window:
        lines.append(f"Period: {window}")

    recap = str(data.get("last_meeting_recap") or "").strip()
    lines.append("")
    lines.append("Recap:")
    lines.append(recap or "(none recorded)")

    items = [i for i in (data.get("open_action_items") or []) if isinstance(i, Mapping)]
    if items:
        lines.append("")
        lines.append("Action items carried in:")
        for item in items[:max_action_items]:
            owner = str(item.get("owner") or "TBD").strip() or "TBD"
            status = str(item.get("status") or "open").strip() or "open"
            lines.append(f"- [{status}] {owner}: {item.get('item', '')}")

    topics = [str(t).strip() for t in (data.get("key_topics_today") or []) if str(t).strip()]
    if topics:
        lines.append("")
        lines.append("Topics discussed:")
        lines.extend(f"- {topic}" for topic in topics[:max_topics])

    lines.append("=" * 30)
    return "\n".join(lines)


# --- Message plumbing -------------------------------------------------------


def _messages(system_prompt: str, user_prompt: str) -> list[Any]:
    from langchain_core.messages import HumanMessage, SystemMessage

    return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]


def _text_of(message: Any) -> str:
    """Flatten a chat response to text.

    Reasoning models return `content` as a list of typed blocks rather than a
    string, so `response.content` is not reliably text any more. Thinking blocks
    are skipped: they are the model's scratch work, not its answer.
    """
    if message is None:
        return ""

    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, Mapping) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)
