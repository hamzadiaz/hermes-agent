"""Tests for pure helper functions in hermes_cli/status.py.

Covers:
- redact_key(): API key redaction for display
- _format_iso_timestamp(): ISO string → local timezone formatted string
- _configured_model_label(): extract model label from config dict
"""

import pytest

from hermes_cli.status import (
    redact_key,
    _format_iso_timestamp,
    _configured_model_label,
)


# ── redact_key ────────────────────────────────────────────────────────────────

class TestRedactKey:
    def test_none_returns_not_set(self):
        assert redact_key(None) == "(not set)"

    def test_empty_returns_not_set(self):
        assert redact_key("") == "(not set)"

    def test_short_key_returns_stars(self):
        assert redact_key("short") == "***"

    def test_exactly_12_chars_shows_first_last_four(self):
        key = "sk-ant-api03"  # 12 chars
        result = redact_key(key)
        assert result.startswith("sk-a")
        assert result.endswith("pi03")
        assert "..." in result

    def test_long_key_shows_first_and_last_four(self):
        key = "sk-ant-api03-abcdefghijklmnop"
        result = redact_key(key)
        assert result.startswith("sk-a")
        assert result.endswith("mnop")
        assert "..." in result

    def test_11_chars_returns_stars(self):
        """11 chars < 12 → returns '***'."""
        assert redact_key("a" * 11) == "***"


# ── _format_iso_timestamp ─────────────────────────────────────────────────────

class TestFormatIsoTimestamp:
    def test_none_returns_unknown(self):
        assert _format_iso_timestamp(None) == "(unknown)"

    def test_empty_returns_unknown(self):
        assert _format_iso_timestamp("") == "(unknown)"

    def test_whitespace_only_returns_unknown(self):
        assert _format_iso_timestamp("   ") == "(unknown)"

    def test_non_string_returns_unknown(self):
        assert _format_iso_timestamp(123) == "(unknown)"

    def test_z_suffix_parsed(self):
        result = _format_iso_timestamp("2024-01-15T10:30:00Z")
        assert "2024" in result

    def test_offset_parsed(self):
        result = _format_iso_timestamp("2024-01-15T10:30:00+00:00")
        assert "2024" in result

    def test_invalid_format_returns_original(self):
        assert _format_iso_timestamp("not-a-date") == "not-a-date"

    def test_valid_date_returns_formatted_string(self):
        result = _format_iso_timestamp("2024-06-01T12:00:00Z")
        assert "2024" in result
        assert ":" in result


# ── _configured_model_label ───────────────────────────────────────────────────

class TestConfiguredModelLabel:
    def test_dict_model_with_default_key(self):
        config = {"model": {"default": "gpt-5"}}
        assert _configured_model_label(config) == "gpt-5"

    def test_dict_model_with_name_key(self):
        config = {"model": {"name": "claude-opus"}}
        assert _configured_model_label(config) == "claude-opus"

    def test_dict_model_default_preferred_over_name(self):
        config = {"model": {"default": "gpt-5", "name": "other"}}
        assert _configured_model_label(config) == "gpt-5"

    def test_string_model(self):
        config = {"model": "claude-opus"}
        assert _configured_model_label(config) == "claude-opus"

    def test_string_model_stripped(self):
        config = {"model": "  gpt-5  "}
        assert _configured_model_label(config) == "gpt-5"

    def test_no_model_returns_not_set(self):
        config = {}
        assert _configured_model_label(config) == "(not set)"

    def test_none_model_returns_not_set(self):
        config = {"model": None}
        assert _configured_model_label(config) == "(not set)"

    def test_empty_dict_model_returns_not_set(self):
        config = {"model": {}}
        assert _configured_model_label(config) == "(not set)"

    def test_whitespace_only_string_returns_not_set(self):
        config = {"model": "   "}
        assert _configured_model_label(config) == "(not set)"
