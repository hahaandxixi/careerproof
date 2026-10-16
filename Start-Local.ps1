param(
    [string]$NodePath = 'node',
    [ValidatePattern('^auto$|^\.venv(?:-[a-z0-9-]+)?$')][string]$BackendVenv = 'auto',
    [ValidatePattern('^$|^[a-z0-9][a-z0-9-]{0,63}$')][string]$FrontendStage = 'auto',
    [switch]$SkipBuild,
    [switch]$Rebuild,
    [switch]$BuildOnly,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
. (Join-Path $projectRoot 'scripts\local-runtime.ps1')
if ($SkipBuild -and $Rebuild) { throw 'Choose -SkipBuild or -Rebuild, not both.' }
$nodeCommand = Get-Command $NodePath -ErrorAction Stop
$nodeExecutable = $nodeCommand.Source
if (!$nodeExecutable) { throw 'NodePath must resolve to a Node executable.' }
$backendCandidates = @($BackendVenv)
if ($BackendVenv -eq 'auto') {
    $backendCandidates = @('.venv') + @(Get-ChildItem -LiteralPath $backendRoot -Directory -Filter '.venv-*' | Sort-Object Name | Select-Object -ExpandProperty Name)
}
$backendVerified = $false
foreach ($candidate in $backendCandidates) {
    if ($candidate -notmatch '^\.venv(?:-[a-z0-9-]+)?$') { continue }
    $directory = Join-Path $backendRoot $candidate
    if (!(Test-Path -LiteralPath $directory)) { continue }
    if ((Get-Item -LiteralPath $directory).Attributes -band [System.IO.FileAttributes]::ReparsePoint) { continue }
    $pythonCandidate = Join-Path $directory 'Scripts\python.exe'
    if (!(Test-Path -LiteralPath $pythonCandidate)) { continue }
    Push-Location $backendRoot
    $probeErrorAction = $ErrorActionPreference
    try { $ErrorActionPreference = 'Continue'; $metadata = & $pythonCandidate -m evals.verify_dependency_environment 2>&1; $verified = $LASTEXITCODE -eq 0 }
    finally { $ErrorActionPreference = $probeErrorAction; Pop-Location }
    if ($verified) { $BackendVenv = $candidate; $backendMetadata = $metadata | ConvertFrom-Json; $backendVerified = $true; break }
}
if (!$backendVerified) { throw 'No selected local Python environment matches current dependency pins. Install backend dependencies or select -BackendVenv explicitly.' }
$frontendCandidates = @($FrontendStage)
if ($FrontendStage -eq 'auto') {
    $frontendCandidates = @('') + @(Get-ChildItem -LiteralPath (Join-Path $backendRoot '.tmp') -Directory -Filter 'dep-frontend-*' -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -ExpandProperty Name)
}
$frontendVerified = $false
foreach ($candidate in $frontendCandidates) {
    $directory = if ($candidate) { Join-Path $backendRoot ".tmp\$candidate" } else { Join-Path $projectRoot 'jianli' }
    if (!(Test-Path -LiteralPath $directory) -or ((Get-Item -LiteralPath $directory).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) { continue }
    $probeErrorAction = $ErrorActionPreference
    try { $ErrorActionPreference = 'Continue'; $metadata = & $nodeExecutable (Join-Path $projectRoot 'scripts\dependencies\verify-frontend-runtime.mjs') --project-root $directory --expected-root (Join-Path $projectRoot 'jianli') 2>&1; $verified = $LASTEXITCODE -eq 0 }
    finally { $ErrorActionPreference = $probeErrorAction }
    if ($verified) { $FrontendStage = $candidate; $frontendMetadata = $metadata | ConvertFrom-Json; $frontendVerified = $true; break }
}
if (!$frontendVerified) { throw 'No selected frontend matches current lock and source. Run npm ci or select an up-to-date -FrontendStage.' }
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
Write-Output "Verified runtime: backend $BackendVenv; frontend $frontendRoot"
if ($CheckOnly) {
    Write-Output 'Runtime/source preflight passed; no services, migrations, builds or model calls started.'
    return
}
$cacheScript = Join-Path $projectRoot 'scripts\local-build-cache.mjs'
$buildStamp = Join-Path $stateRoot 'frontend-build.json'
$buildState = & $nodeExecutable $cacheScript inspect $frontendRoot $buildStamp | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Could not fingerprint the production build.' }
if ($SkipBuild -and !$buildState.reusable) { throw 'No verified current production build. Run without -SkipBuild.' }
$envPath = Join-Path $backendRoot '.env'
if (!$BuildOnly -and !(Test-Path -LiteralPath $envPath)) { throw 'Create backend/.env from .env.example first.' }
$externalEnabled = Get-LocalEnvValue $envPath 'AI_EXTERNAL_ENABLED'
$provider = Get-LocalEnvValue $envPath 'AI_PROVIDER'
$apiKey = Get-LocalEnvValue $envPath 'DEEPSEEK_API_KEY'
if (!$BuildOnly -and ($externalEnabled -ne 'true' -or $provider -ne 'deepseek' -or [string]::IsNullOrWhiteSpace($apiKey))) {
    throw 'Local product startup requires DeepSeek in backend/.env. Rules are automatic fallback, not a selectable mode.'
}
New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
$statePath = Join-Path $stateRoot 'processes.json'
$launchLock = $null
$owned = @()
$savedBackendOrigin = $env:BACKEND_ORIGIN
$savedNextDistDir = $env:NEXT_DIST_DIR
try {
    try { $launchLock = [System.IO.File]::Open((Join-Path $stateRoot 'launcher.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
    catch { throw 'Another local launch/stop is in progress. Wait for it to finish.' }
    $configHash = Get-LocalConfigDigest $envPath
    $backendDigest = Get-LocalBackendDigest $backendRoot
    $existing = Read-LocalRunManifest $statePath
    if ($null -ne $existing) {
        $live = @(Get-ValidatedLocalProcesses $existing $statePath)
        if ($live.Count) {
            if ($BuildOnly) { throw 'Stop the owned local run before rebuilding its frontend.' }
            Assert-LocalReusableManifest $existing $statePath
            if ($Rebuild -or $existing.backendVenv -ne $BackendVenv -or $existing.backendDigest -ne $backendDigest -or $existing.frontendRoot -ne $frontendRoot -or $existing.configHash -ne $configHash -or !$buildState.reusable) { throw 'Existing run differs from the selected code/runtime/config/build. Stop-Local.ps1, then start again.' }
            Wait-LocalService 'http://127.0.0.1:8000/api/v1/health' 8000 $existing.processes[0]
            Wait-LocalService 'http://127.0.0.1:3000' 3000 $existing.processes[1]
            Write-Output 'Existing owned CareerProof services are healthy; reused without migration or rebuild.'
            return
        }
        Remove-Item -LiteralPath $statePath -Force
    }
    foreach ($port in @(3000, 8000)) {
        if (!$BuildOnly -and (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) { throw "Port $port belongs to another run. No process was stopped." }
    }
    if (!$BuildOnly) {
        $probeErrorAction = $ErrorActionPreference
        try { $ErrorActionPreference = 'Continue'; $dockerStatus = & docker info --format '{{.ServerVersion}}' 2>&1; $dockerReady = $LASTEXITCODE -eq 0 }
        finally { $ErrorActionPreference = $probeErrorAction }
        if (!$dockerReady) { throw 'Docker Engine is unavailable. Start Docker Desktop using its desktop icon, then retry.' }
    }
    $env:BACKEND_ORIGIN = 'http://127.0.0.1:8000'
    # next.config treats an explicit override as an isolated directory; unset
    # it to select the normal .next default and avoid inheriting E2E overrides.
    Remove-Item Env:NEXT_DIST_DIR -ErrorAction SilentlyContinue
    if ($Rebuild -or !$buildState.reusable) {
        Write-Output 'Building changed frontend (production)...'
        Push-Location $frontendRoot
        try { Invoke-LocalNative $nodeExecutable @($nextPath, 'build') }
        finally { Pop-Location }
        & $nodeExecutable $cacheScript record $frontendRoot $buildStamp | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Could not record successful production build.' }
    } else { Write-Output 'Reusing verified unchanged production build.' }
    if ($BuildOnly) { Write-Output 'Production build ready; no Docker, migrations, services, seeding or model calls started.'; return }
    Push-Location $backendRoot
    try {
        Invoke-LocalNative 'docker' @('compose', 'up', '-d', '--wait', 'postgres')
        Invoke-LocalNative $pythonPath @('-m', 'alembic', 'upgrade', 'head')
    } finally { Pop-Location }
    $manifest = @{ schemaVersion = 2; backendVenv = $BackendVenv; backendDigest = $backendDigest; frontendRoot = $frontendRoot; configHash = $configHash; createdAt = (Get-Date).ToUniversalTime().ToString('o'); processes = @() }
    $backendProcess = Start-Process -FilePath $pythonPath -ArgumentList '-m uvicorn app.main:app --no-proxy-headers --host 127.0.0.1 --port 8000' -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $stateRoot 'backend.out.log') -RedirectStandardError (Join-Path $stateRoot 'backend.err.log')
    $owned += @{ Id = $backendProcess.Id; Started = $backendProcess.StartTime.ToUniversalTime().ToString('o'); Needle = $pythonPath; Invocation = 'uvicorn app.main:app --no-proxy-headers --host 127.0.0.1 --port 8000' }
    $manifest.processes = @($owned); Save-LocalRunManifest $statePath $manifest
    Wait-LocalService 'http://127.0.0.1:8000/api/v1/health' 8000 $owned[0]
    $frontendProcess = Start-Process -FilePath $nodeExecutable -ArgumentList @(('"' + $nextPath + '"'), 'start', '-H', '127.0.0.1', '-p', '3000') -WorkingDirectory $frontendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $stateRoot 'frontend.out.log') -RedirectStandardError (Join-Path $stateRoot 'frontend.err.log')
    $owned += @{ Id = $frontendProcess.Id; Started = $frontendProcess.StartTime.ToUniversalTime().ToString('o'); Needle = $nextPath; Invocation = $nextPath }
    $manifest.processes = @($owned); Save-LocalRunManifest $statePath $manifest
    Wait-LocalService 'http://127.0.0.1:3000' 3000 $owned[1]
    Write-Output 'CareerProof is ready at http://127.0.0.1:3000'
    Write-Output 'Stop website: ./Stop-Local.ps1. Stop PostgreSQL too: add -Database.'
} catch {
    $originalError = $_
    if ($launchLock) { $launchLock.Dispose(); $launchLock = $null }
    if ($owned.Count -gt 0) { Invoke-LocalCleanupSafely { & (Join-Path $projectRoot 'Stop-Local.ps1') } }
    throw $originalError
} finally {
    $env:BACKEND_ORIGIN = $savedBackendOrigin
    $env:NEXT_DIST_DIR = $savedNextDistDir
    if ($launchLock) { $launchLock.Dispose() }
}
