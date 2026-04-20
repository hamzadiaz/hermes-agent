"""Tests for pure helper functions in gateway/platforms/email.py.

Covers:
- _is_automated_sender(): detect noreply/automated email sources
"""

import pytest

from gateway.platforms.email import _is_automated_sender


# ── _is_automated_sender ──────────────────────────────────────────────────────

class TestIsAutomatedSender:
    def test_normal_user_not_automated(self):
        assert _is_automated_sender("user@example.com", {}) is False

    def test_noreply_address_detected(self):
        assert _is_automated_sender("noreply@example.com", {}) is True

    def test_no_dash_reply_detected(self):
        assert _is_automated_sender("no-reply@service.com", {}) is True

    def test_no_underscore_reply_detected(self):
        assert _is_automated_sender("no_reply@service.com", {}) is True

    def test_donotreply_detected(self):
        assert _is_automated_sender("donotreply@company.com", {}) is True

    def test_do_dash_not_dash_reply_detected(self):
        assert _is_automated_sender("do-not-reply@company.com", {}) is True

    def test_mailer_daemon_detected(self):
        assert _is_automated_sender("mailer-daemon@server.com", {}) is True

    def test_postmaster_detected(self):
        assert _is_automated_sender("postmaster@example.com", {}) is True

    def test_bounce_address_detected(self):
        assert _is_automated_sender("bounce+abc@sendgrid.com", {}) is True

    def test_notifications_address_detected(self):
        assert _is_automated_sender("notifications@github.com", {}) is True

    def test_automated_at_detected(self):
        assert _is_automated_sender("automated@system.com", {}) is True

    def test_case_insensitive_match(self):
        # address is lowercased before matching
        assert _is_automated_sender("NoReply@Example.COM", {}) is True

    def test_precedence_bulk_detected(self):
        assert _is_automated_sender("news@example.com", {"Precedence": "bulk"}) is True

    def test_precedence_list_detected(self):
        assert _is_automated_sender("news@example.com", {"Precedence": "list"}) is True

    def test_precedence_junk_detected(self):
        assert _is_automated_sender("news@example.com", {"Precedence": "junk"}) is True

    def test_precedence_normal_not_automated(self):
        # "normal" or other values are not in the list
        assert _is_automated_sender("news@example.com", {"Precedence": "normal"}) is False

    def test_auto_submitted_auto_generated_detected(self):
        assert _is_automated_sender("user@example.com", {"Auto-Submitted": "auto-generated"}) is True

    def test_auto_submitted_no_not_automated(self):
        # "no" means explicitly NOT auto-submitted
        assert _is_automated_sender("user@example.com", {"Auto-Submitted": "no"}) is False

    def test_x_auto_response_suppress_detected(self):
        assert _is_automated_sender("user@example.com", {"X-Auto-Response-Suppress": "All"}) is True

    def test_list_unsubscribe_detected(self):
        assert _is_automated_sender("news@example.com", {"List-Unsubscribe": "<mailto:unsub@x.com>"}) is True

    def test_empty_headers_does_not_trigger(self):
        assert _is_automated_sender("real.user@example.com", {"Auto-Submitted": ""}) is False
