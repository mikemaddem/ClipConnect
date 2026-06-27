from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.app.db import init_db
from backend.app.routes.clips import router as clips_router
from backend.app.routes.jobs import router as jobs_router
from backend.app.routes.pages import router as pages_router
from backend.app.routes.sessions import router as sessions_router
from backend.app.routes.sync import router as sync_router

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def create_app() -> FastAPI:
    app = FastAPI(title="ClipConnect")

    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    @app.on_event("startup")
    async def startup() -> None:
        init_db()

    @app.get("/")
    async def index(request: Request) -> object:
        return templates.TemplateResponse("index.html", {"request": request})

    app.include_router(sessions_router)
    app.include_router(clips_router)
    app.include_router(jobs_router)
    app.include_router(sync_router)
    app.include_router(pages_router)

    return app


app = create_app()
