$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$scriptPath = Join-Path $repoRoot 'scripts\start-source.ps1'
. (Join-Path $repoRoot 'scripts\source-state.ps1')

function Invoke-SourceStatusForTest([string]$UserDataRoot) {
    $output = & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $scriptPath -Action Status -UserDataRoot $UserDataRoot
    if ($LASTEXITCODE -ne 0) { throw "Status failed: $($output -join [Environment]::NewLine)" }
    return ($output | Out-String | ConvertFrom-Json)
}

function New-CurrentRepoProcessRecord([string]$Role) {
    $command = "cd /d `"$repoRoot`" & ping -n 30 127.0.0.1 >nul"
    $process = Start-Process -FilePath $env:ComSpec -ArgumentList @('/d', '/s', '/c', $command) -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 100
    $liveProcess = Get-Process -Id $process.Id -ErrorAction Stop
    $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)" -ErrorAction Stop
    return [ordered]@{
        process = $process
        record = [ordered]@{
            role = $Role
            pid = $process.Id
            startTicks = $liveProcess.StartTime.ToUniversalTime().Ticks
            executable = [string]$cim.ExecutablePath
            commandLine = [string]$cim.CommandLine
        }
    }
}

function Stop-TestProcess($Process) {
    if ($null -ne $Process -and -not $Process.HasExited) {
        & taskkill.exe /PID $Process.Id /T /F | Out-Null
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

    It 'returns running JSON for complete current-repository process records' {
        $backend = New-CurrentRepoProcessRecord 'backend'
        $web = New-CurrentRepoProcessRecord 'web'
        try {
            $userDataRoot = Join-Path $TestDrive 'complete-state'
            $statePath = Join-Path $userDataRoot 'runtime\source-stack-state.json'
            Write-ManagedSourceState -Path $statePath -Value ([ordered]@{
                schema = 1; repoRoot = $repoRoot; userDataRoot = $userDataRoot
                backend = $backend.record; backendListener = $null; web = $web.record
            })

            $status = Invoke-SourceStatusForTest -UserDataRoot $userDataRoot
            $status.status | Should Be 'running'
            $status.backendPid | Should Be $backend.process.Id
            $status.webPid | Should Be $web.process.Id
        }
        finally {
            Stop-TestProcess $backend.process
            Stop-TestProcess $web.process
        }
    }

    It 'returns degraded JSON when only the backend record is valid and web is null' {
        $backend = New-CurrentRepoProcessRecord 'backend'
        try {
            $userDataRoot = Join-Path $TestDrive 'backend-only-state'
            $statePath = Join-Path $userDataRoot 'runtime\source-stack-state.json'
            Write-ManagedSourceState -Path $statePath -Value ([ordered]@{
                schema = 1; repoRoot = $repoRoot; userDataRoot = $userDataRoot
                backend = $backend.record; backendListener = $null; web = $null
            })

            $status = Invoke-SourceStatusForTest -UserDataRoot $userDataRoot
            $status.status | Should Be 'degraded'
            $status.detail | Should Be 'partial-managed-source-state'
            $status.backendPid | Should Be $backend.process.Id
            $status.webPid | Should Be $null
        }
        finally {
            Stop-TestProcess $backend.process
        }
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

    It 'stops partial state without a property exception or broad process cleanup' {
        $userDataRoot = Join-Path $TestDrive 'partial-stop-state'
        $statePath = Join-Path $userDataRoot 'runtime\source-stack-state.json'
        Write-ManagedSourceState -Path $statePath -Value ([ordered]@{
            schema = 1; repoRoot = $repoRoot; userDataRoot = $userDataRoot
            backend = @{ startTicks=1; executable='x'; commandLine=$repoRoot }
            backendListener = $null; web = $null
        })

        $output = & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $scriptPath -Action Stop -UserDataRoot $userDataRoot
        if ($LASTEXITCODE -ne 0) { throw "Stop failed: $($output -join [Environment]::NewLine)" }
        $stop = $output | Out-String | ConvertFrom-Json

        $stop.status | Should Be 'stopped'
        Test-Path -LiteralPath $statePath | Should Be $false
    }

    It 'rejects an occupied backend port after reading partial state' {
        $userDataRoot = Join-Path $TestDrive 'partial-port-state'
        $statePath = Join-Path $userDataRoot 'runtime\source-stack-state.json'
        Write-ManagedSourceState -Path $statePath -Value ([ordered]@{
            schema = 1; repoRoot = $repoRoot; userDataRoot = $userDataRoot
            backend = $null; backendListener = $null; web = $null
        })
        $listener = $null
        $createdListener = $false
        try {
            if (-not (Get-NetTCPConnection -State Listen -LocalPort 5300 -ErrorAction SilentlyContinue)) {
                $listener = New-Object System.Net.Sockets.TcpListener ([System.Net.IPAddress]::Parse('127.0.0.1'), 5300)
                $listener.Start()
                $createdListener = $true
            }

            $previousErrorActionPreference = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                $output = & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $scriptPath -Action Start -UserDataRoot $userDataRoot -BackendPort 5300 -WebPort 55399 -NoBrowser 2>&1
                $exitCode = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $previousErrorActionPreference
            }
            $exitCode | Should Not Be 0
            ($output -join [Environment]::NewLine) | Should Match 'Port 5300 is already listening \(PID \d+\)'
            ($output -join [Environment]::NewLine) | Should Not Match "The property 'pid' cannot be found"
        }
        finally {
            if ($createdListener) { $listener.Stop() }
        }
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
        }
    }

    It 'rejects a process record when start time or repository command line does not match' {
        $current = New-CurrentRepoProcessRecord 'backend'
        $foreign = Start-Process -FilePath $env:ComSpec -ArgumentList @('/d', '/s', '/c', 'ping -n 30 127.0.0.1 >nul') -WindowStyle Hidden -PassThru
        try {
            (Test-ProcessRecord $current.record) | Should Be $true
            $wrongStart = [ordered]@{} + $current.record
            $wrongStart.startTicks = [int64]$wrongStart.startTicks + 1
            (Test-ProcessRecord $wrongStart) | Should Be $false

            $foreignProcess = Get-Process -Id $foreign.Id -ErrorAction Stop
            $foreignCim = Get-CimInstance Win32_Process -Filter "ProcessId = $($foreign.Id)" -ErrorAction Stop
            $foreignRecord = [ordered]@{ role='foreign'; pid=$foreign.Id; startTicks=$foreignProcess.StartTime.ToUniversalTime().Ticks; executable=[string]$foreignCim.ExecutablePath; commandLine=[string]$foreignCim.CommandLine }
            (Test-ProcessRecord $foreignRecord) | Should Be $false
        }
        finally {
            Stop-TestProcess $current.process
            Stop-TestProcess $foreign
        }
    }
}
