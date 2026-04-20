"""Tests for tools/session_search_tool.py — helper functions and search dispatcher."""

import json
import time
import pytest

from tools.session_search_tool import (
    _format_timestamp,
    _format_conversation,
    _truncate_around_matches,
    _HIDDEN_SESSION_SOURCES,
    MAX_SESSION_CHARS,
    SESSION_SEARCH_SCHEMA,
)


# =========================================================================
# Tool schema guidance
# =========================================================================

class TestHiddenSessionSources:
    """Verify the _HIDDEN_SESSION_SOURCES constant used for third-party isolation."""

    def test_tool_source_is_hidden(self):
        assert "tool" in _HIDDEN_SESSION_SOURCES

    def test_standard_sources_not_hidden(self):
        for src in ("cli", "telegram", "discord", "slack", "cron"):
            assert src not in _HIDDEN_SESSION_SOURCES


class TestSessionSearchSchema:
    def test_keeps_cross_session_recall_guidance_without_current_session_nudge(self):
        description = SESSION_SEARCH_SCHEMA["description"]
        assert "past conversations" in description
        assert "recent turns of the current session" not in description


# =========================================================================
# _format_timestamp
# =========================================================================

class TestFormatTimestamp:
    def test_unix_float(self):
        ts = 1700000000.0  # Nov 14, 2023
        result = _format_timestamp(ts)
        assert "2023" in result or "November" in result

    def test_unix_int(self):
        result = _format_timestamp(1700000000)
        assert isinstance(result, str)
        assert len(result) > 5

    def test_iso_string(self):
        result = _format_timestamp("2024-01-15T10:30:00")
        assert isinstance(result, str)

    def test_none_returns_unknown(self):
        assert _format_timestamp(None) == "unknown"

    def test_numeric_string(self):
        result = _format_timestamp("1700000000.0")
        assert isinstance(result, str)
        assert "unknown" not in result.lower()


# =========================================================================
# _format_conversation
# =========================================================================

class TestFormatConversation:
    def test_basic_messages(self):
        msgs = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = _format_conversation(msgs)
        assert "[USER]: Hello" in result
        assert "[ASSISTANT]: Hi there!" in result

    def test_tool_message(self):
        msgs = [
            {"role": "tool", "content": "search results", "tool_name": "web_search"},
        ]
        result = _format_conversation(msgs)
        assert "[TOOL:web_search]" in result

    def test_long_tool_output_truncated(self):
        msgs = [
            {"role": "tool", "content": "x" * 1000, "tool_name": "terminal"},
        ]
        result = _format_conversation(msgs)
        assert "[truncated]" in result

    def test_assistant_with_tool_calls(self):
        msgs = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "web_search"}},
                    {"function": {"name": "terminal"}},
                ],
            },
        ]
        result = _format_conversation(msgs)
        assert "web_search" in result
        assert "terminal" in result

    def test_empty_messages(self):
        result = _format_conversation([])
        assert result == ""


# =========================================================================
# _truncate_around_matches
# =========================================================================

class TestTruncateAroundMatches:
    def test_short_text_unchanged(self):
        text = "Short text about docker"
        result = _truncate_around_matches(text, "docker")
        assert result == text

    def test_long_text_truncated(self):
        # Create text longer than MAX_SESSION_CHARS with query term in middle
        padding = "x" * (MAX_SESSION_CHARS + 5000)
        text = padding + " KEYWORD_HERE " + padding
        result = _truncate_around_matches(text, "KEYWORD_HERE")
        assert len(result) <= MAX_SESSION_CHARS + 100  # +100 for prefix/suffix markers
        assert "KEYWORD_HERE" in result

    def test_truncation_adds_markers(self):
        text = "a" * 50000 + " target " + "b" * (MAX_SESSION_CHARS + 5000)
        result = _truncate_around_matches(text, "target")
        assert "truncated" in result.lower()

    def test_no_match_takes_from_start(self):
        text = "x" * (MAX_SESSION_CHARS + 5000)
        result = _truncate_around_matches(text, "nonexistent")
        # Should take from the beginning
        assert result.startswith("x")

    def test_match_at_beginning(self):
        text = "KEYWORD " + "x" * (MAX_SESSION_CHARS + 5000)
        result = _truncate_around_matches(text, "KEYWORD")
        assert "KEYWORD" in result


# =========================================================================
# session_search (dispatcher)
# =========================================================================

class TestSessionSearch:
    def test_no_db_returns_error(self):
        from tools.session_search_tool import session_search
        result = json.loads(session_search(query="test"))
        assert result["success"] is False
        assert "not available" in result["error"].lower()

    def test_empty_query_no_db_returns_error(self):
        from tools.session_search_tool import session_search
        result = json.loads(session_search(query="", db=None))
        assert result["success"] is False
        assert "not available" in result["error"].lower()

    def test_whitespace_query_no_db_returns_error(self):
        from tools.session_search_tool import session_search
        result = json.loads(session_search(query="   ", db=None))
        assert result["success"] is False
        assert "not available" in result["error"].lower()

    def test_current_session_excluded(self):
        """session_search should never return the current session."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        current_sid = "20260304_120000_abc123"

        # Simulate FTS5 returning matches only from the current session
        mock_db.search_messages.return_value = [
            {"session_id": current_sid, "content": "test match", "source": "cli",
             "session_started": 1709500000, "model": "test"},
        ]
        mock_db.get_session.return_value = {"parent_session_id": None}

        result = json.loads(session_search(
            query="test", db=mock_db, current_session_id=current_sid,
        ))
        assert result["success"] is True
        assert result["count"] == 0
        assert result["results"] == []

    def test_current_session_excluded_keeps_others(self):
        """Other sessions should still be returned when current is excluded."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        current_sid = "20260304_120000_abc123"
        other_sid = "20260303_100000_def456"

        mock_db.search_messages.return_value = [
            {"session_id": current_sid, "content": "match 1", "source": "cli",
             "session_started": 1709500000, "model": "test"},
            {"session_id": other_sid, "content": "match 2", "source": "telegram",
             "session_started": 1709400000, "model": "test"},
        ]
        mock_db.get_session.return_value = {"parent_session_id": None}
        mock_db.get_messages_as_conversation.return_value = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]

        # Mock async_call_llm to raise RuntimeError → summarizer returns None
        from unittest.mock import AsyncMock, patch as _patch
        with _patch("tools.session_search_tool.async_call_llm",
                     new_callable=AsyncMock,
                     side_effect=RuntimeError("no provider")):
            result = json.loads(session_search(
                query="test", db=mock_db, current_session_id=current_sid,
            ))

        assert result["success"] is True
        # Current session should be skipped, only other_sid should appear
        assert result["sessions_searched"] == 1
        assert current_sid not in [r.get("session_id") for r in result.get("results", [])]

    def test_current_child_session_excludes_parent_lineage(self):
        """Compression/delegation parents should be excluded for the active child session."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = [
            {"session_id": "parent_sid", "content": "match", "source": "cli",
             "session_started": 1709500000, "model": "test"},
        ]

        def _get_session(session_id):
            if session_id == "child_sid":
                return {"parent_session_id": "parent_sid"}
            if session_id == "parent_sid":
                return {"parent_session_id": None}
            return None

        mock_db.get_session.side_effect = _get_session

        result = json.loads(session_search(
            query="test", db=mock_db, current_session_id="child_sid",
        ))

        assert result["success"] is True
        assert result["count"] == 0
        assert result["results"] == []
        assert result["sessions_searched"] == 0

    def test_most_recent_session_injected_when_absent_from_keyword_results(self):
        """Keyword search should always include the most recent session even if it
        doesn't match the query — prevents memory-biased queries from hiding the
        latest work (recency regression: 'what did we last do' returned 6-hour-old
        session instead of the terminal check 6 minutes prior)."""
        from unittest.mock import MagicMock, AsyncMock, patch as _patch
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        current_sid = "20260304_120000_current"
        keyword_match_sid = "20260303_100000_keyword_match"   # 6 hours ago
        most_recent_sid = "20260304_115500_most_recent"       # 6 minutes ago

        # FTS5 only finds the old session (keyword-biased query)
        mock_db.search_messages.return_value = [
            {"session_id": keyword_match_sid, "content": "stale agent fix gateway",
             "source": "telegram", "session_started": 1709400000, "model": "test"},
        ]

        def _get_session(sid):
            return {"parent_session_id": None}

        mock_db.get_session.side_effect = _get_session
        mock_db.get_messages_as_conversation.return_value = [
            {"role": "user", "content": "verify terminal"},
            {"role": "assistant", "content": "Yes, terminal available."},
        ]

        # list_sessions_rich returns most_recent first, then keyword_match
        mock_db.list_sessions_rich.return_value = [
            {"id": most_recent_sid, "source": "telegram",
             "started_at": 1709499600, "model": "test", "parent_session_id": None},
            {"id": keyword_match_sid, "source": "telegram",
             "started_at": 1709400000, "model": "test", "parent_session_id": None},
        ]

        with _patch("tools.session_search_tool.async_call_llm",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("no provider")):
            result = json.loads(session_search(
                query="stale agent fix OR gateway",
                db=mock_db,
                current_session_id=current_sid,
                limit=3,
            ))

        assert result["success"] is True
        session_ids = [r["session_id"] for r in result["results"]]
        # Most recent session must appear in results even though it didn't match the query
        assert most_recent_sid in session_ids, (
            f"Most recent session {most_recent_sid} missing from results: {session_ids}"
        )
        # It should be the first result (injected at position 0)
        assert session_ids[0] == most_recent_sid
        # It should be flagged as most_recent
        most_recent_entry = next(r for r in result["results"] if r["session_id"] == most_recent_sid)
        assert most_recent_entry.get("most_recent") is True

    def test_current_root_session_excludes_child_lineage(self):
        """Delegation child hits should be excluded when they resolve to the current root session."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = [
            {"session_id": "child_sid", "content": "match", "source": "cli",
             "session_started": 1709500000, "model": "test"},
        ]

        def _get_session(session_id):
            if session_id == "root_sid":
                return {"parent_session_id": None}
            if session_id == "child_sid":
                return {"parent_session_id": "root_sid"}
            return None

        mock_db.get_session.side_effect = _get_session

        result = json.loads(session_search(
            query="test", db=mock_db, current_session_id="root_sid",
        ))

        assert result["success"] is True
        assert result["count"] == 0
        assert result["results"] == []
        assert result["sessions_searched"] == 0

    def test_recency_injection_skips_current_session_uses_next_most_recent(self):
        """If the most recent session IS the current session, inject the next-most-recent instead."""
        from unittest.mock import MagicMock, AsyncMock, patch as _patch
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        current_sid = "20260304_120000_current"
        second_recent_sid = "20260304_110000_second"
        keyword_match_sid = "20260303_100000_keyword"

        mock_db.search_messages.return_value = [
            {"session_id": keyword_match_sid, "content": "agent gateway",
             "source": "telegram", "session_started": 1709400000, "model": "test"},
        ]

        def _get_session(sid):
            return {"parent_session_id": None}

        mock_db.get_session.side_effect = _get_session
        mock_db.get_messages_as_conversation.return_value = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]

        # list_sessions_rich: current session is first (most recent), second_recent next
        mock_db.list_sessions_rich.return_value = [
            {"id": current_sid, "source": "telegram",
             "started_at": 1709503600, "model": "test", "parent_session_id": None},
            {"id": second_recent_sid, "source": "telegram",
             "started_at": 1709500000, "model": "test", "parent_session_id": None},
            {"id": keyword_match_sid, "source": "telegram",
             "started_at": 1709400000, "model": "test", "parent_session_id": None},
        ]

        with _patch("tools.session_search_tool.async_call_llm",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("no provider")):
            result = json.loads(session_search(
                query="agent gateway",
                db=mock_db,
                current_session_id=current_sid,
                limit=3,
            ))

        assert result["success"] is True
        session_ids = [r["session_id"] for r in result["results"]]
        # Current session must NOT appear
        assert current_sid not in session_ids
        # Second-most-recent must be injected (most recent non-current)
        assert second_recent_sid in session_ids
        assert session_ids[0] == second_recent_sid

    def test_recency_injection_silently_skips_on_list_sessions_rich_error(self):
        """If list_sessions_rich raises, recency injection fails silently and keyword results are returned."""
        from unittest.mock import MagicMock, AsyncMock, patch as _patch
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        current_sid = "20260304_120000_current"
        keyword_match_sid = "20260303_100000_keyword"

        mock_db.search_messages.return_value = [
            {"session_id": keyword_match_sid, "content": "match",
             "source": "telegram", "session_started": 1709400000, "model": "test"},
        ]

        def _get_session(sid):
            return {"parent_session_id": None}

        mock_db.get_session.side_effect = _get_session
        mock_db.get_messages_as_conversation.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_db.list_sessions_rich.side_effect = RuntimeError("db locked")

        with _patch("tools.session_search_tool.async_call_llm",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("no provider")):
            result = json.loads(session_search(
                query="match",
                db=mock_db,
                current_session_id=current_sid,
                limit=3,
            ))

        # Keyword results should still be returned despite injection failure
        assert result["success"] is True
        session_ids = [r["session_id"] for r in result["results"]]
        assert keyword_match_sid in session_ids

    def test_recency_injection_skipped_when_all_candidates_are_children(self):
        """If all non-current sessions are children, no session is injected into keyword results."""
        from unittest.mock import MagicMock, AsyncMock, patch as _patch
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        current_sid = "20260304_120000_current"
        keyword_match_sid = "20260303_100000_keyword"
        child_sid = "20260304_115900_child"
        parent_of_child = "20260304_100000_parent"

        mock_db.search_messages.return_value = [
            {"session_id": keyword_match_sid, "content": "match",
             "source": "telegram", "session_started": 1709400000, "model": "test"},
        ]

        def _get_session(sid):
            if sid == child_sid:
                return {"parent_session_id": parent_of_child}
            return {"parent_session_id": None}

        mock_db.get_session.side_effect = _get_session
        mock_db.get_messages_as_conversation.return_value = [
            {"role": "user", "content": "hello"},
        ]

        # list_sessions_rich returns only child sessions (all have parent_session_id set)
        mock_db.list_sessions_rich.return_value = [
            {"id": child_sid, "source": "telegram",
             "started_at": 1709503500, "model": "test", "parent_session_id": parent_of_child},
        ]

        with _patch("tools.session_search_tool.async_call_llm",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("no provider")):
            result = json.loads(session_search(
                query="match",
                db=mock_db,
                current_session_id=current_sid,
                limit=3,
            ))

        # child_sid should not be injected
        assert result["success"] is True
        session_ids = [r["session_id"] for r in result["results"]]
        assert child_sid not in session_ids
        # Only the keyword match appears
        assert keyword_match_sid in session_ids


class TestRecentSessionsMode:
    """Tests for the empty-query (recent sessions) path via _list_recent_sessions."""

    def _make_db(self, sessions):
        """Return a mock DB whose list_sessions_rich returns the given sessions."""
        from unittest.mock import MagicMock
        mock_db = MagicMock()
        mock_db.list_sessions_rich.return_value = sessions
        mock_db.get_session.return_value = {"parent_session_id": None}
        return mock_db

    def test_empty_query_returns_recent_mode(self):
        from tools.session_search_tool import session_search
        mock_db = self._make_db([
            {"id": "sid1", "source": "telegram", "started_at": 1709500000,
             "last_active": 1709500100, "message_count": 5, "title": "hello",
             "preview": "hi there", "parent_session_id": None},
        ])
        result = json.loads(session_search(query="", db=mock_db))
        assert result["success"] is True
        assert result["mode"] == "recent"
        assert result["count"] == 1
        assert result["results"][0]["session_id"] == "sid1"

    def test_whitespace_query_returns_recent_mode(self):
        from tools.session_search_tool import session_search
        mock_db = self._make_db([
            {"id": "sid1", "source": "cli", "started_at": 1709500000,
             "last_active": 1709500000, "message_count": 3, "title": None,
             "preview": "test", "parent_session_id": None},
        ])
        result = json.loads(session_search(query="   ", db=mock_db))
        assert result["success"] is True
        assert result["mode"] == "recent"

    def test_recent_mode_excludes_current_session(self):
        """The current session should not appear in recent sessions results."""
        from tools.session_search_tool import session_search
        current_sid = "20260420_090000_current"
        other_sid = "20260420_080000_other"
        mock_db = self._make_db([
            {"id": current_sid, "source": "telegram", "started_at": 1709500100,
             "last_active": 1709500100, "message_count": 2, "title": None,
             "preview": "", "parent_session_id": None},
            {"id": other_sid, "source": "telegram", "started_at": 1709500000,
             "last_active": 1709500000, "message_count": 4, "title": "other",
             "preview": "prev", "parent_session_id": None},
        ])
        result = json.loads(session_search(query="", db=mock_db, current_session_id=current_sid))
        assert result["success"] is True
        session_ids = [r["session_id"] for r in result["results"]]
        assert current_sid not in session_ids
        assert other_sid in session_ids

    def test_recent_mode_excludes_child_sessions(self):
        """Sessions that are compression/delegation children should be skipped."""
        from tools.session_search_tool import session_search
        parent_sid = "20260420_080000_parent"
        child_sid = "20260420_085000_child"
        mock_db = self._make_db([
            {"id": child_sid, "source": "telegram", "started_at": 1709500100,
             "last_active": 1709500100, "message_count": 1, "title": None,
             "preview": "", "parent_session_id": parent_sid},  # child — excluded
            {"id": parent_sid, "source": "telegram", "started_at": 1709500000,
             "last_active": 1709500000, "message_count": 5, "title": "root",
             "preview": "content", "parent_session_id": None},
        ])
        result = json.loads(session_search(query="", db=mock_db))
        assert result["success"] is True
        session_ids = [r["session_id"] for r in result["results"]]
        assert child_sid not in session_ids
        assert parent_sid in session_ids
