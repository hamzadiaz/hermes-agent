"""Tests for pure helper functions in gateway/channel_directory.py.

Covers:
- _session_entry_id(): extract session ID from origin dict (with optional thread_id)
- _session_entry_name(): build human-readable display name from origin dict
"""

import pytest

from gateway.channel_directory import _session_entry_id, _session_entry_name


# ── _session_entry_id ─────────────────────────────────────────────────────────

class TestSessionEntryId:
    def test_empty_origin_returns_none(self):
        assert _session_entry_id({}) is None

    def test_no_chat_id_returns_none(self):
        assert _session_entry_id({"user_name": "alice"}) is None

    def test_chat_id_only_returned_as_string(self):
        assert _session_entry_id({"chat_id": 12345}) == "12345"

    def test_string_chat_id_returned(self):
        assert _session_entry_id({"chat_id": "chan-1"}) == "chan-1"

    def test_chat_id_with_thread_id_combined(self):
        result = _session_entry_id({"chat_id": "c1", "thread_id": "t42"})
        assert result == "c1:t42"

    def test_zero_thread_id_included(self):
        """thread_id=0 is falsy — should not be included."""
        result = _session_entry_id({"chat_id": "c1", "thread_id": 0})
        assert result == "c1"

    def test_empty_thread_id_not_included(self):
        result = _session_entry_id({"chat_id": "c1", "thread_id": ""})
        assert result == "c1"

    def test_numeric_chat_id_converted_to_str(self):
        assert _session_entry_id({"chat_id": 999, "thread_id": "t1"}) == "999:t1"


# ── _session_entry_name ───────────────────────────────────────────────────────

class TestSessionEntryName:
    def test_chat_name_used(self):
        origin = {"chat_id": "1", "chat_name": "General"}
        assert _session_entry_name(origin) == "General"

    def test_user_name_fallback(self):
        origin = {"chat_id": "1", "user_name": "Alice"}
        assert _session_entry_name(origin) == "Alice"

    def test_chat_name_preferred_over_user_name(self):
        origin = {"chat_id": "1", "chat_name": "Group", "user_name": "User"}
        assert _session_entry_name(origin) == "Group"

    def test_chat_id_str_fallback_when_no_names(self):
        origin = {"chat_id": 42}
        assert _session_entry_name(origin) == "42"

    def test_thread_id_appends_topic_label(self):
        origin = {
            "chat_id": "c1",
            "chat_name": "Project",
            "thread_id": "t5",
            "chat_topic": "Sprint Review",
        }
        result = _session_entry_name(origin)
        assert result == "Project / Sprint Review"

    def test_thread_id_without_topic_uses_default_label(self):
        origin = {
            "chat_id": "c1",
            "chat_name": "Project",
            "thread_id": "t5",
        }
        result = _session_entry_name(origin)
        assert result == "Project / topic t5"

    def test_no_thread_id_returns_base_name_only(self):
        origin = {"chat_id": "c1", "chat_name": "General", "chat_topic": "ignored"}
        assert _session_entry_name(origin) == "General"

    def test_zero_thread_id_not_appended(self):
        """thread_id=0 is falsy."""
        origin = {"chat_id": "c1", "chat_name": "Group", "thread_id": 0}
        assert _session_entry_name(origin) == "Group"
