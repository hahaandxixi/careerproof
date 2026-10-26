param([ValidateSet('Start','Stop','Accounts')][string]$Action = 'Start', [switch]$NoOpen)
$ErrorActionPreference = 'Stop'
$env:COMPOSE_ANSI = 'never'
$env:BUILDKIT_PROGRESS = 'plain'
$TrialRoot = Split-Path -Parent $PSScriptRoot
$TrialProject = 'careerproof-family-8ca91cc'
$LocalDir = Join-Path $TrialRoot '.local'
$ConfigPath = Join-Path $LocalDir 'trial.env'
$AccountsPath = Join-Path $LocalDir '本机试用账号.txt'
$LogDir = Join-Path $TrialRoot 'logs'
$script:TrialLog = $null
$script:DockerExe = $null
$script:ComposeArgs = @('--project-name', $TrialProject, '--project-directory', $TrialRoot, '--env-file', $ConfigPath, '-f', (Join-Path $TrialRoot 'compose.yaml'))

function New-HexSecret([int]$Length) {
    $bytes = New-Object byte[] $Length
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
}
function Invoke-TrialCompose([string[]]$Arguments) {
    $savedPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue' # Docker writes ordinary progress to stderr on Windows PowerShell 5.1.
    try {
    & $script:DockerExe compose @script:ComposeArgs @Arguments 2>&1 | ForEach-Object {
        $line = $_.ToString()
        Write-Host $line
        if ($script:TrialLog) { Add-Content -LiteralPath $script:TrialLog -Value $line -Encoding UTF8 -ErrorAction Stop }
    }
    $composeExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedPreference }
    if ($composeExit -ne 0) { throw ('操作失败（退出码 ' + $composeExit + '）。请保留 logs 文件夹，发给家里协助排查。') }
}

try {
    if ($Action -eq 'Accounts') {
        if (!(Test-Path -LiteralPath $AccountsPath)) { throw '请先运行 01-Start.cmd，启动成功后才能查看本机账号。' }
        if (!$NoOpen) { Start-Process -FilePath 'notepad.exe' -ArgumentList ('"' + $AccountsPath + '"') }
        Write-Host ('账号只保存在本机：' + $AccountsPath)
        exit 0
    }
    $dockerCommand = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($dockerCommand) { $script:DockerExe = $dockerCommand.Source }
    else {
        $knownDocker = Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'
        if (Test-Path -LiteralPath $knownDocker) { $script:DockerExe = $knownDocker }
    }
    if (!$script:DockerExe) { throw '尚未安装 Docker Desktop。请先双击“先读我.html”，按第一步安装并打开 Docker Desktop。' }
    $savedPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $engineType = & $script:DockerExe info --format '{{.OSType}}' 2>$null
        $engineExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedPreference }
    if ($engineExit -ne 0 -or $engineType -ne 'linux') { throw 'Docker 尚未就绪。请打开 Docker Desktop，等 Engine running；使用默认 Linux containers 模式，再重试。' }
    & $script:DockerExe compose version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw '未找到 Docker Compose，请完成 Docker Desktop 安装后重试。' }
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    $script:TrialLog = Join-Path $LogDir ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $Action + '.log')

    if ($Action -eq 'Stop') {
        if (!(Test-Path -LiteralPath $ConfigPath)) { throw '未找到本包启动配置。不会操作任何其他服务；如果曾使用过，请恢复原 .local 文件夹。' }
        Invoke-TrialCompose @('down', '--timeout', '30')
        Write-Host '已停止本试用包。材料、账号和报告保留，下次双击 01-Start.cmd 继续。'
        exit 0
    }

    if (!(Test-Path -LiteralPath $ConfigPath)) {
        $existingVolumes = & $script:DockerExe volume ls --filter ('label=com.docker.compose.project=' + $TrialProject) --format '{{.Name}}'
        if ($LASTEXITCODE -ne 0) { throw '无法核对本试用包的数据卷，已停止初始化。' }
        if ($existingVolumes) { throw '发现原试用数据，但缺少 .local/trial.env。请恢复原 .local 文件夹，不要重新生成密码或删除数据。' }
        New-Item -ItemType Directory -Path $LocalDir -Force | Out-Null
        $loginSecret = 'Cp-' + (New-HexSecret 10)
        $envContent = @(
            'TRIAL_DB_PASSWORD=' + (New-HexSecret 24)
            'TRIAL_JWT_SECRET=' + (New-HexSecret 32)
            'TRIAL_LOGIN_PASSWORD=' + $loginSecret
        ) -join "`n"
        [IO.File]::WriteAllText($ConfigPath, $envContent + "`n", (New-Object Text.UTF8Encoding $false))
        $accountText = "CareerProof 本机试用账号`r`n`r`n网址：http://127.0.0.1:3150`r`n学生账号：family.student@example.com`r`n企业账号：family.company@example.com`r`n两个账号的密码：$loginSecret`r`n`r`n这是首次启动时为本机生成的随机密码。请保留 .local 文件夹，不要随反馈转发。`r`n网站仅在本机可访问；这些账号不是儿子电脑上的账号。`r`n"
        [IO.File]::WriteAllText($AccountsPath, $accountText, (New-Object Text.UTF8Encoding $true))
    }
    if (!(Test-Path -LiteralPath $AccountsPath)) { throw '本机账号说明缺失。请恢复 .local 文件夹；程序不会擅自重置已有账号。' }

    $imagesManifestPath = Join-Path $TrialRoot 'images\manifest.json'
    $imagesTar = Join-Path $TrialRoot 'images\runtime.tar'
    if (!(Test-Path -LiteralPath $imagesManifestPath) -or !(Test-Path -LiteralPath $imagesTar)) {
        throw '运行组件缺失。请完整解压试用 ZIP，保留 images 文件夹。'
    }
    $imageManifest = Get-Content -LiteralPath $imagesManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($imageManifest.platform -ne 'linux/amd64' -or $imageManifest.sourceCommit -ne '8ca91cc2c8e32fbd59412134798eb7db257a29d4') {
        throw '运行组件清单与本试用版本不符。请使用同一个完整 ZIP。'
    }
    $missingImage = $false
    $savedPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        foreach ($entry in $imageManifest.images) {
            $actualId = & $script:DockerExe image inspect --format '{{.Id}}' $entry.tag 2>$null
            if ($LASTEXITCODE -ne 0 -or $actualId -ne $entry.id) { $missingImage = $true }
        }
    } finally { $ErrorActionPreference = $savedPreference }
    if ($missingImage) {
        Write-Host '正在核对并导入运行组件；首次需要几分钟，不用下载开发环境。'
        $actualHash = (Get-FileHash -LiteralPath $imagesTar -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $imageManifest.archiveSha256) { throw '运行组件校验失败，压缩包可能未完整传输。请重新接收原 ZIP。' }
        $savedPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            & $script:DockerExe load --input $imagesTar 2>&1 | ForEach-Object {
                Write-Host $_.ToString()
                Add-Content -LiteralPath $script:TrialLog -Value $_.ToString() -Encoding UTF8 -ErrorAction Stop
            }
            $loadExit = $LASTEXITCODE
        } finally { $ErrorActionPreference = $savedPreference }
        if ($loadExit -ne 0) { throw '运行组件导入失败。请保留日志，检查 Docker 可用磁盘空间。' }
    }
    foreach ($entry in $imageManifest.images) {
        $actualId = & $script:DockerExe image inspect --format '{{.Id}}' $entry.tag
        if ($LASTEXITCODE -ne 0 -or $actualId -ne $entry.id) { throw '导入后的运行组件版本不一致，已停止。' }
    }
    Write-Host '正在启动 CareerProof 试用包，不会下载镜像或调用外部 AI。'
    Invoke-TrialCompose @('config', '--quiet')
    Invoke-TrialCompose @('up', '--detach', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '240')
    Invoke-TrialCompose @('exec', '-T', 'backend', 'python', '-m', 'evals.seed_demo')
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:3150/backend/api/v1/health' -TimeoutSec 10
    if ($health.data.status -ne 'ok') { throw '页面到后端的连接未通过，请保留日志。' }
    Write-Host ''
    Write-Host '启动完成！网址：http://127.0.0.1:3150'
    Write-Host '请先用学生账号登录。外部 AI 已禁用，先体验规则报告，不勾选外部 AI。'
    Write-Host '关闭这个窗口不会停止网站。用完请双击 02-Stop.cmd。'
    if (!$NoOpen) {
        Start-Process -FilePath 'notepad.exe' -ArgumentList ('"' + $AccountsPath + '"')
        Start-Process 'http://127.0.0.1:3150/login'
    }
    exit 0
} catch {
    Write-Host ''
    Write-Host ('未完成：' + $_.Exception.Message) -ForegroundColor Red
    if ($script:TrialLog) { Add-Content -LiteralPath $script:TrialLog -Value $_.Exception.Message -Encoding UTF8 }
    Write-Host '请勿删除数据或反复重装。可截图此窗口，并保留 logs 中的日志。'
    exit 1
}
