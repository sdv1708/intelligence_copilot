"""Tests for the test doubles themselves.

Later chunks assert retrieval quality through `HashingEmbedder`, so its
similarity behaviour needs to be trustworthy and stable.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from core.schema import MeetingBrief
from tests.fakes import HashingEmbedder, ScriptedChatModel


class TestHashingEmbedder:
    def test_output_shape_and_dtype(self, embedder: HashingEmbedder) -> None:
        vectors = embedder.encode(["hello world", "second text"])

        assert vectors.shape == (2, 384)
        assert vectors.dtype == np.float32

    def test_empty_input_returns_empty_matrix(self, embedder: HashingEmbedder) -> None:
        vectors = embedder.encode([])

        assert vectors.shape == (0, 384)

    def test_vectors_are_unit_length(self, embedder: HashingEmbedder) -> None:
        vectors = embedder.encode(["the quarterly revenue forecast"])

        assert np.isclose(np.linalg.norm(vectors[0]), 1.0)

    def test_is_deterministic_across_instances(self) -> None:
        """Must not depend on PYTHONHASHSEED, or tests flake between runs."""
        first = HashingEmbedder().encode(["budget approval pending"])
        second = HashingEmbedder().encode(["budget approval pending"])

        np.testing.assert_array_equal(first, second)

    def test_lexical_overlap_scores_higher_than_unrelated_text(
        self, embedder: HashingEmbedder
    ) -> None:
        vectors = embedder.encode(
            [
                "the hiring budget was approved by finance",
                "the hiring budget needs finance approval",
                "penguins migrate across antarctic ice",
            ]
        )
        related = float(vectors[0] @ vectors[1])
        unrelated = float(vectors[0] @ vectors[2])

        assert related > unrelated

    def test_records_what_it_encoded(self, embedder: HashingEmbedder) -> None:
        embedder.encode(["one"])
        embedder.encode(["two", "three"])

        assert embedder.call_count == 2
        assert embedder.encoded_texts == ["one", "two", "three"]

    def test_text_with_no_tokens_does_not_divide_by_zero(
        self, embedder: HashingEmbedder
    ) -> None:
        vectors = embedder.encode(["!!! ??? ..."])

        assert np.all(vectors[0] == 0.0)


class TestScriptedChatModel:
    def test_returns_responses_in_order(self) -> None:
        model = ScriptedChatModel(["first", "second"])

        assert model.invoke([]).content == "first"
        assert model.invoke([]).content == "second"

    def test_raises_a_clear_error_when_exhausted(self) -> None:
        model = ScriptedChatModel(["only one"])
        model.invoke([])

        with pytest.raises(AssertionError, match="exhausted"):
            model.invoke([])

    def test_captures_the_prompt_for_assertions(self) -> None:
        from langchain_core.messages import HumanMessage, SystemMessage

        model = ScriptedChatModel(["ok"])
        model.invoke([SystemMessage(content="you are a copilot"), HumanMessage(content="hi")])

        assert "you are a copilot" in model.last_prompt_text
        assert "hi" in model.last_prompt_text


class TestScriptedStructuredOutput:
    """The fake stands in for `with_structured_output`, so it has to match it."""

    def test_a_mapping_response_validates_into_the_schema(self) -> None:
        model = ScriptedChatModel([{"meeting_title": "Q3 Review"}])

        brief = model.with_structured_output(MeetingBrief).invoke([])

        assert isinstance(brief, MeetingBrief)
        assert brief.meeting_title == "Q3 Review"

    def test_a_json_string_response_validates_too(self) -> None:
        model = ScriptedChatModel(['{"meeting_title": "Q3 Review"}'])

        brief = model.with_structured_output(MeetingBrief).invoke([])

        assert brief.meeting_title == "Q3 Review"

    def test_include_raw_reports_the_failure_instead_of_raising(self) -> None:
        model = ScriptedChatModel(["not json at all"])

        result = model.with_structured_output(MeetingBrief, include_raw=True).invoke([])

        assert result["parsed"] is None
        assert result["parsing_error"] is not None
        assert result["raw"].content == "not json at all"

    def test_without_include_raw_the_failure_is_raised(self) -> None:
        model = ScriptedChatModel(["not json at all"])

        with pytest.raises(json.JSONDecodeError):
            model.with_structured_output(MeetingBrief).invoke([])

    def test_a_mapping_response_arrives_as_tool_call_arguments(self) -> None:
        """Which is the shape structured output actually produces."""
        model = ScriptedChatModel([{"meeting_title": ""}])

        result = model.with_structured_output(MeetingBrief, include_raw=True).invoke([])

        assert result["parsing_error"] is not None  # empty title fails min_length
        assert result["raw"].tool_calls[0]["args"] == {"meeting_title": ""}

    def test_structured_calls_draw_from_the_same_script(self) -> None:
        model = ScriptedChatModel([{"meeting_title": "First"}, "second"])
        structured = model.with_structured_output(MeetingBrief)

        assert structured.invoke([]).meeting_title == "First"
        assert model.invoke([]).content == "second"
