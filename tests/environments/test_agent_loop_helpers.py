"""Tests for pure helper functions in environments/agent_loop.py.

Covers:
- _extract_reasoning_from_message(): extract reasoning text from various provider formats
"""

import pytest
from types import SimpleNamespace

from environments.agent_loop import _extract_reasoning_from_message


class TestExtractReasoningFromMessage:
    def test_none_message_returns_none(self):
        # SimpleNamespace with no attrs — no reasoning fields
        msg = SimpleNamespace()
        assert _extract_reasoning_from_message(msg) is None

    def test_reasoning_content_field_used(self):
        msg = SimpleNamespace(reasoning_content="chain of thought")
        assert _extract_reasoning_from_message(msg) == "chain of thought"

    def test_reasoning_field_used_when_no_reasoning_content(self):
        msg = SimpleNamespace(reasoning="some reasoning")
        assert _extract_reasoning_from_message(msg) == "some reasoning"

    def test_reasoning_content_preferred_over_reasoning(self):
        msg = SimpleNamespace(reasoning_content="rc value", reasoning="r value")
        assert _extract_reasoning_from_message(msg) == "rc value"

    def test_empty_reasoning_content_falls_through_to_reasoning(self):
        msg = SimpleNamespace(reasoning_content="", reasoning="fallback")
        assert _extract_reasoning_from_message(msg) == "fallback"

    def test_none_reasoning_content_falls_through(self):
        msg = SimpleNamespace(reasoning_content=None, reasoning="fallback")
        assert _extract_reasoning_from_message(msg) == "fallback"

    def test_reasoning_details_namespace_used(self):
        detail = SimpleNamespace(text="openrouter reasoning")
        msg = SimpleNamespace(reasoning_details=[detail])
        assert _extract_reasoning_from_message(msg) == "openrouter reasoning"

    def test_reasoning_details_dict_used(self):
        msg = SimpleNamespace(reasoning_details=[{"text": "dict reasoning"}])
        assert _extract_reasoning_from_message(msg) == "dict reasoning"

    def test_reasoning_details_first_with_text_returned(self):
        details = [
            SimpleNamespace(text=""),
            SimpleNamespace(text="second"),
        ]
        msg = SimpleNamespace(reasoning_details=details)
        # First item has empty text → skipped; second returned
        assert _extract_reasoning_from_message(msg) == "second"

    def test_empty_reasoning_details_returns_none(self):
        msg = SimpleNamespace(reasoning_details=[])
        assert _extract_reasoning_from_message(msg) is None

    def test_reasoning_details_no_text_field_returns_none(self):
        msg = SimpleNamespace(reasoning_details=[{"other": "data"}])
        assert _extract_reasoning_from_message(msg) is None

    def test_all_fields_missing_returns_none(self):
        msg = SimpleNamespace(content="plain answer")
        assert _extract_reasoning_from_message(msg) is None
