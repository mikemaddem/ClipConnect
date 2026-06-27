from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session as DBSession

from backend.app import db as db_module
from backend.app.config import settings
from backend.app.models import Clip, Session
from backend.app.storage import LocalBackend, get_backend

router = APIRouter(prefix="/sessions/{session_id}/clips", tags=["clips"])

ALLOWED_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".avi"}


def get_db() -> object:
    session = db_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@router.post("/")
async def upload_clips(
    session_id: str,
    files: list[UploadFile],
    db: DBSession = Depends(get_db),
) -> list[dict]:
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    backend = get_backend()
    created: list[dict] = []

    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=415, detail=f"Unsupported file type: {ext}")

        content = await f.read()
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail=f"File too large: {f.filename}")

        import io

        storage_ref = backend.save_upload(session_id, f.filename or "clip", io.BytesIO(content))

        clip = Clip(
            session_id=session_id,
            filename=f.filename or "clip",
            storage_ref=storage_ref,
            bytes=len(content),
        )
        db.add(clip)
        db.commit()
        db.refresh(clip)
        created.append({"id": clip.id, "filename": clip.filename, "bytes": clip.bytes, "status": clip.status})

    return created


@router.get("/{clip_id}/media")
async def stream_media(
    session_id: str,
    clip_id: str,
    request: Request,
    db: DBSession = Depends(get_db),
) -> object:
    clip = db.query(Clip).filter(Clip.id == clip_id, Clip.session_id == session_id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    backend = get_backend()

    url = backend.get_url(clip.storage_ref)
    if url is not None:
        return RedirectResponse(url=url)

    assert isinstance(backend, LocalBackend)
    file_path = Path(settings.storage_local_dir) / clip.storage_ref
    file_size = file_path.stat().st_size

    range_header = request.headers.get("range")

    if range_header:
        range_spec = range_header.replace("bytes=", "")
        start_str, _, end_str = range_spec.partition("-")
        start = int(start_str)
        end = int(end_str) if end_str else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1

        def iter_file() -> Iterator[bytes]:
            with open(file_path, "rb") as fh:
                fh.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = fh.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            iter_file(),
            status_code=206,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(length),
                "Content-Type": "video/mp4",
            },
        )

    def iter_full() -> Iterator[bytes]:
        with open(file_path, "rb") as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        iter_full(),
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Type": "video/mp4",
        },
    )
