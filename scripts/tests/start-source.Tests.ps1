$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$scriptPath = Join-Path $repoRoot 'scripts\start-source.ps1'
$consoleModePath = Join-Path $repoRoot 'scripts\console-mode.ps1'
. (Join-Path $repoRoot 'scripts\source-state.ps1')

function Invoke-SourceStatusForTest([string]$UserDataRoot) {
    $output = & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $scriptPath -Action Status -UserDataRoot $UserDataRoot
    if ($LASTEXITCODE -ne 0) { throw "Status failed: $($output -join [Environment]::NewLine)" }
    return ($output | Out-String | ConvertFrom-Json)
}

Describe 'console selection mode handling' {
    It 'disables QuickEdit before startup and includes a timeout recovery hint' {
        $content = [IO.File]::ReadAllText($scriptPath)
        $consoleContent = [IO.File]::ReadAllText($consoleModePath)
        $content | Should Match "console-mode\.ps1"
        $content | Should Match 'Disable-ConsoleQuickEdit \| Out-Null'
        $content | Should Match 'Get-ConsoleSelectionModeHint'
        $consoleContent | Should Match 'STD_INPUT_HANDLE = -10'
        $consoleContent | Should Match 'ENABLE_QUICK_EDIT_MODE = 0x0040'
        $consoleContent | Should Match 'ENABLE_EXTENDED_FLAGS = 0x0080'
    }
}

Describe 'source startup state status' {
    It 'returns stopped JSON when no state file exists' {
        $status = Invoke-SourceStatusForTest -UserDataRoot (Join-Path $TestDrive 'no-state')

        $status.status | Should Be 'stopped'
        $status.detail | Should Be 'no-managed-source-state'
        $status.backendPid | Should Be $null
        $status.webPid | Should Be $null
    }

    It 'returns degraded JSON for legacy state records without a runtime record' {
        $userDataRoot = Join-Path $TestDrive 'complete-state'
        $statePath = Join-Path $userDataRoot 'runtime\source-stack-state.json'
        $backendPid = 4101
        $webPid = 4102
        $backendStart = [DateTime]::Parse('2026-01-01T00:00:00Z')
        $webStart = [DateTime]::Parse('2026-01-01T00:01:00Z')
        $backendCommand = "powershell.exe -File fixture.ps1 -Marker $(Join-Path $repoRoot 'main.py')"
        $webCommand = "node.exe $(Join-Path $repoRoot 'web\node_modules\vite\bin\vite.js')"
        Write-ManagedSourceState -Path $statePath -Value ([ordered]@{
            schema = 1; repoRoot = $repoRoot; userDataRoot = $userDataRoot
            backend = [ordered]@{ role='backend'; pid=$backendPid; startTicks=$backendStart.ToUniversalTime().Ticks; executable='C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'; commandLine=$backendCommand }
            backendListener = $null
            web = [ordered]@{ role='web'; pid=$webPid; startTicks=$webStart.ToUniversalTime().Ticks; executable='C:\Program Files\nodejs\node.exe'; commandLine=$webCommand }
        })

        Mock Get-Process {
            switch ($Id) {
                $backendPid { return [pscustomobject]@{ StartTime = $backendStart } }
                $webPid { return [pscustomobject]@{ StartTime = $webStart } }
                default { throw "unexpected process id $Id" }
            }
        }
        Mock Get-CimInstance {
            switch ($Filter) {
                "ProcessId = $backendPid" { return [pscustomobject]@{ ExecutablePath='C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'; CommandLine=$backendCommand; ProcessId=$backendPid } }
                "ProcessId = $webPid" { return [pscustomobject]@{ ExecutablePath='C:\Program Files\nodejs\node.exe'; CommandLine=$webCommand; ProcessId=$webPid } }
                default { throw "unexpected filter $Filter" }
            }
        }

        $status = (. $scriptPath -Action Status -UserDataRoot $userDataRoot -NoBrowser | Out-String | ConvertFrom-Json)
        $status.status | Should Be 'degraded'
        $status.detail | Should Be 'partial-managed-source-state'
        $status.backendPid | Should Be $backendPid
        $status.webPid | Should Be $webPid
        $status.runtimePid | Should Be $null
    }

    It 'returns degraded JSON when only the backend record is valid and web is null' {
        $userDataRoot = Join-Path $TestDrive 'backend-only-state'
        $statePath = Join-Path $userDataRoot 'runtime\source-stack-state.json'
        $backendPid = 4201
        $backendStart = [DateTime]::Parse('2026-01-01T00:02:00Z')
        $backendCommand = "powershell.exe -File fixture.ps1 -Marker $(Join-Path $repoRoot 'main.py')"
        Write-ManagedSourceState -Path $statePath -Value ([ordered]@{
            schema = 1; repoRoot = $repoRoot; userDataRoot = $userDataRoot
            backend = [ordered]@{ role='backend'; pid=$backendPid; startTicks=$backendStart.ToUniversalTime().Ticks; executable='C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'; commandLine=$backendCommand }
            backendListener = $null
            web = $null
        })

        Mock Get-Process { [pscustomobject]@{ StartTime = $backendStart } }
        Mock Get-CimInstance { [pscustomobject]@{ ExecutablePath='C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'; CommandLine=$backendCommand; ProcessId=$backendPid } }

        $status = (. $scriptPath -Action Status -UserDataRoot $userDataRoot -NoBrowser | Out-String | ConvertFrom-Json)
        $status.status | Should Be 'degraded'
        $status.detail | Should Be 'partial-managed-source-state'
        $status.backendPid | Should Be $backendPid
        $status.webPid | Should Be $null
    }

    It 'returns valid JSON instead of throwing for partial, missing, or invalid process records' {
        $cases = @(
            [ordered]@{ name='web-null'; backend=@{ pid=123; startTicks=123; executable='x'; commandLine=$repoRoot }; backendListener=$null; web=$null },
            [ordered]@{ name='backend-null'; backend=$null; backendListener=$null; web=@{ pid=123; startTicks=123; executable='x'; commandLine=$repoRoot } },
            [ordered]@{ name='missing-backend-pid'; backend=@{ startTicks=123; executable='x'; commandLine=$repoRoot }; backendListener=$null; web=$null },
            [ordered]@{ name='missing-web-pid'; backend=$null; backendListener=$null; web=@{ startTicks=123; executable='x'; commandLine=$repoRoot } },
            [ordered]@{ name='null-pid'; backend=@{ pid=$null; startTicks=123; executable='x'; commandLine=$repoRoot }; backendListener=$null; web=$null },
            [ordered]@{ name='invalid-string-pid'; backend=@{ pid='not-a-pid'; startTicks=123; executable='x'; commandLine=$repoRoot }; backendListener=$null; web=$null },
            [ordered]@{ name='missing-start-ticks'; backend=@{ pid=123; executable='x'; commandLine=$repoRoot }; backendListener=$null; web=$null }
        )

        foreach ($case in $cases) {
            $userDataRoot = Join-Path $TestDrive $case.name
            $statePath = Join-Path $userDataRoot 'runtime\source-stack-state.json'
            Write-ManagedSourceState -Path $statePath -Value ([ordered]@{
                schema = 1; repoRoot = $repoRoot; userDataRoot = $userDataRoot
                backend = $case.backend; backendListener = $case.backendListener; web = $case.web
            })

            $status = Invoke-SourceStatusForTest -UserDataRoot $userDataRoot
            $status.status | Should Be 'stopped'
            $status.backendPid | Should Be $null
            $status.webPid | Should Be $null
        }
    }

    It 'returns stopped JSON for stale records and preserves the state file on repeated status calls' {
        $userDataRoot = Join-Path $TestDrive 'stale-state'
        $statePath = Join-Path $userDataRoot 'runtime\source-stack-state.json'
        Write-ManagedSourceState -Path $statePath -Value ([ordered]@{
            schema = 1; repoRoot = $repoRoot; userDataRoot = $userDataRoot
            backend = @{ pid=2147483647; startTicks=1; executable='x'; commandLine=$repoRoot }
            backendListener = $null; web = $null
        })
        $before = [IO.File]::ReadAllBytes($statePath)

        $first = Invoke-SourceStatusForTest -UserDataRoot $userDataRoot
        $second = Invoke-SourceStatusForTest -UserDataRoot $userDataRoot

        $first.status | Should Be 'stopped'
        $first.detail | Should Be 'stale-managed-source-state'
        $second.status | Should Be 'stopped'
        [Convert]::ToBase64String([IO.File]::ReadAllBytes($statePath)) | Should Be ([Convert]::ToBase64String($before))
    }

    It 'returns stopped JSON for truncated state JSON' {
        $userDataRoot = Join-Path $TestDrive 'truncated-state'
        $statePath = Join-Path $userDataRoot 'runtime\source-stack-state.json'
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $statePath) | Out-Null
        [IO.File]::WriteAllText($statePath, '{"schema":1', (New-Object Text.UTF8Encoding($true)))

        $status = Invoke-SourceStatusForTest -UserDataRoot $userDataRoot
        $status.status | Should Be 'stopped'
        $status.detail | Should Be 'no-managed-source-state'
    }

    It 'reports occupied port details without property exceptions' {
        $functionTestRoot = Join-Path $TestDrive 'assert-port-free'
        . $scriptPath -Action Status -UserDataRoot $functionTestRoot -BackendPort 55393 -WebPort 55399 -NoBrowser | Out-Null

        Mock Get-PortOwner { 7788 }
        Mock Get-ListenerProcessRecord {
            [ordered]@{
                role = 'listener-55393'
                pid = 7788
                executable = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
                commandLine = 'powershell.exe -File foreign-fixture.ps1'
                port = 55393
            }
        }

        { Assert-PortFree 55393 } | Should Throw
        try {
            Assert-PortFree 55393
            throw 'Assert-PortFree did not throw'
        }
        catch {
            $message = $_.Exception.Message
            $message | Should Match 'Port 55393 is already listening'
            $message | Should Match 'PID 7788'
            $message | Should Match 'process C:'
            $message | Should Match 'powershell.exe -File foreign-fixture.ps1'
            $message | Should Not Match "The property 'pid' cannot be found"
        }
    }
}

Describe 'source stop recovery' {
    It 'recovers safely when the state file is missing and no managed ports are listening' {
        $userDataRoot = Join-Path $TestDrive 'missing-state-stop'
        $output = & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $scriptPath -Action Stop -UserDataRoot $userDataRoot -BackendPort 55391 -WebPort 55392
        if ($LASTEXITCODE -ne 0) { throw "Stop failed: $($output -join [Environment]::NewLine)" }
        $stop = $output | Out-String | ConvertFrom-Json
        $stop.status | Should Be 'stopped'
        $stop.detail | Should Be 'no-managed-processes'
    }

    It 'uses stable process identity checks and verified listener recovery' {
        $content = [IO.File]::ReadAllText($scriptPath)
        $content | Should Match 'function Get-ManagedProcessDefinition'
        $content | Should Match 'ProcessName.Equals'
        $content | Should Not Match 'Get-CimInstance Win32_Process'
        $content | Should Match 'function Get-CurrentRepoPortOwnerRecord'
        $content | Should Match 'function Stop-CurrentRepoRuntimeTree'
        $content | Should Match 'Port \$Port is occupied by an unverified process'
    }
}

Describe 'source process record validation' {
    BeforeAll {
        $functionTestRoot = Join-Path $TestDrive 'function-state'
        . $scriptPath -Action Status -UserDataRoot $functionTestRoot -NoBrowser | Out-Null
    }

    It 'returns false without throwing for incomplete and invalid records' {
        $invalidRecords = @(
            $null,
            [pscustomobject]@{},
            @{},
            [pscustomobject]@{ startTicks=1; executable='x'; commandLine=$repoRoot },
            [pscustomobject]@{ pid=$null; startTicks=1; executable='x'; commandLine=$repoRoot },
            [pscustomobject]@{ pid='invalid'; startTicks=1; executable='x'; commandLine=$repoRoot },
            [pscustomobject]@{ pid=1; executable='x'; commandLine=$repoRoot },
            [pscustomobject]@{ pid=1; startTicks=1; commandLine=$repoRoot },
            [pscustomobject]@{ pid=1; startTicks=1; executable='x' }
        )

        foreach ($record in $invalidRecords) {
            { Test-ProcessRecord $record } | Should Not Throw
            (Test-ProcessRecord $record) | Should Be $false
            { Test-DesktopRuntimeRecord $record } | Should Not Throw
            (Test-DesktopRuntimeRecord $record) | Should Be $false
        }
    }

    It 'rejects a process record when start time or repository command line does not match' {
        $testPid = 5101
        $start = [DateTime]::Parse('2026-01-01T01:00:00Z')
        $matchingCommand = "powershell.exe -File fixture.ps1 -Marker $(Join-Path $repoRoot 'main.py')"
        $foreignCommand = 'powershell.exe -File foreign-fixture.ps1'
        $record = [ordered]@{ role='backend'; pid=$testPid; startTicks=$start.ToUniversalTime().Ticks; executable='C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'; commandLine=$matchingCommand }

        Mock Get-Process { [pscustomobject]@{ StartTime = $start } }
        Mock Get-CimInstance { [pscustomobject]@{ ExecutablePath='C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'; CommandLine=$matchingCommand; ProcessId=$testPid } }

        (Test-ProcessRecord $record) | Should Be $true
        $wrongStart = [ordered]@{} + $record
        $wrongStart.startTicks = [int64]$wrongStart.startTicks + 1
        (Test-ProcessRecord $wrongStart) | Should Be $false
        $foreignRecord = [ordered]@{} + $record
        $foreignRecord.commandLine = $foreignCommand
        (Test-ProcessRecord $foreignRecord) | Should Be $false
    }
}

Describe 'desktop runtime readiness evaluation' {
    BeforeAll {
        $functionTestRoot = Join-Path $TestDrive 'runtime-health'
        . $scriptPath -Action Status -UserDataRoot $functionTestRoot -NoBrowser | Out-Null
    }

    It 'returns true only when the runtime status is ready with reachability, paste, and send enabled' {
        $readyStatus = [pscustomobject]@{
            status = 'ready'
            runtime_reachable = $true
            inputAvailable = $true
            send_enabled = $true
        }
        $degradedStatus = [pscustomobject]@{
            status = 'ready'
            runtime_reachable = $true
            inputAvailable = $true
            send_enabled = $false
        }

        (Test-DesktopRuntimeHealthy $readyStatus) | Should Be $true
        (Test-DesktopRuntimeHealthy $degradedStatus) | Should Be $false
    }
}

Describe 'source listener ownership recovery' {
    BeforeAll {
        $functionTestRoot = Join-Path $TestDrive 'listener-recovery'
        . $scriptPath -Action Status -UserDataRoot $functionTestRoot -NoBrowser | Out-Null
    }

    It 'accepts a healthy listener only when its live process belongs to this repository' {
        $currentPid = 6101
        $foreignPid = 6102
        $currentStart = [DateTime]::Parse('2026-01-01T02:00:00Z')
        $foreignStart = [DateTime]::Parse('2026-01-01T02:01:00Z')
        $currentCommand = "powershell.exe -File fixture.ps1 -Marker $(Join-Path $repoRoot 'main.py')"
        $foreignCommand = 'powershell.exe -File foreign-fixture.ps1'
        $currentListener = [ordered]@{ role='listener-5300'; pid=$currentPid; startTicks=$currentStart.ToUniversalTime().Ticks; executable='C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'; commandLine=$currentCommand; port=5300 }
        $foreignListener = [ordered]@{ role='listener-5300'; pid=$foreignPid; startTicks=$foreignStart.ToUniversalTime().Ticks; executable='C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'; commandLine=$foreignCommand; port=5300 }

        Mock Get-Process {
            switch ($Id) {
                $currentPid { return [pscustomobject]@{ StartTime = $currentStart } }
                $foreignPid { return [pscustomobject]@{ StartTime = $foreignStart } }
                default { throw "unexpected process id $Id" }
            }
        }
        Mock Get-CimInstance {
            switch ($Filter) {
                "ProcessId = $currentPid" { return [pscustomobject]@{ ExecutablePath='C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'; CommandLine=$currentCommand; ProcessId=$currentPid } }
                "ProcessId = $foreignPid" { return [pscustomobject]@{ ExecutablePath='C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'; CommandLine=$foreignCommand; ProcessId=$foreignPid } }
                default { throw "unexpected filter $Filter" }
            }
        }

        (Test-CurrentRepoListener $currentListener) | Should Be $true
        (Test-CurrentRepoListener $foreignListener) | Should Be $false
    }
}

Describe 'broadcast worker startup readiness' {
    It 'waits for schema verification, recovery, and a single running worker before launching web' {
        $content = [IO.File]::ReadAllText($scriptPath)
        $content | Should Match 'broadcast_schema_ready'
        $content | Should Match 'broadcast_recovery_completed'
        $content | Should Match 'broadcast_worker_running'
        $content | Should Match 'Wait-ForBackend'
    }
}
