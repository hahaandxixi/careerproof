$ErrorActionPreference = 'Continue'
# Repro harness for the E2E-01 fix rounds (2026-10-05, free GLM-5.3 trial).
# Round 3: asyncpg close() fix regressions plus evidence logs rewritten to a
# single encoding - PS5 Tee-Object writes UTF-16 while Add-Content defaults to
# ANSI, and mixing them produced NUL bytes. Every file write below is explicit
# UTF8 (Set-Content/Add-Content -Encoding utf8); command output is captured in
# full (no tail) and native exit codes come from $LASTEXITCODE.
# Lives beside check-ps-parse.ps1; the repo root is four levels up.
$evidence = Split-Path -Parent $PSScriptRoot
$repoRoot = (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))))
$backend = Join-Path $repoRoot 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$results = [ordered]@{}
Set-Location $backend

function Invoke-Logged {
    param([string]$LogFile, [scriptblock]$Block)
    $output = & $Block 2>&1
    $code = $LASTEXITCODE
    $output | Set-Content -LiteralPath $LogFile -Encoding utf8
    # Write-Host keeps the console echo out of the function's output stream;
    # Write-Output here made every $results entry an Object[] of log lines
    # plus the exit code, so no check could ever report a real exit code.
    $output | ForEach-Object { Write-Host $_ }
    return $code
}

# 1. Full isolation/safety regression file, complete output, real exit code.
$results['pytest'] = Invoke-Logged -LogFile (Join-Path $evidence 'tests.log') -Block {
    & $python -m pytest app/tests/test_e2e_fixture_safety.py -q -p no:cacheprovider --basetemp .tmp/pytest-glm53-e2e-a
}

# 2. Ruff over the two owned Python files.
$results['ruff'] = Invoke-Logged -LogFile (Join-Path $evidence 'ruff.log') -Block {
    & $python -m ruff check evals/seed_e2e.py app/tests/test_e2e_fixture_safety.py
}

# 3. PowerShell syntax parse of both E2E scripts (read-only; the scripts are
#    Codex-reviewed this round and are not modified here).
$parseLog = Join-Path $evidence 'ps-parse.log'
Remove-Item -LiteralPath $parseLog -ErrorAction SilentlyContinue
$parseFailed = $false
foreach ($rel in @('scripts/Start-E2E.ps1', 'scripts/Stop-E2E.ps1')) {
    $tokens = $null; $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $repoRoot $rel), [ref]$tokens, [ref]$errors) | Out-Null
    if ($errors.Count -gt 0) {
        $parseFailed = $true
        "$rel PARSE ERRORS:" | Add-Content -Path $parseLog -Encoding utf8
        $errors | ForEach-Object { $_.Message | Add-Content -Path $parseLog -Encoding utf8 }
    } else {
        "$rel`: syntax OK (parsed under PowerShell $($PSVersionTable.PSVersion))" | Add-Content -Path $parseLog -Encoding utf8
    }
}
$results['ps-parse'] = [int]$parseFailed

# 4. Cross-check: a PowerShell 5 style manifest write (Set-Content -Encoding utf8
#    BOM, camelCase keys, .NET 'o' UTC stamps) is exactly what the Python seeder
#    reads back through utf-8-sig + parse_utc_timestamp. Key names and timestamp
#    parsing only - process liveness is covered by the unit tests.
$compatLog = Join-Path $evidence 'ps-python-manifest-compat.log'
$compatJson = Join-Path $backend '.tmp\e2e-compat-manifest.json'
Remove-Item -LiteralPath $compatLog -ErrorAction SilentlyContinue
$started = (Get-Date).ToUniversalTime().ToString('o')
[ordered]@{
    runId = 'e2e-card01'; createdAt = $started; backendPort = 8001; frontendPort = 3001
    databaseName = 'cp_e2e_e2e-card01'; storageDir = (Join-Path $backend '.tmp\e2e-storage\e2e-card01')
    distDir = '.next-e2e'; aiExternalEnabled = 'false'; aiProvider = 'mock'
    backend = [ordered]@{ id = $PID; startedAt = $started; needle = 'python.exe' }
    processes = @([ordered]@{ id = $PID; startedAt = $started; needle = 'python.exe' })
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $compatJson -Encoding utf8
$head = [System.IO.File]::ReadAllBytes($compatJson)[0..2]
$bomText = (($head | ForEach-Object { $_.ToString('x2') }) -join '')
"PowerShell $($PSVersionTable.PSVersion) wrote the manifest via Set-Content -Encoding utf8; leading bytes: $bomText (BOM present: $($bomText -eq 'efbbbf'))" | Add-Content -Path $compatLog -Encoding utf8
$probeFile = Join-Path $backend '.tmp\e2e-compat-check.py'
@'
import os
import sys

sys.path.insert(0, os.environ["E2E_COMPAT_BACKEND"])
from pathlib import Path

from evals.seed_e2e import load_startup_manifest, parse_utc_timestamp

manifest = load_startup_manifest(Path(sys.argv[1]))
assert manifest["backend"]["id"] == int(sys.argv[2]), "backend id key mismatch"
assert manifest["processes"][0]["startedAt"], "processes startedAt key mismatch"
stamp = parse_utc_timestamp(manifest["backend"]["startedAt"])
print(
    "manifest read back OK: backend.id=%s processes[0].needle=%r startedAt parsed as %s"
    % (manifest["backend"]["id"], manifest["processes"][0]["needle"], stamp.isoformat())
)
'@ | Set-Content -LiteralPath $probeFile -Encoding utf8
$env:E2E_COMPAT_BACKEND = $backend
$results['manifest-compat'] = Invoke-Logged -LogFile $compatLog -Block {
    & $python $probeFile $compatJson $PID
}
Remove-Item Env:E2E_COMPAT_BACKEND -ErrorAction SilentlyContinue

# 5. Every evidence log must decode as UTF-8 (BOM allowed) and contain no NUL
#    bytes - the round-2 logs mixed Tee-Object UTF-16 with Add-Content ANSI.
$logPaths = @((Join-Path $evidence 'tests.log'), (Join-Path $evidence 'ruff.log'), $parseLog, $compatLog)
$checkFile = Join-Path $backend '.tmp\e2e-logcheck.py'
@'
import pathlib
import sys

for path in sys.argv[1:]:
    data = pathlib.Path(path).read_bytes()
    data.decode("utf-8-sig")
    assert b"\x00" not in data, f"{path} contains NUL bytes"
print("all logs decode as utf-8, no NUL bytes")
'@ | Set-Content -LiteralPath $checkFile -Encoding utf8
$results['utf8-logs'] = Invoke-Logged -LogFile (Join-Path $evidence 'log-encoding.log') -Block {
    & $python $checkFile $logPaths
}

foreach ($key in $results.Keys) { Write-Output ("{0} exit={1}" -f $key, $results[$key]) }
$failed = @($results.Values | Where-Object { $_ -ne 0 })
if ($failed.Count -gt 0) { Write-Output 'CHECKS FAILED'; exit 1 }
Write-Output 'ALL CHECKS PASSED'
exit 0
