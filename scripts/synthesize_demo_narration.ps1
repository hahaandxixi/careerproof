param([Parameter(Mandatory=$true)][string]$Manifest, [Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$story = Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
if ($story.rate -lt -2 -or $story.rate -gt 2) { throw 'Unsupported speech rate.' }
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Refusing to overwrite narration directory.' }
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speaker.SelectVoice([string]$story.voice)
    if ($speaker.Voice.Culture.Name -ne 'zh-CN') { throw 'Mandarin voice required.' }
    $speaker.Rate = [int]$story.rate
    New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
    foreach ($part in $story.parts) {
        if ($part.name -notmatch '^(intro|outro|technology|clip-[0-9]{2})$') { throw 'Invalid part name.' }
        if ([string]::IsNullOrWhiteSpace($part.text)) { throw 'Empty narration.' }
        $path = Join-Path $OutputDirectory ($part.name + '.wav')
        if (Test-Path -LiteralPath $path) { throw 'Duplicate narration part.' }
        $speaker.SetOutputToWaveFile($path)
        $speaker.Speak([string]$part.text)
        $speaker.SetOutputToNull()
        Write-Output ($part.name + ' synthesized offline')
    }
} finally { $speaker.Dispose() }
