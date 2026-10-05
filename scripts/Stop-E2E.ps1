# Stop only the processes recorded by Start-E2E.ps1 for this RunId.
# The cp_e2e_ database, its storage directory and all Docker volumes are left in
# place; existing services on 8000/3000 are never touched.
param(
    [Parameter(Mandatory = $true)][string]$RunId
)
$ErrorActionPreference = 'Stop'
# Validate the run id before it is ever concatenated into a path.
if ($RunId -notmatch '^[a-z0-9][a-z0-9-]{0,31}$') { throw 'RunId must match [a-z0-9][a-z0-9-]{0,31}.' }
$backendRoot = Join-Path (Split-Path $PSScriptRoot -Parent) 'backend'
$statePath = Join-Path $backendRoot ".tmp\e2e-run\processes-$RunId.json"
if (!(Test-Path -LiteralPath $statePath)) {
    Write-Output "No E2E run record for '$RunId'; nothing to stop."
    exit 0
}
$manifest = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
if (!$manifest -or !$manifest.processes) {
    throw 'E2E run record does not contain a process list; refusing to guess.'
}
# ConvertFrom-Json can emit a JSON array as one pipeline object. Assign first so
# foreach receives each process record instead of one nested Object[]. Entries
# use the same camelCase keys Start-E2E.ps1 writes and the Python seeder reads
# (id/startedAt/needle); access is case-insensitive anyway.
foreach ($record in @($manifest.processes)) {
    $process = Get-Process -Id $record.id -ErrorAction SilentlyContinue
    if (!$process) { continue }
    # PowerShell versions may deserialize ISO timestamps as strings or DateTime.
    $savedStart = ([datetime]$record.startedAt).ToUniversalTime()
    if ($process.StartTime.ToUniversalTime().Ticks -ne $savedStart.Ticks) { throw 'PID was reused; refusing to stop another process. The run record is kept.' }
    $details = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.id)"
    if (!$details.CommandLine -or !$details.CommandLine.Contains([string]$record.needle)) { throw 'Process command does not match this E2E run. The run record is kept.' }
    $allProcesses = @(Get-CimInstance Win32_Process)
    $descendants = @([int]$record.id)
    for ($index = 0; $index -lt $descendants.Count; $index++) {
        $children = @($allProcesses | Where-Object { $_.ParentProcessId -eq $descendants[$index] })
        foreach ($child in $children) { if ($descendants -notcontains [int]$child.ProcessId) { $descendants += [int]$child.ProcessId } }
    }
    [array]::Reverse($descendants)
    foreach ($ownedId in $descendants) { Stop-Process -Id $ownedId -Force -ErrorAction SilentlyContinue }
}
Remove-Item -LiteralPath $statePath -Force
Write-Output 'Owned E2E services stopped; the cp_e2e_ database and its storage directory are left in place.'
