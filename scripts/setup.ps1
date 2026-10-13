$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path '.venv\Scripts\python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Failed to create the Python virtual environment.' }
    }
    & '.\.venv\Scripts\python.exe' -m pip install -r backend/requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Locked backend dependency installation failed.' }
    & '.\.venv\Scripts\python.exe' -m pip install --no-deps -e './backend[dev]'
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
    Push-Location frontend
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
    Write-Host 'Setup complete. Run: powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1'
} finally { Pop-Location }
