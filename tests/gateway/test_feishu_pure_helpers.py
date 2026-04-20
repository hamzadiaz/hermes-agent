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
- _to_post_payload(): extract title+content dict from a candidate dict
- _resolve_locale_payload(): resolve locale-keyed post payload
- _resolve_post_payload(): top-level post payload resolution with nested unwrapping
- _normalize_feishu_text(): normalize whitespace and remove mention placeholders
- _unique_lines(): deduplicate non-empty lines preserving order
- _attachment_placeholder(): format attachment reference string
- _find_header_title(): extract title from Feishu card header dict
- _first_non_empty_text(): return first non-empty normalized text from varargs
- _walk_nodes(): depth-first dict/list node generator
"""

import pytest

from gateway.platforms.feishu import (
    _attachment_placeholder,
    _escape_markdown_text,
    _find_header_title,
    _first_non_empty_text,
    _is_style_enabled,
    _normalize_feishu_text,
    _render_code_block_element,
    _render_text_element,
    _resolve_locale_payload,
    _resolve_post_payload,
    _sanitize_fence_language,
    _strip_markdown_to_plain_text,
    _to_boolean,
    _to_post_payload,
    _unique_lines,
    _walk_nodes,
    _wrap_inline_code,
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


# ── _to_post_payload ──────────────────────────────────────────────────────────

class TestToPostPayload:
    def test_valid_dict_with_content_list_returned(self):
        candidate = {"content": [["text"]], "title": "Hello"}
        result = _to_post_payload(candidate)
        assert result == {"title": "Hello", "content": [["text"]]}

    def test_missing_content_returns_empty(self):
        assert _to_post_payload({"title": "No Content"}) == {}

    def test_content_not_list_returns_empty(self):
        assert _to_post_payload({"content": "string", "title": "T"}) == {}

    def test_none_returns_empty(self):
        assert _to_post_payload(None) == {}

    def test_non_dict_returns_empty(self):
        assert _to_post_payload("not a dict") == {}
        assert _to_post_payload(42) == {}

    def test_missing_title_defaults_to_empty_string(self):
        result = _to_post_payload({"content": [[]]})
        assert result["title"] == ""

    def test_none_title_defaults_to_empty_string(self):
        result = _to_post_payload({"content": [[]], "title": None})
        assert result["title"] == ""


# ── _resolve_locale_payload ───────────────────────────────────────────────────

class TestResolveLocalePayload:
    def test_direct_post_payload_returned(self):
        payload = {"content": [["text"]], "title": "Direct"}
        result = _resolve_locale_payload(payload)
        assert result["title"] == "Direct"

    def test_en_us_locale_found(self):
        payload = {"en_us": {"content": [["text"]], "title": "English"}}
        result = _resolve_locale_payload(payload)
        assert result["title"] == "English"

    def test_zh_cn_locale_found_as_fallback(self):
        payload = {"zh_cn": {"content": [["text"]], "title": "Chinese"}}
        result = _resolve_locale_payload(payload)
        assert result["title"] == "Chinese"

    def test_non_dict_returns_empty(self):
        assert _resolve_locale_payload(None) == {}
        assert _resolve_locale_payload("string") == {}

    def test_no_valid_locale_returns_empty(self):
        assert _resolve_locale_payload({"unknown_key": {"no_content": True}}) == {}

    def test_any_nested_post_payload_found(self):
        payload = {"custom_locale": {"content": [["x"]], "title": "Custom"}}
        result = _resolve_locale_payload(payload)
        assert result["title"] == "Custom"


# ── _resolve_post_payload ─────────────────────────────────────────────────────

class TestResolvePostPayload:
    def test_direct_post_payload_returned(self):
        payload = {"content": [["text"]], "title": "Direct"}
        result = _resolve_post_payload(payload)
        assert result["title"] == "Direct"

    def test_nested_under_post_key(self):
        payload = {"post": {"en_us": {"content": [["text"]], "title": "Nested"}}}
        result = _resolve_post_payload(payload)
        assert result["title"] == "Nested"

    def test_locale_at_top_level(self):
        payload = {"en_us": {"content": [["text"]], "title": "TopLocale"}}
        result = _resolve_post_payload(payload)
        assert result["title"] == "TopLocale"

    def test_non_dict_returns_empty(self):
        assert _resolve_post_payload(None) == {}
        assert _resolve_post_payload("string") == {}

    def test_empty_dict_returns_empty(self):
        assert _resolve_post_payload({}) == {}


# ── _normalize_feishu_text ────────────────────────────────────────────────────

class TestNormalizeFeishuText:
    def test_plain_text_unchanged(self):
        assert _normalize_feishu_text("hello world") == "hello world"

    def test_empty_string_returns_empty(self):
        assert _normalize_feishu_text("") == ""

    def test_none_returns_empty(self):
        assert _normalize_feishu_text(None) == ""

    def test_leading_trailing_whitespace_stripped(self):
        assert _normalize_feishu_text("  hello  ") == "hello"

    def test_mention_placeholder_removed(self):
        result = _normalize_feishu_text("hello @_user_123 world")
        assert "@_user_" not in result
        assert "hello" in result and "world" in result

    def test_crlf_normalized_to_lf(self):
        result = _normalize_feishu_text("a\r\nb")
        assert "\r\n" not in result
        assert "a\nb" == result

    def test_cr_normalized_to_lf(self):
        result = _normalize_feishu_text("a\rb")
        assert "\r" not in result

    def test_multiline_preserved(self):
        result = _normalize_feishu_text("line1\nline2")
        assert result == "line1\nline2"

    def test_multiple_spaces_collapsed(self):
        result = _normalize_feishu_text("a  b   c")
        assert result == "a b c"


# ── _unique_lines ──────────────────────────────────────────────────────────────

class TestUniqueLines:
    def test_empty_list_returns_empty(self):
        assert _unique_lines([]) == []

    def test_duplicates_removed(self):
        assert _unique_lines(["a", "b", "a"]) == ["a", "b"]

    def test_order_preserved(self):
        assert _unique_lines(["c", "a", "b", "a"]) == ["c", "a", "b"]

    def test_empty_strings_excluded(self):
        assert _unique_lines(["a", "", "b", ""]) == ["a", "b"]

    def test_all_duplicates_returns_single(self):
        assert _unique_lines(["x", "x", "x"]) == ["x"]

    def test_no_duplicates_unchanged(self):
        assert _unique_lines(["a", "b", "c"]) == ["a", "b", "c"]


# ── _attachment_placeholder ───────────────────────────────────────────────────

class TestAttachmentPlaceholder:
    def test_named_file_returns_formatted_string(self):
        result = _attachment_placeholder("report.pdf")
        assert result == "[Attachment: report.pdf]"

    def test_empty_name_returns_fallback(self):
        result = _attachment_placeholder("")
        assert result == "[Attachment]"

    def test_whitespace_only_name_returns_fallback(self):
        result = _attachment_placeholder("   ")
        assert result == "[Attachment]"

    def test_file_name_with_spaces(self):
        result = _attachment_placeholder("my report.docx")
        assert "my report.docx" in result


# ── _find_header_title ────────────────────────────────────────────────────────

class TestFindHeaderTitle:
    def test_non_dict_returns_empty(self):
        assert _find_header_title(None) == ""
        assert _find_header_title("string") == ""

    def test_missing_header_returns_empty(self):
        assert _find_header_title({}) == ""

    def test_non_dict_header_returns_empty(self):
        assert _find_header_title({"header": "not a dict"}) == ""

    def test_title_dict_with_content_key(self):
        payload = {"header": {"title": {"content": "My Title"}}}
        assert _find_header_title(payload) == "My Title"

    def test_title_dict_with_text_key(self):
        payload = {"header": {"title": {"text": "Text Title"}}}
        assert _find_header_title(payload) == "Text Title"

    def test_title_string_directly(self):
        payload = {"header": {"title": "Direct Title"}}
        assert _find_header_title(payload) == "Direct Title"

    def test_title_none_returns_empty(self):
        payload = {"header": {"title": None}}
        assert _find_header_title(payload) == ""


# ── _first_non_empty_text ─────────────────────────────────────────────────────

class TestFirstNonEmptyText:
    def test_first_non_empty_string_returned(self):
        assert _first_non_empty_text("", None, "found") == "found"

    def test_all_empty_returns_empty(self):
        assert _first_non_empty_text("", None, "") == ""

    def test_no_args_returns_empty(self):
        assert _first_non_empty_text() == ""

    def test_first_string_returned(self):
        assert _first_non_empty_text("first", "second") == "first"

    def test_dict_values_skipped(self):
        # dicts are skipped
        assert _first_non_empty_text({}, "found") == "found"

    def test_list_values_skipped(self):
        # lists are skipped
        assert _first_non_empty_text([], "found") == "found"

    def test_whitespace_only_string_skipped(self):
        assert _first_non_empty_text("   ", "real") == "real"


# ── _walk_nodes ───────────────────────────────────────────────────────────────

class TestWalkNodes:
    def test_empty_dict_yields_itself(self):
        result = list(_walk_nodes({}))
        assert result == [{}]

    def test_flat_dict_yields_itself(self):
        result = list(_walk_nodes({"a": 1}))
        assert result == [{"a": 1}]

    def test_nested_dict_yields_all_dicts(self):
        result = list(_walk_nodes({"a": {"b": 1}}))
        assert {"a": {"b": 1}} in result
        assert {"b": 1} in result

    def test_list_of_dicts_yields_all(self):
        result = list(_walk_nodes([{"x": 1}, {"y": 2}]))
        assert {"x": 1} in result
        assert {"y": 2} in result

    def test_scalar_yields_nothing(self):
        assert list(_walk_nodes(42)) == []
        assert list(_walk_nodes("string")) == []
        assert list(_walk_nodes(None)) == []

    def test_nested_list_in_dict_traversed(self):
        payload = {"items": [{"id": 1}, {"id": 2}]}
        result = list(_walk_nodes(payload))
        ids = [n.get("id") for n in result if isinstance(n, dict) and "id" in n]
        assert 1 in ids and 2 in ids
