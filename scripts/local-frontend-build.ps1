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
    # Newly produced candidates require a contemporaneous source/artifact manifest.
    # Legacy accepted builds retain their historical evidence grade; never fabricate one.
    if ($Selection.distDir.StartsWith('.next-candidate-', [StringComparison]::Ordinal)) {
        $project = Split-Path -Parent $front.FullName
        $manifestPath = Resolve-LocalFrontendArtifact $project ('output/builds/' + $Selection.distDir + '/artifact-manifest.json')
        $provenance = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($provenance.schema -ne 1 -or $provenance.distDir -cne $Selection.distDir -or
            $provenance.buildId -cne $id -or $provenance.sourceBase -cne $Selection.sourceCommit -or
            !$provenance.capturedAt -or !$provenance.sealedAt -or
            !$provenance.inputFiles -or !$provenance.artifactFiles) {
            throw 'Candidate provenance identity is incomplete or differs from selection.'
        }
        foreach ($group in @(@{ Root=$front.FullName; Files=$provenance.inputFiles },
                            @{ Root=$root; Files=$provenance.artifactFiles })) {
            $entries = @($group.Files.PSObject.Properties)
            if (!$entries.Count) { throw 'Candidate provenance has no file hashes.' }
            foreach ($entry in $entries) {
                if ($entry.Value -isnot [string] -or $entry.Value -cnotmatch '\A[0-9a-f]{64}\z') { throw 'Invalid provenance hash.' }
                $file = Resolve-LocalFrontendArtifact $group.Root $entry.Name
                if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value) {
                    throw "Candidate provenance hash mismatch: $($entry.Name)"
                }
            }
        }
        # New/deleted source inputs also invalidate the candidate, not only changed bytes.
        $expectedInputs = @($provenance.inputFiles.PSObject.Properties.Name | Sort-Object)
        $actualInputs = @()
        foreach ($folder in @('src', 'public')) {
            $folderRoot = Join-Path $front.FullName $folder
            if (Test-Path -LiteralPath $folderRoot) {
                $pending = New-Object 'System.Collections.Generic.Stack[string]'
                $pending.Push($folderRoot)
                while ($pending.Count) {
                    foreach ($item in Get-ChildItem -LiteralPath $pending.Pop() -Force) {
                        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Candidate inputs cannot contain reparse points.' }
                        if ($item.PSIsContainer) { $pending.Push($item.FullName) }
                        else { $actualInputs += $item.FullName.Substring($front.FullName.Length + 1).Replace('\','/') }
                    }
                }
            }
        }
        $actualInputs += @(Get-ChildItem -LiteralPath $front.FullName -File | Where-Object {
            $_.Name -cmatch '^(package(?:-lock)?\.json|next\.config\..+|tsconfig\.json|next-env\.d\.ts|(?:postcss|tailwind)\.config\..+)$'
        } | ForEach-Object { $_.Name })
        if (Compare-Object ($actualInputs | Sort-Object) $expectedInputs -CaseSensitive) { throw 'Candidate source input set changed.' }
        # Match candidate-artifact.mjs: the seal covers the complete artifact
        # set except cache/ and trace, not just the files already in its map.
        $expectedArtifacts = @($provenance.artifactFiles.PSObject.Properties.Name | Sort-Object)
        $actualArtifacts = @()
        $pendingArtifacts = New-Object 'System.Collections.Generic.Stack[string]'
        $pendingArtifacts.Push($root)
        while ($pendingArtifacts.Count) {
            foreach ($item in Get-ChildItem -LiteralPath $pendingArtifacts.Pop() -Force) {
                if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Candidate artifacts cannot contain reparse points.' }
                if ($item.PSIsContainer) { $pendingArtifacts.Push($item.FullName) }
                else {
                    $relative = $item.FullName.Substring($root.Length + 1).Replace('\','/')
                    if ($relative -cne 'trace' -and !$relative.StartsWith('cache/', [StringComparison]::Ordinal)) {
                        $actualArtifacts += $relative
                    }
                }
            }
        }
        if (Compare-Object ($actualArtifacts | Sort-Object) $expectedArtifacts -CaseSensitive) { throw 'Candidate artifact file set changed.' }
    }
    # Start-V1's ready check requests this exact static file, even if the client manifest omits it.
    [void](Resolve-LocalFrontendArtifact $root "static/$id/_buildManifest.js")
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
