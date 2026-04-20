"""Tests for pure helper functions in gateway/session.py.

Covers:
- _hash_id(): deterministic 12-char hex hash of a string identifier
- _hash_sender_id(): hash a sender ID to user_<12hex> format
- _hash_chat_id(): hash a chat ID preserving platform prefix
- _looks_like_phone(): detect E.164 / phone-number-like strings
"""

import pytest

from gateway.session import (
    _hash_chat_id,
    _hash_id,
    _hash_sender_id,
    _looks_like_phone,
)


# ── _hash_id ──────────────────────────────────────────────────────────────────

class TestHashId:
    def test_returns_12_hex_chars(self):
        result = _hash_id("test")
        assert len(result) == 12
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        assert _hash_id("same") == _hash_id("same")

    def test_different_inputs_different_outputs(self):
        assert _hash_id("alice") != _hash_id("bob")

    def test_empty_string_hashed(self):
        result = _hash_id("")
        assert len(result) == 12

    def test_known_hash(self):
        # SHA-256 of "test" truncated to 12 chars
        import hashlib
        expected = hashlib.sha256(b"test").hexdigest()[:12]
        assert _hash_id("test") == expected


# ── _hash_sender_id ───────────────────────────────────────────────────────────

class TestHashSenderId:
    def test_returns_user_prefix(self):
        result = _hash_sender_id("alice")
        assert result.startswith("user_")

    def test_suffix_is_12_hex_chars(self):
        result = _hash_sender_id("alice")
        suffix = result[len("user_"):]
        assert len(suffix) == 12
        assert all(c in "0123456789abcdef" for c in suffix)

    def test_deterministic(self):
        assert _hash_sender_id("alice") == _hash_sender_id("alice")

    def test_different_users_different_hashes(self):
        assert _hash_sender_id("alice") != _hash_sender_id("bob")

    def test_total_length_is_17(self):
        # "user_" (5) + 12 hex chars = 17
        assert len(_hash_sender_id("anyone")) == 17


# ── _hash_chat_id ─────────────────────────────────────────────────────────────

class TestHashChatId:
    def test_plain_id_returns_hash(self):
        result = _hash_chat_id("12345")
        assert len(result) == 12

    def test_platform_prefix_preserved(self):
        result = _hash_chat_id("telegram:12345")
        assert result.startswith("telegram:")

    def test_platform_prefix_numeric_hashed(self):
        result = _hash_chat_id("telegram:12345")
        suffix = result[len("telegram:"):]
        assert len(suffix) == 12

    def test_discord_prefix_preserved(self):
        result = _hash_chat_id("discord:99999")
        assert result.startswith("discord:")

    def test_same_platform_same_numeric_id_deterministic(self):
        assert _hash_chat_id("telegram:12345") == _hash_chat_id("telegram:12345")

    def test_different_ids_different_hashes(self):
        assert _hash_chat_id("telegram:11111") != _hash_chat_id("telegram:22222")

    def test_colon_at_start_not_treated_as_prefix(self):
        # colon > 0 required for prefix extraction
        result = _hash_chat_id(":12345")
        # colon at position 0 → not a valid prefix → entire value hashed
        assert len(result) == 12


# ── _looks_like_phone ─────────────────────────────────────────────────────────

class TestLooksLikePhone:
    def test_e164_format_recognized(self):
        assert _looks_like_phone("+15551234567") is True

    def test_e164_with_spaces_recognized(self):
        assert _looks_like_phone("+1 555 123 4567") is True

    def test_plain_digits_recognized(self):
        assert _looks_like_phone("+447700900000") is True

    def test_username_not_phone(self):
        assert _looks_like_phone("alice") is False

    def test_email_not_phone(self):
        assert _looks_like_phone("user@example.com") is False

    def test_empty_string_not_phone(self):
        assert _looks_like_phone("") is False

    def test_short_number_not_phone(self):
        # Too short for a real phone number
        assert _looks_like_phone("+1") is False

    def test_leading_whitespace_stripped_before_check(self):
        # _looks_like_phone strips whitespace
        assert _looks_like_phone("  +15551234567  ") is True
