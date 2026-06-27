from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from backend.app import db as db_module
from backend.app.align import compute_offsets, extract_audio
from backend.app.config import settings
from backend.app.models import Clip, Job, Session

_active_jobs: dict[str, Job] = {}


def get_job(job_id: str) -> Optional[Job]:
    return _active_jobs.get(job_id)


def _run_align_sync(job_id: str, session_id: str) -> None:
    db: DBSession = db_module.SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.progress = 10
        db.commit()

        session = db.query(Session).filter(Session.id == session_id).first()
        if not session:
            job.status = "failed"
            job.detail = {"error": "Session not found"}
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            return

        clips = db.query(Clip).filter(Clip.session_id == session_id).all()
        if len(clips) < 2:
            job.status = "failed"
            job.detail = {"error": "Need at least 2 clips"}
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            return

        job.progress = 20
        db.commit()

        with tempfile.TemporaryDirectory() as tmp_dir:
            work_dir = Path(tmp_dir)
            wav_paths: list[Path] = []
            clip_map: dict[str, Clip] = {}

            for i, clip in enumerate(clips):
                video_path = Path(settings.storage_local_dir) / clip.storage_ref
                try:
                    wav_path = extract_audio(video_path, work_dir)
                    wav_paths.append(wav_path)
                    clip_map[wav_path.name] = clip
                except Exception as e:
                    clip.status = "failed"
                    clip.error_msg = f"Audio extraction failed: {e}"
                    db.commit()

                job.progress = 20 + int(30 * (i + 1) / len(clips))
                db.commit()

            if len(wav_paths) < 2:
                job.status = "failed"
                job.detail = {"error": "Not enough clips with extractable audio"}
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
                return

            job.progress = 60
            db.commit()

            result = compute_offsets(wav_paths)

            job.progress = 80
            db.commit()

            for wav_name, offset in result.offsets.items():
                matched_clip = clip_map.get(wav_name)
                if matched_clip is not None:
                    matched_clip.offset_sec = offset
                    matched_clip.moment_local_sec = result.moment_locals.get(wav_name, 0.0)
                    matched_clip.status = "aligned"
                    matched_clip.offset_source = "auto"

            for warning in result.warnings:
                for clip in clips:
                    if clip.status == "failed":
                        continue

            job.progress = 100
            job.status = "done"
            job.detail = {
                "offsets": result.offsets,
                "moment_locals": result.moment_locals,
                "rankings": result.rankings,
                "recognizers_used": result.recognizers_used,
                "warnings": result.warnings,
            }
            job.finished_at = datetime.now(timezone.utc)
            db.commit()

    except Exception as e:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "failed"
            job.detail = {"error": str(e)}
            job.finished_at = datetime.now(timezone.utc)
            db.commit()

        for clip in db.query(Clip).filter(Clip.session_id == session_id).all():
            if clip.status not in ["aligned", "manual"]:
                clip.status = "failed"
                clip.error_msg = f"Alignment failed: {e}"
        db.commit()

    finally:
        db.close()


async def _run_align_async(job_id: str, session_id: str) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run_align_sync, job_id, session_id)


def enqueue_align(session_id: str) -> str:
    db: DBSession = db_module.SessionLocal()
    try:
        job = Job(session_id=session_id, kind="align", status="queued", progress=0)
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
        _active_jobs[job_id] = job
    finally:
        db.close()

    asyncio.create_task(_run_align_async(job_id, session_id))
    return job_id
