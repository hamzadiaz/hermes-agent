"""Tests for pure helper functions in hermes_cli/models.py.

Covers:
- normalize_provider(): alias resolution, case normalization, None default
- provider_label(): human-friendly labels, auto passthrough, unknown fallback
- _payload_items(): list/dict/empty input
- _extract_model_ids(): ID extraction from payloads
- _copilot_catalog_item_is_text_model(): model_picker_enabled, capabilities.type,
  supported_endpoints filtering
- _is_github_models_base_url(): Copilot + GitHub AI URLs
"""

import pytest
from hermes_cli.models import (
    normalize_provider,
    provider_label,
    _payload_items,
    _extract_model_ids,
    _copilot_catalog_item_is_text_model,
    _is_github_models_base_url,
)


# ── normalize_provider ────────────────────────────────────────────────────────

class TestNormalizeProvider:
    def test_none_defaults_to_openrouter(self):
        assert normalize_provider(None) == "openrouter"

    def test_empty_string_defaults_to_openrouter(self):
        assert normalize_provider("") == "openrouter"

    def test_whitespace_only_returns_empty_string(self):
        """Whitespace-only is truthy so doesn't use 'openrouter' default; strips to ''."""
        assert normalize_provider("   ") == ""

    def test_canonical_passthrough(self):
        assert normalize_provider("anthropic") == "anthropic"
        assert normalize_provider("openrouter") == "openrouter"

    def test_github_alias(self):
        assert normalize_provider("github") == "copilot"

    def test_github_copilot_alias(self):
        assert normalize_provider("github-copilot") == "copilot"

    def test_claude_alias(self):
        assert normalize_provider("claude") == "anthropic"

    def test_kimi_alias(self):
        assert normalize_provider("kimi") == "kimi-coding"

    def test_uppercase_input_normalized(self):
        assert normalize_provider("ANTHROPIC") == "anthropic"

    def test_unknown_provider_passthrough(self):
        assert normalize_provider("my-custom-provider") == "my-custom-provider"

    def test_auto_passthrough(self):
        """'auto' is not resolved here — it passes through unchanged."""
        assert normalize_provider("auto") == "auto"


# ── provider_label ────────────────────────────────────────────────────────────

class TestProviderLabel:
    def test_none_defaults_to_openrouter_label(self):
        assert provider_label(None) == "OpenRouter"

    def test_known_provider_returns_label(self):
        assert provider_label("anthropic") == "Anthropic"

    def test_alias_resolves_to_label(self):
        assert provider_label("github") == "GitHub Copilot"

    def test_auto_returns_auto(self):
        assert provider_label("auto") == "Auto"

    def test_unknown_provider_returns_original(self):
        assert provider_label("my-unknown-provider") == "my-unknown-provider"

    def test_openrouter_label(self):
        assert provider_label("openrouter") == "OpenRouter"


# ── _payload_items ────────────────────────────────────────────────────────────

class TestPayloadItems:
    def test_list_of_dicts_returned_as_is(self):
        payload = [{"id": "a"}, {"id": "b"}]
        assert _payload_items(payload) == [{"id": "a"}, {"id": "b"}]

    def test_non_dict_items_in_list_filtered(self):
        payload = [{"id": "a"}, "not-a-dict", 42]
        assert _payload_items(payload) == [{"id": "a"}]

    def test_dict_with_data_key_unwrapped(self):
        payload = {"data": [{"id": "x"}, {"id": "y"}]}
        assert _payload_items(payload) == [{"id": "x"}, {"id": "y"}]

    def test_dict_without_data_key_returns_empty(self):
        payload = {"models": [{"id": "x"}]}
        assert _payload_items(payload) == []

    def test_none_returns_empty(self):
        assert _payload_items(None) == []

    def test_empty_list_returns_empty(self):
        assert _payload_items([]) == []

    def test_empty_dict_returns_empty(self):
        assert _payload_items({}) == []


# ── _extract_model_ids ────────────────────────────────────────────────────────

class TestExtractModelIds:
    def test_extracts_ids_from_list(self):
        payload = [{"id": "gpt-5"}, {"id": "gpt-4"}]
        assert _extract_model_ids(payload) == ["gpt-5", "gpt-4"]

    def test_items_without_id_skipped(self):
        payload = [{"id": "gpt-5"}, {"name": "no-id"}]
        assert _extract_model_ids(payload) == ["gpt-5"]

    def test_items_with_empty_id_skipped(self):
        payload = [{"id": ""}, {"id": "gpt-5"}]
        assert _extract_model_ids(payload) == ["gpt-5"]

    def test_extracts_from_data_dict(self):
        payload = {"data": [{"id": "m1"}, {"id": "m2"}]}
        assert _extract_model_ids(payload) == ["m1", "m2"]

    def test_empty_payload_returns_empty(self):
        assert _extract_model_ids([]) == []


# ── _copilot_catalog_item_is_text_model ───────────────────────────────────────

class TestCopilotCatalogItemIsTextModel:
    def test_basic_valid_item(self):
        assert _copilot_catalog_item_is_text_model({"id": "gpt-4o"}) is True

    def test_no_id_returns_false(self):
        assert _copilot_catalog_item_is_text_model({}) is False

    def test_empty_id_returns_false(self):
        assert _copilot_catalog_item_is_text_model({"id": ""}) is False

    def test_model_picker_disabled_returns_false(self):
        item = {"id": "gpt-4o", "model_picker_enabled": False}
        assert _copilot_catalog_item_is_text_model(item) is False

    def test_model_picker_true_allowed(self):
        item = {"id": "gpt-4o", "model_picker_enabled": True}
        assert _copilot_catalog_item_is_text_model(item) is True

    def test_non_chat_capability_type_returns_false(self):
        item = {"id": "dalle-3", "capabilities": {"type": "image"}}
        assert _copilot_catalog_item_is_text_model(item) is False

    def test_chat_capability_type_allowed(self):
        item = {"id": "gpt-4o", "capabilities": {"type": "chat"}}
        assert _copilot_catalog_item_is_text_model(item) is True

    def test_unsupported_endpoint_only_returns_false(self):
        item = {
            "id": "image-model",
            "supported_endpoints": ["/v1/images/generations"],
        }
        assert _copilot_catalog_item_is_text_model(item) is False

    def test_chat_completions_endpoint_allowed(self):
        item = {
            "id": "gpt-4o",
            "supported_endpoints": ["/chat/completions"],
        }
        assert _copilot_catalog_item_is_text_model(item) is True

    def test_responses_endpoint_allowed(self):
        item = {
            "id": "gpt-5",
            "supported_endpoints": ["/responses"],
        }
        assert _copilot_catalog_item_is_text_model(item) is True


# ── _is_github_models_base_url ────────────────────────────────────────────────

class TestIsGithubModelsBaseUrl:
    def test_copilot_base_url_matches(self):
        assert _is_github_models_base_url("https://api.githubcopilot.com") is True

    def test_copilot_base_url_with_path(self):
        assert _is_github_models_base_url("https://api.githubcopilot.com/v1") is True

    def test_github_ai_inference_url_matches(self):
        assert _is_github_models_base_url("https://models.github.ai/inference") is True

    def test_other_url_returns_false(self):
        assert _is_github_models_base_url("https://api.openai.com/v1") is False

    def test_none_returns_false(self):
        assert _is_github_models_base_url(None) is False

    def test_empty_returns_false(self):
        assert _is_github_models_base_url("") is False

    def test_trailing_slash_stripped(self):
        assert _is_github_models_base_url("https://api.githubcopilot.com/") is True
