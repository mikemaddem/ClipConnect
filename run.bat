@echo off
setlocal

where py >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON=py -3
) else (
    set PYTHON=python
)

if not exist .venv (
    echo Creating virtual environment...
    %PYTHON% -m venv .venv
)

echo Installing dependencies...
.venv\Scripts\python -m pip install -U pip >nul
.venv\Scripts\python -m pip install -r backend\requirements.txt

where ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    echo ffmpeg not found on PATH, downloading...
    if not exist .venv\bin mkdir .venv\bin
    .venv\Scripts\python -c "import urllib.request, zipfile, io, sys; r=urllib.request.urlopen('https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'); z=zipfile.ZipFile(io.BytesIO(r.read())); [z.extract(f, '.venv/bin') for f in z.namelist() if f.endswith('ffmpeg.exe')]"
    set "PATH=%CD%\.venv\bin;%PATH%"
)

echo Starting ClipConnect server...
.venv\Scripts\python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
