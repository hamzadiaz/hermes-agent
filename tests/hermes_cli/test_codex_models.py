"""Tests for hermes_cli/codex_models.py.

Covers the pure logic in:
- _add_forward_compat_models(): synthetic model injection
- _read_cache_models(): JSON parsing, priority sorting, filtering
- _read_default_model(): TOML config parsing
"""

import json
import pytest
from pathlib import Path

from hermes_cli.codex_models import (
    _add_forward_compat_models,
    _read_cache_models,
    _read_default_model,
    DEFAULT_CODEX_MODELS,
)


# ── _add_forward_compat_models ─────────────────────────────────────────────────

class TestAddForwardCompatModels:
    """hermes_cli/codex_models.py — _add_forward_compat_models()"""

    def test_empty_list_returns_empty(self):
        assert _add_forward_compat_models([]) == []

    def test_no_template_models_no_change(self):
        """Models with no template matches pass through unchanged."""
        models = ["some-random-model"]
        result = _add_forward_compat_models(models)
        assert result == ["some-random-model"]

    def test_older_model_triggers_synthetic_newer(self):
        """gpt-5.2-codex present → gpt-5.4-mini (and gpt-5.4) should be added."""
        result = _add_forward_compat_models(["gpt-5.2-codex"])
        assert "gpt-5.4-mini" in result
        assert "gpt-5.4" in result
        # Original model preserved
        assert "gpt-5.2-codex" in result

    def test_newer_model_already_present_not_duplicated(self):
        """If the synthetic model is already in the list, don't add it again."""
        result = _add_forward_compat_models(["gpt-5.4-mini", "gpt-5.2-codex"])
        assert result.count("gpt-5.4-mini") == 1

    def test_spark_model_added_when_template_present(self):
        """gpt-5.3-codex present → gpt-5.3-codex-spark should be added."""
        result = _add_forward_compat_models(["gpt-5.3-codex"])
        assert "gpt-5.3-codex-spark" in result

    def test_deduplicated_input(self):
        """Duplicate models in input are deduplicated."""
        result = _add_forward_compat_models(["gpt-5.2-codex", "gpt-5.2-codex"])
        assert result.count("gpt-5.2-codex") == 1

    def test_order_preserved_originals_before_synthetic(self):
        """Original models appear before any synthetic additions."""
        result = _add_forward_compat_models(["gpt-5.2-codex"])
        # gpt-5.2-codex should come before gpt-5.4-mini in the result
        idx_original = result.index("gpt-5.2-codex")
        idx_synthetic = result.index("gpt-5.4-mini")
        assert idx_original < idx_synthetic

    def test_full_discovery_list_no_synthetics_needed(self):
        """When all known models are present, no extra synthetics added."""
        full_list = ["gpt-5.4-mini", "gpt-5.4", "gpt-5.3-codex",
                     "gpt-5.3-codex-spark", "gpt-5.2-codex"]
        result = _add_forward_compat_models(full_list)
        # All present, nothing new injected
        for model in full_list:
            assert result.count(model) == 1


# ── _read_cache_models ─────────────────────────────────────────────────────────

class TestReadCacheModels:
    """hermes_cli/codex_models.py — _read_cache_models()"""

    def _write_cache(self, tmp_path: Path, models: list) -> Path:
        cache = tmp_path / "models_cache.json"
        cache.write_text(json.dumps({"models": models}), encoding="utf-8")
        return tmp_path

    def test_missing_cache_file_returns_empty(self, tmp_path):
        result = _read_cache_models(tmp_path)
        assert result == []

    def test_invalid_json_returns_empty(self, tmp_path):
        (tmp_path / "models_cache.json").write_text("not json")
        assert _read_cache_models(tmp_path) == []

    def test_basic_model_list(self, tmp_path):
        codex_home = self._write_cache(tmp_path, [
            {"slug": "gpt-5.4", "priority": 1},
        ])
        result = _read_cache_models(codex_home)
        assert result == ["gpt-5.4"]

    def test_sorted_by_priority(self, tmp_path):
        codex_home = self._write_cache(tmp_path, [
            {"slug": "gpt-5.2", "priority": 10},
            {"slug": "gpt-5.4", "priority": 1},
            {"slug": "gpt-5.3", "priority": 5},
        ])
        result = _read_cache_models(codex_home)
        assert result == ["gpt-5.4", "gpt-5.3", "gpt-5.2"]

    def test_hidden_models_excluded(self, tmp_path):
        codex_home = self._write_cache(tmp_path, [
            {"slug": "gpt-public", "priority": 1},
            {"slug": "gpt-hidden", "priority": 2, "visibility": "hidden"},
            {"slug": "gpt-hide", "priority": 3, "visibility": "hide"},
        ])
        result = _read_cache_models(codex_home)
        assert "gpt-hidden" not in result
        assert "gpt-hide" not in result
        assert "gpt-public" in result

    def test_api_unsupported_models_excluded(self, tmp_path):
        codex_home = self._write_cache(tmp_path, [
            {"slug": "gpt-api", "priority": 1},
            {"slug": "gpt-no-api", "priority": 2, "supported_in_api": False},
        ])
        result = _read_cache_models(codex_home)
        assert "gpt-no-api" not in result
        assert "gpt-api" in result

    def test_missing_slug_excluded(self, tmp_path):
        codex_home = self._write_cache(tmp_path, [
            {"priority": 1},  # No slug
            {"slug": "gpt-valid", "priority": 2},
        ])
        result = _read_cache_models(codex_home)
        assert result == ["gpt-valid"]

    def test_empty_slug_excluded(self, tmp_path):
        codex_home = self._write_cache(tmp_path, [
            {"slug": "  ", "priority": 1},
            {"slug": "gpt-valid", "priority": 2},
        ])
        result = _read_cache_models(codex_home)
        assert result == ["gpt-valid"]

    def test_non_dict_items_skipped(self, tmp_path):
        codex_home = self._write_cache(tmp_path, [
            "not-a-dict",
            {"slug": "gpt-valid", "priority": 1},
            None,
        ])
        result = _read_cache_models(codex_home)
        assert result == ["gpt-valid"]

    def test_deduplicates_slugs(self, tmp_path):
        """Duplicate slugs after sorting are deduplicated."""
        codex_home = self._write_cache(tmp_path, [
            {"slug": "gpt-dup", "priority": 1},
            {"slug": "gpt-dup", "priority": 5},
        ])
        result = _read_cache_models(codex_home)
        assert result.count("gpt-dup") == 1

    def test_non_list_models_returns_empty(self, tmp_path):
        """When 'models' key is not a list, returns empty."""
        cache = tmp_path / "models_cache.json"
        cache.write_text(json.dumps({"models": "not-a-list"}))
        assert _read_cache_models(tmp_path) == []

    def test_missing_priority_uses_high_default(self, tmp_path):
        """Models missing priority get sorted to end (high rank number)."""
        codex_home = self._write_cache(tmp_path, [
            {"slug": "gpt-priority", "priority": 1},
            {"slug": "gpt-no-priority"},
        ])
        result = _read_cache_models(codex_home)
        assert result[0] == "gpt-priority"
        assert result[1] == "gpt-no-priority"


# ── _read_default_model ────────────────────────────────────────────────────────

class TestReadDefaultModel:
    """hermes_cli/codex_models.py — _read_default_model()"""

    def test_missing_config_returns_none(self, tmp_path):
        assert _read_default_model(tmp_path) is None

    def test_valid_config_returns_model(self, tmp_path):
        config = tmp_path / "config.toml"
        config.write_text('model = "gpt-5.4"\n')
        result = _read_default_model(tmp_path)
        assert result == "gpt-5.4"

    def test_model_stripped_of_whitespace(self, tmp_path):
        config = tmp_path / "config.toml"
        config.write_text('model = "  gpt-5.4  "\n')
        result = _read_default_model(tmp_path)
        assert result == "gpt-5.4"

    def test_empty_model_returns_none(self, tmp_path):
        config = tmp_path / "config.toml"
        config.write_text('model = ""\n')
        assert _read_default_model(tmp_path) is None

    def test_whitespace_only_model_returns_none(self, tmp_path):
        config = tmp_path / "config.toml"
        config.write_text('model = "   "\n')
        assert _read_default_model(tmp_path) is None

    def test_invalid_toml_returns_none(self, tmp_path):
        config = tmp_path / "config.toml"
        config.write_text("not valid toml ::::")
        assert _read_default_model(tmp_path) is None

    def test_no_model_key_returns_none(self, tmp_path):
        config = tmp_path / "config.toml"
        config.write_text('[other]\nkey = "value"\n')
        assert _read_default_model(tmp_path) is None
