"""Tests for pure helper functions in agent/credential_pool.py.

Covers:
- _next_priority(): max priority + 1, empty list
- _is_manual_source(): "manual" detection, prefixed "manual:...", edge cases
- _exhausted_ttl(): 429 → 1 hour cooldown, other codes → 24 hour default
- _normalize_custom_pool_name(): strip/lower/space-to-hyphen
- _iter_custom_providers(): valid entries, missing name, non-dict entries, empty
- label_from_token(): JWT email/username claim extraction, fallback
"""

import base64
import json
from dataclasses import dataclass, field
from typing import List, Optional

import pytest

from agent.credential_pool import (
    _next_priority,
    _is_manual_source,
    _exhausted_ttl,
    _normalize_custom_pool_name,
    _iter_custom_providers,
    label_from_token,
    EXHAUSTED_TTL_429_SECONDS,
    EXHAUSTED_TTL_DEFAULT_SECONDS,
    CUSTOM_POOL_PREFIX,
)


# Minimal stub matching the fields _next_priority cares about
@dataclass
class _FakeEntry:
    priority: int = 0


# ── _next_priority ────────────────────────────────────────────────────────────

class TestNextPriority:
    def test_empty_list_returns_zero(self):
        assert _next_priority([]) == 0

    def test_single_entry(self):
        assert _next_priority([_FakeEntry(priority=0)]) == 1

    def test_multiple_entries_picks_max(self):
        entries = [_FakeEntry(5), _FakeEntry(2), _FakeEntry(9)]
        assert _next_priority(entries) == 10

    def test_negative_priority_entry(self):
        assert _next_priority([_FakeEntry(priority=-1)]) == 0


# ── _is_manual_source ─────────────────────────────────────────────────────────

class TestIsManualSource:
    def test_manual_returns_true(self):
        assert _is_manual_source("manual") is True

    def test_manual_with_colon_prefix_returns_true(self):
        assert _is_manual_source("manual:telegram") is True
        assert _is_manual_source("manual:some-label") is True

    def test_uppercase_manual_returns_true(self):
        assert _is_manual_source("MANUAL") is True

    def test_non_manual_returns_false(self):
        assert _is_manual_source("env") is False
        assert _is_manual_source("config") is False

    def test_empty_string_returns_false(self):
        assert _is_manual_source("") is False

    def test_none_like_empty_returns_false(self):
        assert _is_manual_source(None) is False

    def test_whitespace_stripped(self):
        assert _is_manual_source("  manual  ") is True

    def test_partial_match_returns_false(self):
        """'manually' should not match."""
        assert _is_manual_source("manually") is False


# ── _exhausted_ttl ────────────────────────────────────────────────────────────

class TestExhaustedTtl:
    def test_429_returns_one_hour(self):
        assert _exhausted_ttl(429) == EXHAUSTED_TTL_429_SECONDS
        assert _exhausted_ttl(429) == 3600

    def test_none_returns_24_hour_default(self):
        assert _exhausted_ttl(None) == EXHAUSTED_TTL_DEFAULT_SECONDS
        assert _exhausted_ttl(None) == 86400

    def test_other_error_codes_return_default(self):
        assert _exhausted_ttl(401) == EXHAUSTED_TTL_DEFAULT_SECONDS
        assert _exhausted_ttl(500) == EXHAUSTED_TTL_DEFAULT_SECONDS
        assert _exhausted_ttl(0) == EXHAUSTED_TTL_DEFAULT_SECONDS


# ── _normalize_custom_pool_name ───────────────────────────────────────────────

class TestNormalizeCustomPoolName:
    def test_lowercase(self):
        assert _normalize_custom_pool_name("TogetherAI") == "togetherai"

    def test_spaces_to_hyphens(self):
        assert _normalize_custom_pool_name("together ai") == "together-ai"

    def test_strip_whitespace(self):
        assert _normalize_custom_pool_name("  lm studio  ") == "lm-studio"

    def test_already_normalized(self):
        assert _normalize_custom_pool_name("my-provider") == "my-provider"

    def test_empty_string(self):
        assert _normalize_custom_pool_name("") == ""


# ── _iter_custom_providers ────────────────────────────────────────────────────

class TestIterCustomProviders:
    def test_no_custom_providers_key_yields_nothing(self):
        config = {"model": {"default": "gpt-5.4"}}
        result = list(_iter_custom_providers(config))
        assert result == []

    def test_non_list_custom_providers_yields_nothing(self):
        config = {"custom_providers": "not-a-list"}
        result = list(_iter_custom_providers(config))
        assert result == []

    def test_non_dict_entry_skipped(self):
        config = {"custom_providers": ["not-a-dict", {"name": "valid", "base_url": "http://x"}]}
        result = list(_iter_custom_providers(config))
        assert len(result) == 1
        assert result[0][0] == "valid"

    def test_entry_without_name_skipped(self):
        config = {"custom_providers": [{"base_url": "http://x"}]}
        result = list(_iter_custom_providers(config))
        assert result == []

    def test_name_normalized_in_output(self):
        config = {"custom_providers": [{"name": "My Provider", "base_url": "http://x"}]}
        result = list(_iter_custom_providers(config))
        assert result[0][0] == "my-provider"

    def test_multiple_valid_entries(self):
        config = {
            "custom_providers": [
                {"name": "alpha", "base_url": "http://a"},
                {"name": "beta", "base_url": "http://b"},
            ]
        }
        result = list(_iter_custom_providers(config))
        names = [r[0] for r in result]
        assert names == ["alpha", "beta"]

    def test_none_config_yields_nothing(self):
        result = list(_iter_custom_providers(None))
        assert result == []


# ── label_from_token ──────────────────────────────────────────────────────────

def _make_jwt(payload: dict) -> str:
    """Build a minimal JWT with the given claims (no signature — claims only)."""
    b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"header.{b64}.sig"


class TestLabelFromToken:
    def test_email_claim_used(self):
        token = _make_jwt({"email": "user@example.com", "preferred_username": "user"})
        assert label_from_token(token, "fallback") == "user@example.com"

    def test_preferred_username_used_when_no_email(self):
        token = _make_jwt({"preferred_username": "alice"})
        assert label_from_token(token, "fallback") == "alice"

    def test_upn_used_as_last_resort_claim(self):
        token = _make_jwt({"upn": "alice@corp.com"})
        assert label_from_token(token, "fallback") == "alice@corp.com"

    def test_fallback_used_when_no_claims(self):
        token = _make_jwt({"sub": "user123"})
        assert label_from_token(token, "default-label") == "default-label"

    def test_non_jwt_token_uses_fallback(self):
        assert label_from_token("not-a-jwt", "fallback") == "fallback"

    def test_empty_token_uses_fallback(self):
        assert label_from_token("", "fallback") == "fallback"

    def test_whitespace_email_falls_back(self):
        """Email with only whitespace is skipped."""
        token = _make_jwt({"email": "   ", "preferred_username": "user"})
        assert label_from_token(token, "fallback") == "user"
