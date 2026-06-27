from __future__ import annotations

import io
import time

from fastapi.testclient import TestClient


def _create_session(client: TestClient) -> str:
    resp = client.post("/sessions", json={"title": "Job Test"})
    return resp.json()["id"]


def _upload_clip(client: TestClient, session_id: str, filename: str) -> str:
    fake_mp4 = io.BytesIO(b"\x00" * 100)
    resp = client.post(
        f"/sessions/{session_id}/clips/",
        files=[("files", (filename, fake_mp4, "video/mp4"))],
    )
    return resp.json()[0]["id"]


def test_trigger_align_creates_job(client: TestClient) -> None:
    sid = _create_session(client)
    _upload_clip(client, sid, "clip1.mp4")
    _upload_clip(client, sid, "clip2.mp4")

    resp = client.post(f"/sessions/{sid}/align")
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "queued"


def test_trigger_align_too_few_clips(client: TestClient) -> None:
    sid = _create_session(client)
    _upload_clip(client, sid, "clip1.mp4")

    resp = client.post(f"/sessions/{sid}/align")
    assert resp.status_code == 400
    assert "at least 2 clips" in resp.json()["detail"]


def test_trigger_align_no_clips(client: TestClient) -> None:
    sid = _create_session(client)

    resp = client.post(f"/sessions/{sid}/align")
    assert resp.status_code == 400


def test_trigger_align_session_not_found(client: TestClient) -> None:
    resp = client.post("/sessions/nonexistent/align")
    assert resp.status_code == 404


def test_get_job_status(client: TestClient) -> None:
    sid = _create_session(client)
    _upload_clip(client, sid, "clip1.mp4")
    _upload_clip(client, sid, "clip2.mp4")

    align_resp = client.post(f"/sessions/{sid}/align")
    job_id = align_resp.json()["job_id"]

    time.sleep(0.1)

    resp = client.get(f"/jobs/{job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == job_id
    assert data["session_id"] == sid
    assert data["kind"] == "align"
    assert data["status"] in ["queued", "running", "done", "failed"]
    assert "progress" in data


def test_get_job_not_found(client: TestClient) -> None:
    resp = client.get("/jobs/nonexistent")
    assert resp.status_code == 404


def test_get_session_jobs(client: TestClient) -> None:
    sid = _create_session(client)
    _upload_clip(client, sid, "clip1.mp4")
    _upload_clip(client, sid, "clip2.mp4")

    client.post(f"/sessions/{sid}/align")

    time.sleep(0.1)

    resp = client.get(f"/sessions/{sid}/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sid
    assert "jobs" in data
    assert "clips" in data
    assert "warnings" in data
    assert len(data["jobs"]) >= 1
    assert len(data["clips"]) == 2


def test_get_session_jobs_empty(client: TestClient) -> None:
    sid = _create_session(client)

    resp = client.get(f"/sessions/{sid}/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sid
    assert len(data["jobs"]) == 0
    assert len(data["clips"]) == 0


def test_get_session_jobs_not_found(client: TestClient) -> None:
    resp = client.get("/sessions/nonexistent/jobs")
    assert resp.status_code == 404
