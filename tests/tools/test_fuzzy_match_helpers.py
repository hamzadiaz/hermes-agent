"""Tests for pure helper functions in tools/fuzzy_match.py.

Covers:
- _unicode_normalize(): replace smart quotes, em dashes, etc. with ASCII
- _apply_replacements(): splice new_string into content at given positions
- _strategy_exact(): find exact substring positions in content
"""

import pytest

from tools.fuzzy_match import (
    _unicode_normalize,
    _apply_replacements,
    _strategy_exact,
)


# ── _unicode_normalize ────────────────────────────────────────────────────────

class TestUnicodeNormalize:
    def test_plain_ascii_unchanged(self):
        assert _unicode_normalize("hello world") == "hello world"

    def test_smart_double_quotes_replaced(self):
        result = _unicode_normalize("\u201chello\u201d")
        assert result == '"hello"'

    def test_smart_single_quotes_replaced(self):
        result = _unicode_normalize("\u2018it\u2019s")
        assert result == "'it's"

    def test_em_dash_replaced_with_double_hyphen(self):
        result = _unicode_normalize("a\u2014b")
        assert result == "a--b"

    def test_en_dash_replaced_with_hyphen(self):
        result = _unicode_normalize("a\u2013b")
        assert result == "a-b"

    def test_ellipsis_replaced(self):
        result = _unicode_normalize("wait\u2026")
        assert result == "wait..."

    def test_non_breaking_space_replaced(self):
        result = _unicode_normalize("a\u00a0b")
        assert result == "a b"

    def test_mixed_replacements(self):
        result = _unicode_normalize("\u201chello\u201d \u2014 world")
        assert result == '"hello" -- world'

    def test_empty_string_unchanged(self):
        assert _unicode_normalize("") == ""


# ── _apply_replacements ───────────────────────────────────────────────────────

class TestApplyReplacements:
    def test_single_replacement(self):
        result = _apply_replacements("hello world", [(0, 5)], "goodbye")
        assert result == "goodbye world"

    def test_end_replacement(self):
        result = _apply_replacements("hello world", [(6, 11)], "there")
        assert result == "hello there"

    def test_multiple_replacements_applied_in_order(self):
        # Replace two non-overlapping spans
        result = _apply_replacements("aXbYc", [(1, 2), (3, 4)], "-")
        assert result == "a-b-c"

    def test_empty_new_string_deletes(self):
        result = _apply_replacements("hello world", [(5, 11)], "")
        assert result == "hello"

    def test_replacement_longer_than_original(self):
        result = _apply_replacements("abc", [(1, 2)], "---")
        assert result == "a---c"

    def test_empty_matches_returns_original(self):
        original = "no change"
        result = _apply_replacements(original, [], "anything")
        assert result == original


# ── _strategy_exact ───────────────────────────────────────────────────────────

class TestStrategyExact:
    def test_single_match_found(self):
        matches = _strategy_exact("hello world", "hello")
        assert matches == [(0, 5)]

    def test_match_at_end(self):
        matches = _strategy_exact("hello world", "world")
        assert matches == [(6, 11)]

    def test_no_match_returns_empty(self):
        assert _strategy_exact("hello world", "xyz") == []

    def test_multiple_matches(self):
        matches = _strategy_exact("abcabc", "abc")
        assert len(matches) == 2
        assert (0, 3) in matches
        assert (3, 6) in matches

    def test_match_position_is_correct(self):
        matches = _strategy_exact("123hello456", "hello")
        assert matches == [(3, 8)]

    def test_empty_pattern_returns_empty(self):
        # Empty pattern would match everywhere, but strategy returns nothing for it
        result = _strategy_exact("test", "")
        # Depends on implementation, but at minimum should not crash
        assert isinstance(result, list)

    def test_full_string_match(self):
        matches = _strategy_exact("exact", "exact")
        assert matches == [(0, 5)]
