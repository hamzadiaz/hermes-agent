"""Tests for pure helper functions in tools/transcription_tools.py.

Covers:
- _safe_find_spec(): safely detect whether a module is importable
- _normalize_local_command_model(): filter out cloud model names to local default
"""

import pytest

from tools.transcription_tools import (
    _safe_find_spec,
    _normalize_local_command_model,
    DEFAULT_LOCAL_MODEL,
    OPENAI_MODELS,
    GROQ_MODELS,
)


# ── _safe_find_spec ───────────────────────────────────────────────────────────

class TestSafeFindSpec:
    def test_stdlib_module_returns_true(self):
        assert _safe_find_spec("os") is True

    def test_json_stdlib_returns_true(self):
        assert _safe_find_spec("json") is True

    def test_nonexistent_module_returns_false(self):
        assert _safe_find_spec("nonexistent_module_xyz_12345") is False

    def test_returns_bool(self):
        result = _safe_find_spec("os")
        assert isinstance(result, bool)


# ── _normalize_local_command_model ────────────────────────────────────────────

class TestNormalizeLocalCommandModel:
    def test_none_returns_default(self):
        assert _normalize_local_command_model(None) == DEFAULT_LOCAL_MODEL

    def test_empty_string_returns_default(self):
        assert _normalize_local_command_model("") == DEFAULT_LOCAL_MODEL

    def test_openai_model_returns_default(self):
        openai_model = next(iter(OPENAI_MODELS))
        assert _normalize_local_command_model(openai_model) == DEFAULT_LOCAL_MODEL

    def test_groq_model_returns_default(self):
        groq_model = next(iter(GROQ_MODELS))
        assert _normalize_local_command_model(groq_model) == DEFAULT_LOCAL_MODEL

    def test_local_model_name_preserved(self):
        assert _normalize_local_command_model("large-v3") == "large-v3"

    def test_custom_model_name_preserved(self):
        assert _normalize_local_command_model("base.en") == "base.en"

    def test_default_local_model_is_string(self):
        assert isinstance(DEFAULT_LOCAL_MODEL, str)
        assert DEFAULT_LOCAL_MODEL  # non-empty
