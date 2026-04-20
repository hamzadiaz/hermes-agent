"""Tests for pure helper functions in agent/copilot_acp_client.py.

Covers:
- _jsonrpc_error(): build a JSON-RPC 2.0 error response dict
- _render_message_content(): normalize content field to plain string
- _ensure_path_within_cwd(): validate absolute path stays within cwd
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from agent.copilot_acp_client import (
    _jsonrpc_error,
    _render_message_content,
    _ensure_path_within_cwd,
)


# ── _jsonrpc_error ────────────────────────────────────────────────────────────

class TestJsonrpcError:
    def test_structure(self):
        result = _jsonrpc_error(1, -32600, "Invalid Request")
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert result["error"]["code"] == -32600
        assert result["error"]["message"] == "Invalid Request"

    def test_none_id(self):
        result = _jsonrpc_error(None, -32700, "Parse error")
        assert result["id"] is None

    def test_string_id(self):
        result = _jsonrpc_error("req-123", -32601, "Method not found")
        assert result["id"] == "req-123"

    def test_is_json_serializable(self):
        result = _jsonrpc_error(42, -32000, "Server error")
        serialized = json.dumps(result)
        assert "jsonrpc" in serialized


# ── _render_message_content (copilot_acp variant) ─────────────────────────────
# Same logic as litert variant — verify independently to catch divergence.

class TestRenderMessageContent:
    def test_none_returns_empty(self):
        assert _render_message_content(None) == ""

    def test_string_stripped(self):
        assert _render_message_content("  hi  ") == "hi"

    def test_dict_text_key(self):
        assert _render_message_content({"text": "body"}) == "body"

    def test_dict_content_str_key(self):
        assert _render_message_content({"content": "body"}) == "body"

    def test_dict_no_known_keys_json(self):
        result = _render_message_content({"x": 1})
        assert json.loads(result) == {"x": 1}

    def test_list_items_joined(self):
        assert _render_message_content([{"text": "a"}, {"text": "b"}]) == "a\nb"

    def test_non_string_coerced(self):
        assert _render_message_content(99) == "99"


# ── _ensure_path_within_cwd ───────────────────────────────────────────────────

class TestEnsurePathWithinCwd:
    def test_valid_path_within_cwd(self, tmp_path):
        inner = tmp_path / "subdir" / "file.txt"
        result = _ensure_path_within_cwd(str(inner), str(tmp_path))
        assert result == inner.resolve()

    def test_relative_path_raises(self, tmp_path):
        with pytest.raises(PermissionError, match="absolute"):
            _ensure_path_within_cwd("relative/path.txt", str(tmp_path))

    def test_path_outside_cwd_raises(self, tmp_path):
        outside = "/tmp/outside.txt"
        with pytest.raises(PermissionError):
            _ensure_path_within_cwd(outside, str(tmp_path))

    def test_path_at_cwd_root_accepted(self, tmp_path):
        direct = tmp_path / "file.txt"
        result = _ensure_path_within_cwd(str(direct), str(tmp_path))
        assert result.parent.resolve() == tmp_path.resolve()

    def test_path_traversal_blocked(self, tmp_path):
        """/../ traversal outside cwd should raise."""
        traversal = str(tmp_path / "sub" / ".." / ".." / "etc" / "passwd")
        with pytest.raises(PermissionError):
            _ensure_path_within_cwd(traversal, str(tmp_path))
