$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
. (Join-Path $repoRoot 'scripts\source-state.ps1')

Describe 'managed source state encoding' {
    It 'writes a UTF-8 BOM state file and preserves Unicode paths' {
        $statePath = Join-Path $TestDrive '中文 路径 (source) & !\runtime\source-stack-state.json'
        $expectedPath = [IO.Path]::GetFullPath((Join-Path $TestDrive '中文 路径 (source) & !'))

        Write-ManagedSourceState -Path $statePath -Value ([ordered]@{ repoRoot = $expectedPath; userDataRoot = $expectedPath })

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
            (([ordered]@{ repoRoot = $expectedPath; userDataRoot = $expectedPath }) | ConvertTo-Json),
            (New-Object Text.UTF8Encoding($false))
        )

        (Read-ManagedSourceState -Path $statePath).userDataRoot | Should Be $expectedPath
    }

    It 'returns null for empty or malformed state files without throwing' {
        $emptyPath = Join-Path $TestDrive 'invalid\empty.json'
        $truncatedPath = Join-Path $TestDrive 'invalid\truncated.json'
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $emptyPath) | Out-Null
        [IO.File]::WriteAllText($emptyPath, '', (New-Object Text.UTF8Encoding($true)))
        [IO.File]::WriteAllText($truncatedPath, '{"schema":1,"repoRoot":', (New-Object Text.UTF8Encoding($true)))

        { Read-ManagedSourceState -Path $emptyPath } | Should Not Throw
        (Read-ManagedSourceState -Path $emptyPath) | Should Be $null
        { Read-ManagedSourceState -Path $truncatedPath } | Should Not Throw
        (Read-ManagedSourceState -Path $truncatedPath) | Should Be $null
    }

    It 'returns null for non-object JSON and states without repoRoot' {
        $arrayPath = Join-Path $TestDrive 'invalid\array.json'
        $stringPath = Join-Path $TestDrive 'invalid\string.json'
        $missingRootPath = Join-Path $TestDrive 'invalid\missing-root.json'
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $arrayPath) | Out-Null
        [IO.File]::WriteAllText($arrayPath, '[]', (New-Object Text.UTF8Encoding($true)))
        [IO.File]::WriteAllText($stringPath, '"not a state"', (New-Object Text.UTF8Encoding($true)))
        [IO.File]::WriteAllText($missingRootPath, '{"schema":1}', (New-Object Text.UTF8Encoding($true)))

        (Read-ManagedSourceState -Path $arrayPath) | Should Be $null
        (Read-ManagedSourceState -Path $stringPath) | Should Be $null
        (Read-ManagedSourceState -Path $missingRootPath) | Should Be $null
    }
}
