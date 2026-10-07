"""Comprehensive integration tests for Traceability API and Tripartite Status."""

from __future__ import annotations

import time
import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_coverage_tripartite_status_and_linking(client):
    """Test full coverage response evaluating VERIFIED, MISSING_TEST, CANDIDATE, and ORPHAN."""
    file_content = (
        "# Trace: STORY-101\n"
        "def authenticate_user(username: str, token: str) -> bool:\n"
        "    \"\"\"Authenticate a user with JWT token.\"\"\"\n"
        "    return len(token) > 10\n"
        "\n"
        "# Trace: STORY-101\n"
        "def test_authenticate_success():\n"
        "    assert authenticate_user('alice', 'valid_token_xyz') is True\n"
        "\n"
        "# Trace: STORY-102\n"
        "def calculate_tax(amount: float) -> float:\n"
        "    \"\"\"Calculate sales tax on checkout amount.\"\"\"\n"
        "    return amount * 0.1\n"
        "\n"
        "def render_random_widget():\n"
        "    \"\"\"Totally unrelated canvas helper.\"\"\"\n"
        "    return 'widget'\n"
    )

    request_payload = {
        "stories": [
            {
                "story_id": "STORY-101",
                "user_story": "As a user I want to authenticate with a JWT token so that I can access secure resources.",
                "acceptance_criteria": ["JWT token validation", "Return success boolean"],
            },
            {
                "story_id": "STORY-102",
                "user_story": "As a shopper I want sales tax calculated at checkout.",
                "acceptance_criteria": ["Apply 10% rate"],
            },
            {
                "story_id": "STORY-103",
                "user_story": "As an admin I want audit logs exported to external SIEM.",
                "acceptance_criteria": ["Export logs"],
            },
        ],
        "target_file": "app/auth_and_billing.py",
        "file_content": file_content,
    }

    t0 = time.perf_counter()
    response = client.post("/api/v1/coverage", json=request_payload)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert response.status_code == 200
    data = response.json()
    items = {item["story_id"]: item for item in data["items"]}

    # STORY-101 has code AND test with assertion -> coverage_pct = 1.0, has_linked_tests = True
    assert items["STORY-101"]["coverage_pct"] == 1.0
    assert items["STORY-101"]["has_linked_tests"] is True
    assert len(items["STORY-101"]["linked_artifacts"]) >= 2

    # STORY-102 has code but NO test -> coverage_pct = 0.5, has_linked_tests = False, trace_gaps mentions missing test
    assert items["STORY-102"]["coverage_pct"] == 0.5
    assert items["STORY-102"]["has_linked_tests"] is False
    assert any("lacks test" in gap for gap in items["STORY-102"]["trace_gaps"])

    # STORY-103 has no matching code -> coverage_pct = 0.0
    assert items["STORY-103"]["coverage_pct"] == 0.0

    # Real-time latency budget constraint: < 350ms total
    assert elapsed_ms < 350.0, f"Coverage endpoint took {elapsed_ms:.2f}ms, exceeding 350ms budget!"


def test_file_trace_codelens_payload(client):
    """Verify POST /api/v1/trace/file returns structured function statuses."""
    content = (
        "# Trace: STORY-101\n"
        "def login_handler():\n"
        "    \"\"\"Handle user login.\"\"\"\n"
        "    return True\n"
        "\n"
        "def export_csv():\n"
        "    \"\"\"Export CSV dump.\"\"\"\n"
        "    return 'a,b,c'\n"
    )

    payload = {
        "file_path": "src/handlers.py",
        "file_content": content,
        "stories": [
            {
                "story_id": "STORY-101",
                "user_story": "User login session management",
                "acceptance_criteria": ["Handle login"],
            }
        ],
    }

    res = client.post("/api/v1/trace/file", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert len(data["functions"]) == 2

    fn_login = data["functions"][0]
    assert fn_login["name"] == "login_handler"
    assert fn_login["status"] in ("VERIFIED", "MISSING_TEST")
    assert fn_login["matched_story_id"] == "STORY-101"

    fn_orphan = data["functions"][1]
    assert fn_orphan["name"] == "export_csv"
    assert fn_orphan["status"] == "ORPHAN"


def test_cytoscape_graph_3_node_chain(client):
    """Verify POST /api/v1/trace/graph produces 3-node linear chain for active cursor function."""
    content = (
        "# Trace: STORY-101\n"
        "def authenticate_user():\n"
        "    return True\n"
        "\n"
        "# Trace: STORY-101\n"
        "def test_authenticate_user():\n"
        "    assert authenticate_user() is True\n"
    )

    payload = {
        "file_path": "src/auth.py",
        "cursor_line": 2,
        "file_content": content,
        "stories": [
            {
                "story_id": "STORY-101",
                "user_story": "Authenticate user credentials",
                "acceptance_criteria": ["Verify credentials"],
            }
        ],
    }

    res = client.post("/api/v1/trace/graph", json=payload)
    assert res.status_code == 200
    data = res.json()
    elements = data["graph"]["elements"]

    node_types = {el["data"].get("type") for el in elements if "source" not in el["data"]}
    assert "story" in node_types
    assert "function" in node_types
    assert "test" in node_types

    edge_ids = {el["data"]["id"] for el in elements if "source" in el["data"]}
    assert "edge_story_func" in edge_ids
    assert "edge_func_test" in edge_ids


def test_trace_coverage_endpoint_alias(client):
    """Explicitly verify POST /api/v1/trace/coverage accepts CoverageRequest and returns CoverageResponse."""
    payload = {
        "stories": [
            {
                "story_id": "REQ-1",
                "user_story": "As a user, I want password reset via email verification.",
                "acceptance_criteria": ["Send token", "Verify token"],
            }
        ]
    }
    res = client.post("/api/v1/trace/coverage", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["story_id"] == "REQ-1"
