"""OpenAI-compatible shim that forwards Hermes requests to `claude -p`.

This adapter keeps Claude Code as the first-party auth/runtime surface while
making Hermes the owner of the actual tool loop. When Hermes provides tool
definitions, Claude is instructed to emit Hermes XML tool calls instead of
using Claude Code's own built-in tools, so the existing Hermes skills/browser/
vision/research pipeline continues to execute inside Hermes.
"""

from __future__ import annotations

import ast
import json
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

from environments.tool_call_parsers.hermes_parser import HermesToolCallParser

CLI_MARKER_BASE_URL = "cli://claude-code"
_DEFAULT_TIMEOUT_SECONDS = 900.0
_DEFAULT_HEARTBEAT_SECONDS = 8.0
_TOOL_CALL_BLOCK_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
_ABS_PATH_RE = re.compile(r"(/[A-Za-z0-9._~\-]+(?:/[A-Za-z0-9._~\-]+)+)")
_STRIP_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
)


def _render_message_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        if "text" in content:
            return str(content.get("text") or "").strip()
        if "content" in content and isinstance(content.get("content"), str):
            return str(content.get("content") or "").strip()
        return json.dumps(content, ensure_ascii=True)
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts).strip()
    return str(content).strip()


def _format_tools_for_prompt(tools: list[dict[str, Any]] | None) -> str:
    if not tools:
        return "[]"

    formatted_tools: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        func = tool.get("function") or {}
        if not isinstance(func, dict) or not func.get("name"):
            continue
        formatted_tools.append(
            {
                "name": func.get("name"),
                "description": func.get("description", ""),
                "parameters": func.get("parameters", {}),
                "required": None,
            }
        )
    return json.dumps(formatted_tools, ensure_ascii=False)


def _assistant_tool_xml(message: dict[str, Any]) -> str:
    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        return ""

    parts: list[str] = []
    for tool_call in tool_calls:
        if not tool_call:
            continue
        function = tool_call.get("function") or {}
        name = function.get("name")
        if not name:
            continue
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        tool_call_json = {"name": name, "arguments": arguments}
        parts.append(f"<tool_call>\n{json.dumps(tool_call_json, ensure_ascii=False)}\n</tool_call>")
    return "\n".join(parts)


def _extract_literal_strings(messages: list[dict[str, Any]]) -> list[str]:
    literals: list[str] = []
    seen: set[str] = set()
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        rendered = _render_message_content(message.get("content"))
        for match in _ABS_PATH_RE.findall(rendered):
            value = match.strip()
            if value and value not in seen:
                seen.add(value)
                literals.append(value)
    return literals[:12]


def _format_messages_as_prompt(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> str:
    tool_mode = bool(tools)
    system_parts: list[str] = []
    transcript: list[str] = []
    literal_strings = _extract_literal_strings(messages)

    for message in (messages or []):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "unknown").strip().lower()

        if role == "system":
            rendered = _render_message_content(message.get("content"))
            if rendered:
                system_parts.append(rendered)
            continue

        if role == "assistant":
            content = _render_message_content(message.get("content"))
            xml = _assistant_tool_xml(message)
            parts = [part for part in (content, xml) if part]
            if parts:
                transcript.append("Assistant:\n" + "\n".join(parts))
            continue

        if role == "tool":
            rendered = _render_message_content(message.get("content"))
            if rendered:
                transcript.append(f"Tool:\n<tool_response>\n{rendered}\n</tool_response>")
            continue

        rendered = _render_message_content(message.get("content"))
        if not rendered:
            continue
        label = "User" if role == "user" else "Context"
        transcript.append(f"{label}:\n{rendered}")

    sections: list[str] = []
    if system_parts:
        sections.append("Hermes identity and runtime instructions:\n\n" + "\n\n".join(system_parts))

    if tool_mode:
        sections.append(
            "You are being used as the active Claude Code backend for Hermes.\n"
            "Claude Code provides first-party authentication only. Hermes owns the tool runtime.\n"
            "Ignore any Claude Code startup inventory of built-in tools, slash commands, skills, plugins, browser integrations, or MCP tools.\n"
            "Those are not the authoritative runtime for this task.\n"
            "The only authoritative tool list is the Hermes tool list inside <tools> below.\n"
            "Do not use Claude Code built-in tools, slash commands, skills, browser integrations, or MCP tools.\n"
            "When a tool is needed, emit Hermes XML tool calls only.\n"
            "For any claim about local files, source code, shell commands, browser state, screenshots, UI, processes, logs, skills, or memory, you must use Hermes tools first.\n"
            "Do not answer from memory for repository inspection, code review, debugging, browser inspection, screenshots, or local environment questions.\n"
            "If read_file appears in <tools>, you do have filesystem access through Hermes.\n"
            "If search_files appears in <tools>, you do have repository search through Hermes.\n"
            "If terminal appears in <tools>, you do have shell access through Hermes.\n"
            "If browser_navigate/browser_snapshot/browser_vision appear in <tools>, you do have browser and screenshot inspection through Hermes.\n"
            "Never claim you only have Claude Code, Playwright, MCP, or browser-only tools when Hermes tools are present.\n"
            "Use read_file for reading files and search_files for finding files before falling back to terminal.\n"
            "Copy user-provided file paths, URLs, commands, filenames, and identifiers exactly. Do not shorten, normalize, or rewrite them.\n"
            "If the user asks to read or inspect a specific local file path, calling read_file with that exact path is mandatory before answering.\n"
            "If the user asks to search a codebase or find files, calling search_files is mandatory before answering.\n"
            "Do not answer with limitations about missing filesystem access when read_file exists in <tools>; that limitation would be false.\n"
            "You are provided with Hermes tool signatures within <tools> </tools> XML tags.\n"
            "If no tool is needed, respond in natural language.\n"
            "If you need to read files, search files, run shell commands, browse, inspect screenshots, store memory, or manage todos, use the Hermes tool with that matching purpose.\n"
            "Prefer Hermes names like read_file, search_files, terminal, browser_navigate, browser_snapshot, browser_vision, memory, and todo.\n"
            "Never say a tool ran unless Hermes has already returned a <tool_response> for it.\n"
            "After tool execution, Hermes will return results within <tool_response> </tool_response> XML tags.\n"
            "When you decide to use tools, output one or more <tool_call> blocks and nothing else after them."
        )
        sections.append(
            "<tools>\n"
            f"{_format_tools_for_prompt(tools)}\n"
            "</tools>\n"
            "Each function call must match this JSON shape:\n"
            "{'name': <function-name>, 'arguments': <args-dict>}\n"
            "Each function call must be enclosed inside <tool_call> and </tool_call>.\n"
            "Example:\n"
            "<tool_call>\n"
            "{'name': 'read_file', 'arguments': {'path': '/tmp/demo.txt'}}\n"
            "</tool_call>"
        )
    else:
        sections.extend(
            [
                "You are being used as the active Claude Code backend for Hermes.",
                "Respond directly in natural language.",
                "Do not emit OpenAI tool-call JSON.",
            ]
        )

    if model:
        sections.append(f"Hermes requested model hint: {model}")
    if literal_strings:
        sections.append(
            "Literal strings from the conversation. Preserve these verbatim in any tool arguments or answers:\n"
            + "\n".join(f"- {value}" for value in literal_strings)
        )
    if transcript:
        sections.append("Conversation transcript:\n\n" + "\n\n".join(transcript))
    sections.append("Continue the conversation from the latest user request.")
    return "\n\n".join(part.strip() for part in sections if part and part.strip())


def _usage_from_payload(payload: dict[str, Any]) -> Any:
    usage = payload.get("usage") or {}
    prompt_tokens = int(usage.get("input_tokens") or 0)
    completion_tokens = int(usage.get("output_tokens") or 0)
    cache_read = int(usage.get("cache_read_input_tokens") or 0)
    total_tokens = prompt_tokens + completion_tokens
    return SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        prompt_tokens_details=SimpleNamespace(cached_tokens=cache_read),
    )


def _tool_delta_from_call(tool_call: Any, index: int) -> Any:
    return SimpleNamespace(
        index=index,
        id=getattr(tool_call, "id", f"call_{index}"),
        type="function",
        function=SimpleNamespace(
            name=getattr(tool_call.function, "name", ""),
            arguments=getattr(tool_call.function, "arguments", ""),
        ),
    )


def _display_only_tool_delta(*, name: str, arguments: str, index: int) -> Any:
    return SimpleNamespace(
        index=index,
        id=f"display_tool_{index}",
        type="function",
        extra_content={"display_only": True},
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        ),
    )


def _map_native_tool_name(name: str) -> str:
    raw = str(name or "").strip()
    if not raw:
        return "tool"
    mapping = {
        "Read": "read_file",
        "Write": "write_file",
        "Edit": "patch",
        "NotebookEdit": "patch",
        "Grep": "search_files",
        "Glob": "search_files",
        "Bash": "terminal",
        "WebSearch": "web_search",
        "WebFetch": "web_fetch",
        "TodoWrite": "todo",
        "Skill": "skill_view",
        "Task": "delegate_task",
        "AskUserQuestion": "clarify",
        "mcp__playwright__browser_take_screenshot": "browser_snapshot",
        "mcp__playwright__browser_run_code": "browser_eval",
        "mcp__plugin_superpowers-chrome_chrome__use_browser": "browser_vision",
    }
    if raw in mapping:
        return mapping[raw]
    if raw.startswith("mcp__playwright__browser_"):
        return raw.replace("mcp__playwright__", "", 1)
    if raw.startswith("mcp__plugin_superpowers-chrome_chrome__"):
        return raw.split("__", 1)[-1]
    return raw.lower()


def _final_stream_delta(*, model: str, finish_reason: str, usage: Any) -> Any:
    return SimpleNamespace(
        id="claude-code-stream",
        model=model,
        choices=[
            SimpleNamespace(
                index=0,
                delta=SimpleNamespace(content=None, tool_calls=None, reasoning=None, reasoning_content=None),
                finish_reason=finish_reason,
            )
        ],
        usage=usage,
    )


class _ClaudeCodeChatCompletions:
    def __init__(self, client: "ClaudeCodeClient"):
        self._client = client

    def create(self, **kwargs: Any) -> Any:
        return self._client._create_chat_completion(**kwargs)


class _ClaudeCodeChatNamespace:
    def __init__(self, client: "ClaudeCodeClient"):
        self.completions = _ClaudeCodeChatCompletions(client)


class ClaudeCodeClient:
    """Minimal OpenAI-client-compatible facade for Claude Code CLI."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        default_headers: dict[str, str] | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        **_: Any,
    ):
        self.api_key = api_key or "claude-code"
        self.base_url = base_url or CLI_MARKER_BASE_URL
        self._default_headers = dict(default_headers or {})
        self._command = (
            command
            or os.getenv("HERMES_CLAUDE_CODE_COMMAND", "").strip()
            or os.getenv("CLAUDE_CLI_PATH", "").strip()
            or "claude"
        )
        self._args = list(args or [])
        self._cwd = str(Path(os.getenv("HERMES_CLAUDE_CODE_CWD", str(Path.home()))).expanduser().resolve())
        self._permission_mode = os.getenv("HERMES_CLAUDE_CODE_PERMISSION_MODE", "bypassPermissions").strip() or "bypassPermissions"
        self._extra_add_dirs = [
            p.strip() for p in os.getenv("HERMES_CLAUDE_CODE_ADD_DIRS", "").split(os.pathsep) if p.strip()
        ]
        self._tool_parser = HermesToolCallParser()
        self.chat = _ClaudeCodeChatNamespace(self)
        self.is_closed = False

    def close(self) -> None:
        self.is_closed = True

    def _create_chat_completion(
        self,
        *,
        model: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        timeout: float | None = None,
        stream: bool | None = None,
        **_: Any,
    ) -> Any:
        prompt_text = _format_messages_as_prompt(messages or [], model=model, tools=tools)
        timeout_seconds = float(timeout or _DEFAULT_TIMEOUT_SECONDS)

        if stream:
            return self._run_prompt_stream(prompt_text, model=model, timeout_seconds=timeout_seconds, tools=tools)

        payload = self._run_prompt(prompt_text, model=model, timeout_seconds=timeout_seconds, tools=tools)
        response_text = str(payload.get("result") or "").strip()
        response_text, tool_calls = self._extract_tool_calls(response_text)
        model_name = str(model or payload.get("model") or "claude-code")
        usage = _usage_from_payload(payload)
        finish_reason = "tool_calls" if tool_calls else "stop"

        assistant_message = SimpleNamespace(
            content=response_text,
            tool_calls=tool_calls or [],
            reasoning=None,
            reasoning_content=None,
            reasoning_details=None,
        )
        choice = SimpleNamespace(message=assistant_message, finish_reason=finish_reason)
        return SimpleNamespace(
            choices=[choice],
            usage=usage,
            model=model_name,
        )

    def _build_cmd(
        self,
        *,
        prompt_text: str,
        model: str | None,
        stream: bool,
        tools: list[dict[str, Any]] | None,
    ) -> list[str]:
        cmd = [self._command, "-p"]
        if stream:
            cmd.extend(["--verbose", "--output-format", "stream-json", "--include-partial-messages"])
        else:
            cmd.extend(["--output-format", "json"])
        cmd.extend(["--permission-mode", self._permission_mode, "--disable-slash-commands", "--setting-sources", "local"])
        if tools:
            # Disable Claude Code's own tool runtime so Hermes remains the
            # single source of truth for tool execution.
            cmd.extend(["--tools", ""])
            # Also pass an empty MCP config so user-installed MCP servers
            # (e.g. superpowers Playwright) don't load in the subprocess and
            # shadow Hermes's XML tool protocol.
            empty_mcp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, prefix="hermes_nomcp_"
            )
            json.dump({"mcpServers": {}}, empty_mcp)
            empty_mcp.flush()
            empty_mcp.close()
            cmd.extend(["--mcp-config", empty_mcp.name])
        if model:
            cmd.extend(["--model", model])
        cmd.extend(self._args)
        for add_dir in self._extra_add_dirs:
            cmd.extend(["--add-dir", add_dir])
        cmd.append(prompt_text)
        return cmd

    def _child_env(self) -> dict[str, str]:
        child_env = os.environ.copy()
        for key in _STRIP_ENV_VARS:
            child_env.pop(key, None)
        return child_env

    @staticmethod
    def _extract_mcp_tmp(cmd: list[str]) -> str | None:
        """Return the --mcp-config path if we injected one, else None."""
        try:
            idx = cmd.index("--mcp-config")
            path = cmd[idx + 1]
            return path if "hermes_nomcp_" in path else None
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _cleanup_mcp_tmp(path: str | None) -> None:
        """Delete a temp MCP config file we created, silently ignoring errors."""
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass

    def _extract_tool_calls(self, text: str) -> tuple[str | None, list[Any]]:
        content, tool_calls = self._tool_parser.parse(text)
        if not tool_calls and "<tool_call>" in text:
            fallback_tool_calls: list[Any] = []
            for index, match in enumerate(_TOOL_CALL_BLOCK_RE.findall(text)):
                raw = (match or "").strip()
                if not raw:
                    continue
                parsed: Any = None
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    try:
                        parsed = ast.literal_eval(raw)
                    except (SyntaxError, ValueError):
                        parsed = None
                if not isinstance(parsed, dict):
                    continue
                name = parsed.get("name")
                arguments = parsed.get("arguments", {})
                if not name:
                    continue
                if not isinstance(arguments, dict):
                    arguments = {}
                fallback_tool_calls.append(
                    SimpleNamespace(
                        id=f"call_{index}",
                        type="function",
                        function=SimpleNamespace(
                            name=str(name),
                            arguments=json.dumps(arguments, ensure_ascii=False),
                        ),
                    )
                )
            if fallback_tool_calls:
                tool_calls = fallback_tool_calls
                content = text[: text.find("<tool_call>")].strip() or None
        clean_content = content if isinstance(content, str) else None
        if clean_content is not None:
            clean_content = clean_content.strip() or None
        return clean_content, list(tool_calls or [])

    def _run_prompt(
        self,
        prompt_text: str,
        *,
        model: str | None,
        timeout_seconds: float,
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        cmd = self._build_cmd(prompt_text=prompt_text, model=model, stream=False, tools=tools)
        mcp_tmp = self._extract_mcp_tmp(cmd)

        try:
            completed = subprocess.run(
                cmd,
                cwd=self._cwd,
                env=self._child_env(),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Could not start Claude Code command '{self._command}'. "
                "Install Claude Code or set HERMES_CLAUDE_CODE_COMMAND/CLAUDE_CLI_PATH."
            ) from exc
        finally:
            self._cleanup_mcp_tmp(mcp_tmp)

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        if completed.returncode != 0:
            raise RuntimeError(stderr or stdout or f"Claude Code exited with status {completed.returncode}.")

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Claude Code did not return JSON output: {stdout[:400]}") from exc

        if payload.get("is_error"):
            raise RuntimeError(str(payload.get("result") or payload))
        return payload

    def _run_prompt_stream(
        self,
        prompt_text: str,
        *,
        model: str | None,
        timeout_seconds: float,
        tools: list[dict[str, Any]] | None,
    ) -> Iterable[Any]:
        cmd = self._build_cmd(prompt_text=prompt_text, model=model, stream=True, tools=tools)
        mcp_tmp = self._extract_mcp_tmp(cmd)
        model_name = str(model or "claude-code")
        tool_mode = bool(tools)

        try:
            process = subprocess.Popen(
                cmd,
                cwd=self._cwd,
                env=self._child_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            self._cleanup_mcp_tmp(mcp_tmp)
            raise RuntimeError(
                f"Could not start Claude Code command '{self._command}'. "
                "Install Claude Code or set HERMES_CLAUDE_CODE_COMMAND/CLAUDE_CLI_PATH."
            ) from exc

        assistant_text = ""
        emitted_visible_chars = 0
        emitted_tool_count = 0
        display_tool_index = 0
        final_payload: dict[str, Any] | None = None
        native_tool_blocks: dict[int, dict[str, Any]] = {}
        heartbeat_seconds = float(
            os.getenv("HERMES_CLAUDE_CODE_HEARTBEAT_SECONDS", str(_DEFAULT_HEARTBEAT_SECONDS))
            or _DEFAULT_HEARTBEAT_SECONDS
        )
        last_emission_at = time.time()

        def _yield_text_delta(text_delta: str) -> Any:
            return SimpleNamespace(
                id="claude-code-stream",
                model=model_name,
                choices=[
                    SimpleNamespace(
                        index=0,
                        delta=SimpleNamespace(content=text_delta, tool_calls=None, reasoning=None, reasoning_content=None),
                        finish_reason=None,
                    )
                ],
                usage=None,
            )

        def _yield_heartbeat() -> Any:
            nonlocal display_tool_index, last_emission_at
            last_emission_at = time.time()
            heartbeat = SimpleNamespace(
                id="claude-code-stream",
                model=model_name,
                choices=[
                    SimpleNamespace(
                        index=0,
                        delta=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                _display_only_tool_delta(
                                    name="processing",
                                    arguments="{}",
                                    index=display_tool_index,
                                )
                            ],
                            reasoning=None,
                            reasoning_content=None,
                        ),
                        finish_reason=None,
                    )
                ],
                usage=None,
            )
            display_tool_index += 1
            return heartbeat

        stdout_queue: "queue.Queue[str | None]" = queue.Queue()

        def _reader() -> None:
            try:
                assert process.stdout is not None
                for raw_line in process.stdout:
                    stdout_queue.put(raw_line)
            finally:
                stdout_queue.put(None)

        threading.Thread(target=_reader, daemon=True).start()

        try:
            reader_done = False
            while True:
                try:
                    raw_line = stdout_queue.get(timeout=0.5)
                except queue.Empty:
                    if tool_mode and process.poll() is None and (time.time() - last_emission_at) >= heartbeat_seconds:
                        yield _yield_heartbeat()
                    if process.poll() is not None and reader_done and stdout_queue.empty():
                        break
                    continue

                if raw_line is None:
                    reader_done = True
                    if process.poll() is not None and stdout_queue.empty():
                        break
                    continue

                line = raw_line.strip()
                if not line:
                    continue
                last_emission_at = time.time()
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if event.get("type") == "result":
                    final_payload = event
                    continue

                if event.get("type") != "stream_event":
                    continue

                inner = event.get("event") or {}
                event_type = inner.get("type")
                if event_type == "message_start":
                    message = inner.get("message") or {}
                    model_name = str(message.get("model") or model_name)
                    continue

                if event_type == "content_block_start":
                    block = inner.get("content_block") or {}
                    if block.get("type") == "tool_use":
                        block_index = int(inner.get("index", 0) or 0)
                        native_tool_blocks[block_index] = {
                            "name": str(block.get("name") or ""),
                            "input_json": "",
                            "emitted": False,
                        }
                    continue

                if event_type == "content_block_stop":
                    continue

                if event_type == "thinking_delta":
                    continue

                if event_type == "content_block_delta":
                    delta = inner.get("delta") or {}
                    delta_type = delta.get("type")
                    block_index = int(inner.get("index", 0) or 0)

                    if delta_type == "input_json_delta":
                        state = native_tool_blocks.get(block_index)
                        if state is not None:
                            state["input_json"] += str(delta.get("partial_json") or "")
                            if not state["emitted"]:
                                mapped_name = _map_native_tool_name(state.get("name", ""))
                                yield SimpleNamespace(
                                    id="claude-code-stream",
                                    model=model_name,
                                    choices=[
                                        SimpleNamespace(
                                            index=0,
                                            delta=SimpleNamespace(
                                                content=None,
                                                tool_calls=[
                                                    _display_only_tool_delta(
                                                        name=mapped_name,
                                                        arguments=state["input_json"],
                                                        index=display_tool_index,
                                                    )
                                                ],
                                                reasoning=None,
                                                reasoning_content=None,
                                            ),
                                            finish_reason=None,
                                        )
                                    ],
                                    usage=None,
                                )
                                display_tool_index += 1
                                state["emitted"] = True
                                last_emission_at = time.time()
                        continue

                    if delta_type == "thinking_delta":
                        yield SimpleNamespace(
                            id="claude-code-stream",
                            model=model_name,
                            choices=[
                                SimpleNamespace(
                                    index=0,
                                    delta=SimpleNamespace(
                                        content=None,
                                        tool_calls=None,
                                        reasoning=None,
                                        reasoning_content=str(delta.get("thinking") or ""),
                                    ),
                                    finish_reason=None,
                                )
                            ],
                            usage=None,
                        )
                        last_emission_at = time.time()
                        continue

                    if delta_type != "text_delta":
                        continue

                    text_delta = str(delta.get("text") or "")
                    if not text_delta:
                        continue

                    assistant_text += text_delta

                    if not tool_mode:
                        yield _yield_text_delta(text_delta)
                        last_emission_at = time.time()
                        continue

                    visible_prefix = assistant_text.split("<tool_call>", 1)[0]
                    if len(visible_prefix) > emitted_visible_chars:
                        fresh_text = visible_prefix[emitted_visible_chars:]
                        emitted_visible_chars = len(visible_prefix)
                        if fresh_text:
                            yield _yield_text_delta(fresh_text)
                            last_emission_at = time.time()

                    _, parsed_tool_calls = self._extract_tool_calls(assistant_text)
                    if len(parsed_tool_calls) <= emitted_tool_count:
                        continue

                    for idx in range(emitted_tool_count, len(parsed_tool_calls)):
                        tool_call = parsed_tool_calls[idx]
                        yield SimpleNamespace(
                            id="claude-code-stream",
                            model=model_name,
                            choices=[
                                SimpleNamespace(
                                    index=0,
                                    delta=SimpleNamespace(
                                        content=None,
                                        tool_calls=[_tool_delta_from_call(tool_call, idx)],
                                        reasoning=None,
                                        reasoning_content=None,
                                    ),
                                    finish_reason=None,
                                )
                            ],
                            usage=None,
                        )
                        last_emission_at = time.time()
                    emitted_tool_count = len(parsed_tool_calls)
                    continue

            try:
                _, stderr = process.communicate(timeout=max(1.0, timeout_seconds))
            except subprocess.TimeoutExpired:
                process.kill()
                _, stderr = process.communicate()
                raise RuntimeError("Claude Code stream timed out.")

            if process.returncode != 0:
                raise RuntimeError((stderr or "").strip() or f"Claude Code exited with status {process.returncode}.")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            self._cleanup_mcp_tmp(mcp_tmp)

        if not final_payload:
            final_payload = {
                "result": assistant_text,
                "usage": {},
                "model": model_name,
            }

        final_text = str(final_payload.get("result") or assistant_text or "").strip()
        clean_content, final_tool_calls = self._extract_tool_calls(final_text)
        if tool_mode and clean_content:
            visible_prefix = clean_content
            if len(visible_prefix) > emitted_visible_chars:
                fresh_text = visible_prefix[emitted_visible_chars:]
                emitted_visible_chars = len(visible_prefix)
                if fresh_text:
                    yield _yield_text_delta(fresh_text)

        if tool_mode and len(final_tool_calls) > emitted_tool_count:
            for idx in range(emitted_tool_count, len(final_tool_calls)):
                tool_call = final_tool_calls[idx]
                yield SimpleNamespace(
                    id="claude-code-stream",
                    model=model_name,
                    choices=[
                        SimpleNamespace(
                            index=0,
                            delta=SimpleNamespace(
                                content=None,
                                tool_calls=[_tool_delta_from_call(tool_call, idx)],
                                reasoning=None,
                                reasoning_content=None,
                            ),
                            finish_reason=None,
                        )
                    ],
                    usage=None,
                )
            emitted_tool_count = len(final_tool_calls)

        usage = _usage_from_payload(final_payload)
        finish_reason = "tool_calls" if emitted_tool_count else "stop"
        yield _final_stream_delta(model=model_name, finish_reason=finish_reason, usage=usage)
