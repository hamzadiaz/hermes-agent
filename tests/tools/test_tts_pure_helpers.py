"""Tests for pure helper functions in tools/tts_tool.py.

Covers:
- _get_provider(): provider extraction with default fallback
- _strip_markdown_for_tts(): code blocks, links, bold, italic, headers, etc.
"""

import pytest

from tools.tts_tool import _get_provider, _strip_markdown_for_tts


# ── _get_provider ─────────────────────────────────────────────────────────────

class TestGetProvider:
    def test_returns_configured_provider(self):
        config = {"provider": "elevenlabs"}
        assert _get_provider(config) == "elevenlabs"

    def test_provider_lowercased(self):
        config = {"provider": "ElevenLabs"}
        assert _get_provider(config) == "elevenlabs"

    def test_provider_stripped(self):
        config = {"provider": "  openai  "}
        assert _get_provider(config) == "openai"

    def test_missing_provider_returns_default(self):
        from tools.tts_tool import DEFAULT_PROVIDER
        config = {}
        assert _get_provider(config) == DEFAULT_PROVIDER.lower().strip()

    def test_none_provider_returns_default(self):
        from tools.tts_tool import DEFAULT_PROVIDER
        config = {"provider": None}
        assert _get_provider(config) == DEFAULT_PROVIDER.lower().strip()

    def test_empty_provider_returns_default(self):
        from tools.tts_tool import DEFAULT_PROVIDER
        config = {"provider": ""}
        assert _get_provider(config) == DEFAULT_PROVIDER.lower().strip()


# ── _strip_markdown_for_tts ───────────────────────────────────────────────────

class TestStripMarkdownForTts:
    def test_plain_text_unchanged(self):
        assert _strip_markdown_for_tts("Hello world") == "Hello world"

    def test_code_block_replaced_with_space(self):
        result = _strip_markdown_for_tts("before ```python\ncode\n``` after")
        assert "```" not in result
        assert "before" in result
        assert "after" in result

    def test_inline_code_content_preserved(self):
        result = _strip_markdown_for_tts("Use `print()` to output")
        assert "`" not in result
        assert "print()" in result

    def test_bold_content_preserved(self):
        result = _strip_markdown_for_tts("This is **important** text")
        assert "**" not in result
        assert "important" in result

    def test_italic_content_preserved(self):
        result = _strip_markdown_for_tts("This is *emphasized* text")
        assert "*" not in result
        assert "emphasized" in result

    def test_link_text_preserved_url_removed(self):
        result = _strip_markdown_for_tts("See [the docs](https://example.com) for more")
        assert "the docs" in result
        assert "https://example.com" not in result
        assert "[" not in result

    def test_bare_url_removed(self):
        result = _strip_markdown_for_tts("Visit https://example.com for info")
        assert "https://example.com" not in result

    def test_markdown_header_removed(self):
        result = _strip_markdown_for_tts("## Header text\nBody")
        assert "##" not in result

    def test_list_item_markers_removed(self):
        result = _strip_markdown_for_tts("- item one\n- item two")
        assert result.strip().startswith("-") is False

    def test_horizontal_rule_removed(self):
        result = _strip_markdown_for_tts("line one\n---\nline two")
        assert "---" not in result

    def test_excess_newlines_collapsed(self):
        result = _strip_markdown_for_tts("para one\n\n\n\npara two")
        assert "\n\n\n" not in result

    def test_empty_string_returns_empty(self):
        assert _strip_markdown_for_tts("") == ""

    def test_result_stripped(self):
        result = _strip_markdown_for_tts("  hello world  ")
        assert result == result.strip()

    def test_nested_bold_and_italic(self):
        result = _strip_markdown_for_tts("**bold** and *italic* text")
        assert "**" not in result
        assert "*" not in result
        assert "bold" in result
        assert "italic" in result
