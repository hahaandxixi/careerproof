param(
    [string]$NodePath = 'node',
    [switch]$SkipBuild,
    [switch]$SkipSeed,
    [switch]$NoBrowser,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$startScript = Join-Path $projectRoot 'Start-Local.ps1'
$stopScript = Join-Path $projectRoot 'Stop-Local.ps1'
$pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
$envPath = Join-Path $backendRoot '.env'
$statePath = Join-Path $backendRoot '.tmp\local-run\processes.json'
$demoUrl = 'http://127.0.0.1:3000/demo'
$healthUrl = 'http://127.0.0.1:8000/api/v1/health'

function Test-HttpReady([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Get-DotEnvValue([string]$Path, [string]$Name) {
    if (!(Test-Path -LiteralPath $Path)) { return $null }
    $escapedName = [regex]::Escape($Name)
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match "^\s*$escapedName\s*=\s*(.*)\s*$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return $null
}

if (!(Test-Path -LiteralPath $startScript)) {
    throw 'Start-Local.ps1 is missing.'
}

$externalEnabled = Get-DotEnvValue $envPath 'AI_EXTERNAL_ENABLED'
$provider = Get-DotEnvValue $envPath 'AI_PROVIDER'
$apiKey = Get-DotEnvValue $envPath 'DEEPSEEK_API_KEY'
if ($externalEnabled -ne 'true' -or $provider -ne 'deepseek' -or [string]::IsNullOrWhiteSpace($apiKey)) {
    throw 'CareerProof requires AI_EXTERNAL_ENABLED=true, AI_PROVIDER=deepseek and a local DEEPSEEK_API_KEY in backend/.env. Rules are runtime fallback only.'
}

if ($CheckOnly) {
    & $startScript -NodePath $NodePath -CheckOnly
    if ($LASTEXITCODE -ne 0) { throw 'Preflight failed.' }
    Write-Output 'DeepSeek configuration is present; the key was not printed.'
    Write-Output 'AI-first demo preflight passed; no services started.'
    exit 0
}

$frontendReady = Test-HttpReady $demoUrl
$backendReady = Test-HttpReady $healthUrl

if ($frontendReady -xor $backendReady) {
    throw 'Only one service is responding. Stop or repair the partial run before using this launcher.'
}

if (!$frontendReady -and !$backendReady) {
    if (Test-Path -LiteralPath $statePath) {
        Write-Warning 'Found a previous local run record while both services are offline. Cleaning it safely before startup.'
        & $stopScript
        if (Test-Path -LiteralPath $statePath) {
            throw 'The stale local run record could not be cleared. Run Stop-Local.ps1 and inspect the recorded processes.'
        }
    }
    $startParameters = @{ NodePath = $NodePath }
    if ($SkipBuild) { $startParameters.SkipBuild = $true }
    & $startScript @startParameters
    if ($LASTEXITCODE -ne 0) { throw 'Local services did not start successfully.' }
} else {
    Write-Warning 'CareerProof is already running, so the AI startup configuration was not reapplied. Stop the existing run before restarting.'
}

if (!(Test-HttpReady $demoUrl) -or !(Test-HttpReady $healthUrl)) {
    throw 'Services did not pass the final health check.'
}

if (!$SkipSeed) {
    if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Backend virtual environment is missing.' }
    Push-Location $backendRoot
    try {
        & $pythonPath -m evals.seed_demo
        if ($LASTEXITCODE -ne 0) { throw 'Demo account and job initialization failed.' }
    } finally {
        Pop-Location
    }
}

Write-Output "CareerProof AI demo is ready: $demoUrl"
Write-Output 'Demo accounts and synthetic jobs are ready. No API key was printed or changed.'
Write-Output 'Local rules run automatically only when AI cannot produce an accepted result.'
Write-Output 'Stop with .\Stop-Local.ps1 -Database when the demonstration is finished.'

if (!$NoBrowser) {
    Start-Process $demoUrl
}
