# Isolated E2E environment (E2E-01): cp_e2e_<RunId> database, ports 8001/3001,
# independent storage directory and Next build directory, AI forced to mock.
# Review-gated: creating the cp_e2e_ database, running Alembic and starting the
# services only happen when this script is executed after Codex sign-off.
# Existing services on 8000/3000, the careerproof database and Docker volumes are
# never touched; connection strings and passwords are never printed.
param(
    [Parameter(Mandatory = $true)][string]$RunId,
    [ValidatePattern('^\.venv(?:-[a-z0-9-]+)?$')][string]$BackendVenv = '.venv',
    [ValidatePattern('^$|^[a-z0-9][a-z0-9-]{0,63}$')][string]$FrontendStage = '',
    [switch]$SkipBuild,
    [switch]$SkipSeed,
    [switch]$SyntheticVerification,
    [switch]$ActivateSyntheticBudget,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
if ($ActivateSyntheticBudget -and !$SyntheticVerification) {
    throw 'Synthetic budget activation requires the synthetic verification entry point.'
}
$repoRoot = Split-Path $PSScriptRoot -Parent
$backendRoot = Join-Path $repoRoot 'backend'
$frontendRoot = Join-Path $repoRoot 'jianli'
if ($FrontendStage) {
    $frontendRoot = Join-Path $backendRoot ".tmp\$FrontendStage"
    if (!(Test-Path -LiteralPath $frontendRoot) -or ((Get-Item -LiteralPath $frontendRoot).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw 'The selected frontend stage must be a local existing backend/.tmp directory, not a reparse point.'
    }
}
$venvRoot = Join-Path $backendRoot $BackendVenv
if ((Test-Path -LiteralPath $venvRoot) -and ((Get-Item -LiteralPath $venvRoot).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
    throw 'The selected E2E virtual environment must be a local backend directory, not a reparse point.'
}
$pythonPath = Join-Path $venvRoot 'Scripts\python.exe'
$nextPath = Join-Path $frontendRoot 'node_modules\next\dist\bin\next'
$stateRoot = Join-Path $backendRoot '.tmp\e2e-run'
$statePath = Join-Path $stateRoot "processes-$RunId.json"
$backendPort = 8001
$frontendPort = 3001
$backendTarget = if ($SyntheticVerification) { 'evals.e2e_verification:create_app --factory' } else { 'app.main:app' }
$backendArguments = "-m uvicorn $backendTarget --host 127.0.0.1 --port $backendPort"

if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Backend dependencies missing. Follow backend/README.md first.' }
if (!(Test-Path -LiteralPath $nextPath)) { throw 'Frontend dependencies missing. Run npm ci in jianli/ first.' }
# Run before any database connection, migration, process or fixture creation.
Push-Location $backendRoot
try {
    $runtimeJson = & $pythonPath -m evals.verify_dependency_environment
    if ($LASTEXITCODE -ne 0) { throw 'Selected backend interpreter does not match current production dependency pins.' }
    $backendRuntime = $runtimeJson | ConvertFrom-Json
} finally { Pop-Location }
# Validate the run id before it is ever concatenated into a path.
if ($RunId -notmatch '^[a-z0-9][a-z0-9-]{0,31}$') { throw 'RunId must match [a-z0-9][a-z0-9-]{0,31}.' }
$nodeExecutable = (Get-Command 'node' -ErrorAction Stop).Source
if (!$nodeExecutable) { throw 'Node is unavailable.' }
$frontendRuntimeJson = & $nodeExecutable (Join-Path $PSScriptRoot 'dependencies\verify-frontend-runtime.mjs') --project-root $frontendRoot --expected-root (Join-Path $repoRoot 'jianli')
if ($LASTEXITCODE -ne 0) { throw 'Selected frontend runtime or source does not match the current manifest/lock/source.' }
$frontendRuntime = $frontendRuntimeJson | ConvertFrom-Json

# E2E_DATABASE_URL is read from the environment only; it is validated here and never
# printed. The Python seeder enforces the same guard independently.
$databaseUrl = $env:E2E_DATABASE_URL
if (!$databaseUrl) { throw 'Set E2E_DATABASE_URL (postgresql+asyncpg://...@127.0.0.1:5432/cp_e2e_<RunId>) first; it stays in the environment and is never printed.' }
if ($databaseUrl -notmatch '^postgresql\+asyncpg://[^@]+@(127\.0\.0\.1|localhost):(\d+)/([^/?]+)$') {
    throw 'E2E_DATABASE_URL must be postgresql+asyncpg://<user>:<pass>@127.0.0.1:<port>/<db> (loopback only, percent-encode special characters in the password).'
}
$databaseName = $Matches[3]
if ($databaseName -notmatch '^cp_e2e_[a-z0-9][a-z0-9-]{0,62}$') { throw "E2E database name must match cp_e2e_[a-z0-9-]; refusing '$databaseName'." }
if ($databaseName -ne ('cp_e2e_' + $RunId)) { throw "E2E database name must be cp_e2e_$RunId for this run." }

# Storage isolation is separate from database isolation: only the gitignored
# backend\.tmp tree is accepted, so the business storage directory and any path
# outside the repo are refused.
if ($env:E2E_STORAGE_DIR) {
    $storageDir = [System.IO.Path]::GetFullPath($env:E2E_STORAGE_DIR)
} else {
    $storageDir = [System.IO.Path]::GetFullPath((Join-Path $backendRoot ".tmp\e2e-storage\$RunId"))
}
$tmpRoot = [System.IO.Path]::GetFullPath((Join-Path $backendRoot '.tmp\'))
if (!$storageDir.StartsWith($tmpRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "E2E storage must stay under $tmpRoot (gitignored); refusing $storageDir."
}
if ($storageDir.StartsWith((Join-Path $backendRoot 'storage\'), [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'E2E storage must not be the business storage directory backend\storage.'
}

foreach ($port in @($backendPort, $frontendPort)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $port is occupied. Existing services are preserved; stop the other service or pick another run."
    }
}
if (Test-Path -LiteralPath $statePath) { throw "Existing E2E run record for $RunId. Run scripts/Stop-E2E.ps1 -RunId $RunId first." }

# Health 200 alone cannot prove the responder is the process this script started
# (another process could win the bind race between the preflight above and the
# Start-Process below): accept the socket only when its OwningProcess is the
# recorded PID, or a descendant whose command line contains this run's expected
# invocation and whose creation time is not older than the recorded start. On
# Windows a venv redirector launches the base Python executable; its path differs
# from .venv/Scripts, so backend identity uses the exact uvicorn invocation.
function Test-PortIsOwned {
    param(
        [int]$Port,
        [int]$OwnedPid,
        [string]$RootStartedAt,
        [string]$NeedleDir
    )
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -eq 0) { return $false }
    $ownerIds = @($listeners | ForEach-Object { [int]$_.OwningProcess } | Select-Object -Unique)
    $allProcesses = @(Get-CimInstance Win32_Process)
    $rootStartUtc = ([datetime]$RootStartedAt).ToUniversalTime()
    $rootDetails = $allProcesses | Where-Object { $_.ProcessId -eq $OwnedPid }
    if (!$rootDetails -or !$rootDetails.CommandLine -or !$rootDetails.CommandLine.Contains($NeedleDir)) { return $false }
    if ([math]::Abs((([datetime]$rootDetails.CreationDate).ToUniversalTime() - $rootStartUtc).TotalSeconds) -gt 2) { return $false }
    if ($ownerIds -contains $OwnedPid) { return $true }
    $family = @($OwnedPid)
    for ($index = 0; $index -lt $family.Count; $index++) {
        $children = @($allProcesses | Where-Object { $_.ParentProcessId -eq $family[$index] })
        foreach ($child in $children) { if ($family -notcontains [int]$child.ProcessId) { $family += [int]$child.ProcessId } }
    }
    foreach ($ownerId in $ownerIds) {
        if ($family -notcontains $ownerId) { continue }
        $details = $allProcesses | Where-Object { $_.ProcessId -eq $ownerId }
        if (!$details -or !$details.CommandLine -or !$details.CommandLine.Contains($NeedleDir)) { continue }
        if (([datetime]$details.CreationDate).ToUniversalTime() -lt $rootStartUtc.AddSeconds(-2)) { continue }
        return $true
    }
    return $false
}

if ($CheckOnly) {
    Push-Location $backendRoot
    try {
        & $pythonPath -m evals.seed_e2e --create-database --run-id $RunId --help | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Backend cannot run the E2E seeder module.' }
        & $nodeExecutable --version | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Node is unavailable.' }
    } finally { Pop-Location }
    Write-Output "E2E preflight passed for run '$RunId' (db cp_e2e_$RunId on loopback, ports $backendPort/$frontendPort free, storage $storageDir). Nothing was created or started."
    exit 0
}

New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null

# Start-Process children inherit this session's environment; every override is
# restored in the finally block after the children have captured their copy.
$previousEnv = @{}
foreach ($name in @('DATABASE_URL', 'STORAGE_BASE_DIR', 'AI_EXTERNAL_ENABLED', 'AI_PROVIDER', 'FRONTEND_ORIGINS', 'BACKEND_ORIGIN', 'NEXT_DIST_DIR', 'E2E_STORAGE_DIR', 'NEXT_TELEMETRY_DISABLED', 'E2E_SYNTHETIC_VERIFICATION_RUN')) {
    $previousEnv[$name] = [Environment]::GetEnvironmentVariable($name)
}
# next-env.d.ts is tracked and rewritten by every Next build; tsconfig.json is
# tracked too and a build with a custom distDir appends that directory to the
# include list. Original bytes are restored in finally; user changes present
# before the run are preserved, never overwritten with a checkout.
$trackedFileBytes = @{}
foreach ($name in @('next-env.d.ts', 'tsconfig.json')) {
    $trackedPath = Join-Path $frontendRoot $name
    if (Test-Path -LiteralPath $trackedPath) { $trackedFileBytes[$name] = [System.IO.File]::ReadAllBytes($trackedPath) }
}
$owned = @()
try {
    # Mock AI and the isolated database/storage take effect before any migration or
    # backend start; .env values are overridden in the process environment, never edited.
    $env:DATABASE_URL = $databaseUrl
    $env:STORAGE_BASE_DIR = $storageDir
    $env:AI_EXTERNAL_ENABLED = 'false'
    $env:AI_PROVIDER = 'mock'
    $env:E2E_SYNTHETIC_VERIFICATION_RUN = if ($SyntheticVerification) { $RunId } else { $null }
    $env:NEXT_TELEMETRY_DISABLED = '1'
    $env:FRONTEND_ORIGINS = "[`"http://127.0.0.1:$frontendPort`"]"
    $env:E2E_STORAGE_DIR = $storageDir
    if ($env:AI_EXTERNAL_ENABLED -ne 'false' -or $env:AI_PROVIDER -ne 'mock') { throw 'AI isolation environment could not be enforced.' }

    # 1. Review-gated: create cp_e2e_<RunId> on the loopback server (idempotent).
    Push-Location $backendRoot
    try {
        & $pythonPath -m evals.seed_e2e --create-database --run-id $RunId
        if ($LASTEXITCODE -ne 0) { throw "Could not create cp_e2e_$RunId." }

        # 2. Review-gated: migrate the isolated database only.
        & $pythonPath -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw 'E2E database migration failed.' }
    } finally { Pop-Location }

    if ($ActivateSyntheticBudget) {
        Push-Location $backendRoot
        try {
            & $pythonPath -m evals.activate_e2e_budget --run $RunId
            if ($LASTEXITCODE -ne 0) { throw 'Synthetic budget inventory audit refused activation.' }
        } finally { Pop-Location }
    }

    # 3. Backend on 8001 with AI forced to mock.
    $backendProcess = Start-Process -FilePath $pythonPath -ArgumentList $backendArguments -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $stateRoot "backend-$RunId.out.log") -RedirectStandardError (Join-Path $stateRoot "backend-$RunId.err.log")
    # Manifest keys are camelCase (id/startedAt/needle) exactly as the Python
    # seeder reads them; PowerShell property access is case-insensitive, so
    # Stop-E2E.ps1 keeps working against the same fields.
    $owned += @{ id = $backendProcess.Id; startedAt = $backendProcess.StartTime.ToUniversalTime().ToString('o'); needle = $pythonPath }

    # Write the manifest as soon as the first owned PID exists: if the health
    # wait or any later step fails, Stop-E2E.ps1 can find and stop exactly the
    # processes this script started instead of leaving an orphan on 8001.
    $manifest = [ordered]@{
        runId             = $RunId
        createdAt         = (Get-Date).ToUniversalTime().ToString('o')
        backendPort       = $backendPort
        frontendPort      = $frontendPort
        databaseName      = $databaseName
        storageDir        = $storageDir
        distDir           = '.next-e2e'
        backendVenv       = $BackendVenv
        backendTarget     = $backendTarget
        syntheticVerification = [bool]$SyntheticVerification
        backendRuntime    = $backendRuntime
        frontendStage     = $FrontendStage
        frontendRuntime   = $frontendRuntime
        aiExternalEnabled = 'false'
        aiProvider        = 'mock'
        backend           = @{ id = $backendProcess.Id; startedAt = $backendProcess.StartTime.ToUniversalTime().ToString('o'); needle = $pythonPath }
        processes         = @($owned)
    }
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding utf8

    # 4. Wait for the backend's own health and verify it is still alive; the
    # seeder validates the manifest above before touching anything.
    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if ($backendProcess.HasExited) { throw "Backend exited during startup; see $stateRoot\backend-$RunId.err.log." }
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$backendPort/api/v1/health" -TimeoutSec 2 -UseBasicParsing
            $ready = $response.StatusCode -eq 200
        } catch { $ready = $false }
        if ($ready) { break }
        Start-Sleep -Milliseconds 500
    }
    if (!$ready) { throw "Backend failed health check: http://127.0.0.1:$backendPort/api/v1/health. See $stateRoot logs." }
    # Re-verify ownership immediately before seeding: the health 200 must come
    # from this run's backend, not from a process that stole the port meanwhile.
    if (!(Test-PortIsOwned -Port $backendPort -OwnedPid $backendProcess.Id -RootStartedAt $owned[$owned.Count - 1].startedAt -NeedleDir $backendArguments)) {
        throw "Port $backendPort is not owned by this run's backend PID $($backendProcess.Id); refusing to seed."
    }

    # 5. Seed the synthetic two-student double-delivery fixture through the product API.
    Push-Location $backendRoot
    try {
        if (!$SkipSeed) {
            & $pythonPath -m evals.seed_e2e --run-id $RunId --base-url "http://127.0.0.1:$backendPort/api/v1"
            if ($LASTEXITCODE -ne 0) { throw 'E2E fixture seeding failed.' }
        } else {
            & $pythonPath -m evals.seed_e2e --run-id $RunId --base-url "http://127.0.0.1:$backendPort/api/v1" --verify-only
            if ($LASTEXITCODE -ne 0) { throw 'E2E fixture verification failed.' }
        }
    } finally { Pop-Location }

    # 6. Frontend on 3001 with its own build directory and backend origin.
    $env:BACKEND_ORIGIN = "http://127.0.0.1:$backendPort"
    $env:NEXT_DIST_DIR = '.next-e2e'
    if (!$SkipBuild) {
        Push-Location $frontendRoot
        try {
            & $nodeExecutable $nextPath build
            if ($LASTEXITCODE -ne 0) { throw 'E2E frontend build failed.' }
        } finally { Pop-Location }
    } elseif (!(Test-Path -LiteralPath (Join-Path $frontendRoot '.next-e2e\BUILD_ID'))) {
        throw 'The isolated Next build (.next-e2e) is missing; run without -SkipBuild once.'
    }
    $frontendProcess = Start-Process -FilePath $nodeExecutable -ArgumentList @(('"' + $nextPath + '"'), 'start', '-H', '127.0.0.1', '-p', "$frontendPort") -WorkingDirectory $frontendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $stateRoot "frontend-$RunId.out.log") -RedirectStandardError (Join-Path $stateRoot "frontend-$RunId.err.log")
    $owned += @{ id = $frontendProcess.Id; startedAt = $frontendProcess.StartTime.ToUniversalTime().ToString('o'); needle = $nextPath }
    $manifest.processes = @($owned)
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding utf8

    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if ($frontendProcess.HasExited) { throw "Frontend exited during startup; see $stateRoot\frontend-$RunId.err.log." }
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$frontendPort" -TimeoutSec 2 -UseBasicParsing
            $ready = $response.StatusCode -eq 200
        } catch { $ready = $false }
        if ($ready) { break }
        Start-Sleep -Milliseconds 500
    }
    if (!$ready) { throw "Frontend failed health check: http://127.0.0.1:$frontendPort. See $stateRoot logs." }
    if (!(Test-PortIsOwned -Port $frontendPort -OwnedPid $frontendProcess.Id -RootStartedAt $owned[$owned.Count - 1].startedAt -NeedleDir (Split-Path $nextPath -Parent))) {
        throw "Port $frontendPort is not owned by this run's frontend PID $($frontendProcess.Id); stopping this run."
    }
    Write-Output "CareerProof E2E run '$RunId' is ready at http://127.0.0.1:$frontendPort (backend http://127.0.0.1:$backendPort, database $databaseName on loopback, storage $storageDir, distDir .next-e2e, AI mock)."
    Write-Output "Fixture credentials are only in $backendRoot\.tmp\e2e\$RunId.json (gitignored). Stop with ./scripts/Stop-E2E.ps1 -RunId $RunId."
} catch {
    # The manifest exists from the first owned PID onward, so Stop-E2E.ps1 can
    # clean up recorded processes; if even that write failed, stop our own PIDs
    # directly (start-time checked) rather than leaving orphans behind.
    if (Test-Path -LiteralPath $statePath) {
        & (Join-Path $PSScriptRoot 'Stop-E2E.ps1') -RunId $RunId
    } else {
        foreach ($record in $owned) {
            $process = Get-Process -Id $record.id -ErrorAction SilentlyContinue
            if ($process -and $process.StartTime.ToUniversalTime().Ticks -eq ([datetime]$record.startedAt).ToUniversalTime().Ticks) {
                Stop-Process -Id $record.id -Force -ErrorAction SilentlyContinue
            }
        }
    }
    throw
} finally {
    # Restore tracked files byte-for-byte if the isolated build touched them
    # (Next rewrites next-env.d.ts and appends the distDir to tsconfig.json);
    # pre-existing user changes are preserved and files this run created are
    # removed again.
    foreach ($name in @('next-env.d.ts', 'tsconfig.json')) {
        $trackedPath = Join-Path $frontendRoot $name
        $original = $trackedFileBytes[$name]
        if ($null -ne $original) {
            if (Test-Path -LiteralPath $trackedPath) {
                $currentBytes = [System.IO.File]::ReadAllBytes($trackedPath)
                $changed = $currentBytes.Length -ne $original.Length
                if (!$changed) {
                    for ($i = 0; $i -lt $currentBytes.Length; $i++) {
                        if ($currentBytes[$i] -ne $original[$i]) { $changed = $true; break }
                    }
                }
                if ($changed) {
                    [System.IO.File]::WriteAllBytes($trackedPath, $original)
                    Write-Output "$name was changed by the isolated build; the original bytes were restored."
                }
            } else {
                [System.IO.File]::WriteAllBytes($trackedPath, $original)
                Write-Output "$name was removed by the isolated build; the original bytes were restored."
            }
        } elseif ((Test-Path -LiteralPath $trackedPath) -and $owned.Count -gt 0) {
            Remove-Item -LiteralPath $trackedPath -Force
            Write-Output "$name did not exist before the E2E run; the build-generated copy was removed."
        }
    }
    foreach ($name in $previousEnv.Keys) {
        if ($null -ne $previousEnv[$name] -and "$($previousEnv[$name])" -ne '') {
            [Environment]::SetEnvironmentVariable($name, $previousEnv[$name])
        } else {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        }
    }
}
