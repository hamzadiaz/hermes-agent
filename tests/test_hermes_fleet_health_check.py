import importlib.util
import plistlib
import sys
from pathlib import Path

import yaml


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "hermes_fleet_health_check.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("hermes_fleet_health_check", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_agent(tmp_path, agent, *, model="claude-sonnet-4-6", provider="claude-code", token="123:abc", successful_poll_at_end=True):
    agents_root = tmp_path / ".hermes-agents"
    launch_agents = tmp_path / "Library" / "LaunchAgents"
    agent_dir = agents_root / agent
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "logs").mkdir(exist_ok=True)

    cfg = {
        "model": {"default": model, "provider": provider},
        "platforms": {
            "telegram": {
                "enabled": True,
                "extra": {"allowed_dm_users": ["8092264594"], "require_mention": False},
            }
        },
    }
    (agent_dir / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")

    log_lines = []
    if successful_poll_at_end:
        log_lines.append('2026-04-17 INFO httpx: HTTP Request: POST https://api.telegram.org/bot123:***/getUpdates "HTTP/1.1 200 OK"')
    else:
        log_lines.extend([f'noise line {i}' for i in range(150)])
        log_lines.append('2026-04-17 INFO httpx: HTTP Request: POST https://api.telegram.org/bot123:***/getUpdates "HTTP/1.1 200 OK"')
        log_lines.extend([f'busy line {i}' for i in range(120)])
    (agent_dir / "logs" / "gateway.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    (agent_dir / "logs" / "gateway.error.log").write_text("", encoding="utf-8")

    launch_agents.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": f"ai.hermes.agent.{agent}",
        "WorkingDirectory": str(tmp_path / ".hermes" / "hermes-agent"),
        "EnvironmentVariables": {
            "HERMES_HOME": str(agent_dir),
            "TELEGRAM_BOT_TOKEN": token,
            "TELEGRAM_ALLOWED_DM_USERS": "8092264594",
            "TELEGRAM_ALLOWED_USERS": "8092264594",
        },
    }
    with (launch_agents / f"ai.hermes.agent.{agent}.plist").open("wb") as fh:
        plistlib.dump(plist, fh)


def test_health_check_ok(tmp_path, monkeypatch, capsys):
    module = _load_module()
    _write_agent(tmp_path, "alpha")
    (tmp_path / "Library" / "LaunchAgents" / "ai.optijara.gateway-agent.plist.disabled").write_text("disabled", encoding="utf-8")

    monkeypatch.setattr(module, "HOME", tmp_path)
    monkeypatch.setattr(module, "AGENTS_ROOT", tmp_path / ".hermes-agents")
    monkeypatch.setattr(module, "LAUNCH_AGENTS", tmp_path / "Library" / "LaunchAgents")
    monkeypatch.setattr(module, "SHARED_RUNTIME", str(tmp_path / ".hermes" / "hermes-agent"))
    monkeypatch.setattr(module, "_launchctl_map", lambda: {
        "ai.hermes.gateway": {"pid": "10", "status": "0", "running": True},
        "ai.hermes.agent.alpha": {"pid": "11", "status": "0", "running": True},
    })
    monkeypatch.setattr(sys, "argv", ["health-check"])

    rc = module.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "Failures: 0" in out
    assert "Warnings: 0" in out


def test_health_check_fails_on_disallowed_gemini_and_enabled_stale_launchagent(tmp_path, monkeypatch, capsys):
    module = _load_module()
    _write_agent(tmp_path, "beta", model="gemini-3.1-flash-lite-preview", provider="custom:google-gemini")
    (tmp_path / "Library" / "LaunchAgents" / "ai.optijara.gateway-agent.plist").write_text("enabled", encoding="utf-8")

    monkeypatch.setattr(module, "HOME", tmp_path)
    monkeypatch.setattr(module, "AGENTS_ROOT", tmp_path / ".hermes-agents")
    monkeypatch.setattr(module, "LAUNCH_AGENTS", tmp_path / "Library" / "LaunchAgents")
    monkeypatch.setattr(module, "SHARED_RUNTIME", str(tmp_path / ".hermes" / "hermes-agent"))
    monkeypatch.setattr(module, "_launchctl_map", lambda: {
        "ai.hermes.gateway": {"pid": "10", "status": "0", "running": True},
        "ai.hermes.agent.beta": {"pid": "11", "status": "0", "running": True},
    })
    monkeypatch.setattr(sys, "argv", ["health-check"])

    rc = module.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "disallowed Gemini model" in out
    assert "stale ai.optijara.gateway-agent LaunchAgent is enabled" in out


def test_health_check_looks_far_enough_back_for_successful_poll(tmp_path, monkeypatch, capsys):
    module = _load_module()
    _write_agent(tmp_path, "gamma", successful_poll_at_end=False)
    (tmp_path / "Library" / "LaunchAgents" / "ai.optijara.gateway-agent.plist.disabled").write_text("disabled", encoding="utf-8")

    monkeypatch.setattr(module, "HOME", tmp_path)
    monkeypatch.setattr(module, "AGENTS_ROOT", tmp_path / ".hermes-agents")
    monkeypatch.setattr(module, "LAUNCH_AGENTS", tmp_path / "Library" / "LaunchAgents")
    monkeypatch.setattr(module, "SHARED_RUNTIME", str(tmp_path / ".hermes" / "hermes-agent"))
    monkeypatch.setattr(module, "_launchctl_map", lambda: {
        "ai.hermes.gateway": {"pid": "10", "status": "0", "running": True},
        "ai.hermes.agent.gamma": {"pid": "11", "status": "0", "running": True},
    })
    monkeypatch.setattr(sys, "argv", ["health-check"])

    rc = module.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "Warnings: 0" in out


def test_running_agent_with_nonzero_last_status_is_not_marked_failed(tmp_path, monkeypatch, capsys):
    module = _load_module()
    _write_agent(tmp_path, "delta")
    (tmp_path / "Library" / "LaunchAgents" / "ai.optijara.gateway-agent.plist.disabled").write_text("disabled", encoding="utf-8")

    monkeypatch.setattr(module, "HOME", tmp_path)
    monkeypatch.setattr(module, "AGENTS_ROOT", tmp_path / ".hermes-agents")
    monkeypatch.setattr(module, "LAUNCH_AGENTS", tmp_path / "Library" / "LaunchAgents")
    monkeypatch.setattr(module, "SHARED_RUNTIME", str(tmp_path / ".hermes" / "hermes-agent"))
    monkeypatch.setattr(module, "_launchctl_map", lambda: {
        "ai.hermes.gateway": {"pid": "10", "status": "0", "running": True},
        "ai.hermes.agent.delta": {"pid": "22", "status": "-15", "running": True},
    })
    monkeypatch.setattr(sys, "argv", ["health-check"])

    rc = module.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "Failures: 0" in out
