"""Tests for pure text helper functions in gateway/run.py.

Covers:
- _normalize_gateway_text(): coerce structured content to plain text
- _normalize_whatsapp_identifier(): strip JID/LID syntax to stable numeric ID
"""

import pytest

from gateway.run import _normalize_gateway_text, _normalize_whatsapp_identifier


# ── _normalize_gateway_text ───────────────────────────────────────────────────

class TestNormalizeGatewayText:
    def test_none_returns_empty(self):
        assert _normalize_gateway_text(None) == ""

    def test_string_returned_as_is(self):
        assert _normalize_gateway_text("hello world") == "hello world"

    def test_dict_with_text_key(self):
        assert _normalize_gateway_text({"text": "hello"}) == "hello"

    def test_dict_with_content_key(self):
        assert _normalize_gateway_text({"content": "world"}) == "world"

    def test_dict_text_preferred_over_content(self):
        assert _normalize_gateway_text({"text": "text_val", "content": "content_val"}) == "text_val"

    def test_dict_without_text_or_content_json_serialized(self):
        result = _normalize_gateway_text({"other": "value"})
        assert "other" in result

    def test_list_of_strings_joined_with_newline(self):
        result = _normalize_gateway_text(["line one", "line two"])
        assert "line one" in result
        assert "line two" in result

    def test_list_of_text_dicts_extracted(self):
        items = [{"type": "text", "text": "hello"}, {"type": "text", "text": "world"}]
        result = _normalize_gateway_text(items)
        assert "hello" in result
        assert "world" in result

    def test_list_with_text_key_dict(self):
        items = [{"text": "extracted"}]
        result = _normalize_gateway_text(items)
        assert "extracted" in result

    def test_list_empty_parts_skipped(self):
        result = _normalize_gateway_text(["", "hello", ""])
        assert result == "hello"

    def test_integer_converted_to_string(self):
        assert _normalize_gateway_text(42) == "42"

    def test_list_with_mixed_types(self):
        """Non-dict, non-string list items should be skipped gracefully."""
        items = [{"type": "text", "text": "keep"}, 123, None]
        result = _normalize_gateway_text(items)
        assert "keep" in result


# ── _normalize_whatsapp_identifier ────────────────────────────────────────────

class TestNormalizeWhatsappIdentifier:
    def test_plain_phone_number(self):
        assert _normalize_whatsapp_identifier("12345678900") == "12345678900"

    def test_plus_prefix_stripped(self):
        assert _normalize_whatsapp_identifier("+12345678900") == "12345678900"

    def test_jid_at_suffix_stripped(self):
        assert _normalize_whatsapp_identifier("12345678900@s.whatsapp.net") == "12345678900"

    def test_lid_colon_suffix_stripped(self):
        assert _normalize_whatsapp_identifier("12345678900:12") == "12345678900"

    def test_full_jid_with_colon_and_at(self):
        assert _normalize_whatsapp_identifier("12345678900:12@s.whatsapp.net") == "12345678900"

    def test_plus_and_jid_combined(self):
        assert _normalize_whatsapp_identifier("+12345678900@s.whatsapp.net") == "12345678900"

    def test_none_returns_empty(self):
        assert _normalize_whatsapp_identifier(None) == ""

    def test_empty_string_returns_empty(self):
        assert _normalize_whatsapp_identifier("") == ""

    def test_whitespace_stripped(self):
        assert _normalize_whatsapp_identifier("  12345678900  ") == "12345678900"

    def test_lid_format(self):
        """LID identifiers look like 12345.67890:12@lid."""
        assert _normalize_whatsapp_identifier("12345.67890:12@lid") == "12345.67890"
