# Goal 35: launcher recovery reliability. Offline only: mock processes, own
# scratch files under backend\.tmp, AST checks. No real services, containers,
# ports, existing locks or the real processes.json are ever touched.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'local-runtime.ps1')

$projectRoot = Split-Path $PSScriptRoot -Parent
$scratch = Join-Path $projectRoot ('backend\.tmp\local-launcher-recovery-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $scratch -Force | Out-Null
$failures = @()
$checks = 0
function Assert-Goal([string]$Name, [scriptblock]$Probe) {
    $script:checks++
    try { & $Probe | Out-Null; Write-Output "PASS $Name" }
    catch { $script:failures += "$Name :: $($_.Exception.Message)"; Write-Output "FAIL $Name :: $($_.Exception.Message)" }
}
try {
    # ---------- A. manifest persistence: atomic save, conservative diagnosis ----------
    $manifestPath = Join-Path $scratch 'processes.json'
    $firstManifest = @{ schemaVersion = 2; backendVenv = '.venv'; processes = @(@{ Id = 11; Started = '2026-10-11T00:00:00.0000000Z'; Needle = 'n1'; Invocation = 'i1' }) }
    Assert-Goal 'A1 first write creates the record' {
        Save-LocalRunManifest $manifestPath $firstManifest
        $parsed = Read-LocalRunManifest $manifestPath
        if ($parsed.schemaVersion -ne 2 -or @(Get-LocalRunRecords $parsed).Count -ne 1) { throw 'saved record did not round-trip' }
    }
    Assert-Goal 'A2 second write replaces the record atomically' {
        $second = @{ schemaVersion = 2; backendVenv = '.venv-b'; processes = @(@{ Id = 12; Started = '2026-10-11T01:00:00.0000000Z'; Needle = 'n2'; Invocation = 'i2' }, @{ Id = 13; Started = '2026-10-11T01:00:01.0000000Z'; Needle = 'n3'; Invocation = 'i3' }) }
        Save-LocalRunManifest $manifestPath $second
        $parsed = Read-LocalRunManifest $manifestPath
        if ($parsed.backendVenv -ne '.venv-b' -or @(Get-LocalRunRecords $parsed).Count -ne 2) { throw 'replacement did not take effect' }
    }
    Assert-Goal 'A3 failed save keeps the previous complete record' {
        $before = Get-Content -LiteralPath $manifestPath -Raw
        $stream = [System.IO.File]::Open($manifestPath, 'Open', 'ReadWrite', 'None')
        try {
            $rejected = $false
            try { Save-LocalRunManifest $manifestPath @{ schemaVersion = 2; processes = @() } } catch { $rejected = $true; if ($_.Exception.Message -notlike "*$manifestPath*") { throw "failure message lacks the file path: $($_.Exception.Message)" } }
            if (!$rejected) { throw 'save over a locked destination did not fail' }
        } finally { $stream.Dispose() }
        if ((Get-Content -LiteralPath $manifestPath -Raw) -ne $before) { throw 'previous record was damaged by the failed save' }
        if (Get-ChildItem -LiteralPath $scratch -Filter 'processes.json.tmp*' | ForEach-Object { $_ }) { throw 'temporary file left behind after failed save' }
    }
    Assert-Goal 'A4 reparse-point manifest paths are refused' {
        $target = Join-Path $scratch 'reparse-target'; New-Item -ItemType Directory -Path $target -Force | Out-Null
        Save-LocalRunManifest (Join-Path $target 'processes.json') $firstManifest
        $junction = Join-Path $scratch 'reparse-link'
        New-Item -ItemType Junction -Path $junction -Target $target | Out-Null
        $linked = Join-Path $junction 'processes.json'
        $rejected = $false
        try { Save-LocalRunManifest $linked $firstManifest } catch { $rejected = $true }
        if (!$rejected) { throw 'save through a reparse point was accepted' }
        $rejected = $false
        try { Read-LocalRunManifest $linked | Out-Null } catch { $rejected = $true }
        if (!$rejected) { throw 'read through a reparse point was accepted' }
    }
    Assert-Goal 'A5 corrupt JSON reports the file location and is not deleted' {
        $corrupt = Join-Path $scratch 'corrupt.json'
        Set-Content -LiteralPath $corrupt -Value '{"schemaVersion": 2, "processes": [ {"Id": 1' -Encoding utf8
        $rejected = $false
        try { Read-LocalRunManifest $corrupt | Out-Null } catch { $rejected = $true; if ($_.Exception.Message -notlike "*$corrupt*") { throw "error lacks the file path: $($_.Exception.Message)" } }
        if (!$rejected) { throw 'corrupt record was silently accepted' }
        if (!(Test-Path -LiteralPath $corrupt)) { throw 'corrupt record was deleted automatically' }
        if ((Get-Content -LiteralPath $corrupt -Raw) -notlike '{*') { throw 'corrupt record content was modified' }
    }
    Assert-Goal 'A6 empty record file is refused with the file location' {
        $empty = Join-Path $scratch 'empty.json'
        Set-Content -LiteralPath $empty -Value '' -Encoding utf8
        $rejected = $false
        try { Read-LocalRunManifest $empty | Out-Null } catch { $rejected = $true; if ($_.Exception.Message -notlike "*$empty*") { throw "error lacks the file path: $($_.Exception.Message)" } }
        if (!$rejected) { throw 'empty record was silently accepted' }
        if (!(Test-Path -LiteralPath $empty)) { throw 'empty record was deleted automatically' }
    }

    # ---------- B. validate every root before any stop; missing fields stop nothing ----------
    $procStart = [datetime]'2026-10-10T00:00:00Z'
    $script:stopCalls = @()
    function Get-Process { param($Id, $ErrorAction) if ($Id -in @(400, 401)) { return @{ StartTime = $script:procStart } } }
    function Get-CimInstance {
        param($ClassName, $Filter)
        $rows = @(
            # goal37: the same PID must carry one creation time across APIs; the
            # injected CIM time now matches the Get-Process StartTime and the
            # manifest so the stop path can require cross-API identity equality.
            @{ ProcessId = 400; ParentProcessId = 300; CreationDate = $script:procStart; CommandLine = 'owned-python uvicorn owned' },
            @{ ProcessId = 401; ParentProcessId = 400; CreationDate = $script:procStart; CommandLine = 'child-python next start' },
            @{ ProcessId = 999; ParentProcessId = 300; CreationDate = $script:procStart; CommandLine = 'foreign serve' }
        )
        if ($Filter) { $requested = [int]($Filter -replace 'ProcessId = ', ''); return $rows | Where-Object ProcessId -eq $requested }
        return $rows
    }
    function Stop-Process { param($Id, [switch]$Force, $ErrorAction) $script:stopCalls += [int]$Id }
    Assert-Goal 'B1 valid owned roots are stopped through the extracted stop path' {
        $manifest = @{ schemaVersion = 2; processes = @(
            @{ Id = 400; Started = $script:procStart.ToString('o'); Needle = 'owned-python'; Invocation = 'uvicorn owned' },
            @{ Id = 401; Started = $script:procStart.ToString('o'); Needle = 'child-python'; Invocation = 'next start' }) }
        $live = @(Stop-ValidatedLocalProcesses $manifest (Join-Path $scratch 'unused.json'))
        if ($live.Count -ne 2) { throw "expected 2 live roots, got $($live.Count)" }
        if ($script:stopCalls -notcontains 400 -or $script:stopCalls -notcontains 401) { throw "descendant stop missing: $($script:stopCalls -join ',')" }
        $script:stopCalls = @()
    }
    Assert-Goal 'B2 a record with missing fields stops nothing' {
        $manifest = @{ schemaVersion = 2; processes = @(
            @{ Id = 400; Started = $script:procStart.ToString('o'); Needle = 'owned-python'; Invocation = 'uvicorn owned' },
            @{ Id = 402; Started = $script:procStart.ToString('o') }) }
        $rejected = $false
        try { Stop-ValidatedLocalProcesses $manifest (Join-Path $scratch 'unused.json') | Out-Null } catch { $rejected = $true; if ($_.Exception.Message -notlike '*unused.json*') { throw "error lacks the manifest path: $($_.Exception.Message)" } }
        if (!$rejected) { throw 'incomplete record was accepted' }
        if ($script:stopCalls.Count -ne 0) { throw "Stop-Process was called for an incomplete record: $($script:stopCalls -join ',')" }
    }
    Assert-Goal 'B3 a changed command on the second root stops nothing' {
        $manifest = @{ schemaVersion = 2; processes = @(
            @{ Id = 400; Started = $script:procStart.ToString('o'); Needle = 'owned-python'; Invocation = 'uvicorn owned' },
            @{ Id = 401; Started = $script:procStart.ToString('o'); Needle = 'wrong-python'; Invocation = 'next start' }) }
        $rejected = $false
        try { Stop-ValidatedLocalProcesses $manifest (Join-Path $scratch 'unused.json') | Out-Null } catch { $rejected = $true }
        if (!$rejected) { throw 'changed command was accepted' }
        if ($script:stopCalls.Count -ne 0) { throw "first root was stopped before all roots validated: $($script:stopCalls -join ',')" }
    }
    Assert-Goal 'B4 a reused PID stops nothing' {
        $manifest = @{ schemaVersion = 2; processes = @(
            @{ Id = 400; Started = $script:procStart.AddMinutes(-5).ToString('o'); Needle = 'owned-python'; Invocation = 'uvicorn owned' }) }
        $rejected = $false
        try { Stop-ValidatedLocalProcesses $manifest (Join-Path $scratch 'unused.json') | Out-Null } catch { $rejected = $true }
        if (!$rejected) { throw 'reused PID was accepted' }
        if ($script:stopCalls.Count -ne 0) { throw "reused PID was stopped: $($script:stopCalls -join ',')" }
    }
    Assert-Goal 'B5 reuse is refused for incomplete or legacy manifests with the file location' {
        $statePath = Join-Path $scratch 'reuse.json'
        foreach ($bad in @($null, @{ schemaVersion = 1 }, @{ schemaVersion = 2; processes = @() }, @{ schemaVersion = 2; processes = @(@{ Id = 1 }) })) {
            $rejected = $false
            try { Assert-LocalReusableManifest $bad $statePath } catch { $rejected = $true; if ($_.Exception.Message -notlike "*$statePath*") { throw "error lacks the file path: $($_.Exception.Message)" } }
            if (!$rejected) { throw "incomplete manifest variant was accepted: $($bad | ConvertTo-Json -Compress -Depth 3)" }
        }
        Assert-LocalReusableManifest @{ schemaVersion = 2; processes = @(@{ Id = 1 }, @{ Id = 2 }) } $statePath
    }

    # ---------- C. backend reuse digest covers migrations and alembic config ----------
    $digRoot = Join-Path $scratch 'backend-digest'
    New-Item -ItemType Directory -Path (Join-Path $digRoot 'app\package') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $digRoot 'app\tests') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $digRoot 'alembic\versions') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $digRoot 'alembic\__pycache__') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $digRoot 'app\main.py') -Value 'app-v1'
    Set-Content -LiteralPath (Join-Path $digRoot 'app\package\mod.py') -Value 'mod-v1'
    Set-Content -LiteralPath (Join-Path $digRoot 'app\tests\test_mod.py') -Value 'test-v1'
    Set-Content -LiteralPath (Join-Path $digRoot 'pyproject.toml') -Value 'py-v1'
    Set-Content -LiteralPath (Join-Path $digRoot 'alembic.ini') -Value 'ini-v1'
    Set-Content -LiteralPath (Join-Path $digRoot 'alembic\env.py') -Value 'env-v1'
    Set-Content -LiteralPath (Join-Path $digRoot 'alembic\script.py.mako') -Value 'mako-v1'
    Set-Content -LiteralPath (Join-Path $digRoot 'alembic\versions\0001_initial.py') -Value 'mig1-v1'
    Set-Content -LiteralPath (Join-Path $digRoot 'alembic\versions\0002_next.py') -Value 'mig2-v1'
    Set-Content -LiteralPath (Join-Path $digRoot 'alembic\__pycache__\0001_initial.cpython-312.pyc') -Value 'bytecode-v1'
    $baseline = Get-LocalBackendDigest $digRoot
    Assert-Goal 'C1 digest is stable across repeated calls' {
        if ((Get-LocalBackendDigest $digRoot) -ne $baseline) { throw 'digest is not deterministic' }
    }
    Assert-Goal 'C2 changed migration content invalidates the digest' {
        Set-Content -LiteralPath (Join-Path $digRoot 'alembic\versions\0002_next.py') -Value 'mig2-v2'
        if ((Get-LocalBackendDigest $digRoot) -eq $baseline) { throw 'migration edit did not change the digest' }
        Set-Content -LiteralPath (Join-Path $digRoot 'alembic\versions\0002_next.py') -Value 'mig2-v1'
    }
    Assert-Goal 'C3 added and removed migrations are detectable' {
        Set-Content -LiteralPath (Join-Path $digRoot 'alembic\versions\0003_added.py') -Value 'mig3'
        $withNew = Get-LocalBackendDigest $digRoot
        if ($withNew -eq $baseline) { throw 'added migration did not change the digest' }
        Remove-Item -LiteralPath (Join-Path $digRoot 'alembic\versions\0003_added.py') -Force
        if ((Get-LocalBackendDigest $digRoot) -ne $baseline) { throw 'removing the added migration did not restore the digest' }
    }
    Assert-Goal 'C4 alembic config changes invalidate the digest' {
        Set-Content -LiteralPath (Join-Path $digRoot 'alembic.ini') -Value 'ini-v2'
        if ((Get-LocalBackendDigest $digRoot) -eq $baseline) { throw 'alembic.ini edit did not change the digest' }
        Set-Content -LiteralPath (Join-Path $digRoot 'alembic.ini') -Value 'ini-v1'
        Set-Content -LiteralPath (Join-Path $digRoot 'alembic\env.py') -Value 'env-v2'
        if ((Get-LocalBackendDigest $digRoot) -eq $baseline) { throw 'alembic env.py edit did not change the digest' }
        Set-Content -LiteralPath (Join-Path $digRoot 'alembic\env.py') -Value 'env-v1'
    }
    Assert-Goal 'C5 bytecode cache and unrelated scratch do not affect the digest' {
        Set-Content -LiteralPath (Join-Path $digRoot 'alembic\__pycache__\0001_initial.cpython-312.pyc') -Value 'bytecode-v2'
        Set-Content -LiteralPath (Join-Path $digRoot 'alembic\scratch-notes.txt') -Value 'scratch'
        if ((Get-LocalBackendDigest $digRoot) -ne $baseline) { throw 'bytecode or scratch changed the digest' }
        Remove-Item -LiteralPath (Join-Path $digRoot 'alembic\scratch-notes.txt') -Force
    }
    Assert-Goal 'C6 app source changes still invalidate; tests still do not' {
        Set-Content -LiteralPath (Join-Path $digRoot 'app\tests\test_mod.py') -Value 'test-v2'
        if ((Get-LocalBackendDigest $digRoot) -ne $baseline) { throw 'test file changed the digest' }
        Set-Content -LiteralPath (Join-Path $digRoot 'app\main.py') -Value 'app-v2'
        if ((Get-LocalBackendDigest $digRoot) -eq $baseline) { throw 'app source edit did not change the digest' }
    }

    # ---------- D. cleanup failure must not mask the original error ----------
    Assert-Goal 'D1 safe cleanup swallows cleanup failures with a warning' {
        $redirect = Invoke-LocalCleanupSafely { throw 'cleanup-boom-marker' } 3>&1
        if (($redirect | Out-String) -notmatch 'cleanup-boom-marker') { throw 'cleanup failure was swallowed silently without a warning' }
    }
    Assert-Goal 'D2 safe cleanup still runs a healthy cleanup' {
        $script:cleanupRan = $false
        Invoke-LocalCleanupSafely { $script:cleanupRan = $true }
        if (!$script:cleanupRan) { throw 'healthy cleanup was not executed' }
    }
    Assert-Goal 'D3 original error survives a failing cleanup in the catch pattern' {
        $caught = $null
        try {
            try { throw [System.InvalidOperationException]::new('original-root-cause-marker') }
            catch {
                $original = $_
                Invoke-LocalCleanupSafely { throw 'cleanup-failure-marker' } 3>&1 | Out-Null
                throw $original
            }
        } catch { $caught = $_ }
        if (!$caught -or $caught.Exception.Message -ne 'original-root-cause-marker') { throw "original error was masked: $($caught.Exception.Message)" }
    }
    Assert-Goal 'D4 AST: start/stop scripts parse and wire the new seams' {
        foreach ($relative in @('Start-Local.ps1', 'Stop-Local.ps1', 'scripts\local-runtime.ps1')) {
            $tokens = $null; $errors = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $projectRoot $relative), [ref]$tokens, [ref]$errors)
            if ($errors.Count -gt 0) { throw "$relative has $($errors.Count) syntax error(s): $($errors[0].Message)" }
        }
        $startAst = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $projectRoot 'Start-Local.ps1'), [ref]$null, [ref]$null)
        $startText = $startAst.Extent.Text
        if ($startText -match 'Set-Content') { throw 'Start-Local still writes the manifest without the atomic helper' }
        if ($startText -notmatch 'Invoke-LocalCleanupSafely') { throw 'Start-Local catch does not use the safe cleanup helper' }
        if ($startText -notmatch 'throw \$originalError') { throw 'Start-Local catch does not rethrow the saved original error' }
        if ($startText -notmatch 'Assert-LocalReusableManifest') { throw 'Start-Local reuse path does not guard incomplete manifests' }
        $stopAst = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $projectRoot 'Stop-Local.ps1'), [ref]$null, [ref]$null)
        $stopText = $stopAst.Extent.Text
        if ($stopText -notmatch 'Read-LocalRunManifest') { throw 'Stop-Local does not read the manifest through the guarded reader' }
        if ($stopText -notmatch 'Stop-ValidatedLocalProcesses') { throw 'Stop-Local does not stop through the validate-all-then-stop helper' }
        $runtimeAst = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $projectRoot 'scripts\local-runtime.ps1'), [ref]$null, [ref]$null)
        $digestFn = $runtimeAst.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-LocalBackendDigest' }, $true)
        if (!$digestFn -or $digestFn[0].Extent.Text -notmatch 'alembic') { throw 'backend digest does not reference the alembic tree' }
    }

    # ---------- E. goal37: save temp exclusivity and stop-identity pre-checks ----------
    # E1-E3 pin the save path: a foreign object parked at the legacy fixed temp
    # name must never be overwritten, followed through, or deleted. E4-E6 pin
    # the stop path: identities sampled after the CIM snapshot must still match
    # that snapshot (and the root its manifest record), and every root plus its
    # descendants must finish pre-checking before any Stop-Process runs.
    $script:goal37Links = @()
    $trapRoot = Join-Path $scratch 'linktrap'
    $outside = Join-Path $scratch 'outside-target'
    New-Item -ItemType Directory -Path $trapRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $outside -Force | Out-Null
    Assert-Goal 'E1 save never overwrites a foreign object parked at the legacy fixed temp path' {
        $dir = Join-Path $trapRoot 'occupied'; New-Item -ItemType Directory -Path $dir -Force | Out-Null
        $sentinel = Join-Path $dir 'processes.json.tmp'
        Set-Content -LiteralPath $sentinel -Value 'foreign-sentinel-v1' -Encoding utf8
        Save-LocalRunManifest (Join-Path $dir 'processes.json') $firstManifest
        if ((Get-Content -LiteralPath $sentinel -Raw).Trim() -ne 'foreign-sentinel-v1') { throw 'the object at the legacy fixed temp path was overwritten by the save' }
        if ((Read-LocalRunManifest (Join-Path $dir 'processes.json')).schemaVersion -ne 2) { throw 'save did not round-trip around the parked object' }
        if (Get-ChildItem -LiteralPath $dir -Filter 'processes.json.tmp-*' | ForEach-Object { $_ }) { throw 'own temporary file left behind after a successful save' }
    }
    Assert-Goal 'E2 a hard-linked temp path never reaches the link-external file' {
        $dir = Join-Path $trapRoot 'hardlink'; New-Item -ItemType Directory -Path $dir -Force | Out-Null
        $victim = Join-Path $outside 'victim-hardlink.txt'
        Set-Content -LiteralPath $victim -Value 'victim-v1' -Encoding utf8
        New-Item -ItemType HardLink -Path (Join-Path $dir 'processes.json.tmp') -Target $victim | Out-Null
        Save-LocalRunManifest (Join-Path $dir 'processes.json') $firstManifest
        if ((Get-Content -LiteralPath $victim -Raw).Trim() -ne 'victim-v1') { throw 'the link-external file was modified through the temp hard link' }
    }
    Assert-Goal 'E3 a reparse point parked at the temp path is neither followed nor deleted' {
        $dir = Join-Path $trapRoot 'junction'; New-Item -ItemType Directory -Path $dir -Force | Out-Null
        $payloadDir = Join-Path $outside 'junction-payload'
        New-Item -ItemType Directory -Path $payloadDir -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $payloadDir 'payload.txt') -Value 'payload-v1' -Encoding utf8
        $junction = Join-Path $dir 'processes.json.tmp'
        New-Item -ItemType Junction -Path $junction -Target $payloadDir | Out-Null
        $script:goal37Links += $junction
        Save-LocalRunManifest (Join-Path $dir 'processes.json') $firstManifest
        if (!(Test-Path -LiteralPath $junction)) { throw 'the foreign reparse point at the temp path was deleted' }
        if ((Get-Content -LiteralPath (Join-Path $payloadDir 'payload.txt') -Raw).Trim() -ne 'payload-v1') { throw 'the reparse target payload was modified' }
        if ((Get-ChildItem -LiteralPath $payloadDir | Where-Object { $_.Name -ne 'payload.txt' } | Measure-Object).Count -ne 0) { throw 'content was written through the reparse point' }
        if ((Read-LocalRunManifest (Join-Path $dir 'processes.json')).schemaVersion -ne 2) { throw 'save did not round-trip around the parked reparse point' }
    }
    $script:goal37ProcTimes = @{}
    $script:goal37CimRows = @()
    $script:goal37StopCalls = @()
    function Get-Process { param($Id, $ErrorAction) $key = [int]$Id; if ($script:goal37ProcTimes.ContainsKey($key)) { return @{ StartTime = $script:goal37ProcTimes[$key] } } }
    function Get-CimInstance {
        param($ClassName, $Filter)
        if ($Filter) { $requested = [int]($Filter -replace 'ProcessId = ', ''); return @($script:goal37CimRows | Where-Object { [int]$_.ProcessId -eq $requested }) }
        return $script:goal37CimRows
    }
    function Stop-Process { param($Id, [switch]$Force, $ErrorAction) $script:goal37StopCalls += [int]$Id }
    Assert-Goal 'E4 a descendant whose snapshot creation time differs from its live start is rejected before any stop' {
        $script:goal37ProcTimes = @{ 500 = $script:procStart; 501 = $script:procStart.AddHours(1) }
        $script:goal37CimRows = @(
            @{ ProcessId = 500; ParentProcessId = 90; CreationDate = $script:procStart; CommandLine = 'owned-python uvicorn owned' },
            @{ ProcessId = 501; ParentProcessId = 500; CreationDate = $script:procStart.AddSeconds(1); CommandLine = 'child-python next start' })
        $script:goal37StopCalls = @()
        $manifest = @{ schemaVersion = 2; processes = @(@{ Id = 500; Started = $script:procStart.ToString('o'); Needle = 'owned-python'; Invocation = 'uvicorn owned' }) }
        $rejected = $false
        try { Stop-ValidatedLocalProcesses $manifest (Join-Path $scratch 'unused.json') | Out-Null } catch { $rejected = $true }
        if (!$rejected) { throw 'descendant snapshot/live identity mismatch was accepted' }
        if ($script:goal37StopCalls.Count -ne 0) { throw "the mismatched descendant was stopped: $($script:goal37StopCalls -join ',')" }
    }
    Assert-Goal 'E5 a root that no longer matches its recorded start in the stop snapshot is not stopped' {
        $script:goal37ProcTimes = @{ 600 = $script:procStart }
        $script:goal37CimRows = @(@{ ProcessId = 600; ParentProcessId = 90; CreationDate = $script:procStart.AddHours(2); CommandLine = 'owned-python uvicorn owned' })
        $script:goal37StopCalls = @()
        $manifest = @{ schemaVersion = 2; processes = @(@{ Id = 600; Started = $script:procStart.ToString('o'); Needle = 'owned-python'; Invocation = 'uvicorn owned' }) }
        $rejected = $false
        try { Stop-ValidatedLocalProcesses $manifest (Join-Path $scratch 'unused.json') | Out-Null } catch { $rejected = $true }
        if (!$rejected) { throw 'root identity drift after validation was accepted' }
        if ($script:goal37StopCalls.Count -ne 0) { throw "the unbound root was stopped: $($script:goal37StopCalls -join ',')" }
    }
    Assert-Goal 'E6 a failing second-root pre-check stops nothing from the first root' {
        $script:goal37ProcTimes = @{ 700 = $script:procStart; 701 = $script:procStart.AddSeconds(1); 800 = $script:procStart; 801 = $script:procStart.AddHours(1) }
        $script:goal37CimRows = @(
            @{ ProcessId = 700; ParentProcessId = 90; CreationDate = $script:procStart; CommandLine = 'owned-python uvicorn owned' },
            @{ ProcessId = 701; ParentProcessId = 700; CreationDate = $script:procStart.AddSeconds(1); CommandLine = 'child-python next start' },
            @{ ProcessId = 800; ParentProcessId = 90; CreationDate = $script:procStart; CommandLine = 'owned-python uvicorn owned' },
            @{ ProcessId = 801; ParentProcessId = 800; CreationDate = $script:procStart.AddSeconds(1); CommandLine = 'child-python next start' })
        $script:goal37StopCalls = @()
        $manifest = @{ schemaVersion = 2; processes = @(
            @{ Id = 700; Started = $script:procStart.ToString('o'); Needle = 'owned-python'; Invocation = 'uvicorn owned' },
            @{ Id = 800; Started = $script:procStart.ToString('o'); Needle = 'owned-python'; Invocation = 'uvicorn owned' }) }
        $rejected = $false
        try { Stop-ValidatedLocalProcesses $manifest (Join-Path $scratch 'unused.json') | Out-Null } catch { $rejected = $true }
        if (!$rejected) { throw 'the failing second root was absorbed' }
        if ($script:goal37StopCalls.Count -ne 0) { throw "the first root was stopped before the second root finished pre-check: $($script:goal37StopCalls -join ',')" }
    }
} finally {
    # PS 5.1 Remove-Item throws NullReferenceException on junctions; delete the
    # link itself first so the scratch recursion cannot follow it either.
    $junction = Join-Path $scratch 'reparse-link'
    if (Test-Path -LiteralPath $junction) { try { [System.IO.Directory]::Delete($junction, $false) } catch { } }
    foreach ($extra in @($script:goal37Links)) {
        if ($extra -and (Test-Path -LiteralPath $extra)) { try { [System.IO.Directory]::Delete($extra, $false) } catch { } }
    }
    Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Output "$($checks - $failures.Count)/$checks launcher-recovery assertions passed; no live processes, locks, real manifests, containers or databases touched."
if ($failures.Count) { $failures | ForEach-Object { Write-Output "FAILED: $_" }; exit 1 }
exit 0
