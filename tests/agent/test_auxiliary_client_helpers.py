"""Tests for pure helper functions in agent/auxiliary_client.py.

Covers:
- _pool_runtime_api_key(): extract API key from credential pool entry
- _pool_runtime_base_url(): extract base URL from credential pool entry
- _nous_api_key(): extract best API key from Nous provider state dict
- _normalize_vision_provider(): normalize vision provider string
"""

import pytest
from types import SimpleNamespace

from agent.auxiliary_client import (
    _pool_runtime_api_key,
    _pool_runtime_base_url,
    _nous_api_key,
    _normalize_vision_provider,
)


# ── _pool_runtime_api_key ─────────────────────────────────────────────────────

class TestPoolRuntimeApiKey:
    def test_none_entry_returns_empty(self):
        assert _pool_runtime_api_key(None) == ""

    def test_runtime_api_key_attr_used(self):
        entry = SimpleNamespace(runtime_api_key="sk-test")
        assert _pool_runtime_api_key(entry) == "sk-test"

    def test_access_token_fallback_when_no_runtime_api_key(self):
        entry = SimpleNamespace(access_token="tok-abc")
        assert _pool_runtime_api_key(entry) == "tok-abc"

    def test_runtime_api_key_preferred_over_access_token(self):
        entry = SimpleNamespace(runtime_api_key="runtime", access_token="token")
        assert _pool_runtime_api_key(entry) == "runtime"

    def test_key_stripped_of_whitespace(self):
        entry = SimpleNamespace(runtime_api_key="  sk-key  ")
        assert _pool_runtime_api_key(entry) == "sk-key"

    def test_none_runtime_api_key_falls_through_to_access_token(self):
        entry = SimpleNamespace(runtime_api_key=None, access_token="backup")
        assert _pool_runtime_api_key(entry) == "backup"

    def test_both_none_returns_empty(self):
        entry = SimpleNamespace(runtime_api_key=None, access_token=None)
        assert _pool_runtime_api_key(entry) == ""

    def test_object_without_attributes_returns_empty(self):
        entry = object()
        assert _pool_runtime_api_key(entry) == ""


# ── _pool_runtime_base_url ────────────────────────────────────────────────────

class TestPoolRuntimeBaseUrl:
    def test_none_entry_returns_empty_fallback(self):
        assert _pool_runtime_base_url(None) == ""

    def test_none_entry_returns_stripped_fallback(self):
        assert _pool_runtime_base_url(None, "https://api.example.com/") == "https://api.example.com"

    def test_runtime_base_url_attr_used(self):
        entry = SimpleNamespace(runtime_base_url="https://runtime.api.com")
        assert _pool_runtime_base_url(entry) == "https://runtime.api.com"

    def test_inference_base_url_fallback(self):
        entry = SimpleNamespace(runtime_base_url=None, inference_base_url="https://infer.api.com")
        assert _pool_runtime_base_url(entry) == "https://infer.api.com"

    def test_base_url_fallback(self):
        entry = SimpleNamespace(runtime_base_url=None, inference_base_url=None, base_url="https://base.api.com")
        assert _pool_runtime_base_url(entry) == "https://base.api.com"

    def test_trailing_slash_stripped(self):
        entry = SimpleNamespace(runtime_base_url="https://api.example.com/")
        assert _pool_runtime_base_url(entry) == "https://api.example.com"

    def test_fallback_used_when_all_none(self):
        entry = SimpleNamespace(runtime_base_url=None, inference_base_url=None, base_url=None)
        assert _pool_runtime_base_url(entry, "https://fallback.com") == "https://fallback.com"

    def test_object_without_attributes_returns_fallback(self):
        assert _pool_runtime_base_url(object(), "https://fb.com") == "https://fb.com"


# ── _nous_api_key ─────────────────────────────────────────────────────────────

class TestNousApiKey:
    def test_agent_key_preferred(self):
        assert _nous_api_key({"agent_key": "ak-123", "access_token": "at-456"}) == "ak-123"

    def test_access_token_used_when_no_agent_key(self):
        assert _nous_api_key({"access_token": "at-456"}) == "at-456"

    def test_empty_dict_returns_empty(self):
        assert _nous_api_key({}) == ""

    def test_none_agent_key_falls_through_to_access_token(self):
        # agent_key is None → falsy → falls through
        assert _nous_api_key({"agent_key": None, "access_token": "at-456"}) == "at-456"

    def test_empty_agent_key_falls_through_to_access_token(self):
        assert _nous_api_key({"agent_key": "", "access_token": "at-456"}) == "at-456"


# ── _normalize_vision_provider ────────────────────────────────────────────────

class TestNormalizeVisionProvider:
    def test_none_returns_auto(self):
        assert _normalize_vision_provider(None) == "auto"

    def test_empty_returns_auto(self):
        assert _normalize_vision_provider("") == "auto"

    def test_codex_aliased_to_openai_codex(self):
        assert _normalize_vision_provider("codex") == "openai-codex"

    def test_main_aliased_to_custom(self):
        assert _normalize_vision_provider("main") == "custom"

    def test_openrouter_returned_as_is(self):
        assert _normalize_vision_provider("openrouter") == "openrouter"

    def test_case_normalized_to_lower(self):
        assert _normalize_vision_provider("OpenRouter") == "openrouter"

    def test_whitespace_stripped(self):
        assert _normalize_vision_provider("  auto  ") == "auto"

    def test_unknown_provider_lowercased(self):
        assert _normalize_vision_provider("MyProvider") == "myprovider"
