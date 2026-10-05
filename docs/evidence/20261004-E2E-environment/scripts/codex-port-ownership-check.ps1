# Execute the production ownership function against deterministic process/socket
# inventories. No listener, application service or database is started.
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../../../')).Path
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $repo 'scripts/Start-E2E.ps1'), [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Start script parse failed.' }
$function = $ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -eq 'Test-PortIsOwned'
}, $true)
if (!$function) { throw 'Ownership function not found.' }
Invoke-Expression $function.Extent.Text
function Get-NetTCPConnection { param($LocalPort, $State, $ErrorAction) $script:sockets }
function Get-CimInstance { param($ClassName) $script:inventory }
$stamp = [datetime]::Parse('2026-10-05T00:00:00Z').ToUniversalTime()
$script:inventory = @(
    [pscustomobject]@{ProcessId=100; ParentProcessId=1; CommandLine='owned/python.exe'; CreationDate=$stamp},
    [pscustomobject]@{ProcessId=101; ParentProcessId=100; CommandLine='owned/python.exe'; CreationDate=$stamp.AddSeconds(1)},
    [pscustomobject]@{ProcessId=102; ParentProcessId=101; CommandLine='owned/python.exe'; CreationDate=$stamp.AddSeconds(2)},
    [pscustomobject]@{ProcessId=200; ParentProcessId=1; CommandLine='owned/python.exe'; CreationDate=$stamp.AddSeconds(1)}
)
function Assert-Owner([int]$Owner, [bool]$Expected, [string]$Label) {
    $script:sockets = @([pscustomobject]@{OwningProcess=$Owner})
    $actual = Test-PortIsOwned -Port 8001 -OwnedPid 100 -RootStartedAt $stamp.ToString('o') -NeedleDir 'owned/'
    if ([bool]$actual -ne $Expected) { throw "$Label expected=$Expected actual=$actual" }
    Write-Output "$Label passed"
}
Assert-Owner 100 $true 'owned root'
Assert-Owner 101 $true 'owned child'
Assert-Owner 102 $true 'owned grandchild'
Assert-Owner 200 $false 'foreign same-command process'
$script:inventory[1].CommandLine = 'foreign/python.exe'
Assert-Owner 101 $false 'foreign child command'
$script:inventory[1].CommandLine = 'owned/python.exe'
$script:inventory[1].CreationDate = $stamp.AddMinutes(-10)
Assert-Owner 101 $false 'stale child creation'
$script:sockets = @()
if (Test-PortIsOwned -Port 8001 -OwnedPid 100 -RootStartedAt $stamp.ToString('o') -NeedleDir 'owned/') {
    throw 'No listener was incorrectly accepted.'
}
Write-Output 'no listener passed'
$script:inventory[0].CreationDate = $stamp.AddMinutes(-10)
Assert-Owner 100 $false 'reused root PID'
Write-Output '8 ownership cases passed; mocked inventories only, no real bind/startup proof.'
