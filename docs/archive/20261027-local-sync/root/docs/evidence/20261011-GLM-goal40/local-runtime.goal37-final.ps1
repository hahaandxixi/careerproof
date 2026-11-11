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
    $alembicIni = Join-Path $Root 'alembic.ini'
    if (Test-Path -LiteralPath $alembicIni) { $files += Get-Item -LiteralPath $alembicIni }
    $alembicRoot = Join-Path $Root 'alembic'
    if (Test-Path -LiteralPath $alembicRoot) {
        # Migrations and alembic config invalidate reuse; the bytecode cache and
        # non-config scratch must not.
        $files += @(Get-ChildItem -LiteralPath $alembicRoot -Recurse -File | Where-Object { $_.FullName -notmatch '[\\/]__pycache__[\\/]' -and $_.Extension -match '^\.(py|mako)$' } | Sort-Object FullName)
    }
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

function Assert-LocalStatePath([string]$Path) {
    foreach ($candidate in @($Path, (Split-Path -Parent $Path))) {
        if (!$candidate) { continue }
        $item = Get-Item -LiteralPath $candidate -ErrorAction SilentlyContinue
        if ($item -and ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) { throw "Local run state path must not be a reparse point: $candidate" }
    }
}

function Read-LocalRunManifest([string]$Path) {
    if (!(Test-Path -LiteralPath $Path)) { return $null }
    Assert-LocalStatePath $Path
    $raw = Get-Content -LiteralPath $Path -Raw
    if ([string]::IsNullOrWhiteSpace($raw)) { throw "Local run record at $Path is empty. Corruption is not proof that nothing is running: confirm no services are live, then move the file aside manually; it was not removed automatically." }
    try { $parsed = $raw | ConvertFrom-Json -ErrorAction Stop } catch { throw "Local run record at $Path is unreadable JSON. Corruption is not proof that nothing is running: confirm no services are live, then move the file aside manually; it was not removed automatically. ($($_.Exception.Message))" }
    if ($null -eq $parsed) { throw "Local run record at $Path holds no readable process data. Confirm no services are live, then move the file aside manually; it was not removed automatically." }
    return $parsed
}

function Save-LocalRunManifest([string]$Path, $Manifest) {
    Assert-LocalStatePath $Path
    # Own uniquely named temp beside the target; CreateNew refuses any existing
    # entry (stale temp, occupied file, reparse point), so an object parked at a
    # predictable temp path is never overwritten, followed, or deleted, and only
    # this save's own temp is ever cleaned up.
    $temporary = Join-Path (Split-Path -Parent $Path) ((Split-Path -Leaf $Path) + '.tmp-' + [guid]::NewGuid().ToString('N'))
    try {
        $json = $Manifest | ConvertTo-Json -Depth 4
        $stream = [System.IO.File]::Open($temporary, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
        try {
            $writer = New-Object System.IO.StreamWriter($stream, (New-Object System.Text.UTF8Encoding($true)))
            try { $writer.Write($json) } finally { $writer.Dispose() }
        } finally { $stream.Dispose() }
        # Same-volume metadata replacement (ReplaceFile) when the record exists,
        # a plain move on first write. Both are verifiable Windows replacement
        # behaviors, not a power-failure durability guarantee. PowerShell 5.1
        # binds a bare $null to an empty string here, which ReplaceFile rejects,
        # so a true null must be passed for the no-backup case.
        if (Test-Path -LiteralPath $Path) { [System.IO.File]::Replace($temporary, $Path, [NullString]::Value) }
        else { [System.IO.File]::Move($temporary, $Path) }
    } catch {
        Remove-Item -LiteralPath $temporary -ErrorAction SilentlyContinue
        throw "Failed to save local run record at $Path; the previous record was left untouched. ($($_.Exception.Message))"
    }
}

function Get-LocalRunRecords($Manifest) {
    if ($Manifest.schemaVersion -eq 2) { return @($Manifest.processes) }
    return @($Manifest) # compatibility with saved pre-upgrade process arrays
}

function Get-ValidatedLocalProcesses($Manifest, [string]$StatePath) {
    $where = if ($StatePath) { " in $StatePath" } else { '' }
    $records = @(Get-LocalRunRecords $Manifest)
    if ($records.Count -eq 0) { throw "Empty local process record$where; refusing to guess." }
    $live = @()
    foreach ($record in $records) {
        if (!$record.Id -or !$record.Started -or [string]::IsNullOrWhiteSpace($record.Needle)) { throw "Invalid local process identity$where." }
        $process = Get-Process -Id $record.Id -ErrorAction SilentlyContinue
        if (!$process) { continue }
        if ($process.StartTime.ToUniversalTime().Ticks -ne ([datetime]$record.Started).ToUniversalTime().Ticks) { throw "PID reused; no processes stopped$where." }
        $details = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.Id)"
        if (!$details.CommandLine -or !$details.CommandLine.Contains([string]$record.Needle)) { throw "Local process command changed; no processes stopped$where." }
        $live += $record
    }
    return $live
}

function Assert-LocalReusableManifest($Manifest, [string]$StatePath) {
    if (!$Manifest -or $Manifest.schemaVersion -ne 2 -or @(Get-LocalRunRecords $Manifest).Count -lt 2) {
        throw "Local run record at $StatePath is incomplete or from an older format; refusing to reuse it. Run Stop-Local.ps1 to stop any recorded services, then start again."
    }
}

function Stop-ValidatedLocalProcesses($Manifest, [string]$StatePath, [switch]$ValidateOnly) {
    $live = @(Get-ValidatedLocalProcesses $Manifest $StatePath)
    if ($ValidateOnly) { return $live }
    $where = if ($StatePath) { " in $StatePath" } else { '' }
    # Build the full plan for every root first: snapshot, descendant walk and
    # identity sampling must all succeed before any Stop-Process runs, so a
    # failing later root cannot leave an earlier root already stopped.
    $plans = @()
    foreach ($record in $live) {
        $allProcesses = @(Get-CimInstance Win32_Process)
        $snapshots = @{}
        foreach ($row in $allProcesses) { $snapshots[[int]$row.ProcessId] = $row }
        $rootRow = $snapshots[[int]$record.Id]
        if (!$rootRow) {
            # The validated root vanished before the snapshot: if nothing lives
            # at that PID any more there is nothing to stop, otherwise the
            # snapshot cannot prove the identity and the whole stop is refused.
            if (Get-Process -Id $record.Id -ErrorAction SilentlyContinue) { throw "Root PID $($record.Id) is missing from the process snapshot; no processes stopped$where." }
            continue
        }
        # The root stays bound to its manifest record: a reused PID would show a
        # new creation time in the snapshot even though the live start time was
        # matched by the earlier validation pass.
        if (([datetime]$rootRow.CreationDate).ToUniversalTime().Ticks -ne ([datetime]$record.Started).ToUniversalTime().Ticks) { throw "Root PID $($record.Id) no longer matches its recorded start time; no processes stopped$where." }
        $descendants = @([int]$record.Id)
        for ($index = 0; $index -lt $descendants.Count; $index++) {
            $children = @($allProcesses | Where-Object { $_.ParentProcessId -eq $descendants[$index] })
            foreach ($child in $children) { if ($descendants -notcontains [int]$child.ProcessId -and ([datetime]$child.CreationDate).ToUniversalTime() -ge ([datetime]$record.Started).ToUniversalTime()) { $descendants += [int]$child.ProcessId } }
        }
        [array]::Reverse($descendants)
        $identities = @{}
        foreach ($ownedId in $descendants) {
            $ownedProcess = Get-Process -Id $ownedId -ErrorAction SilentlyContinue
            if (!$ownedProcess) { continue }
            # Kernel creation times are microsecond-aligned, so a process that
            # still is the one from the snapshot carries the exact same time in
            # both APIs; any difference here means the PID was reused between
            # the snapshot and this sampling and the identity is not ours.
            $row = $snapshots[$ownedId]
            if (!$row -or ([datetime]$row.CreationDate).ToUniversalTime().Ticks -ne $ownedProcess.StartTime.ToUniversalTime().Ticks) { throw "PID $ownedId changed identity between the process snapshot and sampling; refusing to stop it$where." }
            $identities[$ownedId] = $ownedProcess.StartTime.ToUniversalTime().Ticks
        }
        $plans += ,@($descendants, $identities)
    }
    foreach ($plan in $plans) {
        $descendants = $plan[0]; $identities = $plan[1]
        foreach ($ownedId in $descendants) {
            $ownedProcess = Get-Process -Id $ownedId -ErrorAction SilentlyContinue
            if ($ownedProcess -and $identities.ContainsKey($ownedId)) {
                if ($ownedProcess.StartTime.ToUniversalTime().Ticks -ne $identities[$ownedId]) { throw 'A descendant PID was reused; refusing to stop it.' }
                Stop-Process -Id $ownedId -Force -ErrorAction SilentlyContinue
            }
        }
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

function Invoke-LocalCleanupSafely([scriptblock]$Cleanup) {
    # Startup cleanup is best effort: its own failure must not mask the error that triggered it.
    try { & $Cleanup } catch { Write-Warning "Startup cleanup did not complete: $($_.Exception.Message)" }
}
