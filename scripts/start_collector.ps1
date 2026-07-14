$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Missing .venv. Run: python -m venv .venv; .\.venv\Scripts\python -m pip install -e .'
}
$tmp = Join-Path $repo '.tmp'
$logs = Join-Path $repo 'outputs\logs'
New-Item -ItemType Directory -Force -Path $tmp, $logs | Out-Null
$pidFile = Join-Path $tmp 'collector.pid'
if (Test-Path -LiteralPath $pidFile) {
    $oldPid = (Get-Content -Raw -LiteralPath $pidFile).Trim()
    if ($oldPid -and (Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue)) {
        throw "Collector already appears to be running with PID $oldPid"
    }
}
$env:PYTHONPATH = Join-Path $repo 'src'
$userKey = [Environment]::GetEnvironmentVariable('DATA_GO_KR_SERVICE_KEY', 'User')
if ($userKey) { $env:DATA_GO_KR_SERVICE_KEY = $userKey }
$stdout = Join-Path $logs 'collector.stdout.log'
$stderr = Join-Path $logs 'collector.stderr.log'
$process = Start-Process -FilePath $python `
    -ArgumentList @('-m','taekbae','collect-daemon','--zones','1,12','--interval','600') `
    -WorkingDirectory $repo -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr
Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ascii
Write-Output "Collector started. PID=$($process.Id)"
