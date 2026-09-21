from fastapi.testclient import TestClient

from lens.api.app import create_app


def test_health_ok() -> None:
    client = TestClient(create_app())
    for path in ("/health", "/api/v1/health"):
        resp = client.get(path)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert resp.headers["x-request-id"]


def test_request_id_is_echoed() -> None:
    client = TestClient(create_app())
    resp = client.get("/health", headers={"x-request-id": "abc123"})
    assert resp.headers["x-request-id"] == "abc123"
