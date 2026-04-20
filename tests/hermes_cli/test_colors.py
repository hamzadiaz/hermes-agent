"""Tests for hermes_cli/colors.py.

Covers:
- should_use_color(): NO_COLOR env, TERM=dumb, non-TTY, and TTY path
- color(): no-op when color disabled, applies codes when enabled
"""

import pytest
from hermes_cli.colors import should_use_color, color, Colors


class TestShouldUseColor:
    def test_no_color_env_disables(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "")
        monkeypatch.delenv("TERM", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        assert should_use_color() is False

    def test_no_color_env_any_value_disables(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        assert should_use_color() is False

    def test_term_dumb_disables(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("TERM", "dumb")
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        assert should_use_color() is False

    def test_non_tty_disables(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        assert should_use_color() is False

    def test_tty_without_overrides_enables(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        assert should_use_color() is True

    def test_term_non_dumb_still_allows_color(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("TERM", "xterm-256color")
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        assert should_use_color() is True

    def test_no_color_wins_over_tty(self, monkeypatch):
        """NO_COLOR takes priority even if stdout is a TTY."""
        monkeypatch.setenv("NO_COLOR", "")
        monkeypatch.delenv("TERM", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        assert should_use_color() is False


class TestColorFunction:
    def test_returns_plain_text_when_no_color(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "")
        result = color("hello", Colors.RED)
        assert result == "hello"

    def test_applies_codes_and_reset_when_color_enabled(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        result = color("hello", Colors.GREEN)
        assert Colors.GREEN in result
        assert "hello" in result
        assert Colors.RESET in result

    def test_multiple_codes_applied(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        result = color("hi", Colors.BOLD, Colors.RED)
        assert Colors.BOLD in result
        assert Colors.RED in result
        assert "hi" in result

    def test_no_codes_still_returns_text(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        result = color("plain")
        assert "plain" in result

    def test_empty_string_passthrough_no_color(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "")
        assert color("") == ""
