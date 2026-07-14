$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $repo '.tmp\collector.pid'
if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Output 'Collector is not running (no PID file).'
    exit 0
}
$collectorPid = [int](Get-Content -Raw -LiteralPath $pidFile).Trim()
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$collectorPid" -ErrorAction SilentlyContinue
if (-not $process) {
    Remove-Item -LiteralPath $pidFile
    Write-Output "Removed stale PID file for $collectorPid."
    exit 0
}
if ($process.CommandLine -notmatch 'taekbae.+collect-daemon') {
    throw "PID $collectorPid does not look like the taekbae collector; refusing to stop it."
}
Stop-Process -Id $collectorPid
Remove-Item -LiteralPath $pidFile
Write-Output "Collector stopped. PID=$collectorPid"
