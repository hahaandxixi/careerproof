param([switch]$Database, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\local-runtime.ps1')
$statePath = Join-Path $PSScriptRoot 'backend\.tmp\local-run\processes.json'
$stopLock = $null
try {
if (Test-Path -LiteralPath (Split-Path $statePath -Parent)) {
    try { $stopLock = [System.IO.File]::Open((Join-Path (Split-Path $statePath -Parent) 'launcher.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
    catch { throw 'A local launch/stop is in progress. No processes stopped.' }
}
if (Test-Path -LiteralPath $statePath) {
    # ConvertFrom-Json can emit a JSON array as one pipeline object. Assign first so
    # foreach receives each process record instead of one nested Object[].
    $records = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    # Validate EVERY root before stopping any, so a mismatched second record
    # cannot leave the first service terminated.
    $live = @(Get-ValidatedLocalProcesses $records)
    if ($CheckOnly) { Write-Output "Validated $($live.Count) owned root processes; no process or database stopped."; return }
    foreach ($record in $live) {
        $allProcesses = @(Get-CimInstance Win32_Process)
        $descendants = @([int]$record.Id)
        for ($index = 0; $index -lt $descendants.Count; $index++) {
            $children = @($allProcesses | Where-Object { $_.ParentProcessId -eq $descendants[$index] })
            foreach ($child in $children) { if ($descendants -notcontains [int]$child.ProcessId -and ([datetime]$child.CreationDate).ToUniversalTime() -ge ([datetime]$record.Started).ToUniversalTime()) { $descendants += [int]$child.ProcessId } }
        }
        [array]::Reverse($descendants)
        $identities = @{}
        foreach ($ownedId in $descendants) {
            $ownedProcess = Get-Process -Id $ownedId -ErrorAction SilentlyContinue
            if ($ownedProcess) { $identities[$ownedId] = $ownedProcess.StartTime.ToUniversalTime().Ticks }
        }
        foreach ($ownedId in $descendants) {
            $ownedProcess = Get-Process -Id $ownedId -ErrorAction SilentlyContinue
            if ($ownedProcess -and $identities.ContainsKey($ownedId)) {
                if ($ownedProcess.StartTime.ToUniversalTime().Ticks -ne $identities[$ownedId]) { throw 'A descendant PID was reused; refusing to stop it.' }
                Stop-Process -Id $ownedId -Force -ErrorAction SilentlyContinue
            }
        }
    }
    Remove-Item -LiteralPath $statePath -Force
}
if ($CheckOnly) { Write-Output 'No local run record; no process or database stopped.'; return }
if ($Database) {
    Push-Location (Join-Path $PSScriptRoot 'backend')
    try { Invoke-LocalNative 'docker' @('compose', 'stop', 'postgres') }
    finally { Pop-Location }
}
Write-Output 'Owned local services stopped.'
} finally { if ($stopLock) { $stopLock.Dispose() } }
