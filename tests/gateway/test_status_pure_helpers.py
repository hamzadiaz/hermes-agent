"""Tests for pure helper functions in gateway/status.py.

Covers:
- _scope_hash(): determinism, length, collision resistance
- _record_looks_like_gateway(): all valid gateway argv patterns + rejection cases
- _read_json_file(): missing file, empty file, invalid JSON, non-dict, valid dict, OSError
- _get_lock_dir(): env-var override, XDG_STATE_HOME, default fallback
- _utc_now_iso(): ISO format, UTC timezone
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from gateway.status import (
    _scope_hash,
    _record_looks_like_gateway,
    _read_json_file,
    _get_lock_dir,
    _utc_now_iso,
)


# ── _scope_hash ───────────────────────────────────────────────────────────────

class TestScopeHash:
    def test_returns_16_char_hex(self):
        result = _scope_hash("some-identity")
        assert isinstance(result, str)
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        assert _scope_hash("tok-abc123") == _scope_hash("tok-abc123")

    def test_different_inputs_different_outputs(self):
        assert _scope_hash("token-A") != _scope_hash("token-B")

    def test_empty_string_produces_hash(self):
        result = _scope_hash("")
        assert isinstance(result, str)
        assert len(result) == 16

    def test_unicode_input(self):
        result = _scope_hash("héllo-wörld")
        assert isinstance(result, str)
        assert len(result) == 16


# ── _record_looks_like_gateway ────────────────────────────────────────────────

class TestRecordLooksLikeGateway:
    def _make_record(self, kind="hermes-gateway", argv=None):
        return {"kind": kind, "argv": argv or ["python", "-m", "hermes_cli.main", "gateway"]}

    # Valid patterns
    def test_module_style_accepted(self):
        record = self._make_record(argv=["python", "-m", "hermes_cli.main", "gateway"])
        assert _record_looks_like_gateway(record) is True

    def test_script_style_accepted(self):
        record = self._make_record(argv=["/venv/bin/python", "hermes_cli/main.py", "gateway"])
        assert _record_looks_like_gateway(record) is True

    def test_hermes_gateway_shorthand_accepted(self):
        record = self._make_record(argv=["hermes", "gateway", "run"])
        assert _record_looks_like_gateway(record) is True

    def test_gateway_run_py_accepted(self):
        record = self._make_record(argv=["python", "gateway/run.py", "--replace"])
        assert _record_looks_like_gateway(record) is True

    # Kind validation
    def test_wrong_kind_rejected(self):
        record = {"kind": "not-a-gateway", "argv": ["python", "-m", "hermes_cli.main", "gateway"]}
        assert _record_looks_like_gateway(record) is False

    def test_missing_kind_rejected(self):
        record = {"argv": ["python", "-m", "hermes_cli.main", "gateway"]}
        assert _record_looks_like_gateway(record) is False

    # argv validation
    def test_missing_argv_rejected(self):
        record = {"kind": "hermes-gateway"}
        assert _record_looks_like_gateway(record) is False

    def test_empty_argv_rejected(self):
        record = {"kind": "hermes-gateway", "argv": []}
        assert _record_looks_like_gateway(record) is False

    def test_non_list_argv_rejected(self):
        record = {"kind": "hermes-gateway", "argv": "python -m hermes_cli.main gateway"}
        assert _record_looks_like_gateway(record) is False

    def test_argv_with_no_matching_pattern_rejected(self):
        record = {"kind": "hermes-gateway", "argv": ["python", "some_other_script.py"]}
        assert _record_looks_like_gateway(record) is False

    def test_numeric_argv_parts_coerced_to_str(self):
        """argv items that aren't strings should be joined as strings without crashing."""
        record = {"kind": "hermes-gateway", "argv": [123, "hermes_cli.main", "gateway"]}
        # "123 hermes_cli.main gateway" — contains "hermes_cli.main gateway" → True
        assert _record_looks_like_gateway(record) is True

    def test_full_path_module_style_accepted(self):
        """Absolute path to hermes_cli/main.py plus 'gateway' token is accepted."""
        record = self._make_record(argv=["/usr/local/bin/python3", "/opt/hermes/hermes_cli/main.py", "gateway"])
        assert _record_looks_like_gateway(record) is True


# ── _read_json_file ───────────────────────────────────────────────────────────

class TestReadJsonFile:
    def test_missing_file_returns_none(self, tmp_path):
        assert _read_json_file(tmp_path / "nonexistent.json") is None

    def test_empty_file_returns_none(self, tmp_path):
        p = tmp_path / "empty.json"
        p.write_text("")
        assert _read_json_file(p) is None

    def test_whitespace_only_returns_none(self, tmp_path):
        p = tmp_path / "ws.json"
        p.write_text("   \n  ")
        assert _read_json_file(p) is None

    def test_invalid_json_returns_none(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not valid json {{{")
        assert _read_json_file(p) is None

    def test_valid_dict_returned(self, tmp_path):
        p = tmp_path / "ok.json"
        p.write_text(json.dumps({"key": "value", "num": 42}))
        result = _read_json_file(p)
        assert result == {"key": "value", "num": 42}

    def test_json_list_returns_none(self, tmp_path):
        """Non-dict JSON (a list) should return None."""
        p = tmp_path / "list.json"
        p.write_text(json.dumps([1, 2, 3]))
        assert _read_json_file(p) is None

    def test_json_number_returns_none(self, tmp_path):
        p = tmp_path / "num.json"
        p.write_text("12345")
        assert _read_json_file(p) is None

    def test_os_error_returns_none(self, tmp_path, monkeypatch):
        """OSError during read_text returns None."""
        p = tmp_path / "file.json"
        p.write_text("{}")
        monkeypatch.setattr(Path, "read_text", lambda *a, **kw: (_ for _ in ()).throw(OSError("disk error")))
        assert _read_json_file(p) is None


# ── _get_lock_dir ─────────────────────────────────────────────────────────────

class TestGetLockDir:
    def test_env_override_used(self, monkeypatch, tmp_path):
        override = str(tmp_path / "custom-locks")
        monkeypatch.setenv("HERMES_GATEWAY_LOCK_DIR", override)
        assert _get_lock_dir() == Path(override)

    def test_xdg_state_home_used(self, monkeypatch, tmp_path):
        monkeypatch.delenv("HERMES_GATEWAY_LOCK_DIR", raising=False)
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        result = _get_lock_dir()
        assert result == tmp_path / "state" / "hermes" / "gateway-locks"

    def test_default_fallback_under_home(self, monkeypatch):
        monkeypatch.delenv("HERMES_GATEWAY_LOCK_DIR", raising=False)
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        result = _get_lock_dir()
        # Should be ~/.local/state/hermes/gateway-locks
        assert result.parts[-3:] == ("hermes", "gateway-locks") or \
               "hermes" in result.parts and "gateway-locks" in result.parts


# ── _utc_now_iso ──────────────────────────────────────────────────────────────

class TestUtcNowIso:
    def test_returns_string(self):
        assert isinstance(_utc_now_iso(), str)

    def test_parseable_as_iso(self):
        result = _utc_now_iso()
        dt = datetime.fromisoformat(result)
        assert dt is not None

    def test_timezone_is_utc(self):
        result = _utc_now_iso()
        dt = datetime.fromisoformat(result)
        # Should have UTC timezone info
        assert dt.tzinfo is not None
        assert dt.utcoffset().total_seconds() == 0

    def test_close_to_now(self):
        before = datetime.now(timezone.utc)
        result = _utc_now_iso()
        after = datetime.now(timezone.utc)
        dt = datetime.fromisoformat(result)
        assert before <= dt <= after
