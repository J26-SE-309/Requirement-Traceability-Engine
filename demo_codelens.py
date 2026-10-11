"""
Requirement Traceability Engine (RTE) — CodeLens Demonstration Suite.

This file demonstrates all 4 tripartite verification states recognized by the engine:
 1. VERIFIED:       Production function + Verified unit test fixture (with assertions).
 2. MISSING_TEST:   Explicitly tagged production function lacking unit test assertions.
 3. CANDIDATE:      Untagged function semantically matched to a story via local INT8 SBERT.
 4. ORPHAN:         Utility helper unrelated to any requirement in the active sprint backlog.
"""

from typing import Tuple, Dict, Any


# ==============================================================================
# SCENARIO 1: VERIFIED STATUS (STORY-101: JWT Authentication)
# Both production function and test fixture are traced, tested, and assert-verified.
# ==============================================================================

# Trace: STORY-101
def verify_jwt_token(token: str, secret_key: str) -> Tuple[bool, int, str]:
    """
    Validate user authentication token signature and expiration.
    Return authenticated user principal with claims, or reject expired
    or malformed bearer tokens with 401 Unauthorized.
    """
    if not token or token == "expired.jwt.token" or token == "malformed.jwt.token":
        return False, 401, "Unauthorized: Token expired or malformed"
    return True, 200, "user_principal_john_doe"


# Trace: STORY-101
def test_verify_jwt_token():
    """Unit test fixture asserting valid JWT token authentication."""
    valid_token = "valid.jwt.signature"
    is_valid, status_code, principal = verify_jwt_token(valid_token, "prod_secret")
    assert is_valid is True
    assert status_code == 200
    assert "john_doe" in principal


# ==============================================================================
# SCENARIO 2: MISSING TEST STATUS (STORY-102: State Sales Tax Computation)
# Explicitly tagged with # Trace: STORY-102, but developer has not yet written tests.
# ==============================================================================

# Trace: STORY-102
def calculate_state_sales_tax(subtotal: float, state_code: str) -> float:
    """
    Query tax rate for jurisdiction state code and calculate tax.
    Round calculated tax to two decimal places.
    Support California (7.25%), New York (4.0%), and Texas (6.25%) state rate lookups.
    """
    state_rates = {
        "CA": 0.0725,
        "NY": 0.0400,
        "TX": 0.0625,
    }
    rate = state_rates.get(state_code.upper(), 0.05)
    return round(subtotal * rate, 2)


# ==============================================================================
# SCENARIO 3: CANDIDATE STATUS (STORY-103: Stripe Credit Card Payments)
# NO explicit # Trace tag! Dense INT8 SBERT ONNX AI matches this automatically!
# ==============================================================================

def process_stripe_card_charge(amount_cents: int, currency: str, token: str) -> Dict[str, Any]:
    """
    Process card transaction charge through payment gateway.
    Validate charge currency and minimum order amount.
    Issue partial or full refund against captured charge ID.
    """
    if amount_cents < 50:
        raise ValueError("Charge amount does not meet minimum order threshold")

    return {
        "charge_id": "ch_3NabcXYZ123",
        "status": "succeeded",
        "captured": True,
        "amount": amount_cents,
        "currency": currency.lower(),
    }


# ==============================================================================
# SCENARIO 4: ORPHAN / UNLINKED FUNCTION
# Internal helper function that does not relate to any active backlog requirement.
# ==============================================================================

def internal_format_currency_label(amount: float, symbol: str = "$") -> str:
    """Utility formatter for UI display. Not linked to any sprint user story."""
    return f"{symbol}{amount:,.2f}"
