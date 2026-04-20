# Learnings — Hermes Memory/Recall Stability Fix

## L1: Root cause of stale-agent reuse
Auto-reset (idle/daily) was not evicting cached AIAgent instances or shutting down Honcho sessions the way manual `/new` does. Combined with a cache signature that excluded `session_id`, this allowed the same stale AIAgent to be reused for what appeared to be a fresh session. Fix: add `_shutdown_gateway_honcho` + `_evict_cached_agent` to auto-reset path AND include `session_id` in `_agent_config_signature`.

## L2: Testing
- Test suite lives in `venv/bin/python3 -m pytest`
- Key test files: tests/gateway/test_agent_cache.py, tests/gateway/test_honcho_lifecycle.py
- 20/20 pass after fix

## L3: Repo state
- Local is 1794 commits behind origin/main
- Many modified hot files (gateway/run.py, prompt_builder.py, anthropic_adapter.py)
- Safe update requires a dedicated integration branch, never blind pull on hot tree

## L4: Agent restart sequence
- Use `launchctl kickstart -k gui/$(id -u)/ai.hermes.agent.<name>` to force-restart
- Always verify with a fresh session after restart
- mark and buni have crash histories — investigate separately

## L5: Model policy
- Anthropic testing: always Opus 4.7 (never 4.6 or below)
- GPT paths: test GPT-5.4 / GPT-5.3 Codex-family where available
- Model switching: always use optijara.ai/models → Save → /new workflow

## L6: Upstream merge is NOT safe to auto-execute
- Local gateway/run.py = 6536 lines; upstream = 10891 lines (completely restructured, 1810 commits ahead)
- Our two critical fixes are NOT in upstream — blind merge would destroy them:
  - **Fix A**: `session_id or ""` in `_agent_config_signature` blob (local line 5383 as of 2026-04-20)
    - In `_agent_config_signature` method, the `session_id or ""` ensures different sessions get different cache keys
  - **Fix B**: `_shutdown_gateway_honcho` + `_evict_cached_agent` in `was_auto_reset` path (local lines 2198-2204 as of 2026-04-20)
    - In `_handle_message_with_agent`, the `if getattr(session_entry, 'was_auto_reset', False)` block must call both methods before running the agent
  - **Scout 26 fix**: `run_agent.py:2825` — context_cwd uses HERMES_HOME not os.getcwd()
  - **Scout 33 fix**: `agent/auxiliary_client.py` — external_process provider logs at DEBUG not WARNING
  - **Scout 39 fix**: `hermes_state.py:140` — `SessionDB.__init__` calls `get_hermes_home()` dynamically
- Integration branch `integration/upstream-merge-2026-04-19` created for safe merge work
- Correct approach: apply upstream changes on integration branch, manually re-apply fixes, re-verify
- The integration branch is now 50 commits behind main (all Scout docs + code fixes since April 19)

## L10: Test suite has many xdist (parallel) isolation failures that pass sequentially (2026-04-19)

Running the full test suite with xdist (-n auto, 10 workers) causes 100+ "failures" that all pass when run individually (sequential). Root causes: global state in tool modules (session trackers, singletons), shared tmp dirs.

Don't use total xdist failure count to judge code health. Use per-module counts or run suspected tests individually to confirm real vs xdist failures. The 31 core gateway tests are stable and use per-test isolation.

## L9: Compression summary fails with Codex because summary_model not routed to Google API (2026-04-19)

`compression.summary_model: gemini-3-flash-preview` was set in config but `auxiliary.compression` had no api_key/base_url. Auto-detect resolved to Codex (gpt-5.4), then passed `gemini-3-flash-preview` as model override — Codex API rejected it.

Fix: wired `auxiliary.compression` with the same Google API key + base_url as `auxiliary.session_search`. Updated `summary_model` to `gemini-3.1-flash-lite-preview` (proven to work). Gateway restarted (now PID 97792).

Lesson: The auxiliary task config sections need matching api_key + base_url when using a model from a specific provider (e.g., Google Gemini). Leaving them empty while setting `model:` causes the model to be sent to whatever auto-detects first (often Codex), which may reject it.

## L8: cli:// URI scheme not recognized as known provider in model_metadata (2026-04-19)

`_is_custom_endpoint("cli://claude-code")` returned True (non-empty, not openrouter) but `_is_known_provider_base_url` returned False (URL parsing breaks on non-HTTP schemes). This caused early return at step 2 with 128K probe-down default instead of reaching step 8 hardcoded defaults.

Fix: exclude `cli://` prefix from `_is_custom_endpoint`; add `claude-opus-4-7/claude-sonnet-4-7` (200K) to DEFAULT_CONTEXT_LENGTHS. Tests: 77/77 model_metadata tests pass; 31/31 gateway tests pass.

Log symptom: `INFO agent.model_metadata: Could not detect context length for model 'claude-opus-4-7' at cli://claude-code — defaulting to 128,000 tokens (probe-down)` on every message.

## L11: Test environment-specificity patterns (2026-04-19)

When tests fail due to machine-specific state (auth credentials, config), common patterns:
- **GitHub Copilot auth**: mock `hermes_cli.copilot_auth._try_gh_cli_token` → None
- **OpenRouter reasoning tests**: set `agent.base_url = "https://openrouter.ai/api/v1"` + reasoning-capable model prefix (`anthropic/`, `openai/`, `qwen/qwen3`, etc.)
- **`_replace_primary_openai_client`**: can silently replace mock client with real OpenAI during error recovery; stub it out in streaming tests to keep mock in place
- **Provider auto-detection**: `detect_provider_for_model` / `_has_any_provider_configured` return machine-specific results; assert `in (allowed_set)` rather than `==`
- **Vision fallback test**: mock specific `_try_*` functions rather than env vars when `_resolve_custom_runtime` reads from runtime provider config

## L13: `gateway/run.py` `load_hermes_dotenv()` at module level injects real .env into os.environ during test collection (2026-04-19)

When `test_codex_execution_paths.py` imports `gateway.run` at module level, `load_hermes_dotenv()` is called with the REAL `~/.hermes/` directory (HERMES_HOME hasn't been monkeypatched yet). This loads `TELEGRAM_BOT_TOKEN`, `DISCORD_BOT_TOKEN`, etc. from the real `.env` into `os.environ`.

These tokens then persist for the entire test session. `_get_enabled_platforms()` in tools_config sees them and includes Telegram/Discord in the platform list, causing `test_first_install_nous_auto_configures_managed_defaults` to process multiple platforms. After CLI auto-configures tools, Telegram sees them as `explicit_configured=True` and routes them to `_configure_toolset` instead.

Fix: Added bot token cleanup to `tests/conftest.py::_isolate_hermes_home`:
```python
for _tok in ("TELEGRAM_BOT_TOKEN", "DISCORD_BOT_TOKEN", "SLACK_BOT_TOKEN", "WHATSAPP_ENABLED"):
    monkeypatch.delenv(_tok, raising=False)
```

## L12: `redact_sensitive_text` has catastrophic backtracking on large repeated-char content (2026-04-19)

`_ENV_ASSIGN_RE` in `agent/redact.py` uses `[A-Z_]*(?:API_?KEY|TOKEN|...)` which exhibits O(n²) backtracking on strings containing only `[A-Za-z]` characters (e.g. "yyyyyyy..."). Tests creating synthetic content >10K chars for file_read_guards tests must mock `tools.file_tools.redact_sensitive_text` to avoid the 30s conftest timeout.

Fix pattern:
```python
@patch("tools.file_tools.redact_sensitive_text", side_effect=lambda x: x)
```
Add as outermost decorator; becomes last arg in the test method signature.

## L14: `test_parallel_mixed_approve_deny` race condition (2026-04-19)

The test used `time.sleep(0.3)` to wait for two threads to submit to the approval queue before resolving. This was a race condition — the fixed-sleep was insufficient under xdist parallel load, causing the test to sometimes resolve an empty queue.

Two bugs in one test:
1. Race condition: Replace `time.sleep(0.3)` with `pending_approval_count(session_key) >= 2` polling loop (same pattern as `test_parallel_subagent_approvals`).
2. Determinism: Test asserted `results[0]["approved"] is True` assuming thread 0 always enters the queue first. Thread scheduling is non-deterministic. Fix: `assert sorted(r["approved"] for r in results) == [False, True]`.

When run in the full suite under xdist, the "once" approval resolved an already-cleared queue (from `setup_method` clearing stale state from parallel tests). The fix: polling + ordering-agnostic assertions.

## L16: sys.modules mutation without restore poisons sibling test modules (2026-04-19)

Tests that aggressively remove module prefixes from sys.modules (e.g., `_reset_modules(("tools", "agent", "hermes_cli"))`) without cleanup cause downstream test modules to fail. When module B's classes were imported at collection time from module A, and test code later removes module A from sys.modules and reimports a fresh version, any monkeypatch that patches `"module_A.ATTR"` now patches the NEW module — but the class's `__globals__` still point to the OLD module. The class methods look up globals in the OLD module and find the real path (e.g., `~/.hermes/memories`).

**Pattern to detect**: `sys.modules.pop(name, None)` in test code without a matching restore in try/finally or autouse fixture.

**Affected files found**: `test_managed_modal_environment.py` (missing restore), `test_cli_provider_resolution.py` (missing restore for tools.*).

**Fix template** (add to each contaminating file):
```python
@pytest.fixture(autouse=True)
def _restore_sys_modules():
    snapshot = {k: v for k, v in sys.modules.items()}
    yield
    for key in list(sys.modules):
        if key not in snapshot:
            del sys.modules[key]
    for key, val in snapshot.items():
        sys.modules[key] = val
```

**Caution**: if tests within the same file intentionally chain on each other's sys.modules state (calling `_import_cli()` or similar per-test), a full snapshot restore will break them. Instead, restore only the modules that the contaminating test REMOVES (not the ones it adds). See `test_cli_provider_resolution.py`'s `_restore_tools_modules` for the targeted approach.

## L15: FakeHAServer WS close handshake deadlock (2026-04-19)

`FakeHAServer._handle_ws` after handshake only reads from `asyncio.Queue` (event push), never from the WebSocket itself. When the client sends a CLOSE frame, aiohttp buffers it but can't auto-respond without the server reading from the WS. `ws_connect(timeout=30)` (deprecated float form) becomes `ws_close=30`, so `ws.close()` waits 30s for server close response → SIGALRM fires.

Fix: run `_drain_incoming()` (`async for msg in ws: pass`) alongside `_write_events()` via `asyncio.gather`. The drain loop lets aiohttp complete the close handshake automatically. Test time: 30s → <1ms.

**Also**: `test_event_received_and_forwarded` had a second bug — missing `watch_all=True` on the adapter, causing all events to be dropped by the filter. The 30s hang previously masked this logic failure.

Pattern: if your fake server's WS handler loop never reads from the WS after handshake, it will deadlock any client that tries to close cleanly.

## L17: os.environ leaks through dotenv and setdefault (2026-04-19)

Three patterns that let env vars escape test isolation:

1. **`monkeypatch.delenv(key, raising=False)` when key doesn't exist**: monkeypatch records the original "absent" state. If external code (e.g. `dotenv.load_dotenv()`) then sets the key directly, monkeypatch may or may not clean it up depending on version. **Fix**: add an autouse fixture that saves/restores `os.environ` entirely (`snapshot = os.environ.copy()` / `os.environ.clear(); os.environ.update(snapshot)`).

2. **`dotenv.load_dotenv()` called directly**: modifies `os.environ` outside monkeypatch tracking. `test_env_loader.py` tests call `load_hermes_dotenv()` which internally calls `dotenv.load_dotenv()`, setting `OPENAI_API_KEY=project-key`. Fix: `_restore_os_environ` autouse fixture in the test file.

3. **`os.environ.setdefault(key, value)` in `setUp` without `tearDown` cleanup**: `test_real_interrupt_subagent.py::setUp` set `OPENAI_API_KEY=test-key` permanently. Fix: save `_was_set` flag in setUp, pop key in tearDown if it wasn't originally present.

Downstream symptom: `test_managed_media_gateways.py` tests that expect no `OPENAI_API_KEY` (so managed gateway is used) fail because prior test leaked the key.

## L18: `/yolo` command sets os.environ globally (2026-04-19)

`gateway/run.py::_handle_yolo_command` toggles `os.environ["HERMES_YOLO_MODE"]`. E2E tests that call `/yolo` via `send_and_capture()` persist this flag for the entire process. **Symptom**: `TestBlockingApprovalE2E` tests in `test_approve_deny_commands.py` all auto-approve because YOLO mode is ON. **Fix**: `_reset_yolo_mode` autouse fixture in `tests/e2e/conftest.py` that saves/restores `HERMES_YOLO_MODE`.

## L19: `_import_cli()` in test_cli_provider_resolution creates TWO run_agent module objects (2026-04-19)

`_import_cli()` pops `cli`, `run_agent`, `tools`, `tools.*` from sys.modules, then reimports `cli` (which reimports `run_agent`). The original fixture only restored `tools.*`, leaving `run_agent` pointing to the NEW module. `test_run_agent.py` uses the ORIGINAL `AIAgent` (bound at collection time) but `from run_agent import _SafeWriter` now returns NEW `_SafeWriter` class → `isinstance(sys.stdout, _SafeWriter)` returns False (two different class objects).

**Fix**: expand `_restore_cli_modules` to also restore `cli` and `run_agent`. Safe because every test in the file calls `_import_cli()` unconditionally at the start, so pre-test state doesn't matter.

## L20: User-installed skills in ~/.hermes/skills affect test behavior (2026-04-19)

`cli.py` calls `_skill_commands = scan_skill_commands()` at module level. If `tools.skills_tool` is first imported BEFORE test isolation (HERMES_HOME monkeypatch), `SKILLS_DIR` points to the real `~/.hermes/skills/`. If the user has a `context` skill, `/context` becomes a skill command. Tests that use `/context` as an alias target fail with `AttributeError: 'HermesCLI' object has no attribute 'session_id'`.

**Fix**: add `session_id` to the `HermesCLI` stub in `_make_cli()`. This makes the stub complete regardless of which commands the alias target resolves to.

## L21: xdist workers sharing same test identity for acquire_scoped_lock cause non-deterministic failures (2026-04-19)

`gateway.status.acquire_scoped_lock(scope, identity)` writes a PID lock file to `~/.local/state/hermes/gateway-locks/` (NOT in HERMES_HOME — not isolated by conftest). When multiple xdist workers call `acquire_scoped_lock` with the same identity string (e.g., `/tmp/test-wa-session`), the first worker writes its PID; subsequent workers see that PID, check it's alive (`os.kill(pid, 0)` succeeds — the other worker is still running), and get `(False, {pid: N})`. Sequential runs pass because the same pytest process holds the lock across all tests (`os.getpid() == existing_pid` → re-acquire allowed).

**Fix**: patch `gateway.status.acquire_scoped_lock` to return `(True, None)` in tests that don't exercise the lock mechanism itself. Use a module-level autouse fixture to avoid touching index-based patch lists.

## L7: All live agents confirmed healthy after fix (2026-04-19)
- 6 DM bots tested via Telegram: Hermes, Codex, Claude, MALIK, Mark, Buni — all confirmed terminal available after /new
- Fleet Mission Control: 11/11 running, 0 errors, 0 idle
- Memory stack verified: session_search, skills, cron, Obsidian all working correctly

## L22: Using `object()` as a mock DB causes spurious ERROR-level log pollution (2026-04-20)

`object()` is truthy, so it bypasses the `if db is None` guard in `session_search()`. Any code path that then calls a SessionDB method (e.g., `db.list_sessions_rich()`) raises `AttributeError`, which is caught and logged at ERROR level. These errors land in `errors.log` and look like production failures.

**Fix**: use `db=None` for tests that don't need a DB. The `db is None` guard returns a clean `"not available"` error with no logging. Reserve `MagicMock()` for tests that need to exercise DB method call paths.

**Symptom pattern**: `'object' object has no attribute 'list_sessions_rich'` appearing in errors.log despite no production issues.

**Affected file**: `tests/tools/test_session_search.py` — `test_empty_query_no_db_returns_error` and `test_whitespace_query_no_db_returns_error` were using `object()`. Fixed 2026-04-20 (Scout 25).

## L24: Auxiliary config must be explicit for all 3 core tasks: session_search, compression, flush_memories (2026-04-20)

Every agent config needs explicit `auxiliary.session_search`, `auxiliary.compression`, and `auxiliary.flush_memories` sections with matching `model`, `base_url`, and `api_key` values. Without explicit config:

- `provider: auto` routes via `_resolve_auto()` which tries `_try_custom_endpoint` and uses `_read_main_model()` as the model override — sending the pro/expensive model (e.g., `gemini-3.1-pro-preview`) to compression calls instead of the intended flash-lite model.
- For agents that use OpenAI-codex as primary, auto-detect may route to Codex, which will reject any passed Gemini model name (returns 404 or unsupported model error).
- For claude-code / litert-lm agents, `resolve_provider_client` short-circuits for `external_process` auth_type, silently returning `(None, None)` — leading to silent failure until logs are checked.

**Standard template for Gemini agents** (all agents in this fleet except codex and Codex-primary ones):
```yaml
auxiliary:
  session_search:
    provider: auto
    model: gemini-3.1-flash-lite-preview
    base_url: https://generativelanguage.googleapis.com/v1beta/openai
    api_key: <GOOGLE_GEMINI_KEY>
    timeout: 30
  compression:
    provider: auto
    model: gemini-3.1-flash-lite-preview
    base_url: https://generativelanguage.googleapis.com/v1beta/openai
    api_key: <GOOGLE_GEMINI_KEY>
    timeout: 120
  flush_memories:
    provider: auto
    model: gemini-3.1-flash-lite-preview
    base_url: https://generativelanguage.googleapis.com/v1beta/openai
    api_key: <GOOGLE_GEMINI_KEY>
    timeout: 30
```

For codex-primary agents (codex agent), substitute `codex`'s own API key (`AIzaSyB8kzbUUgV0nFjZJ5X-WTic0_Am57l0pNg`).

Note: `vision`, `web_extract`, `skills_hub`, `approval`, `mcp` can stay as `model: ''` since they have different auto-detect paths or are less latency-sensitive.

**Applied scouts**: 29 (session_search), 30 (all 10 agents), 31 (compression), 32 (flush_memories), 35 (mark fix).

## L23: Dev AGENTS.md poisons production sessions via WorkingDirectory + missing TERMINAL_CWD (2026-04-20)

All gateway LaunchAgents set `WorkingDirectory=/Users/hamzadiaz/.hermes/hermes-agent` (the repo). When `TERMINAL_CWD` is not set, `build_context_files_prompt(cwd=None)` falls back to `os.getcwd()` = the repo dir. The repo's `AGENTS.md` (developer docs advertising `terminal_tool.py`, `read_file`, `write_file`, etc.) is then injected into every production session's system prompt.

**Symptom**: Agents report "I have terminal, read_file, write_file tools" in sessions where only MCP browser tools are wired (e.g., `claude_code_client` path). Confirmed in session `20260420_011907_ff163f66`.

**Fix** (in `run_agent.py`):
```python
_context_cwd = (
    os.getenv("TERMINAL_CWD")
    or os.getenv("HERMES_HOME")
    or None
)
```
`HERMES_HOME` dirs (`~/.hermes/`, `~/.hermes-agents/<name>/`) have no `AGENTS.md`, so `build_context_files_prompt` finds nothing and injects nothing. Token savings: ~10K tokens per session.

**Key principle**: never use `os.getcwd()` as a fallback for config file discovery in a process that runs from a developer repo dir. Always use the user's config home or an explicit env var.

**Fixed 2026-04-20 (Scout 26)**; all 11 gateways restarted to pick up the change.

## L25: Module-level HERMES_HOME constants break test isolation — use get_hermes_home() at call time (2026-04-20)

`hermes_state.py` had `DEFAULT_DB_PATH = get_hermes_home() / "state.db"` evaluated **at module import time**. The test conftest's `_isolate_hermes_home` fixture redirects `HERMES_HOME` via `monkeypatch.setenv()` *after* module import, so any module-level constant that calls `get_hermes_home()` is already fixed to `~/.hermes`.

**Symptom**: Every test run of `test_cron_run_job_codex_path_handles_internal_401_refresh` wrote a real `cron_job-1_*` session record to `~/.hermes/state.db` (model=`gpt-5.3-codex`, 0 messages, duration ~0.1s). 108 such sessions accumulated over the April 19-20 overnight run.

**Fix**: Change `SessionDB.__init__` to compute the path dynamically:
```python
self.db_path = db_path or (get_hermes_home() / "state.db")
```

**Rule**: Any code that instantiates resources tied to `HERMES_HOME` (databases, file stores, config readers) must call `get_hermes_home()` at instantiation/call time, not at module load time. Module-level constants are fine for display/logging but not for resource paths that tests need to redirect.

**Detection**: If you see sessions with test-specific models (e.g., `gpt-5.3-codex`) in production state.db with 0 messages and ~0.1s duration, they are test artifact leakage — look for module-level `HERMES_HOME` caching.

**Fixed 2026-04-20 (Scout 39)**, commit `0b1cd0a7`.
