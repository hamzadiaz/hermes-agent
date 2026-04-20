"""Tests for pure helper functions in hermes_cli/gateway.py.

Covers:
- _service_scope_label(): return "system" or "user" based on bool flag
- _normalize_service_definition(): strip trailing whitespace and leading/trailing blank lines
- _build_user_local_paths(): filter local bin dirs to those that exist and aren't already listed
"""

import pytest
from pathlib import Path

from hermes_cli.gateway import (
    _service_scope_label,
    _normalize_service_definition,
    _build_user_local_paths,
)


# ── _service_scope_label ──────────────────────────────────────────────────────

class TestServiceScopeLabel:
    def test_system_true_returns_system(self):
        assert _service_scope_label(system=True) == "system"

    def test_system_false_returns_user(self):
        assert _service_scope_label(system=False) == "user"

    def test_default_is_user(self):
        assert _service_scope_label() == "user"


# ── _normalize_service_definition ────────────────────────────────────────────

class TestNormalizeServiceDefinition:
    def test_trailing_whitespace_stripped(self):
        result = _normalize_service_definition("line1   \nline2  ")
        assert result == "line1\nline2"

    def test_leading_and_trailing_blank_lines_removed(self):
        result = _normalize_service_definition("\n\nline1\nline2\n\n")
        assert result == "line1\nline2"

    def test_empty_string_returns_empty(self):
        assert _normalize_service_definition("") == ""

    def test_single_line_stripped(self):
        assert _normalize_service_definition("  hello  ") == "hello"

    def test_internal_blank_lines_preserved(self):
        result = _normalize_service_definition("a\n\nb")
        assert result == "a\n\nb"

    def test_mixed_trailing_whitespace_types(self):
        result = _normalize_service_definition("a \t \nb")
        assert result == "a\nb"


# ── _build_user_local_paths ───────────────────────────────────────────────────

class TestBuildUserLocalPaths:
    def test_existing_paths_included(self, tmp_path):
        local_bin = tmp_path / ".local" / "bin"
        local_bin.mkdir(parents=True)
        result = _build_user_local_paths(tmp_path, [])
        assert str(local_bin) in result

    def test_already_listed_paths_excluded(self, tmp_path):
        local_bin = tmp_path / ".local" / "bin"
        local_bin.mkdir(parents=True)
        result = _build_user_local_paths(tmp_path, [str(local_bin)])
        assert str(local_bin) not in result

    def test_nonexistent_dirs_excluded(self, tmp_path):
        # No dirs created → none should be returned
        result = _build_user_local_paths(tmp_path, [])
        assert result == []

    def test_multiple_existing_dirs_all_returned(self, tmp_path):
        bins = [
            tmp_path / ".local" / "bin",
            tmp_path / ".cargo" / "bin",
        ]
        for b in bins:
            b.mkdir(parents=True)
        result = _build_user_local_paths(tmp_path, [])
        assert len(result) == 2

    def test_returns_string_paths(self, tmp_path):
        local_bin = tmp_path / ".local" / "bin"
        local_bin.mkdir(parents=True)
        result = _build_user_local_paths(tmp_path, [])
        assert all(isinstance(p, str) for p in result)
