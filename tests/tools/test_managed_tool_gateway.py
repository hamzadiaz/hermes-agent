import os
import json
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[2] / "tools" / "managed_tool_gateway.py"
MODULE_SPEC = spec_from_file_location("managed_tool_gateway_test_module", MODULE_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
managed_tool_gateway = module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = managed_tool_gateway
MODULE_SPEC.loader.exec_module(managed_tool_gateway)
resolve_managed_tool_gateway = managed_tool_gateway.resolve_managed_tool_gateway


def test_resolve_managed_tool_gateway_derives_vendor_origin_from_shared_domain():
    with patch.dict(
        os.environ,
        {
            "HERMES_ENABLE_NOUS_MANAGED_TOOLS": "1",
            "TOOL_GATEWAY_DOMAIN": "nousresearch.com",
        },
        clear=False,
    ):
        result = resolve_managed_tool_gateway(
            "firecrawl",
            token_reader=lambda: "nous-token",
        )

    assert result is not None
    assert result.gateway_origin == "https://firecrawl-gateway.nousresearch.com"
    assert result.nous_user_token == "nous-token"
    assert result.managed_mode is True


def test_resolve_managed_tool_gateway_uses_vendor_specific_override():
    with patch.dict(
        os.environ,
        {
            "HERMES_ENABLE_NOUS_MANAGED_TOOLS": "1",
            "BROWSERBASE_GATEWAY_URL": "http://browserbase-gateway.localhost:3009/",
        },
        clear=False,
    ):
        result = resolve_managed_tool_gateway(
            "browserbase",
            token_reader=lambda: "nous-token",
        )

    assert result is not None
    assert result.gateway_origin == "http://browserbase-gateway.localhost:3009"


def test_resolve_managed_tool_gateway_is_inactive_without_nous_token():
    with patch.dict(
        os.environ,
        {
            "HERMES_ENABLE_NOUS_MANAGED_TOOLS": "1",
            "TOOL_GATEWAY_DOMAIN": "nousresearch.com",
        },
        clear=False,
    ):
        result = resolve_managed_tool_gateway(
            "firecrawl",
            token_reader=lambda: None,
        )

    assert result is None


def test_resolve_managed_tool_gateway_is_disabled_without_feature_flag():
    with patch.dict(os.environ, {"TOOL_GATEWAY_DOMAIN": "nousresearch.com"}, clear=False):
        result = resolve_managed_tool_gateway(
            "firecrawl",
            token_reader=lambda: "nous-token",
        )

    assert result is None


def test_read_nous_access_token_refreshes_expiring_cached_token(tmp_path, monkeypatch):
    monkeypatch.delenv("TOOL_GATEWAY_USER_TOKEN", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
    (tmp_path / "auth.json").write_text(json.dumps({
        "providers": {
            "nous": {
                "access_token": "stale-token",
                "refresh_token": "refresh-token",
                "expires_at": expires_at,
            }
        }
    }))
    monkeypatch.setattr(
        "hermes_cli.auth.resolve_nous_access_token",
        lambda refresh_skew_seconds=120: "fresh-token",
    )

    assert managed_tool_gateway.read_nous_access_token() == "fresh-token"


# ── _parse_timestamp pure helper ──────────────────────────────────────────────

_parse_timestamp = managed_tool_gateway._parse_timestamp
_access_token_is_expiring = managed_tool_gateway._access_token_is_expiring


class TestParseTimestamp:
    def test_none_returns_none(self):
        assert _parse_timestamp(None) is None

    def test_non_string_returns_none(self):
        assert _parse_timestamp(12345) is None

    def test_empty_string_returns_none(self):
        assert _parse_timestamp("") is None

    def test_whitespace_only_returns_none(self):
        assert _parse_timestamp("   ") is None

    def test_invalid_format_returns_none(self):
        assert _parse_timestamp("not-a-date") is None

    def test_z_suffix_parsed(self):
        result = _parse_timestamp("2026-04-20T12:00:00Z")
        assert result is not None
        assert result.tzinfo == timezone.utc

    def test_utc_offset_parsed(self):
        result = _parse_timestamp("2026-04-20T12:00:00+00:00")
        assert result is not None
        assert result.tzinfo is not None

    def test_z_and_offset_equivalent(self):
        r1 = _parse_timestamp("2026-04-20T12:00:00Z")
        r2 = _parse_timestamp("2026-04-20T12:00:00+00:00")
        assert r1 is not None and r2 is not None
        assert abs((r1 - r2).total_seconds()) < 0.001

    def test_naive_datetime_treated_as_utc(self):
        result = _parse_timestamp("2026-04-20T12:00:00")
        assert result is not None
        assert result.tzinfo == timezone.utc

    def test_result_normalized_to_utc(self):
        result = _parse_timestamp("2026-04-20T14:00:00+02:00")
        assert result is not None
        assert result.hour == 12  # 14:00+02:00 → 12:00 UTC


class TestAccessTokenIsExpiring:
    def test_none_timestamp_considered_expiring(self):
        assert _access_token_is_expiring(None, skew_seconds=0) is True

    def test_invalid_timestamp_considered_expiring(self):
        assert _access_token_is_expiring("bad-date", skew_seconds=0) is True

    def test_past_timestamp_is_expiring(self):
        past = "2020-01-01T00:00:00Z"
        assert _access_token_is_expiring(past, skew_seconds=0) is True

    def test_far_future_not_expiring(self):
        future = "2099-01-01T00:00:00Z"
        assert _access_token_is_expiring(future, skew_seconds=0) is False

    def test_skew_causes_near_future_to_appear_expiring(self):
        near_future = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
        assert _access_token_is_expiring(near_future, skew_seconds=60) is True

    def test_negative_skew_clamped_to_zero(self):
        """Negative skew is treated as 0 (max(0, skew))."""
        future = "2099-01-01T00:00:00Z"
        assert _access_token_is_expiring(future, skew_seconds=-100) is False
