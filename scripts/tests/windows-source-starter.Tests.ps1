$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$sourceDirectory = Join-Path $repoRoot 'distribution\windows-source'
$buildScript = Join-Path $repoRoot 'scripts\build-windows-source-starter.ps1'
$readmePath = Join-Path $sourceDirectory 'README-安装说明.txt'
$batchNames = @('01-check-environment.bat', '02-install-wecome-bot.bat', '03-start-wecome-bot.bat')
$requiredFiles = @($batchNames + 'README-安装说明.txt')

function Get-Sha256([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Read-Utf8([string]$Path) {
    [IO.File]::ReadAllText($Path, [Text.UTF8Encoding]::new($false))
}

Describe 'Windows Source Starter package' {
    BeforeAll {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $output = Join-Path $TestDrive 'Windows Source Starter 输出目录'
        & $buildScript -Version '0.1.0' -OutputDirectory $output
        if ($LASTEXITCODE -ne 0) { throw "Starter build failed with exit code $LASTEXITCODE" }
        $script:output = $output
        $script:zipPath = Join-Path $output 'Wecome-Bot-Source-Starter-v0.1.0.zip'
        $script:shaPath = $script:zipPath + '.sha256'
        $script:manifestPath = Join-Path $output 'starter-manifest.json'
        $script:manifest = Read-Utf8 $script:manifestPath | ConvertFrom-Json
    }

    It 'provides the build script, README, and three source BAT files' {
        Test-Path -LiteralPath $buildScript -PathType Leaf | Should Be $true
        foreach ($name in $requiredFiles) { Test-Path -LiteralPath (Join-Path $sourceDirectory $name) -PathType Leaf | Should Be $true }
    }

    It 'keeps source BAT files BOM-free, CRLF-terminated, and cmd-compatible' {
        foreach ($name in $batchNames) {
            $bytes = [IO.File]::ReadAllBytes((Join-Path $sourceDirectory $name))
            ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) | Should Be $false
            $text = [Text.UTF8Encoding]::new($false, $true).GetString($bytes)
            $text.StartsWith('@echo off') | Should Be $true
            $text | Should Not Match '(?m)(?<!\r)\n'
        }
    }

    It 'builds only the four expected files at the ZIP root with no nested directory' {
        $archive = [IO.Compression.ZipFile]::OpenRead($script:zipPath)
        try {
            @($archive.Entries | ForEach-Object FullName | Sort-Object) | Should Be @($requiredFiles | Sort-Object)
            @($archive.Entries | Where-Object { $_.FullName -match '/' }).Count | Should Be 0
        } finally { $archive.Dispose() }
    }

    It 'builds BOM-free CRLF BAT files and a readable Chinese README' {
        $extractRoot = Join-Path $TestDrive '解压验收'
        [IO.Compression.ZipFile]::ExtractToDirectory($script:zipPath, $extractRoot)
        foreach ($name in $batchNames) {
            $bytes = [IO.File]::ReadAllBytes((Join-Path $extractRoot $name))
            ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) | Should Be $false
            ([Text.UTF8Encoding]::new($false, $true).GetString($bytes)) | Should Not Match '(?m)(?<!\r)\n'
        }
        (Read-Utf8 (Join-Path $extractRoot 'README-安装说明.txt')) | Should Match '默认启用真实发送能力'
    }

    It 'keeps ZIP SHA-256 and manifest fields consistent with the package' {
        $actualHash = Get-Sha256 $script:zipPath
        ((Get-Content -LiteralPath $script:shaPath -Raw).Trim().Split()[0]) | Should Be $actualHash
        $script:manifest.product | Should Be 'Wecome Bot Source Starter'
        $script:manifest.starter_version | Should Be '0.1.0'
        $script:manifest.source_repository | Should Be 'wuli073/wecome-bot'
        $script:manifest.source_branch | Should Be 'main'
        $script:manifest.source_commit | Should Be ((& git -C $repoRoot rev-parse HEAD).Trim())
        $script:manifest.real_send_default_enabled | Should Be $true
        $script:manifest.asset_sha256 | Should Be $actualHash
        $script:manifest.asset_size | Should Be ([IO.FileInfo]$script:zipPath).Length
        @($script:manifest.files).Count | Should Be 4
        @($script:manifest.files | ForEach-Object { $_.relative_path } | Sort-Object) | Should Be @($requiredFiles | Sort-Object)
        (($script:manifest | ConvertTo-Json -Depth 6) -match '(?i)[A-Z]:\\Users\\') | Should Be $false
    }

    It 'documents installation, update, logs, stop, and enabled real sending' {
        $readme = Read-Utf8 $readmePath
        foreach ($text in @('系统要求', '安装步骤', '更新方式', '日志位置', '停止服务', '默认启用真实发送能力', '自动发送', '群发', 'Connector')) { $readme | Should Match $text }
        $readme | Should Not Match '真实发送默认关闭'
    }

    It 'copies README, excludes distribution files, and retains fixed prebuilt Runtime setup' {
        $installer = Read-Utf8 (Join-Path $sourceDirectory '02-install-wecome-bot.bat')
        $installer | Should Match 'README-安装说明\.txt'
        $installer | Should Match '/README-安装说明\.txt'
        $installer | Should Match 'Start-Transcript -LiteralPath \$setupLog -Append'
        $installer | Should Match 'prebuilt Desktop Runtime'
        $installer | Should Not Match 'releases/download'
    }

    It 'prints the non-blocking real sending notice without an interactive confirmation' {
        $starter = Get-Content -LiteralPath (Join-Path $sourceDirectory '03-start-wecome-bot.bat') -Raw
        $starter | Should Match 'NOTICE: Real message sending is enabled by default\.'
        $starter | Should Match 'Verify the configured account, connector, recipients, and message content before sending\.'
        $starter | Should Not Match 'Read-Host|set /p|choice'
    }

    It 'retains the enabled real-send defaults and runtime readiness requirement' {
        $startSource = Get-Content -LiteralPath (Join-Path $repoRoot 'scripts\start-source.ps1') -Raw
        foreach ($setting in @("LANGBOT_RPA_FORCE_DISABLE_SEND='0'", "LANGBOT_RPA_ALLOW_AUTO_SEND='1'", "LANGBOT_BROADCAST_SEND_ENABLED='1'", "LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS='*'", "realSend='enabled'", 'send_enabled')) { ($startSource -match [regex]::Escape($setting)) | Should Be $true }
    }

    It 'uses a fixed available Desktop Runtime Release and constrained staging cleanup' {
        $descriptor = Get-Content -LiteralPath (Join-Path $repoRoot 'distribution\runtime\desktop-runtime-release.json') -Raw | ConvertFrom-Json
        $descriptor.release_available | Should Be $true
        $descriptor.tag | Should Not Be 'latest'
        $builder = Get-Content -LiteralPath $buildScript -Raw
        $builder | Should Match '\.starter-staging-'
        $builder | Should Match 'Assert-SafeStarterStagingDirectory'
        $builder | Should Match 'Remove-SafeStarterStagingDirectory'
        $builder | Should Not Match 'git clean|git reset|git stash'
    }

    It 'can rebuild into a second TestDrive output with the same ZIP file list' {
        $secondOutput = Join-Path $TestDrive '第二次构建'
        & $buildScript -Version '0.1.0' -OutputDirectory $secondOutput
        $secondZip = Join-Path $secondOutput 'Wecome-Bot-Source-Starter-v0.1.0.zip'
        $first = [IO.Compression.ZipFile]::OpenRead($script:zipPath)
        $second = [IO.Compression.ZipFile]::OpenRead($secondZip)
        try {
            @($first.Entries.FullName | Sort-Object) | Should Be @($second.Entries.FullName | Sort-Object)
        } finally { $first.Dispose(); $second.Dispose() }
    }
}
