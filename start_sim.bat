@echo off
:: ============================================================
::  start_sim.bat — Crane Camera Simulation Launcher (Windows)
::
::  PTZ commands are burned into the video by FFmpeg using the
::  drawtext filter, reading from ptz_cmd.txt which is updated
::  by the PTZ mock server in real time.
:: ============================================================

echo.
echo  ============================================
echo   Crane Camera Simulation — starting up...
echo  ============================================
echo.

:: ── Check dependencies ───────────────────────────────────────
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [ERROR] ffmpeg not found. Install: winget install Gyan.FFmpeg
    pause & exit /b 1
)
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] python not found. Install from python.org
    pause & exit /b 1
)
if exist "%~dp0mediamtx.exe" (
    set MEDIAMTX="%~dp0mediamtx.exe"
) else (
    where mediamtx >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] mediamtx.exe not found.
        echo         https://github.com/bluenviron/mediamtx/releases/latest
        pause & exit /b 1
    )
    set MEDIAMTX=mediamtx
)

echo [OK] All dependencies found.
echo.

:: ── Check if drawtext (freetype) is available ───────────────
:: Run a 1-frame test encode. If it fails, drawtext is not available.
echo Checking FFmpeg drawtext support...
ffmpeg -y -f lavfi -i color=black:s=64x64:d=0.1 -vf "drawtext=text='test':fontsize=12" -frames:v 1 -f null - >nul 2>&1
if errorlevel 1 (
    echo [WARN] drawtext not available in this FFmpeg build.
    echo        PTZ text will NOT appear in the video stream.
    echo        Install the full FFmpeg build to enable this:
    echo        https://www.gyan.dev/ffmpeg/builds/ ^(get "full" not "essentials"^)
    echo.
    set DRAWTEXT_OK=0
) else (
    echo [OK] drawtext supported.
    set DRAWTEXT_OK=1
)
echo.

:: ── Create empty ptz_cmd.txt ────────────────────────────────
echo.> "%~dp0ptz_cmd.txt"

:: ── Window 1: MediaMTX ──────────────────────────────────────
echo Starting MediaMTX...
start "MediaMTX — Stream Server" cmd /k "%MEDIAMTX% "%~dp0mediamtx.yml""
timeout /t 3 /nobreak >nul

:: ── Window 2: FFmpeg ─────────────────────────────────────────
echo Starting FFmpeg...

:: Convert ptz_cmd.txt path to FFmpeg filter-safe format:
::   backslashes → forward slashes, colon escaped (C: → C\:)
set "PTZ_PATH=%~dp0ptz_cmd.txt"
set "PTZ_PATH=%PTZ_PATH:\=/%"
set "PTZ_PATH=%PTZ_PATH::=\:%"

if "%DRAWTEXT_OK%"=="1" (
    :: Full version — PTZ command text burned into video
    :: drawtext reads ptz_cmd.txt and reloads it every frame (reload=1)
    :: fontfile points to a font guaranteed on all Windows machines
    start "FFmpeg — Fake Camera" cmd /k "ffmpeg -re -f lavfi -i testsrc2=size=1920x1080:rate=30 -vf drawtext=fontfile=C\:/Windows/Fonts/consola.ttf:textfile=%PTZ_PATH%:reload=1:fontsize=64:fontcolor=white:x=(w-text_w)/2:y=h-th-80:box=1:boxcolor=black@0.55:boxborderw=18:line_spacing=8 -c:v libx264 -preset ultrafast -tune zerolatency -b:v 4000k -g 30 -f rtsp -rtsp_transport tcp rtsp://localhost:8554/crane"
) else (
    :: Fallback — no text overlay, plain test pattern
    echo [INFO] Running without PTZ text overlay.
    start "FFmpeg — Fake Camera" cmd /k "ffmpeg -re -f lavfi -i testsrc2=size=1920x1080:rate=30 -c:v libx264 -preset ultrafast -tune zerolatency -b:v 4000k -g 30 -f rtsp -rtsp_transport tcp rtsp://localhost:8554/crane"
)

:: ── Window 3: PTZ mock ───────────────────────────────────────
echo Starting PTZ mock server...
start "PTZ Mock — Control Server" cmd /k "python "%~dp0ptz_mock.py""

echo.
echo  ============================================
echo   All services started.
echo.
echo   Wait ~5 sec, then open operator.html
echo   in Chrome or Edge.
echo.
echo   PTZ commands will appear burned into
echo   the video stream itself.
echo  ============================================
echo.
pause
