@echo off
echo ===================================================
echo Starting Arctiq Full Stack
echo ===================================================

echo [1/2] Launching Backend on http://localhost:8000...
start "Arctiq Backend" cmd /k "cd /d %~dp0backend && python -m uvicorn main:app --port 8000 --reload"

echo [2/2] Launching Frontend on http://localhost:5173...
start "Arctiq Frontend" cmd /k "cd /d %~dp0frontend && npm.cmd run dev"

echo.
echo Arctiq is now launching!
echo   - Web Dashboard: http://localhost:5173
echo   - API / Swagger: http://localhost:8000/docs
echo.
