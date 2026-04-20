"""Tests for pure environment helper functions in tools/web_tools.py.

Covers:
- _has_env(): detect non-empty environment variable values
"""

import pytest

from tools.web_tools import _has_env


# ── _has_env ──────────────────────────────────────────────────────────────────

class TestHasEnv:
    def test_set_nonempty_value_returns_true(self, monkeypatch):
        monkeypatch.setenv("TEST_WEB_KEY", "sk-abc123")
        assert _has_env("TEST_WEB_KEY") is True

    def test_unset_env_returns_false(self, monkeypatch):
        monkeypatch.delenv("TEST_WEB_KEY", raising=False)
        assert _has_env("TEST_WEB_KEY") is False

    def test_empty_string_returns_false(self, monkeypatch):
        monkeypatch.setenv("TEST_WEB_KEY", "")
        assert _has_env("TEST_WEB_KEY") is False

    def test_whitespace_only_returns_false(self, monkeypatch):
        monkeypatch.setenv("TEST_WEB_KEY", "   ")
        assert _has_env("TEST_WEB_KEY") is False

    def test_returns_bool(self, monkeypatch):
        monkeypatch.setenv("TEST_WEB_KEY", "value")
        result = _has_env("TEST_WEB_KEY")
        assert isinstance(result, bool)

    def test_value_with_leading_whitespace_returns_true(self, monkeypatch):
        # Non-empty even with spaces (only strips to check truthiness)
        monkeypatch.setenv("TEST_WEB_KEY", "  key  ")
        assert _has_env("TEST_WEB_KEY") is True
