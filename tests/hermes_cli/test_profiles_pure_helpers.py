"""Tests for pure helper functions in hermes_cli/profiles.py.

Covers:
- _normalize_profile_archive_parts(): validate and normalize archive member paths
"""

import pytest

from hermes_cli.profiles import _normalize_profile_archive_parts


# ── _normalize_profile_archive_parts ─────────────────────────────────────────

class TestNormalizeProfileArchiveParts:
    def test_simple_filename_returns_single_element(self):
        assert _normalize_profile_archive_parts("config.yaml") == ["config.yaml"]

    def test_nested_path_returns_parts(self):
        assert _normalize_profile_archive_parts("subdir/config.yaml") == ["subdir", "config.yaml"]

    def test_dotslash_prefix_stripped(self):
        assert _normalize_profile_archive_parts("./config.yaml") == ["config.yaml"]

    def test_dotslash_nested_stripped(self):
        assert _normalize_profile_archive_parts("./subdir/file.txt") == ["subdir", "file.txt"]

    def test_windows_backslash_converted(self):
        assert _normalize_profile_archive_parts("a\\b\\c") == ["a", "b", "c"]

    def test_absolute_path_raises(self):
        with pytest.raises(ValueError, match="Unsafe"):
            _normalize_profile_archive_parts("/absolute/config.yaml")

    def test_dotdot_traversal_raises(self):
        with pytest.raises(ValueError, match="Unsafe"):
            _normalize_profile_archive_parts("../escape/config.yaml")

    def test_dotdot_in_middle_raises(self):
        with pytest.raises(ValueError, match="Unsafe"):
            _normalize_profile_archive_parts("a/../b/config.yaml")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Unsafe"):
            _normalize_profile_archive_parts("")

    def test_dot_only_raises(self):
        with pytest.raises(ValueError, match="Unsafe"):
            _normalize_profile_archive_parts(".")

    def test_windows_absolute_drive_raises(self):
        with pytest.raises(ValueError, match="Unsafe"):
            _normalize_profile_archive_parts("C:\\config.yaml")

    def test_deep_nested_path_returned(self):
        result = _normalize_profile_archive_parts("a/b/c/d.txt")
        assert result == ["a", "b", "c", "d.txt"]

    def test_dotslash_only_raises(self):
        # "./." → parts after filtering = [] → raises
        with pytest.raises(ValueError, match="Unsafe"):
            _normalize_profile_archive_parts("./.")
