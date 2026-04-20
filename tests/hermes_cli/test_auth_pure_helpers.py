"""Tests for pure helper functions in hermes_cli/auth.py.

Covers:
- has_usable_secret(): placeholder detection, length guard
- _parse_iso_timestamp(): ISO 8601 parsing including Z suffix
- _is_expiring(): expiry window check
- _coerce_ttl_seconds(): TTL coercion with error handling
- _optional_base_url(): URL normalization
- _decode_jwt_claims(): JWT claim extraction
- _resolve_kimi_base_url(): Kimi URL routing by key prefix
- format_auth_error(): auth error → user-facing message
- _token_fingerprint(): short hash without leaking token
"""

import time
import pytest

from hermes_cli.auth import (
    has_usable_secret,
    _parse_iso_timestamp,
    _is_expiring,
    _coerce_ttl_seconds,
    _optional_base_url,
    _decode_jwt_claims,
    _resolve_kimi_base_url,
    format_auth_error,
    _token_fingerprint,
    AuthError,
    KIMI_CODE_BASE_URL,
)


# ── has_usable_secret ─────────────────────────────────────────────────────────

class TestHasUsableSecret:
    def test_valid_key_returns_true(self):
        assert has_usable_secret("sk-abc123") is True

    def test_non_string_returns_false(self):
        assert has_usable_secret(None) is False
        assert has_usable_secret(123) is False
        assert has_usable_secret([]) is False

    def test_empty_string_returns_false(self):
        assert has_usable_secret("") is False

    def test_too_short_returns_false(self):
        assert has_usable_secret("ab") is False  # min_length=4

    def test_exactly_min_length_returns_true(self):
        assert has_usable_secret("abcd") is True

    def test_custom_min_length(self):
        assert has_usable_secret("ab", min_length=2) is True
        assert has_usable_secret("a", min_length=2) is False

    def test_placeholder_changeme_returns_false(self):
        assert has_usable_secret("changeme") is False

    def test_placeholder_your_api_key_returns_false(self):
        assert has_usable_secret("your_api_key") is False

    def test_placeholder_case_insensitive(self):
        assert has_usable_secret("PLACEHOLDER") is False
        assert has_usable_secret("CHANGEME") is False

    def test_placeholder_null_returns_false(self):
        assert has_usable_secret("null") is False

    def test_whitespace_stripped_before_check(self):
        """Leading/trailing whitespace is stripped before length/placeholder check."""
        assert has_usable_secret("  changeme  ") is False

    def test_asterisks_are_placeholder(self):
        assert has_usable_secret("***") is False
        assert has_usable_secret("**") is False


# ── _parse_iso_timestamp ──────────────────────────────────────────────────────

class TestParseIsoTimestamp:
    def test_none_returns_none(self):
        assert _parse_iso_timestamp(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_iso_timestamp("") is None

    def test_whitespace_returns_none(self):
        assert _parse_iso_timestamp("   ") is None

    def test_invalid_format_returns_none(self):
        assert _parse_iso_timestamp("not a date") is None

    def test_z_suffix_parsed(self):
        result = _parse_iso_timestamp("2026-04-20T12:00:00Z")
        assert isinstance(result, float)
        assert result > 0

    def test_offset_parsed(self):
        result = _parse_iso_timestamp("2026-04-20T12:00:00+00:00")
        assert isinstance(result, float)
        assert result > 0

    def test_z_and_offset_equivalent(self):
        """2026-04-20T12:00:00Z and 2026-04-20T12:00:00+00:00 should parse to same epoch."""
        r1 = _parse_iso_timestamp("2026-04-20T12:00:00Z")
        r2 = _parse_iso_timestamp("2026-04-20T12:00:00+00:00")
        assert abs(r1 - r2) < 0.001

    def test_naive_datetime_treated_as_utc(self):
        """Naive datetime (no timezone) should be treated as UTC."""
        result = _parse_iso_timestamp("2026-04-20T12:00:00")
        assert isinstance(result, float)

    def test_non_string_returns_none(self):
        assert _parse_iso_timestamp(12345) is None


# ── _is_expiring ──────────────────────────────────────────────────────────────

class TestIsExpiring:
    def test_none_timestamp_considered_expiring(self):
        assert _is_expiring(None, skew_seconds=0) is True

    def test_invalid_timestamp_considered_expiring(self):
        assert _is_expiring("not-a-date", skew_seconds=0) is True

    def test_past_timestamp_is_expiring(self):
        past = "2020-01-01T00:00:00Z"
        assert _is_expiring(past, skew_seconds=0) is True

    def test_future_timestamp_not_expiring(self):
        future = "2099-01-01T00:00:00Z"
        assert _is_expiring(future, skew_seconds=0) is False

    def test_skew_causes_not_yet_expired_to_appear_expiring(self):
        """If token expires in 10 seconds and skew is 60, it should appear expiring."""
        import datetime as dt
        near_future_epoch = time.time() + 10  # expires in 10s
        near_future_iso = dt.datetime.fromtimestamp(
            near_future_epoch, tz=dt.timezone.utc
        ).isoformat()
        assert _is_expiring(near_future_iso, skew_seconds=60) is True


# ── _coerce_ttl_seconds ───────────────────────────────────────────────────────

class TestCoerceTtlSeconds:
    def test_integer_passed_through(self):
        assert _coerce_ttl_seconds(3600) == 3600

    def test_string_integer_coerced(self):
        assert _coerce_ttl_seconds("1800") == 1800

    def test_float_truncated(self):
        assert _coerce_ttl_seconds(99.9) == 99

    def test_none_returns_zero(self):
        assert _coerce_ttl_seconds(None) == 0

    def test_invalid_string_returns_zero(self):
        assert _coerce_ttl_seconds("not a number") == 0

    def test_negative_clamped_to_zero(self):
        assert _coerce_ttl_seconds(-100) == 0


# ── _optional_base_url ────────────────────────────────────────────────────────

class TestOptionalBaseUrl:
    def test_none_returns_none(self):
        assert _optional_base_url(None) is None

    def test_non_string_returns_none(self):
        assert _optional_base_url(123) is None

    def test_empty_string_returns_none(self):
        assert _optional_base_url("") is None

    def test_whitespace_only_returns_none(self):
        assert _optional_base_url("   ") is None

    def test_trailing_slash_stripped(self):
        assert _optional_base_url("https://api.example.com/") == "https://api.example.com"

    def test_multiple_trailing_slashes_stripped(self):
        result = _optional_base_url("https://api.example.com///")
        assert result == "https://api.example.com"

    def test_valid_url_returned(self):
        assert _optional_base_url("https://api.openai.com/v1") == "https://api.openai.com/v1"


# ── _decode_jwt_claims ────────────────────────────────────────────────────────

class TestDecodeJwtClaims:
    def test_non_string_returns_empty(self):
        assert _decode_jwt_claims(None) == {}
        assert _decode_jwt_claims(123) == {}

    def test_non_jwt_format_returns_empty(self):
        assert _decode_jwt_claims("not-a-jwt") == {}

    def test_one_dot_returns_empty(self):
        assert _decode_jwt_claims("header.payload") == {}

    def test_invalid_base64_returns_empty(self):
        assert _decode_jwt_claims("header.!!!invalid_base64!!!.sig") == {}

    def test_valid_jwt_returns_claims(self):
        import base64
        import json as _json
        payload = {"sub": "user123", "exp": 9999999999}
        b64 = base64.urlsafe_b64encode(
            _json.dumps(payload).encode()
        ).rstrip(b"=").decode()
        token = f"header.{b64}.sig"
        result = _decode_jwt_claims(token)
        assert result["sub"] == "user123"
        assert result["exp"] == 9999999999


# ── _resolve_kimi_base_url ────────────────────────────────────────────────────

class TestResolveKimiBaseUrl:
    def test_env_override_wins(self):
        result = _resolve_kimi_base_url(
            api_key="sk-kimi-xxx",
            default_url="https://api.moonshot.cn/v1",
            env_override="https://my-proxy.example.com/v1",
        )
        assert result == "https://my-proxy.example.com/v1"

    def test_sk_kimi_prefix_routes_to_coding(self):
        result = _resolve_kimi_base_url(
            api_key="sk-kimi-abcdef",
            default_url="https://api.moonshot.cn/v1",
            env_override="",
        )
        assert result == KIMI_CODE_BASE_URL

    def test_regular_key_uses_default(self):
        result = _resolve_kimi_base_url(
            api_key="sk-other-provider",
            default_url="https://api.moonshot.cn/v1",
            env_override="",
        )
        assert result == "https://api.moonshot.cn/v1"


# ── format_auth_error ─────────────────────────────────────────────────────────

class TestFormatAuthError:
    def test_non_auth_error_returns_str(self):
        exc = ValueError("something broke")
        assert format_auth_error(exc) == "something broke"

    def test_relogin_required_includes_hermes_model(self):
        exc = AuthError("token expired", relogin_required=True)
        result = format_auth_error(exc)
        assert "hermes model" in result.lower() or "re-authenticate" in result.lower()

    def test_subscription_required_code(self):
        exc = AuthError("no subscription", code="subscription_required")
        result = format_auth_error(exc)
        assert "subscription" in result.lower()

    def test_insufficient_credits_code(self):
        exc = AuthError("out of credits", code="insufficient_credits")
        result = format_auth_error(exc)
        assert "credits" in result.lower()

    def test_temporarily_unavailable_code(self):
        exc = AuthError("down", code="temporarily_unavailable")
        result = format_auth_error(exc)
        assert "retry" in result.lower()

    def test_unknown_code_returns_str(self):
        exc = AuthError("weird error", code="unknown_code")
        result = format_auth_error(exc)
        assert "weird error" in result


# ── _token_fingerprint ────────────────────────────────────────────────────────

class TestTokenFingerprint:
    def test_non_string_returns_none(self):
        assert _token_fingerprint(None) is None
        assert _token_fingerprint(123) is None

    def test_empty_string_returns_none(self):
        assert _token_fingerprint("") is None

    def test_whitespace_only_returns_none(self):
        assert _token_fingerprint("   ") is None

    def test_valid_token_returns_12_char_hex(self):
        result = _token_fingerprint("sk-abc123")
        assert isinstance(result, str)
        assert len(result) == 12
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        """Same token always produces same fingerprint."""
        assert _token_fingerprint("sk-test") == _token_fingerprint("sk-test")

    def test_different_tokens_different_fingerprints(self):
        fp1 = _token_fingerprint("sk-abc")
        fp2 = _token_fingerprint("sk-xyz")
        assert fp1 != fp2
