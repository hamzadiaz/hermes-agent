"""Tests for pure helper functions in batch_runner.py.

Covers:
- _normalize_tool_stats(): fill missing tools with zero-count defaults
- _normalize_tool_error_counts(): fill missing tools with zero error counts
- _extract_tool_stats(): parse message history into per-tool success/failure counts
- _extract_reasoning_stats(): count assistant turns with/without reasoning
"""

import json
import pytest

from batch_runner import (
    _normalize_tool_stats,
    _normalize_tool_error_counts,
    _extract_tool_stats,
    _extract_reasoning_stats,
    ALL_POSSIBLE_TOOLS,
    DEFAULT_TOOL_STATS,
)


# ── _normalize_tool_stats ─────────────────────────────────────────────────────

class TestNormalizeToolStats:
    def test_all_possible_tools_present_in_output(self):
        result = _normalize_tool_stats({})
        for tool in ALL_POSSIBLE_TOOLS:
            assert tool in result

    def test_existing_stats_preserved(self):
        if not ALL_POSSIBLE_TOOLS:
            pytest.skip("No tools defined")
        tool = next(iter(ALL_POSSIBLE_TOOLS))
        stats = {"count": 5, "success": 4, "failure": 1}
        result = _normalize_tool_stats({tool: stats})
        assert result[tool] == stats

    def test_missing_tools_get_zero_defaults(self):
        result = _normalize_tool_stats({})
        for tool in ALL_POSSIBLE_TOOLS:
            assert result[tool] == DEFAULT_TOOL_STATS

    def test_unknown_tool_also_included(self):
        result = _normalize_tool_stats({"unknown_custom_tool": {"count": 1, "success": 1, "failure": 0}})
        assert "unknown_custom_tool" in result

    def test_stats_are_copies_not_references(self):
        if not ALL_POSSIBLE_TOOLS:
            pytest.skip("No tools defined")
        tool = next(iter(ALL_POSSIBLE_TOOLS))
        original = {"count": 2, "success": 2, "failure": 0}
        result = _normalize_tool_stats({tool: original})
        result[tool]["count"] = 99
        assert original["count"] == 2  # original not mutated


# ── _normalize_tool_error_counts ──────────────────────────────────────────────

class TestNormalizeToolErrorCounts:
    def test_all_possible_tools_present(self):
        result = _normalize_tool_error_counts({})
        for tool in ALL_POSSIBLE_TOOLS:
            assert tool in result

    def test_missing_tools_default_to_zero(self):
        result = _normalize_tool_error_counts({})
        for tool in ALL_POSSIBLE_TOOLS:
            assert result[tool] == 0

    def test_existing_counts_preserved(self):
        if not ALL_POSSIBLE_TOOLS:
            pytest.skip("No tools defined")
        tool = next(iter(ALL_POSSIBLE_TOOLS))
        result = _normalize_tool_error_counts({tool: 7})
        assert result[tool] == 7

    def test_unknown_tool_included(self):
        result = _normalize_tool_error_counts({"my_new_tool": 3})
        assert result["my_new_tool"] == 3


# ── _extract_tool_stats ───────────────────────────────────────────────────────

def _make_tool_call(name, call_id):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": "{}"}}


def _make_tool_result(call_id, content, role="tool"):
    return {"role": role, "tool_call_id": call_id, "content": content}


class TestExtractToolStats:
    def test_empty_messages_returns_empty(self):
        assert _extract_tool_stats([]) == {}

    def test_single_successful_tool_call(self):
        messages = [
            {"role": "assistant", "tool_calls": [_make_tool_call("bash", "c1")]},
            _make_tool_result("c1", json.dumps({"output": "done"})),
        ]
        result = _extract_tool_stats(messages)
        assert "bash" in result
        assert result["bash"]["count"] == 1
        assert result["bash"]["success"] == 1
        assert result["bash"]["failure"] == 0

    def test_tool_failure_detected_via_error_key(self):
        messages = [
            {"role": "assistant", "tool_calls": [_make_tool_call("bash", "c1")]},
            _make_tool_result("c1", json.dumps({"content": {"error": "command not found"}})),
        ]
        result = _extract_tool_stats(messages)
        assert result["bash"]["failure"] == 1

    def test_tool_failure_detected_via_success_false(self):
        messages = [
            {"role": "assistant", "tool_calls": [_make_tool_call("bash", "c1")]},
            _make_tool_result("c1", json.dumps({"success": False})),
        ]
        result = _extract_tool_stats(messages)
        assert result["bash"]["failure"] == 1

    def test_empty_content_is_failure(self):
        messages = [
            {"role": "assistant", "tool_calls": [_make_tool_call("bash", "c1")]},
            _make_tool_result("c1", ""),
        ]
        result = _extract_tool_stats(messages)
        assert result["bash"]["failure"] == 1

    def test_error_prefix_content_is_failure(self):
        messages = [
            {"role": "assistant", "tool_calls": [_make_tool_call("bash", "c1")]},
            _make_tool_result("c1", "Error: something went wrong"),
        ]
        result = _extract_tool_stats(messages)
        assert result["bash"]["failure"] == 1

    def test_multiple_calls_accumulated(self):
        messages = [
            {"role": "assistant", "tool_calls": [
                _make_tool_call("bash", "c1"),
                _make_tool_call("bash", "c2"),
            ]},
            _make_tool_result("c1", json.dumps({"output": "ok"})),
            _make_tool_result("c2", json.dumps({"output": "ok"})),
        ]
        result = _extract_tool_stats(messages)
        assert result["bash"]["count"] == 2
        assert result["bash"]["success"] == 2

    def test_different_tools_tracked_separately(self):
        messages = [
            {"role": "assistant", "tool_calls": [
                _make_tool_call("bash", "c1"),
                _make_tool_call("web_search", "c2"),
            ]},
            _make_tool_result("c1", json.dumps({"output": "ok"})),
            _make_tool_result("c2", json.dumps({"results": []})),
        ]
        result = _extract_tool_stats(messages)
        assert "bash" in result
        assert "web_search" in result

    def test_non_tool_messages_ignored(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        assert _extract_tool_stats(messages) == {}


# ── _extract_reasoning_stats ──────────────────────────────────────────────────

class TestExtractReasoningStats:
    def test_empty_messages(self):
        result = _extract_reasoning_stats([])
        assert result["total_assistant_turns"] == 0
        assert result["turns_with_reasoning"] == 0
        assert result["turns_without_reasoning"] == 0

    def test_no_reasoning_turns(self):
        messages = [
            {"role": "assistant", "content": "Plain answer"},
            {"role": "assistant", "content": "Another plain answer"},
        ]
        result = _extract_reasoning_stats(messages)
        assert result["total_assistant_turns"] == 2
        assert result["turns_with_reasoning"] == 0
        assert result["turns_without_reasoning"] == 2

    def test_scratchpad_detected(self):
        messages = [
            {"role": "assistant", "content": "<REASONING_SCRATCHPAD>thinking...</REASONING_SCRATCHPAD> answer"},
        ]
        result = _extract_reasoning_stats(messages)
        assert result["turns_with_reasoning"] == 1

    def test_native_reasoning_field_detected(self):
        messages = [
            {"role": "assistant", "content": "answer", "reasoning": "some thought process"},
        ]
        result = _extract_reasoning_stats(messages)
        assert result["turns_with_reasoning"] == 1

    def test_empty_reasoning_field_not_counted(self):
        messages = [
            {"role": "assistant", "content": "answer", "reasoning": ""},
        ]
        result = _extract_reasoning_stats(messages)
        assert result["turns_with_reasoning"] == 0

    def test_non_assistant_messages_ignored(self):
        messages = [
            {"role": "user", "content": "<REASONING_SCRATCHPAD>not assistant</REASONING_SCRATCHPAD>"},
            {"role": "tool", "content": "<REASONING_SCRATCHPAD>tool response</REASONING_SCRATCHPAD>"},
        ]
        result = _extract_reasoning_stats(messages)
        assert result["total_assistant_turns"] == 0

    def test_mixed_reasoning_and_plain(self):
        messages = [
            {"role": "assistant", "content": "<REASONING_SCRATCHPAD>thinking</REASONING_SCRATCHPAD> answer1"},
            {"role": "assistant", "content": "plain answer2"},
            {"role": "assistant", "content": "plain answer3", "reasoning": "some thoughts"},
        ]
        result = _extract_reasoning_stats(messages)
        assert result["total_assistant_turns"] == 3
        assert result["turns_with_reasoning"] == 2
        assert result["turns_without_reasoning"] == 1

    def test_turns_with_plus_without_equals_total(self):
        messages = [
            {"role": "assistant", "content": "<REASONING_SCRATCHPAD>t</REASONING_SCRATCHPAD>a"},
            {"role": "assistant", "content": "b"},
        ]
        result = _extract_reasoning_stats(messages)
        assert result["turns_with_reasoning"] + result["turns_without_reasoning"] == result["total_assistant_turns"]
