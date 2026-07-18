$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$scriptPath = Join-Path $repoRoot 'scripts\setup-source.ps1'
$consoleModePath = Join-Path $repoRoot 'scripts\console-mode.ps1'
$bundleScriptPath = Join-Path $repoRoot 'scripts\build-desktop-runtime-bundle.ps1'
Add-Type -AssemblyName System.IO.Compression

Describe 'source setup Desktop Runtime contract' {
    BeforeAll {
        $content = [IO.File]::ReadAllText($scriptPath)
        $bundleContent = [IO.File]::ReadAllText($bundleScriptPath)
        . $scriptPath
    }

    It 'accepts explicit prebuilt and source-build mode parameters' {
        $content | Should Match '\[switch\]\$BuildDesktopRuntimeFromSource'
        $content | Should Match '\[string\]\$DesktopRuntimeArchivePath'
        $content | Should Match '\[string\]\$DesktopRuntimeManifestPath'
    }

    It 'disables QuickEdit before setup and installs web dependencies without audit or funding output' {
        $consoleContent = [IO.File]::ReadAllText($consoleModePath)
        $content | Should Match "console-mode\.ps1"
        $content | Should Match 'Disable-ConsoleQuickEdit \| Out-Null'
        $content | Should Match '& \$npm ci --no-audit --fund=false'
        $content | Should Not Match 'npm audit fix'
        $consoleContent | Should Match 'GetStdHandle'
        $consoleContent | Should Match 'GetConsoleMode'
        $consoleContent | Should Match 'SetConsoleMode'
        $consoleContent | Should Match 'ENABLE_QUICK_EDIT_MODE = 0x0040'
        $consoleContent | Should Match 'ENABLE_EXTENDED_FLAGS = 0x0080'
    }

    It 'uses descriptor, verified cache, then fixed Release download without source fallback' {
        $content | Should Match 'Installing prebuilt Desktop Runtime'
        $content | Should Match 'Read-DesktopRuntimeReleaseDescriptor \$Metadata'
        $content | Should Match 'Get-VerifiedCachedDesktopRuntimeArtifact \$descriptor \$Metadata'
        $content | Should Match 'Download-DesktopRuntimeReleaseToCache \$descriptor \$Metadata'
        $content | Should Match 'DESKTOP_RUNTIME_RELEASE_NOT_CONFIGURED'
        $content | Should Match 'Install-PrebuiltDesktopRuntime \$metadata'
        $content | Should Not Match 'catch \{\s*Install-DesktopRuntimeFromSource'
    }

    It 'runs npm ci, native rebuild, and packaging only in explicit source-build mode' {
        $sourceFunction = [regex]::Match($content, 'function Install-DesktopRuntimeFromSource.*?(?=function Invoke-SetupSource)', [Text.RegularExpressions.RegexOptions]::Singleline).Value
        $sourceFunction | Should Match 'Invoke-ExternalCommand \$NpmPath @\(''ci''\)'
        $sourceFunction | Should Match 'Invoke-ExternalCommand \$NpmPath @\(''run'', ''rebuild:native''\)'
        $sourceFunction | Should Match 'Invoke-ExternalCommand \$NpmPath @\(''run'', ''package:win:dir''\)'
        $content | Should Match 'if \(\$BuildDesktopRuntimeFromSource\)'
    }

    It 'verifies descriptor, manifest, archive, package lock, and cache integrity before installation' {
        $content | Should Match 'schema_version'
        $content | Should Match 'package_lock_sha256'
        $content | Should Match 'asset_sha256'
        $content | Should Match 'Read-DesktopRuntimeReleaseDescriptor'
        $content | Should Match 'Get-VerifiedCachedDesktopRuntimeArtifact'
        $content | Should Match 'Download-DesktopRuntimeReleaseToCache'
        $content | Should Match '\.partial'
        $content | Should Match 'Assert-DesktopRuntimeArtifact \$archive \$manifest \$Metadata \$Descriptor'
    }

    It 'rejects unsafe zip entry paths without writing outside staging' {
        $root = Join-Path $TestDrive 'staging'
        New-Item -ItemType Directory -Path $root -Force | Out-Null
        { Assert-SafeZipEntry '..\outside.txt' $root } | Should Throw
        { Assert-SafeZipEntry 'C:\outside.txt' $root } | Should Throw
        { Assert-SafeZipEntry '\\server\share\outside.txt' $root } | Should Throw
        (Assert-SafeZipEntry 'resources/app.asar' $root) | Should Match 'resources\\app\.asar$'
        $logical = [IO.Path]::GetFullPath((Join-Path $root 'physical-io'))
        (ConvertTo-ExtendedWindowsPath $logical) | Should Be ('\\?\' + $logical)
        (ConvertTo-ExtendedWindowsPath ('\\?\' + $logical)) | Should Be ('\\?\' + $logical)
        { ConvertTo-ExtendedWindowsPath '' } | Should Throw
        { ConvertTo-ExtendedWindowsPath 'relative\path' } | Should Throw
    }

    It 'extracts deep Runtime entries through extended-length paths without weakening ZIP safety' {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $archivePath = Join-Path $TestDrive 'deep-runtime.zip'
        $archive = [IO.Compression.ZipFile]::Open($archivePath, [System.IO.Compression.ZipArchiveMode]::Create)
        try {
            $requiredFiles = @('LangBot Desktop RPA Runtime.exe', 'resources/app.asar', 'chrome_100_percent.pak', 'icudtl.dat', 'resources.pak', 'libEGL.dll', 'libGLESv2.dll', 'ffmpeg.dll')
            foreach ($name in $requiredFiles) {
                $entry = $archive.CreateEntry($name)
                $writer = [IO.StreamWriter]::new($entry.Open(), [Text.UTF8Encoding]::new($false))
                try { $writer.Write("fixture:$name") } finally { $writer.Dispose() }
            }
            foreach ($name in @('resources/app.asar.unpacked/node_modules/@hurdlegroup/', 'resources/app.asar.unpacked/node_modules/active-win/', 'resources/app.asar.unpacked/node_modules/node-window-manager/')) {
                [void]$archive.CreateEntry($name)
            }
            $deepEntryName = 'resources/app.asar.unpacked/node_modules/@hurdlegroup/robotjs/build/Release/obj/robotjs/robotjs.node.recipe'
            $deepEntry = $archive.CreateEntry($deepEntryName)
            $deepWriter = [IO.StreamWriter]::new($deepEntry.Open(), [Text.UTF8Encoding]::new($false))
            try { $deepWriter.Write('deep-runtime-fixture') } finally { $deepWriter.Dispose() }
        } finally { $archive.Dispose() }

        $longRoot = Join-Path $TestDrive ('long-segment-' + ('x' * 80))
        $staging = Join-Path $longRoot (('nested-segment-' + ('y' * 80)) + '\staging')
        $expectedPath = [IO.Path]::GetFullPath((Join-Path $staging $deepEntryName.Replace('/', '\')))
        $expectedPath.Length | Should BeGreaterThan 260
        { Expand-DesktopRuntimeArchiveSafely $archivePath $staging } | Should Not Throw
        (Test-LongPathFile $expectedPath) | Should Be $true
        ([IO.File]::ReadAllText((ConvertTo-ExtendedWindowsPath $expectedPath), [Text.UTF8Encoding]::new($false))) | Should Be 'deep-runtime-fixture'
        $proof = Assert-DesktopRuntimeDeepFileIntegrity $archivePath $staging
        $proof.EntryName | Should Be $deepEntryName
        $proof.Length | Should Be ([Text.UTF8Encoding]::new($false).GetByteCount('deep-runtime-fixture'))
        $proof.Sha256 | Should Be (Get-LongPathSha256 $expectedPath)
        [IO.Directory]::Delete((ConvertTo-ExtendedWindowsPath $longRoot), $true)

        $outside = Join-Path $TestDrive 'zip-slip-outside.txt'
        $unsafeArchivePath = Join-Path $TestDrive 'unsafe-runtime.zip'
        $unsafeArchive = [IO.Compression.ZipFile]::Open($unsafeArchivePath, [System.IO.Compression.ZipArchiveMode]::Create)
        try {
            $unsafeEntry = $unsafeArchive.CreateEntry('../zip-slip-outside.txt')
            $unsafeWriter = [IO.StreamWriter]::new($unsafeEntry.Open())
            try { $unsafeWriter.Write('blocked') } finally { $unsafeWriter.Dispose() }
        } finally { $unsafeArchive.Dispose() }
        try {
            Expand-DesktopRuntimeArchiveSafely $unsafeArchivePath (Join-Path $TestDrive 'unsafe-staging')
            throw 'unsafe ZIP fixture was unexpectedly extracted'
        } catch {
            $_.Exception.Message | Should Match '^PREBUILT_RUNTIME_ZIP_INVALID:'
        }
        (Test-Path -LiteralPath $outside) | Should Be $false

        $writeFailureArchivePath = Join-Path $TestDrive 'write-failure-runtime.zip'
        $writeFailureArchive = [IO.Compression.ZipFile]::Open($writeFailureArchivePath, [System.IO.Compression.ZipArchiveMode]::Create)
        try {
            $writeFailureEntry = $writeFailureArchive.CreateEntry('resources/write-failure.bin')
            $writeFailureWriter = [IO.StreamWriter]::new($writeFailureEntry.Open())
            try { $writeFailureWriter.Write('must fail') } finally { $writeFailureWriter.Dispose() }
        } finally { $writeFailureArchive.Dispose() }
        Mock Write-ZipEntryToLongPath { throw [IO.IOException]::new('forced write failure') }
        try {
            Expand-DesktopRuntimeArchiveSafely $writeFailureArchivePath (Join-Path $TestDrive 'write-failure-staging')
            throw 'write failure fixture was unexpectedly extracted'
        } catch {
            $_.Exception.Message | Should Match '^PREBUILT_RUNTIME_ZIP_INVALID: Entry: resources/write-failure\.bin; target:'
            $_.Exception.Message | Should Match 'path length: [0-9]+'
        }
    }

    It 'uses staging, transactional replacement, and rollback for the current repository runtime only' {
        $content | Should Match '\.desktop-runtime-staging-'
        $content | Should Match '\.desktop-runtime-backup-'
        $content | Should Match 'Move-Item -LiteralPath \$desktopRuntimeUnpackedPath -Destination \$backup'
        $content | Should Match 'Move-Item -LiteralPath \$backup -Destination \$desktopRuntimeUnpackedPath'
        $content | Should Match 'Stop-ExistingDesktopRuntimeProcesses \$desktopRuntimeRoot \$desktopRuntimeExecutable'
    }

    It 'rejects dangerous cleanup paths and only removes correctly named TestDrive staging or backup directories' {
        $allowedRoot = Join-Path $TestDrive 'runtime-output'
        $repoFixture = Join-Path $TestDrive 'repository'
        New-Item -ItemType Directory -Path $allowedRoot, $repoFixture -Force | Out-Null
        $legalStaging = Join-Path $allowedRoot '.desktop-runtime-staging-0123456789abcdef0123456789abcdef'
        $legalBackup = Join-Path $allowedRoot '.desktop-runtime-backup-0123456789abcdef0123456789abcdef'
        foreach ($bad in @($null, '', '.', '..', $repoFixture, (Split-Path -Parent $repoFixture), [IO.Path]::GetPathRoot($repoFixture), [Environment]::GetFolderPath('UserProfile'), (Join-Path $TestDrive '.desktop-runtime-staging-0123456789abcdef0123456789abcdef'), (Join-Path $allowedRoot '.desktop-runtime-backup-wrong'))) {
            { Assert-SafeCleanupDirectory $bad $repoFixture @($allowedRoot) '^(?:win-unpacked|\.desktop-runtime-(?:staging|backup)-[0-9a-f]{32})$' } | Should Throw
        }
        foreach ($path in @($legalStaging, $legalBackup)) {
            New-Item -ItemType Directory -Path $path -Force | Out-Null
            Set-Content -LiteralPath (Join-Path $path 'payload.txt') -Value 'test' -Encoding utf8
            { Remove-SafeCleanupDirectory $path $repoFixture @($allowedRoot) '^(?:win-unpacked|\.desktop-runtime-(?:staging|backup)-[0-9a-f]{32})$' } | Should Not Throw
            (Test-Path -LiteralPath $path) | Should Be $false
        }

        $payloadEntries = @('LangBot Desktop RPA Runtime.exe', 'resources\app.asar', 'chrome_100_percent.pak', 'icudtl.dat', 'resources.pak', 'libEGL.dll', 'libGLESv2.dll', 'ffmpeg.dll', 'resources\app.asar.unpacked\node_modules\@hurdlegroup', 'resources\app.asar.unpacked\node_modules\active-win', 'resources\app.asar.unpacked\node_modules\node-window-manager')
        $newValidPayload = {
            param([string]$path)
            foreach ($entry in $payloadEntries) {
                $target = Join-Path $path $entry
                New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($target)) -Force | Out-Null
                if ([IO.Path]::GetExtension($target)) { Set-Content -LiteralPath $target -Value 'fixture' -Encoding utf8 } else { New-Item -ItemType Directory -Path $target -Force | Out-Null }
            }
        }

        $transactionRoot = Join-Path $TestDrive 'transactions'
        New-Item -ItemType Directory -Path $transactionRoot -Force | Out-Null
        $official = Join-Path $transactionRoot 'win-unpacked'
        & $newValidPayload $official
        $staleBackup = Join-Path $transactionRoot '.desktop-runtime-backup-11111111111111111111111111111111'
        & $newValidPayload $staleBackup
        $illegalBackup = Join-Path $transactionRoot '.desktop-runtime-backup-not-managed'
        New-Item -ItemType Directory -Path $illegalBackup -Force | Out-Null
        Recover-DesktopRuntimeTransactions $transactionRoot $official
        (Test-Path -LiteralPath $official) | Should Be $true
        (Test-Path -LiteralPath $staleBackup) | Should Be $false
        (Test-Path -LiteralPath $illegalBackup) | Should Be $true

        Remove-Item -LiteralPath $official -Recurse -Force
        $recoverableBackup = Join-Path $transactionRoot '.desktop-runtime-backup-22222222222222222222222222222222'
        & $newValidPayload $recoverableBackup
        Recover-DesktopRuntimeTransactions $transactionRoot $official
        (Test-Path -LiteralPath $official) | Should Be $true
        (Test-Path -LiteralPath $recoverableBackup) | Should Be $false

        Remove-Item -LiteralPath $official -Recurse -Force
        foreach ($id in @('33333333333333333333333333333333', '44444444444444444444444444444444')) {
            & $newValidPayload (Join-Path $transactionRoot ('.desktop-runtime-backup-' + $id))
        }
        { Recover-DesktopRuntimeTransactions $transactionRoot $official } | Should Throw

        $retryRoot = Join-Path $TestDrive 'retry-output'
        New-Item -ItemType Directory -Path $retryRoot -Force | Out-Null
        $retryPath = Join-Path $retryRoot '.desktop-runtime-backup-55555555555555555555555555555555'
        New-Item -ItemType Directory -Path $retryPath -Force | Out-Null
        $attempts = [Collections.ArrayList]::new()
        $busyThenDelete = { param($extendedPath) [void]$attempts.Add(1); if ($attempts.Count -lt 4) { throw [IO.IOException]::new('EBUSY fixture') }; [IO.Directory]::Delete($extendedPath, $true) }
        { Remove-SafeCleanupDirectory $retryPath $repoFixture @($retryRoot) '^\.desktop-runtime-backup-[0-9a-f]{32}$' 'PREBUILT_RUNTIME_BACKUP_CLEANUP_FAILED' 3 $busyThenDelete } | Should Not Throw
        $attempts.Count | Should Be 4

        $nonRetryPath = Join-Path $retryRoot '.desktop-runtime-backup-66666666666666666666666666666666'
        New-Item -ItemType Directory -Path $nonRetryPath -Force | Out-Null
        $nonRetryAttempts = [Collections.ArrayList]::new()
        $nonRetry = { param($extendedPath) [void]$nonRetryAttempts.Add(1); throw [IO.IOException]::new('unexpected fixture failure') }
        { Remove-SafeCleanupDirectory $nonRetryPath $repoFixture @($retryRoot) '^\.desktop-runtime-backup-[0-9a-f]{32}$' 'PREBUILT_RUNTIME_BACKUP_CLEANUP_FAILED' 3 $nonRetry } | Should Throw
        $nonRetryAttempts.Count | Should Be 1
    }

    It 'keeps the single lock-path result safe under StrictMode' {
        $content | Should Match '\$paths = @\(Get-NpmLockErrorPaths \$CommandOutput\)'
        $paths = @(Get-NpmLockErrorPaths @('npm ERR! path D:\repo\node_modules\electron'))
        $paths.Count | Should Be 1
    }

    It 'matches only desktop runtime processes that belong to the current repository runtime' {
        $runtimeRoot = Join-Path $repoRoot 'apps\desktop-rpa-runtime'
        $runtimeExe = Join-Path $runtimeRoot 'dist-phase2-official\win-dir\win-unpacked\LangBot Desktop RPA Runtime.exe'
        $owned = [pscustomobject]@{ Name = 'LangBot Desktop RPA Runtime.exe'; ExecutablePath = $runtimeExe; CommandLine = 'owned' }
        $foreign = [pscustomobject]@{ Name = 'electron.exe'; ExecutablePath = 'C:\Program Files\OtherApp\electron.exe'; CommandLine = 'foreign' }
        (Test-DesktopRuntimeProcess $owned $runtimeRoot $runtimeExe) | Should Be $true
        (Test-DesktopRuntimeProcess $foreign $runtimeRoot $runtimeExe) | Should Be $false
    }

    It 'waits for the exact packaged Runtime executable to exit before replacement' {
        $runtimeRoot = Join-Path $repoRoot 'apps\desktop-rpa-runtime'
        $runtimeExe = Join-Path $runtimeRoot 'dist-phase2-official\win-dir\win-unpacked\LangBot Desktop RPA Runtime.exe'
        $content | Should Match 'function Wait-DesktopRuntimeExit'
        $content | Should Match 'DESKTOP_RUNTIME_STOP_TIMEOUT'
        $content | Should Match 'Get-SafeCimProperty'
        $content | Should Match 'Wait-DesktopRuntimeExit \$RuntimeRoot \$RuntimeExecutable \$processIds'
        (Test-DesktopRuntimeProcess ([pscustomobject]@{ Name='electron.exe' }) $runtimeRoot $runtimeExe) | Should Be $false
    }

    It 'builds a root-level zip and complete manifest from the packaged runtime' {
        $bundleContent | Should Match 'CreateFromDirectory\(\$winUnpackedPath, \$temporaryArchive.*\$false\)'
        $bundleContent | Should Match 'desktop-runtime-win-x64\.zip'
        $bundleContent | Should Match 'runtime-manifest\.json'
        $bundleContent | Should Match 'package\.json version does not match RUNTIME_VERSION'
        $bundleContent | Should Match "@\('run', 'rebuild:native'\)"
        $bundleContent | Should Match "@\('run', 'package:win:dir'\)"
        $bundleContent | Should Match '\$maxRetries = 3'
        $bundleContent | Should Match 'EBUSY\|EPERM'
        $bundleContent | Should Match 'Stop-ExistingDesktopRuntimeProcesses'
        foreach ($field in @('schema_version', 'runtime_version', 'protocol_version', 'git_commit', 'platform', 'architecture', 'electron_version', 'package_lock_sha256', 'asset_name', 'asset_sha256', 'executable_relative_path', 'created_at')) {
            $bundleContent | Should Match $field
        }
        foreach ($code in @('PREBUILT_RUNTIME_BACKUP_CLEANUP_FAILED', 'PREBUILT_RUNTIME_FINAL_VALIDATION_FAILED', 'PREBUILT_RUNTIME_ROLLBACK_FAILED')) {
            $content | Should Match $code
        }
        $content | Should Match 'function Format-SetupFailure'
        $content | Should Match 'Stage: \$Stage'
        $content | Should Match 'Message: \$\(Protect-SetupErrorMessage \$Message\)'
        $content | Should Match 'Log: \$setupLogPath'
        $content | Should Match 'if \(\$MyInvocation\.InvocationName -ne ''\.''\)'
        $content | Should Match 'Write-Host \$failure'
        $formattedFailure = Format-SetupFailure 'PREBUILT_RUNTIME_BACKUP_CLEANUP_FAILED' 'desktop-runtime-install' 'original EBUSY fixture' @('C:\fixture\backup')
        $formattedFailure | Should Match 'PREBUILT_RUNTIME_BACKUP_CLEANUP_FAILED'
        $formattedFailure | Should Match 'original EBUSY fixture'
        $formattedFailure | Should Match 'C:\\fixture\\backup'
    }
}

Describe 'managed backend update guard' {
    It 'checks the current user-data root before setup changes dependencies or runtime files' {
        $content = [IO.File]::ReadAllText($scriptPath)
        $content | Should Match '\[string\]\$UserDataRoot'
        $content | Should Match 'LANGBOT_DATA_ROOT'
        $content | Should Match 'function Assert-ManagedSourceBackendStopped'
        $content | Should Match 'SETUP_SOURCE_BACKEND_RUNNING'
        $content | Should Match 'Assert-ManagedSourceBackendStopped\s*\r?\n\s*\$script:setupStage = ''source-prerequisites'''
    }
}