@echo off
REM Start Vite dev server in frontend (Windows cmd)
REM Usage: double-click this file or run from cmd: start-dev.bat
pushd "%~dp0"
echo == Starting Vite dev server in: %CD% ==
echo If port 5173 is in use, Vite will try another port. To force 5173, stop the process using it first.
IF NOT EXIST node_modules (
  echo node_modules not found. Running npm install...
  npm install || goto :EOF
)
echo Running: npm run dev -- --host 127.0.0.1 --port 5173
npm run dev -- --host 127.0.0.1 --port 5173
popd
