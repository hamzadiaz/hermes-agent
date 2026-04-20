"""Tests for pure helper functions in agent/claude_code_client.py.

Covers:
- _render_message_content(): coerce content to plain string
- _format_tools_for_prompt(): format OpenAI-style tool list to JSON string
- _assistant_tool_xml(): render tool_calls as Hermes <tool_call> XML blocks
- _extract_literal_strings(): extract unique absolute paths from messages (max 12)
- _map_native_tool_name(): map Claude Code native tool names to Hermes names
- _usage_from_payload(): parse usage dict into SimpleNamespace
"""

import json
import pytest
from types import SimpleNamespace

from agent.claude_code_client import (
    _render_message_content,
    _format_tools_for_prompt,
    _assistant_tool_xml,
    _extract_literal_strings,
    _map_native_tool_name,
    _usage_from_payload,
)


# ── _render_message_content ───────────────────────────────────────────────────

class TestRenderMessageContent:
    def test_none_returns_empty(self):
        assert _render_message_content(None) == ""

    def test_string_stripped(self):
        assert _render_message_content("  hello  ") == "hello"

    def test_empty_string(self):
        assert _render_message_content("") == ""

    def test_dict_with_text_key(self):
        assert _render_message_content({"text": "hello"}) == "hello"

    def test_dict_with_content_key(self):
        assert _render_message_content({"content": "body"}) == "body"

    def test_dict_text_preferred_over_content(self):
        assert _render_message_content({"text": "t", "content": "c"}) == "t"

    def test_dict_no_known_keys_json_encoded(self):
        d = {"foo": "bar"}
        result = _render_message_content(d)
        assert json.loads(result) == d

    def test_dict_text_key_present_but_none_returns_empty(self):
        # "text" key exists (even if None) → returns "" (does NOT fall through to "content")
        result = _render_message_content({"text": None, "content": "body"})
        assert result == ""

    def test_list_of_strings_joined(self):
        result = _render_message_content(["hello", "world"])
        assert "hello" in result
        assert "world" in result

    def test_list_of_text_dicts_joined(self):
        content = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
        result = _render_message_content(content)
        assert "a" in result
        assert "b" in result

    def test_list_skips_items_without_text_key(self):
        content = [{"type": "image", "url": "x"}, {"text": "keep"}]
        result = _render_message_content(content)
        assert "keep" in result
        assert "image" not in result

    def test_list_skips_empty_text(self):
        content = [{"text": ""}, {"text": "keep"}]
        result = _render_message_content(content)
        assert result.strip() == "keep"

    def test_non_string_coerced_to_str(self):
        assert _render_message_content(42) == "42"


# ── _format_tools_for_prompt ──────────────────────────────────────────────────

class TestFormatToolsForPrompt:
    def test_none_returns_empty_list_json(self):
        assert _format_tools_for_prompt(None) == "[]"

    def test_empty_list_returns_empty_list_json(self):
        assert _format_tools_for_prompt([]) == "[]"

    def test_single_tool_included(self):
        tools = [{"function": {"name": "bash", "description": "Run bash", "parameters": {}}}]
        result = json.loads(_format_tools_for_prompt(tools))
        assert len(result) == 1
        assert result[0]["name"] == "bash"
        assert result[0]["description"] == "Run bash"

    def test_tool_without_name_skipped(self):
        tools = [{"function": {"description": "no name", "parameters": {}}}]
        result = json.loads(_format_tools_for_prompt(tools))
        assert result == []

    def test_non_dict_tool_skipped(self):
        tools = ["not a dict", {"function": {"name": "ok"}}]
        result = json.loads(_format_tools_for_prompt(tools))
        assert len(result) == 1
        assert result[0]["name"] == "ok"

    def test_missing_function_key_skipped(self):
        tools = [{"name": "orphan"}]
        result = json.loads(_format_tools_for_prompt(tools))
        assert result == []

    def test_required_field_is_none(self):
        tools = [{"function": {"name": "bash"}}]
        result = json.loads(_format_tools_for_prompt(tools))
        assert result[0]["required"] is None

    def test_multiple_tools(self):
        tools = [
            {"function": {"name": "bash"}},
            {"function": {"name": "read_file"}},
        ]
        result = json.loads(_format_tools_for_prompt(tools))
        names = [t["name"] for t in result]
        assert "bash" in names
        assert "read_file" in names


# ── _assistant_tool_xml ───────────────────────────────────────────────────────

class TestAssistantToolXml:
    def test_no_tool_calls_returns_empty(self):
        assert _assistant_tool_xml({}) == ""

    def test_empty_tool_calls_returns_empty(self):
        assert _assistant_tool_xml({"tool_calls": []}) == ""

    def test_single_call_produces_tool_call_block(self):
        message = {
            "tool_calls": [{"function": {"name": "bash", "arguments": '{"cmd": "ls"}'}}]
        }
        result = _assistant_tool_xml(message)
        assert "<tool_call>" in result
        assert "</tool_call>" in result
        assert "bash" in result

    def test_arguments_parsed_from_json_string(self):
        message = {
            "tool_calls": [{"function": {"name": "bash", "arguments": '{"cmd": "ls"}'}}]
        }
        result = _assistant_tool_xml(message)
        data = json.loads(result.split("<tool_call>")[1].split("</tool_call>")[0].strip())
        assert data["arguments"] == {"cmd": "ls"}

    def test_invalid_json_arguments_fallback_to_empty_dict(self):
        message = {
            "tool_calls": [{"function": {"name": "bash", "arguments": "not-json"}}]
        }
        result = _assistant_tool_xml(message)
        data = json.loads(result.split("<tool_call>")[1].split("</tool_call>")[0].strip())
        assert data["arguments"] == {}

    def test_dict_arguments_used_directly(self):
        message = {
            "tool_calls": [{"function": {"name": "bash", "arguments": {"cmd": "pwd"}}}]
        }
        result = _assistant_tool_xml(message)
        data = json.loads(result.split("<tool_call>")[1].split("</tool_call>")[0].strip())
        assert data["arguments"] == {"cmd": "pwd"}

    def test_tool_call_without_name_skipped(self):
        message = {
            "tool_calls": [{"function": {"arguments": {}}}]
        }
        assert _assistant_tool_xml(message) == ""

    def test_multiple_calls_joined(self):
        message = {
            "tool_calls": [
                {"function": {"name": "bash", "arguments": "{}"}},
                {"function": {"name": "read_file", "arguments": "{}"}},
            ]
        }
        result = _assistant_tool_xml(message)
        assert result.count("<tool_call>") == 2


# ── _extract_literal_strings ──────────────────────────────────────────────────

class TestExtractLiteralStrings:
    def test_empty_messages_returns_empty(self):
        assert _extract_literal_strings([]) == []

    def test_none_messages_returns_empty(self):
        assert _extract_literal_strings(None) == []

    def test_absolute_path_extracted(self):
        messages = [{"role": "user", "content": "Read /tmp/test/file.txt please"}]
        result = _extract_literal_strings(messages)
        assert any("tmp" in s for s in result)

    def test_no_abs_paths_returns_empty(self):
        messages = [{"role": "user", "content": "just some text without paths"}]
        result = _extract_literal_strings(messages)
        assert result == []

    def test_duplicates_deduplicated(self):
        path = "/tmp/test/file.txt"
        messages = [
            {"role": "user", "content": f"Read {path}"},
            {"role": "user", "content": f"Edit {path}"},
        ]
        result = _extract_literal_strings(messages)
        assert result.count(path) == 1

    def test_max_12_strings_returned(self):
        paths = [f"/tmp/dir/file{i}.txt" for i in range(20)]
        content = " ".join(paths)
        messages = [{"role": "user", "content": content}]
        result = _extract_literal_strings(messages)
        assert len(result) <= 12

    def test_non_dict_messages_skipped(self):
        result = _extract_literal_strings(["not a dict", None])
        assert result == []


# ── _map_native_tool_name ─────────────────────────────────────────────────────

class TestMapNativeToolName:
    def test_none_returns_tool(self):
        assert _map_native_tool_name(None) == "tool"

    def test_empty_string_returns_tool(self):
        assert _map_native_tool_name("") == "tool"

    def test_read_mapped_to_read_file(self):
        assert _map_native_tool_name("Read") == "read_file"

    def test_write_mapped_to_write_file(self):
        assert _map_native_tool_name("Write") == "write_file"

    def test_edit_mapped_to_patch(self):
        assert _map_native_tool_name("Edit") == "patch"

    def test_grep_mapped_to_search_files(self):
        assert _map_native_tool_name("Grep") == "search_files"

    def test_glob_mapped_to_search_files(self):
        assert _map_native_tool_name("Glob") == "search_files"

    def test_bash_mapped_to_terminal(self):
        assert _map_native_tool_name("Bash") == "terminal"

    def test_web_search_mapped(self):
        assert _map_native_tool_name("WebSearch") == "web_search"

    def test_todo_write_mapped(self):
        assert _map_native_tool_name("TodoWrite") == "todo"

    def test_playwright_browser_prefix_stripped(self):
        result = _map_native_tool_name("mcp__playwright__browser_navigate")
        assert result == "browser_navigate"

    def test_playwright_screenshot_mapped(self):
        assert _map_native_tool_name("mcp__playwright__browser_take_screenshot") == "browser_snapshot"

    def test_superpowers_chrome_mapped(self):
        assert _map_native_tool_name("mcp__plugin_superpowers-chrome_chrome__use_browser") == "browser_vision"

    def test_unknown_tool_lowercased(self):
        assert _map_native_tool_name("MyCustomTool") == "mycustomtool"

    def test_whitespace_stripped(self):
        assert _map_native_tool_name("  Bash  ") == "terminal"


# ── _usage_from_payload ───────────────────────────────────────────────────────

class TestUsageFromPayload:
    def test_empty_payload_returns_zeros(self):
        usage = _usage_from_payload({})
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_input_output_tokens_parsed(self):
        usage = _usage_from_payload({"usage": {"input_tokens": 100, "output_tokens": 50}})
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150

    def test_total_is_sum_of_prompt_and_completion(self):
        usage = _usage_from_payload({"usage": {"input_tokens": 200, "output_tokens": 75}})
        assert usage.total_tokens == usage.prompt_tokens + usage.completion_tokens

    def test_cache_read_tokens_parsed(self):
        usage = _usage_from_payload({"usage": {"cache_read_input_tokens": 30}})
        assert usage.prompt_tokens_details.cached_tokens == 30

    def test_none_usage_value_treated_as_zero(self):
        usage = _usage_from_payload({"usage": {"input_tokens": None}})
        assert usage.prompt_tokens == 0

    def test_usage_key_absent_returns_zeros(self):
        usage = _usage_from_payload({"model": "claude-3"})
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
