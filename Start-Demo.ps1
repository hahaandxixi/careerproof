param(
    [string]$NodePath = 'node',
    [ValidatePattern('^auto$|^\.venv(?:-[a-z0-9-]+)?$')][string]$BackendVenv = 'auto',
    [ValidatePattern('^$|^[a-z0-9][a-z0-9-]{0,63}$')][string]$FrontendStage = 'auto',
    [switch]$SkipBuild,
    [switch]$Rebuild,
    [switch]$SkipSeed,
    [switch]$Reseed,
    [switch]$NoBrowser,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
if ($SkipSeed -and $Reseed) { throw 'Choose -SkipSeed or -Reseed, not both.' }
if ($SkipBuild -and $Rebuild) { throw 'Choose -SkipBuild or -Rebuild, not both.' }
$projectRoot = $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
. (Join-Path $projectRoot 'scripts\local-runtime.ps1')
$startScript = Join-Path $projectRoot 'Start-Local.ps1'
$envPath = Join-Path $backendRoot '.env'
$statePath = Join-Path $backendRoot '.tmp\local-run\processes.json'
$demoUrl = 'http://127.0.0.1:3000/demo'
$credentialsPath = Join-Path $backendRoot '.tmp\demo-credentials.json'

function New-RandomHex([int]$ByteCount) {
    $bytes = New-Object byte[] $ByteCount
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
}

function Ensure-DemoCredentials {
    $configured = @($env:DEMO_STUDENT_EMAIL, $env:DEMO_ENTERPRISE_EMAIL, $env:DEMO_PASSWORD)
    $provided = @($configured | Where-Object { ![string]::IsNullOrWhiteSpace($_) }).Count
    if ($provided -gt 0 -and $provided -lt 3) {
        throw 'Set DEMO_STUDENT_EMAIL, DEMO_ENTERPRISE_EMAIL and DEMO_PASSWORD together.'
    }
    if ($provided -eq 3 -or (Test-Path -LiteralPath $credentialsPath)) { return }

    $directory = Split-Path -Parent $credentialsPath
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $suffix = New-RandomHex 6
    $credentials = @{
        studentEmail = "demo-student-$suffix@example.com"
        enterpriseEmail = "demo-enterprise-$suffix@example.com"
        password = "Cp!1$(New-RandomHex 20)"
    } | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText(
        $credentialsPath, $credentials, (New-Object System.Text.UTF8Encoding($false))
    )
    Write-Output "Local demo credentials created at $credentialsPath (not committed)."
}

function Get-DemoSeedDigest {
    $digest = (Get-FileHash -LiteralPath (Join-Path $backendRoot 'evals\seed_demo.py')).Hash + (Get-FileHash -LiteralPath (Join-Path $backendRoot 'evals\seed_role_materials.py')).Hash
    if (Test-Path -LiteralPath $credentialsPath) { $digest += (Get-FileHash -LiteralPath $credentialsPath).Hash }
    return $digest
}

if (!(Test-Path -LiteralPath $startScript)) {
    throw 'Start-Local.ps1 is missing.'
}

$externalEnabled = Get-LocalEnvValue $envPath 'AI_EXTERNAL_ENABLED'
$provider = Get-LocalEnvValue $envPath 'AI_PROVIDER'
$apiKey = Get-LocalEnvValue $envPath 'DEEPSEEK_API_KEY'
if ((Get-LocalEnvValue $envPath 'APP_ENV') -ne 'development') {
    throw 'Demo accounts may only be seeded with APP_ENV=development in backend/.env.'
}
if ($externalEnabled -ne 'true' -or $provider -ne 'deepseek' -or [string]::IsNullOrWhiteSpace($apiKey)) {
    throw 'CareerProof requires AI_EXTERNAL_ENABLED=true, AI_PROVIDER=deepseek and a local DEEPSEEK_API_KEY in backend/.env. Rules are runtime fallback only.'
}

if ($CheckOnly) {
    & $startScript -NodePath $NodePath -BackendVenv $BackendVenv -FrontendStage $FrontendStage -CheckOnly
    if ($LASTEXITCODE -ne 0) { throw 'Preflight failed.' }
    Write-Output 'DeepSeek configuration is present; the key was not printed.'
    Write-Output 'AI-first demo preflight passed; no services started.'
    return
}
$demoLock = $null
try {
New-Item -ItemType Directory -Path (Split-Path $statePath -Parent) -Force | Out-Null
try { $demoLock = [System.IO.File]::Open((Join-Path (Split-Path $statePath -Parent) 'demo-launcher.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
catch { throw 'Another demonstration is initializing. Wait for its launcher to finish.' }
$startParameters = @{ NodePath = $NodePath; BackendVenv = $BackendVenv; FrontendStage = $FrontendStage }
if ($SkipBuild) { $startParameters.SkipBuild = $true }
if ($Rebuild) { $startParameters.Rebuild = $true }
& $startScript @startParameters
if ($LASTEXITCODE -ne 0) { throw 'Local services did not start successfully.' }
$manifest = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$pythonPath = Join-Path $backendRoot "$($manifest.backendVenv)\Scripts\python.exe"
$seedMarker = Join-Path (Split-Path $statePath -Parent) 'demo-ready.json'
$seedDigest = Get-DemoSeedDigest
$seedReady = $false
if (!$Reseed -and (Test-Path -LiteralPath $seedMarker)) {
    try {
        $savedSeed = Get-Content -LiteralPath $seedMarker -Raw | ConvertFrom-Json
        $seedReady = $savedSeed.runCreatedAt -eq $manifest.createdAt -and $savedSeed.seedDigest -eq $seedDigest -and (Test-Path -LiteralPath $credentialsPath) -and !($env:DEMO_STUDENT_EMAIL -or $env:DEMO_ENTERPRISE_EMAIL -or $env:DEMO_PASSWORD)
    } catch { $seedReady = $false }
}

if (!$SkipSeed -and !$seedReady) {
    if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Backend virtual environment is missing.' }
    Ensure-DemoCredentials
    Push-Location $backendRoot
    try {
        Invoke-LocalNative $pythonPath @('-m', 'evals.seed_demo')
        Invoke-LocalNative $pythonPath @('-m', 'evals.seed_role_materials', '--apply')
    } finally {
        Pop-Location
    }
    @{ runCreatedAt = $manifest.createdAt; seedDigest = (Get-DemoSeedDigest) } | ConvertTo-Json | Set-Content -LiteralPath $seedMarker -Encoding utf8
} elseif ($seedReady) {
    Write-Output 'Existing demonstration initialization reused; add -Reseed to rerun its idempotent seeders.'
}

Write-Output "CareerProof AI demo is ready: $demoUrl"
if ($SkipSeed) { Write-Output 'Demonstration initialization was skipped; existing data was not verified.' }
else { Write-Output "Demo accounts and synthetic jobs are ready. Read credentials from $credentialsPath or the configured DEMO_* environment variables. No API key was printed or changed." }
Write-Output 'Local rules run automatically only when AI cannot produce an accepted result.'
Write-Output 'Stop website with Stop-Demo.cmd; add -Database only when PostgreSQL is no longer needed.'

if (!$NoBrowser) {
    Start-Process $demoUrl
}
} finally { if ($demoLock) { $demoLock.Dispose() } }
