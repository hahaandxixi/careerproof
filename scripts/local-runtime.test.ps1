$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'local-runtime.ps1')
$start = [datetime]'2026-10-10T00:00:00Z'
$rootRecord = @{ Id = 100; Started = $start.ToString('o'); Needle = 'owned-python'; Invocation = 'uvicorn owned' }
function Get-Process { param($Id, $ErrorAction) if ($Id -in @(100,101)) { return @{ StartTime = $start } } }
function Get-CimInstance {
    param($ClassName, $Filter)
    $rows = @(
        @{ ProcessId=100; ParentProcessId=90; CreationDate=$start; CommandLine='owned-python uvicorn owned' },
        @{ ProcessId=101; ParentProcessId=100; CreationDate=$start.AddSeconds(1); CommandLine='base-python uvicorn owned' },
        @{ ProcessId=999; ParentProcessId=90; CreationDate=$start; CommandLine='foreign uvicorn owned' }
    )
    if ($Filter) { $requested = [int]($Filter -replace 'ProcessId = ', ''); return $rows | Where-Object ProcessId -eq $requested }
    return $rows
}
function Get-NetTCPConnection { param($LocalPort, $State, $ErrorAction) return $script:listeners }
$live = @(Get-ValidatedLocalProcesses @{ schemaVersion=2; processes=@($rootRecord) })
if ($live.Count -ne 1) { throw 'New manifest root was not recognized' }
if (@(Get-ValidatedLocalProcesses @($rootRecord)).Count -ne 1) { throw 'Legacy manifest rejected' }
$bad = @{ Id=101; Started=$start.ToString('o'); Needle='wrong-command' }
$rejected = $false
try { Get-ValidatedLocalProcesses @{ schemaVersion=2; processes=@($rootRecord,$bad) } | Out-Null }
catch { $rejected=$true }
if (!$rejected) { throw 'Mismatched second record accepted' }
$empty = @{ Id=100; Started=$start.ToString('o'); Needle='' }
$rejected=$false
try { Get-ValidatedLocalProcesses @($empty) | Out-Null } catch { $rejected=$true }
if (!$rejected) { throw 'Empty identity accepted' }
$script:listeners=@(@{OwningProcess=101})
if (!(Test-LocalPortOwner 8000 $rootRecord)) { throw 'Redirector child rejected' }
$script:listeners=@(@{OwningProcess=101},@{OwningProcess=999})
if (Test-LocalPortOwner 8000 $rootRecord) { throw 'Mixed foreign listener accepted' }
$script:listeners=@(@{OwningProcess=999})
if (Test-LocalPortOwner 8000 $rootRecord) { throw 'Foreign healthy listener accepted' }
$temporary = Join-Path (Split-Path $PSScriptRoot -Parent) ('backend\.tmp\local-native-' + [guid]::NewGuid().ToString('N') + '.mjs')
try {
    "process.stderr.write('normal-progress'); process.exit(Number(process.argv[2]));" | Set-Content -LiteralPath $temporary -Encoding utf8
    $lines = Invoke-LocalNative 'node' @($temporary, '0')
    if (($lines -join '') -ne 'normal-progress') { throw 'Native stderr progress was not preserved' }
    $rejected=$false
    try { Invoke-LocalNative 'node' @($temporary, '7') | Out-Null } catch { $rejected=$true }
    if (!$rejected) { throw 'Native failure exit ignored' }
} finally {
    $resolved = [IO.Path]::GetFullPath($temporary)
    $allowed = [IO.Path]::GetFullPath((Join-Path (Split-Path $PSScriptRoot -Parent) 'backend\.tmp')) + [IO.Path]::DirectorySeparatorChar
    if (!$resolved.StartsWith($allowed)) { throw 'Temporary cleanup escaped workspace' }
    Remove-Item -LiteralPath $resolved -ErrorAction SilentlyContinue
}
$savedProvider = $env:AI_PROVIDER
try {
    $env:AI_PROVIDER='mock'; $firstDigest=Get-LocalConfigDigest (Join-Path $PSScriptRoot 'nonexistent-env')
    $env:AI_PROVIDER='deepseek'; $secondDigest=Get-LocalConfigDigest (Join-Path $PSScriptRoot 'nonexistent-env')
    if ($firstDigest -eq $secondDigest) { throw 'Changed process environment was ignored' }
} finally { $env:AI_PROVIDER=$savedProvider }
'10 lifecycle/native/config assertions passed; no live processes touched.'
exit 0
