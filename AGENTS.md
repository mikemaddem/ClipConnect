# AGENTS.md — Conventions & commands for AI agents working on ClipConnect

Read this before making changes.

## Project summary

ClipConnect synchronizes gameplay clips from multiple player POVs. Users upload N video files;
the server fingerprints each clip's audio (chromaprint via `audalign`), computes per-clip time
offsets, and sends offsets to the frontend which drives multiple `<video>` elements from one
master control with single-audio-source selection. Self-hosted, no auth, Windows-first.

Target: runs locally on Windows. Python 3.11+, FastAPI, SQLite, vanilla JS frontend.

## Repo layout (target)

```
backend/
  app/
    main.py            # FastAPI app factory, router mounting
    config.py         # Settings (pydantic-settings), reads env vars
    db.py             # SQLite engine/session (SQLAlchemy or sqlite3)
    models.py         # Tables: Clip, Session, Job
    storage.py        # Storage abstraction: LocalBackend / S3Backend
    align.py          # audalign wrapper: extract audio -> fingerprint -> offsets
    jobs.py           # in-process background task runner (asyncio task + status)
    routes/
      sessions.py     # create/list/get a sync session
      clips.py        # upload clips to a session, get status
      sync.py         # GET computed offsets + audio selection
  templates/          # Jinja2: session.html (player), upload.html
  static/             # vanilla JS: player.js, player.css, upload.js
  requirements.txt
frontend/             # (optional) if a build step is ever added
tests/                # pytest; fixtures under tests/fixtures/
run.bat               # Windows launcher
.env.example
TASKS.md
AGENTS.md
README.md
```

A future agent may choose a slightly different layout, but keep FastAPI/SQLite/audalign/vanilla-JS
and the storage abstraction intact.

## Commands

Run all commands on Windows. From repo root after `run.bat` has created `.venv` (or create one
manually: `python -m venv .venv`).

```bat
:: Install deps
.venv\Scripts\python -m pip install -r backend\requirements.txt

:: Run dev server
.venv\Scripts\python -m uvicorn backend.app.main:app --reload --port 8000

:: Typecheck
.venv\Scripts\python -m mypy backend

:: Lint
.venv\Scripts\python -m ruff check backend

:: Tests
.venv\Scripts\python -m pytest
```

If `mypy`/`ruff` configs are added later, update the exact commands here. **Always run lint and
tests before declaring a task complete.** ffmpeg must be on `PATH` for alignment tests to pass.

## Conventions

- **No comments** in code unless asked. Keep docstrings short and only on public functions.
- **Security**: no auth by design, but never expose arbitrary local file paths to clients; serve
  media only through controlled endpoints or signed URLs. Validate uploads (mime, size).
- Keep two storage backends working: `LocalBackend` (default) and `S3Backend`. Never hardcode a
  filesystem path in route logic — go through `storage.py`.
- All long work (audio extraction, fingerprinting) runs in an in-process background task; the
  upload route returns immediately with a `job_id`. Poll for status.
- Offsets are expressed in **seconds, float, relative to the earliest-starting clip** — the clip
  that started recording earliest (contains the most footage before the shared moment) is the
  anchor at offset `0.0`; every later-starting clip gets a positive offset. See TASKS.md
  "Offset convention" for the exact master-timeline math — important to get right.
- Frontend is plain JS modules; no bundler. Use `<script type="module">`.
- Dependencies pinned in `backend/requirements.txt`. ffmpeg is a runtime external dep, never a
  pip package.

## Verification before finishing any task

1. `ruff check backend` passes.
2. `mypy backend` passes (or note if not yet configured).
3. `pytest` passes (add tests for new logic).
4. Manually confirm the app boots: `uvicorn backend.app.main:app` and `GET /` returns 200.