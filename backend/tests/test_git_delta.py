"""Unit tests for Milestone 2: Git Delta Extractor."""

from __future__ import annotations

import time
import pytest
from app.parsers.python_ast import ParsedFunction
from app.watcher.git_delta import (
    filter_functions_by_dirty_lines,
    get_dirty_lines_from_diff,
)


def test_get_dirty_lines_from_diff_patterns():
    diff_text = (
        "--- a/app/service.py\n"
        "+++ b/app/service.py\n"
        "@@ -10,3 +10,4 @@\n"
        " context\n"
        "+added line 1\n"
        "+added line 2\n"
        "@@ -25 +26 @@\n"
        "-old line\n"
        "+new line\n"
        "@@ -40,2 +41,0 @@\n"
        "-deleted\n"
    )
    dirty = get_dirty_lines_from_diff(diff_text)
    # Hunk 1: lines 10, 11, 12, 13
    assert {10, 11, 12, 13}.issubset(dirty)
    # Hunk 2: line 26
    assert 26 in dirty
    # Hunk 3: deletion at 41
    assert 41 in dirty


def test_filter_functions_enclosing_dirty_lines():
    func1 = ParsedFunction(
        name="func_clean",
        qualified_name="func_clean",
        start_line=1,
        end_line=10,
        docstring=None,
        signature="def func_clean()",
        code_snippet="",
        semantic_text="",
    )
    func2 = ParsedFunction(
        name="func_dirty",
        qualified_name="func_dirty",
        start_line=15,
        end_line=25,
        docstring=None,
        signature="def func_dirty()",
        code_snippet="",
        semantic_text="",
    )
    func3 = ParsedFunction(
        name="func_clean_2",
        qualified_name="func_clean_2",
        start_line=30,
        end_line=40,
        docstring=None,
        signature="def func_clean_2()",
        code_snippet="",
        semantic_text="",
    )

    all_funcs = [func1, func2, func3]
    dirty_lines = {18, 19}  # lines inside func2 only

    filtered = filter_functions_by_dirty_lines(all_funcs, dirty_lines)
    assert len(filtered) == 1
    assert filtered[0].name == "func_dirty"


def test_filter_functions_header_comment_modified():
    func = ParsedFunction(
        name="traced_func",
        qualified_name="traced_func",
        start_line=10,
        end_line=20,
        docstring=None,
        signature="def traced_func()",
        code_snippet="",
        semantic_text="",
    )
    # Modify comment 2 lines above function header (line 8)
    dirty_lines = {8}
    filtered = filter_functions_by_dirty_lines([func], dirty_lines)
    assert len(filtered) == 1
    assert filtered[0].name == "traced_func"
