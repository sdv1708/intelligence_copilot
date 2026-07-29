"""Test doubles that let the pipeline run without network or model downloads.

The embedder here is deliberately *lexical* rather than random: texts that share
words really do score higher against each other. That makes retrieval tests
assert on meaningful behaviour instead of just plumbing.
"""

from __future__ import annotations

import re
import zlib
from collections.abc import Sequence

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
    """

    def __init__(self, responses: Sequence[str]) -> None:
        self._responses = list(responses)
        self._index = 0
        self.invocations: list[list] = []

    def invoke(self, messages, **kwargs):
        from langchain_core.messages import AIMessage

        self.invocations.append(messages)
        if self._index >= len(self._responses):
            raise AssertionError(
                f"ScriptedChatModel exhausted: {len(self._responses)} responses "
                f"configured but invoked {self._index + 1} times."
            )
        response = self._responses[self._index]
        self._index += 1
        return AIMessage(content=response)

    @property
    def last_prompt_text(self) -> str:
        """Flattened text of the most recent invocation, for substring asserts."""
        if not self.invocations:
            raise AssertionError("ScriptedChatModel has not been invoked.")
        return "\n".join(str(message.content) for message in self.invocations[-1])
