"""Tests for pure helper functions in tools/terminal_tool.py.

Covers:
- _handle_sudo_failure(): add tip message when sudo fails in gateway context
- _transform_sudo_command(): inject sudo -S flag when password is available
"""

import pytest

from tools.terminal_tool import _handle_sudo_failure, _transform_sudo_command


# ── _handle_sudo_failure ──────────────────────────────────────────────────────

class TestHandleSudoFailure:
    def test_no_gateway_session_returns_original(self, monkeypatch):
        monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
        output = "sudo: a password is required"
        assert _handle_sudo_failure(output, "local") == output

    def test_gateway_session_with_sudo_failure_appends_tip(self, monkeypatch):
        monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
        output = "sudo: a password is required"
        result = _handle_sudo_failure(output, "local")
        assert "Tip:" in result
        assert "SUDO_PASSWORD" in result

    def test_gateway_session_without_sudo_failure_returns_original(self, monkeypatch):
        monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
        output = "ls output\nfile.txt"
        assert _handle_sudo_failure(output, "local") == output

    def test_no_tty_failure_appends_tip(self, monkeypatch):
        monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
        output = "sudo: no tty present"
        result = _handle_sudo_failure(output, "local")
        assert "Tip:" in result

    def test_terminal_required_failure_appends_tip(self, monkeypatch):
        monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
        output = "sudo: a terminal is required"
        result = _handle_sudo_failure(output, "local")
        assert "Tip:" in result


# ── _transform_sudo_command ───────────────────────────────────────────────────

class TestTransformSudoCommand:
    def test_no_sudo_in_command_unchanged(self, monkeypatch):
        monkeypatch.setenv("SUDO_PASSWORD", "secret")
        cmd, stdin = _transform_sudo_command("ls -la")
        assert cmd == "ls -la"
        assert stdin is None

    def test_no_password_configured_returns_original(self, monkeypatch):
        monkeypatch.delenv("SUDO_PASSWORD", raising=False)
        monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
        cmd, stdin = _transform_sudo_command("sudo apt-get install vim")
        assert cmd == "sudo apt-get install vim"
        assert stdin is None

    def test_with_password_transforms_sudo(self, monkeypatch):
        monkeypatch.setenv("SUDO_PASSWORD", "mypassword")
        cmd, stdin = _transform_sudo_command("sudo apt-get install vim")
        assert "sudo -S" in cmd
        assert "mypassword" in (stdin or "")

    def test_stdin_ends_with_newline(self, monkeypatch):
        monkeypatch.setenv("SUDO_PASSWORD", "pass")
        _, stdin = _transform_sudo_command("sudo ls")
        assert stdin is not None
        assert stdin.endswith("\n")

    def test_visudo_not_transformed(self, monkeypatch):
        # 'visudo' contains 'sudo' as a substring but should not be matched
        monkeypatch.setenv("SUDO_PASSWORD", "pass")
        cmd, stdin = _transform_sudo_command("visudo -c")
        # 'visudo' does not match \bsudo\b so should be unchanged
        assert "visudo" in cmd

    def test_multiple_sudo_all_replaced(self, monkeypatch):
        monkeypatch.setenv("SUDO_PASSWORD", "pass")
        cmd, stdin = _transform_sudo_command("sudo mkdir /tmp/a && sudo chmod 777 /tmp/a")
        assert cmd.count("sudo -S") == 2
