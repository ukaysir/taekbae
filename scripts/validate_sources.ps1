$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
$output = Join-Path $repo 'outputs\tables\source_validation_runtime.json'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Missing .venv. Create it and install the project first.'
}
if (-not $env:DATA_GO_KR_SERVICE_KEY) {
    $env:DATA_GO_KR_SERVICE_KEY = [Environment]::GetEnvironmentVariable(
        'DATA_GO_KR_SERVICE_KEY',
        'User'
    )
}
if (-not $env:DATA_GO_KR_SERVICE_KEY) {
    throw 'DATA_GO_KR_SERVICE_KEY is not set.'
}

$env:PYTHONPATH = Join-Path $repo 'src'
Push-Location $repo
try {
    $trafficText = (& $python -m taekbae smoke-api --num-rows 10 2>&1 | Out-String)
    $trafficExit = $LASTEXITCODE
    $traffic = $trafficText | ConvertFrom-Json

    $weatherText = (& $python -m taekbae smoke-weather --station-id 133 --num-rows 100 2>&1 | Out-String)
    $weatherExit = $LASTEXITCODE
    $weather = $weatherText | ConvertFrom-Json

    $qualityText = (& $python -m taekbae quality 2>&1 | Out-String)
    $qualityExit = $LASTEXITCODE
    $quality = $qualityText | ConvertFrom-Json

    $nodeZip = Join-Path $repo 'data\external\NODELINKDATA_2024-11-29.zip'
    $nodeHash = if (Test-Path -LiteralPath $nodeZip) {
        (Get-FileHash -LiteralPath $nodeZip -Algorithm SHA256).Hash.ToLowerInvariant()
    } else {
        $null
    }

    $latestRun = $quality.recent_runs | Select-Object -First 1
    $report = [ordered]@{
        tested_at_kst = (Get-Date).ToString('o')
        credential = [ordered]@{
            environment_variable = 'DATA_GO_KR_SERVICE_KEY'
            present = [bool]$env:DATA_GO_KR_SERVICE_KEY
            value_logged = $false
        }
        sources = [ordered]@{
            daejeon_openapi = [ordered]@{
                dataset_id = '15157924'
                endpoint = 'https://apis.data.go.kr/6300000/rest/getTrafficInfoAll'
                exit_code = $trafficExit
                response = $traffic
                operational_usable = ($trafficExit -eq 0)
            }
            kma_asos_hourly = [ordered]@{
                dataset_id = '15057210'
                station_id = 133
                exit_code = $weatherExit
                response = $weather
                operational_usable = ($weatherExit -eq 0)
            }
            daejeon_tram_web = [ordered]@{
                zones = @(1, 12)
                exit_code = $qualityExit
                latest_run_status = $latestRun.status
                latest_observed_at_kst = $quality.overall.last_observed_at_kst
                snapshots = $quality.overall.source_snapshots
                records = $quality.overall.records
                segments = $quality.overall.segments
                operational_usable = ($qualityExit -eq 0 -and $latestRun.status -eq 'success')
            }
            standard_node_link = [ordered]@{
                version = '2024-11-29'
                file_present = [bool]$nodeHash
                sha256 = $nodeHash
                expected_sha256 = '4ddd6632756204c7fc8a429bfc57a91215f38138f1e78e65d65778e4b9187e90'
                hash_verified = ($nodeHash -eq '4ddd6632756204c7fc8a429bfc57a91215f38138f1e78e65d65778e4b9187e90')
            }
        }
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $output) -Force | Out-Null
    $report | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $output -Encoding utf8
    $report | ConvertTo-Json -Depth 20
} finally {
    Pop-Location
}
