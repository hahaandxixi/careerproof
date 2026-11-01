# Pure file validation shared by V1 selection and startup. No process actions.
function Resolve-LocalFrontendArtifact([string]$Root, [string]$Relative) {
    if ([string]::IsNullOrWhiteSpace($Relative) -or [IO.Path]::IsPathRooted($Relative)) { throw 'Frontend artifact must be a relative file.' }
    $parts = @($Relative -split '[\\/]')
    if (@($parts | Where-Object { $_ -in @('', '.', '..') }).Count) { throw "Frontend artifact escapes the selected build: $Relative" }
    $path = $Root
    foreach ($part in @('') + $parts) {
        if ($part) { $path = Join-Path $path $part }
        $item = Get-Item -LiteralPath $path -Force -ErrorAction Stop
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Frontend artifact cannot use a reparse point: $path" }
    }
    if ($item.PSIsContainer) { throw "Frontend artifact is not a file: $path" }
    return $path
}

function Get-LocalFrontendBuild([string]$FrontendRoot, $Selection) {
    if (!$Selection -or $Selection.distDir -isnot [string] -or
        ![regex]::IsMatch($Selection.distDir, '\A\.next(?:-[a-z0-9-]+)?\z') -or
        $Selection.buildId -isnot [string] -or ![regex]::IsMatch($Selection.buildId, '\A[A-Za-z0-9_-]{1,128}\z') -or
        $Selection.sourceCommit -isnot [string] -or ![regex]::IsMatch($Selection.sourceCommit, '\A[0-9a-f]{40}\z')) {
        throw 'Accepted frontend build selection missing or invalid. Use Select-V1Build.ps1; no fallback to .next.'
    }
    $front = Get-Item -LiteralPath $FrontendRoot -Force -ErrorAction Stop
    if (!$front.PSIsContainer -or ($front.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Frontend root must be the project directory, not a reparse point.' }
    $root = Join-Path $front.FullName $Selection.distDir
    $core = @('BUILD_ID', 'required-server-files.json', 'routes-manifest.json', 'build-manifest.json',
        'app-build-manifest.json', 'react-loadable-manifest.json', 'server/app-paths-manifest.json',
        'server/pages-manifest.json', 'server/webpack-runtime.js')
    foreach ($file in $core) { [void](Resolve-LocalFrontendArtifact $root $file) }
    $id = (Get-Content -LiteralPath (Join-Path $root 'BUILD_ID') -Raw -Encoding UTF8).Trim()
    if ($id -cne $Selection.buildId) { throw 'Selected frontend BUILD_ID does not match the accepted build.' }
    $required = Get-Content -LiteralPath (Join-Path $root 'required-server-files.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($required.config.distDir -cne $Selection.distDir -or $required.files -isnot [array] -or !$required.files.Count) { throw 'Frontend build directory metadata is inconsistent or incomplete.' }
    foreach ($file in $required.files) {
        $relative = ([string]$file).Replace('\', '/')
        $prefix = $Selection.distDir + '/'
        if (!$relative.StartsWith($prefix, [StringComparison]::Ordinal)) { throw 'Required frontend file is outside the selected build.' }
        [void](Resolve-LocalFrontendArtifact $root $relative.Substring($prefix.Length))
    }
    $routes = Get-Content -LiteralPath (Join-Path $root 'routes-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $rewrites = if ($routes.rewrites -is [array]) { @($routes.rewrites) } else {
        @($routes.rewrites.beforeFiles) + @($routes.rewrites.afterFiles) + @($routes.rewrites.fallback)
    }
    $proxy = @($rewrites | Where-Object { $_.source -ceq '/backend/:path*' })
    if ($proxy.Count -ne 1 -or $proxy[0].destination -cne 'http://127.0.0.1:8140/:path*') { throw 'Compiled frontend proxy must target the real API 8140; runtime BACKEND_ORIGIN cannot repair this build.' }
    foreach ($name in @('app-paths-manifest.json', 'pages-manifest.json')) {
        $server = Get-Content -LiteralPath (Join-Path $root "server/$name") -Raw -Encoding UTF8 | ConvertFrom-Json
        if (!$server -or !@($server.PSObject.Properties).Count) { throw "Empty frontend route manifest: $name" }
        foreach ($entry in $server.PSObject.Properties) { [void](Resolve-LocalFrontendArtifact $root ('server/' + $entry.Value)) }
    }
    $client = Get-Content -LiteralPath (Join-Path $root 'build-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $app = Get-Content -LiteralPath (Join-Path $root 'app-build-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $loadable = Get-Content -LiteralPath (Join-Path $root 'react-loadable-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if (!$client.rootMainFiles -or !$app.pages -or !@($app.pages.PSObject.Properties).Count) { throw 'Frontend client manifests are incomplete.' }
    $assets = @($client.rootMainFiles) + @($client.polyfillFiles) + @($client.lowPriorityFiles)
    foreach ($page in @($client.pages.PSObject.Properties) + @($app.pages.PSObject.Properties)) { $assets += @($page.Value) }
    foreach ($entry in $loadable.PSObject.Properties) { $assets += @($entry.Value.files) }
    foreach ($file in @($assets | Where-Object { $_ } | Sort-Object -Unique)) { [void](Resolve-LocalFrontendArtifact $root $file) }
    return [pscustomobject]@{ DistDir = $Selection.distDir; BuildId = $id; SourceCommit = $Selection.sourceCommit; Root = $root }
}
