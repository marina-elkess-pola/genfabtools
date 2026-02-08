# Start Vite dev server in the frontend folder (PowerShell)
# Usage: Right-click -> Run with PowerShell or from PowerShell: .\start-dev.ps1
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir
Write-Host "== Starting Vite dev server in: $scriptDir ==" -ForegroundColor Cyan
Write-Host "If port 5173 is in use, Vite will try the next available port. To force 5173, stop any process using it first." -ForegroundColor Yellow

# Check node_modules exists
if (-not (Test-Path "node_modules")) {
    Write-Host "node_modules not found. Running npm install..." -ForegroundColor Yellow
    npm install
}

# Start Vite, binding to localhost and port 5173 so the URL is stable
Write-Host "Running: npm run dev -- --host 127.0.0.1 --port 5173" -ForegroundColor Green
npm run dev -- --host 127.0.0.1 --port 5173
