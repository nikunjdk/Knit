def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["environment"] == "qa"


def test_all_routes_registered(client):
    paths = {r.path for r in client.app.routes}
    assert "/health" in paths
    assert "/events/lookup" in paths
    assert "/enrich-profile" in paths
    assert "/embeddings/recompute" in paths
    assert "/icebreaker/stream" in paths
    assert "/digest/stream" in paths
