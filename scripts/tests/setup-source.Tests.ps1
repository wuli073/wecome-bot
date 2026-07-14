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
    }

    It 'keeps setup-source output in setup-source.log' {
        $content | Should Match 'setup-source\.log'
        $content | Should Match 'Tee-Object -FilePath \$setupLog -Append'
    }

    It 'pauses before exit when installation fails' {
        $content | Should Match ':failed\s+echo Installation failed\.\s+echo Review the error above or setup-source\.log\.\s+pause\s+endlocal\s+exit /b 1'
    }
}
