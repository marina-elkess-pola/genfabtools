Quick local dev helper for the frontend

Files:

- start-dev.ps1  -> PowerShell script that starts the Vite dev server (binds to 127.0.0.1:5173)
- start-dev.bat  -> Windows cmd script to start the dev server

How to start (PowerShell):

1. Open PowerShell and cd into the frontend folder:
   cd "C:\Users\Personal\OneDrive\Desktop\Marina\pytho\website\occupant_calculator\frontend"
2. Run the helper (shows logs):
   .\start-dev.ps1

How to start (cmd):

1. Open cmd and cd into frontend folder:
   cd /d "C:\Users\Personal\OneDrive\Desktop\Marina\pytho\website\occupant_calculator\frontend"
2. Run:
   start-dev.bat

Common checks and fixes

- If the page says "localhost page can’t be found":
  - Make sure the script is running and shows "VITE v" output in the terminal.
  - The scripts bind to 127.0.0.1:5173. Open <http://127.0.0.1:5173/> in your browser.
- If Vite reports "Port 5173 is in use" it will try another port. To force 5173:
  1. Find the process using the port (PowerShell):
     Get-NetTCPConnection -LocalPort 5173 | Format-Table -Auto
     or
     netstat -ano | findstr ":5173"
  2. Kill the PID (cmd):
     taskkill /PID <pid> /F
- Quick port-check in PowerShell:
  (Invoke-WebRequest -UseBasicParsing -Uri '<http://127.0.0.1:5173/>' -Method GET -TimeoutSec 3 -ErrorAction SilentlyContinue).StatusCode

If problems persist

- Run `npm install` inside `frontend` to ensure dependencies are installed.
- If you see "Invalid hook call" errors in the browser console, let me know and I will continue debugging React duplication / bundle issues.

If you'd like, I can also start the server for you now and paste the terminal output (if you allow me to run commands).
