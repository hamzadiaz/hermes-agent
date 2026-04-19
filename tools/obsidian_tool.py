#!/usr/bin/env python3
"""
Obsidian Vault Integration Tool

Writes session checkpoints and working-context updates to the
Hermes-Memory-Vault Obsidian vault. Each agent has its own
working-context.md and daily log under 03-Agent-Private/{agent}/.

Called automatically at session end via the memory flush agent,
and available as a tool for agents to call during sessions.
"""

import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

VAULT_PATH = (
    Path.home()
    / "Library"
    / "Mobile Documents"
    / "com~apple~CloudDocs"
    / "Obsidian"
    / "Hermes-Memory-Vault"
)
VAULT_TOOLS_SCRIPT = Path.home() / ".hermes" / "scripts" / "hermes_vault_tools.py"

# Map HERMES_HOME directory name → vault agent folder name
_AGENT_NAME_MAP = {
    "mark": "Marketing",
    "malik": "Malik",
    "musa": "Musa",
    "buni": "Boone",
    "alex": "Alex",
    "hermes": "Hermes-Core",
    # The main gateway runs from ~/.hermes/ whose .name is "hermes-agent" on some setups
    "hermes-agent": "Hermes-Core",
}


def _get_vault_agent_name() -> Optional[str]:
    """Derive vault agent name from the current HERMES_HOME directory."""
    try:
        from hermes_constants import get_hermes_home
        home = get_hermes_home()
        dir_name = home.name.lower().lstrip(".")
        return _AGENT_NAME_MAP.get(dir_name)
    except Exception as e:
        logger.debug("Could not resolve vault agent name: %s", e)
        return None


def _run_vault_cmd(*args: str, timeout: int = 15) -> dict:
    """Run hermes_vault_tools.py with the given subcommand args."""
    if not VAULT_TOOLS_SCRIPT.exists():
        return {"ok": False, "error": f"Vault tools script missing: {VAULT_TOOLS_SCRIPT}"}
    try:
        result = subprocess.run(
            [sys.executable, str(VAULT_TOOLS_SCRIPT)] + list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return {"ok": True, "output": result.stdout.strip()}
        return {"ok": False, "error": result.stderr.strip() or result.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Vault command timed out"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def obsidian_checkpoint(event: str, note: str, agent: str = "") -> str:
    """
    Append a checkpoint entry to the agent's Obsidian daily log and
    working-context.md. Call this at the end of any significant session
    or when you complete a meaningful task.

    Args:
        event: Short event label, e.g. 'session_end', 'task_done', 'blocked'
        note:  One or two sentence summary of what happened / what's next
        agent: Vault agent name override (leave blank to auto-detect)
    """
    vault_agent = agent or _get_vault_agent_name()
    if not vault_agent:
        return json.dumps({
            "success": False,
            "error": "Cannot determine vault agent name. Pass agent= explicitly.",
        })

    res = _run_vault_cmd("checkpoint", "--agent", vault_agent, "--event", event, "--note", note)
    if res["ok"]:
        return json.dumps({"success": True, "agent": vault_agent, "event": event})
    return json.dumps({"success": False, "error": res["error"], "agent": vault_agent})


def obsidian_update_working_context(
    current_goal: str,
    last_action: str,
    next_steps: str,
    open_questions: str = "",
    agent: str = "",
) -> str:
    """
    Rewrite the structured sections of the agent's working-context.md.
    Use this to keep the Obsidian vault in sync after meaningful sessions.

    Args:
        current_goal:   What the agent is currently focused on
        last_action:    What was just completed (1-2 sentences)
        next_steps:     Numbered list of the next 1-3 concrete actions
        open_questions: Any blockers or unresolved questions (optional)
        agent:          Vault agent name override (leave blank to auto-detect)
    """
    vault_agent = agent or _get_vault_agent_name()
    if not vault_agent:
        return json.dumps({
            "success": False,
            "error": "Cannot determine vault agent name. Pass agent= explicitly.",
        })

    wc_path = VAULT_PATH / "03-Agent-Private" / vault_agent / "working-context.md"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
        # Read existing checkpoint log to preserve it
        existing_log = ""
        if wc_path.exists():
            txt = wc_path.read_text(encoding="utf-8")
            marker = "## Checkpoint Log\n"
            if marker in txt:
                existing_log = txt.split(marker, 1)[1]

        content = (
            f"# {vault_agent} Working Context\n"
            f"*Last updated: {ts}*\n\n"
            f"## Current Goal\n{current_goal}\n\n"
            f"## Last Action\n{last_action}\n\n"
            f"## Next 3 Steps\n{next_steps}\n\n"
            f"## Open Questions\n{open_questions or '-'}\n\n"
            f"## Checkpoint Log\n{existing_log}"
        )
        wc_path.parent.mkdir(parents=True, exist_ok=True)
        wc_path.write_text(content, encoding="utf-8")
        return json.dumps({"success": True, "agent": vault_agent, "path": str(wc_path)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e), "agent": vault_agent})


# ── Tool Schemas ──────────────────────────────────────────────────────────────

OBSIDIAN_CHECKPOINT_SCHEMA = {
    "name": "obsidian_checkpoint",
    "description": (
        "Append a checkpoint entry to your Obsidian working-context.md and daily log. "
        "Call this at the end of any significant session or when you complete a meaningful task. "
        "Keeps the Obsidian vault in sync so the nightly vault audit stays healthy."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "event": {
                "type": "string",
                "description": "Short event label: 'session_end', 'task_done', 'blocked', 'milestone', etc.",
            },
            "note": {
                "type": "string",
                "description": "1-2 sentence summary of what happened and what's next.",
            },
            "agent": {
                "type": "string",
                "description": "Vault agent name override. Leave blank to auto-detect from HERMES_HOME.",
            },
        },
        "required": ["event", "note"],
    },
}

OBSIDIAN_UPDATE_SCHEMA = {
    "name": "obsidian_update_working_context",
    "description": (
        "Rewrite the structured sections of your Obsidian working-context.md "
        "(Current Goal, Last Action, Next Steps, Open Questions). "
        "Use after completing a major task or at session end to keep your vault current."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "current_goal": {
                "type": "string",
                "description": "What you are currently focused on.",
            },
            "last_action": {
                "type": "string",
                "description": "What was just completed (1-2 sentences).",
            },
            "next_steps": {
                "type": "string",
                "description": "Numbered list of the next 1-3 concrete actions.",
            },
            "open_questions": {
                "type": "string",
                "description": "Any blockers or unresolved questions (optional).",
            },
            "agent": {
                "type": "string",
                "description": "Vault agent name override. Leave blank to auto-detect.",
            },
        },
        "required": ["current_goal", "last_action", "next_steps"],
    },
}


# ── Registry ──────────────────────────────────────────────────────────────────

def check_obsidian_requirements() -> bool:
    """Obsidian tool is available when vault path is reachable."""
    return VAULT_PATH.exists()


from tools.registry import registry

registry.register(
    name="obsidian_checkpoint",
    toolset="obsidian",
    schema=OBSIDIAN_CHECKPOINT_SCHEMA,
    handler=lambda args, **_kw: obsidian_checkpoint(
        event=args.get("event", "checkpoint"),
        note=args.get("note", ""),
        agent=args.get("agent", ""),
    ),
    check_fn=check_obsidian_requirements,
    emoji="📓",
)

registry.register(
    name="obsidian_update_working_context",
    toolset="obsidian",
    schema=OBSIDIAN_UPDATE_SCHEMA,
    handler=lambda args, **_kw: obsidian_update_working_context(
        current_goal=args.get("current_goal", ""),
        last_action=args.get("last_action", ""),
        next_steps=args.get("next_steps", ""),
        open_questions=args.get("open_questions", ""),
        agent=args.get("agent", ""),
    ),
    check_fn=check_obsidian_requirements,
    emoji="📓",
)
