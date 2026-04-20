"""Tests for pure helper functions in gateway/platforms/feishu.py.

Covers:
- _escape_markdown_text(): escape Markdown special chars
- _to_boolean(): coerce various truthy inputs to bool
- _is_style_enabled(): check whether a style dict key is truthy
- _wrap_inline_code(): wrap code with appropriate backtick fence
- _sanitize_fence_language(): strip whitespace/newlines from language hint
- _render_text_element(): render a Feishu text element to Markdown
- _render_code_block_element(): render a Feishu code block element to Markdown fence
- _strip_markdown_to_plain_text(): strip Markdown formatting to plain text
"""

import pytest

from gateway.platforms.feishu import (
    _escape_markdown_text,
    _to_boolean,
    _is_style_enabled,
    _wrap_inline_code,
    _sanitize_fence_language,
    _render_text_element,
    _render_code_block_element,
    _strip_markdown_to_plain_text,
)


# ── _escape_markdown_text ─────────────────────────────────────────────────────

class TestEscapeMarkdownText:
    def test_plain_text_unchanged(self):
        assert _escape_markdown_text("hello world") == "hello world"

    def test_asterisk_escaped(self):
        assert _escape_markdown_text("bold*word") == r"bold\*word"

    def test_underscore_escaped(self):
        assert _escape_markdown_text("_italic_") == r"\_italic\_"

    def test_backtick_escaped(self):
        assert _escape_markdown_text("`code`") == r"\`code\`"

    def test_brackets_escaped(self):
        result = _escape_markdown_text("[link](url)")
        assert r"\[" in result
        assert r"\]" in result

    def test_hash_escaped(self):
        assert _escape_markdown_text("# Heading") == r"\# Heading"

    def test_empty_string(self):
        assert _escape_markdown_text("") == ""

    def test_tilde_escaped(self):
        assert _escape_markdown_text("~~strike~~") == r"\~\~strike\~\~"


# ── _to_boolean ───────────────────────────────────────────────────────────────

class TestToBoolean:
    def test_true_literal(self):
        assert _to_boolean(True) is True

    def test_one_is_true(self):
        assert _to_boolean(1) is True

    def test_string_true_is_true(self):
        assert _to_boolean("true") is True

    def test_false_literal(self):
        assert _to_boolean(False) is False

    def test_zero_is_false(self):
        assert _to_boolean(0) is False

    def test_none_is_false(self):
        assert _to_boolean(None) is False

    def test_string_false_is_false(self):
        assert _to_boolean("false") is False

    def test_string_one_is_false(self):
        # Only exact int 1 and True match, not "1"
        assert _to_boolean("1") is False

    def test_empty_string_is_false(self):
        assert _to_boolean("") is False


# ── _is_style_enabled ─────────────────────────────────────────────────────────

class TestIsStyleEnabled:
    def test_none_style_returns_false(self):
        assert _is_style_enabled(None, "bold") is False

    def test_empty_dict_returns_false(self):
        assert _is_style_enabled({}, "bold") is False

    def test_key_true_returns_true(self):
        assert _is_style_enabled({"bold": True}, "bold") is True

    def test_key_absent_returns_false(self):
        assert _is_style_enabled({"italic": True}, "bold") is False

    def test_key_false_returns_false(self):
        assert _is_style_enabled({"bold": False}, "bold") is False

    def test_key_one_returns_true(self):
        assert _is_style_enabled({"bold": 1}, "bold") is True


# ── _wrap_inline_code ─────────────────────────────────────────────────────────

class TestWrapInlineCode:
    def test_simple_text_single_backtick(self):
        result = _wrap_inline_code("hello")
        assert result == "`hello`"

    def test_text_with_backtick_uses_double_fence(self):
        result = _wrap_inline_code("a`b")
        assert result.startswith("``")
        assert result.endswith("``")

    def test_text_starting_with_backtick_adds_spaces(self):
        result = _wrap_inline_code("`start")
        # Should add padding space to avoid fence ambiguity
        assert " " in result[1:]  # space after opening fence

    def test_text_ending_with_backtick_adds_spaces(self):
        # "end`" has a trailing backtick → body gets padded → "`` end` ``"
        result = _wrap_inline_code("end`")
        assert " end`" in result  # padding space added before trailing backtick

    def test_empty_string(self):
        result = _wrap_inline_code("")
        assert result == "``"


# ── _sanitize_fence_language ──────────────────────────────────────────────────

class TestSanitizeFenceLanguage:
    def test_plain_language_unchanged(self):
        assert _sanitize_fence_language("python") == "python"

    def test_whitespace_stripped(self):
        assert _sanitize_fence_language("  js  ") == "js"

    def test_newline_replaced_with_space(self):
        result = _sanitize_fence_language("py\nthon")
        assert "\n" not in result
        assert "py" in result

    def test_carriage_return_replaced(self):
        result = _sanitize_fence_language("py\rthon")
        assert "\r" not in result

    def test_empty_string_unchanged(self):
        assert _sanitize_fence_language("") == ""


# ── _render_text_element ──────────────────────────────────────────────────────

class TestRenderTextElement:
    def test_plain_text_escaped(self):
        result = _render_text_element({"text": "hello"})
        assert result == "hello"

    def test_bold_wraps_with_stars(self):
        result = _render_text_element({"text": "hello", "style": {"bold": True}})
        assert result == "**hello**"

    def test_italic_wraps_with_single_star(self):
        result = _render_text_element({"text": "hi", "style": {"italic": True}})
        assert result == "*hi*"

    def test_strikethrough_wraps_with_tildes(self):
        result = _render_text_element({"text": "del", "style": {"strikethrough": True}})
        assert result == "~~del~~"

    def test_underline_wraps_with_u_tag(self):
        result = _render_text_element({"text": "under", "style": {"underline": True}})
        assert result == "<u>under</u>"

    def test_code_style_wraps_with_backticks(self):
        result = _render_text_element({"text": "ls", "style": {"code": True}})
        assert result.startswith("`")
        assert result.endswith("`")

    def test_empty_text_returns_empty(self):
        assert _render_text_element({"text": ""}) == ""

    def test_special_chars_escaped_in_plain_text(self):
        result = _render_text_element({"text": "a*b"})
        assert r"\*" in result


# ── _render_code_block_element ────────────────────────────────────────────────

class TestRenderCodeBlockElement:
    def test_produces_fenced_code_block(self):
        result = _render_code_block_element({"language": "python", "text": "print(1)"})
        assert result.startswith("```python")
        assert "print(1)" in result
        assert result.endswith("```")

    def test_no_language_produces_bare_fence(self):
        result = _render_code_block_element({"text": "code"})
        assert result.startswith("```\n")

    def test_trailing_newline_not_doubled(self):
        result = _render_code_block_element({"text": "code\n"})
        # Code already ends with \n → no extra newline injected → no double newline before ```
        assert "\n\n```" not in result

    def test_content_key_fallback(self):
        result = _render_code_block_element({"content": "body"})
        assert "body" in result

    def test_crlf_normalized(self):
        result = _render_code_block_element({"text": "a\r\nb"})
        assert "\r\n" not in result
        assert "a\nb" in result


# ── _strip_markdown_to_plain_text ─────────────────────────────────────────────

class TestStripMarkdownToPlainText:
    def test_plain_text_unchanged(self):
        assert _strip_markdown_to_plain_text("hello world") == "hello world"

    def test_heading_stripped(self):
        result = _strip_markdown_to_plain_text("# Title")
        assert result == "Title"

    def test_bold_stripped(self):
        result = _strip_markdown_to_plain_text("**bold**")
        assert result == "bold"

    def test_italic_stripped(self):
        result = _strip_markdown_to_plain_text("*italic*")
        assert result == "italic"

    def test_strikethrough_stripped(self):
        result = _strip_markdown_to_plain_text("~~strike~~")
        assert result == "strike"

    def test_inline_code_stripped(self):
        result = _strip_markdown_to_plain_text("`code`")
        assert result == "code"

    def test_fenced_code_block_stripped(self):
        result = _strip_markdown_to_plain_text("```python\nprint(1)\n```")
        assert "print(1)" in result
        assert "```" not in result

    def test_link_expanded_to_text_and_url(self):
        result = _strip_markdown_to_plain_text("[Google](https://google.com)")
        assert "Google" in result
        assert "google.com" in result

    def test_underline_tag_stripped(self):
        result = _strip_markdown_to_plain_text("<u>under</u>")
        assert result == "under"

    def test_multiple_blank_lines_collapsed(self):
        result = _strip_markdown_to_plain_text("a\n\n\n\nb")
        assert "\n\n\n" not in result

    def test_blockquote_marker_removed(self):
        result = _strip_markdown_to_plain_text("> quoted text")
        assert result == "quoted text"

    def test_h3_heading_stripped(self):
        result = _strip_markdown_to_plain_text("### Section")
        assert result == "Section"

    def test_empty_string_returns_empty(self):
        assert _strip_markdown_to_plain_text("") == ""
