"""Tests for pure helper functions in run_agent.py.

Covers:
- _normalize_assistant_content(): coerce provider-specific content blocks to plain text
- _is_destructive_command(): heuristic detection of file-destructive commands
- _sanitize_surrogates(): replace lone UTF-16 surrogates with U+FFFD
- _sanitize_messages_surrogates(): in-place surrogate cleanup across messages list
- _strip_budget_warnings_from_history(): remove _budget_warning keys from tool msgs
"""

import json
import pytest

from run_agent import (
    _is_destructive_command,
    _normalize_assistant_content,
    _sanitize_messages_surrogates,
    _sanitize_surrogates,
    _strip_budget_warnings_from_history,
)


# ── _normalize_assistant_content ─────────────────────────────────────────────

class TestNormalizeAssistantContent:
    def test_none_returns_empty(self):
        assert _normalize_assistant_content(None) == ""

    def test_string_returned_as_is(self):
        assert _normalize_assistant_content("hello") == "hello"

    def test_empty_string_returned(self):
        assert _normalize_assistant_content("") == ""

    def test_dict_with_text_key(self):
        assert _normalize_assistant_content({"text": "hello"}) == "hello"

    def test_dict_with_content_key(self):
        assert _normalize_assistant_content({"content": "body"}) == "body"

    def test_dict_text_preferred_over_content(self):
        assert _normalize_assistant_content({"text": "t", "content": "c"}) == "t"

    def test_dict_no_known_keys_json_encoded(self):
        d = {"foo": "bar"}
        result = _normalize_assistant_content(d)
        assert json.loads(result) == d

    def test_dict_text_none_falls_through_to_json(self):
        d = {"text": None, "other": "x"}
        result = _normalize_assistant_content(d)
        # text=None → falsy → check content → also missing → json.dumps
        assert "other" in result

    def test_list_of_strings_joined(self):
        result = _normalize_assistant_content(["hello", "world"])
        assert "hello" in result
        assert "world" in result

    def test_list_of_text_dicts_joined(self):
        content = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
        result = _normalize_assistant_content(content)
        assert "a" in result
        assert "b" in result

    def test_list_skips_non_text_type_dicts(self):
        content = [{"type": "image", "url": "x"}, {"type": "text", "text": "keep"}]
        result = _normalize_assistant_content(content)
        assert "keep" in result
        assert "image" not in result

    def test_list_includes_dict_with_text_key_no_type(self):
        content = [{"text": "no-type"}]
        result = _normalize_assistant_content(content)
        assert "no-type" in result

    def test_list_empty_text_excluded(self):
        content = [{"type": "text", "text": ""}, {"type": "text", "text": "keep"}]
        result = _normalize_assistant_content(content)
        assert result.strip() == "keep"

    def test_non_string_non_dict_non_list_coerced(self):
        assert _normalize_assistant_content(42) == "42"


# ── _is_destructive_command ───────────────────────────────────────────────────

class TestIsDestructiveCommand:
    def test_empty_string_returns_false(self):
        assert _is_destructive_command("") is False

    def test_rm_command_detected(self):
        assert _is_destructive_command("rm -rf /tmp/test") is True

    def test_rmdir_detected(self):
        assert _is_destructive_command("rmdir mydir") is True

    def test_mv_detected(self):
        assert _is_destructive_command("mv old.txt new.txt") is True

    def test_sed_inplace_detected(self):
        assert _is_destructive_command("sed -i 's/old/new/' file.txt") is True

    def test_truncate_detected(self):
        assert _is_destructive_command("truncate -s 0 file.txt") is True

    def test_dd_detected(self):
        assert _is_destructive_command("dd if=/dev/zero of=file") is True

    def test_shred_detected(self):
        assert _is_destructive_command("shred -u file.txt") is True

    def test_git_reset_detected(self):
        assert _is_destructive_command("git reset --hard HEAD") is True

    def test_git_clean_detected(self):
        assert _is_destructive_command("git clean -fd") is True

    def test_git_checkout_detected(self):
        assert _is_destructive_command("git checkout -- .") is True

    def test_overwrite_redirect_detected(self):
        assert _is_destructive_command("echo hello > file.txt") is True

    def test_append_redirect_not_destructive(self):
        assert _is_destructive_command("echo hello >> file.txt") is False

    def test_safe_ls_not_destructive(self):
        assert _is_destructive_command("ls -la") is False

    def test_safe_cat_not_destructive(self):
        assert _is_destructive_command("cat file.txt") is False

    def test_safe_grep_not_destructive(self):
        assert _is_destructive_command("grep -r pattern /path") is False

    def test_chained_destructive_command(self):
        assert _is_destructive_command("mkdir dir && rm -rf dir") is True

    def test_word_containing_rm_not_destructive(self):
        """'from' contains 'rm' but not as a standalone command."""
        assert _is_destructive_command("echo from here") is False


# ── _sanitize_surrogates ──────────────────────────────────────────────────────

class TestSanitizeSurrogates:
    def test_plain_text_unchanged(self):
        assert _sanitize_surrogates("hello world") == "hello world"

    def test_empty_string_unchanged(self):
        assert _sanitize_surrogates("") == ""

    def test_surrogate_replaced_with_replacement_char(self):
        text = "hello\ud800world"
        result = _sanitize_surrogates(text)
        assert "\ud800" not in result
        assert "\ufffd" in result

    def test_high_surrogate_replaced(self):
        text = "a\udbffb"
        result = _sanitize_surrogates(text)
        assert "\udbff" not in result
        assert "\ufffd" in result

    def test_low_surrogate_replaced(self):
        text = "x\udc00y"
        result = _sanitize_surrogates(text)
        assert "\udc00" not in result
        assert "\ufffd" in result

    def test_multiple_surrogates_all_replaced(self):
        text = "\ud800\udfff"
        result = _sanitize_surrogates(text)
        assert result.count("\ufffd") == 2

    def test_no_surrogates_returns_same_object(self):
        text = "clean text"
        result = _sanitize_surrogates(text)
        assert result is text


# ── _sanitize_messages_surrogates ────────────────────────────────────────────

class TestSanitizeMessagesSurrogates:
    def test_empty_list_returns_false(self):
        assert _sanitize_messages_surrogates([]) is False

    def test_no_surrogates_returns_false(self):
        messages = [{"role": "user", "content": "hello"}]
        assert _sanitize_messages_surrogates(messages) is False

    def test_surrogate_in_content_string_replaced(self):
        messages = [{"role": "user", "content": "bad\ud800char"}]
        result = _sanitize_messages_surrogates(messages)
        assert result is True
        assert "\ud800" not in messages[0]["content"]

    def test_surrogate_in_list_content_text_replaced(self):
        messages = [{"role": "user", "content": [{"type": "text", "text": "bad\ud800"}]}]
        result = _sanitize_messages_surrogates(messages)
        assert result is True
        assert "\ud800" not in messages[0]["content"][0]["text"]

    def test_non_dict_messages_skipped_without_crash(self):
        messages = ["not a dict", None, {"role": "user", "content": "clean"}]
        assert _sanitize_messages_surrogates(messages) is False

    def test_message_without_content_key_skipped(self):
        messages = [{"role": "user"}]
        assert _sanitize_messages_surrogates(messages) is False

    def test_mutates_in_place(self):
        messages = [{"role": "user", "content": "bad\ud800char"}]
        _sanitize_messages_surrogates(messages)
        assert "\ufffd" in messages[0]["content"]


# ── _strip_budget_warnings_from_history ──────────────────────────────────────

class TestStripBudgetWarningsFromHistory:
    def test_empty_list_no_error(self):
        messages = []
        _strip_budget_warnings_from_history(messages)
        assert messages == []

    def test_non_tool_messages_untouched(self):
        messages = [{"role": "user", "content": "_budget_warning present"}]
        _strip_budget_warnings_from_history(messages)
        assert "_budget_warning" in messages[0]["content"]

    def test_json_budget_warning_key_removed(self):
        payload = {"result": "done", "_budget_warning": "Iteration 5/10."}
        messages = [{"role": "tool", "content": json.dumps(payload)}]
        _strip_budget_warnings_from_history(messages)
        parsed = json.loads(messages[0]["content"])
        assert "_budget_warning" not in parsed
        assert parsed["result"] == "done"

    def test_plain_text_budget_warning_stripped(self):
        content = "ok\n[BUDGET WARNING: Iteration 5/10. Be concise.]"
        messages = [{"role": "tool", "content": content}]
        _strip_budget_warnings_from_history(messages)
        assert "[BUDGET" not in messages[0]["content"]
        assert "ok" in messages[0]["content"]

    def test_clean_tool_message_untouched(self):
        payload = {"result": "all good"}
        content = json.dumps(payload)
        messages = [{"role": "tool", "content": content}]
        _strip_budget_warnings_from_history(messages)
        assert json.loads(messages[0]["content"]) == payload

    def test_non_tool_role_with_budget_text_not_stripped(self):
        messages = [{"role": "assistant", "content": "[BUDGET WARNING: Iteration 1/10. tight]"}]
        _strip_budget_warnings_from_history(messages)
        assert "[BUDGET" in messages[0]["content"]

    def test_mutates_in_place(self):
        payload = {"data": "x", "_budget_warning": "tight"}
        msg = {"role": "tool", "content": json.dumps(payload)}
        messages = [msg]
        _strip_budget_warnings_from_history(messages)
        parsed = json.loads(messages[0]["content"])
        assert "_budget_warning" not in parsed
