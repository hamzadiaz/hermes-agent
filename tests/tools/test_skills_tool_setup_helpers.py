"""Tests for pure helper functions in tools/skills_tool.py.

Covers:
- _normalize_prerequisite_values(): coerce various prerequisite values to list of strings
- _normalize_setup_metadata(): parse and normalize skill setup metadata dict
"""

import pytest

from tools.skills_tool import _normalize_prerequisite_values, _normalize_setup_metadata


# ── _normalize_prerequisite_values ───────────────────────────────────────────

class TestNormalizePrerequisiteValues:
    def test_none_returns_empty(self):
        assert _normalize_prerequisite_values(None) == []

    def test_empty_list_returns_empty(self):
        assert _normalize_prerequisite_values([]) == []

    def test_string_converted_to_list(self):
        assert _normalize_prerequisite_values("OPENAI_API_KEY") == ["OPENAI_API_KEY"]

    def test_list_of_strings_returned(self):
        result = _normalize_prerequisite_values(["VAR1", "VAR2"])
        assert result == ["VAR1", "VAR2"]

    def test_empty_string_items_filtered(self):
        result = _normalize_prerequisite_values(["valid", "  ", ""])
        assert result == ["valid"]

    def test_non_string_items_coerced_to_str(self):
        result = _normalize_prerequisite_values([42, "hello"])
        assert "42" in result
        assert "hello" in result

    def test_false_value_returns_empty(self):
        assert _normalize_prerequisite_values(False) == []

    def test_zero_returns_empty(self):
        assert _normalize_prerequisite_values(0) == []


# ── _normalize_setup_metadata ─────────────────────────────────────────────────

class TestNormalizeSetupMetadata:
    def test_no_setup_key_returns_defaults(self):
        result = _normalize_setup_metadata({})
        assert result["help"] is None
        assert result["collect_secrets"] == []

    def test_non_dict_setup_returns_defaults(self):
        result = _normalize_setup_metadata({"setup": "string"})
        assert result["help"] is None
        assert result["collect_secrets"] == []

    def test_help_text_included(self):
        result = _normalize_setup_metadata({"setup": {"help": "Run this first"}})
        assert result["help"] == "Run this first"

    def test_whitespace_only_help_returns_none(self):
        result = _normalize_setup_metadata({"setup": {"help": "   "}})
        assert result["help"] is None

    def test_collect_secrets_list_processed(self):
        setup = {
            "setup": {
                "collect_secrets": [
                    {"env_var": "API_KEY", "prompt": "Enter API key"}
                ]
            }
        }
        result = _normalize_setup_metadata(setup)
        secrets = result["collect_secrets"]
        assert len(secrets) == 1
        assert secrets[0]["env_var"] == "API_KEY"
        assert secrets[0]["prompt"] == "Enter API key"

    def test_collect_secrets_dict_wrapped_in_list(self):
        # Single dict (not list) should be wrapped
        setup = {
            "setup": {
                "collect_secrets": {"env_var": "KEY", "prompt": "Enter"}
            }
        }
        result = _normalize_setup_metadata(setup)
        assert len(result["collect_secrets"]) == 1

    def test_secret_defaults_to_true(self):
        setup = {"setup": {"collect_secrets": [{"env_var": "KEY"}]}}
        result = _normalize_setup_metadata(setup)
        assert result["collect_secrets"][0]["secret"] is True

    def test_secret_false_respected(self):
        setup = {"setup": {"collect_secrets": [{"env_var": "KEY", "secret": False}]}}
        result = _normalize_setup_metadata(setup)
        assert result["collect_secrets"][0]["secret"] is False

    def test_missing_env_var_skipped(self):
        setup = {"setup": {"collect_secrets": [{"prompt": "No env var here"}]}}
        result = _normalize_setup_metadata(setup)
        assert result["collect_secrets"] == []

    def test_provider_url_included_when_present(self):
        setup = {
            "setup": {
                "collect_secrets": [
                    {"env_var": "KEY", "provider_url": "https://api.example.com"}
                ]
            }
        }
        result = _normalize_setup_metadata(setup)
        assert result["collect_secrets"][0]["provider_url"] == "https://api.example.com"

    def test_provider_url_absent_when_not_provided(self):
        setup = {"setup": {"collect_secrets": [{"env_var": "KEY"}]}}
        result = _normalize_setup_metadata(setup)
        assert "provider_url" not in result["collect_secrets"][0]

    def test_default_prompt_used_when_missing(self):
        setup = {"setup": {"collect_secrets": [{"env_var": "MY_VAR"}]}}
        result = _normalize_setup_metadata(setup)
        prompt = result["collect_secrets"][0]["prompt"]
        assert "MY_VAR" in prompt
