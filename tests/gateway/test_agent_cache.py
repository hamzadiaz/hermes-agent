"""Integration tests for gateway AIAgent caching.

Verifies that the agent cache correctly:
- Reuses agents across messages (same config → same instance)
- Rebuilds agents when config changes (model, provider, toolsets)
- Updates reasoning_config in-place without rebuilding
- Evicts on session reset
- Evicts on fallback activation
- Preserves frozen system prompt across turns
"""

import asyncio
import hashlib
import json
import sys
import threading
import types
from unittest.mock import MagicMock, patch

import pytest


def _make_runner():
    """Create a minimal GatewayRunner with just the cache infrastructure."""
    from gateway.run import GatewayRunner

    runner = GatewayRunner.__new__(GatewayRunner)
    runner._agent_cache = {}
    runner._agent_cache_lock = threading.Lock()
    return runner


def _make_run_agent_runner():
    """Create a bare GatewayRunner suitable for calling _run_agent directly."""
    import gateway.run as gateway_run

    runner = object.__new__(gateway_run.GatewayRunner)
    runner.adapters = {}
    runner._ephemeral_system_prompt = ""
    runner._prefill_messages = []
    runner._reasoning_config = None
    runner._show_reasoning = False
    runner._provider_routing = {}
    runner._fallback_model = None
    runner._running_agents = {}
    runner._session_db = None
    runner._agent_cache = {}
    runner._agent_cache_lock = threading.Lock()
    runner._get_or_create_gateway_honcho = lambda session_key: (None, None)
    runner.hooks = MagicMock()
    runner.hooks.emit = MagicMock()
    runner.hooks.loaded_hooks = []
    return runner


class TestAgentConfigSignature:
    """Config signature produces stable, distinct keys."""

    def test_same_config_same_signature(self):
        from gateway.run import GatewayRunner

        runtime = {"api_key": "sk-test12345678", "base_url": "https://openrouter.ai/api/v1",
                    "provider": "openrouter", "api_mode": "chat_completions"}
        sig1 = GatewayRunner._agent_config_signature("claude-sonnet-4", runtime, ["hermes-telegram"], "", "session-1")
        sig2 = GatewayRunner._agent_config_signature("claude-sonnet-4", runtime, ["hermes-telegram"], "", "session-1")
        assert sig1 == sig2

    def test_model_change_different_signature(self):
        from gateway.run import GatewayRunner

        runtime = {"api_key": "sk-test12345678", "base_url": "https://openrouter.ai/api/v1",
                    "provider": "openrouter"}
        sig1 = GatewayRunner._agent_config_signature("claude-sonnet-4", runtime, ["hermes-telegram"], "", "session-1")
        sig2 = GatewayRunner._agent_config_signature("claude-opus-4.6", runtime, ["hermes-telegram"], "", "session-1")
        assert sig1 != sig2

    def test_same_token_prefix_different_full_token_changes_signature(self):
        """Tokens sharing a JWT-style prefix must not collide."""
        from gateway.run import GatewayRunner

        rt1 = {
            "api_key": "eyJhbGci.token-for-account-a",
            "base_url": "https://chatgpt.com/backend-api/codex",
            "provider": "openai-codex",
            "api_mode": "codex_responses",
        }
        rt2 = {
            "api_key": "eyJhbGci.token-for-account-b",
            "base_url": "https://chatgpt.com/backend-api/codex",
            "provider": "openai-codex",
            "api_mode": "codex_responses",
        }

        assert rt1["api_key"][:8] == rt2["api_key"][:8]
        sig1 = GatewayRunner._agent_config_signature("gpt-5.3-codex", rt1, ["hermes-telegram"], "", "session-1")
        sig2 = GatewayRunner._agent_config_signature("gpt-5.3-codex", rt2, ["hermes-telegram"], "", "session-1")
        assert sig1 != sig2

    def test_provider_change_different_signature(self):
        from gateway.run import GatewayRunner

        rt1 = {"api_key": "sk-test12345678", "base_url": "https://openrouter.ai/api/v1", "provider": "openrouter"}
        rt2 = {"api_key": "sk-test12345678", "base_url": "https://api.anthropic.com", "provider": "anthropic"}
        sig1 = GatewayRunner._agent_config_signature("claude-sonnet-4", rt1, ["hermes-telegram"], "", "session-1")
        sig2 = GatewayRunner._agent_config_signature("claude-sonnet-4", rt2, ["hermes-telegram"], "", "session-1")
        assert sig1 != sig2

    def test_toolset_change_different_signature(self):
        from gateway.run import GatewayRunner

        runtime = {"api_key": "sk-test12345678", "base_url": "https://openrouter.ai/api/v1", "provider": "openrouter"}
        sig1 = GatewayRunner._agent_config_signature("claude-sonnet-4", runtime, ["hermes-telegram"], "", "session-1")
        sig2 = GatewayRunner._agent_config_signature("claude-sonnet-4", runtime, ["hermes-discord"], "", "session-1")
        assert sig1 != sig2

    def test_reasoning_not_in_signature(self):
        """Reasoning config is set per-message, not part of the signature."""
        from gateway.run import GatewayRunner

        runtime = {"api_key": "***", "base_url": "https://openrouter.ai/api/v1", "provider": "openrouter"}
        # Same config — signature should be identical regardless of what
        # reasoning_config the caller might have (it's not passed in)
        sig1 = GatewayRunner._agent_config_signature("claude-sonnet-4", runtime, ["hermes-telegram"], "", "session-1")
        sig2 = GatewayRunner._agent_config_signature("claude-sonnet-4", runtime, ["hermes-telegram"], "", "session-1")
        assert sig1 == sig2

    def test_session_id_change_different_signature(self):
        """A fresh session_id must force a fresh cached agent."""
        from gateway.run import GatewayRunner

        runtime = {"api_key": "***", "base_url": "https://openrouter.ai/api/v1", "provider": "openrouter"}
        sig1 = GatewayRunner._agent_config_signature(
            "claude-sonnet-4",
            runtime,
            ["hermes-telegram"],
            "",
            "session-old",
        )
        sig2 = GatewayRunner._agent_config_signature(
            "claude-sonnet-4",
            runtime,
            ["hermes-telegram"],
            "",
            "session-new",
        )
        assert sig1 != sig2


class TestAgentCacheLifecycle:
    """End-to-end cache behavior with real AIAgent construction."""

    def test_cache_hit_returns_same_agent(self):
        """Second message with same config reuses the cached agent instance."""
        from run_agent import AIAgent

        runner = _make_runner()
        session_key = "telegram:12345"
        runtime = {"api_key": "test", "base_url": "https://openrouter.ai/api/v1",
                    "provider": "openrouter", "api_mode": "chat_completions"}
        sig = runner._agent_config_signature("anthropic/claude-sonnet-4", runtime, ["hermes-telegram"], "", "session-1")

        # First message — create and cache
        agent1 = AIAgent(
            model="anthropic/claude-sonnet-4", api_key="test",
            base_url="https://openrouter.ai/api/v1", provider="openrouter",
            max_iterations=5, quiet_mode=True, skip_context_files=True,
            skip_memory=True, platform="telegram",
        )
        with runner._agent_cache_lock:
            runner._agent_cache[session_key] = (agent1, sig)

        # Second message — cache hit
        with runner._agent_cache_lock:
            cached = runner._agent_cache.get(session_key)
        assert cached is not None
        assert cached[1] == sig
        assert cached[0] is agent1  # same instance

    def test_cache_miss_on_model_change(self):
        """Model change produces different signature → cache miss."""
        from run_agent import AIAgent

        runner = _make_runner()
        session_key = "telegram:12345"
        runtime = {"api_key": "test", "base_url": "https://openrouter.ai/api/v1",
                    "provider": "openrouter", "api_mode": "chat_completions"}

        old_sig = runner._agent_config_signature("anthropic/claude-sonnet-4", runtime, ["hermes-telegram"], "", "session-1")
        agent1 = AIAgent(
            model="anthropic/claude-sonnet-4", api_key="test",
            base_url="https://openrouter.ai/api/v1", provider="openrouter",
            max_iterations=5, quiet_mode=True, skip_context_files=True,
            skip_memory=True, platform="telegram",
        )
        with runner._agent_cache_lock:
            runner._agent_cache[session_key] = (agent1, old_sig)

        # New model → different signature
        new_sig = runner._agent_config_signature("anthropic/claude-opus-4.6", runtime, ["hermes-telegram"], "", "session-1")
        assert new_sig != old_sig

        with runner._agent_cache_lock:
            cached = runner._agent_cache.get(session_key)
        assert cached[1] != new_sig  # signature mismatch → would create new agent

    def test_evict_on_session_reset(self):
        """_evict_cached_agent removes the entry."""
        from run_agent import AIAgent

        runner = _make_runner()
        session_key = "telegram:12345"

        agent = AIAgent(
            model="anthropic/claude-sonnet-4", api_key="test",
            base_url="https://openrouter.ai/api/v1", provider="openrouter",
            max_iterations=5, quiet_mode=True, skip_context_files=True,
            skip_memory=True,
        )
        with runner._agent_cache_lock:
            runner._agent_cache[session_key] = (agent, "sig123")

        runner._evict_cached_agent(session_key)

        with runner._agent_cache_lock:
            assert session_key not in runner._agent_cache

    def test_evict_does_not_affect_other_sessions(self):
        """Evicting one session leaves other sessions cached."""
        runner = _make_runner()
        with runner._agent_cache_lock:
            runner._agent_cache["session-A"] = ("agent-A", "sig-A")
            runner._agent_cache["session-B"] = ("agent-B", "sig-B")

        runner._evict_cached_agent("session-A")

        with runner._agent_cache_lock:
            assert "session-A" not in runner._agent_cache
            assert "session-B" in runner._agent_cache

    def test_reasoning_config_updates_in_place(self):
        """Reasoning config can be set on a cached agent without eviction."""
        from run_agent import AIAgent

        agent = AIAgent(
            model="anthropic/claude-sonnet-4", api_key="test",
            base_url="https://openrouter.ai/api/v1", provider="openrouter",
            max_iterations=5, quiet_mode=True, skip_context_files=True,
            skip_memory=True,
            reasoning_config={"enabled": True, "effort": "medium"},
        )

        # Simulate per-message reasoning update
        agent.reasoning_config = {"enabled": True, "effort": "high"}
        assert agent.reasoning_config["effort"] == "high"

        # System prompt should not be affected by reasoning change
        prompt1 = agent._build_system_prompt()
        agent._cached_system_prompt = prompt1  # simulate run_conversation caching
        agent.reasoning_config = {"enabled": True, "effort": "low"}
        prompt2 = agent._cached_system_prompt
        assert prompt1 is prompt2  # same object — not invalidated by reasoning change

    def test_system_prompt_frozen_across_cache_reuse(self):
        """The cached agent's system prompt stays identical across turns."""
        from run_agent import AIAgent

        agent = AIAgent(
            model="anthropic/claude-sonnet-4", api_key="test",
            base_url="https://openrouter.ai/api/v1", provider="openrouter",
            max_iterations=5, quiet_mode=True, skip_context_files=True,
            skip_memory=True, platform="telegram",
        )

        # Build system prompt (simulates first run_conversation)
        prompt1 = agent._build_system_prompt()
        agent._cached_system_prompt = prompt1

        # Simulate second turn — prompt should be frozen
        prompt2 = agent._cached_system_prompt
        assert prompt1 is prompt2  # same object, not rebuilt

    def test_callbacks_update_without_cache_eviction(self):
        """Per-message callbacks can be set on cached agent."""
        from run_agent import AIAgent

        agent = AIAgent(
            model="anthropic/claude-sonnet-4", api_key="***",
            base_url="https://openrouter.ai/api/v1", provider="openrouter",
            max_iterations=5, quiet_mode=True, skip_context_files=True,
            skip_memory=True,
        )

        # Set callbacks like the gateway does per-message
        cb1 = lambda *a: None
        cb2 = lambda *a: None
        agent.tool_progress_callback = cb1
        agent.step_callback = cb2
        agent.stream_delta_callback = None
        agent.status_callback = None

        assert agent.tool_progress_callback is cb1
        assert agent.step_callback is cb2

        # Update for next message
        cb3 = lambda *a: None
        agent.tool_progress_callback = cb3
        assert agent.tool_progress_callback is cb3

    def test_run_agent_rebuilds_cached_agent_when_session_id_changes(self, monkeypatch):
        """Same session_key + new session_id must not reuse a stale cached agent."""
        import gateway.run as gateway_run
        from gateway.config import Platform
        from gateway.session import SessionSource

        class _CountingAgent:
            init_calls = []

            def __init__(self, *args, **kwargs):
                type(self).init_calls.append(dict(kwargs))
                self.session_id = kwargs.get("session_id")
                self.tools = []
                self.reasoning_config = kwargs.get("reasoning_config")
                self.tool_progress_callback = None
                self.step_callback = None
                self.stream_delta_callback = None
                self.status_callback = None

            def run_conversation(self, message, conversation_history=None, task_id=None):
                return {
                    "final_response": "ok",
                    "messages": [],
                    "api_calls": 1,
                    "session_id": self.session_id,
                }

        fake_run_agent = types.ModuleType("run_agent")
        fake_run_agent.AIAgent = _CountingAgent
        monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)
        monkeypatch.setattr(gateway_run, "load_dotenv", lambda *args, **kwargs: None)
        monkeypatch.setattr(gateway_run, "_resolve_runtime_agent_kwargs", lambda: {
            "provider": "openrouter",
            "api_mode": "chat_completions",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "***",
        })

        runner = _make_run_agent_runner()
        source = SessionSource(
            platform=Platform.LOCAL,
            chat_id="cli",
            chat_name="CLI",
            chat_type="dm",
            user_id="user-1",
        )

        _CountingAgent.init_calls = []
        session_key = "agent:main:local:dm"

        result1 = asyncio.run(
            runner._run_agent(
                None,
                message="ping",
                context_prompt="",
                history=[],
                source=source,
                session_id="session-1",
                session_key=session_key,
            )
        )
        result2 = asyncio.run(
            runner._run_agent(
                None,
                message="ping again",
                context_prompt="",
                history=[],
                source=source,
                session_id="session-2",
                session_key=session_key,
            )
        )

        assert result1["final_response"] == "ok"
        assert result2["final_response"] == "ok"
        assert len(_CountingAgent.init_calls) == 2
        assert _CountingAgent.init_calls[0]["session_id"] == "session-1"
        assert _CountingAgent.init_calls[1]["session_id"] == "session-2"
