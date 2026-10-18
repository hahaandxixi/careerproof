# Launcher entry checks: one recommended normal entry, real param forwarding, no secrets.
# Offline only: parses scripts, reads the guide, and runs Start-Local.ps1 -CheckOnly once
# (that path returns before Docker, migrations, builds or services).
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$checks = 0
function Check([string]$Name, [scriptblock]$Probe) {
    & $Probe
    $script:checks++
    Write-Output "PASS $Name"
}

$cmdPath = Join-Path $projectRoot 'Start-Local.cmd'
Check 'normal-environment cmd entry exists' {
    if (!(Test-Path -LiteralPath $cmdPath)) { throw 'Start-Local.cmd is missing.' }
}

Check 'cmd entry is a thin forwarder to Start-Local.ps1 with argument passthrough' {
    $text = Get-Content -LiteralPath $cmdPath -Raw
    if ($text -notmatch 'Start-Local\.ps1') { throw 'cmd entry does not call Start-Local.ps1.' }
    if ($text -notmatch '%\*') { throw 'cmd entry does not forward arguments.' }
    if ($text -notmatch '-ExecutionPolicy Bypass') { throw 'cmd entry does not bypass the script execution policy.' }
    if ($text -match 'uvicorn|next start|docker compose') { throw 'cmd entry duplicates process management instead of forwarding.' }
}

Check 'launcher scripts parse without syntax errors' {
    foreach ($relative in @('Start-Local.ps1', 'Start-Demo.ps1', 'Stop-Local.ps1', 'scripts\local-runtime.ps1')) {
        $tokens = $null; $errors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path $projectRoot $relative), [ref]$tokens, [ref]$errors)
        if ($errors.Count) { throw "$relative has syntax errors: $($errors[0].Message)" }
    }
}

Check 'guide recommends the same entry and the self-service registration page' {
    # Locate the guide by pattern: this script must stay ASCII-only so Windows
    # PowerShell 5.1 reads it the same way regardless of the console code page.
    $guides = @(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'docs\guides') -Filter '*.md' -File)
    if (!$guides.Count) { throw 'No guide file found under docs/guides.' }
    $guide = ($guides | ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 }) -join "`n"
    if ($guide -notmatch 'Start-Local\.cmd') { throw 'guide does not mention Start-Local.cmd.' }
    if ($guide -notmatch '/register') { throw 'guide does not point at the registration page.' }
}

Check 'normal entry prints no secret values' {
    $text = Get-Content -LiteralPath (Join-Path $projectRoot 'Start-Local.ps1') -Raw
    # The key/environment values may only be read for validation, never written out.
    if ($text -match 'Write-Output[^\r\n]*\$apiKey') { throw 'Start-Local.ps1 prints the API key.' }
    if ($text -match 'Write-Output[^\r\n]*\$envPath') { throw 'Start-Local.ps1 prints the env file path.' }
    if ($text -match 'Write-Output[^\r\n]*(DATABASE_URL\s*=|postgresql(\+asyncpg)?://)') { throw 'Start-Local.ps1 prints a database URL.' }
    if ($text -notmatch 'http://127\.0\.0\.1:3000/register') { throw 'ready message does not point at the registration page.' }
    if ($text -notmatch 'APP_ENV') { throw 'ready message does not state the environment.' }
}

Check 'preflight either passes without starting services or names every failed path' {
    # A failing preflight writes to stderr; under Stop that becomes a terminating
    # NativeCommandError in Windows PowerShell 5.1, so judge it by exit code instead.
    $saved = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $projectRoot 'Start-Local.ps1') -CheckOnly 2>&1
        $exit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $saved }
    $text = ($output | ForEach-Object { [string]$_ }) -join "`n"
    if ($text -match 'CareerProof is ready') { throw 'Preflight started and announced services.' }
    if ($exit -eq 0) {
        if ($text -notmatch 'preflight passed') { throw 'Successful preflight did not report its result.' }
    } else {
        if ($text -notmatch 'Tried:') { throw 'Failure did not list the attempted environments.' }
        if ($text -notmatch '(\.venv[a-z0-9-]*|jianli|dep-frontend-[a-z0-9-]+)') { throw 'Failure did not name any attempted path.' }
        if ($text -match 'npm install|pip install|Install-Package') { throw 'Failure suggested installing instead of reporting the mismatch.' }
    }
}

Write-Output "$checks launcher-entry assertions passed; no services, containers, databases or files outside the project were touched."
exit 0
