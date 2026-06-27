from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")

    clips: Mapped[list["Clip"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"))
    filename: Mapped[str] = mapped_column(String(512))
    storage_ref: Mapped[str] = mapped_column(String(1024))
    bytes: Mapped[int] = mapped_column(Integer)
    duration_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    moment_local_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    offset_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    offset_override_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    offset_source: Mapped[str] = mapped_column(String(10), default="auto")
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    error_msg: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    session: Mapped["Session"] = relationship(back_populates="clips")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"))
    kind: Mapped[str] = mapped_column(String(50), default="align")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    session: Mapped["Session"] = relationship(back_populates="jobs")
