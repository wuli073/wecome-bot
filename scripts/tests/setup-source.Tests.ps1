$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$scriptPath = Join-Path $repoRoot 'scripts\setup-source.ps1'
$installerPath = Join-Path $repoRoot 'distribution\windows-source\02-install-wecome-bot.bat'

Describe 'source setup Desktop Runtime contract' {
    BeforeAll {
        $content = [IO.File]::ReadAllText($scriptPath)
        . $scriptPath
    }

    It 'requires the runtime package manifest and npm lock file' {
        $content | Should Match 'apps\\desktop-rpa-runtime'
        $content | Should Match 'package\.json'
        $content | Should Match 'package-lock\.json'
    }

    It 'binds desktop runtime npm commands to the managed Python 3.12 executable' {
        $content | Should Match '\.venv\\Scripts\\python\.exe'
        $content | Should Match '\$env:PYTHON = \$PythonPath'
        $content | Should Match '\$env:npm_config_python = \$PythonPath'
        $content | Should Match 'Expected Python 3\.12 in \.venv'
    }

    It 'installs runtime dependencies with npm ci and preserves lock hashes' {
        $content | Should Match 'Invoke-ExternalCommand \$npm @\(''ci''\)'
        $content | Should Match 'Desktop Runtime npm ci failed'
        $content | Should Match 'Get-FileHash'
        $content | Should Match 'Dependency installation modified lock file'
    }

    It 'uses the repository native rebuild and deterministic package entrypoint' {
        $content | Should Match 'Invoke-ExternalCommand \$npm @\(''run'', ''rebuild:native''\)'
        $content | Should Match 'Invoke-ExternalCommand \$npm @\(''run'', ''package:win:dir''\)'
        $content | Should Match 'LangBot Desktop RPA Runtime\.exe'
    }

    It 'keeps the Node 22 prerequisite before runtime dependency installation' {
        $nodeGateIndex = $content.IndexOf('Node.js 22.x is required')
        $runtimeInstallIndex = $content.IndexOf('Installing Desktop Runtime dependencies')

        ($nodeGateIndex -ge 0) | Should Be $true
        ($runtimeInstallIndex -ge 0) | Should Be $true
        ($nodeGateIndex -lt $runtimeInstallIndex) | Should Be $true
    }

    It 'restores process-level Python environment variables after Desktop Runtime commands' {
        $originalPython = [Environment]::GetEnvironmentVariable('PYTHON', 'Process')
        $originalNpmPython = [Environment]::GetEnvironmentVariable('npm_config_python', 'Process')
        $testPython = Join-Path $TestDrive 'python.exe'
        Set-Content -LiteralPath $testPython -Value '' -Encoding Ascii

        Invoke-WithManagedPythonEnvironment $testPython {
            [Environment]::GetEnvironmentVariable('PYTHON', 'Process') | Should Be $testPython
            [Environment]::GetEnvironmentVariable('npm_config_python', 'Process') | Should Be $testPython
        }

        [Environment]::GetEnvironmentVariable('PYTHON', 'Process') | Should Be $originalPython
        [Environment]::GetEnvironmentVariable('npm_config_python', 'Process') | Should Be $originalNpmPython
    }

    It 'extracts locked node_modules paths from npm EBUSY and EPERM output' {
        $paths = Get-NpmLockErrorPaths @(
            'npm ERR! code EBUSY'
            'npm ERR! path D:\projects\bot\apps\desktop-rpa-runtime\node_modules\electron'
            "npm ERR! syscall unlink 'D:\projects\bot\apps\desktop-rpa-runtime\node_modules\sqlite3'"
        )

        ($paths -contains 'D:\projects\bot\apps\desktop-rpa-runtime\node_modules\electron') | Should Be $true
        ($paths -contains 'D:\projects\bot\apps\desktop-rpa-runtime\node_modules\sqlite3') | Should Be $true
    }

    It 'matches only desktop runtime processes that belong to the current repository runtime' {
        $runtimeRoot = Join-Path $repoRoot 'apps\desktop-rpa-runtime'
        $runtimeExe = Join-Path $runtimeRoot 'dist-phase2-official\win-dir\win-unpacked\LangBot Desktop RPA Runtime.exe'
        $owned = [pscustomobject]@{
            Name = 'electron.exe'
            ExecutablePath = (Join-Path $runtimeRoot 'node_modules\electron\dist\electron.exe')
            CommandLine = '"' + (Join-Path $runtimeRoot 'node_modules\electron\dist\electron.exe') + '" .'
        }
        $foreign = [pscustomobject]@{
            Name = 'electron.exe'
            ExecutablePath = 'C:\Program Files\OtherApp\electron.exe'
            CommandLine = '"C:\Program Files\OtherApp\electron.exe" .'
        }

        (Test-DesktopRuntimeProcess $owned $runtimeRoot $runtimeExe) | Should Be $true
        (Test-DesktopRuntimeProcess $foreign $runtimeRoot $runtimeExe) | Should Be $false
    }
}

Describe 'source installer batch contract' {
    BeforeAll {
        $content = [IO.File]::ReadAllText($installerPath)
        $setExclusionsDefinition = [regex]::Match(
            $content,
            'function Set-DistributionExclusions\(\[string\]\$RepoRoot\) \{.*?\}(?=; function Assert-CleanWorkingTree)',
            [Text.RegularExpressions.RegexOptions]::Singleline
        ).Value
        $assertCleanDefinition = [regex]::Match(
            $content,
            'function Assert-CleanWorkingTree\(\[string\]\$RepoRoot\) \{.*?\}(?=; if \(Test-Path -LiteralPath \$target\))',
            [Text.RegularExpressions.RegexOptions]::Singleline
        ).Value

        if ([string]::IsNullOrWhiteSpace($setExclusionsDefinition)) {
            throw 'Failed to extract Set-DistributionExclusions from 02-install-wecome-bot.bat.'
        }

        if ([string]::IsNullOrWhiteSpace($assertCleanDefinition)) {
            throw 'Failed to extract Assert-CleanWorkingTree from 02-install-wecome-bot.bat.'
        }

        Invoke-Expression $setExclusionsDefinition
        Invoke-Expression $assertCleanDefinition
        $git = Get-Command git.exe -ErrorAction Stop
        $managedArtifacts = @(
            '/01-check-environment.bat'
            '/02-install-wecome-bot.bat'
            '/03-start-wecome-bot.bat'
            '/setup-source.log'
            '/apps/desktop-rpa-runtime/node_modules/'
            '/apps/desktop-rpa-runtime/out/'
            '/apps/desktop-rpa-runtime/dist-phase2-official/'
            '/distribution/packages/'
            '/runtime/'
        )
    }

    BeforeEach {
        function New-TestInstallerRepo([string]$Path) {
            New-Item -ItemType Directory -Path $Path -Force | Out-Null
            & $git.Source init --quiet $Path
            if ($LASTEXITCODE -ne 0) { throw 'git init failed.' }

            & $git.Source -C $Path config user.name 'Test User'
            if ($LASTEXITCODE -ne 0) { throw 'git config user.name failed.' }

            & $git.Source -C $Path config user.email 'test@example.com'
            if ($LASTEXITCODE -ne 0) { throw 'git config user.email failed.' }

            Set-Content -LiteralPath (Join-Path $Path 'tracked.txt') -Value 'baseline' -Encoding utf8
            & $git.Source -C $Path add tracked.txt
            if ($LASTEXITCODE -ne 0) { throw 'git add tracked.txt failed.' }

            & $git.Source -C $Path commit --quiet -m 'test: baseline'
            if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        }

        function Assert-InstallerRejectsWorkingTree([string]$RepoRoot) {
            try {
                Assert-CleanWorkingTree $RepoRoot
                throw 'Expected Assert-CleanWorkingTree to reject the working tree.'
            } catch {
                $_.Exception.Message | Should Match 'Refusing to update because the working tree contains tracked or untracked files\.'
            }
        }
    }

    It 'keeps setup-source output in setup-source.log' {
        $content | Should Match 'setup-source\.log'
        $content | Should Match 'Tee-Object -FilePath \$setupLog -Append'
    }

    It 'pauses before exit when installation fails' {
        $content | Should Match ':failed\s+echo Installation failed\.\s+echo Review the error above or setup-source\.log\.\s+pause\s+endlocal\s+exit /b 1'
    }

    It 'allows updates when only managed generated artifacts exist in a Chinese and spaced path' {
        $repoRoot = Join-Path $TestDrive '中文 空格 repo'
        New-TestInstallerRepo $repoRoot

        Set-Content -LiteralPath (Join-Path $repoRoot 'setup-source.log') -Value 'log' -Encoding utf8

        foreach ($relativePath in @(
            'apps\desktop-rpa-runtime\node_modules\placeholder.txt'
            'apps\desktop-rpa-runtime\out\placeholder.txt'
            'apps\desktop-rpa-runtime\dist-phase2-official\placeholder.txt'
            'distribution\packages\placeholder.txt'
            'runtime\placeholder.txt'
        )) {
            $targetPath = Join-Path $repoRoot $relativePath
            New-Item -ItemType Directory -Path (Split-Path -Parent $targetPath) -Force | Out-Null
            Set-Content -LiteralPath $targetPath -Value 'generated' -Encoding utf8
        }

        Set-DistributionExclusions $repoRoot
        { Assert-CleanWorkingTree $repoRoot } | Should Not Throw
    }

    It 'still rejects updates when a tracked file is modified' {
        $repoRoot = Join-Path $TestDrive 'tracked-modified'
        New-TestInstallerRepo $repoRoot
        Set-DistributionExclusions $repoRoot

        Set-Content -LiteralPath (Join-Path $repoRoot 'tracked.txt') -Value 'changed' -Encoding utf8

        Assert-InstallerRejectsWorkingTree $repoRoot
    }

    It 'still rejects updates when an unknown untracked file exists' {
        $repoRoot = Join-Path $TestDrive 'unknown-untracked'
        New-TestInstallerRepo $repoRoot
        Set-DistributionExclusions $repoRoot

        Set-Content -LiteralPath (Join-Path $repoRoot 'unexpected.txt') -Value 'surprise' -Encoding utf8

        Assert-InstallerRejectsWorkingTree $repoRoot
    }

    It 'does not append duplicate exclude entries across repeated runs' {
        $repoRoot = Join-Path $TestDrive 'repeat-exclude'
        New-TestInstallerRepo $repoRoot

        Set-DistributionExclusions $repoRoot
        Set-DistributionExclusions $repoRoot

        $excludePath = Join-Path $repoRoot '.git\info\exclude'
        $excludeLines = [IO.File]::ReadAllLines($excludePath)

        foreach ($entry in $managedArtifacts) {
            (@($excludeLines | Where-Object { $_ -eq $entry })).Count | Should Be 1
        }
    }
}
