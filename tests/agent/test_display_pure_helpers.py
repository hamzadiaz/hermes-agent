"""Tests for pure helper functions in agent/display.py.

Covers:
- _oneline(): collapse whitespace to single spaces
- _result_succeeded(): detect whether a tool result JSON represents success
- _split_unified_diff_sections(): split unified diff into per-file sections
- _detect_tool_failure(): detect terminal exit codes and generic error markers
- _osc8_link(): produce OSC 8 terminal hyperlink escape sequence
"""

import json
import pytest

from agent.display import (
    _oneline,
    _result_succeeded,
    _split_unified_diff_sections,
    _detect_tool_failure,
    _osc8_link,
)


# ── _oneline ──────────────────────────────────────────────────────────────────

class TestOneline:
    def test_plain_text_unchanged(self):
        assert _oneline("hello world") == "hello world"

    def test_newlines_collapsed(self):
        assert _oneline("hello\nworld") == "hello world"

    def test_tabs_collapsed(self):
        assert _oneline("hello\tworld") == "hello world"

    def test_multiple_spaces_collapsed(self):
        assert _oneline("hello   world") == "hello world"

    def test_leading_trailing_stripped(self):
        assert _oneline("  hello  ") == "hello"

    def test_empty_string(self):
        assert _oneline("") == ""

    def test_mixed_whitespace(self):
        assert _oneline("  a\n  b\t  c  ") == "a b c"


# ── _result_succeeded ─────────────────────────────────────────────────────────

class TestResultSucceeded:
    def test_none_returns_false(self):
        assert _result_succeeded(None) is False

    def test_empty_string_returns_false(self):
        assert _result_succeeded("") is False

    def test_success_true_returns_true(self):
        result = json.dumps({"success": True})
        assert _result_succeeded(result) is True

    def test_success_false_returns_false(self):
        result = json.dumps({"success": False})
        assert _result_succeeded(result) is False

    def test_no_success_key_but_no_error_returns_true(self):
        # A dict without "error" and without "success" → conservatively true
        result = json.dumps({"output": "done"})
        assert _result_succeeded(result) is True

    def test_error_key_present_returns_false(self):
        result = json.dumps({"error": "something went wrong"})
        assert _result_succeeded(result) is False

    def test_non_json_string_returns_false(self):
        assert _result_succeeded("not json") is False

    def test_json_array_returns_false(self):
        assert _result_succeeded("[1, 2, 3]") is False

    def test_empty_dict_returns_true(self):
        # {} has no "error", no "success" → True (success unknown = not a failure)
        assert _result_succeeded("{}") is True


# ── _split_unified_diff_sections ──────────────────────────────────────────────

class TestSplitUnifiedDiffSections:
    def test_empty_string_returns_empty(self):
        assert _split_unified_diff_sections("") == []

    def test_single_file_diff_returned_as_one_section(self):
        diff = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new"
        sections = _split_unified_diff_sections(diff)
        assert len(sections) == 1
        assert "file.py" in sections[0]

    def test_two_file_diff_split_into_two_sections(self):
        diff = (
            "--- a/file1.py\n+++ b/file1.py\n@@ -1 +1 @@\n-old\n+new\n"
            "--- a/file2.py\n+++ b/file2.py\n@@ -1 +1 @@\n-x\n+y"
        )
        sections = _split_unified_diff_sections(diff)
        assert len(sections) == 2

    def test_section_content_preserved(self):
        diff = "--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-before\n+after"
        sections = _split_unified_diff_sections(diff)
        assert "before" in sections[0]
        assert "after" in sections[0]

    def test_no_file_headers_returns_single_section(self):
        diff = "Some text\nwithout file headers"
        sections = _split_unified_diff_sections(diff)
        assert len(sections) == 1


# ── _detect_tool_failure ──────────────────────────────────────────────────────

class TestDetectToolFailure:
    def test_none_result_returns_no_failure(self):
        is_fail, suffix = _detect_tool_failure("terminal", None)
        assert is_fail is False
        assert suffix == ""

    def test_terminal_exit_code_zero_not_failure(self):
        result = json.dumps({"exit_code": 0, "output": "ok"})
        is_fail, suffix = _detect_tool_failure("terminal", result)
        assert is_fail is False

    def test_terminal_exit_code_nonzero_is_failure(self):
        result = json.dumps({"exit_code": 1, "output": "error"})
        is_fail, suffix = _detect_tool_failure("terminal", result)
        assert is_fail is True
        assert "exit 1" in suffix

    def test_terminal_exit_code_in_suffix(self):
        result = json.dumps({"exit_code": 127})
        is_fail, suffix = _detect_tool_failure("terminal", result)
        assert "127" in suffix

    def test_memory_full_error_detected(self):
        result = json.dumps({"success": False, "error": "exceed the limit of storage"})
        is_fail, suffix = _detect_tool_failure("memory", result)
        assert is_fail is True
        assert "full" in suffix

    def test_generic_error_key_in_result_detected(self):
        result = '{"error": "something broke"}'
        is_fail, suffix = _detect_tool_failure("bash", result)
        assert is_fail is True
        assert "error" in suffix

    def test_result_starting_with_error_detected(self):
        is_fail, suffix = _detect_tool_failure("read_file", "Error: file not found")
        assert is_fail is True

    def test_clean_result_not_failure(self):
        result = json.dumps({"output": "success"})
        is_fail, suffix = _detect_tool_failure("bash", result)
        assert is_fail is False
        assert suffix == ""

    def test_terminal_non_json_result_not_failure(self):
        is_fail, suffix = _detect_tool_failure("terminal", "plain text output")
        assert is_fail is False


# ── _osc8_link ────────────────────────────────────────────────────────────────

class TestOsc8Link:
    def test_produces_escape_sequences(self):
        result = _osc8_link("https://example.com", "click me")
        assert "\033]8;;" in result
        assert "click me" in result

    def test_url_embedded(self):
        result = _osc8_link("https://example.com", "link")
        assert "https://example.com" in result

    def test_text_embedded(self):
        result = _osc8_link("https://example.com", "visible text")
        assert "visible text" in result

    def test_closing_sequence_present(self):
        result = _osc8_link("https://example.com", "text")
        # Should contain the closing OSC 8 sequence (empty URL)
        assert result.count("\033]8;;") == 2
