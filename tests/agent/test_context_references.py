"""Tests for pure helper functions in agent/context_references.py.

Covers:
- _strip_trailing_punctuation(): trailing punctuation removal, unmatched bracket removal
- _code_fence_language(): extension → language name mapping, unknown extensions
- parse_context_references(): @diff, @staged, @file:, @folder:, @git:, @url:,
  line ranges, trailing punctuation in values, no-match cases
- _remove_reference_tokens(): token removal, whitespace normalization
"""

from dataclasses import dataclass
from pathlib import Path

import pytest

from agent.context_references import (
    _strip_trailing_punctuation,
    _code_fence_language,
    parse_context_references,
    _remove_reference_tokens,
    ContextReference,
)


# ── _strip_trailing_punctuation ───────────────────────────────────────────────

class TestStripTrailingPunctuation:
    def test_no_punctuation_unchanged(self):
        assert _strip_trailing_punctuation("myfile.py") == "myfile.py"

    def test_trailing_period_stripped(self):
        assert _strip_trailing_punctuation("myfile.py.") == "myfile.py"

    def test_trailing_comma_stripped(self):
        assert _strip_trailing_punctuation("myfile.py,") == "myfile.py"

    def test_multiple_trailing_punctuation_stripped(self):
        assert _strip_trailing_punctuation("myfile.py,.;") == "myfile.py"

    def test_unmatched_close_paren_stripped(self):
        assert _strip_trailing_punctuation("myfile.py)") == "myfile.py"

    def test_matched_parens_preserved(self):
        assert _strip_trailing_punctuation("(myfile.py)") == "(myfile.py)"

    def test_unmatched_bracket_stripped(self):
        assert _strip_trailing_punctuation("file.py]") == "file.py"

    def test_unmatched_brace_stripped(self):
        assert _strip_trailing_punctuation("file.py}") == "file.py"

    def test_empty_string(self):
        assert _strip_trailing_punctuation("") == ""

    def test_punctuation_only_stripped_to_empty(self):
        assert _strip_trailing_punctuation(",.;") == ""


# ── _code_fence_language ──────────────────────────────────────────────────────

class TestCodeFenceLanguage:
    def test_py_returns_python(self):
        assert _code_fence_language(Path("script.py")) == "python"

    def test_js_returns_javascript(self):
        assert _code_fence_language(Path("app.js")) == "javascript"

    def test_ts_returns_typescript(self):
        assert _code_fence_language(Path("mod.ts")) == "typescript"

    def test_tsx_returns_tsx(self):
        assert _code_fence_language(Path("comp.tsx")) == "tsx"

    def test_jsx_returns_jsx(self):
        assert _code_fence_language(Path("comp.jsx")) == "jsx"

    def test_json_returns_json(self):
        assert _code_fence_language(Path("data.json")) == "json"

    def test_md_returns_markdown(self):
        assert _code_fence_language(Path("README.md")) == "markdown"

    def test_sh_returns_bash(self):
        assert _code_fence_language(Path("run.sh")) == "bash"

    def test_yml_returns_yaml(self):
        assert _code_fence_language(Path("config.yml")) == "yaml"

    def test_yaml_returns_yaml(self):
        assert _code_fence_language(Path("config.yaml")) == "yaml"

    def test_toml_returns_toml(self):
        assert _code_fence_language(Path("pyproject.toml")) == "toml"

    def test_unknown_extension_returns_empty(self):
        assert _code_fence_language(Path("file.xyz")) == ""

    def test_no_extension_returns_empty(self):
        assert _code_fence_language(Path("Makefile")) == ""

    def test_case_insensitive_suffix(self):
        assert _code_fence_language(Path("script.PY")) == "python"


# ── parse_context_references ──────────────────────────────────────────────────

class TestParseContextReferences:
    def test_empty_message_returns_empty(self):
        assert parse_context_references("") == []

    def test_no_references_returns_empty(self):
        assert parse_context_references("just plain text") == []

    def test_diff_simple_reference(self):
        refs = parse_context_references("Here is @diff please review")
        assert len(refs) == 1
        assert refs[0].kind == "diff"
        assert refs[0].target == ""

    def test_staged_simple_reference(self):
        refs = parse_context_references("check @staged")
        assert len(refs) == 1
        assert refs[0].kind == "staged"

    def test_file_reference(self):
        refs = parse_context_references("look at @file:src/main.py please")
        assert len(refs) == 1
        assert refs[0].kind == "file"
        assert refs[0].target == "src/main.py"

    def test_folder_reference(self):
        refs = parse_context_references("@folder:src/components")
        assert len(refs) == 1
        assert refs[0].kind == "folder"
        assert refs[0].target == "src/components"

    def test_git_reference(self):
        refs = parse_context_references("@git:HEAD~1")
        assert len(refs) == 1
        assert refs[0].kind == "git"
        assert refs[0].target == "HEAD~1"

    def test_url_reference(self):
        refs = parse_context_references("@url:https://example.com/page")
        assert len(refs) == 1
        assert refs[0].kind == "url"

    def test_file_with_line_range(self):
        refs = parse_context_references("see @file:src/main.py:10-20")
        assert len(refs) == 1
        assert refs[0].target == "src/main.py"
        assert refs[0].line_start == 10
        assert refs[0].line_end == 20

    def test_file_with_single_line(self):
        refs = parse_context_references("@file:src/main.py:42")
        assert len(refs) == 1
        assert refs[0].line_start == 42
        assert refs[0].line_end == 42

    def test_trailing_punctuation_stripped_from_target(self):
        refs = parse_context_references("at @file:src/main.py,")
        assert len(refs) == 1
        assert refs[0].target == "src/main.py"

    def test_multiple_references(self):
        refs = parse_context_references("@file:a.py and @file:b.py")
        assert len(refs) == 2
        assert refs[0].target == "a.py"
        assert refs[1].target == "b.py"

    def test_start_end_positions_correct(self):
        msg = "hello @diff world"
        refs = parse_context_references(msg)
        assert len(refs) == 1
        assert msg[refs[0].start:refs[0].end] == "@diff"

    def test_word_prefix_not_matched(self):
        """@diff preceded by a word char should not match."""
        refs = parse_context_references("mycode@diff")
        assert refs == []


# ── _remove_reference_tokens ──────────────────────────────────────────────────

def _ref(start: int, end: int) -> ContextReference:
    """Build a minimal ContextReference for removal tests."""
    return ContextReference(raw="", kind="file", target="", start=start, end=end)


class TestRemoveReferenceTokens:
    def test_empty_refs_returns_message_unchanged(self):
        assert _remove_reference_tokens("hello world", []) == "hello world"

    def test_single_ref_removed(self):
        msg = "look at @file:main.py please"
        # @file:main.py is at positions 8..21
        ref_start = msg.index("@file")
        ref_end = msg.index(" please")
        result = _remove_reference_tokens(msg, [_ref(ref_start, ref_end)])
        assert "@file" not in result
        assert "look at" in result
        assert "please" in result

    def test_multiple_refs_removed(self):
        msg = "check @diff and @staged now"
        # Parse actual refs to get positions
        refs = parse_context_references(msg)
        result = _remove_reference_tokens(msg, refs)
        assert "@diff" not in result
        assert "@staged" not in result
        assert "check" in result
        assert "now" in result

    def test_extra_whitespace_collapsed(self):
        """Multiple spaces left by removal should be collapsed to one."""
        msg = "a @diff b"
        refs = parse_context_references(msg)
        result = _remove_reference_tokens(msg, refs)
        assert "  " not in result

    def test_result_stripped(self):
        """Leading/trailing whitespace is stripped."""
        msg = "@diff "
        refs = parse_context_references(msg)
        result = _remove_reference_tokens(msg, refs)
        assert result == result.strip()
