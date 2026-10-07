"""Unit tests for Milestone 2: Python AST Symbol Parser."""

from __future__ import annotations

import pytest
from app.parsers.python_ast import (
    ParsedFunction,
    parse_python_source,
    _extract_story_ids_from_comment,
)


def test_extract_story_ids_directive_variants():
    """Verify various formats of # Trace: and # @trace directives."""
    assert _extract_story_ids_from_comment("# Trace: STORY-101") == ["STORY-101"]
    assert _extract_story_ids_from_comment("# @trace STORY-102") == ["STORY-102"]
    assert _extract_story_ids_from_comment("# trace: S-1, S-2") == ["S-1", "S-2"]
    assert _extract_story_ids_from_comment("# @trace: REQ_003") == ["REQ_003"]
    assert _extract_story_ids_from_comment("# Regular comment without tag") == []


def test_parse_functions_and_classes():
    source = (
        "# Trace: STORY-100\n"
        "def process_payment(amount: float, currency: str = 'USD') -> bool:\n"
        "    \"\"\"Process credit card transaction.\"\"\"\n"
        "    return amount > 0\n"
        "\n"
        "class InvoiceManager:\n"
        "    # @trace STORY-101\n"
        "    def generate_invoice(self, order_id: str):\n"
        "        \"\"\"Generate invoice for order.\"\"\"\n"
        "        pass\n"
    )

    funcs = parse_python_source(source, "src/billing.py")
    assert len(funcs) == 2

    f1 = funcs[0]
    assert f1.name == "process_payment"
    assert f1.qualified_name == "process_payment"
    assert f1.kind == "code"
    assert f1.explicit_traces == ["STORY-100"]
    assert "Process credit card transaction." in (f1.docstring or "")
    assert f1.start_line == 2
    assert f1.end_line == 4

    f2 = funcs[1]
    assert f2.name == "generate_invoice"
    assert f2.qualified_name == "InvoiceManager.generate_invoice"
    assert f2.kind == "code"
    assert f2.explicit_traces == ["STORY-101"]


def test_parse_test_fixture_with_assertions():
    source = (
        "# Trace: STORY-100\n"
        "def test_process_payment_success():\n"
        "    res = process_payment(50.0)\n"
        "    assert res is True\n"
    )

    funcs = parse_python_source(source, "tests/test_billing.py")
    assert len(funcs) == 1
    t1 = funcs[0]
    assert t1.name == "test_process_payment_success"
    assert t1.kind == "test"
    assert t1.has_assertions is True
    assert t1.explicit_traces == ["STORY-100"]


def test_test_fixture_without_assertions():
    source = (
        "def test_incomplete():\n"
        "    # no assertions here\n"
        "    pass\n"
    )
    funcs = parse_python_source(source, "tests/test_billing.py")
    assert len(funcs) == 1
    assert funcs[0].kind == "test"
    assert funcs[0].has_assertions is False


def test_syntax_error_resilience():
    bad_code = "def broken_syntax(:\n    pass"
    funcs = parse_python_source(bad_code, "broken.py")
    assert funcs == []
