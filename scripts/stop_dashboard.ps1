$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $repo '.tmp\dashboard.pid'
if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Output 'Dashboard is not running (no PID file).'
    exit 0
}
$dashboardPid = [int](Get-Content -Raw -LiteralPath $pidFile).Trim()
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$dashboardPid" -ErrorAction SilentlyContinue
if ($process -and $process.CommandLine -notmatch 'taekbae\s+serve') {
    throw "Refusing to stop PID $dashboardPid because it is not the taekbae dashboard"
}
if ($process) {
    Stop-Process -Id $dashboardPid -Force
    Write-Output "Dashboard stopped. PID=$dashboardPid"
} else {
    Write-Output "Dashboard was already stopped. Stale PID=$dashboardPid"
}
Remove-Item -LiteralPath $pidFile -Force
