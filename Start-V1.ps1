param([switch]$Stop)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\local-runtime.ps1')
$backend = Join-Path $PSScriptRoot 'backend'
$frontend = Join-Path $PSScriptRoot 'jianli'
$state = Join-Path $backend '.tmp\v1-run'
$statePath = Join-Path $state 'processes.json'
New-Item -ItemType Directory -Path $state -Force | Out-Null
$lock = $null
$saved = @{}
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
    $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    # One business configuration: backend/.env. The private runtime profile only
    # selects executables and the owned container; it holds no second AI/DB config.
    $envPath = Join-Path $backend '.env'
    $envJson = & $config.python -c 'import json,sys; from dotenv import dotenv_values; print(json.dumps(dotenv_values(sys.argv[1])))' $envPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not read the unified backend/.env.' }
    $appConfig = $envJson | ConvertFrom-Json
    if ($appConfig.AI_PROVIDER -ne 'deepseek' -or $appConfig.AI_EXTERNAL_ENABLED -ne 'true' -or [string]::IsNullOrWhiteSpace($appConfig.DEEPSEEK_API_KEY)) { throw 'V1 requires the configured real DeepSeek provider.' }
    if (!$appConfig.DATABASE_URL.EndsWith('/careerproof_v1')) { throw 'Refusing a source database as the unified target.' }
    $configHash = (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash + ':' + (Get-FileHash -LiteralPath $envPath -Algorithm SHA256).Hash
    $backendDigest = Get-LocalBackendDigest $backend
    $buildId = (Get-Content -LiteralPath (Join-Path $frontend '.next\BUILD_ID') -Raw).Trim()
    if ($previous -and @(Get-ValidatedLocalProcesses $previous $statePath).Count) {
        Assert-LocalReusableManifest $previous $statePath
        if ($previous.configHash -ne $configHash -or $previous.backendDigest -ne $backendDigest -or $previous.buildId -ne $buildId) { throw 'V1 code/config/build changed. Stop this owned run before restarting.' }
        Wait-LocalService 'http://127.0.0.1:8140/api/v1/health' 8140 $previous.processes[0]
        Wait-LocalService 'http://127.0.0.1:3140' 3140 $previous.processes[1]
        Write-Output 'V1 already ready at http://127.0.0.1:3140 (same owned services).'
        return
    }
    foreach ($port in @(3140, 8140)) {
        if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw "Port $port belongs to another run; nothing stopped." }
    }
    foreach ($property in $appConfig.PSObject.Properties) {
        $saved[$property.Name] = [Environment]::GetEnvironmentVariable($property.Name, 'Process')
        [Environment]::SetEnvironmentVariable($property.Name, [string]$property.Value, 'Process')
    }
    $saved['BACKEND_ORIGIN'] = $env:BACKEND_ORIGIN
    $env:BACKEND_ORIGIN = 'http://127.0.0.1:8140'
    Invoke-LocalNative 'docker' @('start', $config.container) | Out-Null
    Push-Location $backend
    try { Invoke-LocalNative $config.python @('-m', 'alembic', 'upgrade', 'head') }
    finally { Pop-Location }
    $manifest = @{schemaVersion=2; configHash=$configHash; backendDigest=$backendDigest; buildId=$buildId; sourceCommit=(& git -C $PSScriptRoot rev-parse HEAD); processes=@()}
    $api = Start-Process -FilePath $config.python -ArgumentList '-m uvicorn app.main:app --no-proxy-headers --host 127.0.0.1 --port 8140' -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $state 'api.stdout.log') -RedirectStandardError (Join-Path $state 'api.stderr.log')
    $manifest.processes += @{Id=$api.Id; Started=$api.StartTime.ToUniversalTime().ToString('o'); Needle=$config.python; Invocation='uvicorn app.main:app --no-proxy-headers --host 127.0.0.1 --port 8140'}
    Save-LocalRunManifest $statePath $manifest
    Wait-LocalService 'http://127.0.0.1:8140/api/v1/health' 8140 $manifest.processes[0]
    $next = Join-Path $frontend 'node_modules\next\dist\bin\next'
    $web = Start-Process -FilePath $config.node -ArgumentList @(('"'+$next+'"'), 'start', '-H', '127.0.0.1', '-p', '3140') -WorkingDirectory $frontend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $state 'web.stdout.log') -RedirectStandardError (Join-Path $state 'web.stderr.log')
    $manifest.processes += @{Id=$web.Id; Started=$web.StartTime.ToUniversalTime().ToString('o'); Needle=$next; Invocation=$next}
    Save-LocalRunManifest $statePath $manifest
    Wait-LocalService 'http://127.0.0.1:3140' 3140 $manifest.processes[1]
    Write-Output 'CareerProof V1 ready at http://127.0.0.1:3140; API 8140; unified data; real DeepSeek enabled.'
} finally {
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
    if ($lock) { $lock.Dispose() }
}
