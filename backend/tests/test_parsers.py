"""Automated Unit Tests for AST Symbol Extractor and Git Delta Watcher."""

from __future__ import annotations

import pytest
from app.parsers.python_ast import (
    ParsedSymbol,
    parse_python_symbols,
)
from app.watcher.git_delta import (
    filter_symbols_by_delta,
    get_delta_ranges_from_diff,
)


def test_parse_python_symbols_with_and_without_trace_tags():
    """Verify AST extraction captures functions with and without # Trace: / # @trace directives."""
    source = (
        "# Trace: REQ-101\n"
        "def authenticate_user(token: str) -> bool:\n"
        "    \"\"\"Validate JWT bearer token.\"\"\"\n"
        "    return len(token) > 20\n"
        "\n"
        "# @trace REQ-102\n"
        "async def process_transaction(amount: float) -> str:\n"
        "    \"\"\"Process checkout payment transaction.\"\"\"\n"
        "    return 'tx_123'\n"
        "\n"
        "def untraced_helper():\n"
        "    \"\"\"Internal untraced helper.\"\"\"\n"
        "    return 42\n"
    )

    symbols = parse_python_symbols(file_path="app/auth.py", source_code=source)
    assert len(symbols) == 3

    # Symbol 1: authenticate_user with # Trace: REQ-101
    s1 = symbols[0]
    assert s1.name == "authenticate_user"
    assert s1.explicit_traces == ["REQ-101"]
    assert s1.kind == "code"
    assert s1.line_start == 2
    assert s1.line_end == 4
    assert "Validate JWT bearer token." in (s1.docstring or "")
    assert "def authenticate_user" in s1.code_snippet

    # Symbol 2: process_transaction with # @trace REQ-102
    s2 = symbols[1]
    assert s2.name == "process_transaction"
    assert s2.explicit_traces == ["REQ-102"]
    assert s2.kind == "code"
    assert s2.line_start == 7
    assert s2.line_end == 9
    assert "Process checkout payment transaction." in (s2.docstring or "")

    # Symbol 3: untraced_helper without any tags
    s3 = symbols[2]
    assert s3.name == "untraced_helper"
    assert s3.explicit_traces == []
    assert s3.kind == "code"
    assert s3.line_start == 11
    assert s3.line_end == 13


def test_syntax_error_resilience():
    """Verify in-progress syntax errors are handled gracefully without raising."""
    broken_source = "def incomplete_func(\n    return"
    symbols = parse_python_symbols(file_path="app/broken.py", source_code=broken_source)
    assert symbols == []


def test_test_fixture_classification_and_assertions():
    """Verify test functions in test files are classified kind='test' and detect assertions."""
    source = (
        "# Trace: REQ-101\n"
        "def test_authenticate_success():\n"
        "    res = authenticate_user('valid_bearer_token_12345')\n"
        "    assert res is True\n"
        "\n"
        "def test_unasserted_stub():\n"
        "    pass\n"
    )

    symbols = parse_python_symbols(file_path="tests/test_auth.py", source_code=source)
    assert len(symbols) == 2

    assert symbols[0].kind == "test"
    assert symbols[0].has_assertions is True
    assert symbols[0].explicit_traces == ["REQ-101"]

    assert symbols[1].kind == "test"
    assert symbols[1].has_assertions is False


def test_get_delta_ranges_from_diff():
    """Verify unified diff output parses into (start_line, end_line) intervals."""
    mock_diff = (
        "--- a/app/service.py\n"
        "+++ b/app/service.py\n"
        "@@ -10,3 +10,5 @@\n"
        " context\n"
        "+added line 1\n"
        "+added line 2\n"
        "@@ -25 +27 @@\n"
        "-old\n"
        "+new\n"
        "@@ -40,2 +42,0 @@\n"
        "-deleted\n"
    )

    ranges = get_delta_ranges_from_diff(mock_diff)
    assert len(ranges) == 3
    # Hunk 1: starts at 10, count 5 -> 10 to 14
    assert ranges[0] == (10, 14)
    # Hunk 2: starts at 27, count 1 -> 27 to 27
    assert ranges[1] == (27, 27)
    # Hunk 3: deletion at 42 -> (42, 42)
    assert ranges[2] == (42, 42)


def test_filter_symbols_by_delta():
    """Verify delta filtering selects only functions intersecting modified line ranges."""
    symbols = [
        ParsedSymbol(
            name="func_a",
            line_start=5,
            line_end=15,
            docstring=None,
            code_snippet="",
            kind="code",
        ),
        ParsedSymbol(
            name="func_b",
            line_start=20,
            line_end=30,
            docstring=None,
            code_snippet="",
            kind="code",
        ),
        ParsedSymbol(
            name="func_c",
            line_start=35,
            line_end=45,
            docstring=None,
            code_snippet="",
            kind="code",
        ),
    ]

    # Delta range only overlaps func_b (lines 22-24)
    delta_ranges = [(22, 24)]
    filtered = filter_symbols_by_delta(symbols, delta_ranges)
    assert len(filtered) == 1
    assert filtered[0].name == "func_b"

    # Delta range at line 18 (2 lines above func_b start_line 20) triggers header intersection
    header_delta = [(18, 18)]
    filtered_header = filter_symbols_by_delta(symbols, header_delta)
    assert len(filtered_header) == 1
    assert filtered_header[0].name == "func_b"

    # Delta range far outside any function
    outside_delta = [(100, 105)]
    assert filter_symbols_by_delta(symbols, outside_delta) == []
