$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$manifestPath = Join-Path $PSScriptRoot 'cleanup.json'
$plan = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (![string]::Equals($root, $plan.root, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected workspace root.' }
$boundary = $root.TrimEnd('\') + '\'
$runtimePath = Join-Path $root 'backend/.tmp/local-run/processes.json'
$runtime = Get-Content -LiteralPath $runtimePath -Raw | ConvertFrom-Json
if ($runtime.frontendRoot -ne $plan.activeFrontend) { throw 'Runtime changed since inventory.' }
$live = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(node|python|pythonw)\.exe$' })
$testsRunning = @($live | Where-Object { $_.CommandLine -match '(?:-m\s+pytest|pytest\.exe|node(?:\.exe)?\s+.*--test)' })
$results = @()
$runMarker = Join-Path $PSScriptRoot 'cleanup-started.txt'
if (Test-Path -LiteralPath $runMarker) { throw 'One-shot cleanup already started; inspect results instead of rerunning.' }
[IO.File]::WriteAllText($runMarker, [DateTime]::UtcNow.ToString('o'))

function Assert-PlainTree([string]$absolute) {
    $ancestor = $absolute
    while ($ancestor -and ![string]::Equals($ancestor, $root, [StringComparison]::OrdinalIgnoreCase)) {
        $item = Get-Item -LiteralPath $ancestor -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse point in target ancestry.' }
        $ancestor = Split-Path -Parent $ancestor
    }
    if (!$ancestor) { throw 'Target has no workspace ancestor.' }
    $stack = New-Object 'System.Collections.Generic.Stack[string]'
    $stack.Push($absolute)
    while ($stack.Count) {
        foreach ($entry in Get-ChildItem -LiteralPath $stack.Pop() -Force) {
            if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse point inside target.' }
            if ($entry.PSIsContainer) { $stack.Push($entry.FullName) }
        }
    }
}

foreach ($candidate in $plan.candidates) {
    if ($candidate.status -ne 'planned') { continue }
    $absolute = [IO.Path]::GetFullPath($candidate.path)
    $row = [ordered]@{ path = $absolute; beforeBytes = $candidate.bytes; beforeFiles = $candidate.files; status = 'skipped'; reason = '' }
    try {
        if (!$absolute.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase)) { throw 'Outside workspace boundary.' }
        if (!(Test-Path -LiteralPath $absolute -PathType Container)) { throw 'Candidate missing or no longer a directory.' }
        $resolved = (Resolve-Path -LiteralPath $absolute).Path
        if (![string]::Equals($resolved, $absolute, [StringComparison]::OrdinalIgnoreCase)) { throw 'Resolved target differs.' }
        $active = [IO.Path]::GetFullPath($runtime.frontendRoot).TrimEnd('\')
        if ($absolute.StartsWith($active + '\', [StringComparison]::OrdinalIgnoreCase) -or $active.StartsWith($absolute + '\', [StringComparison]::OrdinalIgnoreCase) -or $active -eq $absolute) { throw 'Active runtime overlap.' }
        if ($testsRunning.Count -and $candidate.reason.StartsWith('pytest')) { throw 'A live test process exists; preserve all basetemps.' }
        foreach ($process in $live) {
            if ($process.CommandLine -and ($process.CommandLine.IndexOf($absolute, [StringComparison]::OrdinalIgnoreCase) -ge 0)) { throw "Live process $($process.ProcessId) references target." }
        }
        Assert-PlainTree $absolute
        # One shell end-to-end; exact LiteralPath only. No ACL changes or cross-shell deletion.
        Remove-Item -LiteralPath $absolute -Recurse -Force
        $row.status = 'deleted'
    }
    catch {
        $row.status = if (Test-Path -LiteralPath $absolute) { 'retained-or-partial' } else { 'removed-with-error' }
        $row.reason = $_.Exception.GetType().Name + ': ' + $_.Exception.Message
    }
    $results += [pscustomobject]$row
}
$results | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'deletion-results.json') -Encoding UTF8
[pscustomobject]@{ Deleted = @($results | Where-Object status -eq 'deleted').Count; Other = @($results | Where-Object status -ne 'deleted').Count } | ConvertTo-Json -Compress
