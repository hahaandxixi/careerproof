param(
    [ValidateSet('Rules', 'AI')]
    [string]$Mode = 'Rules',
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
$pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
$envPath = Join-Path $backendRoot '.env'
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

if ($Mode -eq 'AI') {
    $externalEnabled = Get-DotEnvValue $envPath 'AI_EXTERNAL_ENABLED'
    $provider = Get-DotEnvValue $envPath 'AI_PROVIDER'
    $apiKey = Get-DotEnvValue $envPath 'DEEPSEEK_API_KEY'
    if ($externalEnabled -ne 'true' -or $provider -ne 'deepseek' -or [string]::IsNullOrWhiteSpace($apiKey)) {
        throw 'AI mode requires AI_EXTERNAL_ENABLED=true, AI_PROVIDER=deepseek and a local DEEPSEEK_API_KEY in backend/.env.'
    }
}

if ($CheckOnly) {
    & $startScript -NodePath $NodePath -CheckOnly
    if ($LASTEXITCODE -ne 0) { throw 'Preflight failed.' }
    if ($Mode -eq 'AI') { Write-Output 'DeepSeek configuration is present; the key was not printed.' }
    Write-Output "Demo preflight passed for $Mode mode; no services started."
    exit 0
}

$frontendReady = Test-HttpReady $demoUrl
$backendReady = Test-HttpReady $healthUrl

if ($frontendReady -xor $backendReady) {
    throw 'Only one service is responding. Stop or repair the partial run before using this launcher.'
}

if (!$frontendReady -and !$backendReady) {
    $startParameters = @{ NodePath = $NodePath }
    if ($SkipBuild) { $startParameters.SkipBuild = $true }
    if ($Mode -eq 'Rules') { $startParameters.RulesOnly = $true }
    & $startScript @startParameters
    if ($LASTEXITCODE -ne 0) { throw 'Local services did not start successfully.' }
} else {
    Write-Warning 'CareerProof is already running. The requested mode was not reapplied. Stop it first when you need to change modes.'
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

Write-Output "CareerProof demo is ready in $Mode mode: $demoUrl"
Write-Output 'Demo accounts and synthetic jobs are ready. No API key was printed or changed.'
Write-Output 'Stop with .\Stop-Local.ps1 -Database when the demonstration is finished.'

if (!$NoBrowser) {
    Start-Process $demoUrl
}
