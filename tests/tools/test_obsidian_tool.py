"""Tests for tools/obsidian_tool.py.

Covers:
- _get_vault_agent_name(): HERMES_HOME directory → vault agent name mapping
- _run_vault_cmd(): missing script, timeout, subprocess error, success/failure
- obsidian_checkpoint(): agent name resolution, success/failure paths
- obsidian_update_working_context(): file write, checkpoint log preservation, error path
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── _get_vault_agent_name ──────────────────────────────────────────────────────

class TestGetVaultAgentName:
    """tools/obsidian_tool.py — _get_vault_agent_name()"""

    def _call(self, home_path: Path):
        from tools.obsidian_tool import _get_vault_agent_name
        with patch("tools.obsidian_tool.get_hermes_home", return_value=home_path, create=True):
            with patch("tools.obsidian_tool.__builtins__", {}):
                pass
        # Patch via the module's import path
        with patch("hermes_constants.get_hermes_home", return_value=home_path):
            return _get_vault_agent_name()

    def test_mark_maps_to_marketing(self, tmp_path):
        home = tmp_path / "mark"
        home.mkdir()
        result = self._call(home)
        assert result == "Marketing"

    def test_malik_maps_correctly(self, tmp_path):
        home = tmp_path / "malik"
        home.mkdir()
        result = self._call(home)
        assert result == "Malik"

    def test_hermes_maps_to_hermes_core(self, tmp_path):
        home = tmp_path / "hermes"
        home.mkdir()
        result = self._call(home)
        assert result == "Hermes-Core"

    def test_hermes_agent_maps_to_hermes_core(self, tmp_path):
        home = tmp_path / "hermes-agent"
        home.mkdir()
        result = self._call(home)
        assert result == "Hermes-Core"

    def test_buni_maps_to_boone(self, tmp_path):
        home = tmp_path / "buni"
        home.mkdir()
        result = self._call(home)
        assert result == "Boone"

    def test_unknown_agent_returns_none(self, tmp_path):
        home = tmp_path / "unknownagent"
        home.mkdir()
        result = self._call(home)
        assert result is None

    def test_dotfile_prefix_stripped(self, tmp_path):
        """Leading dots are stripped — .hermes-agent → hermes-agent → Hermes-Core."""
        home = tmp_path / ".hermes-agent"
        home.mkdir()
        result = self._call(home)
        assert result == "Hermes-Core"

    def test_exception_returns_none(self):
        """If get_hermes_home() raises, _get_vault_agent_name returns None silently."""
        from tools.obsidian_tool import _get_vault_agent_name
        with patch("hermes_constants.get_hermes_home", side_effect=RuntimeError("no home")):
            result = _get_vault_agent_name()
        assert result is None


# ── _run_vault_cmd ─────────────────────────────────────────────────────────────

class TestRunVaultCmd:
    """tools/obsidian_tool.py — _run_vault_cmd()"""

    def test_missing_script_returns_error(self, tmp_path):
        """When VAULT_TOOLS_SCRIPT doesn't exist, returns ok=False immediately."""
        from tools.obsidian_tool import _run_vault_cmd
        with patch("tools.obsidian_tool.VAULT_TOOLS_SCRIPT", tmp_path / "missing.py"):
            result = _run_vault_cmd("checkpoint")
        assert result["ok"] is False
        assert "missing" in result["error"].lower() or "Vault tools script" in result["error"]

    def test_successful_subprocess_returns_ok_true(self, tmp_path):
        """When subprocess exits 0, returns ok=True with output."""
        fake_script = tmp_path / "vault_tools.py"
        fake_script.write_text("print('done')")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "checkpoint written\n"
        mock_result.stderr = ""
        from tools.obsidian_tool import _run_vault_cmd
        with patch("tools.obsidian_tool.VAULT_TOOLS_SCRIPT", fake_script):
            with patch("subprocess.run", return_value=mock_result):
                result = _run_vault_cmd("checkpoint", "--agent", "Hermes-Core")
        assert result["ok"] is True
        assert result["output"] == "checkpoint written"

    def test_failed_subprocess_returns_ok_false(self, tmp_path):
        """When subprocess exits non-0, returns ok=False with stderr."""
        fake_script = tmp_path / "vault_tools.py"
        fake_script.write_text("")
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "vault path not found"
        from tools.obsidian_tool import _run_vault_cmd
        with patch("tools.obsidian_tool.VAULT_TOOLS_SCRIPT", fake_script):
            with patch("subprocess.run", return_value=mock_result):
                result = _run_vault_cmd("checkpoint")
        assert result["ok"] is False
        assert "vault path not found" in result["error"]

    def test_timeout_returns_ok_false(self, tmp_path):
        """TimeoutExpired is caught and returns ok=False."""
        fake_script = tmp_path / "vault_tools.py"
        fake_script.write_text("")
        from tools.obsidian_tool import _run_vault_cmd
        with patch("tools.obsidian_tool.VAULT_TOOLS_SCRIPT", fake_script):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=15)):
                result = _run_vault_cmd("checkpoint", timeout=1)
        assert result["ok"] is False
        assert "timed out" in result["error"].lower()

    def test_generic_exception_returns_ok_false(self, tmp_path):
        """Generic Exception is caught and returned as ok=False."""
        fake_script = tmp_path / "vault_tools.py"
        fake_script.write_text("")
        from tools.obsidian_tool import _run_vault_cmd
        with patch("tools.obsidian_tool.VAULT_TOOLS_SCRIPT", fake_script):
            with patch("subprocess.run", side_effect=OSError("permission denied")):
                result = _run_vault_cmd("checkpoint")
        assert result["ok"] is False
        assert "permission denied" in result["error"]


# ── obsidian_checkpoint ────────────────────────────────────────────────────────

class TestObsidianCheckpoint:
    """tools/obsidian_tool.py — obsidian_checkpoint()"""

    def test_missing_agent_name_returns_error(self):
        """When agent can't be determined and no override, returns success=False."""
        from tools.obsidian_tool import obsidian_checkpoint
        with patch("tools.obsidian_tool._get_vault_agent_name", return_value=None):
            result = json.loads(obsidian_checkpoint(event="test", note="testing"))
        assert result["success"] is False
        assert "vault agent name" in result["error"].lower()

    def test_explicit_agent_override_skips_auto_detect(self):
        """Passing agent= bypasses _get_vault_agent_name."""
        from tools.obsidian_tool import obsidian_checkpoint
        with patch("tools.obsidian_tool._run_vault_cmd", return_value={"ok": True}):
            result = json.loads(obsidian_checkpoint(event="done", note="ok", agent="Hermes-Core"))
        assert result["success"] is True
        assert result["agent"] == "Hermes-Core"

    def test_run_vault_cmd_failure_returns_error(self):
        """When _run_vault_cmd fails, obsidian_checkpoint returns success=False."""
        from tools.obsidian_tool import obsidian_checkpoint
        with patch("tools.obsidian_tool._get_vault_agent_name", return_value="Hermes-Core"):
            with patch("tools.obsidian_tool._run_vault_cmd",
                       return_value={"ok": False, "error": "vault locked"}):
                result = json.loads(obsidian_checkpoint(event="done", note="ok"))
        assert result["success"] is False
        assert "vault locked" in result["error"]

    def test_success_returns_event_and_agent(self):
        """Successful checkpoint returns event label and agent name."""
        from tools.obsidian_tool import obsidian_checkpoint
        with patch("tools.obsidian_tool._get_vault_agent_name", return_value="Alex"):
            with patch("tools.obsidian_tool._run_vault_cmd", return_value={"ok": True}):
                result = json.loads(obsidian_checkpoint(event="milestone", note="shipped!"))
        assert result["success"] is True
        assert result["event"] == "milestone"
        assert result["agent"] == "Alex"


# ── obsidian_update_working_context ───────────────────────────────────────────

class TestObsidianUpdateWorkingContext:
    """tools/obsidian_tool.py — obsidian_update_working_context()"""

    def test_missing_agent_name_returns_error(self):
        from tools.obsidian_tool import obsidian_update_working_context
        with patch("tools.obsidian_tool._get_vault_agent_name", return_value=None):
            result = json.loads(obsidian_update_working_context(
                current_goal="test", last_action="tested", next_steps="1. done"
            ))
        assert result["success"] is False

    def test_writes_file_and_returns_success(self, tmp_path):
        """Working context is written to vault path and success returned."""
        from tools.obsidian_tool import obsidian_update_working_context, VAULT_PATH
        fake_vault = tmp_path / "vault"
        agent_dir = fake_vault / "03-Agent-Private" / "Hermes-Core"
        agent_dir.mkdir(parents=True)

        with patch("tools.obsidian_tool.VAULT_PATH", fake_vault):
            with patch("tools.obsidian_tool._get_vault_agent_name", return_value="Hermes-Core"):
                result = json.loads(obsidian_update_working_context(
                    current_goal="Stabilize Hermes",
                    last_action="Fixed xdist contamination",
                    next_steps="1. Verify\n2. Commit",
                    open_questions="None",
                ))

        assert result["success"] is True
        wc_path = agent_dir / "working-context.md"
        assert wc_path.exists()
        content = wc_path.read_text()
        assert "Stabilize Hermes" in content
        assert "Fixed xdist contamination" in content
        assert "1. Verify" in content

    def test_preserves_existing_checkpoint_log(self, tmp_path):
        """Existing checkpoint log section is preserved when updating working context."""
        from tools.obsidian_tool import obsidian_update_working_context
        fake_vault = tmp_path / "vault"
        agent_dir = fake_vault / "03-Agent-Private" / "Hermes-Core"
        agent_dir.mkdir(parents=True)
        wc_path = agent_dir / "working-context.md"
        existing = (
            "# Hermes-Core Working Context\n"
            "*Last updated: 2026-04-19 10:00*\n\n"
            "## Current Goal\nOld goal\n\n"
            "## Checkpoint Log\n- 2026-04-19: session_end — all good\n"
        )
        wc_path.write_text(existing)

        with patch("tools.obsidian_tool.VAULT_PATH", fake_vault):
            with patch("tools.obsidian_tool._get_vault_agent_name", return_value="Hermes-Core"):
                result = json.loads(obsidian_update_working_context(
                    current_goal="New goal",
                    last_action="Updated",
                    next_steps="1. Continue",
                ))

        assert result["success"] is True
        content = wc_path.read_text()
        # Old log entry must survive
        assert "2026-04-19: session_end — all good" in content
        # New goal must be present
        assert "New goal" in content

    def test_creates_parent_directories(self, tmp_path):
        """Parent directories are created if they don't exist."""
        from tools.obsidian_tool import obsidian_update_working_context
        fake_vault = tmp_path / "vault"
        # Don't pre-create agent_dir — mkdir(parents=True, exist_ok=True) should handle it

        with patch("tools.obsidian_tool.VAULT_PATH", fake_vault):
            with patch("tools.obsidian_tool._get_vault_agent_name", return_value="Hermes-Core"):
                result = json.loads(obsidian_update_working_context(
                    current_goal="test",
                    last_action="tested",
                    next_steps="1. done",
                ))

        assert result["success"] is True
        assert (fake_vault / "03-Agent-Private" / "Hermes-Core" / "working-context.md").exists()

    def test_os_error_returns_failure(self, tmp_path):
        """When file write fails, returns success=False with error message."""
        from tools.obsidian_tool import obsidian_update_working_context
        fake_vault = tmp_path / "vault"

        with patch("tools.obsidian_tool.VAULT_PATH", fake_vault):
            with patch("tools.obsidian_tool._get_vault_agent_name", return_value="Hermes-Core"):
                with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
                    with patch("pathlib.Path.mkdir"):
                        with patch("pathlib.Path.exists", return_value=False):
                            result = json.loads(obsidian_update_working_context(
                                current_goal="test",
                                last_action="tested",
                                next_steps="1. done",
                            ))

        assert result["success"] is False
        assert "disk full" in result["error"]
