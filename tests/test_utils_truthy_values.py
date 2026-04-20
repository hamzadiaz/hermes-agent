"""Tests for shared truthy-value helpers and atomic write utilities."""

import json
from pathlib import Path

import pytest
import yaml

from utils import env_var_enabled, is_truthy_value, atomic_json_write, atomic_yaml_write


def test_is_truthy_value_accepts_common_truthy_strings():
    assert is_truthy_value("true") is True
    assert is_truthy_value(" YES ") is True
    assert is_truthy_value("on") is True
    assert is_truthy_value("1") is True


def test_is_truthy_value_respects_default_for_none():
    assert is_truthy_value(None, default=True) is True
    assert is_truthy_value(None, default=False) is False


def test_is_truthy_value_rejects_falsey_strings():
    assert is_truthy_value("false") is False
    assert is_truthy_value("0") is False
    assert is_truthy_value("off") is False


def test_is_truthy_value_passthrough_for_bool():
    assert is_truthy_value(True) is True
    assert is_truthy_value(False) is False


def test_is_truthy_value_non_string_non_bool_uses_bool():
    assert is_truthy_value(1) is True
    assert is_truthy_value(0) is False
    assert is_truthy_value([]) is False
    assert is_truthy_value([1]) is True


def test_env_var_enabled_uses_shared_truthy_rules(monkeypatch):
    monkeypatch.setenv("HERMES_TEST_BOOL", "YeS")
    assert env_var_enabled("HERMES_TEST_BOOL") is True

    monkeypatch.setenv("HERMES_TEST_BOOL", "no")
    assert env_var_enabled("HERMES_TEST_BOOL") is False


def test_env_var_enabled_missing_var_returns_false(monkeypatch):
    monkeypatch.delenv("HERMES_NONEXISTENT_VAR", raising=False)
    assert env_var_enabled("HERMES_NONEXISTENT_VAR") is False


# ── atomic_json_write ─────────────────────────────────────────────────────────

class TestAtomicJsonWrite:
    def test_writes_valid_json(self, tmp_path):
        p = tmp_path / "data.json"
        atomic_json_write(p, {"key": "value", "num": 42})
        result = json.loads(p.read_text())
        assert result == {"key": "value", "num": 42}

    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "nested" / "deeply" / "data.json"
        atomic_json_write(p, {"a": 1})
        assert p.exists()

    def test_overwrites_existing_file(self, tmp_path):
        p = tmp_path / "data.json"
        atomic_json_write(p, {"v": 1})
        atomic_json_write(p, {"v": 2})
        assert json.loads(p.read_text())["v"] == 2

    def test_indentation_applied(self, tmp_path):
        p = tmp_path / "data.json"
        atomic_json_write(p, {"a": 1}, indent=4)
        content = p.read_text()
        assert "    " in content  # 4-space indent

    def test_non_ascii_preserved(self, tmp_path):
        p = tmp_path / "data.json"
        atomic_json_write(p, {"greeting": "héllo wörld"})
        result = json.loads(p.read_text())
        assert result["greeting"] == "héllo wörld"


# ── atomic_yaml_write ─────────────────────────────────────────────────────────

class TestAtomicYamlWrite:
    def test_writes_valid_yaml(self, tmp_path):
        p = tmp_path / "config.yaml"
        atomic_yaml_write(p, {"key": "value"})
        result = yaml.safe_load(p.read_text())
        assert result == {"key": "value"}

    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "sub" / "config.yaml"
        atomic_yaml_write(p, {"a": 1})
        assert p.exists()

    def test_extra_content_appended(self, tmp_path):
        p = tmp_path / "config.yaml"
        atomic_yaml_write(p, {"a": 1}, extra_content="# extra comment\n")
        content = p.read_text()
        assert "# extra comment" in content

    def test_overwrites_existing_file(self, tmp_path):
        p = tmp_path / "config.yaml"
        atomic_yaml_write(p, {"v": 1})
        atomic_yaml_write(p, {"v": 2})
        assert yaml.safe_load(p.read_text())["v"] == 2
