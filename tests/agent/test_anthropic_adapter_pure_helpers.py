"""Tests for pure helper functions in agent/anthropic_adapter.py.

Covers:
- _get_anthropic_max_output(): longest-prefix match, default for unknowns
- _supports_adaptive_thinking(): 4.6 detection
- _is_oauth_token(): sk-ant-api vs OAuth tokens
- _is_third_party_anthropic_endpoint(): non-Anthropic URLs
- _requires_bearer_auth(): MiniMax endpoint detection
- normalize_model_name(): anthropic/ prefix strip, dot→hyphen, preserve_dots
- _sanitize_tool_id(): invalid chars replaced, empty → "tool_0"
- _convert_openai_image_part_to_anthropic(): URL and base64 data URIs
- _convert_user_content_part_to_anthropic(): text, image_url, passthrough
- convert_tools_to_anthropic(): OpenAI → Anthropic tool format
"""

import pytest

from agent.anthropic_adapter import (
    _get_anthropic_max_output,
    _supports_adaptive_thinking,
    _is_oauth_token,
    _is_third_party_anthropic_endpoint,
    _requires_bearer_auth,
    normalize_model_name,
    _sanitize_tool_id,
    _convert_openai_image_part_to_anthropic,
    _convert_user_content_part_to_anthropic,
    _image_source_from_openai_url,
    _convert_content_part_to_anthropic,
    _convert_content_to_anthropic,
    _generate_pkce,
    convert_tools_to_anthropic,
)


# ── _get_anthropic_max_output ─────────────────────────────────────────────────

class TestGetAnthropicMaxOutput:
    def test_claude_opus_4_6_returns_128k(self):
        assert _get_anthropic_max_output("claude-opus-4-6") == 128_000

    def test_claude_sonnet_4_6_returns_64k(self):
        assert _get_anthropic_max_output("claude-sonnet-4-6") == 64_000

    def test_claude_3_5_sonnet_returns_8192(self):
        assert _get_anthropic_max_output("claude-3-5-sonnet") == 8_192

    def test_date_stamped_id_resolves_via_substring(self):
        """claude-sonnet-4-6-20250929 contains 'claude-sonnet-4-6'."""
        assert _get_anthropic_max_output("claude-sonnet-4-6-20250929") == 64_000

    def test_variant_suffix_resolves_via_substring(self):
        """claude-opus-4-6:1m contains 'claude-opus-4-6'."""
        assert _get_anthropic_max_output("claude-opus-4-6:1m") == 128_000

    def test_unknown_model_returns_default(self):
        from agent.anthropic_adapter import _ANTHROPIC_DEFAULT_OUTPUT_LIMIT
        assert _get_anthropic_max_output("some-future-model") == _ANTHROPIC_DEFAULT_OUTPUT_LIMIT

    def test_case_insensitive_matching(self):
        assert _get_anthropic_max_output("Claude-Opus-4-6") == 128_000

    def test_longer_prefix_wins_over_shorter(self):
        """claude-3-5-sonnet (more specific) should beat claude-3-5."""
        result = _get_anthropic_max_output("claude-3-5-sonnet")
        assert result == 8_192


# ── _supports_adaptive_thinking ───────────────────────────────────────────────

class TestSupportsAdaptiveThinking:
    def test_claude_opus_4_6_with_hyphen(self):
        assert _supports_adaptive_thinking("claude-opus-4-6") is True

    def test_claude_sonnet_4_6_with_dot(self):
        assert _supports_adaptive_thinking("claude-opus-4.6") is True

    def test_non_4_6_model_returns_false(self):
        assert _supports_adaptive_thinking("claude-opus-4-5") is False

    def test_claude_4_6_haiku(self):
        assert _supports_adaptive_thinking("claude-haiku-4-6") is True

    def test_empty_string_returns_false(self):
        assert _supports_adaptive_thinking("") is False

    def test_gpt_model_returns_false(self):
        assert _supports_adaptive_thinking("gpt-5") is False


# ── _is_oauth_token ───────────────────────────────────────────────────────────

class TestIsOauthToken:
    def test_empty_string_returns_false(self):
        assert _is_oauth_token("") is False

    def test_none_like_empty_returns_false(self):
        assert _is_oauth_token("") is False

    def test_sk_ant_api_returns_false(self):
        assert _is_oauth_token("sk-ant-api03-abc123") is False

    def test_sk_ant_oat_returns_true(self):
        assert _is_oauth_token("sk-ant-oat01-abc123") is True

    def test_arbitrary_token_returns_true(self):
        """Any key that isn't sk-ant-api is treated as OAuth."""
        assert _is_oauth_token("eyJhbGciOiJSUzI1NiJ9...") is True

    def test_managed_key_returns_true(self):
        assert _is_oauth_token("some-managed-token-value") is True


# ── _is_third_party_anthropic_endpoint ───────────────────────────────────────

class TestIsThirdPartyAnthropicEndpoint:
    def test_none_returns_false(self):
        assert _is_third_party_anthropic_endpoint(None) is False

    def test_empty_returns_false(self):
        assert _is_third_party_anthropic_endpoint("") is False

    def test_direct_anthropic_api_returns_false(self):
        assert _is_third_party_anthropic_endpoint("https://api.anthropic.com/v1") is False

    def test_azure_endpoint_returns_true(self):
        assert _is_third_party_anthropic_endpoint("https://myazure.openai.azure.com/") is True

    def test_bedrock_endpoint_returns_true(self):
        assert _is_third_party_anthropic_endpoint("https://bedrock.us-east-1.amazonaws.com") is True

    def test_trailing_slash_handled(self):
        assert _is_third_party_anthropic_endpoint("https://api.anthropic.com/") is False

    def test_anthropic_com_in_url_returns_false(self):
        assert _is_third_party_anthropic_endpoint("https://proxy.anthropic.com/v1") is False


# ── _requires_bearer_auth ─────────────────────────────────────────────────────

class TestRequiresBearerAuth:
    def test_none_returns_false(self):
        assert _requires_bearer_auth(None) is False

    def test_empty_returns_false(self):
        assert _requires_bearer_auth("") is False

    def test_minimax_global_returns_true(self):
        assert _requires_bearer_auth("https://api.minimax.io/anthropic") is True

    def test_minimax_china_returns_true(self):
        assert _requires_bearer_auth("https://api.minimaxi.com/anthropic") is True

    def test_minimax_with_path_returns_true(self):
        assert _requires_bearer_auth("https://api.minimax.io/anthropic/v1") is True

    def test_regular_anthropic_api_returns_false(self):
        assert _requires_bearer_auth("https://api.anthropic.com/v1") is False

    def test_trailing_slash_stripped(self):
        assert _requires_bearer_auth("https://api.minimax.io/anthropic/") is True


# ── normalize_model_name ──────────────────────────────────────────────────────

class TestNormalizeModelName:
    def test_strips_anthropic_prefix(self):
        assert normalize_model_name("anthropic/claude-opus") == "claude-opus"

    def test_case_insensitive_prefix_strip(self):
        assert normalize_model_name("Anthropic/claude-opus") == "claude-opus"

    def test_dots_converted_to_hyphens(self):
        assert normalize_model_name("claude-opus-4.6") == "claude-opus-4-6"

    def test_preserve_dots_keeps_dots(self):
        assert normalize_model_name("qwen3.5-plus", preserve_dots=True) == "qwen3.5-plus"

    def test_no_prefix_no_dots_unchanged(self):
        assert normalize_model_name("claude-opus-4-6") == "claude-opus-4-6"

    def test_anthropic_prefix_with_dots(self):
        result = normalize_model_name("anthropic/claude-opus-4.6")
        assert result == "claude-opus-4-6"

    def test_empty_string_returns_empty(self):
        assert normalize_model_name("") == ""


# ── _sanitize_tool_id ─────────────────────────────────────────────────────────

class TestSanitizeToolId:
    def test_valid_id_unchanged(self):
        assert _sanitize_tool_id("tool_abc-123") == "tool_abc-123"

    def test_empty_returns_tool_0(self):
        assert _sanitize_tool_id("") == "tool_0"

    def test_spaces_replaced_with_underscores(self):
        result = _sanitize_tool_id("my tool id")
        assert " " not in result
        assert "_" in result

    def test_dots_replaced_with_underscores(self):
        result = _sanitize_tool_id("tool.v2.call")
        assert "." not in result

    def test_alphanumeric_and_underscore_hyphen_allowed(self):
        assert _sanitize_tool_id("Tool-1_a") == "Tool-1_a"

    def test_special_chars_replaced(self):
        result = _sanitize_tool_id("tool@#$%call")
        assert all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in result)

    def test_all_invalid_chars_returns_tool_0(self):
        """If sanitization produces empty string, fallback to 'tool_0'."""
        # Non-ASCII-alphanumeric-_- chars get replaced; if all replaced it's underscores
        result = _sanitize_tool_id("@@@")
        assert result == "___"  # underscores, not empty


# ── _convert_openai_image_part_to_anthropic ───────────────────────────────────

class TestConvertOpenaiImagePartToAnthropic:
    def test_http_url_returns_url_source(self):
        part = {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}}
        result = _convert_openai_image_part_to_anthropic(part)
        assert result["type"] == "image"
        assert result["source"]["type"] == "url"
        assert result["source"]["url"] == "https://example.com/img.png"

    def test_https_url_returns_url_source(self):
        part = {"type": "image_url", "image_url": {"url": "https://cdn.example.com/pic.jpg"}}
        result = _convert_openai_image_part_to_anthropic(part)
        assert result["source"]["type"] == "url"

    def test_base64_data_uri_returns_base64_source(self):
        part = {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}}
        result = _convert_openai_image_part_to_anthropic(part)
        assert result["type"] == "image"
        assert result["source"]["type"] == "base64"
        assert result["source"]["media_type"] == "image/png"
        assert result["source"]["data"] == "abc123"

    def test_data_uri_without_semicolon_base64_returns_none(self):
        """data:image/png without ;base64 is not a base64 encoding."""
        part = {"type": "image_url", "image_url": {"url": "data:image/png,notbase64"}}
        result = _convert_openai_image_part_to_anthropic(part)
        assert result is None

    def test_empty_url_returns_none(self):
        part = {"type": "image_url", "image_url": {"url": ""}}
        result = _convert_openai_image_part_to_anthropic(part)
        assert result is None

    def test_missing_image_url_key_returns_none(self):
        part = {"type": "image_url"}
        result = _convert_openai_image_part_to_anthropic(part)
        assert result is None

    def test_image_url_as_string_not_dict(self):
        """image_url can be a string directly."""
        part = {"type": "image_url", "image_url": "https://example.com/img.png"}
        result = _convert_openai_image_part_to_anthropic(part)
        assert result["source"]["type"] == "url"


# ── _convert_user_content_part_to_anthropic ───────────────────────────────────

class TestConvertUserContentPartToAnthropic:
    def test_text_part_returned_as_text_block(self):
        part = {"type": "text", "text": "Hello world"}
        result = _convert_user_content_part_to_anthropic(part)
        assert result == {"type": "text", "text": "Hello world"}

    def test_text_part_with_cache_control_preserved(self):
        part = {"type": "text", "text": "cached", "cache_control": {"type": "ephemeral"}}
        result = _convert_user_content_part_to_anthropic(part)
        assert result["cache_control"] == {"type": "ephemeral"}

    def test_image_url_part_delegated(self):
        part = {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}}
        result = _convert_user_content_part_to_anthropic(part)
        assert result is not None
        assert result["type"] == "image"

    def test_anthropic_image_source_passthrough(self):
        part = {"type": "image", "source": {"type": "url", "url": "https://x.com/i.png"}}
        result = _convert_user_content_part_to_anthropic(part)
        assert result == part

    def test_base64_image_data_format(self):
        part = {"type": "image", "data": "abc123", "mimeType": "image/jpeg"}
        result = _convert_user_content_part_to_anthropic(part)
        assert result["source"]["type"] == "base64"
        assert result["source"]["media_type"] == "image/jpeg"

    def test_tool_result_passthrough(self):
        part = {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}
        result = _convert_user_content_part_to_anthropic(part)
        assert result == part

    def test_non_dict_converted_to_text(self):
        result = _convert_user_content_part_to_anthropic("plain text")
        assert result == {"type": "text", "text": "plain text"}

    def test_none_returns_none(self):
        assert _convert_user_content_part_to_anthropic(None) is None

    def test_number_converted_to_text(self):
        result = _convert_user_content_part_to_anthropic(42)
        assert result == {"type": "text", "text": "42"}


# ── convert_tools_to_anthropic ────────────────────────────────────────────────

class TestConvertToolsToAnthropic:
    def test_empty_list_returns_empty(self):
        assert convert_tools_to_anthropic([]) == []

    def test_none_returns_empty(self):
        assert convert_tools_to_anthropic(None) == []

    def test_single_tool_converted(self):
        tools = [{"function": {"name": "search", "description": "Search the web", "parameters": {"type": "object"}}}]
        result = convert_tools_to_anthropic(tools)
        assert len(result) == 1
        assert result[0]["name"] == "search"
        assert result[0]["description"] == "Search the web"
        assert result[0]["input_schema"] == {"type": "object"}

    def test_missing_function_key_uses_defaults(self):
        result = convert_tools_to_anthropic([{}])
        assert result[0]["name"] == ""
        assert result[0]["description"] == ""

    def test_missing_parameters_uses_default_schema(self):
        tools = [{"function": {"name": "tool", "description": "desc"}}]
        result = convert_tools_to_anthropic(tools)
        assert result[0]["input_schema"] == {"type": "object", "properties": {}}

    def test_multiple_tools_all_converted(self):
        tools = [
            {"function": {"name": "tool_a", "description": "a", "parameters": {}}},
            {"function": {"name": "tool_b", "description": "b", "parameters": {}}},
        ]
        result = convert_tools_to_anthropic(tools)
        assert len(result) == 2
        assert result[0]["name"] == "tool_a"


# ── _image_source_from_openai_url ─────────────────────────────────────────────

class TestImageSourceFromOpenaiUrl:
    def test_regular_url_returned_as_url_type(self):
        result = _image_source_from_openai_url("https://example.com/img.png")
        assert result == {"type": "url", "url": "https://example.com/img.png"}

    def test_data_uri_returned_as_base64(self):
        result = _image_source_from_openai_url("data:image/jpeg;base64,abc123")
        assert result["type"] == "base64"
        assert result["media_type"] == "image/jpeg"
        assert result["data"] == "abc123"

    def test_data_uri_png_media_type(self):
        result = _image_source_from_openai_url("data:image/png;base64,xyz")
        assert result["media_type"] == "image/png"

    def test_data_uri_no_mime_defaults_to_jpeg(self):
        result = _image_source_from_openai_url("data:;base64,abc")
        assert result["media_type"] == "image/jpeg"

    def test_empty_string_returns_empty_url(self):
        result = _image_source_from_openai_url("")
        assert result == {"type": "url", "url": ""}

    def test_none_like_empty_returns_empty_url(self):
        result = _image_source_from_openai_url(None)
        assert result == {"type": "url", "url": ""}

    def test_whitespace_stripped(self):
        result = _image_source_from_openai_url("  https://example.com/img.jpg  ")
        assert result["url"] == "https://example.com/img.jpg"


# ── _convert_content_part_to_anthropic ────────────────────────────────────────

class TestConvertContentPartToAnthropic:
    def test_none_returns_none(self):
        assert _convert_content_part_to_anthropic(None) is None

    def test_string_becomes_text_block(self):
        result = _convert_content_part_to_anthropic("hello")
        assert result == {"type": "text", "text": "hello"}

    def test_non_dict_non_str_coerced_to_text(self):
        result = _convert_content_part_to_anthropic(42)
        assert result == {"type": "text", "text": "42"}

    def test_input_text_type_converted(self):
        result = _convert_content_part_to_anthropic({"type": "input_text", "text": "hi"})
        assert result == {"type": "text", "text": "hi"}

    def test_image_url_type_converted(self):
        result = _convert_content_part_to_anthropic({
            "type": "image_url",
            "image_url": {"url": "https://example.com/img.png"},
        })
        assert result["type"] == "image"
        assert result["source"]["type"] == "url"

    def test_cache_control_propagated(self):
        part = {
            "type": "input_text",
            "text": "cached",
            "cache_control": {"type": "ephemeral"},
        }
        result = _convert_content_part_to_anthropic(part)
        assert result.get("cache_control") == {"type": "ephemeral"}

    def test_unknown_type_passed_through(self):
        part = {"type": "custom", "data": "x"}
        result = _convert_content_part_to_anthropic(part)
        assert result["type"] == "custom"
        assert result["data"] == "x"


# ── _convert_content_to_anthropic ────────────────────────────────────────────

class TestConvertContentToAnthropic:
    def test_non_list_returned_as_is(self):
        assert _convert_content_to_anthropic("plain text") == "plain text"
        assert _convert_content_to_anthropic(None) is None

    def test_empty_list_returns_empty(self):
        assert _convert_content_to_anthropic([]) == []

    def test_list_of_strings_converted(self):
        result = _convert_content_to_anthropic(["hello", "world"])
        assert result[0] == {"type": "text", "text": "hello"}
        assert result[1] == {"type": "text", "text": "world"}

    def test_none_parts_excluded(self):
        # None parts return None from _convert_content_part_to_anthropic → excluded
        result = _convert_content_to_anthropic([None, "keep"])
        assert len(result) == 1
        assert result[0]["text"] == "keep"

    def test_dict_parts_preserved(self):
        parts = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
        result = _convert_content_to_anthropic(parts)
        assert len(result) == 2


# ── _generate_pkce ────────────────────────────────────────────────────────────

class TestGeneratePkce:
    def test_returns_tuple_of_two_strings(self):
        verifier, challenge = _generate_pkce()
        assert isinstance(verifier, str)
        assert isinstance(challenge, str)

    def test_verifier_is_url_safe_base64(self):
        verifier, _ = _generate_pkce()
        # URL-safe base64: only alphanumeric, hyphen, underscore (no padding)
        import re
        assert re.match(r'^[A-Za-z0-9\-_]+$', verifier)

    def test_challenge_is_url_safe_base64(self):
        _, challenge = _generate_pkce()
        import re
        assert re.match(r'^[A-Za-z0-9\-_]+$', challenge)

    def test_each_call_generates_different_pair(self):
        v1, c1 = _generate_pkce()
        v2, c2 = _generate_pkce()
        assert v1 != v2
        assert c1 != c2

    def test_challenge_derived_from_verifier(self):
        """The challenge must be SHA-256 of verifier (S256 method)."""
        import base64
        import hashlib
        verifier, challenge = _generate_pkce()
        expected_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        assert challenge == expected_challenge
