$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$scriptPath = Join-Path $repoRoot 'scripts\setup-source.ps1'
$descriptorPath = Join-Path $repoRoot 'distribution\runtime\desktop-runtime-release.json'
$installerPath = Join-Path $repoRoot 'distribution\windows-source\02-install-wecome-bot.bat'
$environmentPath = Join-Path $repoRoot 'distribution\windows-source\01-check-environment.bat'

Describe 'desktop runtime Release descriptor and cache contract' {
    BeforeAll {
        . $scriptPath
        $script:metadata = Get-DesktopRuntimeMetadata
    }

    It 'contains calculated archive and package-lock SHA-256 values' {
        $descriptor = Read-DesktopRuntimeReleaseDescriptor $script:metadata $descriptorPath
        $descriptor.asset_sha256 | Should Be '225BD50CF1B09D18A3FB78BFE1E0189D4E02C3260717EE403DB8CE0EB0F91165'
        $descriptor.package_lock_sha256 | Should Be (Get-Sha256 (Join-Path $repoRoot 'apps\desktop-rpa-runtime\package-lock.json'))
        $archive = Join-Path $repoRoot 'distribution\packages\desktop-runtime\desktop-runtime-win-x64.zip'
        (Get-Sha256 $archive) | Should Be $descriptor.asset_sha256
    }

    It 'requires a fixed non-latest tag and valid repository and asset names' {
        $fixture = Join-Path $TestDrive 'descriptor.json'
        Copy-Item -LiteralPath $descriptorPath -Destination $fixture
        $invalid = Get-Content -LiteralPath $fixture -Raw | ConvertFrom-Json
        $invalid.tag = 'latest'
        $invalid | ConvertTo-Json | Set-Content -LiteralPath $fixture -Encoding utf8
        { Read-DesktopRuntimeReleaseDescriptor $script:metadata $fixture } | Should Throw

        $invalid = Get-Content -LiteralPath $descriptorPath -Raw | ConvertFrom-Json
        $invalid.repository = 'wuli073/../wecome-bot'
        $invalid | ConvertTo-Json | Set-Content -LiteralPath $fixture -Encoding utf8
        { Read-DesktopRuntimeReleaseDescriptor $script:metadata $fixture } | Should Throw

        $invalid = Get-Content -LiteralPath $descriptorPath -Raw | ConvertFrom-Json
        $invalid.asset_name = '../desktop-runtime-win-x64.zip'
        $invalid | ConvertTo-Json | Set-Content -LiteralPath $fixture -Encoding utf8
        { Read-DesktopRuntimeReleaseDescriptor $script:metadata $fixture } | Should Throw
    }

    It 'constructs fixed HTTPS GitHub Release URLs and restricts redirect hosts' {
        $descriptor = Read-DesktopRuntimeReleaseDescriptor $script:metadata $descriptorPath
        (Get-DesktopRuntimeReleaseUri $descriptor $descriptor.asset_name).AbsoluteUri | Should Be 'https://github.com/wuli073/wecome-bot/releases/download/desktop-runtime-v0.1.0/desktop-runtime-win-x64.zip'
        (Get-DesktopRuntimeReleaseUri $descriptor $descriptor.manifest_asset_name).AbsoluteUri | Should Be 'https://github.com/wuli073/wecome-bot/releases/download/desktop-runtime-v0.1.0/runtime-manifest.json'
        (Test-ApprovedDesktopRuntimeDownloadUri ([Uri]'https://objects.githubusercontent.com/asset')) | Should Be $true
        (Test-ApprovedDesktopRuntimeDownloadUri ([Uri]'http://github.com/wuli073/wecome-bot')) | Should Be $false
        (Test-ApprovedDesktopRuntimeDownloadUri ([Uri]'https://example.invalid/asset')) | Should Be $false
    }

    It 'downloads both assets to partial paths before publishing a verified cache entry' {
        $originalCacheRoot = $script:desktopRuntimeCacheRoot
        $originalDescriptorPath = $script:desktopRuntimeReleaseDescriptorPath
        $script:desktopRuntimeCacheRoot = Join-Path $TestDrive ('cache-' + [guid]::NewGuid().ToString('N'))
        $script:desktopRuntimeReleaseDescriptorPath = $descriptorPath
        try {
            $descriptor = Read-DesktopRuntimeReleaseDescriptor $script:metadata $descriptorPath
            $descriptor.release_available = $true
            $archiveSource = Join-Path $repoRoot 'distribution\packages\desktop-runtime\desktop-runtime-win-x64.zip'
            $manifestSource = Join-Path $repoRoot 'distribution\packages\desktop-runtime\runtime-manifest.json'
            Mock Invoke-ApprovedDesktopRuntimeDownload {
                param($InitialUri, $PartialPath, $FailureCode)
                if ($FailureCode -eq 'DESKTOP_RUNTIME_DOWNLOAD_FAILED') { Copy-Item -LiteralPath $archiveSource -Destination $PartialPath }
                else { Copy-Item -LiteralPath $manifestSource -Destination $PartialPath }
            }
            $artifact = Download-DesktopRuntimeReleaseToCache $descriptor $script:metadata
            $artifact.IsCache | Should Be $true
            (Test-Path -LiteralPath $artifact.Archive -PathType Leaf) | Should Be $true
            (Test-Path -LiteralPath $artifact.Manifest -PathType Leaf) | Should Be $true
            (Test-Path -LiteralPath "$($artifact.Archive).partial") | Should Be $false
            Assert-MockCalled Invoke-ApprovedDesktopRuntimeDownload -Times 2 -Exactly
        } finally {
            $script:desktopRuntimeCacheRoot = $originalCacheRoot
            $script:desktopRuntimeReleaseDescriptorPath = $originalDescriptorPath
        }
    }

    It 'uses a complete verified cache entry without downloading again' {
        $originalCacheRoot = $script:desktopRuntimeCacheRoot
        $script:desktopRuntimeCacheRoot = Join-Path $TestDrive ('cache-' + [guid]::NewGuid().ToString('N'))
        try {
            $descriptor = Read-DesktopRuntimeReleaseDescriptor $script:metadata $descriptorPath
            $cacheDir = Join-Path $script:desktopRuntimeCacheRoot $descriptor.runtime_version
            New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null
            Copy-Item -LiteralPath (Join-Path $repoRoot 'distribution\packages\desktop-runtime\desktop-runtime-win-x64.zip') -Destination (Join-Path $cacheDir $descriptor.asset_name)
            Copy-Item -LiteralPath (Join-Path $repoRoot 'distribution\packages\desktop-runtime\runtime-manifest.json') -Destination (Join-Path $cacheDir $descriptor.manifest_asset_name)
            Copy-Item -LiteralPath $descriptorPath -Destination (Join-Path $cacheDir 'release-descriptor.json')
            $artifact = Get-VerifiedCachedDesktopRuntimeArtifact $descriptor $script:metadata
            $artifact.IsCache | Should Be $true
            (Get-Sha256 $artifact.Archive) | Should Be $descriptor.asset_sha256
        } finally { $script:desktopRuntimeCacheRoot = $originalCacheRoot }
    }

    It 'rejects incomplete or corrupt cache entries instead of treating partial files as cache' {
        $originalCacheRoot = $script:desktopRuntimeCacheRoot
        $script:desktopRuntimeCacheRoot = Join-Path $TestDrive ('cache-' + [guid]::NewGuid().ToString('N'))
        try {
            $descriptor = Read-DesktopRuntimeReleaseDescriptor $script:metadata $descriptorPath
            $cacheDir = Join-Path $script:desktopRuntimeCacheRoot $descriptor.runtime_version
            New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null
            Copy-Item -LiteralPath (Join-Path $repoRoot 'distribution\packages\desktop-runtime\desktop-runtime-win-x64.zip') -Destination (Join-Path $cacheDir ($descriptor.asset_name + '.partial'))
            (Get-VerifiedCachedDesktopRuntimeArtifact $descriptor $script:metadata) | Should Be $null
            Copy-Item -LiteralPath (Join-Path $repoRoot 'distribution\packages\desktop-runtime\desktop-runtime-win-x64.zip') -Destination (Join-Path $cacheDir $descriptor.asset_name)
            Copy-Item -LiteralPath (Join-Path $repoRoot 'distribution\packages\desktop-runtime\runtime-manifest.json') -Destination (Join-Path $cacheDir $descriptor.manifest_asset_name)
            Copy-Item -LiteralPath $descriptorPath -Destination (Join-Path $cacheDir 'release-descriptor.json')
            Set-Content -LiteralPath (Join-Path $cacheDir $descriptor.asset_name) -Value 'corrupt' -Encoding utf8
            (Get-VerifiedCachedDesktopRuntimeArtifact $descriptor $script:metadata) | Should Be $null
        } finally { $script:desktopRuntimeCacheRoot = $originalCacheRoot }
    }

    It 'times out rather than allowing concurrent writers to share a cache entry' {
        $cacheDir = Join-Path $TestDrive 'locked-cache'
        $firstLock = Acquire-DesktopRuntimeCacheLock $cacheDir 1
        try {
            { Acquire-DesktopRuntimeCacheLock $cacheDir 0 } | Should Throw
        } finally { $firstLock.Dispose() }
    }

    It 'reports an unpublished descriptor instead of attempting an unconfigured Release URL' {
        $descriptor = Read-DesktopRuntimeReleaseDescriptor $script:metadata $descriptorPath
        { Download-DesktopRuntimeReleaseToCache $descriptor $script:metadata } | Should Throw
    }

    It 'keeps the starter free of Runtime inputs and preserves the PowerShell exit code and transcript' {
        $installer = Get-Content -LiteralPath $installerPath -Raw
        $installer | Should Match '& \$setupScript; \$setupExit=\$LASTEXITCODE'
        $installer | Should Match 'Start-Transcript -LiteralPath \$setupLog -Append'
        $installer | Should Match 'LB_EXIT_CODE=%ERRORLEVEL%'
        $installer | Should Match 'exit \$setupExit'
        $installer | Should Match 'prebuilt Desktop Runtime'
        $installer | Should Not Match 'DesktopRuntimeArchivePath'
        $installer | Should Not Match 'DesktopRuntimeManifestPath'
        $installer | Should Not Match 'releases/download'
    }

    It 'keeps Git, Node/npm, and uv checks while explaining that C++ tools are unnecessary' {
        $environment = Get-Content -LiteralPath $environmentPath -Raw
        $environment | Should Match "Get-Tool 'git.exe'"
        $environment | Should Match "Get-Tool 'node.exe'"
        $environment | Should Match "Get-Tool 'npm.cmd'"
        $environment | Should Match "Get-Tool 'uv.exe'"
        $environment | Should Match 'C\+\+ build tools are not required'
        $environment | Should Not Match 'Visual Studio'
    }

    It 'rejects descriptor, manifest, archive, and package-lock mismatches' {
        $descriptor = Read-DesktopRuntimeReleaseDescriptor $script:metadata $descriptorPath
        $archive = Join-Path $repoRoot 'distribution\packages\desktop-runtime\desktop-runtime-win-x64.zip'
        $manifest = Join-Path $repoRoot 'distribution\packages\desktop-runtime\runtime-manifest.json'
        $fixtureManifest = Join-Path $TestDrive 'runtime-manifest.json'

        $badManifest = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
        $badManifest.asset_sha256 = ('0' * 64)
        $badManifest | ConvertTo-Json | Set-Content -LiteralPath $fixtureManifest -Encoding utf8
        { Assert-DesktopRuntimeArtifact $archive $fixtureManifest $script:metadata $descriptor } | Should Throw

        $badManifest = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
        $badManifest.package_lock_sha256 = ('0' * 64)
        $badManifest | ConvertTo-Json | Set-Content -LiteralPath $fixtureManifest -Encoding utf8
        { Assert-DesktopRuntimeArtifact $archive $fixtureManifest $script:metadata $descriptor } | Should Throw
    }
}
