# Real stop of one test-owned hidden child. No website, port, Docker or database.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'local-runtime.ps1')
$engine = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$nonce = 'owned-stop-' + [guid]::NewGuid().ToString('N')
$child = Start-Process -FilePath $engine -ArgumentList @('-NoProfile', '-Command', ('"Start-Sleep -Seconds 8; # ' + $nonce + '"')) -WindowStyle Hidden -PassThru
$childStarted = $child.StartTime.ToUniversalTime()
$script:allowedOwnedIds = @($child.Id)
$script:actualStops = @()
# Tripwire restricts real stops to the child and its observed console helpers.
function Stop-Process {
    param($Id, [switch]$Force, $ErrorAction)
    if ([int]$Id -notin $script:allowedOwnedIds) { throw 'Stop attempted outside the test-owned child tree.' }
    $script:actualStops += [int]$Id
    Microsoft.PowerShell.Management\Stop-Process -Id $Id -Force:$Force -ErrorAction Stop
}
try {
    Start-Sleep -Milliseconds 300
    $details = Get-CimInstance Win32_Process -Filter "ProcessId = $($child.Id)"
    if (!$details.CommandLine.Contains($nonce)) { throw 'Child nonce was not verified.' }
    $all = @(Get-CimInstance Win32_Process)
    for ($index = 0; $index -lt $script:allowedOwnedIds.Count; $index++) {
        foreach ($descendant in @($all | Where-Object ParentProcessId -eq $script:allowedOwnedIds[$index])) {
            if (([datetime]$descendant.CreationDate).ToUniversalTime() -ge $childStarted -and [int]$descendant.ProcessId -notin $script:allowedOwnedIds) {
                $script:allowedOwnedIds += [int]$descendant.ProcessId
            }
        }
    }
    $manifest = @{ schemaVersion = 2; processes = @(@{ Id = $child.Id; Started = $childStarted.ToString('o'); Needle = $nonce; Invocation = $nonce }) }
    $live = @(Stop-ValidatedLocalProcesses $manifest $null)
    if ($live.Count -ne 1 -or $child.Id -notin $script:actualStops) { throw 'Expected the recorded test-owned root to stop.' }
    if (Get-Process -Id $child.Id -ErrorAction SilentlyContinue) { throw 'Owned child remains alive.' }
    Write-Output "PASS real owned-child tree stop; $($script:actualStops.Count) verified test-tree processes stopped, no services or files touched."
} finally {
    # A failed test leaves the short-lived child to exit naturally, never guesses.
    $remaining = Get-Process -Id $child.Id -ErrorAction SilentlyContinue
    if ($remaining -and $remaining.StartTime.ToUniversalTime().Ticks -eq $childStarted.Ticks) {
        Wait-Process -Id $child.Id -Timeout 15 -ErrorAction SilentlyContinue
    }
}
