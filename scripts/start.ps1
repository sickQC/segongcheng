$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonPath)) { throw 'Run scripts/setup.ps1 first.' }
if (-not (Test-Path (Join-Path $projectRoot 'frontend\dist\index.html'))) {
    throw 'Build the frontend first: cd frontend; npm ci; npm run build'
}
Push-Location (Join-Path $projectRoot 'backend')
try {
    & $pythonPath -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
    Write-Host 'Open http://127.0.0.1:8000 - press Ctrl+C to stop.'
    # Run a single worker for the local Sprint 0 demo.
    & $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port 8000
    if ($LASTEXITCODE -ne 0) { throw 'Server startup failed. Check whether port 8000 is occupied.' }
} finally { Pop-Location }
