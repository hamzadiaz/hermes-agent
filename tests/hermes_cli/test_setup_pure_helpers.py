"""Tests for pure helper functions in hermes_cli/setup.py.

Covers:
- _model_config_dict(): model key normalization (dict / string / missing)
- _set_model_provider(): writes provider + base_url into model section
- _set_default_model(): writes default model name into model section
- _get_credential_pool_strategies(): safe extraction with type coercion
- _set_credential_pool_strategy(): upsert into credential_pool_strategies
- _current_reasoning_effort(): extract and normalize agent.reasoning_effort
- _set_reasoning_effort(): upsert reasoning_effort under agent section
"""

import pytest

from hermes_cli.setup import (
    _model_config_dict,
    _set_model_provider,
    _set_default_model,
    _get_credential_pool_strategies,
    _set_credential_pool_strategy,
    _current_reasoning_effort,
    _set_reasoning_effort,
)


# ── _model_config_dict ────────────────────────────────────────────────────────

class TestModelConfigDict:
    def test_model_dict_returned_as_copy(self):
        config = {"model": {"default": "gpt-5", "provider": "openai"}}
        result = _model_config_dict(config)
        assert result == {"default": "gpt-5", "provider": "openai"}

    def test_returned_dict_is_a_copy_not_same_object(self):
        config = {"model": {"default": "gpt-5"}}
        result = _model_config_dict(config)
        result["extra"] = "value"
        assert "extra" not in config["model"]

    def test_model_string_wrapped_in_default_key(self):
        config = {"model": "claude-opus"}
        result = _model_config_dict(config)
        assert result == {"default": "claude-opus"}

    def test_whitespace_only_model_string_returns_empty(self):
        config = {"model": "   "}
        result = _model_config_dict(config)
        assert result == {}

    def test_model_none_returns_empty(self):
        config = {"model": None}
        result = _model_config_dict(config)
        assert result == {}

    def test_no_model_key_returns_empty(self):
        config = {}
        result = _model_config_dict(config)
        assert result == {}

    def test_model_string_stripped(self):
        config = {"model": "  gpt-5  "}
        result = _model_config_dict(config)
        assert result == {"default": "gpt-5"}


# ── _set_model_provider ───────────────────────────────────────────────────────

class TestSetModelProvider:
    def test_sets_provider_in_model_section(self):
        config = {}
        _set_model_provider(config, "anthropic")
        assert config["model"]["provider"] == "anthropic"

    def test_sets_base_url_when_provided(self):
        config = {}
        _set_model_provider(config, "custom", base_url="https://api.example.com")
        assert config["model"]["base_url"] == "https://api.example.com"

    def test_base_url_trailing_slash_stripped(self):
        config = {}
        _set_model_provider(config, "custom", base_url="https://api.example.com/")
        assert config["model"]["base_url"] == "https://api.example.com"

    def test_empty_base_url_removes_base_url_key(self):
        config = {"model": {"provider": "old", "base_url": "https://old.com"}}
        _set_model_provider(config, "anthropic", base_url="")
        assert "base_url" not in config["model"]

    def test_preserves_existing_model_keys(self):
        config = {"model": {"default": "claude-opus"}}
        _set_model_provider(config, "anthropic")
        assert config["model"]["default"] == "claude-opus"
        assert config["model"]["provider"] == "anthropic"

    def test_overwrites_existing_provider(self):
        config = {"model": {"provider": "openai"}}
        _set_model_provider(config, "anthropic")
        assert config["model"]["provider"] == "anthropic"

    def test_string_model_preserved_as_default(self):
        config = {"model": "gpt-5"}
        _set_model_provider(config, "openai")
        assert config["model"]["default"] == "gpt-5"
        assert config["model"]["provider"] == "openai"


# ── _set_default_model ────────────────────────────────────────────────────────

class TestSetDefaultModel:
    def test_sets_default_model(self):
        config = {}
        _set_default_model(config, "gpt-5")
        assert config["model"]["default"] == "gpt-5"

    def test_empty_model_name_is_no_op(self):
        config = {}
        _set_default_model(config, "")
        assert "model" not in config

    def test_preserves_existing_provider(self):
        config = {"model": {"provider": "openai"}}
        _set_default_model(config, "gpt-5")
        assert config["model"]["provider"] == "openai"
        assert config["model"]["default"] == "gpt-5"

    def test_overwrites_existing_default(self):
        config = {"model": {"default": "old-model"}}
        _set_default_model(config, "new-model")
        assert config["model"]["default"] == "new-model"


# ── _get_credential_pool_strategies ──────────────────────────────────────────

class TestGetCredentialPoolStrategies:
    def test_returns_copy_of_strategies(self):
        config = {"credential_pool_strategies": {"openai": "round-robin"}}
        result = _get_credential_pool_strategies(config)
        assert result == {"openai": "round-robin"}

    def test_no_key_returns_empty_dict(self):
        config = {}
        assert _get_credential_pool_strategies(config) == {}

    def test_non_dict_value_returns_empty_dict(self):
        config = {"credential_pool_strategies": "not-a-dict"}
        assert _get_credential_pool_strategies(config) == {}

    def test_none_value_returns_empty_dict(self):
        config = {"credential_pool_strategies": None}
        assert _get_credential_pool_strategies(config) == {}

    def test_returned_dict_is_copy(self):
        config = {"credential_pool_strategies": {"openai": "round-robin"}}
        result = _get_credential_pool_strategies(config)
        result["new"] = "x"
        assert "new" not in config["credential_pool_strategies"]


# ── _set_credential_pool_strategy ─────────────────────────────────────────────

class TestSetCredentialPoolStrategy:
    def test_sets_strategy_for_provider(self):
        config = {}
        _set_credential_pool_strategy(config, "openai", "round-robin")
        assert config["credential_pool_strategies"]["openai"] == "round-robin"

    def test_overwrites_existing_strategy(self):
        config = {"credential_pool_strategies": {"openai": "priority"}}
        _set_credential_pool_strategy(config, "openai", "round-robin")
        assert config["credential_pool_strategies"]["openai"] == "round-robin"

    def test_preserves_other_providers(self):
        config = {"credential_pool_strategies": {"anthropic": "priority"}}
        _set_credential_pool_strategy(config, "openai", "round-robin")
        assert config["credential_pool_strategies"]["anthropic"] == "priority"

    def test_empty_provider_is_no_op(self):
        config = {}
        _set_credential_pool_strategy(config, "", "round-robin")
        assert "credential_pool_strategies" not in config


# ── _current_reasoning_effort ─────────────────────────────────────────────────

class TestCurrentReasoningEffort:
    def test_returns_reasoning_effort_from_agent_section(self):
        config = {"agent": {"reasoning_effort": "high"}}
        assert _current_reasoning_effort(config) == "high"

    def test_normalizes_to_lowercase(self):
        config = {"agent": {"reasoning_effort": "HIGH"}}
        assert _current_reasoning_effort(config) == "high"

    def test_strips_whitespace(self):
        config = {"agent": {"reasoning_effort": "  low  "}}
        assert _current_reasoning_effort(config) == "low"

    def test_no_agent_section_returns_empty(self):
        config = {}
        assert _current_reasoning_effort(config) == ""

    def test_agent_not_dict_returns_empty(self):
        config = {"agent": "not-a-dict"}
        assert _current_reasoning_effort(config) == ""

    def test_none_reasoning_effort_returns_empty(self):
        config = {"agent": {"reasoning_effort": None}}
        assert _current_reasoning_effort(config) == ""

    def test_empty_reasoning_effort_returns_empty(self):
        config = {"agent": {"reasoning_effort": ""}}
        assert _current_reasoning_effort(config) == ""

    def test_absent_reasoning_effort_key_returns_empty(self):
        config = {"agent": {"max_turns": 20}}
        assert _current_reasoning_effort(config) == ""


# ── _set_reasoning_effort ─────────────────────────────────────────────────────

class TestSetReasoningEffort:
    def test_sets_effort_in_agent_section(self):
        config = {}
        _set_reasoning_effort(config, "high")
        assert config["agent"]["reasoning_effort"] == "high"

    def test_creates_agent_section_if_missing(self):
        config = {}
        _set_reasoning_effort(config, "low")
        assert "agent" in config
        assert config["agent"]["reasoning_effort"] == "low"

    def test_overwrites_existing_effort(self):
        config = {"agent": {"reasoning_effort": "low"}}
        _set_reasoning_effort(config, "high")
        assert config["agent"]["reasoning_effort"] == "high"

    def test_preserves_other_agent_settings(self):
        config = {"agent": {"max_turns": 20}}
        _set_reasoning_effort(config, "medium")
        assert config["agent"]["max_turns"] == 20
        assert config["agent"]["reasoning_effort"] == "medium"

    def test_agent_not_dict_replaced_with_new_dict(self):
        config = {"agent": "invalid"}
        _set_reasoning_effort(config, "high")
        assert isinstance(config["agent"], dict)
        assert config["agent"]["reasoning_effort"] == "high"
