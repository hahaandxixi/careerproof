# Shared by the local and demonstration launchers. No actions at dot-source time.
function Invoke-LocalNative([string]$Executable, [string[]]$Arguments) {
    # Windows PowerShell 5.1 turns native stderr progress into NativeCommandError
    # under Stop, even when Docker/Alembic exit successfully. Judge exit code.
    $savedPreference = $ErrorActionPreference
    try { $ErrorActionPreference = 'Continue'; $lines = & $Executable @Arguments 2>&1; $code = $LASTEXITCODE }
    finally { $ErrorActionPreference = $savedPreference }
    foreach ($line in $lines) { Write-Output ([string]$line) }
    if ($code -ne 0) { throw "Local command failed (exit $code). Inspect the output above." }
}

function Get-LocalConfigDigest([string]$Path) {
    $parts = @('missing-env-file')
    if (Test-Path -LiteralPath $Path) { $parts = @((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash) }
    foreach ($name in @('DATABASE_URL','AI_PROVIDER','AI_EXTERNAL_ENABLED','DEEPSEEK_API_KEY','APP_ENV','STORAGE_BASE_DIR','PYTHONPATH')) {
        $parts += $name + '=' + [Environment]::GetEnvironmentVariable($name)
    }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes(($parts -join "`n")))).Replace('-', '') }
    finally { $sha.Dispose() }
}

function Get-LocalBackendDigest([string]$Root) {
    $files = @(Get-ChildItem -LiteralPath (Join-Path $Root 'app') -Recurse -File -Filter '*.py' | Where-Object { $_.FullName -notmatch '[\\/]tests[\\/]' } | Sort-Object FullName)
    $files += Get-Item -LiteralPath (Join-Path $Root 'pyproject.toml')
    $parts = foreach ($file in $files) { $file.FullName.Substring($Root.Length) + ':' + (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes(($parts -join "`n")))).Replace('-', '') }
    finally { $sha.Dispose() }
}

function Get-LocalEnvValue([string]$Path, [string]$Name) {
    if (!(Test-Path -LiteralPath $Path)) { return $null }
    $escaped = [regex]::Escape($Name)
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match "^\s*$escaped\s*=\s*(.*)\s*$") { return $Matches[1].Trim().Trim('"').Trim("'") }
    }
    return $null
}

function Get-LocalRunRecords($Manifest) {
    if ($Manifest.schemaVersion -eq 2) { return @($Manifest.processes) }
    return @($Manifest) # compatibility with saved pre-upgrade process arrays
}

function Get-ValidatedLocalProcesses($Manifest) {
    $records = @(Get-LocalRunRecords $Manifest)
    if ($records.Count -eq 0) { throw 'Empty local process record; refusing to guess.' }
    $live = @()
    foreach ($record in $records) {
        if (!$record.Id -or !$record.Started -or [string]::IsNullOrWhiteSpace($record.Needle)) { throw 'Invalid local process identity.' }
        $process = Get-Process -Id $record.Id -ErrorAction SilentlyContinue
        if (!$process) { continue }
        if ($process.StartTime.ToUniversalTime().Ticks -ne ([datetime]$record.Started).ToUniversalTime().Ticks) { throw 'PID reused; no processes stopped.' }
        $details = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.Id)"
        if (!$details.CommandLine -or !$details.CommandLine.Contains([string]$record.Needle)) { throw 'Local process command changed; no processes stopped.' }
        $live += $record
    }
    return $live
}

function Test-LocalPortOwner([int]$Port, $Record) {
    if (!$Record -or [string]::IsNullOrWhiteSpace($Record.Invocation)) { return $false }
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if (!$listeners.Count) { return $false }
    $all = @(Get-CimInstance Win32_Process)
    $family = @([int]$Record.Id)
    for ($index = 0; $index -lt $family.Count; $index++) {
        foreach ($child in @($all | Where-Object ParentProcessId -eq $family[$index])) {
            if ($family -notcontains [int]$child.ProcessId -and ([datetime]$child.CreationDate).ToUniversalTime() -ge ([datetime]$Record.Started).ToUniversalTime()) { $family += [int]$child.ProcessId }
        }
    }
    foreach ($listener in $listeners) {
        if ($family -notcontains [int]$listener.OwningProcess) { return $false }
        $details = $all | Where-Object ProcessId -eq $listener.OwningProcess
        if (!$details.CommandLine -or !$details.CommandLine.Contains([string]$Record.Invocation)) { return $false }
    }
    return $true
}

function Wait-LocalService([string]$Url, [int]$Port, $Record) {
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if (!(Get-Process -Id $Record.Id -ErrorAction SilentlyContinue)) { throw "Service exited; inspect backend/.tmp/local-run logs (port $Port)." }
        try {
            $response = Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing
            if ($response.StatusCode -eq 200 -and (Test-LocalPortOwner $Port $Record)) { return }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    throw "Service failed its owned health check (port $Port); inspect backend/.tmp/local-run logs."
}
