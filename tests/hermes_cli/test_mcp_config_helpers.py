"""Tests for pure helper functions in hermes_cli/mcp_config.py.

Covers:
- _unwrap_exception_group(): extract root-cause from BaseExceptionGroup wrappers
- _interpolate_value(): resolve ${ENV_VAR} placeholders in strings
"""

import pytest

from hermes_cli.mcp_config import _unwrap_exception_group, _interpolate_value


# ── _unwrap_exception_group ───────────────────────────────────────────────────

class TestUnwrapExceptionGroup:
    def test_plain_exception_returned_as_is(self):
        exc = ValueError("something broke")
        result = _unwrap_exception_group(exc)
        assert isinstance(result, ValueError)

    def test_single_wrapped_exception_unwrapped(self):
        inner = ConnectionError("401 Unauthorized")
        wrapped = BaseExceptionGroup("task group", [inner])
        result = _unwrap_exception_group(wrapped)
        assert isinstance(result, ConnectionError)
        assert "401" in str(result)

    def test_nested_exception_group_fully_unwrapped(self):
        inner = RuntimeError("root cause")
        mid = BaseExceptionGroup("mid", [inner])
        outer = BaseExceptionGroup("outer", [mid])
        result = _unwrap_exception_group(outer)
        assert isinstance(result, RuntimeError)
        assert "root cause" in str(result)

    def test_returns_exception_type(self):
        exc = TypeError("type error")
        result = _unwrap_exception_group(exc)
        assert isinstance(result, Exception)

    def test_base_exception_not_exception_wrapped_in_runtime_error(self):
        # SystemExit is a BaseException but not an Exception
        exc = SystemExit(1)
        result = _unwrap_exception_group(exc)
        assert isinstance(result, RuntimeError)


# ── _interpolate_value ────────────────────────────────────────────────────────

class TestInterpolateValue:
    def test_plain_string_unchanged(self):
        assert _interpolate_value("hello world") == "hello world"

    def test_env_var_substituted(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "tok-abc123")
        result = _interpolate_value("Bearer ${MY_TOKEN}")
        assert result == "Bearer tok-abc123"

    def test_multiple_env_vars_substituted(self, monkeypatch):
        monkeypatch.setenv("HOST", "api.example.com")
        monkeypatch.setenv("PORT", "8080")
        result = _interpolate_value("${HOST}:${PORT}")
        assert result == "api.example.com:8080"

    def test_missing_env_var_replaced_with_empty(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
        result = _interpolate_value("prefix-${NONEXISTENT_VAR}-suffix")
        assert result == "prefix--suffix"

    def test_no_placeholder_unchanged(self):
        assert _interpolate_value("no placeholder here") == "no placeholder here"

    def test_empty_string_unchanged(self):
        assert _interpolate_value("") == ""

    def test_adjacent_placeholders(self, monkeypatch):
        monkeypatch.setenv("A", "hello")
        monkeypatch.setenv("B", "world")
        result = _interpolate_value("${A}${B}")
        assert result == "helloworld"
