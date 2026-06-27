from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from backend.app import db as db_module
from backend.app.models import Session

router = APIRouter(prefix="/sessions", tags=["sessions"])


def get_db() -> object:
    session = db_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


class SessionCreate(BaseModel):
    title: Optional[str] = None


class SessionOut(BaseModel):
    id: str
    created_at: datetime
    title: Optional[str]
    status: str

    model_config = {"from_attributes": True}


class ClipOut(BaseModel):
    id: str
    filename: str
    bytes: int
    status: str
    offset_sec: Optional[float]
    offset_source: str

    model_config = {"from_attributes": True}


class SessionDetail(SessionOut):
    clips: list[ClipOut] = []


@router.post("", response_model=SessionOut)
async def create_session(body: SessionCreate, db: DBSession = Depends(get_db)) -> Session:
    session = Session(title=body.title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("", response_model=list[SessionOut])
async def list_sessions(db: DBSession = Depends(get_db)) -> list[Session]:
    return db.query(Session).order_by(Session.created_at.desc()).all()


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str, db: DBSession = Depends(get_db)) -> Session:
    from fastapi import HTTPException

    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
