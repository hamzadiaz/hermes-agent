"""Tests for tools/tool_backend_helpers.py.

Covers the pure logic helpers: coerce_modal_mode, normalize_browser_cloud_provider,
and resolve_modal_backend_state (which has meaningful branching).
"""

import os
import pytest
from tools.tool_backend_helpers import (
    coerce_modal_mode,
    normalize_browser_cloud_provider,
    resolve_modal_backend_state,
    resolve_openai_audio_api_key,
)


# ── normalize_browser_cloud_provider ──────────────────────────────────────────

class TestNormalizeBrowserCloudProvider:
    def test_none_returns_default(self):
        assert normalize_browser_cloud_provider(None) == "local"

    def test_empty_string_returns_default(self):
        assert normalize_browser_cloud_provider("") == "local"

    def test_value_lowercased_and_stripped(self):
        assert normalize_browser_cloud_provider("  BrowserBase  ") == "browserbase"

    def test_known_value_passed_through(self):
        assert normalize_browser_cloud_provider("local") == "local"


# ── coerce_modal_mode ──────────────────────────────────────────────────────────

class TestCoerceModalMode:
    def test_none_returns_auto(self):
        assert coerce_modal_mode(None) == "auto"

    def test_valid_direct(self):
        assert coerce_modal_mode("direct") == "direct"

    def test_valid_managed(self):
        assert coerce_modal_mode("managed") == "managed"

    def test_invalid_value_returns_auto(self):
        assert coerce_modal_mode("invalid_mode") == "auto"

    def test_case_insensitive(self):
        assert coerce_modal_mode("DIRECT") == "direct"


# ── resolve_modal_backend_state ────────────────────────────────────────────────

class TestResolveModalBackendState:
    """tools/tool_backend_helpers.py — resolve_modal_backend_state()"""

    # --- auto mode ---

    def test_auto_mode_managed_preferred_when_ready(self, monkeypatch):
        """auto mode selects managed when nous tools enabled and managed ready."""
        monkeypatch.setattr("tools.tool_backend_helpers.managed_nous_tools_enabled", lambda: True)
        result = resolve_modal_backend_state("auto", has_direct=True, managed_ready=True)
        assert result["selected_backend"] == "managed"
        assert result["mode"] == "auto"

    def test_auto_mode_falls_back_to_direct(self, monkeypatch):
        """auto mode falls back to direct when managed not available."""
        monkeypatch.setattr("tools.tool_backend_helpers.managed_nous_tools_enabled", lambda: False)
        result = resolve_modal_backend_state("auto", has_direct=True, managed_ready=True)
        assert result["selected_backend"] == "direct"

    def test_auto_mode_no_backend_available(self, monkeypatch):
        """auto mode selects None when neither managed nor direct available."""
        monkeypatch.setattr("tools.tool_backend_helpers.managed_nous_tools_enabled", lambda: False)
        result = resolve_modal_backend_state("auto", has_direct=False, managed_ready=False)
        assert result["selected_backend"] is None

    # --- direct mode ---

    def test_direct_mode_selects_direct_when_available(self, monkeypatch):
        monkeypatch.setattr("tools.tool_backend_helpers.managed_nous_tools_enabled", lambda: False)
        result = resolve_modal_backend_state("direct", has_direct=True, managed_ready=False)
        assert result["selected_backend"] == "direct"

    def test_direct_mode_returns_none_when_no_credentials(self, monkeypatch):
        monkeypatch.setattr("tools.tool_backend_helpers.managed_nous_tools_enabled", lambda: False)
        result = resolve_modal_backend_state("direct", has_direct=False, managed_ready=False)
        assert result["selected_backend"] is None

    # --- managed mode ---

    def test_managed_mode_blocked_when_nous_tools_disabled(self, monkeypatch):
        monkeypatch.setattr("tools.tool_backend_helpers.managed_nous_tools_enabled", lambda: False)
        result = resolve_modal_backend_state("managed", has_direct=False, managed_ready=True)
        assert result["selected_backend"] is None
        assert result["managed_mode_blocked"] is True

    def test_managed_mode_selected_when_nous_tools_enabled(self, monkeypatch):
        monkeypatch.setattr("tools.tool_backend_helpers.managed_nous_tools_enabled", lambda: True)
        result = resolve_modal_backend_state("managed", has_direct=False, managed_ready=True)
        assert result["selected_backend"] == "managed"
        assert result["managed_mode_blocked"] is False

    def test_managed_mode_returns_none_when_not_ready(self, monkeypatch):
        """managed mode returns None when nous tools enabled but managed not ready."""
        monkeypatch.setattr("tools.tool_backend_helpers.managed_nous_tools_enabled", lambda: True)
        result = resolve_modal_backend_state("managed", has_direct=False, managed_ready=False)
        assert result["selected_backend"] is None

    # --- result fields ---

    def test_result_includes_all_fields(self, monkeypatch):
        monkeypatch.setattr("tools.tool_backend_helpers.managed_nous_tools_enabled", lambda: False)
        result = resolve_modal_backend_state("auto", has_direct=True, managed_ready=False)
        assert "requested_mode" in result
        assert "mode" in result
        assert "has_direct" in result
        assert "managed_ready" in result
        assert "managed_mode_blocked" in result
        assert "selected_backend" in result

    def test_invalid_mode_defaults_to_auto(self, monkeypatch):
        """Unknown mode is coerced to 'auto' with auto semantics."""
        monkeypatch.setattr("tools.tool_backend_helpers.managed_nous_tools_enabled", lambda: False)
        result = resolve_modal_backend_state("unknown_mode", has_direct=True, managed_ready=False)
        assert result["mode"] == "auto"
        assert result["selected_backend"] == "direct"


# ── resolve_openai_audio_api_key ───────────────────────────────────────────────

class TestResolveOpenaiAudioApiKey:
    def test_prefers_voice_tools_key(self, monkeypatch):
        monkeypatch.setenv("VOICE_TOOLS_OPENAI_KEY", "voice-key-123")
        monkeypatch.setenv("OPENAI_API_KEY", "openai-key-456")
        assert resolve_openai_audio_api_key() == "voice-key-123"

    def test_falls_back_to_openai_key(self, monkeypatch):
        monkeypatch.delenv("VOICE_TOOLS_OPENAI_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "openai-key-456")
        assert resolve_openai_audio_api_key() == "openai-key-456"

    def test_returns_empty_when_neither_set(self, monkeypatch):
        monkeypatch.delenv("VOICE_TOOLS_OPENAI_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert resolve_openai_audio_api_key() == ""

    def test_strips_whitespace(self, monkeypatch):
        monkeypatch.setenv("VOICE_TOOLS_OPENAI_KEY", "  key-with-spaces  ")
        assert resolve_openai_audio_api_key() == "key-with-spaces"
