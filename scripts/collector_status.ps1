$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $repo '.tmp\collector.pid'
if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Output 'Collector status: no PID file'
    exit 1
}
$collectorPid = [int](Get-Content -Raw -LiteralPath $pidFile).Trim()
$process = Get-Process -Id $collectorPid -ErrorAction SilentlyContinue
if (-not $process) {
    Write-Output "Collector status: stopped (stale PID $collectorPid)"
    exit 1
}
Write-Output "Collector status: running PID=$collectorPid START=$($process.StartTime)"
$python = Join-Path $repo '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $repo 'src'
Push-Location $repo
try { & $python -m taekbae quality } finally { Pop-Location }
