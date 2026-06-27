from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

os.environ["STORAGE_LOCAL_DIR"] = ""
os.environ["LIBRARY_DIR"] = ""


@pytest.fixture()
def tmp_dirs(tmp_path: Path) -> Path:
    storage_dir = tmp_path / "media"
    library_dir = tmp_path / "data"
    storage_dir.mkdir()
    library_dir.mkdir()
    os.environ["STORAGE_LOCAL_DIR"] = str(storage_dir)
    os.environ["LIBRARY_DIR"] = str(library_dir)
    return tmp_path


@pytest.fixture()
def client(tmp_dirs: Path) -> Generator[TestClient, None, None]:
    from backend.app.config import Settings

    test_settings = Settings()

    import backend.app.config as config_mod

    original = config_mod.settings
    config_mod.settings = test_settings

    import backend.app.db as db_mod
    from backend.app.models import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_url = f"sqlite:///{tmp_dirs / 'data' / 'test.sqlite'}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    db_mod.engine = engine
    db_mod.SessionLocal = TestSession

    from backend.app.main import create_app

    app = create_app()

    with TestClient(app) as c:
        yield c

    Base.metadata.drop_all(bind=engine)
    config_mod.settings = original
