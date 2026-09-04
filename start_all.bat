@echo off
echo ===================================================
echo Starting ColdSense Full Stack
echo ===================================================

echo [1/2] Launching Backend on http://localhost:8000...
start "ColdSense Backend" cmd /k "cd /d %~dp0backend && python -m uvicorn main:app --port 8000 --reload"

echo [2/2] Launching Frontend on http://localhost:5173...
start "ColdSense Frontend" cmd /k "cd /d %~dp0frontend && npm.cmd run dev"

echo.
echo ColdSense is now launching!
echo   - Web Dashboard: http://localhost:5173
echo   - API / Swagger: http://localhost:8000/docs
echo.
