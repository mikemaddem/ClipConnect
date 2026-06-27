from __future__ import annotations

import io

from fastapi.testclient import TestClient


def _create_session(client: TestClient) -> str:
    resp = client.post("/sessions", json={"title": "Clip Test"})
    return resp.json()["id"]


def test_upload_clip(client: TestClient) -> None:
    sid = _create_session(client)
    fake_mp4 = io.BytesIO(b"\x00" * 100)
    resp = client.post(
        f"/sessions/{sid}/clips/",
        files=[("files", ("test.mp4", fake_mp4, "video/mp4"))],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["filename"] == "test.mp4"
    assert data[0]["status"] == "uploaded"
    assert data[0]["bytes"] == 100


def test_upload_multiple_clips(client: TestClient) -> None:
    sid = _create_session(client)
    files = [
        ("files", ("a.mp4", io.BytesIO(b"\x00" * 50), "video/mp4")),
        ("files", ("b.mkv", io.BytesIO(b"\x00" * 60), "video/x-matroska")),
    ]
    resp = client.post(f"/sessions/{sid}/clips/", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_upload_bad_extension(client: TestClient) -> None:
    sid = _create_session(client)
    resp = client.post(
        f"/sessions/{sid}/clips/",
        files=[("files", ("test.txt", io.BytesIO(b"hello"), "text/plain"))],
    )
    assert resp.status_code == 415


def test_upload_to_missing_session(client: TestClient) -> None:
    resp = client.post(
        "/sessions/missing/clips/",
        files=[("files", ("test.mp4", io.BytesIO(b"\x00"), "video/mp4"))],
    )
    assert resp.status_code == 404


def test_media_stream(client: TestClient) -> None:
    sid = _create_session(client)
    content = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09"
    upload_resp = client.post(
        f"/sessions/{sid}/clips/",
        files=[("files", ("stream.mp4", io.BytesIO(content), "video/mp4"))],
    )
    clip_id = upload_resp.json()[0]["id"]

    resp = client.get(f"/sessions/{sid}/clips/{clip_id}/media")
    assert resp.status_code == 200
    assert resp.content == content


def test_media_range_request(client: TestClient) -> None:
    sid = _create_session(client)
    content = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09"
    upload_resp = client.post(
        f"/sessions/{sid}/clips/",
        files=[("files", ("range.mp4", io.BytesIO(content), "video/mp4"))],
    )
    clip_id = upload_resp.json()[0]["id"]

    resp = client.get(
        f"/sessions/{sid}/clips/{clip_id}/media",
        headers={"range": "bytes=2-5"},
    )
    assert resp.status_code == 206
    assert resp.content == content[2:6]
    assert "content-range" in resp.headers


def test_media_not_found(client: TestClient) -> None:
    sid = _create_session(client)
    resp = client.get(f"/sessions/{sid}/clips/nonexistent/media")
    assert resp.status_code == 404
