from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session as DBSession

from backend.app import db as db_module
from backend.app.models import Session

router = APIRouter(tags=["pages"])


def get_db() -> object:
    session = db_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@router.get("/play/{session_id}")
async def play_page(session_id: str, request: Request, db: DBSession = Depends(get_db)) -> object:
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    from backend.app.main import templates
    return templates.TemplateResponse("session.html", {"request": request, "session_id": session_id})


@router.get("/upload")
async def upload_page(request: Request) -> object:
    from backend.app.main import templates
    return templates.TemplateResponse("upload.html", {"request": request, "session_id": None})


@router.get("/sessions/{session_id}/upload")
async def session_upload_page(
    session_id: str, request: Request, db: DBSession = Depends(get_db)
) -> object:
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    from backend.app.main import templates
    return templates.TemplateResponse("upload.html", {"request": request, "session_id": session_id})
