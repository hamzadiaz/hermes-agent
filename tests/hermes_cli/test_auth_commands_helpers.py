"""Tests for pure helper functions in hermes_cli/auth_commands.py.

Covers:
- _oauth_default_label(): label generation for OAuth credentials
- _api_key_default_label(): label generation for API key credentials
- _display_source(): manual: prefix stripping
- _normalize_provider(): alias resolution (or/open-router → openrouter)
"""

import pytest

from hermes_cli.auth_commands import (
    _oauth_default_label,
    _api_key_default_label,
    _display_source,
    _normalize_provider,
)


# ── _oauth_default_label ──────────────────────────────────────────────────────

class TestOauthDefaultLabel:
    def test_basic_label(self):
        assert _oauth_default_label("anthropic", 1) == "anthropic-oauth-1"

    def test_count_two(self):
        assert _oauth_default_label("openai", 2) == "openai-oauth-2"

    def test_provider_preserved_as_is(self):
        assert _oauth_default_label("my-custom-provider", 3) == "my-custom-provider-oauth-3"

    def test_count_zero(self):
        assert _oauth_default_label("anthropic", 0) == "anthropic-oauth-0"


# ── _api_key_default_label ────────────────────────────────────────────────────

class TestApiKeyDefaultLabel:
    def test_count_one(self):
        assert _api_key_default_label(1) == "api-key-1"

    def test_count_two(self):
        assert _api_key_default_label(2) == "api-key-2"

    def test_count_zero(self):
        assert _api_key_default_label(0) == "api-key-0"


# ── _display_source ───────────────────────────────────────────────────────────

class TestDisplaySource:
    def test_manual_prefix_stripped(self):
        assert _display_source("manual:my-key-label") == "my-key-label"

    def test_non_manual_source_unchanged(self):
        assert _display_source("imported") == "imported"

    def test_empty_manual_prefix(self):
        """manual: with no value produces empty label."""
        assert _display_source("manual:") == ""

    def test_plain_source_without_colon(self):
        assert _display_source("api_key") == "api_key"

    def test_other_prefix_not_stripped(self):
        assert _display_source("oauth:google") == "oauth:google"


# ── _normalize_provider ───────────────────────────────────────────────────────

class TestNormalizeProvider:
    def test_or_alias_resolves_to_openrouter(self):
        assert _normalize_provider("or") == "openrouter"

    def test_open_router_alias_resolves(self):
        assert _normalize_provider("open-router") == "openrouter"

    def test_canonical_openrouter_unchanged(self):
        assert _normalize_provider("openrouter") == "openrouter"

    def test_anthropic_lowercased(self):
        assert _normalize_provider("Anthropic") == "anthropic"

    def test_empty_returns_empty(self):
        assert _normalize_provider("") == ""

    def test_none_like_empty_returns_empty(self):
        assert _normalize_provider(None) == ""

    def test_whitespace_stripped(self):
        assert _normalize_provider("  anthropic  ") == "anthropic"

    def test_unknown_provider_lowercased_passthrough(self):
        assert _normalize_provider("MyProvider") == "myprovider"
