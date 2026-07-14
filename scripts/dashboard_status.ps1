$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $repo '.tmp\dashboard.pid'
if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Output 'Dashboard status: no PID file'
    exit 1
}
$dashboardPid = [int](Get-Content -Raw -LiteralPath $pidFile).Trim()
$process = Get-Process -Id $dashboardPid -ErrorAction SilentlyContinue
if (-not $process) {
    Write-Output "Dashboard status: stopped (stale PID $dashboardPid)"
    exit 1
}
Write-Output "Dashboard status: running PID=$dashboardPid START=$($process.StartTime)"
Invoke-RestMethod -Uri 'http://127.0.0.1:8765/healthz' -TimeoutSec 5 | ConvertTo-Json
