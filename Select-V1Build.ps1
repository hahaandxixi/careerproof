param(
    [Parameter(Mandatory=$true)][string]$DistDir,
    [Parameter(Mandatory=$true)][string]$BuildId,
    [Parameter(Mandatory=$true)][string]$SourceCommit
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\local-runtime.ps1')
. (Join-Path $PSScriptRoot 'scripts\local-frontend-build.ps1')
$state = Join-Path $PSScriptRoot 'backend\.tmp\v1-run'
$profile = Join-Path $PSScriptRoot 'backend\.tmp\unified-runtime.private.json'
if (!(Test-Path -LiteralPath $profile)) { throw 'Local unified configuration missing; no configuration was created.' }
New-Item -ItemType Directory -Path $state -Force | Out-Null
$lock = [IO.File]::Open((Join-Path $state 'launcher.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
try {
    $previous = Read-LocalRunManifest (Join-Path $state 'processes.json')
    if ($previous -and @(Get-ValidatedLocalProcesses $previous (Join-Path $state 'processes.json')).Count) { throw 'Stop the owned V1 run before selecting another build.' }
    $selection = @{ distDir = $DistDir; buildId = $BuildId; sourceCommit = $SourceCommit }
    $build = Get-LocalFrontendBuild (Join-Path $PSScriptRoot 'jianli') $selection
    $resolved = @(Invoke-LocalNative 'git' @('-C', $PSScriptRoot, 'rev-parse', '--verify', ($SourceCommit + '^{commit}')))
    if ($resolved.Count -ne 1 -or $resolved[0] -cne $SourceCommit) { throw 'Build source commit is not available in this repository.' }
    $raw = $null
    try { $raw = Get-Content -LiteralPath $profile -Raw -Encoding UTF8 }
    catch { throw "Local unified configuration at $profile could not be read. Confirm no services are live, then move the file aside manually; it was not removed automatically." }
    try { $config = $raw | ConvertFrom-Json }
    catch { throw "Local unified configuration at $profile is unreadable JSON. Confirm no services are live, then move the file aside manually; it was not removed automatically." }
    $invalid = $true
    if ($config -is [System.Management.Automation.PSCustomObject]) {
        $invalid = @('python','node','container') | Where-Object { $p = $config.PSObject.Properties[$_]; (-not $p) -or ($p.Value -isnot [string]) -or ([string]::IsNullOrWhiteSpace($p.Value)) }
    }
    if ($null -eq $config -or $invalid) {
        throw "Local unified configuration at $profile is structurally invalid: the runtime profile must be an object with python, node and container. Confirm no services are live, then move the file aside manually; it was not removed automatically."
    }
    $config | Add-Member -NotePropertyName frontendBuild -NotePropertyValue $selection -Force
    Save-LocalRunManifest $profile $config
    Write-Output "Selected V1 frontend: $($build.DistDir) / $($build.BuildId). No services, containers or migrations started."
} finally { $lock.Dispose() }
