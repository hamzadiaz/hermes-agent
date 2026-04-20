"""Tests for pure helper functions in tools/approval.py.

Covers:
- _legacy_pattern_key(): reproduce old regex-derived approval key
- _normalize_approval_mode(): normalize YAML/config mode values
- _format_tirith_description(): build human-readable tirith findings summary
"""

import pytest

from tools.approval import (
    _format_tirith_description,
    _legacy_pattern_key,
    _normalize_approval_mode,
)


# ── _legacy_pattern_key ───────────────────────────────────────────────────────

class TestLegacyPatternKey:
    def test_pattern_with_word_boundary_returns_suffix(self):
        # r'\b' in pattern → return the part after the first \b
        result = _legacy_pattern_key(r"rm\b -rf")
        assert result == " -rf"

    def test_pattern_without_word_boundary_returns_first_20_chars(self):
        result = _legacy_pattern_key("somepattern")
        assert result == "somepattern"

    def test_long_pattern_without_word_boundary_truncated_to_20(self):
        pattern = "a" * 30
        result = _legacy_pattern_key(pattern)
        assert len(result) == 20
        assert result == "a" * 20

    def test_exactly_20_chars_returned_as_is(self):
        pattern = "b" * 20
        assert _legacy_pattern_key(pattern) == pattern

    def test_empty_pattern_returns_empty(self):
        result = _legacy_pattern_key("")
        assert result == ""

    def test_word_boundary_at_start(self):
        # \b at index 0 → suffix after \b is the rest
        result = _legacy_pattern_key(r"\bsudo")
        assert result == "sudo"


# ── _normalize_approval_mode ──────────────────────────────────────────────────

class TestNormalizeApprovalMode:
    def test_false_returns_off(self):
        # YAML 1.1 parses bare 'off' as False
        assert _normalize_approval_mode(False) == "off"

    def test_true_returns_manual(self):
        # YAML 1.1 parses bare 'on' as True → conservative fallback
        assert _normalize_approval_mode(True) == "manual"

    def test_string_smart_returned_as_is(self):
        assert _normalize_approval_mode("smart") == "smart"

    def test_string_off_returned_lowercased(self):
        assert _normalize_approval_mode("OFF") == "off"

    def test_string_manual_returned_lowercased(self):
        assert _normalize_approval_mode("MANUAL") == "manual"

    def test_string_with_whitespace_stripped(self):
        assert _normalize_approval_mode("  smart  ") == "smart"

    def test_empty_string_returns_manual(self):
        assert _normalize_approval_mode("") == "manual"

    def test_whitespace_only_returns_manual(self):
        assert _normalize_approval_mode("   ") == "manual"

    def test_integer_returns_manual(self):
        assert _normalize_approval_mode(42) == "manual"

    def test_none_returns_manual(self):
        assert _normalize_approval_mode(None) == "manual"


# ── _format_tirith_description ────────────────────────────────────────────────

class TestFormatTirithDescription:
    def test_empty_findings_uses_summary(self):
        result = _format_tirith_description({"findings": [], "summary": "no issues"})
        assert "no issues" in result

    def test_no_findings_key_uses_summary(self):
        result = _format_tirith_description({"summary": "clean scan"})
        assert "clean scan" in result

    def test_none_findings_uses_summary(self):
        result = _format_tirith_description({"findings": None, "summary": "ok"})
        assert "ok" in result

    def test_missing_everything_uses_default_summary(self):
        result = _format_tirith_description({})
        assert "security issue detected" in result

    def test_single_finding_with_all_fields(self):
        findings = [{"severity": "HIGH", "title": "RCE", "description": "remote code exec"}]
        result = _format_tirith_description({"findings": findings})
        assert "HIGH" in result
        assert "RCE" in result
        assert "remote code exec" in result

    def test_finding_with_title_no_description(self):
        findings = [{"severity": "LOW", "title": "Info leak"}]
        result = _format_tirith_description({"findings": findings})
        assert "Info leak" in result

    def test_finding_without_severity(self):
        findings = [{"title": "Overflow", "description": "buffer overflow"}]
        result = _format_tirith_description({"findings": findings})
        assert "Overflow" in result
        assert "buffer overflow" in result
        assert "[]" not in result  # no empty severity brackets

    def test_multiple_findings_joined_with_semicolon(self):
        findings = [
            {"severity": "HIGH", "title": "A", "description": "a desc"},
            {"severity": "LOW", "title": "B", "description": "b desc"},
        ]
        result = _format_tirith_description({"findings": findings})
        assert ";" in result
        assert "A" in result
        assert "B" in result

    def test_findings_with_no_title_fall_through_to_summary(self):
        # findings present but all have no title → parts empty → falls back to summary
        findings = [{"severity": "HIGH", "description": "no title here"}]
        result = _format_tirith_description({"findings": findings, "summary": "fallback"})
        # no title means nothing added to parts; summary should be used
        assert "Security scan" in result

    def test_result_starts_with_security_scan(self):
        findings = [{"severity": "MED", "title": "XSS", "description": "cross-site"}]
        result = _format_tirith_description({"findings": findings})
        assert result.startswith("Security scan")
