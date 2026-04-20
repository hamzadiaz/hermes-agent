"""Tests for pure helper functions in agent/litert_lm_client.py.

Covers:
- _render_message_content(): normalize content field to plain string
- _truncate_for_prompt(): truncate long text with tail-first strategy
"""

import json
import pytest

from agent.litert_lm_client import (
    _render_message_content,
    _truncate_for_prompt,
    _assistant_tool_xml,
    _extract_literal_strings,
    _format_tools_for_prompt,
    _usage_stub,
)


# ── _render_message_content ───────────────────────────────────────────────────

class TestRenderMessageContent:
    def test_none_returns_empty(self):
        assert _render_message_content(None) == ""

    def test_string_stripped(self):
        assert _render_message_content("  hello  ") == "hello"

    def test_empty_string_returned_as_empty(self):
        assert _render_message_content("") == ""

    def test_dict_with_text_key(self):
        assert _render_message_content({"text": "hello"}) == "hello"

    def test_dict_text_stripped(self):
        assert _render_message_content({"text": "  hi  "}) == "hi"

    def test_dict_text_none_returns_empty(self):
        assert _render_message_content({"text": None}) == ""

    def test_dict_content_str_key(self):
        assert _render_message_content({"content": "body"}) == "body"

    def test_dict_text_preferred_over_content(self):
        result = _render_message_content({"text": "first", "content": "second"})
        assert result == "first"

    def test_dict_no_known_keys_json_encoded(self):
        d = {"foo": "bar"}
        result = _render_message_content(d)
        assert json.loads(result) == d

    def test_list_of_strings_joined(self):
        result = _render_message_content(["hello", "world"])
        assert result == "hello\nworld"

    def test_list_of_dicts_with_text(self):
        result = _render_message_content([{"text": "a"}, {"text": "b"}])
        assert result == "a\nb"

    def test_list_skips_items_without_text(self):
        result = _render_message_content([{"image_url": "x"}, {"text": "keep"}])
        assert result == "keep"

    def test_list_skips_whitespace_only_text(self):
        result = _render_message_content([{"text": "   "}, {"text": "real"}])
        assert result == "real"

    def test_list_mixed_strings_and_dicts(self):
        result = _render_message_content(["hello", {"text": "world"}])
        assert "hello" in result
        assert "world" in result

    def test_non_string_non_dict_non_list_coerced_to_str(self):
        assert _render_message_content(42) == "42"

    def test_empty_list_returns_empty(self):
        assert _render_message_content([]) == ""


# ── _truncate_for_prompt ──────────────────────────────────────────────────────

class TestTruncateForPrompt:
    def test_short_text_returned_unchanged(self):
        text = "hello world"
        assert _truncate_for_prompt(text, 100) == text

    def test_exact_limit_not_truncated(self):
        text = "a" * 50
        assert _truncate_for_prompt(text, 50) == text

    def test_over_limit_appends_truncated_marker(self):
        text = "x" * 200
        result = _truncate_for_prompt(text, 50)
        assert result.endswith("\n\n[truncated]\n")

    def test_truncated_result_within_limit(self):
        text = "a" * 500
        limit = 100
        result = _truncate_for_prompt(text, limit)
        assert len(result) <= limit

    def test_tail_is_preserved_over_head(self):
        """The tail of the text should be kept, not the head."""
        head = "BEGINNING_" * 50
        tail = "END_UNIQUE_SUFFIX"
        text = head + tail
        result = _truncate_for_prompt(text, 80)
        assert "END_UNIQUE_SUFFIX" in result

    def test_zero_limit_returns_truncated_marker_only(self):
        text = "hello world"
        result = _truncate_for_prompt(text, 0)
        assert "[truncated]" in result

    def test_empty_text_returned_as_is(self):
        assert _truncate_for_prompt("", 100) == ""


# ── _format_tools_for_prompt ──────────────────────────────────────────────────

class TestFormatToolsForPrompt:
    def test_none_returns_empty_json_array(self):
        assert _format_tools_for_prompt(None) == "[]"

    def test_empty_list_returns_empty_json_array(self):
        assert _format_tools_for_prompt([]) == "[]"

    def test_valid_tool_included(self):
        tools = [{"function": {"name": "my_tool", "description": "does stuff", "parameters": {}}}]
        result = json.loads(_format_tools_for_prompt(tools))
        assert len(result) == 1
        assert result[0]["name"] == "my_tool"
        assert result[0]["description"] == "does stuff"

    def test_tool_without_name_excluded(self):
        tools = [{"function": {"description": "no name"}}]
        result = json.loads(_format_tools_for_prompt(tools))
        assert result == []

    def test_non_dict_items_excluded(self):
        tools = ["string", 42, {"function": {"name": "ok"}}]
        result = json.loads(_format_tools_for_prompt(tools))
        assert len(result) == 1
        assert result[0]["name"] == "ok"

    def test_missing_description_defaults_to_empty_string(self):
        tools = [{"function": {"name": "tool_x"}}]
        result = json.loads(_format_tools_for_prompt(tools))
        assert result[0]["description"] == ""

    def test_multiple_tools_all_included(self):
        tools = [
            {"function": {"name": "a", "description": "A"}},
            {"function": {"name": "b", "description": "B"}},
        ]
        result = json.loads(_format_tools_for_prompt(tools))
        names = [t["name"] for t in result]
        assert names == ["a", "b"]


# ── _assistant_tool_xml ───────────────────────────────────────────────────────

class TestAssistantToolXml:
    def test_no_tool_calls_returns_empty(self):
        assert _assistant_tool_xml({}) == ""
        assert _assistant_tool_xml({"tool_calls": []}) == ""

    def test_single_tool_call_produces_xml(self):
        msg = {"tool_calls": [{"function": {"name": "my_tool", "arguments": {"x": 1}}}]}
        result = _assistant_tool_xml(msg)
        assert "<tool_call>" in result
        assert "my_tool" in result
        assert "</tool_call>" in result

    def test_arguments_string_parsed_as_json(self):
        msg = {"tool_calls": [{"function": {"name": "t", "arguments": '{"key": "val"}'}}]}
        result = _assistant_tool_xml(msg)
        data = json.loads(result.replace("<tool_call>\n", "").replace("\n</tool_call>", ""))
        assert data["arguments"] == {"key": "val"}

    def test_invalid_arguments_string_defaults_to_empty_dict(self):
        msg = {"tool_calls": [{"function": {"name": "t", "arguments": "not-json"}}]}
        result = _assistant_tool_xml(msg)
        assert '"arguments": {}' in result

    def test_non_dict_arguments_defaults_to_empty_dict(self):
        msg = {"tool_calls": [{"function": {"name": "t", "arguments": [1, 2, 3]}}]}
        result = _assistant_tool_xml(msg)
        assert '"arguments": {}' in result

    def test_tool_call_without_name_excluded(self):
        msg = {"tool_calls": [{"function": {"description": "no name"}}]}
        assert _assistant_tool_xml(msg) == ""

    def test_multiple_tool_calls_separated_by_newline(self):
        msg = {"tool_calls": [
            {"function": {"name": "a", "arguments": {}}},
            {"function": {"name": "b", "arguments": {}}},
        ]}
        result = _assistant_tool_xml(msg)
        assert result.count("<tool_call>") == 2


# ── _extract_literal_strings ──────────────────────────────────────────────────

class TestExtractLiteralStrings:
    def test_empty_messages_returns_empty(self):
        assert _extract_literal_strings([]) == []

    def test_none_messages_returns_empty(self):
        assert _extract_literal_strings(None) == []

    def test_absolute_path_extracted(self):
        msgs = [{"role": "user", "content": "check /home/user/file.py please"}]
        result = _extract_literal_strings(msgs)
        assert any("/home/user/file.py" in p for p in result)

    def test_no_absolute_paths_returns_empty(self):
        msgs = [{"role": "user", "content": "just some text"}]
        assert _extract_literal_strings(msgs) == []

    def test_duplicates_deduplicated(self):
        msgs = [
            {"role": "user", "content": "check /home/user/file.py and /home/user/file.py"},
        ]
        result = _extract_literal_strings(msgs)
        assert result.count("/home/user/file.py") == 1

    def test_max_12_results(self):
        content = " ".join(f"/home/user/file{i}.py" for i in range(20))
        msgs = [{"role": "user", "content": content}]
        result = _extract_literal_strings(msgs)
        assert len(result) <= 12

    def test_non_dict_messages_ignored(self):
        msgs = ["string", 42, {"role": "user", "content": "/etc/hosts is there"}]
        result = _extract_literal_strings(msgs)
        assert any("/etc/hosts" in p for p in result)


# ── _usage_stub ───────────────────────────────────────────────────────────────

class TestUsageStub:
    def test_empty_text_returns_zero_completion_tokens(self):
        result = _usage_stub("")
        assert result.completion_tokens == 0
        assert result.prompt_tokens == 0

    def test_none_text_returns_zero(self):
        result = _usage_stub(None)
        assert result.completion_tokens == 0

    def test_text_estimates_completion_tokens(self):
        result = _usage_stub("a" * 400)
        assert result.completion_tokens == 100

    def test_short_text_at_least_one_token(self):
        result = _usage_stub("x")
        assert result.completion_tokens >= 1

    def test_total_tokens_equals_completion_tokens(self):
        result = _usage_stub("hello world test")
        assert result.total_tokens == result.completion_tokens

    def test_cached_tokens_zero(self):
        result = _usage_stub("text")
        assert result.prompt_tokens_details.cached_tokens == 0
