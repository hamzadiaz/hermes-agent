"""Tests for URL and payload pure helpers in agent/model_metadata.py.

Covers:
- _normalize_base_url(): strip whitespace and trailing slash
- _is_openrouter_base_url(): detect openrouter.ai base URLs
- _is_custom_endpoint(): detect HTTP endpoints eligible for probing
- _infer_provider_from_url(): map base URL to known provider name
- _is_known_provider_base_url(): check if URL maps to a known provider
- _iter_nested_dicts(): yield all dicts from nested structure
- _coerce_reasonable_int(): parse int within [1024, 10_000_000] range
- _extract_first_int(): find first matching key value in nested payload
"""

import pytest

from agent.model_metadata import (
    _coerce_reasonable_int,
    _extract_first_int,
    _infer_provider_from_url,
    _is_custom_endpoint,
    _is_known_provider_base_url,
    _is_openrouter_base_url,
    _iter_nested_dicts,
    _normalize_base_url,
)


# ── _normalize_base_url ───────────────────────────────────────────────────────

class TestNormalizeBaseUrl:
    def test_trailing_slash_stripped(self):
        assert _normalize_base_url("https://api.example.com/") == "https://api.example.com"

    def test_whitespace_stripped(self):
        assert _normalize_base_url("  https://api.example.com  ") == "https://api.example.com"

    def test_none_returns_empty(self):
        assert _normalize_base_url(None) == ""

    def test_empty_string_returns_empty(self):
        assert _normalize_base_url("") == ""

    def test_multiple_trailing_slashes_stripped(self):
        assert _normalize_base_url("https://api.example.com///") == "https://api.example.com"

    def test_path_without_trailing_slash_unchanged(self):
        result = _normalize_base_url("https://api.example.com/v1")
        assert result == "https://api.example.com/v1"


# ── _is_openrouter_base_url ───────────────────────────────────────────────────

class TestIsOpenrouterBaseUrl:
    def test_openrouter_url_detected(self):
        assert _is_openrouter_base_url("https://openrouter.ai/api/v1") is True

    def test_openrouter_no_path_detected(self):
        assert _is_openrouter_base_url("https://openrouter.ai") is True

    def test_non_openrouter_returns_false(self):
        assert _is_openrouter_base_url("https://api.openai.com/v1") is False

    def test_empty_returns_false(self):
        assert _is_openrouter_base_url("") is False

    def test_partial_match_not_a_url_returns_false(self):
        assert _is_openrouter_base_url("not-a-url") is False

    def test_case_insensitive(self):
        assert _is_openrouter_base_url("https://OpenRouter.AI/api/v1") is True


# ── _is_custom_endpoint ───────────────────────────────────────────────────────

class TestIsCustomEndpoint:
    def test_http_endpoint_is_custom(self):
        assert _is_custom_endpoint("https://my-lm-studio.local/v1") is True

    def test_openrouter_not_custom(self):
        # OpenRouter is excluded from probing
        assert _is_custom_endpoint("https://openrouter.ai/api/v1") is False

    def test_cli_scheme_not_custom(self):
        assert _is_custom_endpoint("cli://claude-code") is False

    def test_empty_not_custom(self):
        assert _is_custom_endpoint("") is False

    def test_anthropic_api_is_custom(self):
        # Any non-openrouter, non-cli URL is "custom" (eligible for probing)
        assert _is_custom_endpoint("https://api.anthropic.com/v1") is True

    def test_openai_api_is_custom(self):
        assert _is_custom_endpoint("https://api.openai.com/v1") is True


# ── _infer_provider_from_url ──────────────────────────────────────────────────

class TestInferProviderFromUrl:
    def test_anthropic_api_inferred(self):
        assert _infer_provider_from_url("https://api.anthropic.com/v1") == "anthropic"

    def test_openai_api_inferred(self):
        assert _infer_provider_from_url("https://api.openai.com/v1") == "openai"

    def test_openrouter_inferred(self):
        assert _infer_provider_from_url("https://openrouter.ai/api/v1") == "openrouter"

    def test_google_inferred(self):
        assert _infer_provider_from_url("https://generativelanguage.googleapis.com/v1") == "google"

    def test_deepseek_inferred(self):
        assert _infer_provider_from_url("https://api.deepseek.com/v1") == "deepseek"

    def test_unknown_url_returns_none(self):
        assert _infer_provider_from_url("https://unknown-provider.example.com") is None

    def test_empty_returns_none(self):
        assert _infer_provider_from_url("") is None

    def test_none_returns_none(self):
        assert _infer_provider_from_url(None) is None


# ── _is_known_provider_base_url ───────────────────────────────────────────────

class TestIsKnownProviderBaseUrl:
    def test_known_url_returns_true(self):
        assert _is_known_provider_base_url("https://api.anthropic.com") is True

    def test_unknown_url_returns_false(self):
        assert _is_known_provider_base_url("https://my-custom-server.local") is False

    def test_empty_returns_false(self):
        assert _is_known_provider_base_url("") is False


# ── _iter_nested_dicts ────────────────────────────────────────────────────────

class TestIterNestedDicts:
    def test_flat_dict_yields_itself(self):
        d = {"a": 1}
        result = list(_iter_nested_dicts(d))
        assert d in result
        assert len(result) == 1

    def test_nested_dict_yields_both(self):
        inner = {"b": 2}
        outer = {"a": inner}
        result = list(_iter_nested_dicts(outer))
        assert outer in result
        assert inner in result

    def test_list_of_dicts_yields_each(self):
        d1 = {"x": 1}
        d2 = {"y": 2}
        result = list(_iter_nested_dicts([d1, d2]))
        assert d1 in result
        assert d2 in result

    def test_non_dict_non_list_yields_nothing(self):
        assert list(_iter_nested_dicts("string")) == []
        assert list(_iter_nested_dicts(42)) == []
        assert list(_iter_nested_dicts(None)) == []

    def test_empty_dict_yields_itself(self):
        result = list(_iter_nested_dicts({}))
        assert result == [{}]

    def test_deeply_nested(self):
        structure = {"a": {"b": {"c": {"d": 1}}}}
        result = list(_iter_nested_dicts(structure))
        # Should yield 4 dicts: a, b, c, d
        assert len(result) == 4


# ── _coerce_reasonable_int ────────────────────────────────────────────────────

class TestCoerceReasonableInt:
    def test_valid_int_within_range(self):
        assert _coerce_reasonable_int(8192) == 8192

    def test_minimum_boundary(self):
        assert _coerce_reasonable_int(1024) == 1024

    def test_below_minimum_returns_none(self):
        assert _coerce_reasonable_int(100) is None

    def test_above_maximum_returns_none(self):
        assert _coerce_reasonable_int(10_000_001) is None

    def test_string_int_parsed(self):
        assert _coerce_reasonable_int("16384") == 16384

    def test_comma_formatted_string_parsed(self):
        assert _coerce_reasonable_int("8,192") == 8192

    def test_float_truncated(self):
        assert _coerce_reasonable_int(8192.9) == 8192

    def test_bool_returns_none(self):
        assert _coerce_reasonable_int(True) is None

    def test_none_returns_none(self):
        assert _coerce_reasonable_int(None) is None

    def test_non_numeric_string_returns_none(self):
        assert _coerce_reasonable_int("not-a-number") is None

    def test_maximum_boundary(self):
        assert _coerce_reasonable_int(10_000_000) == 10_000_000


# ── _extract_first_int ────────────────────────────────────────────────────────

class TestExtractFirstInt:
    def test_finds_exact_key(self):
        payload = {"context_length": 32768}
        result = _extract_first_int(payload, ("context_length",))
        assert result == 32768

    def test_case_insensitive_key_match(self):
        payload = {"Context_Length": 8192}
        result = _extract_first_int(payload, ("context_length",))
        assert result == 8192

    def test_first_matching_key_returned(self):
        payload = {"max_tokens": 4096, "context_length": 8192}
        result = _extract_first_int(payload, ("context_length", "max_tokens"))
        # Both are valid — first found in iteration order wins
        assert result in (4096, 8192)

    def test_nested_key_found(self):
        payload = {"model": {"context_length": 16384}}
        result = _extract_first_int(payload, ("context_length",))
        assert result == 16384

    def test_no_matching_key_returns_none(self):
        payload = {"other_key": 100000}
        result = _extract_first_int(payload, ("context_length",))
        assert result is None

    def test_value_out_of_range_skipped(self):
        payload = {"context_length": 50}  # below minimum 1024
        result = _extract_first_int(payload, ("context_length",))
        assert result is None

    def test_empty_payload_returns_none(self):
        assert _extract_first_int({}, ("context_length",)) is None
