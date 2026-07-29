"""Test doubles that let the pipeline run without network or model downloads.

The embedder here is deliberately *lexical* rather than random: texts that share
words really do score higher against each other. That makes retrieval tests
assert on meaningful behaviour instead of just plumbing.
"""

from __future__ import annotations

import json
import re
import zlib
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]+")


def _bucket(token: str, dim: int) -> int:
    """Stable hash. `hash()` is salted per process, so it cannot be used here."""
    return zlib.crc32(token.encode("utf-8")) % dim


class HashingEmbedder:
    """Deterministic bag-of-words embedder with the same interface as the real one.

    Tokens are hashed into buckets and the resulting count vector is
    L2-normalised, so cosine similarity behaves like lexical overlap. No model
    weights, no GPU, no download -- and identical results on every machine.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim
        self.call_count = 0
        self.encoded_texts: list[str] = []

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        self.call_count += 1
        self.encoded_texts.extend(texts)

        if not texts:
            return np.zeros((0, self.dim), dtype="float32")

        vectors = np.zeros((len(texts), self.dim), dtype="float32")
        for row, text in enumerate(texts):
            for token in _TOKEN.findall(text.lower()):
                vectors[row, _bucket(token, self.dim)] += 1.0

        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0  # leave all-zero rows as zeros
        return (vectors / norms).astype("float32")


class ScriptedChatModel:
    """Returns canned responses in order, recording what it was asked.

    Use when a test needs to assert on the prompt that was built, or to force a
    specific malformed response through the error path.

    A scripted response is either:

    * a **string** — the model replied with text. `with_structured_output` will
      try to parse it as JSON, which is how a malformed-response test is
      written.
    * a **mapping** — the model called the bound tool with these arguments,
      which is the shape `with_structured_output` actually produces. The raw
      message carries them in `tool_calls`, so the recovery path in
      `core.synthesis` can be exercised with arguments that fail validation.
    """

    #: `core.llm_providers.describe` reads this; keeps the model id in results.
    model = "scripted-test-model"

    def __init__(self, responses: Sequence[str | Mapping[str, Any]]) -> None:
        self._responses = list(responses)
        self._index = 0
        self.invocations: list[list] = []
        self.structured_schemas: list[Any] = []
        self.structured_kwargs: list[dict[str, Any]] = []

    def _next(self) -> str | Mapping[str, Any]:
        if self._index >= len(self._responses):
            raise AssertionError(
                f"ScriptedChatModel exhausted: {len(self._responses)} responses "
                f"configured but invoked {self._index + 1} times."
            )
        response = self._responses[self._index]
        self._index += 1
        return response

    def invoke(self, messages, **kwargs):
        from langchain_core.messages import AIMessage

        self.invocations.append(messages)
        return _as_message(self._next(), AIMessage)

    def with_structured_output(
        self, schema, *, include_raw: bool = False, method: str | None = None, **kwargs
    ):
        """Mimic LangChain's contract closely enough to test against."""
        self.structured_schemas.append(schema)
        self.structured_kwargs.append({"include_raw": include_raw, "method": method})
        return _StructuredScript(self, schema, include_raw=include_raw)

    @property
    def last_prompt_text(self) -> str:
        """Flattened text of the most recent invocation, for substring asserts."""
        if not self.invocations:
            raise AssertionError("ScriptedChatModel has not been invoked.")
        return "\n".join(str(message.content) for message in self.invocations[-1])


class _StructuredScript:
    """What `ScriptedChatModel.with_structured_output` returns."""

    def __init__(self, parent: ScriptedChatModel, schema, *, include_raw: bool) -> None:
        self._parent = parent
        self._schema = schema
        self._include_raw = include_raw

    def invoke(self, messages, **kwargs):
        from langchain_core.messages import AIMessage

        self._parent.invocations.append(messages)
        response = self._parent._next()
        raw = _as_message(response, AIMessage)

        payload: Any = response
        error: Exception | None = None
        parsed = None

        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as decode_error:
                payload, error = None, decode_error

        if error is None:
            try:
                parsed = self._schema.model_validate(payload)
            except Exception as validation_error:  # mirrors LangChain's own catch
                error = validation_error

        if not self._include_raw:
            if error is not None:
                raise error
            return parsed
        return {"raw": raw, "parsed": parsed, "parsing_error": error}


def _as_message(response: str | Mapping[str, Any], message_cls):
    """Wrap a scripted response the way a provider would return it."""
    if isinstance(response, Mapping):
        return message_cls(
            content="",
            tool_calls=[
                {"name": "MeetingBrief", "args": dict(response), "id": "call_scripted"}
            ],
        )
    return message_cls(content=response)
