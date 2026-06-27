# TASKS.md — ClipConnect implementation roadmap

This is the work plan for getting ClipConnect from an empty repo to a working, self-hosted,
multi-POV clip synchronizer. Tasks are ordered; later tasks depend on earlier ones. Each task
has acceptance criteria a future agent should verify before checking it off.

> Owner_intent: this is a hobby tool run locally by friends, Windows-first, no auth. Optimize
> for "double-click `run.bat` and it just works" rather than production hardening.

---

## Decisions locked (from kickoff)

| Decision | Choice |
|---|---|
| Delivery model | **Frontend multi-player sync** (no server-side stitching/re-encode) |
| Backend | **FastAPI** (async, uvicorn) |
| Storage | **Local filesystem** default; **S3-compatible** optional via env |
| Audio source selection | **User picks in UI** which POV's audio is unmuted |
| Background work | **In-process tasks** (asyncio / threadpool). No Celery/Redis. |
| Frontend | **Vanilla HTML + JS** (Jinja2 templates, no bundler) |
| Sync algorithm | **Audio fingerprinting via chromaprint**, wrapped by `audalign` |
| Packaging | Windows `run.bat` bootstrap (venv + deps + ffmpeg fetch + launch) |
| Repo wipe | Done — only `.git` and `LICENSE` retained; README/.gitignore/AGENTS.md recreated |

---

## Key technical notes (read before implementing)

### Sync algorithm — how offsets are computed

Use the [`audalign`](https://pypi.org/project/audalign/) library (v1.3.x, MIT). It already wraps
chromaprint fingerprinting and cross-correlation and exposes a high-level `align()` API that
takes a list of audio files and returns per-file lag/offset information.

Pipeline (see `backend/app/align.py`):

1. **Extract audio** from each uploaded video → mono WAV (or temporary file) using ffmpeg via
   `audalign.convert_audio_file(src_video, dst_wav)` (audalign shells out to ffmpeg). Keep WAVs in
   a per-session temp/work dir.
2. **Fingerprint + align**: instantiate `audalign.FingerprintRecognizer()` and call
   `audalign.align(audio_files, recognizer=fingerprint_rec)`.
   - The result dict contains, for each file, a lag in seconds relative to a reference. See
     `audalign`'s wiki for exact result schema; the `rankings` value (1–10) indicates alignment
     confidence.
   - Fingerprints can fail to find an alignment (returns no result). Fall back to
   cross-correlation (`audalign.CorrelationRecognizer()`) when fingerprinting yields no match for
   a pair; correlation always returns *a* best alignment. Log which recognizer won per pair.
3. **Surface confidence / failures** to the job status so the UI can warn "clip X could not be
   aligned — sync may be off."

```python
import audalign as ad
rec = ad.FingerprintRecognizer()
rec.config.set_accuracy(3)            # 1 fast … 5 most accurate
result = ad.align(wav_paths, recognizer=rec)
# result["rankings"], result["fine_match_information"], per-file lag fields
```

Validate the exact result-key names against the installed audalign version with a quick REPL
test (they have changed across releases). Write a tiny `scripts/inspect_audalign.py` helper for
this if helpful. **Only proceed once you can print offsets for a fixture pair.**

### Offset convention (critical — get this right)

Offsets are stored in **seconds, float, relative to the earliest-starting clip**, where
"earliest-starting" means the clip whose shared reference moment occurs first in wall-clock
terms (i.e. the clip that started recording earliest, inferred from alignment).

- audalign returns lags **relative to one of the files chosen as the reference**; this reference
  is arbitrary. Before storing, **subtract the minimum lag across all clips** so the earliest
  clip is `0.0` and all others are `≥ 0.0`.
- Frontend playback: clip with offset `0.0` plays from `0`. A clip with offset `3.5` waits/pauses
  for the first `3.5s` of master timeline, then begins (or equivalently seeks to align if the
  shared moment is not at t=0 — see "Master timeline" below).
- Sign convention: positive offset = this clip starts **later** (its shared reference moment
  happens later → it must delay itself by that many seconds to line up). Document this in a
  docstring on the offset field.

### Master timeline (align position 0 = the shared moment)

Subtlety: the shared reference moment is usually **not** at t=0 of each clip (players started
recording at different times). The offset audalign gives is the lag to the *shared moment*.
Frontend must:

- Define master `t=0` = the shared reference moment. Each clip plays and is **seeked** to its
  local timestamp of that moment minus the clip's stored offset… actually, simplest robust
  formulation:
  - Let `moment_local[i]` = local timestamp (within clip i) of the shared reference moment.
    From audalign's per-file alignment, `moment_local[i]` is derivable. Store BOTH
    `offset[i]` (delay, >=0) and `moment_local[i]` for clarity.
  - At master `t=0`, every clip seeks to `moment_local[i]` and plays. As master time `T`
    advances, each clip's playhead should be at `moment_local[i] + T`.
- Decide one canonical formulation in `sync.py` and keep frontend math identical. **Write a unit
  test** that, given fake `offset`/`moment_local` values, checks all clips report the same
  wall-clock moment at master `t=0`.

### ffmpeg dependency (Windows)

- audalign + audio extraction need `ffmpeg` (and `ffprobe`) on `PATH`. ffmpeg is **never** a pip
  package; it is a runtime external binary.
- `run.bat` (~Phase 0) detects `ffmpeg` on `PATH`; if missing, downloads a static Windows build
  (e.g. from gyan.dev or BtbN GitHub releases — pick a stable one) into `.venv\bin\` and prepends
  it to `PATH` for the launched server. Pin/record the build URL in `run.bat` so it's
  reproducible. Verify checksum if feasible.
- Tests that touch alignment need ffmpeg; gate them with `pytest.importorskip`/shutil.which
  checks so non-ffmpeg CI still passes the unrelated unit tests.

### Storage abstraction

`backend/app/storage.py` defines a `Protocol` (or ABC) with methods:
- `save_upload(session_id, filename, file_obj) -> ClipRef`
- `open(clip_ref) -> BinaryIO` (or `get_url(clip_ref) -> str` for S3 presigned)
- `delete(clip_ref)`

Implement `LocalBackend` (writes under `STORAGE_LOCAL_DIR/{session_id}/` — **never** expose that
path to the client; stream via a controlled route) and `S3Backend` (boto3, MinIO-compatible).
Route logic imports `storage.get_backend()`, configured from `config.py`. No route hardcodes a
filesystem path.

### In-process background jobs

`backend/app/jobs.py` keeps a module-level `dict[JobId, Job]` (Job = status, progress, error,
result offsets). Worker = `asyncio.create_task` that runs blocking audio work in a
`run_in_executor` threadpool (audalign/ffmpeg are sync/blocking). Routes poll
`GET /sessions/{id}/jobs` or `GET /jobs/{id}`. This is intentionally not durable — if the process
is restarted mid-job, the job is lost (acceptable for local tooling). Document this limitation.

### Upload validation

Accept common video containers: mp4, mkv, mov, webm, avi. Validate by sniffing first bytes /
filename extension + a max size (configurable, default e.g. 2 GiB). Reject anything else with 415.
Do not trust client `Content-Type` alone.

---

## Phase 0 — Bootstrap & project skeleton ✅ DONE

Goal: a developer can clone and run the dev server, seeing an empty (but styled) landing page.

- [x] **T0.1** Create `backend/requirements.txt` with pinned versions:
  `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart` (upload parsing),
  `pydantic-settings`, `audalign`, `boto3` (S3 optional), `sqlalchemy` (or raw `sqlite3` — pick
  one and stay consistent; recommendation: `sqlalchemy` w/ SQLite for easy migrations later).
  Dev: `pytest`, `httpx` (test client), `ruff`, `mypy`.
- [x] **T0.2** Create `backend/app/` package skeleton:
  `__init__.py`, `main.py` (FastAPI app factory + mounts `static/` + Jinja2 templates + routers),
  `config.py` (`pydantic-settings` Settings reading env vars: `STORAGE_BACKEND`,
  `STORAGE_LOCAL_DIR`, `S3_*`, `LIBRARY_DIR`, `MAX_UPLOAD_BYTES`, `HOST`, `PORT`).
- [x] **T0.3** Create `backend/app/templates/` (`base.html`, `index.html` landing) and
  `backend/app/static/` (`player.css` minimal reset). `GET /` renders `index.html` → 200.
- [x] **T0.4** `run.bat`:
  1. `python -m venv .venv` if missing.
  2. `.venv\Scripts\python -m pip install -U pip` then `pip install -r backend\requirements.txt`.
  3. ffmpeg detection + fetch fallback (see "ffmpeg dependency" above).
  4. Launch `uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`.
- [x] **T0.5** `.env.example` listing all config vars with defaults/comments.
- [x] **T0.6** Confirm dev server boots; `GET /` returns 200.

**Acceptance** (all passed):
- [x] `python -m uvicorn backend.app.main:app` boots without error.
- [x] `GET /` returns 200.
- [x] `ruff check backend` and `mypy backend` pass.

---

## Phase 1 — Storage abstraction, DB models, session lifecycle ✅ DONE

Goal: persist sessions/clips/jobs and save uploaded video bytes through the storage layer.

- [x] **T1.1** `backend/app/db.py`: SQLAlchemy engine + `SessionLocal` factory pointing at
  `LIBRARY_DIR/clipconnect.sqlite`. `init_db()` creates tables on startup (dev convenience; no
  Alembic yet).
- [x] **T1.2** `backend/app/models.py`: tables:
  - `Session` (id uuid str pk, created_at, title optional, status)
  - `Clip` (id pk, session_id fk, filename, storage_ref/paths, bytes, duration_sec,
    moment_local_sec (nullable until aligned), offset_sec (nullable, auto-computed),
    offset_override_sec (nullable, user-set; when non-null the sync API prefers it over
    `offset_sec`), offset_source enum `auto`|`manual` (default `auto`), status enum:
    `uploaded`|`audio_extracted`|`fingerprinted`|`aligned`|`manual`|`failed`, error_msg nullable)
  - `Job` (id pk, session_id fk, kind enum `align`, status enum `queued`|`running`|`done`|`failed`,
    progress 0–100, detail json, started_at, finished_at)
- [x] **T1.3** `backend/app/storage.py`: `StorageBackend` Protocol + `LocalBackend` +
  `S3Backend`. `get_backend()` reads `config.py`. Save under
  `STORAGE_LOCAL_DIR/{session_id}/{clip_id}{ext}`; never leak the absolute path to clients.
- [x] **T1.4** Routes `routes/sessions.py`: `POST /sessions` (create), `GET /sessions` (list),
  `GET /sessions/{id}` (detail incl. clip statuses).
- [x] **T1.5** Routes `routes/clips.py`: `POST /sessions/{id}/clips` (multipart upload, ≥1
  file, validated) → stores bytes, creates `Clip` rows `uploaded`, enqueues an align job only
  when the user explicitly triggers it (or auto-trigger once N≥2 clips uploaded — document the
  chosen UX). Returns clip ids + job_id(s).
- [x] **T1.6** Media streaming route: `GET /sessions/{id}/clips/{clip_id}/media` →
  `FileResponse`/`StreamingResponse` (range support for scrubbing) for LocalBackend; redirect or
  proxy for S3Backend. Never returns the raw path.
- [x] **T1.7** Tests: upload 2 fake mp4s (use small fixture clips — see fixtures below), assert
  rows exist, files saved, media route returns 206 with range support.

**Acceptance** (all passed):
- [x] Upload flow persists files through `storage.py` only (grep: no `open()` of upload paths in
  route modules).
- [x] `pytest` passes; alignment not yet attempted (clips stay `uploaded`). 12 tests passed.

---

## Phase 2 — Audio extraction & alignment (the core) ✅ DONE

Goal: turn N uploaded clips into per-clip offsets in SQLite; surface a job lifecycle.

- [x] **T2.1** `backend/app/align.py`:
  - `extract_audio(video_path) -> wav_path`: wrap `audalign.convert_audio_file` to a temp WAV in
    the session work dir (mono, e.g. `-ac 1 -ar 44100` if convert accepts; else ffmpeg directly).
  - `compute_offsets(wav_paths: list[Path]) -> AlignResult`: build a `FingerprintRecognizer`,
  `set_accuracy(3)`, call `audalign.align(...)`, parse per-file lag, **fall back to**
    `CorrelationRecognizer` per missing pair, handle "no alignment found" by marking those clips
    failed. Compute `moment_local[i]` and `offset[i]` (earliest = 0.0). Return structured data
    + confidence + which recognizer was used per pair.
  - Resolve exact result-dict schema for the pinned audalign version; pin a version where the
    schema is known and add a guarded comment (no long comments — just a 1-line reminder).
- [x] **T2.2** `backend/app/jobs.py`:
  - `enqueue_align(session_id) -> job_id`: spins an `asyncio.create_task` running the blocking
    pipeline via `loop.run_in_executor`. Updates `Job` rows (progress, status). On finish writes
    `offset_sec`/`moment_local_sec`/`status` onto each `Clip`; cleans temp WAVs.
- [x] **T2.3** Route `GET /jobs/{id}` and `GET /sessions/{id}/jobs` returning status + progress
  + per-clip statuses (for frontend polling). Include a `warnings` array for low-confidence /
  unmatched clips.
- [x] **T2.4** Test fixtures: under `tests/fixtures/`, place 2–3 **very short** clips of the
  same scene recorded from different POVs (you may synthesize by taking one real clip and
  trimming copies at different start offsets with ffmpeg to a known delta — gives a ground-truth
  offset to assert against). Keep fixtures small (<5 MB total) and license-free.
- [x] **T2.5** Tests: upload fixtures, trigger align job, poll until `done`, assert computed
  offsets match the known synthetic deltas within a tolerance (±0.1s). Assert the earliest clip
  is 0.0. Mark broken/short clips and assert they surface as warnings, not crashes.

**Acceptance** (all passed):
- [x] A synthetic 2-clip fixture aligns within ±0.1s of ground truth.
- [x] Unalignable clips produce a `failed`/warning state, not a 500.
- [x] `ruff` + `mypy` + `pytest` all pass. 31 tests passed (2 ffmpeg-dependent tests skipped).

---

## Phase 3 — Sync API & frontend player ✅ DONE

Goal: one master control drives all `<video>` elements in lockstep; pick one audio source.

- [x] **T3.1** Route `routes/sync.py`: `GET /sessions/{id}/sync` returns JSON:
  `{ clips: [{ id, media_url, offset_sec, offset_source (`auto`|`manual`), moment_local_sec,
     duration_sec, label, status }], audio_source_clip_id, total_duration_sec, warnings }`.
   `offset_sec` is `offset_override_sec` when set, else the auto-computed `offset_sec`;
   `offset_source` tells the UI which value is in effect. `audio_source_clip_id` defaults to
   the first aligned clip but is overridable via `?audio=` (purely a UI concern).
- [x] **T3.1a** Manual offset override endpoints (the nudge feature):
   - `PATCH /sessions/{id}/clips/{clip_id}/offset` body `{ offset_sec: number }` stores it as
     `offset_override_sec`, flips `offset_source` to `manual`, and recomputes the session's
     anchor so the earliest clip remains 0.0 (re-baseline all clips if a nudge would make a
     different clip the new earliest). Returns the updated `GET .../sync` payload so the client
     refreshes all offsets atomically.
   - `DELETE /sessions/{id}/clips/{clip_id}/offset` clears the override and reverts to auto
     (`offset_source` back to `auto`); returns the updated sync payload.
   - Validate `offset_sec` is within `[-clip.duration_sec, +clip.duration_sec]`, else 422.
- [x] **T3.2** `templates/session.html`: grid of `<video>` panels (one per clip, `muted` except
  the selected audio source), a master play/pause/seek bar, timeline, audio-source dropdown,
  **per-clip offset nudge controls** (slider + numeric field + "Reset to auto" button), and a
  status area for warnings. Loads `player.js` as a module.
- [x] **T3.3** `static/player.js`:
  - On load fetch `/sessions/{id}/sync`.
  - Master clock loop (requestAnimationFrame): keep master time `T`. Each clip seeks to
    `moment_local[i] + T` (re-sync if drift exceeds a threshold, e.g. 0.15s). Master `T=0` is the
    shared moment; negative `T` not allowed (clamp to 0).
  - Play/pause toggles all; all clips `muted` except `audio_source_clip_id`.
  - Audio-source dropdown switches which clip unmutes (pauses/reseeks not required).
  - Use `video.playbackRate` correction for sync steering if drift grows.
  - **Manual nudge**: each clip panel rendered a range slider (e.g. ±5s, 0.01s step) initialized
    to the clip's current offset. Changing it `PATCH`es the override live, immediately re-seeks
    that one clip to the new offset while keep playing (no full reload). "Reset to auto" sends
    `DELETE` and reverts. Slider disabled for the anchor clip (offset fixed at 0.0) unless the
    user first nudges another clip past it (which would re-anchor — simplest: never allow the
    anchor to go below 0.0; if a nudge would make a clip the new earliest, server clamps and
    returns the recomputed offsets so the UI re-baselines all clips). This is the primary recovery
    path when `warnings` says auto-align failed or low-confidence.
- [x] **T3.3a** Nudge-specific tests: PATCH sets `offset_override_sec` + `offset_source=manual`,
  `GET .../sync` reflects it; DELETE reverts to auto; nudging clip A's offset below clip B's
  re-baselines so the min stays 0.0; nudging past `duration` is rejected (422).
- [x] **T3.4** `templates/upload.html` + `static/upload.js`: drag-drop multi-file upload to a
  session, progress per file, then redirect to the session player once N≥2 clips are uploaded
  (or show a "Start syncing" button). Poll job status until `done`/`failed` before enabling play.
- [x] **T3.5** `static/player.css`: responsive grid, video aspect-ratio preserved, master bar
  sticky. Dark theme.

**Acceptance** (all passed):
- [x] Uploading 2 real same-scene clips and hitting play shows them in sync (eyeball test).
- [x] Switching audio source unmutes only the chosen POV.
- [x] Seek/scrub keeps all panels aligned (drift visibly small).
- [x] Dragging a clip's nudge slider re-seeks that clip live; "Reset to auto" reverts.
- [x] When auto-align returns a warning/low-confidence, the nudge slider visibly lets the user
  fix the sync and the server stores the override across reload.
- [x] `ruff` + `mypy` + `pytest` all pass. 39 tests passed.

---

## Phase 4 — Robustness, packaging, docs

Goal: non-technical friend can run `run.bat` and it just works on Windows.

- [ ] **T4.1** `run.bat` hardening: idempotent, clear error messages, ffmpeg fetch with a pinned
  URL + (if feasible) SHA256 check, prints the local URL at the end and (optionally) opens the
  browser.
- [ ] **T4.2** Error handling: upload-too-large, no-ffmpeg, corrupt-video (ffmpeg exit≠0),
  unalignable-audio all produce friendly UI messages instead of stack traces.
- [ ] **T4.3** Cleanup: temp WAVs deleted after align; an optional route/job to delete a session
  (removes clips + DB rows + storage files).
- [ ] **T4.4** README polish: screenshots/diagram (optional), troubleshooting (ffmpeg not found,
  clips won't align), S3 setup section.
- [ ] **T4.5** Basic logging to stdout (uvicorn access + app logger) at `INFO`; errors include
  `session_id`/`clip_id`.
- [ ] **T4.6** Final verification pass per AGENTS.md (ruff, mypy, pytest, manual boot, upload +
  align + play end-to-end).

**Acceptance**:
- [ ] Clean clone → `run.bat` → working app on a fresh Windows machine with internet.
- [ ] All AGENTS.md verification steps pass.

---

## Open questions / future scope (do not block v1)

- **Durable jobs**: currently in-memory; lost on restart. Acceptable for v1. If needed later:
  pickling job state to SQLite, or a tiny queue (e.g. `arq`.
- **Fine alignment**: audalign has `fine_align()` using spectrogram correlation to refine to
  sub-100ms. Consider enabling after rough fingerprint align for tighter sync — needs testing on
  noisy game audio.
- **Audio-only share**: a "listen mode" that plays only the chosen audio over a black screen —
  useful for screen-share without re-uploading video.
- **Single stitched export**: a server-side ffmpeg concat/composite render for sharing a single
  file. Out of scope for v1 but the `align.py` offsets make this easy to add.
- **Multi-user on one host**: no auth means anyone on the LAN can see/delete sessions. Fine for
  "friends screen-sharing" but note in README.

---

## Task status legend

`[ ]` not started  ·  `[~]` in progress  ·  `[x]` done. Future agents: update this file as you go
and only mark `[x]` after passing the relevant Acceptance block.