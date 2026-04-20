"""Tests for pure helper functions in gateway/run.py.

Covers:
- _platform_config_key(): map Platform enum to config.yaml key
- _resolve_gateway_model(): extract model string from config dict
- _apply_event_runtime_overrides(): apply per-message runtime overrides
"""

from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.run import (
    _apply_event_runtime_overrides,
    _platform_config_key,
    _resolve_gateway_model,
)


# ── _platform_config_key ─────────────────────────────────────────────────────

class TestPlatformConfigKey:
    def test_local_returns_cli(self):
        assert _platform_config_key(Platform.LOCAL) == "cli"

    def test_telegram_returns_telegram(self):
        assert _platform_config_key(Platform.TELEGRAM) == "telegram"

    def test_discord_returns_discord(self):
        assert _platform_config_key(Platform.DISCORD) == "discord"

    def test_whatsapp_returns_whatsapp(self):
        assert _platform_config_key(Platform.WHATSAPP) == "whatsapp"

    def test_slack_returns_slack(self):
        assert _platform_config_key(Platform.SLACK) == "slack"

    def test_api_server_returns_api_server(self):
        assert _platform_config_key(Platform.API_SERVER) == "api_server"

    def test_all_non_local_use_enum_value(self):
        for platform in Platform:
            if platform == Platform.LOCAL:
                continue
            assert _platform_config_key(platform) == platform.value


# ── _resolve_gateway_model ───────────────────────────────────────────────────

class TestResolveGatewayModel:
    def test_empty_config_returns_empty(self):
        assert _resolve_gateway_model({}) == ""

    def test_string_model_returned(self):
        assert _resolve_gateway_model({"model": "claude-3"}) == "claude-3"

    def test_dict_model_default_key(self):
        assert _resolve_gateway_model({"model": {"default": "gpt-4"}}) == "gpt-4"

    def test_dict_model_model_key_fallback(self):
        assert _resolve_gateway_model({"model": {"model": "gemini"}}) == "gemini"

    def test_dict_model_default_preferred_over_model_key(self):
        result = _resolve_gateway_model({"model": {"default": "a", "model": "b"}})
        assert result == "a"

    def test_dict_model_empty_values_return_empty(self):
        assert _resolve_gateway_model({"model": {}}) == ""

    def test_none_config_loads_from_file(self):
        # None triggers _load_gateway_config() which reads the actual file
        result = _resolve_gateway_model(None)
        assert isinstance(result, str)  # returns string, actual value is file-dependent

    def test_model_key_absent_returns_empty(self):
        assert _resolve_gateway_model({"other": "stuff"}) == ""

    def test_dict_model_none_default_falls_to_model_key(self):
        result = _resolve_gateway_model({"model": {"default": None, "model": "fallback"}})
        assert result == "fallback"


# ── _apply_event_runtime_overrides ───────────────────────────────────────────

class TestApplyEventRuntimeOverrides:
    def _event(self, **kwargs):
        """Build a minimal MessageEvent-like namespace."""
        defaults = {
            "model_override": "",
            "provider_override": "",
            "base_url_override": "",
            "api_mode_override": "",
            "api_key_env_override": "",
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_no_overrides_returns_original_model(self):
        event = self._event()
        model, runtime = _apply_event_runtime_overrides(event, "base-model", {})
        assert model == "base-model"

    def test_model_override_takes_effect(self):
        event = self._event(model_override="overridden-model")
        model, runtime = _apply_event_runtime_overrides(event, "base-model", {})
        assert model == "overridden-model"

    def test_whitespace_model_override_falls_back(self):
        event = self._event(model_override="   ")
        model, runtime = _apply_event_runtime_overrides(event, "base-model", {})
        assert model == "base-model"

    def test_provider_override_added_to_runtime(self):
        event = self._event(provider_override="anthropic")
        _, runtime = _apply_event_runtime_overrides(event, "model", {})
        assert runtime["provider"] == "anthropic"

    def test_base_url_override_added_to_runtime(self):
        event = self._event(base_url_override="https://custom.api/v1")
        _, runtime = _apply_event_runtime_overrides(event, "model", {})
        assert runtime["base_url"] == "https://custom.api/v1"

    def test_api_mode_override_added_to_runtime(self):
        event = self._event(api_mode_override="responses")
        _, runtime = _apply_event_runtime_overrides(event, "model", {})
        assert runtime["api_mode"] == "responses"

    def test_no_overrides_runtime_kwargs_preserved(self):
        event = self._event()
        _, runtime = _apply_event_runtime_overrides(event, "model", {"timeout": 30})
        assert runtime["timeout"] == 30

    def test_runtime_kwargs_not_mutated(self):
        event = self._event(provider_override="openai")
        original = {"timeout": 30}
        _, runtime = _apply_event_runtime_overrides(event, "model", original)
        # original dict is not mutated
        assert "provider" not in original
        assert runtime["provider"] == "openai"

    def test_empty_provider_override_not_added(self):
        event = self._event(provider_override="")
        _, runtime = _apply_event_runtime_overrides(event, "model", {})
        assert "provider" not in runtime

    def test_event_without_override_attrs_handled(self):
        """Event with none of the override attrs — falls back to defaults."""
        event = SimpleNamespace()  # missing all override attrs
        model, runtime = _apply_event_runtime_overrides(event, "fallback-model", {})
        assert model == "fallback-model"
        assert runtime == {}
