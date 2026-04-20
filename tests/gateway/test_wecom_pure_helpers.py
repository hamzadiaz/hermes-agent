"""Tests for pure helper functions in gateway/platforms/wecom.py.

Covers:
- _coerce_list(): coerce config values into a trimmed string list
- _normalize_entry(): normalize allowlist entries stripping platform/type prefixes
- _entry_matches(): case-insensitive allowlist match with wildcard support
"""

import pytest

from gateway.platforms.wecom import (
    _coerce_list,
    _entry_matches,
    _normalize_entry,
)


# ── _coerce_list ──────────────────────────────────────────────────────────────

class TestCoerceList:
    def test_none_returns_empty(self):
        assert _coerce_list(None) == []

    def test_comma_separated_string_split(self):
        assert _coerce_list("a, b, c") == ["a", "b", "c"]

    def test_single_string_returns_single_item_list(self):
        assert _coerce_list("alice") == ["alice"]

    def test_string_with_empty_parts_filtered(self):
        assert _coerce_list("a,,b, ,c") == ["a", "b", "c"]

    def test_list_input_trimmed(self):
        assert _coerce_list(["  a  ", "b", " c "]) == ["a", "b", "c"]

    def test_list_with_empty_strings_filtered(self):
        assert _coerce_list(["a", "", "  ", "b"]) == ["a", "b"]

    def test_tuple_input_handled(self):
        assert _coerce_list(("a", "b")) == ["a", "b"]

    def test_integer_wrapped_in_list(self):
        assert _coerce_list(42) == ["42"]

    def test_zero_returns_empty(self):
        # str(0) = "0" → non-empty → returns ["0"]
        assert _coerce_list(0) == ["0"]

    def test_empty_string_returns_empty(self):
        assert _coerce_list("") == []

    def test_whitespace_only_string_returns_empty(self):
        assert _coerce_list("   ") == []


# ── _normalize_entry ──────────────────────────────────────────────────────────

class TestNormalizeEntry:
    def test_plain_value_unchanged(self):
        assert _normalize_entry("alice") == "alice"

    def test_wecom_prefix_stripped(self):
        assert _normalize_entry("wecom:alice") == "alice"

    def test_wecom_case_insensitive(self):
        assert _normalize_entry("WECOM:alice") == "alice"

    def test_user_prefix_stripped(self):
        assert _normalize_entry("user:alice") == "alice"

    def test_group_prefix_stripped(self):
        assert _normalize_entry("group:devteam") == "devteam"

    def test_wecom_user_both_prefixes_stripped(self):
        assert _normalize_entry("wecom:user:alice") == "alice"

    def test_wecom_group_both_prefixes_stripped(self):
        assert _normalize_entry("wecom:group:devteam") == "devteam"

    def test_whitespace_stripped(self):
        assert _normalize_entry("  alice  ") == "alice"

    def test_wildcard_preserved(self):
        assert _normalize_entry("*") == "*"

    def test_wecom_wildcard(self):
        assert _normalize_entry("wecom:*") == "*"


# ── _entry_matches ────────────────────────────────────────────────────────────

class TestEntryMatches:
    def test_exact_match(self):
        assert _entry_matches(["alice", "bob"], "alice") is True

    def test_case_insensitive_match(self):
        assert _entry_matches(["ALICE"], "alice") is True

    def test_target_uppercase_matches_lower_entry(self):
        assert _entry_matches(["alice"], "ALICE") is True

    def test_wildcard_matches_anything(self):
        assert _entry_matches(["*"], "anyone") is True

    def test_wildcard_matches_empty_target(self):
        assert _entry_matches(["*"], "") is True

    def test_no_match_returns_false(self):
        assert _entry_matches(["alice", "bob"], "charlie") is False

    def test_empty_entries_returns_false(self):
        assert _entry_matches([], "alice") is False

    def test_wecom_prefixed_entry_matches_plain_target(self):
        # entries are normalized before comparison
        assert _entry_matches(["wecom:alice"], "alice") is True

    def test_user_prefixed_entry_matches_plain_target(self):
        assert _entry_matches(["user:alice"], "alice") is True

    def test_partial_match_is_not_a_match(self):
        assert _entry_matches(["alice"], "alice123") is False
