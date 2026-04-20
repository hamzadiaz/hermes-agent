"""Tests for pure helper functions in hermes_cli/nous_subscription.py.

Covers:
- _model_config_dict(): model key normalization (dict/string/missing)
- _browser_label(): provider → human-readable label mapping
- _tts_label(): provider → human-readable TTS label mapping
- _resolve_browser_feature_state(): browser availability precedence logic
"""

import pytest

from hermes_cli.nous_subscription import (
    _model_config_dict,
    _browser_label,
    _tts_label,
    _resolve_browser_feature_state,
)


# ── _model_config_dict ────────────────────────────────────────────────────────

class TestModelConfigDict:
    def test_dict_model_returned_as_copy(self):
        config = {"model": {"default": "gpt-5", "provider": "openai"}}
        result = _model_config_dict(config)
        assert result == {"default": "gpt-5", "provider": "openai"}

    def test_returned_dict_is_a_copy(self):
        config = {"model": {"default": "gpt-5"}}
        result = _model_config_dict(config)
        result["extra"] = "x"
        assert "extra" not in config["model"]

    def test_string_model_wrapped_in_default(self):
        config = {"model": "claude-opus"}
        result = _model_config_dict(config)
        assert result == {"default": "claude-opus"}

    def test_whitespace_string_returns_empty(self):
        config = {"model": "   "}
        result = _model_config_dict(config)
        assert result == {}

    def test_none_model_returns_empty(self):
        config = {"model": None}
        result = _model_config_dict(config)
        assert result == {}

    def test_missing_model_returns_empty(self):
        config = {}
        result = _model_config_dict(config)
        assert result == {}

    def test_string_stripped(self):
        config = {"model": "  gpt-5  "}
        result = _model_config_dict(config)
        assert result == {"default": "gpt-5"}


# ── _browser_label ────────────────────────────────────────────────────────────

class TestBrowserLabel:
    def test_browserbase_returns_label(self):
        assert _browser_label("browserbase") == "Browserbase"

    def test_browser_use_returns_label(self):
        assert _browser_label("browser-use") == "Browser Use"

    def test_camofox_returns_label(self):
        assert _browser_label("camofox") == "Camofox"

    def test_local_returns_label(self):
        assert _browser_label("local") == "Local browser"

    def test_unknown_provider_returned_as_is(self):
        assert _browser_label("my-browser") == "my-browser"

    def test_none_returns_default(self):
        assert _browser_label(None) == "Local browser"

    def test_empty_returns_default(self):
        assert _browser_label("") == "Local browser"


# ── _tts_label ────────────────────────────────────────────────────────────────

class TestTtsLabel:
    def test_openai_returns_openai_tts(self):
        assert _tts_label("openai") == "OpenAI TTS"

    def test_elevenlabs_returns_elevenlabs(self):
        assert _tts_label("elevenlabs") == "ElevenLabs"

    def test_edge_returns_edge_tts(self):
        assert _tts_label("edge") == "Edge TTS"

    def test_neutts_returns_neutts(self):
        assert _tts_label("neutts") == "NeuTTS"

    def test_unknown_provider_returned_as_is(self):
        assert _tts_label("custom-tts") == "custom-tts"

    def test_none_returns_default(self):
        assert _tts_label(None) == "Edge TTS"

    def test_empty_returns_default(self):
        assert _tts_label("") == "Edge TTS"


# ── _resolve_browser_feature_state ───────────────────────────────────────────

def _kwargs(**overrides):
    """Build keyword args for _resolve_browser_feature_state with sane defaults."""
    defaults = dict(
        browser_tool_enabled=False,
        browser_provider="",
        browser_provider_explicit=False,
        browser_local_available=True,
        direct_camofox=False,
        direct_browserbase=False,
        direct_browser_use=False,
        managed_browser_available=False,
    )
    defaults.update(overrides)
    return defaults


class TestResolveBrowserFeatureState:
    def test_direct_camofox_wins_regardless_of_other_flags(self):
        provider, available, active, managed = _resolve_browser_feature_state(
            **_kwargs(direct_camofox=True, browser_tool_enabled=True)
        )
        assert provider == "camofox"
        assert available is True
        assert managed is False

    def test_direct_camofox_active_matches_browser_tool_enabled(self):
        _, _, active, _ = _resolve_browser_feature_state(**_kwargs(
            direct_camofox=True, browser_tool_enabled=True
        ))
        assert active is True

    def test_direct_camofox_inactive_when_tool_disabled(self):
        _, _, active, _ = _resolve_browser_feature_state(**_kwargs(
            direct_camofox=True, browser_tool_enabled=False
        ))
        assert active is False

    def test_explicit_browserbase_provider(self):
        provider, available, active, managed = _resolve_browser_feature_state(**_kwargs(
            browser_provider="browserbase",
            browser_provider_explicit=True,
            browser_local_available=True,
            direct_browserbase=True,
            browser_tool_enabled=True,
        ))
        assert provider == "browserbase"
        assert available is True
        assert active is True

    def test_explicit_browser_use_provider(self):
        provider, available, active, _ = _resolve_browser_feature_state(**_kwargs(
            browser_provider="browser-use",
            browser_provider_explicit=True,
            browser_local_available=True,
            direct_browser_use=True,
            browser_tool_enabled=True,
        ))
        assert provider == "browser-use"
        assert available is True
        assert active is True

    def test_explicit_browser_use_unavailable_when_no_direct(self):
        _, available, active, _ = _resolve_browser_feature_state(**_kwargs(
            browser_provider="browser-use",
            browser_provider_explicit=True,
            browser_local_available=True,
            direct_browser_use=False,
        ))
        assert available is False
        assert active is False

    def test_explicit_camofox_provider_returns_not_available(self):
        provider, available, active, managed = _resolve_browser_feature_state(**_kwargs(
            browser_provider="camofox",
            browser_provider_explicit=True,
        ))
        assert provider == "camofox"
        assert available is False
        assert active is False

    def test_managed_browserbase_auto_selected(self):
        provider, available, active, managed = _resolve_browser_feature_state(**_kwargs(
            managed_browser_available=True,
            browser_local_available=True,
            browser_tool_enabled=True,
        ))
        assert provider == "browserbase"
        assert available is True
        assert active is True

    def test_no_special_flags_falls_through_to_local(self):
        provider, available, active, _ = _resolve_browser_feature_state(**_kwargs(
            browser_local_available=True,
            browser_tool_enabled=True,
        ))
        assert provider == "local"
        assert active is True

    def test_local_unavailable_when_local_not_available(self):
        _, available, active, _ = _resolve_browser_feature_state(**_kwargs(
            browser_local_available=False,
        ))
        assert available is False
        assert active is False
