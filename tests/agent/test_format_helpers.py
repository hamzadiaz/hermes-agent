"""Tests for formatting helper functions in agent/insights.py and agent/usage_pricing.py.

Covers:
- _bar_chart(): proportional bar scaling, empty list, all-zero values
- format_duration_compact(): seconds/minutes/hours/days formatting
- format_token_count_compact(): K/M/B suffixes, decimal trimming, negative values
"""

import pytest

from agent.insights import _bar_chart
from agent.usage_pricing import format_duration_compact, format_token_count_compact


# ── _bar_chart ────────────────────────────────────────────────────────────────

class TestBarChart:
    def test_empty_list_returns_empty_list(self):
        assert _bar_chart([]) == []

    def test_all_zeros_returns_all_empty_strings(self):
        result = _bar_chart([0, 0, 0])
        assert all(s == "" for s in result)

    def test_single_value_fills_max_width(self):
        result = _bar_chart([100], max_width=10)
        assert len(result) == 1
        assert len(result[0]) == 10

    def test_proportional_scaling(self):
        result = _bar_chart([10, 5, 0], max_width=10)
        # Peak (10) should have 10 bars; half (5) should have 5; zero should have ""
        assert len(result[0]) == 10
        assert len(result[1]) == 5
        assert result[2] == ""

    def test_non_zero_small_value_gets_at_least_one_bar(self):
        """Values > 0 should always produce at least 1 bar character."""
        result = _bar_chart([1000, 1], max_width=20)
        assert len(result[1]) >= 1

    def test_returns_one_entry_per_value(self):
        values = [5, 10, 0, 8, 3]
        assert len(_bar_chart(values)) == len(values)

    def test_default_max_width_20(self):
        result = _bar_chart([100])
        assert len(result[0]) == 20


# ── format_duration_compact ───────────────────────────────────────────────────

class TestFormatDurationCompact:
    def test_zero_seconds(self):
        assert format_duration_compact(0) == "0s"

    def test_45_seconds(self):
        assert format_duration_compact(45) == "45s"

    def test_59_seconds(self):
        assert format_duration_compact(59) == "59s"

    def test_60_seconds_is_one_minute(self):
        assert format_duration_compact(60) == "1m"

    def test_90_seconds_is_one_and_half_minutes(self):
        assert format_duration_compact(90) == "2m"

    def test_3600_seconds_is_one_hour(self):
        assert format_duration_compact(3600) == "1h"

    def test_3660_seconds_is_one_hour_one_minute(self):
        assert format_duration_compact(3660) == "1h 1m"

    def test_7200_seconds_is_two_hours(self):
        assert format_duration_compact(7200) == "2h"

    def test_86400_seconds_is_one_day(self):
        assert format_duration_compact(86400) == "1.0d"

    def test_172800_seconds_is_two_days(self):
        assert format_duration_compact(172800) == "2.0d"

    def test_exact_hour_no_minutes_shown(self):
        """Hours that are exact should not show '0m'."""
        result = format_duration_compact(2 * 3600)
        assert result == "2h"


# ── format_token_count_compact ────────────────────────────────────────────────

class TestFormatTokenCountCompact:
    def test_zero(self):
        assert format_token_count_compact(0) == "0"

    def test_small_number_unchanged(self):
        assert format_token_count_compact(500) == "500"

    def test_999_not_abbreviated(self):
        assert format_token_count_compact(999) == "999"

    def test_1000_becomes_1K(self):
        assert format_token_count_compact(1000) == "1K"

    def test_1500_becomes_1_5K(self):
        assert format_token_count_compact(1500) == "1.5K"

    def test_10000_becomes_10K(self):
        assert format_token_count_compact(10000) == "10K"

    def test_100000_becomes_100K(self):
        assert format_token_count_compact(100000) == "100K"

    def test_1_million_becomes_1M(self):
        assert format_token_count_compact(1_000_000) == "1M"

    def test_1_5_million(self):
        assert format_token_count_compact(1_500_000) == "1.5M"

    def test_1_billion(self):
        assert format_token_count_compact(1_000_000_000) == "1B"

    def test_negative_value(self):
        result = format_token_count_compact(-5000)
        assert result.startswith("-")
        assert "5K" in result

    def test_trailing_zeros_stripped(self):
        """1.00K should become 1K (no trailing zeros)."""
        result = format_token_count_compact(1000)
        assert result == "1K"
        assert ".00" not in result
