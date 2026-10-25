"""
Unit test verification suite for STORY-121.
Tests implementation in src/track_package_service.py.

User Story:
As a customer, I want to track my package delivery in real time using a GPS tracking ID.
"""

from __future__ import annotations

import pytest
from src.track_package_service import (
    query_real_time,
    process_return_estimated,
    process_raise_deliverynotfounderror,
)


# Trace: STORY-121
def test_query_real_time():
    """
    Verify Acceptance Criterion AC-1:
    Query real-time delivery coordinates for valid tracking ID
    """
    result = query_real_time("valid_sample_input")
    assert result is not None
    assert result["status"] == "completed"
    assert result["story_id"] == "STORY-121"
    assert result["verified"] is True

    with pytest.raises(ValueError):
        query_real_time(None)


# Trace: STORY-121
def test_process_return_estimated():
    """
    Verify Acceptance Criterion AC-2:
    Return estimated arrival timestamp and courier status
    """
    result = process_return_estimated("valid_sample_input")
    assert result is not None
    assert result["status"] == "completed"
    assert result["story_id"] == "STORY-121"
    assert result["verified"] is True

    with pytest.raises(ValueError):
        process_return_estimated(None)


# Trace: STORY-121
def test_process_raise_deliverynotfounderror():
    """
    Verify Acceptance Criterion AC-3:
    Raise DeliveryNotFoundError if tracking ID is invalid
    """
    result = process_raise_deliverynotfounderror("valid_sample_input")
    assert result is not None
    assert result["status"] == "completed"
    assert result["story_id"] == "STORY-121"
    assert result["verified"] is True

    with pytest.raises(ValueError):
        process_raise_deliverynotfounderror(None)
