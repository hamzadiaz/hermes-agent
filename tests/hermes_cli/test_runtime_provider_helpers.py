"""Tests for pure helper functions in hermes_cli/runtime_provider.py.

Covers:
- _normalize_custom_provider_name(): strip/lower/space-to-hyphen
- _detect_api_mode_for_url(): OpenAI URL → codex_responses, all others → None
- _parse_api_mode(): valid/invalid/case-insensitive mode strings
- format_runtime_provider_error(): AuthError delegation vs plain str()
- _auto_detect_local_model(): empty base_url returns empty string
- _copilot_runtime_api_mode(): configured api_mode preference, no-model fallback
"""

import pytest
from unittest.mock import MagicMock

from hermes_cli.runtime_provider import (
    _auto_detect_local_model,
    _copilot_runtime_api_mode,
    _detect_api_mode_for_url,
    _normalize_custom_provider_name,
    _parse_api_mode,
    format_runtime_provider_error,
)
from hermes_cli.auth import AuthError


# ── _normalize_custom_provider_name ──────────────────────────────────────────

class TestNormalizeCustomProviderName:
    def test_lowercase(self):
        assert _normalize_custom_provider_name("MyProvider") == "myprovider"

    def test_spaces_replaced_with_hyphens(self):
        assert _normalize_custom_provider_name("my provider") == "my-provider"

    def test_leading_trailing_whitespace_stripped(self):
        assert _normalize_custom_provider_name("  provider  ") == "provider"

    def test_multiple_spaces_each_replaced(self):
        assert _normalize_custom_provider_name("a b c") == "a-b-c"

    def test_already_normalized_passthrough(self):
        assert _normalize_custom_provider_name("my-provider") == "my-provider"

    def test_empty_string(self):
        assert _normalize_custom_provider_name("") == ""

    def test_mixed_case_with_spaces(self):
        assert _normalize_custom_provider_name("  OpenAI Custom  ") == "openai-custom"


# ── _detect_api_mode_for_url ──────────────────────────────────────────────────

class TestDetectApiModeForUrl:
    def test_openai_direct_returns_codex_responses(self):
        assert _detect_api_mode_for_url("https://api.openai.com/v1") == "codex_responses"

    def test_openai_with_trailing_slash(self):
        assert _detect_api_mode_for_url("https://api.openai.com/v1/") == "codex_responses"

    def test_openrouter_url_returns_none(self):
        """OpenRouter URL contains openrouter — should NOT return codex_responses."""
        assert _detect_api_mode_for_url("https://openrouter.ai/api/v1") is None

    def test_localhost_returns_none(self):
        assert _detect_api_mode_for_url("http://localhost:1234/v1") is None

    def test_anthropic_returns_none(self):
        assert _detect_api_mode_for_url("https://api.anthropic.com/v1") is None

    def test_empty_string_returns_none(self):
        assert _detect_api_mode_for_url("") is None

    def test_none_like_empty_returns_none(self):
        assert _detect_api_mode_for_url(None) is None

    def test_case_insensitive_openai_match(self):
        assert _detect_api_mode_for_url("HTTPS://API.OPENAI.COM/V1") == "codex_responses"

    def test_openai_via_proxy_still_matches(self):
        """A proxy that has api.openai.com in its URL still triggers the mode."""
        assert _detect_api_mode_for_url("https://api.openai.com/some-proxy/v1") == "codex_responses"


# ── _parse_api_mode ───────────────────────────────────────────────────────────

class TestParseApiMode:
    def test_valid_chat_completions(self):
        assert _parse_api_mode("chat_completions") == "chat_completions"

    def test_valid_codex_responses(self):
        assert _parse_api_mode("codex_responses") == "codex_responses"

    def test_valid_anthropic_messages(self):
        assert _parse_api_mode("anthropic_messages") == "anthropic_messages"

    def test_uppercase_normalized(self):
        assert _parse_api_mode("CHAT_COMPLETIONS") == "chat_completions"

    def test_whitespace_stripped(self):
        assert _parse_api_mode("  codex_responses  ") == "codex_responses"

    def test_invalid_mode_returns_none(self):
        assert _parse_api_mode("invalid_mode") is None

    def test_none_returns_none(self):
        assert _parse_api_mode(None) is None

    def test_non_string_returns_none(self):
        assert _parse_api_mode(123) is None

    def test_empty_string_returns_none(self):
        assert _parse_api_mode("") is None


# ── format_runtime_provider_error ─────────────────────────────────────────────

class TestFormatRuntimeProviderError:
    def test_plain_exception_returns_str(self):
        exc = ValueError("something broke")
        assert format_runtime_provider_error(exc) == "something broke"

    def test_auth_error_delegates_to_format_auth_error(self):
        exc = AuthError("token expired", relogin_required=True)
        result = format_runtime_provider_error(exc)
        # format_auth_error returns a user-friendly message mentioning re-auth
        assert result != "token expired"  # not the raw message
        assert isinstance(result, str)
        assert len(result) > 0

    def test_runtime_error_returns_str(self):
        exc = RuntimeError("network unavailable")
        assert format_runtime_provider_error(exc) == "network unavailable"

    def test_auth_error_no_special_code_returns_message(self):
        exc = AuthError("generic auth failure")
        result = format_runtime_provider_error(exc)
        assert "generic auth failure" in result


# ── _auto_detect_local_model ──────────────────────────────────────────────────

class TestAutoDetectLocalModel:
    def test_empty_base_url_returns_empty(self):
        assert _auto_detect_local_model("") == ""

    def test_none_base_url_returns_empty(self):
        assert _auto_detect_local_model(None) == ""

    def test_unreachable_server_returns_empty(self):
        # A port that almost certainly refuses connections
        result = _auto_detect_local_model("http://127.0.0.1:19999")
        assert result == ""

    def test_non_localhost_returns_empty_when_unreachable(self):
        result = _auto_detect_local_model("http://192.0.2.1:11434")  # TEST-NET
        assert result == ""


# ── _copilot_runtime_api_mode ─────────────────────────────────────────────────

class TestCopilotRuntimeApiMode:
    def test_configured_chat_completions_returned(self):
        result = _copilot_runtime_api_mode({"api_mode": "chat_completions", "default": "gpt-4"}, "key")
        assert result == "chat_completions"

    def test_configured_codex_responses_returned(self):
        result = _copilot_runtime_api_mode({"api_mode": "codex_responses", "default": "codex"}, "key")
        assert result == "codex_responses"

    def test_empty_model_name_returns_chat_completions_default(self):
        # No model name → can't look up api mode → chat_completions
        result = _copilot_runtime_api_mode({"api_mode": None, "default": ""}, "key")
        assert result == "chat_completions"

    def test_no_api_mode_no_model_returns_chat_completions(self):
        result = _copilot_runtime_api_mode({}, "")
        assert result == "chat_completions"

    def test_invalid_api_mode_falls_through_to_lookup(self):
        # Invalid api_mode → _parse_api_mode returns None → model lookup attempted
        # With an empty api_key the copilot_model_api_mode may fail → fallback
        result = _copilot_runtime_api_mode({"api_mode": "invalid", "default": "gpt-4o"}, "")
        assert isinstance(result, str)
        assert len(result) > 0
