"""Tests for pure helper functions in hermes_cli/cron.py.

Covers:
- _normalize_skills(): dedup + strip skill names from various input forms
"""

import pytest

from hermes_cli.cron import _normalize_skills


class TestNormalizeSkills:
    def test_none_single_none_skills_returns_none(self):
        """Both args None → no skills specified at all."""
        assert _normalize_skills(None, None) is None

    def test_single_skill_returned_in_list(self):
        result = _normalize_skills(single_skill="elves")
        assert result == ["elves"]

    def test_skills_iterable_used_when_provided(self):
        result = _normalize_skills(skills=["elves", "commit"])
        assert result == ["elves", "commit"]

    def test_single_skill_ignored_when_skills_provided(self):
        """When skills= is set, single_skill= is ignored."""
        result = _normalize_skills(single_skill="ignored", skills=["elves"])
        assert result == ["elves"]

    def test_empty_skills_list_returns_empty_list(self):
        result = _normalize_skills(skills=[])
        assert result == []

    def test_whitespace_items_stripped(self):
        result = _normalize_skills(skills=["  elves  ", " commit "])
        assert result == ["elves", "commit"]

    def test_empty_strings_filtered_out(self):
        result = _normalize_skills(skills=["elves", "", "   "])
        assert result == ["elves"]

    def test_duplicates_removed(self):
        result = _normalize_skills(skills=["elves", "elves", "commit"])
        assert result == ["elves", "commit"]

    def test_order_preserved(self):
        result = _normalize_skills(skills=["commit", "elves", "review"])
        assert result == ["commit", "elves", "review"]

    def test_single_skill_stripped(self):
        result = _normalize_skills(single_skill="  elves  ")
        assert result == ["elves"]

    def test_none_single_skill_with_none_in_skills(self):
        """None items in skills list coerced to empty str and filtered."""
        result = _normalize_skills(skills=[None, "elves"])
        assert result == ["elves"]
