@echo off
REM Start the frontend and backend dev servers in separate cmd windows (Windows)
REM Run this from the repository root: start-dev.bat

REM Open a new terminal for frontend and run Vite
start "Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

REM Open a new terminal for backend and run nodemon
start "Backend" cmd /k "cd /d %~dp0backend && npm run dev"

REM This script uses `start` to open new terminals so logs remain visible.
REM Close each terminal to stop the corresponding server.
