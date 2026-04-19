#!/usr/bin/env python3
"""Zero-LLM-token Hermes fleet health monitor.

Runs the local health check, stores prior state, and sends Telegram alerts only on:
- new warning/failure state
- changed warning/failure details
- recovery from unhealthy -> healthy

No LLM calls are made. Alerts go directly through Telegram Bot API.
"""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HOME = Path.home()
HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(HOME / ".hermes")))
REPO_ROOT = Path(__file__).resolve().parent.parent
HEALTH_SCRIPT = REPO_ROOT / "scripts" / "hermes_fleet_health_check.py"
STATE_DIR = HERMES_HOME / "health"
STATE_FILE = STATE_DIR / "fleet-monitor-state.json"
LOG_DIR = HERMES_HOME / "logs"
LOG_FILE = LOG_DIR / "fleet-monitor.log"
CHAT_ID = "8092264594"
TOKEN_SOURCE_PLISTS = [
    HOME / "Library" / "LaunchAgents" / "ai.hermes.agent.claude.plist",
    HOME / "Library" / "LaunchAgents" / "ai.hermes.agent.mark.plist",
    HOME / "Library" / "LaunchAgents" / "ai.hermes.agent.alex.plist",
]


def _log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(f"[{stamp}] {message}\n")


def _load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _telegram_token() -> str:
    env_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if env_token:
        return env_token
    for path in TOKEN_SOURCE_PLISTS:
        if not path.exists():
            continue
        try:
            with path.open("rb") as fh:
                data = plistlib.load(fh) or {}
            token = ((data.get("EnvironmentVariables") or {}).get("TELEGRAM_BOT_TOKEN") or "").strip()
            if token:
                return token
        except Exception:
            continue
    return ""


def _run_health() -> dict[str, Any]:
    cp = subprocess.run(
        [sys.executable, str(HEALTH_SCRIPT), "--json"],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if not cp.stdout.strip():
        raise RuntimeError(f"health check returned no JSON stdout (rc={cp.returncode} stderr={cp.stderr.strip()})")
    report = json.loads(cp.stdout)
    report["exit_code"] = cp.returncode
    return report


def _digest(report: dict[str, Any]) -> str:
    material = json.dumps(
        {
            "warnings": report.get("warnings", []),
            "failures": report.get("failures", []),
            "agents": [
                {
                    "agent": a.get("agent"),
                    "status": a.get("launchctl", {}).get("status"),
                    "polling_ok": a.get("polling_ok"),
                    "model": a.get("model"),
                    "provider": a.get("provider"),
                }
                for a in report.get("agents", [])
            ],
        },
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _format_message(report: dict[str, Any], *, recovered: bool = False) -> str:
    if recovered:
        return "✅ Hermes fleet health recovered. Warnings: 0. Failures: 0."
    lines = ["⚠️ Hermes fleet health issue detected."]
    warnings = report.get("warnings", [])
    failures = report.get("failures", [])
    if failures:
        lines.append(f"Failures ({len(failures)}):")
        lines.extend(f"- {item}" for item in failures[:8])
    if warnings:
        lines.append(f"Warnings ({len(warnings)}):")
        lines.extend(f"- {item}" for item in warnings[:8])
    unhealthy = [a for a in report.get("agents", []) if a.get("launchctl", {}).get("status") != "0" or not a.get("polling_ok")]
    if unhealthy:
        lines.append("Affected agents:")
        for item in unhealthy[:8]:
            lines.append(
                f"- {item.get('agent')}: status={item.get('launchctl', {}).get('status')} polling_ok={item.get('polling_ok')}"
            )
    return "\n".join(lines)


def _send_telegram(text: str) -> bool:
    token = _telegram_token()
    if not token:
        _log("No TELEGRAM_BOT_TOKEN available for monitor alerts")
        return False
    payload = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text})
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload.encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
        _log(f"Telegram alert sent ({resp.status}): {body[:200]}")
        return True
    except Exception as exc:
        _log(f"Telegram alert failed: {exc}")
        return False


def main() -> int:
    try:
        report = _run_health()
    except Exception as exc:
        _log(f"Health monitor failed to run health check: {exc}")
        return 1

    current_ok = not report.get("warnings") and not report.get("failures")
    current_digest = _digest(report)
    state = _load_state()
    previous_ok = state.get("ok")
    previous_digest = state.get("digest")

    should_alert = False
    recovered = False
    if previous_ok is None:
        should_alert = not current_ok
    elif previous_ok and not current_ok:
        should_alert = True
    elif not previous_ok and current_ok:
        should_alert = True
        recovered = True
    elif not current_ok and previous_digest != current_digest:
        should_alert = True

    if should_alert:
        message = _format_message(report, recovered=recovered)
        _send_telegram(message)
        _log(f"Alert decision: sent recovered={recovered} digest={current_digest}")
    else:
        _log(f"Alert decision: no-send ok={current_ok} digest={current_digest}")

    _save_state({
        "ok": current_ok,
        "digest": current_digest,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "warnings": report.get("warnings", []),
        "failures": report.get("failures", []),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
