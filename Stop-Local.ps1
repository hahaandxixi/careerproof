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
$records = Read-LocalRunManifest $statePath
if ($null -ne $records) {
    # Validate EVERY root before stopping any, so a mismatched second record
    # cannot leave the first service terminated.
    $live = @(Stop-ValidatedLocalProcesses $records $statePath -ValidateOnly:$CheckOnly)
    if ($CheckOnly) { Write-Output "Validated $($live.Count) owned root processes; no process or database stopped."; return }
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
