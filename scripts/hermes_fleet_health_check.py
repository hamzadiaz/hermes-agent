#!/usr/bin/env python3
"""Hermes fleet health check for local LaunchAgent-based agent deployments.

Checks:
- Shared runtime drift (launch agent working dir / HERMES_HOME)
- Duplicate Telegram bot tokens across Hermes agents
- Disallowed Gemini model selections (< 3.1 Pro) in agent configs
- launchctl status for Hermes gateway/agents
- Recent Telegram polling success in per-agent logs
- Stale cross-system gateway-agent LaunchAgent accidentally re-enabled

Exit codes:
- 0: all checks passed
- 1: warnings or failures detected
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

HOME = Path.home()
AGENTS_ROOT = HOME / ".hermes-agents"
LAUNCH_AGENTS = HOME / "Library" / "LaunchAgents"
SHARED_RUNTIME = str(HOME / ".hermes" / "hermes-agent")
EXPECTED_DM_USER = "8092264594"
POLLING_OK_RE = re.compile(r"getUpdates .*HTTP/1\.1 200 OK")
DISALLOWED_GEMINI_RE = re.compile(r"gemini-(?!3\.1-pro)\S*", re.IGNORECASE)


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def _launchctl_map() -> dict[str, dict[str, Any]]:
    cp = _run(["launchctl", "list"])
    mapping: dict[str, dict[str, Any]] = {}
    for line in cp.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        pid, status, label = parts
        pid = pid.strip()
        mapping[label] = {
            "pid": pid,
            "status": status.strip(),
            "running": bool(pid and pid != '-'),
        }
    return mapping


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _load_plist(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        return plistlib.load(fh) or {}


def _tail(path: Path, lines: int = 200) -> list[str]:
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return content[-lines:]


def _agent_names() -> list[str]:
    return sorted(p.parent.name for p in AGENTS_ROOT.glob("*/config.yaml"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Hermes fleet runtime health")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human text")
    args = parser.parse_args()

    launchctl = _launchctl_map()
    agents = []
    warnings: list[str] = []
    failures: list[str] = []
    token_owners: dict[str, list[str]] = {}

    stale_enabled = (LAUNCH_AGENTS / "ai.optijara.gateway-agent.plist").exists()
    stale_disabled = (LAUNCH_AGENTS / "ai.optijara.gateway-agent.plist.disabled").exists()
    if stale_enabled:
        failures.append("stale ai.optijara.gateway-agent LaunchAgent is enabled")
    elif not stale_disabled:
        warnings.append("stale ai.optijara.gateway-agent LaunchAgent is not present as .disabled sentinel")

    for agent in _agent_names():
        cfg_path = AGENTS_ROOT / agent / "config.yaml"
        plist_path = LAUNCH_AGENTS / f"ai.hermes.agent.{agent}.plist"
        cfg = _load_yaml(cfg_path)
        plist = _load_plist(plist_path)
        env = plist.get("EnvironmentVariables") or {}
        model = (cfg.get("model") or {}).get("default") or ""
        provider = (cfg.get("model") or {}).get("provider") or ""
        telegram_cfg = ((cfg.get("platforms") or {}).get("telegram") or {})
        extra = telegram_cfg.get("extra") or {}
        label = f"ai.hermes.agent.{agent}"
        launch = launchctl.get(label, {"pid": None, "status": "missing"})
        token_prefix = (env.get("TELEGRAM_BOT_TOKEN") or "").split(":", 1)[0]
        if token_prefix:
            token_owners.setdefault(token_prefix, []).append(agent)
        hermes_home = env.get("HERMES_HOME")
        expected_home = str(AGENTS_ROOT / agent)
        working_dir = plist.get("WorkingDirectory")
        out_log = AGENTS_ROOT / agent / "logs" / "gateway.log"
        err_log = AGENTS_ROOT / agent / "logs" / "gateway.error.log"
        out_tail = _tail(out_log)
        err_tail = _tail(err_log)
        polling_ok = any(POLLING_OK_RE.search(line) for line in out_tail)

        if provider.startswith("custom:google-gemini") and DISALLOWED_GEMINI_RE.search(model):
            failures.append(f"{agent}: disallowed Gemini model '{model}'")
        if not launch.get("running") and str(launch.get("status")) != "0":
            failures.append(f"{agent}: launchctl status={launch.get('status')}")
        if hermes_home != expected_home:
            failures.append(f"{agent}: HERMES_HOME mismatch ({hermes_home})")
        if working_dir != SHARED_RUNTIME:
            failures.append(f"{agent}: WorkingDirectory drift ({working_dir})")
        if extra.get("allowed_dm_users") != [EXPECTED_DM_USER]:
            warnings.append(f"{agent}: allowed_dm_users config is {extra.get('allowed_dm_users')}")
        if env.get("TELEGRAM_ALLOWED_DM_USERS") != EXPECTED_DM_USER:
            warnings.append(f"{agent}: TELEGRAM_ALLOWED_DM_USERS env is {env.get('TELEGRAM_ALLOWED_DM_USERS')}")
        if not polling_ok:
            warnings.append(f"{agent}: no recent successful getUpdates poll seen in gateway.log tail")

        agents.append({
            "agent": agent,
            "model": model,
            "provider": provider,
            "launchctl": launch,
            "telegram_token_prefix": token_prefix,
            "hermes_home": hermes_home,
            "working_dir": working_dir,
            "polling_ok": polling_ok,
            "last_out": out_tail[-1] if out_tail else None,
            "last_err": err_tail[-1] if err_tail else None,
        })

    duplicates = {token: owners for token, owners in token_owners.items() if len(owners) > 1}
    for token, owners in duplicates.items():
        failures.append(f"duplicate TELEGRAM_BOT_TOKEN prefix {token} across {', '.join(owners)}")

    gateway = launchctl.get("ai.hermes.gateway", {"pid": None, "status": "missing"})
    if str(gateway.get("status")) != "0":
        failures.append(f"gateway: launchctl status={gateway.get('status')}")

    report = {
        "gateway": gateway,
        "agents": agents,
        "duplicates": duplicates,
        "stale_openclaw_launchagent_disabled": stale_disabled and not stale_enabled,
        "warnings": warnings,
        "failures": failures,
        "ok": not warnings and not failures,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("Hermes Fleet Health Check")
        print(f"Gateway: status={gateway.get('status')} pid={gateway.get('pid')}")
        for item in agents:
            print(
                f"- {item['agent']}: status={item['launchctl'].get('status')} pid={item['launchctl'].get('pid')} "
                f"model={item['model']} provider={item['provider']} polling_ok={item['polling_ok']}"
            )
        print()
        print(f"Warnings: {len(warnings)}")
        for w in warnings:
            print(f"  - {w}")
        print(f"Failures: {len(failures)}")
        for f in failures:
            print(f"  - {f}")

    return 0 if not warnings and not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
