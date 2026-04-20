"""Tests for pure value-deserialization helpers in tool call parsers.

Covers:
- glm45_parser._deserialize_value(): json→literal_eval→raw-string fallback
- qwen3_coder_parser._try_convert_value(): null/json/literal_eval/string fallback
"""

import pytest

from environments.tool_call_parsers.glm45_parser import _deserialize_value
from environments.tool_call_parsers.qwen3_coder_parser import _try_convert_value
from environments.tool_call_parsers.mistral_parser import _generate_mistral_id


# ── _deserialize_value (glm45) ────────────────────────────────────────────────

class TestDeserializeValue:
    def test_json_integer(self):
        assert _deserialize_value("42") == 42

    def test_json_float(self):
        assert _deserialize_value("3.14") == 3.14

    def test_json_bool_true(self):
        assert _deserialize_value("true") is True

    def test_json_bool_false(self):
        assert _deserialize_value("false") is False

    def test_json_null_returns_none(self):
        assert _deserialize_value("null") is None

    def test_json_string(self):
        assert _deserialize_value('"hello"') == "hello"

    def test_json_dict(self):
        assert _deserialize_value('{"key": "val"}') == {"key": "val"}

    def test_json_list(self):
        assert _deserialize_value('[1, 2, 3]') == [1, 2, 3]

    def test_python_literal_tuple(self):
        result = _deserialize_value("(1, 2, 3)")
        assert result == (1, 2, 3)

    def test_plain_string_returned_as_is(self):
        assert _deserialize_value("hello world") == "hello world"

    def test_empty_string_returned_as_is(self):
        assert _deserialize_value("") == ""

    def test_whitespace_string_returned_as_is(self):
        assert _deserialize_value("   ") == "   "

    def test_invalid_json_and_literal_returned_as_is(self):
        result = _deserialize_value("{not valid json}")
        assert result == "{not valid json}"


# ── _try_convert_value (qwen3_coder) ─────────────────────────────────────────

class TestTryConvertValue:
    def test_null_literal_returns_none(self):
        assert _try_convert_value("null") is None

    def test_null_case_insensitive(self):
        assert _try_convert_value("NULL") is None
        assert _try_convert_value("Null") is None

    def test_json_integer(self):
        assert _try_convert_value("42") == 42

    def test_json_float(self):
        assert _try_convert_value("3.14") == 3.14

    def test_json_true(self):
        assert _try_convert_value("true") is True

    def test_json_false(self):
        assert _try_convert_value("false") is False

    def test_json_object(self):
        assert _try_convert_value('{"a": 1}') == {"a": 1}

    def test_json_array(self):
        assert _try_convert_value('[1, 2]') == [1, 2]

    def test_json_string_literal(self):
        assert _try_convert_value('"hello"') == "hello"

    def test_python_literal_tuple(self):
        result = _try_convert_value("(1, 2, 3)")
        assert result == (1, 2, 3)

    def test_whitespace_stripped_for_null(self):
        assert _try_convert_value("  null  ") is None

    def test_plain_string_returned_as_is(self):
        # Not valid JSON, not null, not literal — falls through to raw string
        assert _try_convert_value("hello world") == "hello world"

    def test_empty_string_behavior(self):
        # Empty string is not null/JSON, returned as-is
        result = _try_convert_value("")
        assert result == ""


# ── _generate_mistral_id ─────────────────────────────────────────────────────

class TestGenerateMistralId:
    def test_returns_string(self):
        assert isinstance(_generate_mistral_id(), str)

    def test_length_is_9(self):
        assert len(_generate_mistral_id()) == 9

    def test_alphanumeric_only(self):
        import string
        allowed = set(string.ascii_letters + string.digits)
        for _ in range(20):
            result = _generate_mistral_id()
            assert all(c in allowed for c in result), f"Non-alphanumeric char in {result!r}"

    def test_unique_ids_generated(self):
        ids = {_generate_mistral_id() for _ in range(50)}
        assert len(ids) > 40  # should be highly unique
