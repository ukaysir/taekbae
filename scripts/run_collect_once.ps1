$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Missing .venv. Run: python -m venv .venv; .\.venv\Scripts\python -m pip install -e .'
}
$env:PYTHONPATH = Join-Path $repo 'src'
Push-Location $repo
try {
    & $python -m taekbae collect-djtram --zones 1,12
} finally {
    Pop-Location
}
