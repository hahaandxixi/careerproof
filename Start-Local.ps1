param(
    [string]$NodePath = 'node',
    [ValidatePattern('^\.venv(?:-[a-z0-9-]+)?$')][string]$BackendVenv = '.venv',
    [ValidatePattern('^$|^[a-z0-9][a-z0-9-]{0,63}$')][string]$FrontendStage = '',
    [switch]$SkipBuild,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$frontendRoot = Join-Path $projectRoot 'jianli'
if ($FrontendStage) { $frontendRoot = Join-Path $backendRoot ".tmp\$FrontendStage" }
$venvRoot = Join-Path $backendRoot $BackendVenv
foreach ($directory in @($venvRoot, $frontendRoot)) {
    $item = Get-Item -LiteralPath $directory -ErrorAction Stop
    if (!$item.PSIsContainer -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw 'Startup runtime directories must be local directories, not reparse points.'
    }
}
$pythonPath = Join-Path $venvRoot 'Scripts\python.exe'
$nextPath = Join-Path $frontendRoot 'node_modules\next\dist\bin\next'
$stateRoot = Join-Path $backendRoot '.tmp\local-run'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Backend dependencies missing. Follow backend/README.md first.' }
if (!(Test-Path -LiteralPath $nextPath)) { throw 'Frontend dependencies missing. Run npm ci in jianli/ first.' }
$nodeCommand = Get-Command $NodePath -ErrorAction Stop
$nodeExecutable = $nodeCommand.Source
if (!$nodeExecutable) { throw 'NodePath must resolve to a Node executable.' }
Push-Location $backendRoot
try {
    & $pythonPath -m evals.verify_dependency_environment | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Selected backend runtime does not match current production dependency pins.' }
} finally { Pop-Location }
& $nodeExecutable (Join-Path $projectRoot 'scripts\dependencies\verify-frontend-runtime.mjs') --project-root $frontendRoot --expected-root (Join-Path $projectRoot 'jianli') | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Selected frontend runtime or source does not match the current lock/source.' }
if ($CheckOnly) {
    Write-Output 'Runtime/source preflight passed; no services, migrations, builds or model calls started.'
    exit 0
}
if ($SkipBuild -and !(Test-Path -LiteralPath (Join-Path $frontendRoot '.next\BUILD_ID'))) {
    throw 'No production build found. Run without -SkipBuild.'
}
$envPath = Join-Path $backendRoot '.env'
if (!(Test-Path -LiteralPath $envPath)) { throw 'Create backend/.env from .env.example first.' }
function Get-DotEnvValue([string]$Path, [string]$Name) {
    $escapedName = [regex]::Escape($Name)
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match "^\s*$escapedName\s*=\s*(.*)\s*$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return $null
}
$externalEnabled = Get-DotEnvValue $envPath 'AI_EXTERNAL_ENABLED'
$provider = Get-DotEnvValue $envPath 'AI_PROVIDER'
$apiKey = Get-DotEnvValue $envPath 'DEEPSEEK_API_KEY'
if ($externalEnabled -ne 'true' -or $provider -ne 'deepseek' -or [string]::IsNullOrWhiteSpace($apiKey)) {
    throw 'Local product startup requires DeepSeek in backend/.env. Rules are automatic fallback, not a selectable mode.'
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
$savedBackendOrigin = $env:BACKEND_ORIGIN
$savedNextDistDir = $env:NEXT_DIST_DIR
try {
    $env:BACKEND_ORIGIN = 'http://127.0.0.1:8000'
    $env:NEXT_DIST_DIR = '.next'
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
} finally {
    $env:BACKEND_ORIGIN = $savedBackendOrigin
    $env:NEXT_DIST_DIR = $savedNextDistDir
}
