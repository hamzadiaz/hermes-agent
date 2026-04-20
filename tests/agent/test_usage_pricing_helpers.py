"""Tests for pure helper functions in agent/usage_pricing.py.

Covers:
- _to_decimal(): value coercion to Decimal, invalid → None
- _to_int(): value coercion to int, invalid → 0
- resolve_billing_route(): billing route classification from model/provider/base_url
- CanonicalUsage: derived properties (prompt_tokens, total_tokens)
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from agent.usage_pricing import (
    _to_decimal,
    _to_int,
    resolve_billing_route,
    CanonicalUsage,
)


# ── _to_decimal ───────────────────────────────────────────────────────────────

class TestToDecimal:
    def test_none_returns_none(self):
        assert _to_decimal(None) is None

    def test_int_value(self):
        assert _to_decimal(5) == Decimal("5")

    def test_float_value(self):
        assert _to_decimal(1.5) == Decimal("1.5")

    def test_string_value(self):
        assert _to_decimal("3.14") == Decimal("3.14")

    def test_zero_int(self):
        assert _to_decimal(0) == Decimal("0")

    def test_invalid_string_returns_none(self):
        assert _to_decimal("not-a-number") is None

    def test_empty_string_returns_none(self):
        assert _to_decimal("") is None

    def test_decimal_input(self):
        d = Decimal("2.5")
        assert _to_decimal(d) == Decimal("2.5")

    def test_scientific_notation_string(self):
        result = _to_decimal("1e-6")
        assert result is not None
        assert result < Decimal("1")


# ── _to_int ───────────────────────────────────────────────────────────────────

class TestToInt:
    def test_none_returns_zero(self):
        assert _to_int(None) == 0

    def test_int_value(self):
        assert _to_int(5) == 5

    def test_float_truncated(self):
        assert _to_int(3.9) == 3

    def test_string_int(self):
        assert _to_int("42") == 42

    def test_zero(self):
        assert _to_int(0) == 0

    def test_invalid_string_returns_zero(self):
        assert _to_int("abc") == 0

    def test_empty_string_returns_zero(self):
        assert _to_int("") == 0

    def test_false_returns_zero(self):
        assert _to_int(False) == 0

    def test_true_returns_one(self):
        assert _to_int(True) == 1


# ── resolve_billing_route ─────────────────────────────────────────────────────

class TestResolveBillingRoute:
    def test_openrouter_provider_name(self):
        route = resolve_billing_route("some-model", provider="openrouter")
        assert route.provider == "openrouter"
        assert route.billing_mode == "official_models_api"

    def test_openrouter_base_url(self):
        route = resolve_billing_route("some-model", base_url="https://openrouter.ai/api/v1")
        assert route.provider == "openrouter"

    def test_anthropic_provider(self):
        route = resolve_billing_route("claude-opus", provider="anthropic")
        assert route.provider == "anthropic"
        assert route.billing_mode == "official_docs_snapshot"

    def test_openai_provider(self):
        route = resolve_billing_route("gpt-5", provider="openai")
        assert route.provider == "openai"
        assert route.billing_mode == "official_docs_snapshot"

    def test_openai_codex_provider(self):
        route = resolve_billing_route("gpt-5.3-codex", provider="openai-codex")
        assert route.provider == "openai-codex"
        assert route.billing_mode == "subscription_included"

    def test_custom_provider(self):
        route = resolve_billing_route("llama-3", provider="custom")
        assert route.billing_mode == "unknown"

    def test_localhost_base_url_is_local(self):
        route = resolve_billing_route("llama-3", base_url="http://localhost:11434/v1")
        assert route.billing_mode == "unknown"

    def test_model_with_slash_infers_provider(self):
        """anthropic/claude-opus should resolve anthropic as provider."""
        route = resolve_billing_route("anthropic/claude-opus")
        assert route.provider == "anthropic"
        assert route.model == "claude-opus"

    def test_google_slash_inferred(self):
        route = resolve_billing_route("google/gemini-3-flash")
        assert route.provider == "google"
        assert route.model == "gemini-3-flash"

    def test_openai_slash_inferred(self):
        route = resolve_billing_route("openai/gpt-5")
        assert route.provider == "openai"
        assert route.model == "gpt-5"

    def test_unknown_provider_passthrough(self):
        route = resolve_billing_route("my-model", provider="my-custom")
        assert route.provider == "my-custom"
        assert route.billing_mode == "unknown"

    def test_empty_model_empty_provider(self):
        route = resolve_billing_route("", provider="")
        assert route.provider == "unknown"

    def test_model_stripped_of_prefix_path_for_known_providers(self):
        """anthropic/a/b should strip to just 'b' (split on '/')."""
        route = resolve_billing_route("extra/claude-opus", provider="anthropic")
        # model.split('/')[-1] = 'claude-opus'
        assert route.model == "claude-opus"

    def test_base_url_preserved_in_route(self):
        route = resolve_billing_route("gpt-5", provider="openai", base_url="https://api.openai.com/v1")
        assert route.base_url == "https://api.openai.com/v1"


# ── CanonicalUsage derived properties ─────────────────────────────────────────

class TestCanonicalUsageProperties:
    def test_prompt_tokens_sums_input_cache_read_cache_write(self):
        u = CanonicalUsage(input_tokens=100, cache_read_tokens=50, cache_write_tokens=25)
        assert u.prompt_tokens == 175

    def test_total_tokens_includes_output(self):
        u = CanonicalUsage(input_tokens=100, output_tokens=200)
        assert u.total_tokens == 300

    def test_defaults_all_zero(self):
        u = CanonicalUsage()
        assert u.prompt_tokens == 0
        assert u.total_tokens == 0

    def test_total_tokens_includes_cache_buckets(self):
        u = CanonicalUsage(input_tokens=10, output_tokens=20, cache_read_tokens=5, cache_write_tokens=3)
        assert u.total_tokens == 38
