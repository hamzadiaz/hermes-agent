"""Tests for pure helper functions in agent/smart_model_routing.py.

Covers:
- _coerce_bool(): truthy-value coercion with default
- _coerce_int(): int coercion with default fallback
- choose_cheap_model_route(): conservative cheap-model routing logic
"""

import pytest

from agent.smart_model_routing import (
    _coerce_bool,
    _coerce_int,
    choose_cheap_model_route,
)


# ── _coerce_bool ──────────────────────────────────────────────────────────────

class TestCoerceBool:
    def test_true_string_returns_true(self):
        assert _coerce_bool("true") is True

    def test_false_string_returns_false(self):
        assert _coerce_bool("false") is False

    def test_one_string_returns_true(self):
        assert _coerce_bool("1") is True

    def test_zero_string_returns_false(self):
        assert _coerce_bool("0") is False

    def test_none_returns_default_false(self):
        assert _coerce_bool(None, default=False) is False

    def test_none_returns_default_true_when_set(self):
        assert _coerce_bool(None, default=True) is True

    def test_empty_string_returns_default(self):
        assert _coerce_bool("", default=False) is False

    def test_bool_true_passthrough(self):
        assert _coerce_bool(True) is True

    def test_bool_false_passthrough(self):
        assert _coerce_bool(False) is False


# ── _coerce_int ───────────────────────────────────────────────────────────────

class TestCoerceInt:
    def test_int_returned_directly(self):
        assert _coerce_int(42, 0) == 42

    def test_string_int_converted(self):
        assert _coerce_int("99", 0) == 99

    def test_float_truncated(self):
        assert _coerce_int(3.9, 0) == 3

    def test_none_returns_default(self):
        assert _coerce_int(None, 7) == 7

    def test_invalid_string_returns_default(self):
        assert _coerce_int("not-a-number", 5) == 5

    def test_empty_string_returns_default(self):
        assert _coerce_int("", 10) == 10

    def test_zero_int(self):
        assert _coerce_int(0, 99) == 0

    def test_negative_int(self):
        assert _coerce_int(-5, 0) == -5


# ── choose_cheap_model_route ──────────────────────────────────────────────────

_CHEAP_CFG = {
    "enabled": True,
    "cheap_model": {"provider": "openai", "model": "gpt-4o-mini"},
}


class TestChooseCheapModelRoute:
    def test_none_config_returns_none(self):
        assert choose_cheap_model_route("hello", None) is None

    def test_disabled_returns_none(self):
        cfg = {**_CHEAP_CFG, "enabled": False}
        assert choose_cheap_model_route("hello", cfg) is None

    def test_simple_message_returns_route(self):
        result = choose_cheap_model_route("hello", _CHEAP_CFG)
        assert result is not None
        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4o-mini"
        assert result["routing_reason"] == "simple_turn"

    def test_empty_message_returns_none(self):
        assert choose_cheap_model_route("", _CHEAP_CFG) is None
        assert choose_cheap_model_route("   ", _CHEAP_CFG) is None

    def test_long_message_returns_none(self):
        long_msg = "a " * 200  # well over 160 chars
        assert choose_cheap_model_route(long_msg, _CHEAP_CFG) is None

    def test_many_words_returns_none(self):
        many_words = " ".join(["word"] * 30)  # > 28 words
        assert choose_cheap_model_route(many_words, _CHEAP_CFG) is None

    def test_multiline_returns_none(self):
        assert choose_cheap_model_route("line1\nline2\nline3", _CHEAP_CFG) is None

    def test_backtick_code_returns_none(self):
        assert choose_cheap_model_route("run `foo`", _CHEAP_CFG) is None

    def test_code_block_returns_none(self):
        assert choose_cheap_model_route("```python\ncode\n```", _CHEAP_CFG) is None

    def test_url_returns_none(self):
        assert choose_cheap_model_route("check https://example.com", _CHEAP_CFG) is None

    def test_www_url_returns_none(self):
        assert choose_cheap_model_route("go to www.example.com", _CHEAP_CFG) is None

    def test_complex_keyword_returns_none(self):
        for kw in ("debug", "implement", "refactor", "analyze", "test"):
            assert choose_cheap_model_route(f"please {kw} this", _CHEAP_CFG) is None

    def test_provider_lowercased_in_result(self):
        cfg = {
            "enabled": True,
            "cheap_model": {"provider": "OpenAI", "model": "gpt-4o-mini"},
        }
        result = choose_cheap_model_route("hi there", cfg)
        assert result["provider"] == "openai"

    def test_missing_provider_returns_none(self):
        cfg = {
            "enabled": True,
            "cheap_model": {"model": "gpt-4o-mini"},
        }
        assert choose_cheap_model_route("hello", cfg) is None

    def test_missing_model_returns_none(self):
        cfg = {
            "enabled": True,
            "cheap_model": {"provider": "openai"},
        }
        assert choose_cheap_model_route("hello", cfg) is None

    def test_cheap_model_not_dict_returns_none(self):
        cfg = {"enabled": True, "cheap_model": "openai/gpt-4o-mini"}
        assert choose_cheap_model_route("hello", cfg) is None

    def test_custom_max_chars_respected(self):
        cfg = {**_CHEAP_CFG, "max_simple_chars": 5}
        # "hello world" = 11 chars > 5 → None
        assert choose_cheap_model_route("hello world", cfg) is None
        # "hi" = 2 chars ≤ 5 → route
        assert choose_cheap_model_route("hi", cfg) is not None

    def test_custom_max_words_respected(self):
        cfg = {**_CHEAP_CFG, "max_simple_words": 3}
        assert choose_cheap_model_route("one two three four", cfg) is None
        assert choose_cheap_model_route("one two", cfg) is not None
