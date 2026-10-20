param([switch]$Postgres)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$previousPath = $env:PATH
$localNode = Join-Path $projectRoot '.local\node-v22.20.0-win-x64'
if (Test-Path (Join-Path $localNode 'node.exe')) { $env:PATH = $localNode + ';' + $env:PATH }
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$testDirectory = Join-Path $projectRoot ('.local\pytest-' + [guid]::NewGuid().ToString('N'))
$previousPostgresFlag = $env:RUN_POSTGRES_TESTS
try {
    if ($Postgres) { $env:RUN_POSTGRES_TESTS = '1' }
    Push-Location $projectRoot
    try {
        & $pythonPath -m pytest backend/tests -q --tb=short -p no:cacheprovider "--basetemp=$testDirectory"
        if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
    } finally { Pop-Location }
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
} finally { $env:RUN_POSTGRES_TESTS = $previousPostgresFlag; $env:PATH = $previousPath }
