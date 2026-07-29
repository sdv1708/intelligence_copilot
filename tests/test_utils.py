"""Tests for shared helpers."""

from __future__ import annotations

import re

from core.utils import generate_id, utc_now_iso


class TestGenerateId:
    def test_includes_the_prefix(self) -> None:
        assert generate_id("meeting").startswith("meeting_")

    def test_omits_the_separator_when_no_prefix_given(self) -> None:
        assert not generate_id().startswith("_")

    def test_ids_are_unique(self) -> None:
        ids = {generate_id("chunk") for _ in range(500)}

        assert len(ids) == 500

    def test_shape_is_prefix_timestamp_random(self) -> None:
        assert re.fullmatch(r"brief_\d{14}_[0-9a-f]{8}", generate_id("brief"))

    def test_ids_sort_chronologically(self) -> None:
        """Brief history ordering depends on this."""
        earlier = generate_id("brief")
        later = generate_id("brief")

        assert earlier[:20] <= later[:20]


class TestUtcNowIso:
    def test_is_timezone_aware(self) -> None:
        """Naive timestamps compare incorrectly across a DST boundary."""
        stamp = utc_now_iso()

        assert stamp.endswith("+00:00")

    def test_is_parseable(self) -> None:
        from datetime import datetime

        assert datetime.fromisoformat(utc_now_iso()).tzinfo is not None
