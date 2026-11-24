from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_legacy_health_backward_compatible():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_v1_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database_enabled"] is False
    assert body["demo_mode"] is True


def test_v1_stocks_list():
    r = client.get("/api/v1/stocks")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 8
    assert any(item.get("is_synthetic") for item in data["items"])


def test_scan_horizon_validation():
    r = client.get("/api/scan?horizon=invalid")
    assert r.status_code == 400