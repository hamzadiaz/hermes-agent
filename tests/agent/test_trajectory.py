"""Tests for agent/trajectory.py pure helper functions.

Covers:
- convert_scratchpad_to_think(): tag replacement logic
- has_incomplete_scratchpad(): open-tag-without-close detection
"""

from agent.trajectory import convert_scratchpad_to_think, has_incomplete_scratchpad


class TestConvertScratchpadToThink:
    def test_empty_string_returned_unchanged(self):
        assert convert_scratchpad_to_think("") == ""

    def test_none_returned_unchanged(self):
        assert convert_scratchpad_to_think(None) is None

    def test_no_scratchpad_tag_unchanged(self):
        text = "Just some plain text without tags."
        assert convert_scratchpad_to_think(text) == text

    def test_opening_tag_replaced(self):
        result = convert_scratchpad_to_think("<REASONING_SCRATCHPAD>thinking</REASONING_SCRATCHPAD>")
        assert "<think>thinking</think>" == result

    def test_only_opening_tag_replaced(self):
        result = convert_scratchpad_to_think("<REASONING_SCRATCHPAD>open only")
        assert result == "<think>open only"
        assert "<REASONING_SCRATCHPAD>" not in result

    def test_multiple_scratchpad_blocks_all_replaced(self):
        text = (
            "<REASONING_SCRATCHPAD>first</REASONING_SCRATCHPAD>"
            " text "
            "<REASONING_SCRATCHPAD>second</REASONING_SCRATCHPAD>"
        )
        result = convert_scratchpad_to_think(text)
        assert "<REASONING_SCRATCHPAD>" not in result
        assert "</REASONING_SCRATCHPAD>" not in result
        assert "<think>first</think>" in result
        assert "<think>second</think>" in result

    def test_surrounding_text_preserved(self):
        text = "before <REASONING_SCRATCHPAD>middle</REASONING_SCRATCHPAD> after"
        result = convert_scratchpad_to_think(text)
        assert result == "before <think>middle</think> after"

    def test_whitespace_only_content_replaced(self):
        result = convert_scratchpad_to_think("<REASONING_SCRATCHPAD>  \n  </REASONING_SCRATCHPAD>")
        assert "<think>  \n  </think>" == result


class TestHasIncompleteScratchpad:
    def test_none_returns_false(self):
        assert has_incomplete_scratchpad(None) is False

    def test_empty_string_returns_false(self):
        assert has_incomplete_scratchpad("") is False

    def test_no_tags_returns_false(self):
        assert has_incomplete_scratchpad("just text") is False

    def test_complete_block_returns_false(self):
        assert has_incomplete_scratchpad(
            "<REASONING_SCRATCHPAD>done</REASONING_SCRATCHPAD>"
        ) is False

    def test_open_without_close_returns_true(self):
        assert has_incomplete_scratchpad("<REASONING_SCRATCHPAD>incomplete") is True

    def test_close_without_open_returns_false(self):
        """Closing tag only (no opening) is not flagged as incomplete."""
        assert has_incomplete_scratchpad("</REASONING_SCRATCHPAD>") is False

    def test_multiple_blocks_last_open_returns_false_if_any_close_exists(self):
        """Function uses simple substring check: any closing tag means not incomplete."""
        text = (
            "<REASONING_SCRATCHPAD>closed</REASONING_SCRATCHPAD>"
            "<REASONING_SCRATCHPAD>open"
        )
        # </REASONING_SCRATCHPAD> is present (from first block) → returns False
        assert has_incomplete_scratchpad(text) is False

    def test_multiple_complete_blocks_returns_false(self):
        text = (
            "<REASONING_SCRATCHPAD>one</REASONING_SCRATCHPAD>"
            "<REASONING_SCRATCHPAD>two</REASONING_SCRATCHPAD>"
        )
        assert has_incomplete_scratchpad(text) is False
