from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.app.db import init_db
from backend.app.routes.clips import router as clips_router
from backend.app.routes.sessions import router as sessions_router

BASE_DIR = Path(__file__).resolve().parent


def create_app() -> FastAPI:
    app = FastAPI(title="ClipConnect")

    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

    @app.on_event("startup")
    async def startup() -> None:
        init_db()

    @app.get("/")
    async def index(request: Request) -> object:
        return templates.TemplateResponse("index.html", {"request": request})

    app.include_router(sessions_router)
    app.include_router(clips_router)

    return app


app = create_app()
