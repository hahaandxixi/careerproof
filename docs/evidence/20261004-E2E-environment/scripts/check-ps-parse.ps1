$ErrorActionPreference = 'Stop'
# This script lives at docs/evidence/20261004-E2E-environment/scripts/; the repo
# root is four levels up.
$repoRoot = (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))))
Set-Location $repoRoot
foreach ($file in @('scripts/Start-E2E.ps1', 'scripts/Stop-E2E.ps1')) {
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $file), [ref]$tokens, [ref]$errors) | Out-Null
    if ($errors.Count -gt 0) {
        Write-Output "${file} PARSE ERRORS:"
        $errors | ForEach-Object { Write-Output $_.Message }
        exit 1
    }
    Write-Output "${file}: syntax OK"
}
exit 0
