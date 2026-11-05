param([switch]$Stop)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\local-runtime.ps1')
. (Join-Path $PSScriptRoot 'scripts\local-frontend-build.ps1')
$backend = Join-Path $PSScriptRoot 'backend'
$frontend = Join-Path $PSScriptRoot 'jianli'
$state = Join-Path $backend '.tmp\v1-run'
$statePath = Join-Path $state 'processes.json'
New-Item -ItemType Directory -Path $state -Force | Out-Null
$lock = $null
$saved = @{}
$createdRecords = @()
$publishedStateHash = $null
try {
    $lock = [IO.File]::Open((Join-Path $state 'launcher.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    $previous = Read-LocalRunManifest $statePath
    if ($Stop) {
        if ($previous) {
            Stop-ValidatedLocalProcesses $previous $statePath | Out-Null
            Remove-Item -LiteralPath $statePath
        }
        Write-Output 'V1 website stopped; database and materials retained.'
        return
    }
    $configPath = Join-Path $backend '.tmp\unified-runtime.private.json'
    if (!(Test-Path -LiteralPath $configPath)) { throw 'Local unified configuration missing. This launcher does not create or reset data.' }
    $raw = $null
    try { $raw = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 }
    catch { throw "Local unified configuration at $configPath could not be read. Confirm no services are live, then move the file aside manually; it was not removed automatically." }
    try { $config = $raw | ConvertFrom-Json }
    catch { throw "Local unified configuration at $configPath is unreadable JSON. Confirm no services are live, then move the file aside manually; it was not removed automatically." }
    $invalid = $true
    if ($config -is [System.Management.Automation.PSCustomObject]) {
        $invalid = @('python','node','container') | Where-Object { $p = $config.PSObject.Properties[$_]; (-not $p) -or ($p.Value -isnot [string]) -or ([string]::IsNullOrWhiteSpace($p.Value)) }
    }
    if ($null -eq $config -or $invalid) {
        throw "Local unified configuration at $configPath is structurally invalid: the runtime profile must be an object with python, node and container. Confirm no services are live, then move the file aside manually; it was not removed automatically."
    }
    # The accepted artifact is persistent configuration, not an inherited env
    # variable or the disposable process record. Validate before any native work.
    $build = Get-LocalFrontendBuild $frontend $config.frontendBuild
    # One business configuration: backend/.env. The private runtime profile only
    # selects executables, the owned container and accepted frontend artifact.
    # It holds no second AI/DB config.
    $envPath = Join-Path $backend '.env'
    $envJson = & $config.python -c 'import json,sys; from dotenv import dotenv_values; print(json.dumps(dotenv_values(sys.argv[1])))' $envPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not read the unified backend/.env.' }
    $appConfig = $envJson | ConvertFrom-Json
    if ($appConfig.AI_PROVIDER -ne 'deepseek' -or $appConfig.AI_EXTERNAL_ENABLED -ne 'true' -or [string]::IsNullOrWhiteSpace($appConfig.DEEPSEEK_API_KEY)) { throw 'V1 requires the configured real DeepSeek provider.' }
    if (!$appConfig.DATABASE_URL.EndsWith('/careerproof_v1')) { throw 'Refusing a source database as the unified target.' }
    $configHash = (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash + ':' + (Get-FileHash -LiteralPath $envPath -Algorithm SHA256).Hash
    $backendDigest = Get-LocalBackendDigest $backend
    $buildId = $build.BuildId
    $buildUrl = 'http://127.0.0.1:3140/_next/static/' + $buildId + '/_buildManifest.js'
    if ($previous -and @(Get-ValidatedLocalProcesses $previous $statePath).Count) {
        Assert-LocalReusableManifest $previous $statePath
        if ($previous.configHash -ne $configHash -or $previous.backendDigest -ne $backendDigest -or $previous.buildId -cne $buildId -or $previous.frontendDistDir -cne $build.DistDir -or $previous.frontendSourceCommit -cne $build.SourceCommit) { throw 'V1 code/config/build changed. Stop this owned run before restarting.' }
        Wait-LocalService 'http://127.0.0.1:8140/api/v1/ready' 8140 $previous.processes[0]
        Wait-LocalService $buildUrl 3140 $previous.processes[1]
        Write-Output "V1 already ready at http://127.0.0.1:3140 (same owned services; build $buildId)."
        return
    }
    foreach ($port in @(3140, 8140)) {
        if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw "Port $port belongs to another run; nothing stopped." }
    }
    foreach ($name in @('NEXT_DIST_DIR', 'BACKEND_ORIGIN') + @($appConfig.PSObject.Properties.Name)) {
        if (!$saved.ContainsKey($name)) { $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
    }
    foreach ($property in $appConfig.PSObject.Properties) {
        [Environment]::SetEnvironmentVariable($property.Name, [string]$property.Value, 'Process')
    }
    $env:NEXT_DIST_DIR = if ($build.DistDir -eq '.next') { $null } else { $build.DistDir }
    $env:BACKEND_ORIGIN = 'http://127.0.0.1:8140'
    Invoke-LocalNative 'docker' @('start', $config.container) | Out-Null
    Push-Location $backend
    try { Invoke-LocalNative $config.python @('-m', 'alembic', 'upgrade', 'head') }
    finally { Pop-Location }
    $manifest = @{schemaVersion=2; configHash=$configHash; backendDigest=$backendDigest; buildId=$buildId; frontendDistDir=$build.DistDir; frontendSourceCommit=$build.SourceCommit; sourceCommit=(& git -C $PSScriptRoot rev-parse HEAD); processes=@()}
    $api = Start-Process -FilePath $config.python -ArgumentList '-m uvicorn app.main:app --no-proxy-headers --host 127.0.0.1 --port 8140' -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $state 'api.stdout.log') -RedirectStandardError (Join-Path $state 'api.stderr.log')
    $apiRecord = @{Id=$api.Id; Started=$api.StartTime.ToUniversalTime().ToString('o'); Needle=$config.python; Invocation='uvicorn app.main:app --no-proxy-headers --host 127.0.0.1 --port 8140'}
    $createdRecords += $apiRecord
    $manifest.processes += $apiRecord
    Save-LocalRunManifest $statePath $manifest
    $publishedStateHash = (Get-FileHash -LiteralPath $statePath -Algorithm SHA256).Hash
    Wait-LocalService 'http://127.0.0.1:8140/api/v1/ready' 8140 $manifest.processes[0]
    $next = Join-Path $frontend 'node_modules\next\dist\bin\next'
    $web = Start-Process -FilePath $config.node -ArgumentList @(('"'+$next+'"'), 'start', '-H', '127.0.0.1', '-p', '3140') -WorkingDirectory $frontend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $state 'web.stdout.log') -RedirectStandardError (Join-Path $state 'web.stderr.log')
    $webRecord = @{Id=$web.Id; Started=$web.StartTime.ToUniversalTime().ToString('o'); Needle=$next; Invocation=$next}
    $createdRecords += $webRecord
    $manifest.processes += $webRecord
    Save-LocalRunManifest $statePath $manifest
    $publishedStateHash = (Get-FileHash -LiteralPath $statePath -Algorithm SHA256).Hash
    Wait-LocalService $buildUrl 3140 $manifest.processes[1]
    Write-Output "CareerProof V1 ready at http://127.0.0.1:3140; build $buildId; API 8140; unified data; real DeepSeek enabled."
} catch {
    $startupFailure = $_
    if ($createdRecords.Count) {
        # Never clean up a reused run or infer ownership from an occupied port.
        # Validate every newly created root/tree before the first stop.
        $createdManifest = @{schemaVersion=2; processes=@($createdRecords)}
        $cleanupComplete = $false
        try {
            Stop-ValidatedLocalProcesses $createdManifest $statePath | Out-Null
            if (@(Get-ValidatedLocalProcesses $createdManifest $statePath).Count) {
                throw 'Newly created processes have not yet confirmed exit.'
            }
            $cleanupComplete = $true
        } catch {
            Write-Warning "Startup cleanup could not confirm all new services stopped; existing recovery records retained. ($($_.Exception.Message))"
            # A failed second save may leave only the API in processes.json.
            # Preserve the complete in-memory identities in a new file without
            # overwriting an unknown/corrupt/changed main record.
            $recoveryPath = Join-Path $state ('startup-failed-' + [guid]::NewGuid().ToString('N') + '.json')
            try { Save-LocalRunManifest $recoveryPath $createdManifest }
            catch { Write-Warning "Could not save supplemental recovery identities for PIDs $($createdRecords.Id -join ', '): $($_.Exception.Message)" }
        }
        if ($cleanupComplete -and $publishedStateHash -and (Test-Path -LiteralPath $statePath)) {
            try {
                Assert-LocalStatePath $statePath
                if ((Get-FileHash -LiteralPath $statePath -Algorithm SHA256).Hash -ceq $publishedStateHash) {
                    Remove-Item -LiteralPath $statePath
                } else {
                    Write-Warning 'Startup cleanup preserved a process record changed since this attempt wrote it.'
                }
            } catch { Write-Warning "Startup cleanup preserved the process record: $($_.Exception.Message)" }
        }
    }
    throw $startupFailure
} finally {
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
    if ($lock) { $lock.Dispose() }
}
