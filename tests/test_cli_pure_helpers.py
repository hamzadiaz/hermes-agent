"""Tests for pure helper functions in cli.py.

Covers:
- _path_is_within_root(): path-containment check using relative_to
- _parse_skills_argument(): normalize CLI skills flag into deduped list
"""

import pytest
from pathlib import Path

from cli import _path_is_within_root, _parse_skills_argument


# ── _path_is_within_root ──────────────────────────────────────────────────────

class TestPathIsWithinRoot:
    def test_path_within_root_returns_true(self, tmp_path):
        inner = tmp_path / "sub" / "file.txt"
        assert _path_is_within_root(inner, tmp_path) is True

    def test_path_equal_to_root_returns_true(self, tmp_path):
        assert _path_is_within_root(tmp_path, tmp_path) is True

    def test_path_outside_root_returns_false(self, tmp_path):
        sibling = tmp_path.parent / "other"
        assert _path_is_within_root(sibling, tmp_path) is False

    def test_parent_of_root_returns_false(self, tmp_path):
        assert _path_is_within_root(tmp_path.parent, tmp_path) is False

    def test_deep_nesting_within_root(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "d.py"
        assert _path_is_within_root(deep, tmp_path) is True

    def test_absolute_path_outside(self):
        root = Path("/tmp/myroot")
        outside = Path("/etc/passwd")
        assert _path_is_within_root(outside, root) is False


# ── _parse_skills_argument ────────────────────────────────────────────────────

class TestParseSkillsArgument:
    def test_none_returns_empty(self):
        assert _parse_skills_argument(None) == []

    def test_empty_string_returns_empty(self):
        assert _parse_skills_argument("") == []

    def test_empty_list_returns_empty(self):
        assert _parse_skills_argument([]) == []

    def test_single_string_skill(self):
        assert _parse_skills_argument("elves") == ["elves"]

    def test_comma_separated_string_split(self):
        result = _parse_skills_argument("elves,commit,review")
        assert result == ["elves", "commit", "review"]

    def test_comma_separated_with_spaces_stripped(self):
        result = _parse_skills_argument("elves, commit , review")
        assert result == ["elves", "commit", "review"]

    def test_list_of_skills_returned(self):
        result = _parse_skills_argument(["elves", "commit"])
        assert result == ["elves", "commit"]

    def test_tuple_of_skills_returned(self):
        result = _parse_skills_argument(("elves", "commit"))
        assert result == ["elves", "commit"]

    def test_duplicates_deduplicated(self):
        result = _parse_skills_argument("elves,elves,commit")
        assert result == ["elves", "commit"]

    def test_list_with_duplicates_deduplicated(self):
        result = _parse_skills_argument(["elves", "elves", "commit"])
        assert result == ["elves", "commit"]

    def test_order_preserved(self):
        result = _parse_skills_argument("commit,elves,review")
        assert result == ["commit", "elves", "review"]

    def test_none_items_in_list_skipped(self):
        result = _parse_skills_argument(["elves", None, "commit"])
        assert result == ["elves", "commit"]

    def test_empty_parts_from_comma_skipped(self):
        result = _parse_skills_argument("elves,,commit")
        assert result == ["elves", "commit"]

    def test_whitespace_only_parts_skipped(self):
        result = _parse_skills_argument("elves, , commit")
        assert result == ["elves", "commit"]
