$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$scriptPath = Join-Path $repoRoot 'scripts\setup-source.ps1'

Describe 'source setup Desktop Runtime contract' {
    BeforeAll {
        $content = [IO.File]::ReadAllText($scriptPath)
    }

    It 'requires the runtime package manifest and npm lock file' {
        $content | Should Match 'apps\\desktop-rpa-runtime'
        $content | Should Match 'package\.json'
        $content | Should Match 'package-lock\.json'
    }

    It 'installs runtime dependencies with npm ci and preserves lock hashes' {
        $content | Should Match '& \$npm ci'
        $content | Should Match 'Desktop Runtime dependency installation failed\.'
        $content | Should Match 'Get-FileHash'
        $content | Should Match 'Dependency installation modified lock file'
    }

    It 'uses the repository native rebuild and deterministic package entrypoint' {
        $content | Should Match 'npm run rebuild:native'
        $content | Should Match 'npm run package:win:dir'
        $content | Should Match 'LangBot Desktop RPA Runtime\.exe'
    }

    It 'keeps the Node 22 prerequisite before runtime dependency installation' {
        $nodeGateIndex = $content.IndexOf('Node.js 22.x is required')
        $runtimeInstallIndex = $content.IndexOf('Installing Desktop Runtime dependencies')

        ($nodeGateIndex -ge 0) | Should Be $true
        ($runtimeInstallIndex -ge 0) | Should Be $true
        ($nodeGateIndex -lt $runtimeInstallIndex) | Should Be $true
    }
}
