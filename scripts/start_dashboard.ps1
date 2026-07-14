param(
    [string]$BindHost = '127.0.0.1',
    [int]$Port = 8765
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Missing .venv. Create it and install the project first.'
}
$tmp = Join-Path $repo '.tmp'
$logs = Join-Path $repo 'outputs\logs'
New-Item -ItemType Directory -Force -Path $tmp, $logs | Out-Null
$pidFile = Join-Path $tmp 'dashboard.pid'
if (Test-Path -LiteralPath $pidFile) {
    $oldPid = (Get-Content -Raw -LiteralPath $pidFile).Trim()
    if ($oldPid -and (Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue)) {
        throw "Dashboard already appears to be running with PID $oldPid"
    }
}
$env:PYTHONPATH = Join-Path $repo 'src'
$env:PYTHONUTF8 = '1'
$stdout = Join-Path $logs 'dashboard.stdout.log'
$stderr = Join-Path $logs 'dashboard.stderr.log'
$process = Start-Process -FilePath $python `
    -ArgumentList @('-m','taekbae','serve','--host',$BindHost,'--port',[string]$Port) `
    -WorkingDirectory $repo -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr
Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ascii
Write-Output "Dashboard started. PID=$($process.Id) URL=http://${BindHost}:$Port"
