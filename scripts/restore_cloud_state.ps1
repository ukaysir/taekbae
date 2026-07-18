param(
    [string]$Repository = 'ukaysir/taekbae',
    [string]$Release = 'cloud-collector-state'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$tmp = Join-Path $repo '.tmp'

foreach ($pidName in @('collector.pid', 'dashboard.pid')) {
    $pidPath = Join-Path $tmp $pidName
    if (Test-Path -LiteralPath $pidPath) {
        throw "Refusing to restore while $pidPath exists. Stop the local process first."
    }
}

$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) {
    throw 'GitHub CLI (gh) is required. Install it and run gh auth login first.'
}

& $gh.Source auth status --hostname github.com 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'GitHub CLI is not authenticated. Run gh auth login first.'
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$restoreRoot = Join-Path $tmp "cloud-restore\$stamp"
$archiveDir = Join-Path $restoreRoot 'archive'
$extractDir = Join-Path $restoreRoot 'extracted'
$backupDir = Join-Path $restoreRoot 'backup'
New-Item -ItemType Directory -Force -Path $archiveDir, $extractDir | Out-Null

$assetName = $null
foreach ($candidate in @('collector-state.tar.gz', 'collector-state.previous.tar.gz')) {
    & $gh.Source release download $Release `
        --repo $Repository `
        --pattern $candidate `
        --dir $archiveDir 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $assetName = $candidate
        break
    }
}
if (-not $assetName) {
    throw "Neither collector state asset could be downloaded from $Repository release $Release."
}

$archive = Join-Path $archiveDir $assetName
$releaseJson = (& $gh.Source release view $Release `
    --repo $Repository `
    --json assets 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) {
    throw "Could not read release metadata for $Release."
}
$releaseInfo = $releaseJson | ConvertFrom-Json
$asset = $releaseInfo.assets | Where-Object { $_.name -eq $assetName } | Select-Object -First 1
if (-not $asset -or [string]$asset.digest -notmatch '^sha256:([0-9a-fA-F]{64})$') {
    throw "Release asset $assetName does not expose a valid SHA-256 digest."
}
$expectedHash = $Matches[1].ToLowerInvariant()
$actualHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedHash) {
    throw "Collector state SHA-256 mismatch: expected $expectedHash, got $actualHash."
}

& tar -xzf $archive -C $extractDir
if ($LASTEXITCODE -ne 0) {
    throw "Could not extract collector state archive $archive."
}

$sourceRaw = Join-Path $extractDir 'data\raw\djtram_web'
$sourceDb = Join-Path $extractDir 'data\processed\traffic.sqlite'
if (-not (Test-Path -LiteralPath $sourceRaw -PathType Container)) {
    throw 'Collector state archive is missing data/raw/djtram_web.'
}
if (-not (Test-Path -LiteralPath $sourceDb -PathType Leaf)) {
    throw 'Collector state archive is missing data/processed/traffic.sqlite.'
}

$destinationRaw = Join-Path $repo 'data\raw\djtram_web'
$destinationDb = Join-Path $repo 'data\processed\traffic.sqlite'
$backupRawParent = Join-Path $backupDir 'data\raw'
$backupDbParent = Join-Path $backupDir 'data\processed'

if (Test-Path -LiteralPath $destinationRaw) {
    New-Item -ItemType Directory -Force -Path $backupRawParent | Out-Null
    Copy-Item -LiteralPath $destinationRaw -Destination $backupRawParent -Recurse
}
if (Test-Path -LiteralPath $destinationDb) {
    New-Item -ItemType Directory -Force -Path $backupDbParent | Out-Null
    Copy-Item -LiteralPath $destinationDb -Destination $backupDbParent
}

New-Item -ItemType Directory -Force -Path $destinationRaw | Out-Null
Get-ChildItem -LiteralPath $sourceRaw -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $destinationRaw -Recurse -Force
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destinationDb) | Out-Null
Copy-Item -LiteralPath $sourceDb -Destination $destinationDb -Force

$requiredExternal = @(
    'data\external\NODELINKDATA_2024-11-29.zip',
    'data\external\nodelink_2024_11_29',
    'data\external\sbiz_stores_20260331.zip',
    'data\external\sbiz_stores_daejeon_202603.csv'
)
$missingExternal = @($requiredExternal | Where-Object {
    -not (Test-Path -LiteralPath (Join-Path $repo $_))
})

Write-Output "Cloud collector state restored from $assetName."
Write-Output "Archive SHA-256: $actualHash"
Write-Output "Restore workspace: $restoreRoot"
if (Test-Path -LiteralPath $backupDir) {
    Write-Output "Previous local state backup: $backupDir"
}
if ($missingExternal.Count -gt 0) {
    Write-Warning ('Finalization still requires these intentionally untracked external assets: ' + ($missingExternal -join ', '))
}
Write-Output 'Next check: .\.venv\Scripts\python.exe -m taekbae quality'
