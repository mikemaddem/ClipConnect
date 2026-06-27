from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_session(client: TestClient) -> None:
    resp = client.post("/sessions", json={"title": "Test Session"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Test Session"
    assert data["status"] == "active"
    assert "id" in data


def test_create_session_no_title(client: TestClient) -> None:
    resp = client.post("/sessions", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] is None


def test_list_sessions(client: TestClient) -> None:
    client.post("/sessions", json={"title": "First"})
    client.post("/sessions", json={"title": "Second"})
    resp = client.get("/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["title"] == "Second"
    assert data[1]["title"] == "First"


def test_get_session(client: TestClient) -> None:
    create_resp = client.post("/sessions", json={"title": "Detail"})
    sid = create_resp.json()["id"]
    resp = client.get(f"/sessions/{sid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Detail"
    assert "clips" in data


def test_get_session_not_found(client: TestClient) -> None:
    resp = client.get("/sessions/nonexistent")
    assert resp.status_code == 404
