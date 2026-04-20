"""Tests for pure functions in hermes_constants.py.

Covers:
- display_hermes_home(): user-friendly ~/... display string
- parse_reasoning_effort(): parse effort level string to config dict
- get_optional_skills_dir(): resolve optional skills dir with env override
"""

import pytest
from pathlib import Path

from hermes_constants import (
    display_hermes_home,
    parse_reasoning_effort,
    get_optional_skills_dir,
    VALID_REASONING_EFFORTS,
)


# ── display_hermes_home ───────────────────────────────────────────────────────

class TestDisplayHermesHome:
    def test_default_path_uses_tilde(self, monkeypatch, tmp_path):
        # Simulate ~/.hermes under a tmp home
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        hermes = fake_home / ".hermes"
        monkeypatch.setenv("HERMES_HOME", str(hermes))
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
        from hermes_constants import get_hermes_home
        result = display_hermes_home()
        assert result.startswith("~/")

    def test_returns_string(self):
        result = display_hermes_home()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_custom_path_outside_home_returned_absolute(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
        result = display_hermes_home()
        # If tmp_path is not under home, should return absolute path
        assert isinstance(result, str)


# ── parse_reasoning_effort ────────────────────────────────────────────────────

class TestParseReasoningEffort:
    def test_none_returns_none(self):
        assert parse_reasoning_effort("") is None

    def test_whitespace_only_returns_none(self):
        assert parse_reasoning_effort("   ") is None

    def test_none_disables_reasoning(self):
        result = parse_reasoning_effort("none")
        assert result == {"enabled": False}

    def test_high_returns_enabled_dict(self):
        result = parse_reasoning_effort("high")
        assert result == {"enabled": True, "effort": "high"}

    def test_all_valid_efforts_accepted(self):
        for effort in VALID_REASONING_EFFORTS:
            result = parse_reasoning_effort(effort)
            assert result is not None
            assert result["enabled"] is True
            assert result["effort"] == effort

    def test_xhigh_accepted(self):
        result = parse_reasoning_effort("xhigh")
        assert result == {"enabled": True, "effort": "xhigh"}

    def test_minimal_accepted(self):
        result = parse_reasoning_effort("minimal")
        assert result == {"enabled": True, "effort": "minimal"}

    def test_unknown_effort_returns_none(self):
        assert parse_reasoning_effort("ultra") is None

    def test_case_normalized_to_lower(self):
        result = parse_reasoning_effort("HIGH")
        assert result == {"enabled": True, "effort": "high"}

    def test_whitespace_stripped(self):
        result = parse_reasoning_effort("  medium  ")
        assert result == {"enabled": True, "effort": "medium"}

    def test_none_string_case_insensitive(self):
        result = parse_reasoning_effort("NONE")
        assert result == {"enabled": False}


# ── get_optional_skills_dir ───────────────────────────────────────────────────

class TestGetOptionalSkillsDir:
    def test_env_override_used(self, monkeypatch, tmp_path):
        skills_dir = tmp_path / "skills"
        monkeypatch.setenv("HERMES_OPTIONAL_SKILLS", str(skills_dir))
        result = get_optional_skills_dir()
        assert result == skills_dir

    def test_no_override_uses_default(self, monkeypatch, tmp_path):
        monkeypatch.delenv("HERMES_OPTIONAL_SKILLS", raising=False)
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        result = get_optional_skills_dir()
        assert result == tmp_path / "optional-skills"

    def test_custom_default_used_when_no_env(self, monkeypatch, tmp_path):
        monkeypatch.delenv("HERMES_OPTIONAL_SKILLS", raising=False)
        monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
        custom_default = tmp_path / "custom-skills"
        result = get_optional_skills_dir(default=custom_default)
        assert result == custom_default

    def test_env_override_takes_priority_over_default(self, monkeypatch, tmp_path):
        env_dir = tmp_path / "env-skills"
        default_dir = tmp_path / "default-skills"
        monkeypatch.setenv("HERMES_OPTIONAL_SKILLS", str(env_dir))
        result = get_optional_skills_dir(default=default_dir)
        assert result == env_dir

    def test_returns_path_object(self, monkeypatch, tmp_path):
        monkeypatch.delenv("HERMES_OPTIONAL_SKILLS", raising=False)
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        result = get_optional_skills_dir()
        assert isinstance(result, Path)
