param(
    [string]$NodePath = 'node',
    [switch]$SkipBuild,
    [switch]$RulesOnly,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$frontendRoot = Join-Path $projectRoot 'jianli'
$pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
$nextPath = Join-Path $frontendRoot 'node_modules\next\dist\bin\next'
$stateRoot = Join-Path $backendRoot '.tmp\local-run'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Backend dependencies missing. Follow backend/README.md first.' }
if (!(Test-Path -LiteralPath $nextPath)) { throw 'Frontend dependencies missing. Run npm ci in jianli/ first.' }
$nodeCommand = Get-Command $NodePath -ErrorAction Stop
$nodeExecutable = $nodeCommand.Source
if (!$nodeExecutable) { throw 'NodePath must resolve to a Node executable.' }
if (!(Test-Path -LiteralPath (Join-Path $backendRoot '.env'))) { throw 'Create backend/.env from .env.example first.' }
if ($CheckOnly) {
    & $pythonPath -c "import fastapi, sqlalchemy, httpx; print('Backend dependencies OK')"
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependencies failed.' }
    & $nodeExecutable --version
    if ($LASTEXITCODE -ne 0) { throw 'Node is unavailable.' }
    Write-Output 'Preflight passed; no services started.'
    exit 0
}
foreach ($port in @(3000, 8000)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $port is occupied. Stop the existing service before starting."
    }
}
New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
$statePath = Join-Path $stateRoot 'processes.json'
if (Test-Path -LiteralPath $statePath) { throw 'Existing local run record. Run Stop-Local.ps1 first.' }
$owned = @()
$previousExternal = $env:AI_EXTERNAL_ENABLED
try {
    Push-Location $backendRoot
    try {
        & docker compose up -d --wait postgres
        if ($LASTEXITCODE -ne 0) { throw 'Docker PostgreSQL did not start.' }
        & $pythonPath -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
    } finally { Pop-Location }
    if (!$SkipBuild) {
        Push-Location $frontendRoot
        try {
            & $nodeExecutable $nextPath build
            if ($LASTEXITCODE -ne 0) { throw 'Production build failed.' }
        } finally { Pop-Location }
    }
    if ($RulesOnly) { $env:AI_EXTERNAL_ENABLED = 'false' }
    $backendProcess = Start-Process -FilePath $pythonPath -ArgumentList '-m uvicorn app.main:app --host 127.0.0.1 --port 8000' -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $stateRoot 'backend.out.log') -RedirectStandardError (Join-Path $stateRoot 'backend.err.log')
    $owned += @{ Id = $backendProcess.Id; Started = $backendProcess.StartTime.ToUniversalTime().ToString('o'); Needle = $pythonPath }
    $owned | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $statePath -Encoding utf8
    $frontendProcess = Start-Process -FilePath $nodeExecutable -ArgumentList @(('"' + $nextPath + '"'), 'start', '-H', '127.0.0.1', '-p', '3000') -WorkingDirectory $frontendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $stateRoot 'frontend.out.log') -RedirectStandardError (Join-Path $stateRoot 'frontend.err.log')
    $owned += @{ Id = $frontendProcess.Id; Started = $frontendProcess.StartTime.ToUniversalTime().ToString('o'); Needle = $nextPath }
    $owned | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $statePath -Encoding utf8
    foreach ($url in @('http://127.0.0.1:8000/api/v1/health', 'http://127.0.0.1:3000')) {
        $ready = $false
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            try { $response = Invoke-WebRequest -Uri $url -TimeoutSec 2 -UseBasicParsing; $ready = $response.StatusCode -eq 200 } catch { $ready = $false }
            if ($ready) { break }
            Start-Sleep -Milliseconds 500
        }
        if (!$ready) { throw "Service failed health check: $url. See backend/.tmp/local-run logs." }
    }
    Write-Output 'CareerProof is ready at http://127.0.0.1:3000'
    Write-Output 'Stop using ./Stop-Local.ps1 -Database; no API key is printed or changed.'
} catch {
    if ($owned.Count -gt 0) { & (Join-Path $projectRoot 'Stop-Local.ps1') }
    throw
} finally { $env:AI_EXTERNAL_ENABLED = $previousExternal }
