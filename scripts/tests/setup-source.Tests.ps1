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

        function New-TestInstallerOrigin([string]$Path, [string]$SetupScriptContent) {
            $worktreePath = Join-Path $Path 'origin-worktree'
            $bareRepoPath = Join-Path $Path 'origin.git'
            New-Item -ItemType Directory -Path (Join-Path $worktreePath 'scripts') -Force | Out-Null

            & $git.Source init --quiet --initial-branch=main $worktreePath
            if ($LASTEXITCODE -ne 0) { throw 'git init --initial-branch=main failed.' }

            & $git.Source -C $worktreePath config user.name 'Test User'
            if ($LASTEXITCODE -ne 0) { throw 'git config user.name failed for origin.' }

            & $git.Source -C $worktreePath config user.email 'test@example.com'
            if ($LASTEXITCODE -ne 0) { throw 'git config user.email failed for origin.' }

            Set-Content -LiteralPath (Join-Path $worktreePath 'scripts\setup-source.ps1') -Value $SetupScriptContent -Encoding utf8
            Set-Content -LiteralPath (Join-Path $worktreePath 'README.md') -Value 'test repo' -Encoding utf8

            & $git.Source -C $worktreePath add .
            if ($LASTEXITCODE -ne 0) { throw 'git add failed for origin.' }

            & $git.Source -C $worktreePath commit --quiet -m 'test: setup source'
            if ($LASTEXITCODE -ne 0) { throw 'git commit failed for origin.' }

            & $git.Source clone --quiet --bare $worktreePath $bareRepoPath
            if ($LASTEXITCODE -ne 0) { throw 'git clone --bare failed.' }

            [pscustomobject]@{
                WorktreePath = $worktreePath
                BareRepoPath = $bareRepoPath
            }
        }

        function Invoke-TestInstallerBatch([string]$SetupScriptContent) {
            $scenarioRoot = Join-Path $TestDrive ([guid]::NewGuid().ToString())
            $sourceDir = Join-Path $scenarioRoot '中文 空格 source'
            $targetDir = Join-Path $scenarioRoot '中文 空格 install'
            $origin = New-TestInstallerOrigin $scenarioRoot $SetupScriptContent
            $homeDir = Join-Path $scenarioRoot 'home'
            $gitConfig = Join-Path $scenarioRoot 'gitconfig'
            $stdoutPath = Join-Path $scenarioRoot 'stdout.log'
            $stderrPath = Join-Path $scenarioRoot 'stderr.log'

            New-Item -ItemType Directory -Path $sourceDir, $homeDir -Force | Out-Null
            Copy-Item -LiteralPath $installerPath -Destination (Join-Path $sourceDir '02-install-wecome-bot.bat')
            Set-Content -LiteralPath (Join-Path $sourceDir '01-check-environment.bat') -Value '@echo off' -Encoding ascii
            Set-Content -LiteralPath (Join-Path $sourceDir '03-start-wecome-bot.bat') -Value '@echo off' -Encoding ascii

            $originUri = [Uri]::new($origin.BareRepoPath).AbsoluteUri
            & $git.Source config --file $gitConfig "url.$originUri.insteadOf" 'https://github.com/wuli073/wecome-bot.git'
            if ($LASTEXITCODE -ne 0) { throw 'git config url.*.insteadOf failed.' }
            $batchPath = Join-Path $sourceDir '02-install-wecome-bot.bat'
            $cmdCommand = "echo.| call `"$batchPath`" `"$targetDir`""

            $previousEnv = @{
                HOME = [Environment]::GetEnvironmentVariable('HOME', 'Process')
                USERPROFILE = [Environment]::GetEnvironmentVariable('USERPROFILE', 'Process')
                GIT_CONFIG_GLOBAL = [Environment]::GetEnvironmentVariable('GIT_CONFIG_GLOBAL', 'Process')
                GIT_TERMINAL_PROMPT = [Environment]::GetEnvironmentVariable('GIT_TERMINAL_PROMPT', 'Process')
            }

            try {
                [Environment]::SetEnvironmentVariable('HOME', $homeDir, 'Process')
                [Environment]::SetEnvironmentVariable('USERPROFILE', $homeDir, 'Process')
                [Environment]::SetEnvironmentVariable('GIT_CONFIG_GLOBAL', $gitConfig, 'Process')
                [Environment]::SetEnvironmentVariable('GIT_TERMINAL_PROMPT', '0', 'Process')

                $process = Start-Process -FilePath 'cmd.exe' -ArgumentList '/u', '/d', '/c', $cmdCommand -WorkingDirectory $scenarioRoot -PassThru -Wait -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
            }
            finally {
                foreach ($name in $previousEnv.Keys) {
                    [Environment]::SetEnvironmentVariable($name, $previousEnv[$name], 'Process')
                }
            }

            $stdout = if (Test-Path -LiteralPath $stdoutPath -PathType Leaf) { [IO.File]::ReadAllText($stdoutPath) } else { '' }
            $stderr = if (Test-Path -LiteralPath $stderrPath -PathType Leaf) { [IO.File]::ReadAllText($stderrPath) } else { '' }
            $setupLog = Join-Path $targetDir 'setup-source.log'

            [pscustomobject]@{
                ExitCode = $process.ExitCode
                Output = $stdout
                ErrorOutput = $stderr
                CombinedOutput = $stdout + $stderr
                TargetDir = $targetDir
                SetupLog = $setupLog
            }
        }
    }

    It 'records setup-source output with a transcript and does not tee merged streams' {
        $content | Should Match 'setup-source\.log'
        $content | Should Match 'Start-Transcript -LiteralPath \$setupLog -Force'
        $content | Should Match '& \$setupScript; \$setupExit=\$LASTEXITCODE'
        $content | Should Match 'Stop-Transcript'
        $content | Should Match 'Failed to start setup log transcript'
        $content | Should Not Match '\*>\&1\s*\|\s*Tee-Object'
    }

    It 'pauses before exit when installation fails' {
        $content | Should Match ':failed\s+echo Installation failed\.\s+echo Review the error above or setup-source\.log\.\s+pause\s+endlocal\s+exit /b 1'
    }

    It 'continues when setup writes native stderr but exits with zero and creates setup-source.log' {
        $result = Invoke-TestInstallerBatch @'
$ErrorActionPreference = 'Stop'
Write-Host '[1/6] Checking source prerequisites...'
Write-Host '[2/6] Preparing managed Python 3.12...'
& cmd.exe /d /c "echo Python 3.12 is already installed 1>&2 & exit /b 0"
Write-Host '[3/6] Installing Python dependencies...'
Write-Host '[4/6] Installing Web dependencies...'
Write-Host '[5/6] Installing Desktop Runtime dependencies...'
Write-Host '[6/6] Verifying environment...'
[ordered]@{
    status = 'ok'
}
'@

        $result.ExitCode | Should Be 0
        $result.CombinedOutput | Should Match 'Python 3\.12 is already installed'
        $result.CombinedOutput | Should Match '\[3/6\] Installing Python dependencies\.{3}'
        $result.CombinedOutput | Should Match '\[6/6\] Verifying environment\.{3}'
        $result.CombinedOutput | Should Match 'status\s+ok'
        $result.CombinedOutput | Should Match 'Installed or updated: '
        $result.CombinedOutput | Should Not Match 'NativeCommandError'
        (Test-Path -LiteralPath $result.SetupLog -PathType Leaf) | Should Be $true
        [IO.File]::ReadAllText($result.SetupLog) | Should Match 'Windows PowerShell transcript start'
    }

    It 'fails and pauses when setup returns a non-zero native exit code' {
        $result = Invoke-TestInstallerBatch @'
$ErrorActionPreference = 'Stop'
Write-Host '[1/6] Checking source prerequisites...'
& cmd.exe /d /c "echo native failure 1>&2 & exit /b 23"
'@

        $result.ExitCode | Should Be 1
        $result.CombinedOutput | Should Match 'Dependency installation failed with exit code 23'
        $result.CombinedOutput | Should Match 'Installation failed\.'
        $result.CombinedOutput | Should Match 'Review the error above or setup-source\.log\.'
        $result.CombinedOutput | Should Match 'Press any key to continue \. \. \.'
    }

    It 'fails and keeps setup-source.log when setup throws' {
        $result = Invoke-TestInstallerBatch @'
$ErrorActionPreference = 'Stop'
Write-Host '[1/6] Checking source prerequisites...'
throw 'setup exploded'
'@

        $result.ExitCode | Should Be 1
        $result.CombinedOutput | Should Match 'setup exploded'
        $result.CombinedOutput | Should Match 'Installation failed\.'
        (Test-Path -LiteralPath $result.SetupLog -PathType Leaf) | Should Be $true
        [IO.File]::ReadAllText($result.SetupLog) | Should Match 'setup exploded'
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
