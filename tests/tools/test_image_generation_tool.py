"""Tests for tools/image_generation_tool.py.

Covers the pure validation logic in _validate_parameters() and
_normalize_fal_queue_url_format(), plus check_fal_api_key().
"""

import os
import pytest
from tools.image_generation_tool import (
    _validate_parameters,
    _normalize_fal_queue_url_format,
    check_fal_api_key,
    check_image_generation_requirements,
    VALID_IMAGE_SIZES,
    VALID_OUTPUT_FORMATS,
    VALID_ACCELERATION_MODES,
)


# ── _normalize_fal_queue_url_format ────────────────────────────────────────────

class TestNormalizeFalQueueUrlFormat:
    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="origin is required"):
            _normalize_fal_queue_url_format("")

    def test_none_raises(self):
        with pytest.raises(ValueError, match="origin is required"):
            _normalize_fal_queue_url_format(None)

    def test_adds_trailing_slash(self):
        result = _normalize_fal_queue_url_format("https://example.com")
        assert result == "https://example.com/"

    def test_strips_double_trailing_slash(self):
        result = _normalize_fal_queue_url_format("https://example.com//")
        assert result.count("/") == 3  # https://example.com/

    def test_preserves_path(self):
        result = _normalize_fal_queue_url_format("https://fal.run/v1")
        assert result == "https://fal.run/v1/"


# ── _validate_parameters ───────────────────────────────────────────────────────

class TestValidateParameters:
    """tools/image_generation_tool.py — _validate_parameters()"""

    def _valid_call(self, **overrides):
        """Call with valid defaults, optionally overriding specific params."""
        defaults = dict(
            image_size="square_hd",
            num_inference_steps=28,
            guidance_scale=4.5,
            num_images=1,
            output_format="jpeg",
            acceleration="none",
        )
        defaults.update(overrides)
        return _validate_parameters(**defaults)

    # --- image_size ---

    def test_valid_preset_string(self):
        result = self._valid_call(image_size="landscape_16_9")
        assert result["image_size"] == "landscape_16_9"

    def test_all_valid_preset_strings(self):
        for size in VALID_IMAGE_SIZES:
            result = self._valid_call(image_size=size)
            assert result["image_size"] == size

    def test_invalid_preset_string_raises(self):
        with pytest.raises(ValueError, match="Invalid image_size"):
            self._valid_call(image_size="ultra_hd_4k")

    def test_custom_dict_valid(self):
        result = self._valid_call(image_size={"width": 512, "height": 768})
        assert result["image_size"] == {"width": 512, "height": 768}

    def test_custom_dict_missing_height_raises(self):
        with pytest.raises(ValueError, match="'width' and 'height' keys"):
            self._valid_call(image_size={"width": 512})

    def test_custom_dict_missing_width_raises(self):
        with pytest.raises(ValueError, match="'width' and 'height' keys"):
            self._valid_call(image_size={"height": 512})

    def test_custom_dict_non_int_raises(self):
        with pytest.raises(ValueError, match="must be integers"):
            self._valid_call(image_size={"width": "512", "height": 768})

    def test_custom_dict_too_small_raises(self):
        with pytest.raises(ValueError, match="at least 64x64"):
            self._valid_call(image_size={"width": 32, "height": 768})

    def test_custom_dict_too_large_raises(self):
        with pytest.raises(ValueError, match="must not exceed 2048x2048"):
            self._valid_call(image_size={"width": 2049, "height": 512})

    def test_image_size_wrong_type_raises(self):
        with pytest.raises(ValueError, match="either a preset string or a dict"):
            self._valid_call(image_size=512)

    # --- num_inference_steps ---

    def test_valid_steps(self):
        result = self._valid_call(num_inference_steps=50)
        assert result["num_inference_steps"] == 50

    def test_steps_minimum(self):
        result = self._valid_call(num_inference_steps=1)
        assert result["num_inference_steps"] == 1

    def test_steps_maximum(self):
        result = self._valid_call(num_inference_steps=100)
        assert result["num_inference_steps"] == 100

    def test_steps_zero_raises(self):
        with pytest.raises(ValueError, match="between 1 and 100"):
            self._valid_call(num_inference_steps=0)

    def test_steps_over_max_raises(self):
        with pytest.raises(ValueError, match="between 1 and 100"):
            self._valid_call(num_inference_steps=101)

    def test_steps_float_raises(self):
        with pytest.raises(ValueError, match="between 1 and 100"):
            self._valid_call(num_inference_steps=28.5)

    # --- guidance_scale ---

    def test_valid_guidance_scale(self):
        result = self._valid_call(guidance_scale=7.5)
        assert result["guidance_scale"] == 7.5

    def test_guidance_scale_too_low_raises(self):
        with pytest.raises(ValueError, match="between 0.1 and 20.0"):
            self._valid_call(guidance_scale=0.0)

    def test_guidance_scale_too_high_raises(self):
        with pytest.raises(ValueError, match="between 0.1 and 20.0"):
            self._valid_call(guidance_scale=20.1)

    def test_guidance_scale_int_accepted(self):
        result = self._valid_call(guidance_scale=4)
        assert result["guidance_scale"] == 4.0  # coerced to float

    # --- num_images ---

    def test_valid_num_images(self):
        result = self._valid_call(num_images=2)
        assert result["num_images"] == 2

    def test_num_images_max_4(self):
        result = self._valid_call(num_images=4)
        assert result["num_images"] == 4

    def test_num_images_zero_raises(self):
        with pytest.raises(ValueError, match="between 1 and 4"):
            self._valid_call(num_images=0)

    def test_num_images_over_4_raises(self):
        with pytest.raises(ValueError, match="between 1 and 4"):
            self._valid_call(num_images=5)

    # --- output_format ---

    def test_valid_output_formats(self):
        for fmt in VALID_OUTPUT_FORMATS:
            result = self._valid_call(output_format=fmt)
            assert result["output_format"] == fmt

    def test_invalid_output_format_raises(self):
        with pytest.raises(ValueError, match="Invalid output_format"):
            self._valid_call(output_format="gif")

    # --- acceleration ---

    def test_valid_acceleration_modes(self):
        for mode in VALID_ACCELERATION_MODES:
            result = self._valid_call(acceleration=mode)
            assert result["acceleration"] == mode

    def test_invalid_acceleration_raises(self):
        with pytest.raises(ValueError, match="Invalid acceleration"):
            self._valid_call(acceleration="turbo")

    # --- complete valid result ---

    def test_complete_valid_result_has_all_keys(self):
        result = self._valid_call()
        assert set(result.keys()) == {
            "image_size", "num_inference_steps", "guidance_scale",
            "num_images", "output_format", "acceleration",
        }


# ── check_fal_api_key ──────────────────────────────────────────────────────────

class TestCheckFalApiKey:
    def test_returns_true_when_key_set(self, monkeypatch):
        monkeypatch.setenv("FAL_KEY", "test-key")
        assert check_fal_api_key() is True

    def test_returns_false_when_key_absent(self, monkeypatch):
        monkeypatch.delenv("FAL_KEY", raising=False)
        monkeypatch.delenv("FAL_KEY_SECRET", raising=False)
        # check_fal_api_key returns True only when a key is present
        # If neither is set, returns False
        result = check_fal_api_key()
        assert result is False
