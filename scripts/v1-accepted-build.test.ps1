# Windows PowerShell 5.1 offline fixtures. Every process, native command, HTTP
# request and port query is a substitute. Never invokes real Docker/API/Next/DB.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$scratch = Join-Path $projectRoot ('backend\.tmp\v1-build-tests-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $scratch -Force | Out-Null
$sourceId = 'a' * 40
$global:cpV1Fixture = @{}
$checks = 0
function Assert([bool]$Ok, [string]$Message) { if (!$Ok) { throw $Message } }
function Json([string]$Path, $Value) { $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $Path -Encoding UTF8 }
function Check([string]$Name, [scriptblock]$Probe) { & $Probe; $script:checks++; Write-Output "PASS $Name" }
function Make-Build([string]$Front, [string]$Dist, [string]$Id) {
    $root = Join-Path $Front $Dist
    foreach ($dir in @('server/app', 'server/pages', 'static/chunks', "static/$Id")) { New-Item -ItemType Directory -Path (Join-Path $root $dir) -Force | Out-Null }
    foreach ($file in @('server/webpack-runtime.js', 'server/app/page.js', 'server/pages/_app.js', 'static/chunks/main.js', 'static/chunks/lazy.js', "static/$Id/_buildManifest.js")) { 'fixture' | Set-Content -LiteralPath (Join-Path $root $file) -Encoding UTF8 }
    $Id | Set-Content -LiteralPath (Join-Path $root 'BUILD_ID') -Encoding UTF8
    Json (Join-Path $root 'routes-manifest.json') @{ rewrites = @{ beforeFiles=@(); afterFiles=@(@{source='/backend/:path*';destination='http://127.0.0.1:8140/:path*'}); fallback=@() } }
    Json (Join-Path $root 'server/app-paths-manifest.json') @{'/page'='app/page.js'}
    Json (Join-Path $root 'server/pages-manifest.json') @{'/_app'='pages/_app.js'}
    Json (Join-Path $root 'build-manifest.json') @{rootMainFiles=@('static/chunks/main.js');polyfillFiles=@();lowPriorityFiles=@("static/$Id/_buildManifest.js");pages=@{'/_app'=@('static/chunks/main.js')}}
    Json (Join-Path $root 'app-build-manifest.json') @{pages=@{'/page'=@('static/chunks/main.js')}}
    Json (Join-Path $root 'react-loadable-manifest.json') @{fixture=@{files=@('static/chunks/lazy.js')}}
    Json (Join-Path $root 'required-server-files.json') @{config=@{distDir=$Dist};files=@("$Dist/BUILD_ID","$Dist/routes-manifest.json","$Dist/server/app-paths-manifest.json")}
}
function New-Fixture {
    $root = Join-Path $scratch ([guid]::NewGuid().ToString('N'))
    foreach ($dir in @('scripts','backend/app','backend/.tmp','jianli')) { New-Item -ItemType Directory -Path (Join-Path $root $dir) -Force | Out-Null }
    foreach ($name in @('Start-V1.ps1','Select-V1Build.ps1','scripts/local-runtime.ps1','scripts/local-frontend-build.ps1')) { Copy-Item -LiteralPath (Join-Path $projectRoot $name) -Destination (Join-Path $root $name) }
    'fixture' | Set-Content -LiteralPath (Join-Path $root 'backend/app/fixture.py') -Encoding UTF8
    '[project]' | Set-Content -LiteralPath (Join-Path $root 'backend/pyproject.toml') -Encoding UTF8
    'fixture-only, not a business configuration' | Set-Content -LiteralPath (Join-Path $root 'backend/.env') -Encoding UTF8
    Make-Build (Join-Path $root 'jianli') '.next' 'old-build'
    Make-Build (Join-Path $root 'jianli') '.next-accepted' 'new-build'
    $global:cpV1Fixture.case = @{Root=$root;Profile=(Join-Path $root 'backend/.tmp/unified-runtime.private.json');State=(Join-Path $root 'backend/.tmp/v1-run/processes.json')}
    Json $global:cpV1Fixture.case.Profile @{python='Fixture-Python';node='fixture-node';container='fixture-container'}
    $global:cpV1Fixture.live=@{}; $global:cpV1Fixture.ports=@{}; $global:cpV1Fixture.starts=@(); $global:cpV1Fixture.native=@(); $global:cpV1Fixture.health=@(); $global:cpV1Fixture.stops=@()
    $global:cpV1Fixture.denyPath=''; $global:cpV1Fixture.reparsePath=''; $global:cpV1Fixture.wrongHealth=$false; $global:cpV1Fixture.migrationFails=$false; $global:cpV1Fixture.sequence=0
    $global:cpV1Fixture.appConfig=@{AI_PROVIDER='deepseek';AI_EXTERNAL_ENABLED='true';DEEPSEEK_API_KEY='fixture-only-not-a-real-key';DATABASE_URL='postgresql+asyncpg://fixture/careerproof_v1';NEXT_DIST_DIR='.next-env-injection';BACKEND_ORIGIN='http://127.0.0.1:8999'}
}
function Select-Fixture([string]$Dist='.next-accepted',[string]$Id='new-build') {
    $messages = & (Join-Path $global:cpV1Fixture.case.Root 'Select-V1Build.ps1') -DistDir $Dist -BuildId $Id -SourceCommit $sourceId
    Assert (($messages -join '') -match 'No services') 'Selection did not identify its offline boundary.'
}
function Start-Fixture { & (Join-Path $global:cpV1Fixture.case.Root 'Start-V1.ps1') | Out-Null }
function No-Startup { Assert ($global:cpV1Fixture.starts.Count -eq 0 -and !@($global:cpV1Fixture.native | Where-Object { $_ -in @('docker','migration') }).Count) 'Invalid preflight reached a start or migration.' }
function Reject([scriptblock]$Operation,[string]$Pattern) {
    $failed=$false
    try { & $Operation | Out-Null } catch { $failed=$true; Assert ($_.Exception.Message -match $Pattern) "Unexpected refusal: $($_.Exception.Message)" }
    Assert $failed 'Expected refusal did not occur.'
}
# Executable names below exist only as functions in this test process.
function Fixture-Python {
    $global:LASTEXITCODE=0
    if ($args -contains '-c') { return ($global:cpV1Fixture.appConfig | ConvertTo-Json -Compress) }
    if ($args -contains 'alembic') { $global:cpV1Fixture.native+='migration'; if($global:cpV1Fixture.migrationFails){$global:LASTEXITCODE=7}; return }
    throw 'Unexpected fixture Python command.'
}
function docker { $global:cpV1Fixture.native+='docker'; $global:LASTEXITCODE=0 }
function git { $global:LASTEXITCODE=0; return $sourceId }
function Start-Process {
    param($FilePath,$ArgumentList,$WorkingDirectory,$WindowStyle,[switch]$PassThru,$RedirectStandardOutput,$RedirectStandardError)
    Assert ($FilePath -in @('Fixture-Python','fixture-node')) 'Unexpected executable was requested.'
    Assert ($WindowStyle -eq 'Hidden') 'Launcher would expose an unnecessary window.'
    $global:cpV1Fixture.sequence++; $number=70000+$global:cpV1Fixture.sequence
    $started=([datetime]'2026-11-01T00:00:00Z').AddSeconds($global:cpV1Fixture.sequence)
    $command=$FilePath+' '+($ArgumentList -join ' ')
    $global:cpV1Fixture.live[$number]=@{StartTime=$started;CommandLine=$command}
    $port=if($FilePath -eq 'fixture-node'){3140}else{8140};$global:cpV1Fixture.ports[$port]=$number
    $global:cpV1Fixture.starts+=@{Id=$number;File=$FilePath;Dist=$env:NEXT_DIST_DIR;Api=$env:BACKEND_ORIGIN}
    return [pscustomobject]@{Id=$number;StartTime=$started}
}
function Get-Process { param($Id,$ErrorAction) if($global:cpV1Fixture.live.ContainsKey([int]$Id)){return [pscustomobject]@{StartTime=$global:cpV1Fixture.live[[int]$Id].StartTime}} }
function Get-CimInstance {
    param($ClassName,$Filter)
    $rows=@(foreach($number in $global:cpV1Fixture.live.Keys){[pscustomobject]@{ProcessId=$number;ParentProcessId=0;CreationDate=$global:cpV1Fixture.live[$number].StartTime;CommandLine=$global:cpV1Fixture.live[$number].CommandLine}})
    if($Filter){$number=[int]($Filter -replace '\D','');return $rows|Where-Object ProcessId -eq $number};return $rows
}
function Get-NetTCPConnection { param($LocalPort,$State,$ErrorAction) if($global:cpV1Fixture.ports.ContainsKey([int]$LocalPort)){return [pscustomobject]@{OwningProcess=$global:cpV1Fixture.ports[[int]$LocalPort]}} }
function Stop-Process {
    param($Id,[switch]$Force,$ErrorAction)
    Assert ($global:cpV1Fixture.live.ContainsKey([int]$Id)) 'Attempt to stop an unowned process.'
    $global:cpV1Fixture.stops+=[int]$Id;$global:cpV1Fixture.live.Remove([int]$Id)
    foreach($port in @($global:cpV1Fixture.ports.Keys)){if($global:cpV1Fixture.ports[$port] -eq [int]$Id){$global:cpV1Fixture.ports.Remove($port)}}
}
function Invoke-WebRequest {
    param($Uri,$TimeoutSec,[switch]$UseBasicParsing)
    $global:cpV1Fixture.health+=$Uri
    if($global:cpV1Fixture.wrongHealth -and $Uri -match '/_next/'){throw 'Fixture server is serving another build.'}
    return [pscustomobject]@{StatusCode=200}
}
function Start-Sleep { param($Milliseconds) }
function Get-Item {
    param($LiteralPath,[switch]$Force,$ErrorAction)
    if($global:cpV1Fixture.denyPath -and $LiteralPath.StartsWith($global:cpV1Fixture.denyPath,[StringComparison]::OrdinalIgnoreCase)){throw [UnauthorizedAccessException]::new('Fixture directory access denied.')}
    if($global:cpV1Fixture.reparsePath -and $LiteralPath -eq $global:cpV1Fixture.reparsePath){return [pscustomobject]@{FullName=$LiteralPath;PSIsContainer=$true;Attributes=[IO.FileAttributes]::ReparsePoint}}
    Microsoft.PowerShell.Management\Get-Item @PSBoundParameters
}

Check 'explicit selection persists without starting anything' {
    New-Fixture;Select-Fixture;No-Startup
    $profile=Get-Content -LiteralPath $global:cpV1Fixture.case.Profile -Raw|ConvertFrom-Json
    Assert ($profile.frontendBuild.distDir -eq '.next-accepted' -and $profile.frontendBuild.buildId -eq 'new-build' -and $profile.python -eq 'Fixture-Python') 'Selection or existing profile fields lost.'
}
Check 'cold start ignores old default and inherited env; records the actual selected build' {
    $oldDist=$env:NEXT_DIST_DIR;$oldApi=$env:BACKEND_ORIGIN
    try{
        $env:NEXT_DIST_DIR='.next-foreign';$env:BACKEND_ORIGIN='http://127.0.0.1:8888'
        Start-Fixture
        $manifest=Get-Content -LiteralPath $global:cpV1Fixture.case.State -Raw|ConvertFrom-Json
        Assert ($manifest.frontendDistDir -eq '.next-accepted' -and $manifest.buildId -eq 'new-build' -and $manifest.frontendSourceCommit -eq $sourceId) 'Manifest does not identify the selected artifact.'
        Assert ($global:cpV1Fixture.starts[1].Dist -eq '.next-accepted' -and $global:cpV1Fixture.starts[1].Api -eq 'http://127.0.0.1:8140') 'Child inherited an unaccepted directory or API.'
        Assert ($env:NEXT_DIST_DIR -eq '.next-foreign' -and $env:BACKEND_ORIGIN -eq 'http://127.0.0.1:8888') 'Caller environment was not restored.'
        Assert ($global:cpV1Fixture.health -contains 'http://127.0.0.1:3140/_next/static/new-build/_buildManifest.js') 'Ready check does not identify the actual build.'
    }finally{$env:NEXT_DIST_DIR=$oldDist;$env:BACKEND_ORIGIN=$oldApi}
}
Check 'reuse keeps identities and build checks without another start or migration' {
    $count=$global:cpV1Fixture.native.Count;Start-Fixture
    Assert ($global:cpV1Fixture.starts.Count -eq 2 -and $global:cpV1Fixture.native.Count -eq $count) 'Reuse started another service or migration.'
}
Check 'stop removes only process record; next cold start retains accepted selection' {
    $before=(Get-FileHash -LiteralPath $global:cpV1Fixture.case.Profile).Hash
    & (Join-Path $global:cpV1Fixture.case.Root 'Start-V1.ps1') -Stop|Out-Null
    Assert (!(Test-Path -LiteralPath $global:cpV1Fixture.case.State) -and (Get-FileHash -LiteralPath $global:cpV1Fixture.case.Profile).Hash -eq $before) 'Stop removed the persistent selection.'
    Start-Fixture;Assert ($global:cpV1Fixture.starts[-1].Dist -eq '.next-accepted') 'Restart reverted to the old default.'
}
Check 'selection refuses an active owned run' { $before=(Get-FileHash -LiteralPath $global:cpV1Fixture.case.Profile).Hash;Reject {Select-Fixture} 'Stop the owned';Assert ((Get-FileHash -LiteralPath $global:cpV1Fixture.case.Profile).Hash -eq $before) 'Active selection changed.' }
Check 'missing selection does not fall back to a valid old .next' { New-Fixture;Reject {Start-Fixture} 'selection missing';No-Startup }
Check 'missing route, lazy chunk and metadata files fail before native work' {
    foreach($file in @('server/app/page.js','static/chunks/lazy.js','required-server-files.json')){New-Fixture;Select-Fixture;Remove-Item -LiteralPath (Join-Path $global:cpV1Fixture.case.Root "jianli/.next-accepted/$file");Reject {Start-Fixture} 'Cannot find';No-Startup}
}
Check 'wrong BUILD_ID and directory metadata are rejected' {
    New-Fixture;Select-Fixture;'other-build'|Set-Content -LiteralPath (Join-Path $global:cpV1Fixture.case.Root 'jianli/.next-accepted/BUILD_ID');Reject {Start-Fixture} 'BUILD_ID';No-Startup
    New-Fixture;Select-Fixture;$path=Join-Path $global:cpV1Fixture.case.Root 'jianli/.next-accepted/required-server-files.json';$v=Get-Content -LiteralPath $path -Raw|ConvertFrom-Json;$v.config.distDir='.next';Json $path $v;Reject {Start-Fixture} 'directory metadata';No-Startup
}
Check 'required files cannot borrow another build directory' {
    New-Fixture;Select-Fixture;$path=Join-Path $global:cpV1Fixture.case.Root 'jianli/.next-accepted/required-server-files.json'
    $v=Get-Content -LiteralPath $path -Raw|ConvertFrom-Json;$v.files=@('.next/BUILD_ID');Json $path $v
    Reject {Start-Fixture} 'outside the selected build';No-Startup
}
Check 'compiled wrong backend is rejected; selection failure preserves prior profile' {
    New-Fixture;Select-Fixture;$before=(Get-FileHash -LiteralPath $global:cpV1Fixture.case.Profile).Hash
    $path=Join-Path $global:cpV1Fixture.case.Root 'jianli/.next-accepted/routes-manifest.json';$v=Get-Content -LiteralPath $path -Raw|ConvertFrom-Json;$v.rewrites.afterFiles[0].destination='http://127.0.0.1:8164/:path*';Json $path $v
    Reject {Select-Fixture} 'Compiled frontend proxy';Assert ((Get-FileHash -LiteralPath $global:cpV1Fixture.case.Profile).Hash -eq $before) 'Failed selection damaged profile.'
    Reject {Start-Fixture} 'Compiled frontend proxy';No-Startup
}
Check 'outside, denied and reparse directories cannot reach a startup' {
    New-Fixture;Reject {Select-Fixture '../foreign' 'new-build'} 'selection missing';No-Startup
    New-Fixture;Select-Fixture;$global:cpV1Fixture.denyPath=Join-Path $global:cpV1Fixture.case.Root 'jianli/.next-accepted';Reject {Start-Fixture} 'access denied';No-Startup
    New-Fixture;Select-Fixture;$global:cpV1Fixture.reparsePath=Join-Path $global:cpV1Fixture.case.Root 'jianli/.next-accepted';Reject {Start-Fixture} 'reparse point';No-Startup
}
Check 'occupied 3140 or 8140 is never stopped or replaced' {
    foreach($port in @(3140,8140)){New-Fixture;Select-Fixture;$global:cpV1Fixture.ports[$port]=999;Reject {Start-Fixture} 'another run';No-Startup;Assert ($global:cpV1Fixture.stops.Count -eq 0) 'Foreign port was stopped.'}
}
Check 'reuse rejects wrong directory, source, config and process identity' {
    foreach($field in @('frontendDistDir','frontendSourceCommit','configHash')){
        New-Fixture;Select-Fixture;Start-Fixture;$m=Get-Content -LiteralPath $global:cpV1Fixture.case.State -Raw|ConvertFrom-Json;$m.$field='wrong';Json $global:cpV1Fixture.case.State $m
        Reject {Start-Fixture} 'code/config/build changed';Assert ($global:cpV1Fixture.starts.Count -eq 2 -and $global:cpV1Fixture.stops.Count -eq 0) 'Mismatch caused service changes.'
    }
    New-Fixture;Select-Fixture;Start-Fixture;$global:cpV1Fixture.live[$global:cpV1Fixture.starts[1].Id].CommandLine='foreign';Reject {Start-Fixture} 'command changed';Assert ($global:cpV1Fixture.starts.Count -eq 2) 'Unowned process was reused.'
}
Check 'reuse requires the selected build URL, not just a healthy home page' { New-Fixture;Select-Fixture;Start-Fixture;$global:cpV1Fixture.wrongHealth=$true;Reject {Start-Fixture} 'owned health check';Assert ($global:cpV1Fixture.starts.Count -eq 2) 'Bad health restarted services.' }
Check 'failed migration restores inherited environment and does not start processes' {
    New-Fixture;Select-Fixture;$global:cpV1Fixture.migrationFails=$true;$beforeDist=$env:NEXT_DIST_DIR;$beforeApi=$env:BACKEND_ORIGIN
    Reject {Start-Fixture} 'exit 7';Assert ($global:cpV1Fixture.starts.Count -eq 0 -and $env:NEXT_DIST_DIR -eq $beforeDist -and $env:BACKEND_ORIGIN -eq $beforeApi) 'Failure leaked env or started a process.'
}
Check 'explicit accepted default clears NEXT_DIST_DIR for next.config compatibility' {
    New-Fixture;Select-Fixture '.next' 'old-build';$old=$env:NEXT_DIST_DIR
    try{$env:NEXT_DIST_DIR='.next-foreign';Start-Fixture;Assert ([string]::IsNullOrEmpty($global:cpV1Fixture.starts[1].Dist)) 'Default .next was passed as an invalid NEXT_DIST_DIR.';Assert ($env:NEXT_DIST_DIR -eq '.next-foreign') 'Inherited env lost.'}finally{$env:NEXT_DIST_DIR=$old}
}
Write-Output "$checks offline V1 build-selection checks passed; no real services, containers, migrations or business data touched. Fixtures: $scratch"
