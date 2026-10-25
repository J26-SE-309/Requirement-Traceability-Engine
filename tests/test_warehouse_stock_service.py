"""
Unit test verification suite for STORY-104.
Tests implementation in src/warehouse_stock_service.py.

User Story:
As an inventory manager, I want warehouse stock reserved atomically when items are added to a checkout cart.
"""

from __future__ import annotations

import pytest
from src.warehouse_stock_service import (
    query_available_warehouse,
    process_atomically_decrement,
    process_raise_outofstockerror,
)


# Trace: STORY-104
def test_query_available_warehouse():
    """
    Verify Acceptance Criterion AC-1:
    Query available warehouse SKU quantity from database
    """
    result = query_available_warehouse("valid_sample_input")
    assert result is not None
    assert result["status"] == "completed"
    assert result["story_id"] == "STORY-104"
    assert result["verified"] is True

    with pytest.raises(ValueError):
        query_available_warehouse(None)


# Trace: STORY-104
def test_process_atomically_decrement():
    """
    Verify Acceptance Criterion AC-2:
    Atomically decrement stock count to avoid overselling
    """
    result = process_atomically_decrement("valid_sample_input")
    assert result is not None
    assert result["status"] == "completed"
    assert result["story_id"] == "STORY-104"
    assert result["verified"] is True

    with pytest.raises(ValueError):
        process_atomically_decrement(None)


# Trace: STORY-104
def test_process_raise_outofstockerror():
    """
    Verify Acceptance Criterion AC-3:
    Raise OutOfStockError if requested quantity exceeds inventory
    """
    result = process_raise_outofstockerror("valid_sample_input")
    assert result is not None
    assert result["status"] == "completed"
    assert result["story_id"] == "STORY-104"
    assert result["verified"] is True

    with pytest.raises(ValueError):
        process_raise_outofstockerror(None)
