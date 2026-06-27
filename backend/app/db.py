from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config import settings
from backend.app.models import Base

lib_dir = Path(settings.library_dir)
lib_dir.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{lib_dir / 'clipconnect.sqlite'}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
