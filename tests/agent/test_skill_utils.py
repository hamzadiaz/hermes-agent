"""Tests for agent/skill_utils.py pure helper functions.

Covers:
- parse_frontmatter(): YAML parsing, no-frontmatter passthrough, malformed YAML fallback
- skill_matches_platform(): absent field, single platform, multi-platform, mapped names
- extract_skill_conditions(): all 4 condition keys, missing metadata, non-dict metadata
- extract_skill_description(): truncation at 60 chars, strip quotes, empty
- _normalize_string_set(): string, list, None, whitespace stripping, empty values
- iter_skill_index_files(): walks dirs, excludes .git/.github/.hub, sorted order
"""

import sys
from pathlib import Path

import pytest

from agent.skill_utils import (
    parse_frontmatter,
    skill_matches_platform,
    extract_skill_conditions,
    extract_skill_description,
    _normalize_string_set,
    iter_skill_index_files,
)


# ── parse_frontmatter ─────────────────────────────────────────────────────────

class TestParseFrontmatter:
    def test_no_frontmatter_returns_empty_dict_and_full_body(self):
        content = "Just plain markdown text."
        fm, body = parse_frontmatter(content)
        assert fm == {}
        assert body == content

    def test_valid_frontmatter_parsed(self):
        content = "---\nname: My Skill\ndescription: Does stuff\n---\nBody text"
        fm, body = parse_frontmatter(content)
        assert fm["name"] == "My Skill"
        assert fm["description"] == "Does stuff"
        assert "Body text" in body

    def test_body_is_content_after_closing_delimiter(self):
        content = "---\nname: test\n---\nThis is the body."
        _, body = parse_frontmatter(content)
        assert body.strip() == "This is the body."

    def test_list_value_in_frontmatter(self):
        content = "---\nplatforms:\n  - macos\n  - linux\n---\nbody"
        fm, _ = parse_frontmatter(content)
        assert fm["platforms"] == ["macos", "linux"]

    def test_nested_frontmatter(self):
        content = "---\nmetadata:\n  hermes:\n    requires_toolsets: [terminal]\n---\nbody"
        fm, _ = parse_frontmatter(content)
        assert fm["metadata"]["hermes"]["requires_toolsets"] == ["terminal"]

    def test_unclosed_frontmatter_returns_empty(self):
        """No closing --- → treat as no frontmatter."""
        content = "---\nname: test\nno closing delimiter"
        fm, body = parse_frontmatter(content)
        assert fm == {}
        assert body == content

    def test_empty_frontmatter_returns_empty_dict(self):
        content = "---\n---\nbody"
        fm, body = parse_frontmatter(content)
        assert fm == {}
        assert "body" in body

    def test_malformed_yaml_fallback_to_simple_parsing(self):
        """When YAML is malformed, fallback key:value parsing kicks in."""
        content = "---\nname: My Skill\nbad: yaml: here\n---\nbody"
        fm, _ = parse_frontmatter(content)
        # Simple parser should at minimum pick up the first clean key
        assert "name" in fm


# ── skill_matches_platform ────────────────────────────────────────────────────

class TestSkillMatchesPlatform:
    def test_no_platforms_field_matches_all(self):
        assert skill_matches_platform({}) is True

    def test_empty_platforms_list_matches_all(self):
        assert skill_matches_platform({"platforms": []}) is True

    def test_none_platforms_matches_all(self):
        assert skill_matches_platform({"platforms": None}) is True

    def test_current_platform_matches(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        assert skill_matches_platform({"platforms": ["macos"]}) is True

    def test_wrong_platform_no_match(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert skill_matches_platform({"platforms": ["macos"]}) is False

    def test_multi_platform_one_matches(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert skill_matches_platform({"platforms": ["macos", "linux"]}) is True

    def test_direct_platform_string(self, monkeypatch):
        """Non-list platforms field is coerced to list."""
        monkeypatch.setattr(sys, "platform", "darwin")
        assert skill_matches_platform({"platforms": "macos"}) is True

    def test_linux_mapped_correctly(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert skill_matches_platform({"platforms": ["linux"]}) is True

    def test_win32_mapped_correctly(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        assert skill_matches_platform({"platforms": ["windows"]}) is True

    def test_unmapped_platform_matched_directly(self, monkeypatch):
        """An unmapped platform string is compared to sys.platform directly."""
        monkeypatch.setattr(sys, "platform", "freebsd")
        assert skill_matches_platform({"platforms": ["freebsd"]}) is True


# ── extract_skill_conditions ──────────────────────────────────────────────────

class TestExtractSkillConditions:
    def test_empty_frontmatter_returns_empty_lists(self):
        result = extract_skill_conditions({})
        assert result == {
            "fallback_for_toolsets": [],
            "requires_toolsets": [],
            "fallback_for_tools": [],
            "requires_tools": [],
        }

    def test_all_condition_keys_extracted(self):
        fm = {
            "metadata": {
                "hermes": {
                    "fallback_for_toolsets": ["terminal"],
                    "requires_toolsets": ["web"],
                    "fallback_for_tools": ["bash"],
                    "requires_tools": ["python"],
                }
            }
        }
        result = extract_skill_conditions(fm)
        assert result["fallback_for_toolsets"] == ["terminal"]
        assert result["requires_toolsets"] == ["web"]
        assert result["fallback_for_tools"] == ["bash"]
        assert result["requires_tools"] == ["python"]

    def test_non_dict_metadata_treated_as_empty(self):
        fm = {"metadata": "not-a-dict"}
        result = extract_skill_conditions(fm)
        assert result["requires_toolsets"] == []

    def test_non_dict_hermes_treated_as_empty(self):
        fm = {"metadata": {"hermes": "not-a-dict"}}
        result = extract_skill_conditions(fm)
        assert result["requires_tools"] == []

    def test_partial_conditions_returned(self):
        fm = {"metadata": {"hermes": {"requires_tools": ["terminal"]}}}
        result = extract_skill_conditions(fm)
        assert result["requires_tools"] == ["terminal"]
        assert result["requires_toolsets"] == []


# ── extract_skill_description ─────────────────────────────────────────────────

class TestExtractSkillDescription:
    def test_empty_frontmatter_returns_empty_string(self):
        assert extract_skill_description({}) == ""

    def test_none_description_returns_empty(self):
        assert extract_skill_description({"description": None}) == ""

    def test_short_description_returned_as_is(self):
        assert extract_skill_description({"description": "Short desc"}) == "Short desc"

    def test_exactly_60_chars_not_truncated(self):
        desc = "a" * 60
        assert extract_skill_description({"description": desc}) == desc

    def test_61_chars_truncated_with_ellipsis(self):
        desc = "a" * 61
        result = extract_skill_description({"description": desc})
        assert result.endswith("...")
        assert len(result) == 60

    def test_quotes_stripped(self):
        result = extract_skill_description({"description": "'quoted desc'"})
        assert result == "quoted desc"

    def test_double_quotes_stripped(self):
        result = extract_skill_description({"description": '"quoted desc"'})
        assert result == "quoted desc"

    def test_whitespace_stripped(self):
        result = extract_skill_description({"description": "  trimmed  "})
        assert result == "trimmed"


# ── _normalize_string_set ─────────────────────────────────────────────────────

class TestNormalizeStringSet:
    def test_none_returns_empty_set(self):
        assert _normalize_string_set(None) == set()

    def test_string_wrapped_in_set(self):
        assert _normalize_string_set("one") == {"one"}

    def test_list_of_strings_returned_as_set(self):
        assert _normalize_string_set(["a", "b", "c"]) == {"a", "b", "c"}

    def test_whitespace_stripped(self):
        assert _normalize_string_set(["  foo  ", "bar"]) == {"foo", "bar"}

    def test_empty_strings_excluded(self):
        assert _normalize_string_set(["", "  ", "ok"]) == {"ok"}

    def test_non_string_items_coerced(self):
        assert _normalize_string_set([1, 2]) == {"1", "2"}


# ── iter_skill_index_files ────────────────────────────────────────────────────

class TestIterSkillIndexFiles:
    def test_finds_matching_files(self, tmp_path):
        skill_dir = tmp_path / "skills"
        (skill_dir / "skill_a").mkdir(parents=True)
        (skill_dir / "skill_a" / "skill.md").write_text("content")
        (skill_dir / "skill_b").mkdir()
        (skill_dir / "skill_b" / "skill.md").write_text("content")

        results = list(iter_skill_index_files(skill_dir, "skill.md"))
        names = [p.parent.name for p in results]
        assert "skill_a" in names
        assert "skill_b" in names

    def test_excludes_git_dir(self, tmp_path):
        skill_dir = tmp_path / "skills"
        (skill_dir / ".git" / "some_skill").mkdir(parents=True)
        (skill_dir / ".git" / "some_skill" / "skill.md").write_text("content")
        (skill_dir / "real_skill").mkdir()
        (skill_dir / "real_skill" / "skill.md").write_text("content")

        results = list(iter_skill_index_files(skill_dir, "skill.md"))
        parents = [p.parent.name for p in results]
        assert "some_skill" not in parents
        assert "real_skill" in parents

    def test_excludes_github_dir(self, tmp_path):
        skill_dir = tmp_path / "skills"
        (skill_dir / ".github" / "sub").mkdir(parents=True)
        (skill_dir / ".github" / "sub" / "skill.md").write_text("x")
        (skill_dir / "ok_skill").mkdir()
        (skill_dir / "ok_skill" / "skill.md").write_text("x")

        results = list(iter_skill_index_files(skill_dir, "skill.md"))
        parents = [p.parent.name for p in results]
        assert "sub" not in parents
        assert "ok_skill" in parents

    def test_results_sorted_alphabetically(self, tmp_path):
        skill_dir = tmp_path / "skills"
        for name in ["zzz", "aaa", "mmm"]:
            (skill_dir / name).mkdir(parents=True)
            (skill_dir / name / "skill.md").write_text("x")

        results = list(iter_skill_index_files(skill_dir, "skill.md"))
        names = [p.parent.name for p in results]
        assert names == sorted(names)

    def test_nonexistent_dir_yields_nothing(self, tmp_path):
        results = list(iter_skill_index_files(tmp_path / "nonexistent", "skill.md"))
        assert results == []

    def test_no_matching_files_yields_nothing(self, tmp_path):
        skill_dir = tmp_path / "skills"
        (skill_dir / "a_skill").mkdir(parents=True)
        (skill_dir / "a_skill" / "other.md").write_text("x")

        results = list(iter_skill_index_files(skill_dir, "skill.md"))
        assert results == []
