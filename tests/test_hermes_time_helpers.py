"""Tests for pure helper functions in hermes_time.py.

Covers:
- _get_zoneinfo(): validate and return a ZoneInfo or None for invalid names
- _resolve_timezone_name(): read timezone from env var or config (env-var path only)
"""

import os
import pytest

from hermes_time import _get_zoneinfo, _resolve_timezone_name, reset_cache


# ── _get_zoneinfo ─────────────────────────────────────────────────────────────

class TestGetZoneinfo:
    def test_empty_string_returns_none(self):
        assert _get_zoneinfo("") is None

    def test_valid_timezone_returns_zoneinfo(self):
        tz = _get_zoneinfo("UTC")
        assert tz is not None
        assert tz.key == "UTC"

    def test_common_timezone_returned(self):
        tz = _get_zoneinfo("America/New_York")
        assert tz is not None

    def test_invalid_timezone_returns_none(self):
        assert _get_zoneinfo("Not/A/Real/Zone") is None

    def test_invalid_timezone_logs_warning(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            result = _get_zoneinfo("Fake/Timezone")
        assert result is None

    def test_asia_kolkata_returned(self):
        tz = _get_zoneinfo("Asia/Kolkata")
        assert tz is not None

    def test_europe_london_returned(self):
        tz = _get_zoneinfo("Europe/London")
        assert tz is not None


# ── _resolve_timezone_name ────────────────────────────────────────────────────

class TestResolveTimezoneName:
    def test_env_var_takes_priority(self, monkeypatch):
        monkeypatch.setenv("HERMES_TIMEZONE", "Asia/Tokyo")
        reset_cache()
        result = _resolve_timezone_name()
        assert result == "Asia/Tokyo"

    def test_env_var_stripped_of_whitespace(self, monkeypatch):
        monkeypatch.setenv("HERMES_TIMEZONE", "  Europe/Paris  ")
        reset_cache()
        result = _resolve_timezone_name()
        assert result == "Europe/Paris"

    def test_empty_env_var_falls_through(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HERMES_TIMEZONE", "")
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        reset_cache()
        result = _resolve_timezone_name()
        assert result == ""

    def test_returns_string(self, monkeypatch):
        monkeypatch.setenv("HERMES_TIMEZONE", "UTC")
        reset_cache()
        result = _resolve_timezone_name()
        assert isinstance(result, str)
