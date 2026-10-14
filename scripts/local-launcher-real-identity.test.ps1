# Goal 40: real-process read-only identity verification. Only the current test
# process and one self-owned short-lived hidden nonce child are observed; every
# API call is read-only, nothing is ever stopped, no service, port, database or
# run record is touched and no file is written.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'local-runtime.ps1')

# Tripwire: any attempt to stop a process fails the whole run.
function Stop-Process { throw "REAL-IDENTITY-TEST-MUST-NOT-STOP-ANYTHING (asked for $($args -join ' '))" }
$failures = @()
$checks = 0
function Assert-Goal([string]$Name, [scriptblock]$Probe) {
    $script:checks++
    try {
        # Forward probe output (e.g. raw TICKS evidence) instead of swallowing it.
        foreach ($line in @(& $Probe)) { Write-Output $line }
        Write-Output "PASS $Name"
    }
    catch { $script:failures += "$Name :: $($_.Exception.Message)"; Write-Output "FAIL $Name :: $($_.Exception.Message)" }
}
function Assert-RealTickRelation([string]$Label, $Proc, $CimRow) {
    # Real cross-API contract pinned by goal 40: CIM floors the kernel 100ns
    # creation time onto its microsecond grid, .NET keeps full 100ns ticks.
    $net = $Proc.StartTime.ToUniversalTime().Ticks
    $cim = ([datetime]$CimRow.CreationDate).ToUniversalTime().Ticks
    Write-Output ("TICKS " + $Label + " pid=" + $Proc.Id + " net=" + $net + " cim=" + $cim + " gap=" + ($net - $cim))
    if ($cim % 10 -ne 0) { throw "$Label CIM creation time is not on the microsecond grid (mod10=$($cim % 10))" }
    if ($cim -gt $net) { throw "$Label CIM time sits above the .NET start time; rounding, not truncation, was observed" }
    if ($net - $cim -ge 10) { throw "$Label cross-API gap is a full microsecond or more" }
    if ((Get-LocalCimMicrosecondTicks $net) -ne $cim) { throw "$Label the microsecond-grid normalization does not reproduce the real CIM value" }
}
try {
    $ownProc = Get-Process -Id $PID
    $ownCim = Get-CimInstance Win32_Process -Filter "ProcessId = $PID"
    $ownCommandLine = [string]$ownCim.CommandLine
    # Precise command-line identity of this very process, per the task card.
    $needle = 'local-launcher-real-identity.test.ps1'
    if (!$ownCommandLine.Contains($needle)) { $needle = $ownCommandLine.Trim() }
    $ownStart = $ownProc.StartTime.ToUniversalTime().ToString('o')

    Assert-Goal 'R1 the current test process is accepted by its own real record in ValidateOnly' {
        $manifest = @{ schemaVersion = 2; processes = @(@{ Id = $PID; Started = $ownStart; Needle = $needle; Invocation = $needle }) }
        $live = @(Stop-ValidatedLocalProcesses $manifest $null -ValidateOnly)
        if ($live.Count -ne 1 -or [int]$live[0].Id -ne $PID) { throw 'the current process was not returned as live' }
    }
    Assert-Goal 'R2 the real self tick pair sits on the CIM microsecond grid' {
        Assert-RealTickRelation 'self' $ownProc $ownCim
    }
    Assert-Goal 'R3 a real command-line mismatch on the self record is refused' {
        $manifest = @{ schemaVersion = 2; processes = @(@{ Id = $PID; Started = $ownStart; Needle = 'goal40-not-our-command-line'; Invocation = 'x' }) }
        $rejected = $false
        try { Stop-ValidatedLocalProcesses $manifest $null -ValidateOnly | Out-Null } catch { $rejected = $true }
        if (!$rejected) { throw 'a foreign command line was accepted for the real process' }
    }

    # One self-owned, hidden, short-lived nonce child: sampled read-only and
    # left to exit on its own; it is never stopped and nothing else is touched.
    $nonce = 'goal40-real-identity-' + [guid]::NewGuid().ToString('N')
    $child = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList @('-NoProfile', '-Command', ('"Start-Sleep -Seconds 4; # ' + $nonce + '"')) -WindowStyle Hidden -PassThru
    Write-Output ("CHILD nonce=" + $nonce + " pid=" + $child.Id + " started-at=" + (Get-Date).ToString('o') + " exits-by-itself-after-4s")
    $childProc = $null
    $childCim = $null
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 300
        $childProc = Get-Process -Id $child.Id -ErrorAction SilentlyContinue
        $childCim = Get-CimInstance Win32_Process -Filter "ProcessId = $($child.Id)" -ErrorAction SilentlyContinue
        if ($childProc -and $childCim) { break }
    }
    if (!$childProc -or !$childCim) { throw "the nonce child did not become observable (proc=$($childProc -ne $null), cim=$($childCim -ne $null))" }
    $childStart = $childProc.StartTime.ToUniversalTime().ToString('o')
    Assert-Goal 'R4 the nonce child is accepted by its own real record in ValidateOnly' {
        $manifest = @{ schemaVersion = 2; processes = @(@{ Id = $child.Id; Started = $childStart; Needle = $nonce; Invocation = $nonce }) }
        $live = @(Stop-ValidatedLocalProcesses $manifest $null -ValidateOnly)
        if ($live.Count -ne 1 -or [int]$live[0].Id -ne $child.Id) { throw 'the nonce child was not returned as live' }
    }
    Assert-Goal 'R5 the real child tick pair sits on the CIM microsecond grid' {
        Assert-RealTickRelation 'child' $childProc $childCim
    }
    Assert-Goal 'R6 a one-hour start drift on the child record is refused' {
        $manifest = @{ schemaVersion = 2; processes = @(@{ Id = $child.Id; Started = $childProc.StartTime.ToUniversalTime().AddHours(1).ToString('o'); Needle = $nonce; Invocation = $nonce }) }
        $rejected = $false
        try { Stop-ValidatedLocalProcesses $manifest $null -ValidateOnly | Out-Null } catch { $rejected = $true }
        if (!$rejected) { throw 'a reused-PID start drift was accepted for the real process' }
    }
    Assert-Goal 'R7 a one-microsecond manifest drift on the child record is refused' {
        # The manifest carries full .NET ticks: a 10-tick shift is a different
        # process start and must stay rejected at high precision.
        $manifest = @{ schemaVersion = 2; processes = @(@{ Id = $child.Id; Started = $childProc.StartTime.ToUniversalTime().AddTicks(10).ToString('o'); Needle = $nonce; Invocation = $nonce }) }
        $rejected = $false
        try { Stop-ValidatedLocalProcesses $manifest $null -ValidateOnly | Out-Null } catch { $rejected = $true }
        if (!$rejected) { throw 'a one-microsecond manifest drift was accepted for the real process' }
    }
    # Natural exit only: wait, never stop. A timeout is a failure to report,
    # not a kill.
    $exited = $false
    try { Wait-Process -Id $child.Id -Timeout 30 -ErrorAction Stop; $exited = $true }
    catch {
        if (Get-Process -Id $child.Id -ErrorAction SilentlyContinue) { throw "the nonce child did not exit on its own within 30s; it was NOT stopped (ownership: test-spawned nonce $nonce, pid $($child.Id))" }
        $exited = $true
    }
    if (!$exited -or (Get-Process -Id $child.Id -ErrorAction SilentlyContinue)) { throw "the nonce child is still alive (pid $($child.Id)); nothing was stopped" }
    Write-Output ("CHILD exited-on-its-own pid=" + $child.Id)
} finally {
    # Deliberately no cleanup: nothing was created, started permanently or
    # stopped. If the nonce child somehow outlived the run it exits itself.
}
Write-Output "$($checks - $failures.Count)/$checks real-identity assertions passed; read-only observation only, zero stops, zero files written."
if ($failures.Count) { $failures | ForEach-Object { Write-Output "FAILED: $_" }; exit 1 }
exit 0
