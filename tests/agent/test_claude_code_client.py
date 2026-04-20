"""Unit tests for claude_code_client.py — focuses on the MCP isolation fix.

These tests verify that _build_cmd injects an empty --mcp-config when Hermes
provides tool schemas, preventing user-installed MCP servers (e.g. the
superpowers Playwright plugin) from loading in the claude subprocess and
shadowing Hermes's XML tool protocol.
"""
import json
import os
import tempfile

import pytest


@pytest.fixture
def client():
    """Return a ClaudeCodeClient instance with a dummy command."""
    from agent.claude_code_client import ClaudeCodeClient

    return ClaudeCodeClient(api_key="test", base_url="cli://claude-code", command="claude")


SAMPLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
        },
    }
]


class TestBuildCmd:
    def test_no_tools_does_not_inject_mcp_config(self, client):
        cmd = client._build_cmd(prompt_text="hello", model=None, stream=False, tools=None)
        assert "--mcp-config" not in cmd

    def test_no_tools_does_not_inject_tools_flag(self, client):
        cmd = client._build_cmd(prompt_text="hello", model=None, stream=False, tools=None)
        assert "--tools" not in cmd

    def test_with_tools_injects_empty_tools_flag(self, client):
        cmd = client._build_cmd(prompt_text="hello", model=None, stream=False, tools=SAMPLE_TOOLS)
        assert "--tools" in cmd
        idx = cmd.index("--tools")
        assert cmd[idx + 1] == ""

    def test_with_tools_injects_mcp_config(self, client):
        cmd = client._build_cmd(prompt_text="hello", model=None, stream=False, tools=SAMPLE_TOOLS)
        assert "--mcp-config" in cmd

    def test_mcp_config_points_to_empty_json_file(self, client):
        cmd = client._build_cmd(prompt_text="hello", model=None, stream=False, tools=SAMPLE_TOOLS)
        idx = cmd.index("--mcp-config")
        path = cmd[idx + 1]
        assert os.path.isfile(path), "temp MCP config file must exist"
        with open(path) as f:
            data = json.load(f)
        assert data == {"mcpServers": {}}, "temp MCP config must be empty mcpServers dict"
        os.unlink(path)  # cleanup

    def test_mcp_config_filename_has_hermes_nomcp_prefix(self, client):
        cmd = client._build_cmd(prompt_text="hello", model=None, stream=False, tools=SAMPLE_TOOLS)
        idx = cmd.index("--mcp-config")
        path = cmd[idx + 1]
        assert "hermes_nomcp_" in path
        os.unlink(path)  # cleanup

    def test_model_injected_when_provided(self, client):
        cmd = client._build_cmd(
            prompt_text="hello", model="claude-opus-4-7", stream=False, tools=None
        )
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "claude-opus-4-7"

    def test_stream_mode_uses_stream_json_format(self, client):
        cmd = client._build_cmd(prompt_text="hello", model=None, stream=True, tools=None)
        assert "--output-format" in cmd
        idx = cmd.index("--output-format")
        assert cmd[idx + 1] == "stream-json"


class TestExtractMcpTmp:
    def test_returns_none_when_no_mcp_config(self, client):
        cmd = ["claude", "-p", "--output-format", "json", "hello"]
        assert client._extract_mcp_tmp(cmd) is None

    def test_returns_none_for_non_hermes_mcp_config(self, client):
        cmd = ["claude", "-p", "--mcp-config", "/other/path/settings.json", "hello"]
        assert client._extract_mcp_tmp(cmd) is None

    def test_returns_path_for_hermes_nomcp_file(self, client):
        cmd = ["claude", "-p", "--mcp-config", "/tmp/hermes_nomcp_abc123.json", "hello"]
        result = client._extract_mcp_tmp(cmd)
        assert result == "/tmp/hermes_nomcp_abc123.json"

    def test_returns_none_for_truncated_cmd(self, client):
        cmd = ["claude", "--mcp-config"]  # no path after --mcp-config
        assert client._extract_mcp_tmp(cmd) is None


class TestCleanupMcpTmp:
    def test_cleanup_removes_file(self, client):
        with tempfile.NamedTemporaryFile(delete=False, prefix="hermes_nomcp_", suffix=".json") as f:
            path = f.name
        assert os.path.isfile(path)
        client._cleanup_mcp_tmp(path)
        assert not os.path.isfile(path)

    def test_cleanup_ignores_none(self, client):
        # Should not raise
        client._cleanup_mcp_tmp(None)

    def test_cleanup_ignores_missing_file(self, client):
        # Should not raise even if file is already gone
        client._cleanup_mcp_tmp("/tmp/hermes_nomcp_does_not_exist.json")

    def test_build_cmd_then_extract_then_cleanup(self, client):
        """End-to-end: build → extract path → cleanup file."""
        cmd = client._build_cmd(
            prompt_text="test", model=None, stream=False, tools=SAMPLE_TOOLS
        )
        path = client._extract_mcp_tmp(cmd)
        assert path is not None
        assert os.path.isfile(path)
        client._cleanup_mcp_tmp(path)
        assert not os.path.isfile(path)
