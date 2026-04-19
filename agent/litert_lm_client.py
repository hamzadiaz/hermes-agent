"""OpenAI-compatible shim that forwards Hermes requests to `litert-lm run`.

This adapter lets Hermes treat local LiteRT-LM models as a chat backend.
When Hermes provides tool definitions, the model is instructed to emit Hermes
XML tool calls so Hermes can keep owning the actual tool runtime.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

from environments.tool_call_parsers.hermes_parser import HermesToolCallParser

CLI_MARKER_BASE_URL = "cli://litert-lm"
_DEFAULT_TIMEOUT_SECONDS = 900.0
_DEFAULT_MAX_PROMPT_CHARS = 12000
_DEFAULT_MAX_MESSAGES = 6
_TOOL_CALL_BLOCK_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
_ALT_TOOL_CALL_BLOCK_RE = re.compile(r"<\|tool_call\>call:(?P<name>[A-Za-z0-9_:-]+)\{(?P<body>.*?)\}<tool_call\|>", re.DOTALL)
_ABS_PATH_RE = re.compile(r"(/[A-Za-z0-9._~\-]+(?:/[A-Za-z0-9._~\-]+)+)")


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


def _truncate_for_prompt(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    keep = max(0, limit - len("\n\n[truncated]\n"))
    return text[-keep:] + "\n\n[truncated]\n"


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
        parts.append(
            "<tool_call>\n"
            f"{json.dumps({'name': name, 'arguments': arguments}, ensure_ascii=False)}\n"
            "</tool_call>"
        )
    return "\n".join(parts)


def _extract_tool_calls(text: str, parser: HermesToolCallParser) -> tuple[str | None, list[Any]]:
    content, tool_calls = parser.parse(text)
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
    if not tool_calls and "<|tool_call>" in text:
        fallback_tool_calls = []
        for index, match in enumerate(_ALT_TOOL_CALL_BLOCK_RE.finditer(text)):
            name = str(match.group("name") or "").strip()
            body = str(match.group("body") or "").strip()
            if not name:
                continue
            arguments: dict[str, Any] = {}
            if body:
                for key, value in re.findall(r"([A-Za-z0-9_]+)\s*:\s*(.+?)(?=,\s*[A-Za-z0-9_]+\s*:|$)", body):
                    cleaned = value.strip()
                    cleaned = cleaned.replace('<|"|>', '"').strip()
                    if cleaned.startswith('"') and cleaned.endswith('"') and len(cleaned) >= 2:
                        cleaned = cleaned[1:-1]
                    arguments[key] = cleaned
            fallback_tool_calls.append(
                SimpleNamespace(
                    id=f"call_alt_{index}",
                    type="function",
                    function=SimpleNamespace(
                        name=name,
                        arguments=json.dumps(arguments, ensure_ascii=False),
                    ),
                )
            )
        if fallback_tool_calls:
            tool_calls = fallback_tool_calls
            content = text[: text.find("<|tool_call>")].strip() or None
    clean_content = content if isinstance(content, str) else None
    if clean_content is not None:
        clean_content = clean_content.strip() or None
    return clean_content, list(tool_calls or [])


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
    max_prompt_chars = int(os.getenv("HERMES_LITERT_LM_MAX_PROMPT_CHARS", str(_DEFAULT_MAX_PROMPT_CHARS)) or _DEFAULT_MAX_PROMPT_CHARS)
    max_messages = int(os.getenv("HERMES_LITERT_LM_MAX_MESSAGES", str(_DEFAULT_MAX_MESSAGES)) or _DEFAULT_MAX_MESSAGES)
    tool_mode = bool(tools)
    literal_strings = _extract_literal_strings(messages)
    sections: list[str] = ["You are being used as the active LiteRT-LM backend for Hermes."]
    if tool_mode:
        sections.extend(
            [
                "Hermes owns the tool runtime. The only authoritative tool list is inside <tools> below.",
                "For any claim about local files, source code, shell commands, browser state, screenshots, UI, processes, logs, skills, or memory, you must use Hermes tools first.",
                "Do not answer from memory for repository inspection, code review, debugging, browser inspection, screenshots, or local environment questions.",
                "If read_file appears in <tools>, you do have filesystem access through Hermes.",
                "If search_files appears in <tools>, you do have repository search through Hermes.",
                "If terminal appears in <tools>, you do have shell access through Hermes.",
                "If browser_navigate/browser_snapshot/browser_vision appear in <tools>, you do have browser and screenshot inspection through Hermes.",
                "Never claim you only have browser-only or built-in tools when Hermes tools are present.",
                "Use read_file for reading files and search_files for finding files before falling back to terminal.",
                "Copy user-provided file paths, URLs, commands, filenames, and identifiers exactly. Do not shorten, normalize, or rewrite them.",
                "If the user asks to read or inspect a specific local file path, calling read_file with that exact path is mandatory before answering.",
                "If the user asks to search a codebase or find files, calling search_files is mandatory before answering.",
                "When a tool is needed, emit Hermes XML tool calls only.",
                "Prefer Hermes names like read_file, search_files, terminal, browser_navigate, browser_snapshot, browser_vision, memory, and todo.",
                "Never say a tool ran unless Hermes has already returned a <tool_response> for it.",
                "When you decide to use tools, output one or more <tool_call> blocks and nothing else after them.",
                "<tools>\n" + f"{_format_tools_for_prompt(tools)}\n" + "</tools>",
                "Each function call must match this JSON shape:",
                "{'name': <function-name>, 'arguments': <args-dict>}",
                "Each function call must be enclosed inside <tool_call> and </tool_call>.",
            ]
        )
    else:
        sections.extend(
            [
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

    transcript: list[str] = []
    compact_messages = list(messages[-max_messages:]) if max_messages > 0 else list(messages)
    for message in compact_messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "unknown").strip().lower()
        source_role = role
        if role not in {"system", "user", "assistant", "tool"}:
            role = "context"
        rendered = _render_message_content(message.get("content"))
        if source_role == "assistant":
            xml = _assistant_tool_xml(message)
            if xml:
                rendered = "\n".join(part for part in (rendered, xml) if part).strip()
        elif source_role == "tool" and rendered:
            rendered = f"<tool_response>\n{rendered}\n</tool_response>"
        if not rendered:
            continue
        if role == "system":
            rendered = _truncate_for_prompt(rendered, max(800, max_prompt_chars // 6))
        elif role == "assistant":
            rendered = _truncate_for_prompt(rendered, max(1000, max_prompt_chars // 4))
        else:
            rendered = _truncate_for_prompt(rendered, max(1500, max_prompt_chars // 3))
        label = {
            "system": "System",
            "user": "User",
            "assistant": "Assistant",
            "tool": "Tool",
            "context": "Context",
        }.get(role, role.title())
        transcript.append(f"{label}:\n{rendered}")

    if transcript:
        sections.append("Recent conversation transcript:\n\n" + "\n\n".join(transcript))
    sections.append("Continue the conversation from the latest user request.")
    prompt = "\n\n".join(part.strip() for part in sections if part and part.strip())
    return _truncate_for_prompt(prompt, max_prompt_chars)


def _usage_stub(text: str) -> Any:
    completion_tokens = max(1, len(text) // 4) if text else 0
    return SimpleNamespace(
        prompt_tokens=0,
        completion_tokens=completion_tokens,
        total_tokens=completion_tokens,
        prompt_tokens_details=SimpleNamespace(cached_tokens=0),
    )


def _stream_chunks_from_text(
    text: str,
    *,
    model: str,
    usage: Any,
    tool_calls: list[Any] | None = None,
) -> Iterable[Any]:
    chunks: list[Any] = []
    if text:
        chunks.append(
            SimpleNamespace(
                id="litert-lm-stream",
                model=model,
                choices=[
                    SimpleNamespace(
                        index=0,
                        delta=SimpleNamespace(content=text, tool_calls=None, reasoning=None, reasoning_content=None),
                        finish_reason=None,
                    )
                ],
                usage=None,
            )
        )
    for index, tool_call in enumerate(tool_calls or []):
        chunks.append(
            SimpleNamespace(
                id="litert-lm-stream",
                model=model,
                choices=[
                    SimpleNamespace(
                        index=0,
                        delta=SimpleNamespace(
                            content=None,
                            tool_calls=[_tool_delta_from_call(tool_call, index)],
                            reasoning=None,
                            reasoning_content=None,
                        ),
                        finish_reason=None,
                    )
                ],
                usage=None,
            )
        )
    chunks.append(
        SimpleNamespace(
            id="litert-lm-stream",
            model=model,
            choices=[
                SimpleNamespace(
                    index=0,
                    delta=SimpleNamespace(content=None, tool_calls=None, reasoning=None, reasoning_content=None),
                    finish_reason="tool_calls" if tool_calls else "stop",
                )
            ],
            usage=usage,
        )
    )
    return chunks


class _LiteRtLmChatCompletions:
    def __init__(self, client: "LiteRtLmClient"):
        self._client = client

    def create(self, **kwargs: Any) -> Any:
        return self._client._create_chat_completion(**kwargs)


class _LiteRtLmChatNamespace:
    def __init__(self, client: "LiteRtLmClient"):
        self.completions = _LiteRtLmChatCompletions(client)


class LiteRtLmClient:
    """Minimal OpenAI-client-compatible facade for LiteRT-LM CLI."""

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
        self.api_key = api_key or "litert-lm"
        self.base_url = base_url or CLI_MARKER_BASE_URL
        self._default_headers = dict(default_headers or {})
        self._command = command or os.getenv("HERMES_LITERT_LM_COMMAND", "").strip() or "litert-lm"
        self._args = list(args or [])
        self._cwd = str(Path(os.getenv("HERMES_LITERT_LM_CWD", str(Path.home()))).expanduser().resolve())
        self._backend = os.getenv("HERMES_LITERT_LM_BACKEND", "gpu").strip() or "gpu"
        self._tool_parser = HermesToolCallParser()
        self.chat = _LiteRtLmChatNamespace(self)
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
        model_name = str(model or "").strip()
        if not model_name:
            raise RuntimeError("LiteRT-LM requires an explicit model id.")

        prompt_text = _format_messages_as_prompt(messages or [], model=model_name, tools=tools)
        response_text = self._run_prompt(prompt_text, model=model_name, timeout_seconds=float(timeout or _DEFAULT_TIMEOUT_SECONDS))
        clean_content, tool_calls = _extract_tool_calls(response_text, self._tool_parser)
        usage = _usage_stub(response_text)

        if stream:
            return _stream_chunks_from_text(clean_content or "", model=model_name, usage=usage, tool_calls=tool_calls)

        assistant_message = SimpleNamespace(
            content=clean_content,
            tool_calls=tool_calls,
            reasoning=None,
            reasoning_content=None,
            reasoning_details=None,
        )
        choice = SimpleNamespace(message=assistant_message, finish_reason="tool_calls" if tool_calls else "stop")
        return SimpleNamespace(
            choices=[choice],
            usage=usage,
            model=model_name,
        )

    def _run_prompt(self, prompt_text: str, *, model: str, timeout_seconds: float) -> str:
        cmd = [
            self._command,
            "run",
            model,
            "-b",
            self._backend,
            "--prompt",
            prompt_text,
        ]
        cmd.extend(self._args)

        try:
            completed = subprocess.run(
                cmd,
                cwd=self._cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Could not start LiteRT-LM command '{self._command}'. "
                "Install litert-lm or set HERMES_LITERT_LM_COMMAND."
            ) from exc

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        if completed.returncode != 0:
            raise RuntimeError(stderr or stdout or f"LiteRT-LM exited with status {completed.returncode}.")
        if not stdout:
            raise RuntimeError(stderr or "LiteRT-LM returned no text output.")
        return stdout
