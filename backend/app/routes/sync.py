from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from backend.app import db as db_module
from backend.app.models import Clip, Job, Session

router = APIRouter(tags=["sync"])


def get_db() -> object:
    session = db_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


class SyncClipOut(BaseModel):
    id: str
    media_url: str
    offset_sec: float
    offset_source: str
    moment_local_sec: float
    duration_sec: Optional[float]
    label: str
    status: str


class SyncOut(BaseModel):
    clips: list[SyncClipOut]
    audio_source_clip_id: Optional[str]
    total_duration_sec: float
    warnings: list[str]


class OffsetPatch(BaseModel):
    offset_sec: float


def _effective_offset(clip: Clip) -> float:
    if clip.offset_override_sec is not None:
        return clip.offset_override_sec
    return clip.offset_sec if clip.offset_sec is not None else 0.0


def _build_sync_payload(db: DBSession, session_id: str) -> dict:
    clips = db.query(Clip).filter(Clip.session_id == session_id).all()

    warnings: list[str] = []
    latest_job = (
        db.query(Job)
        .filter(Job.session_id == session_id, Job.status == "done")
        .order_by(Job.finished_at.desc())
        .first()
    )
    if latest_job and latest_job.detail and isinstance(latest_job.detail, dict):
        job_warnings = latest_job.detail.get("warnings", [])
        if isinstance(job_warnings, list):
            warnings.extend(job_warnings)

    sync_clips: list[dict] = []
    audio_source_clip_id: Optional[str] = None
    max_remaining = 0.0

    for clip in clips:
        eff = _effective_offset(clip)
        ml = clip.moment_local_sec if clip.moment_local_sec is not None else 0.0
        dur = clip.duration_sec

        if clip.status in ("aligned", "manual") and audio_source_clip_id is None:
            audio_source_clip_id = clip.id

        if dur is not None:
            remaining = dur - eff
            if remaining > max_remaining:
                max_remaining = remaining

        src = clip.offset_source if clip.offset_source else "auto"
        if clip.offset_override_sec is not None:
            src = "manual"

        sync_clips.append({
            "id": clip.id,
            "media_url": f"/sessions/{session_id}/clips/{clip.id}/media",
            "offset_sec": eff,
            "offset_source": src,
            "moment_local_sec": ml,
            "duration_sec": dur,
            "label": clip.filename,
            "status": clip.status,
        })

    return {
        "clips": sync_clips,
        "audio_source_clip_id": audio_source_clip_id,
        "total_duration_sec": max_remaining,
        "warnings": warnings,
    }


def _rebaseline(db: DBSession, session_id: str) -> None:
    clips = db.query(Clip).filter(Clip.session_id == session_id).all()
    if not clips:
        return

    eff_offsets = [_effective_offset(c) for c in clips]
    min_eff = min(eff_offsets)

    if min_eff < 0:
        for clip in clips:
            current = _effective_offset(clip)
            new_val = current - min_eff
            if clip.offset_override_sec is not None:
                clip.offset_override_sec = new_val
            else:
                clip.offset_override_sec = new_val
        db.commit()


@router.get("/sessions/{session_id}/sync", response_model=SyncOut)
async def get_sync(session_id: str, db: DBSession = Depends(get_db)) -> dict:
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _build_sync_payload(db, session_id)


@router.patch("/sessions/{session_id}/clips/{clip_id}/offset", response_model=SyncOut)
async def patch_offset(
    session_id: str,
    clip_id: str,
    body: OffsetPatch,
    db: DBSession = Depends(get_db),
) -> dict:
    clip = db.query(Clip).filter(Clip.id == clip_id, Clip.session_id == session_id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    dur = clip.duration_sec
    if dur is not None:
        if body.offset_sec < -dur or body.offset_sec > dur:
            raise HTTPException(
                status_code=422,
                detail=f"offset_sec must be within [-{dur}, {dur}]",
            )

    clip.offset_override_sec = body.offset_sec
    clip.offset_source = "manual"
    clip.status = "manual"
    db.commit()

    _rebaseline(db, session_id)

    return _build_sync_payload(db, session_id)


@router.delete("/sessions/{session_id}/clips/{clip_id}/offset", response_model=SyncOut)
async def delete_offset(
    session_id: str,
    clip_id: str,
    db: DBSession = Depends(get_db),
) -> dict:
    clip = db.query(Clip).filter(Clip.id == clip_id, Clip.session_id == session_id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    clip.offset_override_sec = None
    clip.offset_source = "auto"
    if clip.offset_sec is not None:
        clip.status = "aligned"
    db.commit()

    _rebaseline(db, session_id)

    return _build_sync_payload(db, session_id)
