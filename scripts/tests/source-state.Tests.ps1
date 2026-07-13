$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
. (Join-Path $repoRoot 'scripts\source-state.ps1')

Describe 'managed source state encoding' {
    It 'writes a UTF-8 BOM state file and preserves Unicode paths' {
        $statePath = Join-Path $TestDrive '中文 路径 (source) & !\runtime\source-stack-state.json'
        $expectedPath = [IO.Path]::GetFullPath((Join-Path $TestDrive '中文 路径 (source) & !'))

        Write-ManagedSourceState -Path $statePath -Value ([ordered]@{ userDataRoot = $expectedPath })

        $bytes = [IO.File]::ReadAllBytes($statePath)
        $bytes[0] | Should Be 0xEF
        $bytes[1] | Should Be 0xBB
        $bytes[2] | Should Be 0xBF
        (Read-ManagedSourceState -Path $statePath).userDataRoot | Should Be $expectedPath
    }

    It 'reads legacy UTF-8 without BOM state files containing Unicode paths' {
        $statePath = Join-Path $TestDrive 'legacy\source-stack-state.json'
        $expectedPath = [IO.Path]::GetFullPath((Join-Path $TestDrive '中文 路径 (legacy) & !'))
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $statePath) | Out-Null
        [IO.File]::WriteAllText(
            $statePath,
            (([ordered]@{ userDataRoot = $expectedPath }) | ConvertTo-Json),
            (New-Object Text.UTF8Encoding($false))
        )

        (Read-ManagedSourceState -Path $statePath).userDataRoot | Should Be $expectedPath
    }
}
