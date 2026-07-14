$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Missing .venv. Create it and install the project first.'
}

$env:PYTHONPATH = Join-Path $repo 'src'
Push-Location $repo
try {
    # Refresh API, fallback-page, node-link, official-map, and mapping evidence first.
    & (Join-Path $PSScriptRoot 'validate_sources.ps1') | Out-Null

    # Exit 3 means the 48-hour/data-volume gate is still pending, not a pipeline failure.
    & $python -m taekbae finalize-snapshot
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $exitCode
