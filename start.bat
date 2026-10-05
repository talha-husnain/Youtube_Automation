@echo off
title OpenShorts AI Video Generator & Editor
echo ========================================================
echo        OpenShorts + Custom Video Editing Engine
echo ========================================================
echo.
echo Select an option:
echo 1) Start Full Stack (Backend Python on :8000 + Frontend Vite on :5173) [Recommended]
echo 2) Start Backend API only (Python FastAPI on port 8000)
echo 3) Start Frontend Dashboard only (Vite on port 5173)
echo 4) Run Custom Anti-Copyright & Background Editor CLI
echo 5) Start with Docker Compose
echo 6) Exit
echo.
set /p opt="Enter choice [1-6]: "

if "%opt%"=="1" (
    echo Starting Backend in background...
    start "OpenShorts Backend API" cmd /k "cd /d %~dp0 && .venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8000"
    timeout /t 3 >nul
    echo Starting Frontend Dashboard...
    cd /d "%~dp0dashboard"
    npm run dev
) else if "%opt%"=="2" (
    echo Starting Backend API...
    cd /d "%~dp0"
    .venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8000
) else if "%opt%"=="3" (
    echo Starting Frontend Dashboard...
    cd /d "%~dp0dashboard"
    npm run dev
) else if "%opt%"=="4" (
    echo.
    set /p input_video="Enter input video path: "
    set /p output_video="Enter output video path: "
    set /p bg_style="Enter background style [keep/blur/solid] (default: blur): "
    if "%bg_style%"=="" set bg_style=blur
    cd /d "%~dp0"
    .venv\Scripts\python.exe custom_editor.py --input "%input_video%" --output "%output_video%" --speed 1.03 --bg %bg_style%
) else if "%opt%"=="5" (
    echo Starting Docker containers...
    cd /d "%~dp0"
    docker compose up --build
) else (
    echo Exiting.
)
pause
