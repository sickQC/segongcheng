param([switch]$History)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts/setup.ps1 first.' }
Push-Location $projectRoot
try {
    & $pythonPath -m ruff check --config ruff.toml backend scripts deploy
    if ($LASTEXITCODE -ne 0) { throw 'Python quality gate failed.' }
    $scanner = Join-Path $projectRoot '.local\tools\gitleaks-8.30.1\gitleaks.exe'
    if (-not (Test-Path -LiteralPath $scanner)) {
        throw 'Install the pinned scanner first: .\.venv\Scripts\python.exe scripts/install_quality_tools.py'
    }
    & $pythonPath scripts/check_secrets.py --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Scanner self-test failed; secret checking cannot be trusted.' }
    $scanArguments = @('scripts/check_secrets.py')
    if ($History) { $scanArguments += '--history' }
    & $pythonPath @scanArguments
    if ($LASTEXITCODE -ne 0) { throw 'Secret gate failed; see the sanitized report in .local/ci.' }
} finally { Pop-Location }
