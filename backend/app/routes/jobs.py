from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from backend.app import db as db_module
from backend.app.jobs import enqueue_align
from backend.app.models import Clip, Job, Session

router = APIRouter(tags=["jobs"])


def get_db() -> object:
    session = db_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


class JobOut(BaseModel):
    id: str
    session_id: str
    kind: str
    status: str
    progress: int
    detail: Optional[dict]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ClipStatusOut(BaseModel):
    id: str
    filename: str
    status: str
    offset_sec: Optional[float]
    error_msg: Optional[str]

    model_config = {"from_attributes": True}


class SessionJobsOut(BaseModel):
    session_id: str
    jobs: list[JobOut]
    clips: list[ClipStatusOut]
    warnings: list[str]


class AlignRequestOut(BaseModel):
    job_id: str
    status: str


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job_status(job_id: str, db: DBSession = Depends(get_db)) -> Job:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/sessions/{session_id}/jobs", response_model=SessionJobsOut)
async def get_session_jobs(session_id: str, db: DBSession = Depends(get_db)) -> dict:
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    jobs = db.query(Job).filter(Job.session_id == session_id).all()
    clips = db.query(Clip).filter(Clip.session_id == session_id).all()

    warnings: list[str] = []
    for job in jobs:
        if job.detail and isinstance(job.detail, dict):
            job_warnings = job.detail.get("warnings", [])
            if isinstance(job_warnings, list):
                warnings.extend(job_warnings)

    for clip in clips:
        if clip.status == "failed":
            warnings.append(f"Clip {clip.filename} failed: {clip.error_msg or 'unknown error'}")

    return {
        "session_id": session_id,
        "jobs": jobs,
        "clips": clips,
        "warnings": warnings,
    }


@router.post("/sessions/{session_id}/align", response_model=AlignRequestOut)
async def trigger_align(session_id: str, db: DBSession = Depends(get_db)) -> dict:
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    clips = (
        db.query(Clip)
        .filter(Clip.session_id == session_id, Clip.status.in_(["uploaded", "audio_extracted"]))
        .all()
    )

    if len(clips) < 2:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least 2 clips with status 'uploaded' or 'audio_extracted', found {len(clips)}",
        )

    job_id = enqueue_align(session_id)
    return {"job_id": job_id, "status": "queued"}
