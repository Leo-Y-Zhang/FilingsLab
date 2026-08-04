@echo off
title FilingsLab
cd /d "%~dp0"

echo.
echo  ==========================================
echo   FilingsLab  ^|  Starting up...
echo  ==========================================
echo.

:: ── Auto-start Docker Desktop if not running ─────────────────────────────────
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready

echo  [DOCKER] Docker Desktop not running. Starting it now...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
echo  [DOCKER] Waiting for Docker to be ready (up to 60 seconds)...

:wait_loop
timeout /t 4 /nobreak >nul
docker info >nul 2>&1
if errorlevel 1 goto wait_loop

:docker_ready
echo  [OK] Docker Desktop is ready.

:: ── One-time Kronos setup ─────────────────────────────────────────────────────
if exist "backend\kronos_lib\" goto kronos_done

echo.
echo  [SETUP] Kronos AI not found. Running one-time setup...
echo          This downloads ~50 MB of model code. Only happens once.
echo.
python setup_kronos.py
if errorlevel 1 (
    echo.
    echo  [WARNING] Kronos setup failed. FilingsLab will still work,
    echo            but the Forecast page will show a setup notice.
    echo.
) else (
    echo.
    echo  [OK] Kronos setup complete.
)

:kronos_done
echo  [OK] Kronos ready.

:: ── Launch ────────────────────────────────────────────────────────────────────
echo.
echo  [LAUNCH] Starting FilingsLab via Docker Compose...
echo           Open your browser to: http://localhost
echo           (ready when you see "Application startup complete")
echo.

docker compose up --build

pause
