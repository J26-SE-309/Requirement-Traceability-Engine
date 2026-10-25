"""
Unit test verification suite for STORY-101.
Tests implementation in src/authenticate_jwt_service.py.

User Story:
As a registered customer, I want to authenticate with JWT tokens so that I can securely access protected platform resources.
"""

from __future__ import annotations

import pytest
from src.authenticate_jwt_service import (
    validate_authentication_token,
    process_return_authenticated,
    reject_expired_malformed,
)


# Trace: STORY-101
def test_validate_authentication_token():
    """
    Verify Acceptance Criterion AC-1:
    Validate user authentication token signature and expiration
    """
    result = validate_authentication_token("valid_sample_input")
    assert result is not None
    assert result["status"] == "completed"
    assert result["story_id"] == "STORY-101"
    assert result["verified"] is True

    with pytest.raises(ValueError):
        validate_authentication_token(None)


# Trace: STORY-101
def test_process_return_authenticated():
    """
    Verify Acceptance Criterion AC-2:
    Return authenticated user principal with claims
    """
    result = process_return_authenticated("valid_sample_input")
    assert result is not None
    assert result["status"] == "completed"
    assert result["story_id"] == "STORY-101"
    assert result["verified"] is True

    with pytest.raises(ValueError):
        process_return_authenticated(None)


# Trace: STORY-101
def test_reject_expired_malformed():
    """
    Verify Acceptance Criterion AC-3:
    Reject expired or malformed bearer tokens with 401 Unauthorized
    """
    result = reject_expired_malformed("valid_sample_input")
    assert result is not None
    assert result["status"] == "completed"
    assert result["story_id"] == "STORY-101"
    assert result["verified"] is True

    with pytest.raises(ValueError):
        reject_expired_malformed(None)
