from __future__ import annotations

import io

from fastapi.testclient import TestClient


def _create_session(client: TestClient) -> str:
    resp = client.post("/sessions", json={"title": "Sync Test"})
    return resp.json()["id"]


def _upload_clip(client: TestClient, sid: str, name: str, size: int = 100) -> str:
    resp = client.post(
        f"/sessions/{sid}/clips/",
        files=[("files", (name, io.BytesIO(b"\x00" * size), "video/mp4"))],
    )
    return resp.json()[0]["id"]


def _set_clip_aligned(client: TestClient, sid: str, clip_id: str, offset: float = 0.0) -> None:
    from backend.app import db as db_module
    from backend.app.models import Clip

    db = db_module.SessionLocal()
    try:
        clip = db.query(Clip).filter(Clip.id == clip_id).first()
        if clip:
            clip.offset_sec = offset
            clip.moment_local_sec = offset
            clip.duration_sec = 120.0
            clip.status = "aligned"
            clip.offset_source = "auto"
            db.commit()
    finally:
        db.close()


def test_get_sync_structure(client: TestClient) -> None:
    sid = _create_session(client)
    cid = _upload_clip(client, sid, "clip1.mp4")
    _set_clip_aligned(client, sid, cid, offset=0.0)

    resp = client.get(f"/sessions/{sid}/sync")
    assert resp.status_code == 200
    data = resp.json()

    assert "clips" in data
    assert "audio_source_clip_id" in data
    assert "total_duration_sec" in data
    assert "warnings" in data

    assert len(data["clips"]) == 1
    clip = data["clips"][0]
    assert clip["id"] == cid
    assert clip["media_url"] == f"/sessions/{sid}/clips/{cid}/media"
    assert clip["offset_sec"] == 0.0
    assert clip["offset_source"] == "auto"
    assert clip["label"] == "clip1.mp4"
    assert clip["status"] == "aligned"
    assert data["audio_source_clip_id"] == cid


def test_get_sync_not_found(client: TestClient) -> None:
    resp = client.get("/sessions/nonexistent/sync")
    assert resp.status_code == 404


def test_patch_offset(client: TestClient) -> None:
    sid = _create_session(client)
    cid = _upload_clip(client, sid, "clip1.mp4")
    _set_clip_aligned(client, sid, cid, offset=0.0)

    resp = client.patch(
        f"/sessions/{sid}/clips/{cid}/offset",
        json={"offset_sec": 2.5},
    )
    assert resp.status_code == 200
    data = resp.json()

    clip_data = next(c for c in data["clips"] if c["id"] == cid)
    assert clip_data["offset_source"] == "manual"
    assert clip_data["status"] == "manual"


def test_get_sync_after_patch(client: TestClient) -> None:
    sid = _create_session(client)
    cid = _upload_clip(client, sid, "clip1.mp4")
    _set_clip_aligned(client, sid, cid, offset=0.0)

    client.patch(
        f"/sessions/{sid}/clips/{cid}/offset",
        json={"offset_sec": 3.0},
    )

    resp = client.get(f"/sessions/{sid}/sync")
    assert resp.status_code == 200
    data = resp.json()
    clip_data = next(c for c in data["clips"] if c["id"] == cid)
    assert clip_data["offset_sec"] == 3.0
    assert clip_data["offset_source"] == "manual"


def test_delete_offset(client: TestClient) -> None:
    sid = _create_session(client)
    cid = _upload_clip(client, sid, "clip1.mp4")
    _set_clip_aligned(client, sid, cid, offset=1.5)

    client.patch(
        f"/sessions/{sid}/clips/{cid}/offset",
        json={"offset_sec": 5.0},
    )

    resp = client.delete(f"/sessions/{sid}/clips/{cid}/offset")
    assert resp.status_code == 200
    data = resp.json()
    clip_data = next(c for c in data["clips"] if c["id"] == cid)
    assert clip_data["offset_source"] == "auto"
    assert clip_data["offset_sec"] == 1.5


def test_nudge_past_duration_rejected(client: TestClient) -> None:
    sid = _create_session(client)
    cid = _upload_clip(client, sid, "clip1.mp4")
    _set_clip_aligned(client, sid, cid, offset=0.0)

    resp = client.patch(
        f"/sessions/{sid}/clips/{cid}/offset",
        json={"offset_sec": 200.0},
    )
    assert resp.status_code == 422


def test_rebaseline_on_nudge(client: TestClient) -> None:
    sid = _create_session(client)
    cid_a = _upload_clip(client, sid, "a.mp4")
    cid_b = _upload_clip(client, sid, "b.mp4")
    _set_clip_aligned(client, sid, cid_a, offset=0.0)
    _set_clip_aligned(client, sid, cid_b, offset=5.0)

    resp = client.patch(
        f"/sessions/{sid}/clips/{cid_a}/offset",
        json={"offset_sec": -3.0},
    )
    assert resp.status_code == 200
    data = resp.json()

    offsets = {c["id"]: c["offset_sec"] for c in data["clips"]}
    min_offset = min(offsets.values())
    assert min_offset >= 0.0


def test_total_duration_calculation(client: TestClient) -> None:
    sid = _create_session(client)
    cid_a = _upload_clip(client, sid, "a.mp4")
    cid_b = _upload_clip(client, sid, "b.mp4")
    _set_clip_aligned(client, sid, cid_a, offset=0.0)
    _set_clip_aligned(client, sid, cid_b, offset=10.0)

    resp = client.get(f"/sessions/{sid}/sync")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_duration_sec"] == 120.0
