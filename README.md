# ClipConnect

A self-hosted web app that synchronizes gameplay clips recorded from **different player POVs**
into one frame-accurate, single-playback experience. Friends each upload their own recording of
the same moment; ClipConnect analyzes the audio of each clip, aligns them to a common timeline,
and plays them back in lockstep — with only **one** POV's audio audible at a time (your choice).

> Designed for friends who all clipped the same funny moment from their own perspective and want
> to rewatch them synced together. No accounts, no cloud, no auth — just run it locally and share
> the URL over screen-share.

## How it works

1. **Upload** — Drop 2–N video files (one per player POV) through the web UI.
2. **Extract audio** — The server pulls a mono WAV track from each clip via `ffmpeg`.
3. **Fingerprint & align** — Each audio track is fingerprinted using
   [chromaprint](https://github.com/acoustid/chromaprint) (via the
   [audalign](https://pypi.org/project/audalign/) Python library). The fingerprints are matched
   across clips to compute a per-clip **time offset** — how far into each clip a shared reference
   moment occurs.
4. **Sync playback** — The frontend receives the offsets and drives multiple `<video>` elements
   from a single master play/pause/seek control, starting each clip at its offset so every POV
   lines up. Only the selected POV's audio is unmuted; switch the audio source anytime in the UI.
   When auto-align can't lock onto a clip (or you just disagree), drag that clip's **offset nudge
   slider** to align it by eye — the override is saved on the server and survives reloads.

No re-encoding, no stitching — the original files are streamed as-is and aligned in the browser.

## Tech stack

| Layer        | Choice                                                         |
|--------------|----------------------------------------------------------------|
| Backend      | **Python 3.11+ / FastAPI** (async, uvicorn)                    |
| Audio alignment | **audalign** + **chromaprint** (audio fingerprinting)       |
| Media decode | **ffmpeg** (external binary, must be on `PATH` or bundled)     |
| Storage      | **Local filesystem** by default; optional **S3-compatible** (MinIO/AWS) via env config |
| Task processing | In-process background tasks (no Celery/Redis)              |
| Frontend     | Server-rendered **Jinja2** templates + **vanilla JS**          |
| Database     | **SQLite** (file metadata, jobs) — zero-config                 |
| Packaging    | Windows `run.bat` bootstrap script (creates venv, fetches ffmpeg, installs deps, launches server) |

## Quick start (Windows)

```bat
run.bat
```

The first run will:
1. Create a `.venv` Python virtual environment.
2. Install all Python dependencies from `requirements.txt`.
3. Download a static `ffmpeg` build if `ffmpeg` is not already on your `PATH`.
4. Start the uvicorn server on `http://localhost:8000`.

Open that URL in your browser, share it via screen-share, and upload your clips.

> See `TASKS.md` for the full implementation roadmap and `AGENTS.md` for dev commands.

## Status

> **Note:** This repository is a fresh scaffold. The implementation plan lives in
> [`TASKS.md`](./TASKS.md) — future work is tracked there. None of the application code is
> written yet.

## Configuration

All runtime config is optional and provided via environment variables (see `.env.example`):

| Variable           | Default            | Description                                            |
|--------------------|--------------------|-------------------------------------------------------|
| `STORAGE_BACKEND`  | `local`            | `local` for filesystem, `s3` for S3-compatible storage |
| `STORAGE_LOCAL_DIR`| `./media`          | Local folder for uploads                              |
| `S3_ENDPOINT_URL`  | —                  | e.g. `http://localhost:9000` (MinIO)                  |
| `S3_BUCKET`        | —                  | Bucket name                                           |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | —     | Credentials                                           |
| `LIBRARY_DIR`      | `./data`           | SQLite DB + fingerprint cache                         |

## License

See [LICENSE](./LICENSE).