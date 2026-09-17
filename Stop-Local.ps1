param([switch]$Database)
$ErrorActionPreference = 'Stop'
$statePath = Join-Path $PSScriptRoot 'backend\.tmp\local-run\processes.json'
if (Test-Path -LiteralPath $statePath) {
    # ConvertFrom-Json can emit a JSON array as one pipeline object. Assign first so
    # foreach receives each process record instead of one nested Object[].
    $records = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    foreach ($record in @($records)) {
        $process = Get-Process -Id $record.Id -ErrorAction SilentlyContinue
        if (!$process) { continue }
        # PowerShell versions may deserialize ISO timestamps as strings or DateTime.
        $savedStart = ([datetime]$record.Started).ToUniversalTime()
        if ($process.StartTime.ToUniversalTime().Ticks -ne $savedStart.Ticks) { throw 'PID was reused; refusing to stop another process.' }
        $details = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.Id)"
        if (!$details.CommandLine -or !$details.CommandLine.Contains([string]$record.Needle)) { throw 'Process command does not match this local run.' }
        $allProcesses = @(Get-CimInstance Win32_Process)
        $descendants = @([int]$record.Id)
        for ($index = 0; $index -lt $descendants.Count; $index++) {
            $children = @($allProcesses | Where-Object { $_.ParentProcessId -eq $descendants[$index] })
            foreach ($child in $children) { if ($descendants -notcontains [int]$child.ProcessId) { $descendants += [int]$child.ProcessId } }
        }
        [array]::Reverse($descendants)
        foreach ($ownedId in $descendants) { Stop-Process -Id $ownedId -Force -ErrorAction SilentlyContinue }
    }
    Remove-Item -LiteralPath $statePath -Force
}
if ($Database) {
    Push-Location (Join-Path $PSScriptRoot 'backend')
    try { & docker compose stop postgres; if ($LASTEXITCODE -ne 0) { throw 'Could not stop PostgreSQL.' } }
    finally { Pop-Location }
}
Write-Output 'Owned local services stopped.'
