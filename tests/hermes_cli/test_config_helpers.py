"""Tests for pure helper functions in hermes_cli/config.py.

Covers:
- _deep_merge(): recursive dict merge, override wins, nested preservation
- _expand_env_vars(): ${VAR} substitution, recursion, unresolved verbatim
- _normalize_root_model_keys(): root provider/base_url migration into model section
- _normalize_max_turns_config(): root max_turns migration into agent section
"""

import pytest

from hermes_cli.config import (
    _deep_merge,
    _expand_env_vars,
    _normalize_root_model_keys,
    _normalize_max_turns_config,
)


# ── _deep_merge ───────────────────────────────────────────────────────────────

class TestDeepMerge:
    def test_empty_override_returns_base(self):
        base = {"a": 1, "b": 2}
        result = _deep_merge(base, {})
        assert result == {"a": 1, "b": 2}

    def test_empty_base_returns_override(self):
        result = _deep_merge({}, {"a": 1})
        assert result == {"a": 1}

    def test_both_empty_returns_empty(self):
        assert _deep_merge({}, {}) == {}

    def test_override_wins_for_scalar(self):
        result = _deep_merge({"a": 1}, {"a": 99})
        assert result["a"] == 99

    def test_base_key_not_in_override_preserved(self):
        result = _deep_merge({"a": 1, "b": 2}, {"a": 99})
        assert result["b"] == 2

    def test_nested_dict_merged_recursively(self):
        base = {"tts": {"model": "default_model", "voice": "alice"}}
        override = {"tts": {"voice": "bob"}}
        result = _deep_merge(base, override)
        assert result["tts"]["model"] == "default_model"
        assert result["tts"]["voice"] == "bob"

    def test_nested_override_wins_over_base(self):
        base = {"tts": {"voice": "alice"}}
        override = {"tts": {"voice": "bob"}}
        result = _deep_merge(base, override)
        assert result["tts"]["voice"] == "bob"

    def test_override_dict_value_replaces_scalar(self):
        """If base has scalar and override has dict, override wins outright."""
        result = _deep_merge({"a": 42}, {"a": {"nested": True}})
        assert result["a"] == {"nested": True}

    def test_override_scalar_replaces_dict(self):
        """If base has dict and override has scalar, override wins."""
        result = _deep_merge({"a": {"x": 1}}, {"a": 99})
        assert result["a"] == 99

    def test_does_not_mutate_base(self):
        base = {"a": {"x": 1}}
        _deep_merge(base, {"a": {"y": 2}})
        assert "y" not in base["a"]

    def test_does_not_mutate_override(self):
        override = {"a": 99}
        _deep_merge({"a": 1}, override)
        assert override == {"a": 99}

    def test_deep_nesting(self):
        base = {"a": {"b": {"c": {"d": 1}}}}
        override = {"a": {"b": {"c": {"e": 2}}}}
        result = _deep_merge(base, override)
        assert result["a"]["b"]["c"]["d"] == 1
        assert result["a"]["b"]["c"]["e"] == 2

    def test_new_key_in_override_added(self):
        result = _deep_merge({"a": 1}, {"b": 2})
        assert result["a"] == 1
        assert result["b"] == 2

    def test_none_value_override(self):
        result = _deep_merge({"a": 1}, {"a": None})
        assert result["a"] is None


# ── _expand_env_vars ──────────────────────────────────────────────────────────

class TestExpandEnvVars:
    def test_string_with_set_var_expanded(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "secret123")
        result = _expand_env_vars("token=${MY_TOKEN}")
        assert result == "token=secret123"

    def test_string_with_unset_var_kept_verbatim(self, monkeypatch):
        monkeypatch.delenv("HERMES_NONEXISTENT", raising=False)
        result = _expand_env_vars("value=${HERMES_NONEXISTENT}")
        assert result == "value=${HERMES_NONEXISTENT}"

    def test_multiple_vars_in_one_string(self, monkeypatch):
        monkeypatch.setenv("HOST", "localhost")
        monkeypatch.setenv("PORT", "5432")
        result = _expand_env_vars("${HOST}:${PORT}")
        assert result == "localhost:5432"

    def test_string_without_vars_unchanged(self):
        assert _expand_env_vars("plain string") == "plain string"

    def test_empty_string_unchanged(self):
        assert _expand_env_vars("") == ""

    def test_dict_values_expanded_recursively(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "key-abc")
        obj = {"credentials": {"api_key": "${API_KEY}"}}
        result = _expand_env_vars(obj)
        assert result["credentials"]["api_key"] == "key-abc"

    def test_dict_keys_not_expanded(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "resolved")
        obj = {"${MY_KEY}": "value"}
        result = _expand_env_vars(obj)
        assert "${MY_KEY}" in result  # keys are not processed

    def test_list_items_expanded(self, monkeypatch):
        monkeypatch.setenv("ITEM", "hello")
        result = _expand_env_vars(["${ITEM}", "world"])
        assert result == ["hello", "world"]

    def test_integer_unchanged(self):
        assert _expand_env_vars(42) == 42

    def test_none_unchanged(self):
        assert _expand_env_vars(None) is None

    def test_bool_unchanged(self):
        assert _expand_env_vars(True) is True

    def test_nested_list_in_dict(self, monkeypatch):
        monkeypatch.setenv("VAL", "expanded")
        obj = {"items": ["${VAL}", "static"]}
        result = _expand_env_vars(obj)
        assert result["items"] == ["expanded", "static"]

    def test_no_dollar_brace_pattern_not_touched(self):
        """$VAR without braces is not expanded."""
        result = _expand_env_vars("$HOME_DIR")
        assert result == "$HOME_DIR"


# ── _normalize_root_model_keys ────────────────────────────────────────────────

class TestNormalizeRootModelKeys:
    def test_no_root_keys_returns_unchanged(self):
        config = {"model": {"default": "gpt-5"}}
        result = _normalize_root_model_keys(config)
        assert result == {"model": {"default": "gpt-5"}}

    def test_root_provider_migrated_into_model(self):
        config = {"provider": "anthropic"}
        result = _normalize_root_model_keys(config)
        assert result["model"]["provider"] == "anthropic"
        assert "provider" not in result

    def test_root_base_url_migrated_into_model(self):
        config = {"base_url": "https://api.example.com"}
        result = _normalize_root_model_keys(config)
        assert result["model"]["base_url"] == "https://api.example.com"
        assert "base_url" not in result

    def test_root_provider_does_not_override_existing_model_provider(self):
        config = {"provider": "anthropic", "model": {"provider": "openai"}}
        result = _normalize_root_model_keys(config)
        assert result["model"]["provider"] == "openai"
        assert "provider" not in result

    def test_root_base_url_does_not_override_existing_model_base_url(self):
        config = {"base_url": "https://root.com", "model": {"base_url": "https://model.com"}}
        result = _normalize_root_model_keys(config)
        assert result["model"]["base_url"] == "https://model.com"

    def test_existing_model_section_extended(self):
        config = {"provider": "anthropic", "model": {"default": "claude-opus"}}
        result = _normalize_root_model_keys(config)
        assert result["model"]["default"] == "claude-opus"
        assert result["model"]["provider"] == "anthropic"

    def test_model_as_string_wrapped_in_dict(self):
        """If model is a plain string, it becomes model.default."""
        config = {"provider": "openai", "model": "gpt-5"}
        result = _normalize_root_model_keys(config)
        assert result["model"]["default"] == "gpt-5"
        assert result["model"]["provider"] == "openai"

    def test_model_absent_creates_model_dict(self):
        config = {"provider": "openai"}
        result = _normalize_root_model_keys(config)
        assert isinstance(result["model"], dict)
        assert result["model"]["provider"] == "openai"

    def test_empty_root_provider_not_migrated(self):
        """Empty/falsy provider should not be migrated."""
        config = {"provider": ""}
        result = _normalize_root_model_keys(config)
        assert "model" not in result or not result.get("model", {}).get("provider")

    def test_does_not_mutate_input(self):
        config = {"provider": "anthropic"}
        original = dict(config)
        _normalize_root_model_keys(config)
        assert config == original


# ── _normalize_max_turns_config ───────────────────────────────────────────────

class TestNormalizeMaxTurnsConfig:
    def test_root_max_turns_migrated_to_agent(self):
        config = {"max_turns": 20}
        result = _normalize_max_turns_config(config)
        assert result["agent"]["max_turns"] == 20
        assert "max_turns" not in result

    def test_root_max_turns_does_not_override_existing_agent_max_turns(self):
        config = {"max_turns": 20, "agent": {"max_turns": 50}}
        result = _normalize_max_turns_config(config)
        assert result["agent"]["max_turns"] == 50
        assert "max_turns" not in result

    def test_no_root_max_turns_uses_default(self):
        config = {}
        result = _normalize_max_turns_config(config)
        assert "max_turns" in result["agent"]

    def test_existing_agent_section_preserved(self):
        config = {"agent": {"some_setting": True}}
        result = _normalize_max_turns_config(config)
        assert result["agent"]["some_setting"] is True

    def test_does_not_mutate_input(self):
        config = {"max_turns": 10}
        _normalize_max_turns_config(config)
        # Root key still in original (function works on a copy)
        assert "max_turns" in config

    def test_root_max_turns_removed_from_result(self):
        config = {"max_turns": 5, "other": "value"}
        result = _normalize_max_turns_config(config)
        assert "max_turns" not in result
        assert result["other"] == "value"

    def test_none_agent_section_treated_as_empty(self):
        """agent: null in YAML should be treated as empty dict."""
        config = {"agent": None, "max_turns": 7}
        result = _normalize_max_turns_config(config)
        assert result["agent"]["max_turns"] == 7
