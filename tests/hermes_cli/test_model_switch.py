"""Tests for hermes_cli/model_switch.py.

Covers the switch_model() and switch_to_custom_provider() pipeline logic.
All external dependencies (parse_model_input, detect_provider_for_model,
validate_requested_model, resolve_runtime_provider) are patched at their
source modules since switch_model() imports them lazily inside the function.
"""

import pytest
from unittest.mock import patch, MagicMock

from hermes_cli.model_switch import switch_model, ModelSwitchResult


def _patched_switch(
    raw_input="gpt-5.4",
    current_provider="anthropic",
    current_base_url="",
    current_api_key="",
    parse_result=("openai", "gpt-5.4"),
    detect_result=None,
    runtime=None,
    validation=None,
    runtime_exc=None,
):
    if runtime is None and runtime_exc is None:
        runtime = {"api_key": "test-key", "base_url": "https://api.openai.com/v1"}
    if validation is None:
        validation = {"accepted": True, "persist": True, "recognized": True, "message": None}

    with patch("hermes_cli.models.parse_model_input", return_value=parse_result):
        with patch("hermes_cli.models.detect_provider_for_model", return_value=detect_result):
            if runtime_exc is not None:
                with patch("hermes_cli.runtime_provider.resolve_runtime_provider",
                           side_effect=runtime_exc):
                    with patch("hermes_cli.models.validate_requested_model",
                               return_value=validation):
                        return switch_model(
                            raw_input=raw_input,
                            current_provider=current_provider,
                            current_base_url=current_base_url,
                            current_api_key=current_api_key,
                        )
            else:
                with patch("hermes_cli.runtime_provider.resolve_runtime_provider",
                           return_value=runtime):
                    with patch("hermes_cli.models.validate_requested_model",
                               return_value=validation):
                        return switch_model(
                            raw_input=raw_input,
                            current_provider=current_provider,
                            current_base_url=current_base_url,
                            current_api_key=current_api_key,
                        )


class TestSwitchModel:
    """hermes_cli/model_switch.py — switch_model()"""

    def test_successful_provider_change(self):
        """Switching from anthropic to openai resolves credentials and returns success."""
        result = _patched_switch(
            parse_result=("openai", "gpt-5.4"),
            current_provider="anthropic",
        )
        assert result.success is True
        assert result.new_model == "gpt-5.4"
        assert result.target_provider == "openai"
        assert result.provider_changed is True

    def test_same_provider_no_provider_changed(self):
        """When provider stays the same, provider_changed is False."""
        result = _patched_switch(
            parse_result=("anthropic", "claude-sonnet-4-6"),
            current_provider="anthropic",
        )
        assert result.success is True
        assert result.provider_changed is False

    def test_provider_change_sets_api_key(self):
        """Changing provider resolves and sets the new provider's api_key."""
        result = _patched_switch(
            parse_result=("openai", "gpt-5.4"),
            current_provider="anthropic",
            runtime={"api_key": "openai-resolved-key", "base_url": "https://api.openai.com"},
        )
        assert result.api_key == "openai-resolved-key"

    def test_credential_resolution_failure_returns_error(self):
        """When resolve_runtime_provider raises for non-custom provider, returns failure."""
        result = _patched_switch(
            parse_result=("openai", "gpt-5.4"),
            current_provider="anthropic",
            runtime_exc=ValueError("no openai key"),
        )
        assert result.success is False
        assert result.error_message != ""

    def test_custom_provider_credential_failure_returns_specific_message(self):
        """When custom provider credential resolution fails, returns setup instructions."""
        result = _patched_switch(
            parse_result=("custom", "local-model"),
            current_provider="anthropic",
            runtime_exc=ValueError("no base_url"),
        )
        assert result.success is False
        # Should mention custom endpoint configuration
        assert "config.yaml" in result.error_message or "custom" in result.error_message.lower()

    def test_validation_rejected_returns_failure(self):
        """When validate_requested_model returns accepted=False, returns failure."""
        result = _patched_switch(
            parse_result=("openai", "gpt-invalid"),
            validation={"accepted": False, "persist": False, "message": "Unknown model gpt-invalid"},
        )
        assert result.success is False
        assert "Unknown model" in result.error_message

    def test_validation_warning_preserved(self):
        """Warning from validation is surfaced in warning_message."""
        result = _patched_switch(
            parse_result=("openai", "gpt-5.4"),
            validation={"accepted": True, "persist": True, "message": "Model in beta"},
        )
        assert result.success is True
        assert result.warning_message == "Model in beta"

    def test_auto_detect_provider_used_when_no_explicit_provider(self):
        """When detect_provider_for_model finds a match, it overrides target provider."""
        result = _patched_switch(
            parse_result=("anthropic", "gpt-5.4"),  # parse returns same as current
            detect_result=("openai", "gpt-5.4"),    # auto-detection finds openai
            current_provider="anthropic",
        )
        assert result.target_provider == "openai"
        assert result.provider_changed is True

    def test_is_custom_target_localhost_url(self):
        """localhost base_url sets is_custom_target=True."""
        result = _patched_switch(
            parse_result=("custom", "local-model"),
            current_provider="anthropic",
            runtime={"api_key": "", "base_url": "http://localhost:1234/v1"},
        )
        assert result.success is True
        assert result.is_custom_target is True

    def test_persist_from_validation(self):
        """persist field comes from validation result."""
        result = _patched_switch(
            validation={"accepted": True, "persist": False, "message": None},
        )
        assert result.persist is False

    def test_validation_exception_defaults_to_accepted(self):
        """If validate_requested_model raises, defaults to accepted=True."""
        with patch("hermes_cli.models.parse_model_input",
                   return_value=("openai", "gpt-5.4")):
            with patch("hermes_cli.models.detect_provider_for_model", return_value=None):
                with patch("hermes_cli.runtime_provider.resolve_runtime_provider",
                           return_value={"api_key": "k", "base_url": ""}):
                    with patch("hermes_cli.models.validate_requested_model",
                               side_effect=RuntimeError("network error")):
                        result = switch_model(
                            raw_input="gpt-5.4",
                            current_provider="anthropic",
                        )
        assert result.success is True

    def test_custom_provider_not_auto_detected(self):
        """When current provider is custom, detect_provider_for_model is not called."""
        detect_mock = MagicMock(return_value=("openai", "gpt-5.4"))
        with patch("hermes_cli.models.parse_model_input",
                   return_value=("custom", "local-model")):
            with patch("hermes_cli.models.detect_provider_for_model", detect_mock):
                with patch("hermes_cli.runtime_provider.resolve_runtime_provider",
                           return_value={"api_key": "", "base_url": "http://localhost/v1"}):
                    with patch("hermes_cli.models.validate_requested_model",
                               return_value={"accepted": True, "persist": True}):
                        switch_model(
                            raw_input="local-model",
                            current_provider="custom",
                            current_base_url="http://localhost/v1",
                        )
        detect_mock.assert_not_called()

    def test_localhost_in_current_base_url_is_custom(self):
        """current_base_url with localhost is treated as is_custom, skips auto-detect."""
        detect_mock = MagicMock(return_value=("openai", "gpt-5.4"))
        with patch("hermes_cli.models.parse_model_input",
                   return_value=("openai", "gpt-5.4")):
            with patch("hermes_cli.models.detect_provider_for_model", detect_mock):
                with patch("hermes_cli.runtime_provider.resolve_runtime_provider",
                           return_value={"api_key": "k", "base_url": ""}):
                    with patch("hermes_cli.models.validate_requested_model",
                               return_value={"accepted": True, "persist": True}):
                        switch_model(
                            raw_input="gpt-5.4",
                            current_provider="openai",
                            current_base_url="http://localhost:8080/v1",
                        )
        # is_custom=True because of localhost in base_url — detect skipped
        detect_mock.assert_not_called()
