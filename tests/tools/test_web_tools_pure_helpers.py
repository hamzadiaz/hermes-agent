"""Tests for pure helper functions in tools/web_tools.py.

Covers:
- _to_plain_object(): SDK object → plain Python data structure
- _normalize_result_list(): mixed SDK/list payloads → list of dicts
- _extract_web_search_results(): Firecrawl search response shape normalisation
- _extract_scrape_payload(): Firecrawl scrape response shape normalisation
"""

import pytest
from unittest.mock import MagicMock

from tools.web_tools import (
    _to_plain_object,
    _normalize_result_list,
    _extract_web_search_results,
    _extract_scrape_payload,
)


# ── _to_plain_object ──────────────────────────────────────────────────────────

class TestToPlainObject:
    def test_none_returns_none(self):
        assert _to_plain_object(None) is None

    def test_dict_returned_as_is(self):
        d = {"a": 1}
        assert _to_plain_object(d) is d

    def test_list_returned_as_is(self):
        lst = [1, 2, 3]
        assert _to_plain_object(lst) is lst

    def test_string_returned_as_is(self):
        assert _to_plain_object("hello") == "hello"

    def test_int_returned_as_is(self):
        assert _to_plain_object(42) == 42

    def test_float_returned_as_is(self):
        assert _to_plain_object(3.14) == 3.14

    def test_bool_returned_as_is(self):
        assert _to_plain_object(True) is True

    def test_model_dump_called_when_available(self):
        obj = MagicMock(spec=["model_dump"])
        obj.model_dump.return_value = {"key": "value"}
        result = _to_plain_object(obj)
        assert result == {"key": "value"}
        obj.model_dump.assert_called_once()

    def test_model_dump_exception_falls_through_to_dict(self):
        """If model_dump() raises, fall back to __dict__."""
        obj = MagicMock()
        obj.model_dump.side_effect = RuntimeError("bad")
        obj.__dict__ = {"pub": 1, "_priv": 2}
        result = _to_plain_object(obj)
        assert result == {"pub": 1}

    def test_dict_fallback_used_when_no_model_dump(self):
        class Simple:
            def __init__(self):
                self.x = 10
                self._hidden = 99

        obj = Simple()
        result = _to_plain_object(obj)
        assert result == {"x": 10}

    def test_private_attrs_excluded_from_dict_fallback(self):
        class WithPrivate:
            def __init__(self):
                self.pub = "yes"
                self._priv = "no"
                self.__very_priv = "also no"

        result = _to_plain_object(WithPrivate())
        assert "pub" in result
        assert "_priv" not in result

    def test_unknown_object_returned_as_is(self):
        """Object with no model_dump and __dict__ raising an exception → returned as-is."""
        class Opaque:
            @property
            def __dict__(self):
                raise AttributeError("no dict")

        obj = Opaque()
        result = _to_plain_object(obj)
        assert result is obj


# ── _normalize_result_list ────────────────────────────────────────────────────

class TestNormalizeResultList:
    def test_non_list_returns_empty(self):
        assert _normalize_result_list(None) == []
        assert _normalize_result_list("string") == []
        assert _normalize_result_list(42) == []
        assert _normalize_result_list({"a": 1}) == []

    def test_empty_list_returns_empty(self):
        assert _normalize_result_list([]) == []

    def test_list_of_dicts_preserved(self):
        items = [{"url": "a"}, {"url": "b"}]
        assert _normalize_result_list(items) == items

    def test_non_dict_items_excluded(self):
        items = [{"url": "a"}, "string", 42, None]
        assert _normalize_result_list(items) == [{"url": "a"}]

    def test_sdk_objects_converted_via_to_plain_object(self):
        obj = MagicMock(spec=["model_dump"])
        obj.model_dump.return_value = {"url": "sdk-url"}
        result = _normalize_result_list([obj])
        assert result == [{"url": "sdk-url"}]

    def test_sdk_objects_that_dont_produce_dict_excluded(self):
        """model_dump returns a non-dict → excluded."""
        obj = MagicMock(spec=["model_dump"])
        obj.model_dump.return_value = ["not", "a", "dict"]
        result = _normalize_result_list([obj])
        assert result == []

    def test_mixed_valid_and_invalid_items(self):
        obj = MagicMock(spec=["model_dump"])
        obj.model_dump.return_value = {"url": "x"}
        result = _normalize_result_list([{"url": "a"}, obj, "skip", {"url": "b"}])
        assert result == [{"url": "a"}, {"url": "x"}, {"url": "b"}]


# ── _extract_web_search_results ───────────────────────────────────────────────

class TestExtractWebSearchResults:
    # --- data key is a list (Firecrawl direct shape) ---

    def test_data_list_returned_directly(self):
        response = {"data": [{"url": "a"}, {"url": "b"}]}
        assert _extract_web_search_results(response) == [{"url": "a"}, {"url": "b"}]

    def test_data_empty_list(self):
        assert _extract_web_search_results({"data": []}) == []

    # --- data key is a dict with .web sub-key ---

    def test_data_dict_with_web_key(self):
        response = {"data": {"web": [{"url": "w"}]}}
        assert _extract_web_search_results(response) == [{"url": "w"}]

    def test_data_dict_with_results_key_when_no_web(self):
        response = {"data": {"results": [{"url": "r"}]}}
        assert _extract_web_search_results(response) == [{"url": "r"}]

    def test_data_dict_web_preferred_over_results(self):
        response = {"data": {"web": [{"url": "w"}], "results": [{"url": "r"}]}}
        assert _extract_web_search_results(response) == [{"url": "w"}]

    # --- top-level keys ---

    def test_top_level_web_key(self):
        response = {"web": [{"url": "top"}]}
        assert _extract_web_search_results(response) == [{"url": "top"}]

    def test_top_level_results_key(self):
        response = {"results": [{"url": "top-r"}]}
        assert _extract_web_search_results(response) == [{"url": "top-r"}]

    def test_top_level_web_preferred_over_results(self):
        response = {"web": [{"url": "w"}], "results": [{"url": "r"}]}
        assert _extract_web_search_results(response) == [{"url": "w"}]

    # --- SDK object with .web attribute ---

    def test_sdk_object_with_web_attribute(self):
        obj = MagicMock(spec=["web"])
        obj.web = [{"url": "sdk-web"}]
        # model_dump/dict conversion won't produce a dict here since spec excludes them
        # Use a real object so _to_plain_object returns the object itself
        class SDKResponse:
            web = [{"url": "sdk-web"}]

        result = _extract_web_search_results(SDKResponse())
        assert result == [{"url": "sdk-web"}]

    # --- edge cases ---

    def test_none_response_returns_empty(self):
        assert _extract_web_search_results(None) == []

    def test_empty_dict_returns_empty(self):
        assert _extract_web_search_results({}) == []

    def test_non_list_data_value_falls_through(self):
        """data=str → not a list/dict → skip to top-level keys → empty."""
        response = {"data": "unexpected"}
        assert _extract_web_search_results(response) == []

    def test_data_dict_with_no_known_keys_falls_through(self):
        response = {"data": {"other": [{"url": "x"}]}}
        assert _extract_web_search_results(response) == []


# ── _extract_scrape_payload ───────────────────────────────────────────────────

class TestExtractScrapePayload:
    def test_dict_with_data_nested_dict_returned(self):
        result = _extract_scrape_payload({"data": {"markdown": "# Hello"}})
        assert result == {"markdown": "# Hello"}

    def test_flat_dict_returned_as_is(self):
        result = _extract_scrape_payload({"markdown": "# Hello", "url": "x"})
        assert result == {"markdown": "# Hello", "url": "x"}

    def test_non_dict_returns_empty(self):
        assert _extract_scrape_payload(None) == {}
        assert _extract_scrape_payload("string") == {}
        assert _extract_scrape_payload(42) == {}
        assert _extract_scrape_payload([]) == {}

    def test_data_non_dict_falls_through_to_outer_dict(self):
        """data=list → not a dict → return the outer dict instead."""
        payload = {"data": [1, 2, 3], "other": "x"}
        result = _extract_scrape_payload(payload)
        assert result == payload

    def test_sdk_object_converted_via_model_dump(self):
        obj = MagicMock(spec=["model_dump"])
        obj.model_dump.return_value = {"data": {"content": "converted"}}
        result = _extract_scrape_payload(obj)
        assert result == {"content": "converted"}

    def test_empty_dict_returned_as_is(self):
        assert _extract_scrape_payload({}) == {}

    def test_data_key_empty_dict_returned(self):
        result = _extract_scrape_payload({"data": {}})
        assert result == {}
