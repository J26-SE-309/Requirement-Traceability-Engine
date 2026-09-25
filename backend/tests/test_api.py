def test_coverage_returns_one_item_per_story(client):
    stories = [{"story_id": "S-1", "user_story": "As a user..."}, {"story_id": "S-2", "user_story": "As an admin..."}]
    response = client.post("/api/v1/coverage", json={"stories": stories})
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["story_id"] for item in items] == ["S-1", "S-2"]
    assert all(0 <= item["coverage_pct"] <= 1 for item in items)


def test_coverage_needs_at_least_one_story(client):
    response = client.post("/api/v1/coverage", json={"stories": []})
    assert response.status_code == 422
