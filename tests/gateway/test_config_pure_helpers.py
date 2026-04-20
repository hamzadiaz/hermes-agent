"""Tests for pure helper functions in gateway/config.py.

Covers:
- _coerce_bool(): coerce bool-ish config values including yes/no/on/off
- _normalize_unauthorized_dm_behavior(): normalize unauthorized DM behavior string
"""

import pytest

from gateway.config import _coerce_bool, _normalize_unauthorized_dm_behavior


# ── _coerce_bool ─────────────────────────────────────────────────────────────

class TestCoerceBool:
    def test_true_string_returns_true(self):
        assert _coerce_bool("true") is True

    def test_false_string_returns_false(self):
        assert _coerce_bool("false") is False

    def test_one_string_returns_true(self):
        assert _coerce_bool("1") is True

    def test_zero_string_returns_false(self):
        assert _coerce_bool("0") is False

    def test_yes_string_returns_true(self):
        assert _coerce_bool("yes") is True

    def test_no_string_returns_false(self):
        assert _coerce_bool("no") is False

    def test_on_string_returns_true(self):
        assert _coerce_bool("on") is True

    def test_off_string_returns_false(self):
        assert _coerce_bool("off") is False

    def test_none_returns_default_true(self):
        assert _coerce_bool(None, True) is True

    def test_none_returns_default_false(self):
        assert _coerce_bool(None, False) is False

    def test_unknown_string_returns_default(self):
        assert _coerce_bool("junk", False) is False

    def test_true_bool_returns_true(self):
        assert _coerce_bool(True) is True

    def test_false_bool_returns_false(self):
        assert _coerce_bool(False, True) is False

    def test_uppercase_true_normalized(self):
        assert _coerce_bool("TRUE") is True

    def test_uppercase_false_normalized(self):
        assert _coerce_bool("FALSE") is False

    def test_mixed_case_yes_normalized(self):
        assert _coerce_bool("YES") is True

    def test_whitespace_stripped(self):
        assert _coerce_bool("  true  ") is True


# ── _normalize_unauthorized_dm_behavior ──────────────────────────────────────

class TestNormalizeUnauthorizedDmBehavior:
    def test_pair_returned(self):
        assert _normalize_unauthorized_dm_behavior("pair") == "pair"

    def test_ignore_returned(self):
        assert _normalize_unauthorized_dm_behavior("ignore") == "ignore"

    def test_uppercase_normalized(self):
        assert _normalize_unauthorized_dm_behavior("PAIR") == "pair"

    def test_mixed_case_normalized(self):
        assert _normalize_unauthorized_dm_behavior("Ignore") == "ignore"

    def test_whitespace_stripped(self):
        assert _normalize_unauthorized_dm_behavior("  pair  ") == "pair"

    def test_unknown_string_returns_default(self):
        assert _normalize_unauthorized_dm_behavior("block", "pair") == "pair"

    def test_none_returns_default(self):
        assert _normalize_unauthorized_dm_behavior(None, "ignore") == "ignore"

    def test_empty_string_returns_default(self):
        assert _normalize_unauthorized_dm_behavior("", "pair") == "pair"

    def test_default_is_pair(self):
        assert _normalize_unauthorized_dm_behavior("unknown") == "pair"
