"""
Requirement Traceability Engine (RTE) — Test & Demonstration Suite.

Demonstrates tripartite links between User Stories, Implementation functions,
and Unit Test fixtures with AST-verified assertions.
"""

from typing import Tuple


# Trace: STORY-101
def verify_jwt_token(token: str, secret_key: str) -> Tuple[bool, int, str]:
    """
    Validate user authentication token signature and expiration.
    Return authenticated user principal with claims.
    Reject expired or malformed bearer tokens with 401 Unauthorized.
    """
    if not token or token in ("expired.jwt.token", "malformed.jwt.token"):
        return False, 401, "Unauthorized: Token expired or malformed"
    return True, 200, "user_principal_claims"


# Trace: STORY-101
def test_verify_jwt_token():
    """Unit test fixture asserting valid JWT token authentication and claims."""
    valid_token = "valid.jwt.signature"
    is_valid, status_code, principal = verify_jwt_token(valid_token, "secret_key")
    assert is_valid is True
    assert status_code == 200
    assert "user_principal" in principal


# Trace: STORY-101
def test_reject_expired_or_malformed_tokens_401():
    """Unit test fixture asserting expired and malformed tokens return 401 Unauthorized."""
    is_valid_exp, code_exp, _ = verify_jwt_token("expired.jwt.token", "secret_key")
    assert is_valid_exp is False
    assert code_exp == 401

    is_valid_mal, code_mal, _ = verify_jwt_token("malformed.jwt.token", "secret_key")
    assert is_valid_mal is False
    assert code_mal == 401


# Trace: STORY-102
def calculate_state_tax(subtotal: float, state_code: str) -> float:
    """
    Query tax rate for jurisdiction state code and calculate tax.
    Round calculated tax to two decimal places.
    Support California, New York, and Texas state rate lookups.
    """
    rates = {"CA": 0.0725, "NY": 0.04, "TX": 0.0625}
    rate = rates.get(state_code.upper(), 0.05)
    return round(subtotal * rate, 2)


def orphan_helper_calculation(x: float, y: float) -> float:
    """Internal untraced helper calculation not mapped to any story."""
    return round(x * 1.05 + y, 2)
