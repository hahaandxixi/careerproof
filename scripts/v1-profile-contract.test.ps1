# Offline only: reuse the launcher's fixture constructors and command substitutes.
$ErrorActionPreference = 'Stop'
$harnessPath = Join-Path $PSScriptRoot 'v1-accepted-build.test.ps1'
$source = Get-Content -LiteralPath $harnessPath -Raw -Encoding UTF8
$boundary = $source.IndexOf("Check 'explicit selection persists")
if ($boundary -lt 0) { throw 'Offline fixture harness boundary changed.' }
$fixtureProjectRoot = Split-Path -Parent $PSScriptRoot
$prefix = $source.Substring(0, $boundary).Replace(
    '$projectRoot = Split-Path -Parent $PSScriptRoot', '$projectRoot = $fixtureProjectRoot')
. ([scriptblock]::Create($prefix))

$marker = 'SYNTHETIC_PROFILE_SECRET_CONTRACT'
$valid = '{"python":"Fixture-Python","node":"fixture-node","container":"fixture-container","note":"' + $marker + '"}'
$cases = @(
    @{ Name='empty-object'; Raw='{}'; Expected='structurally invalid' },
    @{ Name='array'; Raw=('[' + $valid + ']'); Expected='structurally invalid' },
    @{ Name='scalar'; Raw=('"' + $marker + '"'); Expected='structurally invalid' },
    @{ Name='missing-key'; Raw='{"python":"Fixture-Python","node":"fixture-node"}'; Expected='structurally invalid' },
    @{ Name='blank-key'; Raw='{"python":"Fixture-Python","node":"fixture-node","container":" "}'; Expected='structurally invalid' },
    @{ Name='null'; Raw='null'; Expected='structurally invalid' },
    @{ Name='truncated'; Raw=('{"note":"' + $marker + '"'); Expected='unreadable JSON' },
    @{ Name='directory-read-failure'; Raw=$null; Expected='could not be read' }
)
foreach ($entry in @('Start', 'Select')) {
    foreach ($case in $cases) {
        Check "$entry rejects $($case.Name) without mutation or native actions" {
            New-Fixture
            $profile = $global:cpV1Fixture.case.Profile
            if ($null -eq $case.Raw) {
                # This is only a directory substitute, not an ACL acceptance test.
                Remove-Item -LiteralPath $profile
                New-Item -ItemType Directory -Path $profile | Out-Null
                $before = $null
            } else {
                [IO.File]::WriteAllText($profile, $case.Raw)
                $before = (Get-FileHash -LiteralPath $profile -Algorithm SHA256).Hash
            }
            $errorText = $null
            $output = @()
            try {
                if ($entry -eq 'Start') { $output = @(& (Join-Path $global:cpV1Fixture.case.Root 'Start-V1.ps1') 2>&1) }
                else { $output = @(Select-Fixture 2>&1) }
            } catch { $errorText = $_ | Out-String }
            Assert (![string]::IsNullOrEmpty($errorText)) 'Expected a refusal.'
            Assert ($errorText.Contains($case.Expected)) "Wrong branch for $($case.Name)."
            Assert (!(($output -join "`n") + $errorText).Contains($marker)) 'Synthetic marker leaked.'
            if ($null -ne $before) {
                Assert ((Get-FileHash -LiteralPath $profile -Algorithm SHA256).Hash -eq $before) 'Profile bytes changed.'
            } else { Assert (Test-Path -LiteralPath $profile -PathType Container) 'Read-failure substitute changed.' }
            No-Startup
            Assert ($global:cpV1Fixture.health.Count -eq 0) 'Unexpected HTTP action.'
            Assert (!(Test-Path -LiteralPath $global:cpV1Fixture.case.State)) 'Process state was written.'
        }
    }
}
Check 'valid profile preserves runtime keys and supports selection and substituted startup' {
    New-Fixture
    [IO.File]::WriteAllText($global:cpV1Fixture.case.Profile, $valid)
    Select-Fixture
    $selected = Get-Content -LiteralPath $global:cpV1Fixture.case.Profile -Raw | ConvertFrom-Json
    Assert ($selected.python -ceq 'Fixture-Python' -and $selected.node -ceq 'fixture-node' -and $selected.container -ceq 'fixture-container') 'Runtime keys changed.'
    Assert ($selected.frontendBuild.buildId -ceq 'new-build') 'Wrong build selected.'
    Start-Fixture
    Assert ($global:cpV1Fixture.starts.Count -eq 2) 'Valid fixture did not reach substituted startup.'
}
Write-Output "$checks profile contract checks passed; all native/process/HTTP actions were substitutes."
