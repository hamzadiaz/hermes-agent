"""Tests for pure helper functions in run_agent.py.

Covers:
- _normalize_assistant_content(): coerce provider-specific content blocks to plain text
- _is_destructive_command(): heuristic detection of file-destructive commands
"""

import json
import pytest

from run_agent import _normalize_assistant_content, _is_destructive_command


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
