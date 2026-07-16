$ErrorActionPreference = 'Stop'

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$scriptPath = Join-Path $repoRoot 'scripts\start-local.ps1'
$cmdWrapperPath = Join-Path $repoRoot 'scripts\start-local.cmd'

Describe 'start-local core helpers' {
    It 'exposes repo-scoped launcher mutex naming for Start Stop and Restart' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $startName = Get-LauncherMutexName -RepoRoot $repoRoot -Action 'Start'
        $stopName = Get-LauncherMutexName -RepoRoot $repoRoot -Action 'Stop'
        $restartName = Get-LauncherMutexName -RepoRoot $repoRoot -Action 'Restart'

        $startName | Should Match '^Local\\LangBot-Launcher-'
        $startName | Should Be $stopName
        $startName | Should Be $restartName

        $mutex = Acquire-LauncherMutex -MutexName $startName -TimeoutMs 1000
        try {
            $mutex | Should Not Be $null
        }
        finally {
            Release-LauncherMutex -Mutex $mutex
        }
    }

    It 'writes state json through atomic replace semantics without leaving temp files behind' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('start-local-tests-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmpRoot | Out-Null
        try {
            $statePath = Join-Path $tmpRoot 'state.json'
            Write-JsonAtomically -Path $statePath -Data @{ status = 'starting'; pid = 42 }
            Test-Path -LiteralPath $statePath | Should Be $true

            $first = Get-Content -Raw -LiteralPath $statePath
            $first | Should Match 'starting'

            Write-JsonAtomically -Path $statePath -Data @{ status = 'running'; pid = 43 }
            $second = Get-Content -Raw -LiteralPath $statePath
            $second | Should Match 'running'
            Test-Path -LiteralPath ($statePath + '.tmp') | Should Be $false
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'refuses unknown occupied backend port before startup' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse('127.0.0.1'), 0)
        $listener.Start()
        try {
            $port = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
            { Assert-PortAvailableOrOwned -Address '127.0.0.1' -Port $port -OwnerCheck { $false } } | Should Throw "Port $port is already in use by a non-repo-owned process."
        }
        finally {
            $listener.Stop()
        }
    }

    It 'starts managed process with direct output redirection and restores process environment overrides' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('start-local-tests-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmpRoot | Out-Null
        $stdoutPath = Join-Path $tmpRoot 'stdout.log'
        $stderrPath = Join-Path $tmpRoot 'stderr.log'
        [System.Environment]::SetEnvironmentVariable('START_LOCAL_TEST_ENV', 'before', 'Process')
        try {
            $proc = Start-ManagedProcess -FilePath 'cmd.exe' -ArgumentList @('/d', '/s', '/c', 'echo %START_LOCAL_TEST_ENV% & echo err 1>&2') -WorkingDirectory $repoRoot -Environment @{ START_LOCAL_TEST_ENV = 'during' } -StdoutLogPath $stdoutPath -StderrLogPath $stderrPath
            $proc.WaitForExit()

            [System.Environment]::GetEnvironmentVariable('START_LOCAL_TEST_ENV', 'Process') | Should Be 'before'
            (Get-Content -Raw -LiteralPath $stdoutPath) | Should Match 'during'
            (Get-Content -Raw -LiteralPath $stderrPath) | Should Match 'err'
        }
        finally {
            [System.Environment]::SetEnvironmentVariable('START_LOCAL_TEST_ENV', $null, 'Process')
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'loads dynamic host and port from config without clobbering built-in variables' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $config = Resolve-ApiConfiguration -RepoRoot $repoRoot
        $config.Host | Should Be '127.0.0.1'
        $config.Port | Should Be 5300
    }

    It 'forces safe-send environment variables without injecting legacy Runtime startup variables' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $command = New-BackendCommand -RepoRoot $repoRoot -SessionId 'session-safe' -ShutdownRequestPath 'C:\tmp\shutdown.request.json'

        $command.Environment.LANGBOT_RPA_FORCE_DISABLE_SEND | Should Be '1'
        $command.Environment.LANGBOT_RPA_ALLOW_AUTO_SEND | Should Be '0'
        $command.Environment.LANGBOT_BROADCAST_SEND_ENABLED | Should Be '0'
        $command.Environment.PYTHONPATH | Should Be (Join-Path $repoRoot 'src')
        ($command.Environment.ContainsKey('LANGBOT_RPA_MANAGED')) | Should Be $false
        ($command.Environment.ContainsKey('LANGBOT_RPA_TOKEN')) | Should Be $false
    }

    It 'recognizes only current repo official runtime executable paths for recovery' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $validPath = Join-Path $repoRoot 'apps\desktop-rpa-runtime\dist-phase2-official\2026-07-08T00-00-00-000Z\win-unpacked\LangBot Desktop RPA Runtime.exe'
        $outsidePath = 'D:\OtherRepo\apps\desktop-rpa-runtime\dist-phase2-official\2026-07-08T00-00-00-000Z\win-unpacked\LangBot Desktop RPA Runtime.exe'
        $legacyPath = Join-Path $repoRoot 'apps\desktop-rpa-runtime\dist-phase2-official\win-unpacked\LangBot Desktop RPA Runtime.exe'
        $wrongName = Join-Path $repoRoot 'apps\desktop-rpa-runtime\dist-phase2-official\2026-07-08T00-00-00-000Z\win-unpacked\Other.exe'

        (Test-OfficialRuntimeExecutablePath -ExecutablePath $validPath -RepoRoot $repoRoot) | Should Be $true
        (Test-OfficialRuntimeExecutablePath -ExecutablePath $outsidePath -RepoRoot $repoRoot) | Should Be $false
        (Test-OfficialRuntimeExecutablePath -ExecutablePath $legacyPath -RepoRoot $repoRoot) | Should Be $false
        (Test-OfficialRuntimeExecutablePath -ExecutablePath $wrongName -RepoRoot $repoRoot) | Should Be $false
    }
}

Describe 'start-local broadcast send configuration' {
    It 'keeps broadcast send disabled by default in backend launch command' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $command = New-BackendCommand -RepoRoot $repoRoot -SessionId 'session-default-broadcast' -ShutdownRequestPath 'C:\tmp\shutdown.request.json'

        $command.Environment.LANGBOT_BROADCAST_SEND_ENABLED | Should Be '0'
        $command.Environment.LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS | Should Be ''
        $command.BroadcastSend.enabled | Should Be $false
        $command.BroadcastSend.allowedConnectorCount | Should Be 0
    }

    It 'enables broadcast send with an explicit connector allowlist' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $script:EnableBroadcastSend = $true
        $script:BroadcastSendAllowConnectors = @(' wxwork-local ', 'wechat-local', 'wxwork-local', '')

        $command = New-BackendCommand -RepoRoot $repoRoot -SessionId 'session-enabled-broadcast' -ShutdownRequestPath 'C:\tmp\shutdown.request.json'

        $command.Environment.LANGBOT_BROADCAST_SEND_ENABLED | Should Be '1'
        $command.Environment.LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS | Should Be 'wxwork-local,wechat-local'
        $command.BroadcastSend.enabled | Should Be $true
        $command.BroadcastSend.allowedConnectorCount | Should Be 2
    }

    It 'fails when broadcast send is enabled without an allowlist' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        { Resolve-BroadcastSendConfiguration -Enabled $true -AllowConnectors @() } | Should Throw 'When enabling real send, specify at least one Connector ID via -BroadcastSendAllowConnectors.'
    }

    It 'normalizes connector allowlist by trimming removing empties and deduplicating' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $config = Resolve-BroadcastSendConfiguration -Enabled $true -AllowConnectors @(' wxwork-local ', '', 'wechat-local', 'wxwork-local', '   ')

        $config.Environment.LANGBOT_BROADCAST_SEND_ENABLED | Should Be '1'
        $config.Environment.LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS | Should Be 'wxwork-local,wechat-local'
        $config.Summary.enabled | Should Be $true
        $config.Summary.allowedConnectorCount | Should Be 2
    }

    It 'rejects wildcard connector allowlist entries' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        { Resolve-BroadcastSendConfiguration -Enabled $true -AllowConnectors @('*') } | Should Throw 'Connector ID must not contain the wildcard *.'
    }

    It 'reports broadcast send summary in dry-run output' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $script:DryRun = $true
        $script:EnableBroadcastSend = $true
        $script:BroadcastSendAllowConnectors = @('wxwork-local')
        try {
            $summary = New-StartDryRunSummary -WebModeValue 'Bundled'

            $summary.broadcastSend.enabled | Should Be $true
            $summary.broadcastSend.allowedConnectorCount | Should Be 1
            $summary.backend.environment.LANGBOT_BROADCAST_SEND_ENABLED | Should Be '1'
            $summary.backend.environment.LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS | Should Be 'wxwork-local'
        }
        finally {
            $script:DryRun = $false
            $script:EnableBroadcastSend = $false
            $script:BroadcastSendAllowConnectors = @()
        }
    }

    It 'status remains broadcast-send disabled by default when no launcher state exists' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('start-local-tests-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmpRoot | Out-Null
        try {
            $script:StackRoot = $tmpRoot
            $script:ControlDir = Join-Path $script:StackRoot 'control'
            $script:LogsDir = Join-Path $script:StackRoot 'logs'
            $script:StatePath = Join-Path $script:StackRoot 'state.json'
            $script:ShutdownRequestPath = Join-Path $script:ControlDir 'shutdown.request.json'

            $status = Get-StackStatus -RequestedWebMode 'Bundled'

            $status.broadcastSend.enabled | Should Be $false
            $status.broadcastSend.allowedConnectorCount | Should Be 0
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'stop dry run does not enable broadcast send' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $script:DryRun = $true
        try {
            $result = Stop-BackendStack -RequestedWebMode 'Bundled'

            $result.broadcastSend.enabled | Should Be $false
            $result.broadcastSend.allowedConnectorCount | Should Be 0
        }
        finally {
            $script:DryRun = $false
        }
    }
}

Describe 'start-local lifecycle flows' {
    It 'stores processStartTimeUtcTicks in backend and web state' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $state = New-LauncherState -SessionId 'session-1' -BackendRecord @{ pid = 100; processStartTimeUtcTicks = 123456; status = 'running' } -WebRecord @{ pid = 200; processStartTimeUtcTicks = 654321; status = 'running' }

        $state.backend.processStartTimeUtcTicks | Should Be 123456
        $state.web.processStartTimeUtcTicks | Should Be 654321
        ($state.backend.PSObject.Properties.Name -contains 'processCreatedAt') | Should Be $false
    }

    It 'reads process identity through ProcessId-named parameters in real helper calls' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $snapshot = Read-CurrentProcessIdentity -ProcessId $PID

        $snapshot | Should Not Be $null
        [int64]$snapshot.pid | Should Be $PID
        [int64]$snapshot.processStartTimeUtcTicks | Should BeGreaterThan 0
    }

    It 'writes shutdown control file with matching sessionId on Stop helper' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('start-local-tests-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmpRoot | Out-Null
        try {
            $controlPath = Join-Path $tmpRoot 'shutdown.json'
            Request-GracefulBackendShutdown -ControlPath $controlPath -SessionId 'session-2'

            $payload = Get-Content -Raw -LiteralPath $controlPath | ConvertFrom-Json
            $payload.sessionId | Should Be 'session-2'
            $payload.action | Should Be 'shutdown'
            $payload.reason | Should Be 'launcher-stop'
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'keeps bundled web status as not-used when state has null web pid' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('start-local-tests-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmpRoot | Out-Null
        try {
            $script:StackRoot = $tmpRoot
            $script:ControlDir = Join-Path $script:StackRoot 'control'
            $script:LogsDir = Join-Path $script:StackRoot 'logs'
            $script:StatePath = Join-Path $script:StackRoot 'state.json'
            $script:ShutdownRequestPath = Join-Path $script:ControlDir 'shutdown.request.json'

            $state = [ordered]@{
                sessionId = 'session-bundled'
                status = 'running'
                webMode = 'Bundled'
                updatedAt = [DateTime]::UtcNow.ToString('o')
                backend = $null
                web = [ordered]@{
                    role = 'web'
                    status = 'not-used'
                    pid = $null
                    processStartTimeUtcTicks = $null
                    executablePath = $null
                    commandLine = $null
                    repoRoot = $repoRoot
                }
                runtime = [ordered]@{ status = 'managed-by-backend' }
            }
            Save-LauncherState -State $state

            $status = Get-StackStatus -RequestedWebMode 'Bundled'
            $status.web.status | Should Be 'not-used'
            $status.web.pid | Should Be $null
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'uses absolute pnpm cmd path and absolute repo web path in Dev mode' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $cmd = New-WebDevCommand -RepoRoot $repoRoot -BackendUrl 'http://127.0.0.1:5302' -PnpmCmdPath 'C:\tools\pnpm.cmd' -NodeExePath 'C:\tools\node.exe'

        $cmd.FilePath | Should Be 'cmd.exe'
        $cmd.ArgumentList[3] | Should Match '^call\s+"'
        $cmd.ArgumentList[3] | Should Match ([regex]::Escape('C:\tools\node.exe'))
        $cmd.ArgumentList[3] | Should Match ([regex]::Escape((Join-Path $repoRoot 'web\node_modules\vite\bin\vite.js')))
        $cmd.ArgumentList[3] | Should Match '--host 127\.0\.0\.1'
        $cmd.ArgumentList[3] | Should Match '--strictPort'
        $cmd.WorkingDirectory | Should Be (Join-Path $repoRoot 'web')
    }

    It 'refuses to kill a reused PID when creation time differs' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $identity = @{ pid = 10; processStartTimeUtcTicks = 123; executablePath = 'C:\Python\python.exe'; commandLine = 'python main.py'; repoRoot = $repoRoot }
        $snapshot = @{ pid = 10; processStartTimeUtcTicks = 456; executablePath = 'C:\Python\python.exe'; commandLine = 'python main.py'; repoRoot = $repoRoot }

        Test-ManagedProcessOwnership -Identity $identity -Snapshot $snapshot | Should Be $false
    }

    It 'status keeps stored dev web mode after stop without falling back to bundled' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('start-local-tests-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmpRoot | Out-Null
        try {
            $script:StackRoot = $tmpRoot
            $script:ControlDir = Join-Path $script:StackRoot 'control'
            $script:LogsDir = Join-Path $script:StackRoot 'logs'
            $script:StatePath = Join-Path $script:StackRoot 'state.json'
            $script:ShutdownRequestPath = Join-Path $script:ControlDir 'shutdown.request.json'

            Save-LauncherState -State ([ordered]@{
                sessionId = 'dev-session'
                status = 'stopped'
                webMode = 'Dev'
                updatedAt = [DateTime]::UtcNow.ToString('o')
                backend = $null
                web = $null
                runtime = [ordered]@{ status = 'managed-by-backend' }
            })

            $status = Get-StackStatus -RequestedWebMode 'Bundled'
            $status.webMode | Should Be 'Dev'
            $status.web.status | Should Be 'down'
            $status.web.url | Should Be 'http://127.0.0.1:3000'
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'forwards all CMD arguments to start-local.ps1 through percent star' {
        Test-Path -LiteralPath $cmdWrapperPath | Should Be $true
        $content = Get-Content -Raw -LiteralPath $cmdWrapperPath

        $content | Should Match '%\*'
        $content | Should Match 'start-local\.ps1'
    }
}

Describe 'start-local runtime recovery guard' {
    It 'default start refuses unmanaged runtime before backend spawn' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('start-local-tests-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmpRoot | Out-Null
        try {
            $script:StackRoot = $tmpRoot
            $script:ControlDir = Join-Path $script:StackRoot 'control'
            $script:LogsDir = Join-Path $script:StackRoot 'logs'
            $script:StatePath = Join-Path $script:StackRoot 'state.json'
            $script:ShutdownRequestPath = Join-Path $script:ControlDir 'shutdown.request.json'

            Mock Assert-BundledFrontendReady { 'ok' }
            Mock Resolve-ApiConfiguration { [pscustomobject]@{ Host='127.0.0.1'; Port=5302; BaseUrl='http://127.0.0.1:5302'; HealthUrl='http://127.0.0.1:5302/healthz'; ConfigPath='config.yaml' } }
            Mock Get-StackStatus { [ordered]@{ status = 'stopped'; ownership = 'none' } }
            Mock Read-JsonFile { $null }
            Mock Assert-PortAvailableOrOwned { }
            Mock Test-TcpPortListening { $false }
            Mock Assert-NoUnmanagedOfficialRuntime { throw "RUNTIME_OWNERSHIP_CONFLICT`nPID: 6101`nPath: $repoRoot\apps\desktop-rpa-runtime\dist-phase2-official\2026-07-08T00-00-00-000Z\win-unpacked\LangBot Desktop RPA Runtime.exe" }
            Mock Start-ManagedProcess { throw 'must not spawn backend' }

            { Start-BackendStack -WebModeValue 'Bundled' } | Should Throw 'RUNTIME_OWNERSHIP_CONFLICT'
            Assert-MockCalled Assert-NoUnmanagedOfficialRuntime -Times 1 -Exactly
            Assert-MockCalled Start-ManagedProcess -Times 0 -Exactly
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'recover mode stops unmanaged runtime tree before backend spawn' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $validPath = Join-Path $repoRoot 'apps\desktop-rpa-runtime\dist-phase2-official\2026-07-08T00-00-00-000Z\win-unpacked\LangBot Desktop RPA Runtime.exe'
        $script:stoppedRuntimePids = @()

        Mock Get-RepoOfficialRuntimeProcesses {
            @(
                [pscustomobject]@{
                    pid = 6101
                    parentProcessId = 0
                    executablePath = $validPath
                    buildTimestamp = '2026-07-08T00-00-00-000Z'
                }
            )
        }
        Mock Stop-OfficialRuntimeProcessTree {
            param($RuntimeProcess)
            $script:stoppedRuntimePids += [int]$RuntimeProcess.pid
            $true
        }

        Assert-NoUnmanagedOfficialRuntime -RepoRoot $repoRoot -Recover

        $script:stoppedRuntimePids | Should Be @(6101)
        Assert-MockCalled Stop-OfficialRuntimeProcessTree -Times 1 -Exactly
    }
}

Describe 'start-local health waiting and diagnostics' {
    BeforeEach {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath
    }

    It 'dry run reports configurable backend and web timeouts' {
        $script:DryRun = $true
        $script:BackendHealthTimeoutSeconds = 123
        $script:WebHealthTimeoutSeconds = 67
        try {
            $summary = New-StartDryRunSummary -WebModeValue 'Dev'

            $summary.timeout.backendHealthTimeoutSeconds | Should Be 123
            $summary.timeout.webHealthTimeoutSeconds | Should Be 67
            $summary.timeout.pollIntervalMilliseconds | Should Be 500
        }
        finally {
            $script:DryRun = $false
            $script:BackendHealthTimeoutSeconds = 120
            $script:WebHealthTimeoutSeconds = 60
        }
    }

    It 'backend health waiter keeps polling while process is alive and health is not ready' {
        $timeline = New-LauncherDiagnostics -SessionId 'session-keep-polling' -WebModeValue 'Bundled'
        $probeCalls = 0
        $sleepCalls = 0
        $script:probeCalls = 0
        $script:sleepCalls = 0

        Mock Get-ManagedProcessLifecycleStatus { @{ state = 'running'; exitCode = $null } }
        Mock Test-TcpPortListening { $false }
        Mock Invoke-BackendHealthProbe {
            $script:probeCalls++
            if ($script:probeCalls -lt 3) {
                return @{ ready = $false; responded = $false; statusCode = $null; code = $null; msg = $null }
            }
            return @{ ready = $true; responded = $true; statusCode = 200; code = 0; msg = 'ok' }
        }
        Mock Start-Sleep { $script:sleepCalls++ }

        $result = Wait-ForBackendHealth `
            -BackendIdentity @{ pid = 10; processStartTimeUtcTicks = 20 } `
            -HealthUrl 'http://127.0.0.1:5302/healthz' `
            -Address '127.0.0.1' `
            -Port 5302 `
            -TimeoutSeconds 5 `
            -PollIntervalMilliseconds 1 `
            -StdoutLogPath 'stdout.log' `
            -StderrLogPath 'stderr.log' `
            -Diagnostics $timeline

        $result.status | Should Be 'ready'
        $script:probeCalls | Should Be 3
        $script:sleepCalls | Should BeGreaterThan 0
        $timeline.backend.firstValidHealthResponseAtUtc | Should Not Be $null
    }

    It 'backend health waiter fails immediately when owned process exits early' {
        $timeline = New-LauncherDiagnostics -SessionId 'session-exit' -WebModeValue 'Bundled'

        function Get-ManagedProcessLifecycleStatus { [pscustomobject]@{ state = 'exited'; exitCode = 23; exitedAtUtc = '2026-07-06T12:00:00.0000000Z' } }
        function Get-LogTail {
            param([string]$Path)
            if ($Path -like '*stdout*') { return @('stdout tail') }
            return @('stderr tail')
        }
        function Start-Sleep { throw 'should not sleep after exit' }

        $result = Wait-ForBackendHealth `
            -BackendIdentity @{ pid = 11; processStartTimeUtcTicks = 22 } `
            -HealthUrl 'http://127.0.0.1:5302/healthz' `
            -Address '127.0.0.1' `
            -Port 5302 `
            -TimeoutSeconds 5 `
            -PollIntervalMilliseconds 1 `
            -StdoutLogPath 'stdout.log' `
            -StderrLogPath 'stderr.log' `
            -Diagnostics $timeline

        $result.status | Should Be 'exited'
        $result.exitCode | Should Be 23
        $result.stdoutTail[0] | Should Be 'stdout tail'
        $timeline.backend.exitAtUtc | Should Be '2026-07-06T12:00:00.0000000Z'
    }

    It 'backend health waiter times out with log tail when process stays alive without ready health' {
        $timeline = New-LauncherDiagnostics -SessionId 'session-timeout' -WebModeValue 'Bundled'
        $probeCalls = 0
        $script:probeCalls = 0

        function Get-ManagedProcessLifecycleStatus { @{ state = 'running'; exitCode = $null } }
        function Test-TcpPortListening { $script:probeCalls -ge 2 }
        Mock Invoke-BackendHealthProbe {
            $script:probeCalls++
            @{ ready = $false; responded = ($script:probeCalls -ge 3); statusCode = 503; code = 1; msg = 'warming' }
        }
        function Get-LogTail { @('tail-1', 'tail-2') }
        function Start-Sleep { }

        $result = Wait-ForBackendHealth `
            -BackendIdentity @{ pid = 12; processStartTimeUtcTicks = 24 } `
            -HealthUrl 'http://127.0.0.1:5302/healthz' `
            -Address '127.0.0.1' `
            -Port 5302 `
            -TimeoutSeconds 0 `
            -PollIntervalMilliseconds 1 `
            -StdoutLogPath 'stdout.log' `
            -StderrLogPath 'stderr.log' `
            -Diagnostics $timeline

        $result.status | Should Be 'timeout'
        $result.stdoutTail.Count | Should Be 2
    }

    It 'health probe accepts only code zero and ok message as ready' {
        Mock Invoke-WebRequest {
            [pscustomobject]@{
                StatusCode = 200
                Content = '{"code":0,"msg":"starting"}'
            }
        }

        $probe = Invoke-BackendHealthProbe -Url 'http://127.0.0.1:5302/healthz'
        $probe.responded | Should Be $true
        $probe.ready | Should Be $false
        $probe.statusCode | Should Be 200
    }
}

Describe 'start-local sequencing and rollback guards' {
    BeforeEach {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath
    }

    It 'dev start does not launch vite before backend health succeeds' {
        $tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('start-local-tests-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmpRoot | Out-Null
        try {
            $script:StackRoot = $tmpRoot
            $script:ControlDir = Join-Path $script:StackRoot 'control'
            $script:LogsDir = Join-Path $script:StackRoot 'logs'
            $script:StatePath = Join-Path $script:StackRoot 'state.json'
            $script:ShutdownRequestPath = Join-Path $script:ControlDir 'shutdown.request.json'

            $script:calls = New-Object System.Collections.Generic.List[string]
            Mock Assert-PortAvailableOrOwned { }
            Mock Test-TcpPortListening { $false }
            Mock Read-JsonFile { $null }
            Mock Get-NetTCPConnection { param([string]$State, [int[]]$LocalPort, $ErrorAction) $null }
            Mock Get-ProcessIdentitySnapshot { $null }
            Mock Resolve-ApiConfiguration { [pscustomobject]@{ Host='127.0.0.1'; Port=5302; BaseUrl='http://127.0.0.1:5302'; HealthUrl='http://127.0.0.1:5302/healthz'; ConfigPath='config.yaml' } }
            Mock Start-ManagedProcess {
                param([string]$FilePath)
                $script:calls.Add($FilePath) | Out-Null
                if ($FilePath -eq 'cmd.exe') {
                    return [pscustomobject]@{ Id = 202 }
                }
                return [pscustomobject]@{ Id = 101 }
            }
            Mock Read-CurrentProcessIdentity {
                param([int]$ProcessId)
                @{ pid = $ProcessId; processStartTimeUtcTicks = 1000 + $ProcessId; executablePath = if ($ProcessId -eq 202) { 'C:\Windows\System32\cmd.exe' } else { 'C:\Python\python.exe' }; commandLine = "pid-$ProcessId" }
            }
            Mock Wait-ForBackendHealth {
                $script:calls.Add('backend-health-ok') | Out-Null
                @{ status = 'ready' }
            }
            Mock Wait-ForHttpOk {
                $script:calls.Add('web-health-ok') | Out-Null
                $true
            }
            Mock Save-LauncherState { }
            Mock Remove-StaleShutdownRequest { }
            Mock Write-LauncherDiagnostics { }
            Mock New-WebDevCommand { [pscustomobject]@{ FilePath='cmd.exe'; ArgumentList=@('/d','/s','/c','call "C:\pnpm.cmd" --dir "C:\repo\web" dev'); WorkingDirectory=$repoRoot; Environment=@{ VITE_API_BASE_URL='http://127.0.0.1:5302' }; WebPath=(Join-Path $repoRoot 'web'); PnpmCmdPath='C:\pnpm.cmd' } }
            Mock Assert-NoUnmanagedOfficialRuntime { }

            $result = Start-BackendStack -WebModeValue 'Dev'

            $result.status | Should Be 'running'
            $script:calls[0] | Should Not Be 'cmd.exe'
            $script:calls[1] | Should Be 'backend-health-ok'
            $script:calls[2] | Should Be 'cmd.exe'
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'rollback timeout only targets owned backend and writes graceful shutdown first' {
        $backendIdentity = @{ pid = 303; processStartTimeUtcTicks = 404; executablePath = 'C:\Python\python.exe'; commandLine = 'python main.py'; repoRoot = $repoRoot }
        $timeline = New-LauncherDiagnostics -SessionId 'session-rollback' -WebModeValue 'Dev'
        $script:calls = New-Object System.Collections.Generic.List[string]

        Mock Request-GracefulBackendShutdown { $script:calls.Add('graceful') | Out-Null }
        Mock Wait-ForProcessExit { $script:calls.Add('wait-exit') | Out-Null; $false }
        Mock Stop-RepoOwnedProcess { $script:calls.Add('taskkill') | Out-Null; $true }
        Mock Remove-LauncherState { $script:calls.Add('remove-state') | Out-Null }
        function Remove-StaleShutdownRequest { $script:calls.Add('remove-shutdown') | Out-Null }

        Rollback-PartialStart -BackendIdentity $backendIdentity -WebIdentity $null -SessionId 'session-rollback' -Diagnostics $timeline

        $script:calls[0] | Should Be 'graceful'
        $script:calls[1] | Should Be 'wait-exit'
        $script:calls[2] | Should Be 'taskkill'
        ($script:calls -contains 'remove-shutdown') | Should Be $true
        $timeline.rollback.startedAtUtc | Should Not Be $null
        $timeline.rollback.endedAtUtc | Should Not Be $null
    }

    It 'stale shutdown request can be deleted before a new session starts' {
        $tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('start-local-tests-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmpRoot | Out-Null
        try {
            $controlDir = Join-Path $tmpRoot 'control'
            New-Item -ItemType Directory -Path $controlDir | Out-Null
            $requestPath = Join-Path $controlDir 'shutdown.request.json'
            Set-Content -LiteralPath $requestPath -Value '{"sessionId":"old-session","action":"shutdown"}'

            Remove-StaleShutdownRequest -Path $requestPath

            Test-Path -LiteralPath $requestPath | Should Be $false
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'bundled start fails fast when web dist index is missing and does not create state' {
        $tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('start-local-tests-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmpRoot | Out-Null
        $repo = Join-Path $tmpRoot 'repo'
        New-Item -ItemType Directory -Path (Join-Path $repo 'scripts') -Force | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $repo 'web\dist') -Force | Out-Null
        try {
            . $scriptPath
            $script:RepoRoot = $repo
            $script:StackRoot = Join-Path $repo '.tmp\local-stack'
            $script:ControlDir = Join-Path $script:StackRoot 'control'
            $script:LogsDir = Join-Path $script:StackRoot 'logs'
            $script:StatePath = Join-Path $script:StackRoot 'state.json'
            $script:ShutdownRequestPath = Join-Path $script:ControlDir 'shutdown.request.json'

            Mock Resolve-ApiConfiguration { [pscustomobject]@{ Host='127.0.0.1'; Port=5302; BaseUrl='http://127.0.0.1:5302'; HealthUrl='http://127.0.0.1:5302/healthz'; ConfigPath='config.yaml' } }
            Mock Read-JsonFile { $null }
            Mock Test-TcpPortListening { $false }
            Mock Assert-PortAvailableOrOwned { }
            Mock Start-ManagedProcess { throw 'should not spawn backend' }

            $didThrow = $false
            $message = ''
            try {
                Start-BackendStack -WebModeValue 'Bundled' | Out-Null
            }
            catch {
                $didThrow = $true
                $message = $_.Exception.Message
            }
            $didThrow | Should Be $true
            $message | Should Match 'index\.html'
            Test-Path -LiteralPath $script:StatePath | Should Be $false
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'restart does not start when stop fails' {
        . $scriptPath
        $script:Action = 'Restart'
        $script:WebMode = 'Bundled'
        $script:restartStopCalls = 0
        $script:restartStartCalls = 0
        function Stop-BackendStack {
            param([string]$RequestedWebMode)
            $script:restartStopCalls += 1
            throw 'stop failed'
        }
        function Start-BackendStack {
            param([string]$WebModeValue)
            $script:restartStartCalls += 1
            throw 'must not start'
        }

        $didThrow = $false
        $message = ''
        try {
            Invoke-StartLocal | Out-Null
        }
        catch {
            $didThrow = $true
            $message = $_.Exception.Message
        }
        $script:restartStopCalls | Should Be 1
        $didThrow | Should Be $true
        $message | Should Match 'stop failed'
        $script:restartStartCalls | Should Be 0
    }

}

Describe 'start-local ownership and fail-closed behavior' {
    BeforeEach {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath
    }

    AfterEach {
        foreach ($fn in @(
            'Get-NetTCPConnection',
            'Get-ProcessIdentitySnapshot',
            'Get-CimInstance',
            'Invoke-WebRequest'
        )) {
            Remove-Item -Path ("Function:\{0}" -f $fn) -Force -ErrorAction SilentlyContinue
        }
    }

    function New-TestStackRoot {
        $tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('start-local-tests-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmpRoot | Out-Null
        $script:StackRoot = $tmpRoot
        $script:ControlDir = Join-Path $script:StackRoot 'control'
        $script:LogsDir = Join-Path $script:StackRoot 'logs'
        $script:StatePath = Join-Path $script:StackRoot 'state.json'
        $script:ShutdownRequestPath = Join-Path $script:ControlDir 'shutdown.request.json'
        return $tmpRoot
    }

    function New-TestRecord {
        param(
            [Parameter(Mandatory = $true)][string]$Role,
            [Parameter(Mandatory = $true)][Alias('Pid')][int]$RecordPid,
            [Parameter(Mandatory = $true)][int64]$Ticks,
            [Parameter(Mandatory = $true)][string]$ExecutablePath,
            [Parameter(Mandatory = $true)][string]$CommandLine
        )

        return [ordered]@{
            role = $Role
            status = 'running'
            pid = $RecordPid
            processStartTimeUtcTicks = $Ticks
            executablePath = $ExecutablePath
            commandLine = $CommandLine
            repoRoot = $repoRoot
        }
    }

    It 'captures backend ownership inputs before the closure runs' {
        $escapedRepoRoot = $repoRoot.Replace("'", "''")
        $proc = Start-Process `
            -FilePath 'powershell.exe' `
            -ArgumentList @(
                '-NoProfile',
                '-Command',
                "Set-Location -LiteralPath '$escapedRepoRoot'; Start-Sleep -Seconds 8"
            ) `
            -WindowStyle Hidden `
            -PassThru
        try {
            Start-Sleep -Milliseconds 300
            $snapshot = Read-CurrentProcessIdentity -ProcessId $proc.Id
            $identity = [pscustomobject]@{
                pid = $snapshot.pid
                processStartTimeUtcTicks = $snapshot.processStartTimeUtcTicks
                executablePath = $snapshot.executablePath
                commandLine = $snapshot.commandLine
                repoRoot = $repoRoot
            }

            $ownerCheck = Get-StateOwnedBackendCheck -State ([pscustomobject]@{
                backend = $identity
            })

            $script:RepoRoot = $null

            (& $ownerCheck) | Should Be $true
        }
        finally {
            $proc | Stop-Process -Force -ErrorAction SilentlyContinue
        }
    }

    It 'fails Stop closed when persisted session differs from detected listener owner' {
        $tmpRoot = New-TestStackRoot
        try {
            $state = [ordered]@{
                sessionId = 'session-a'
                status = 'running'
                webMode = 'Bundled'
                updatedAt = [DateTime]::UtcNow.ToString('o')
                backend = New-TestRecord -Role 'backend' -Pid 101 -Ticks 1001 -ExecutablePath 'C:\Python\python.exe' -CommandLine "C:\Python\python.exe $repoRoot\main.py --session session-a"
                web = $null
                runtime = [ordered]@{ status = 'managed-by-backend' }
            }
            Save-LauncherState -State $state

            function Get-NetTCPConnection {
                param([string]$State, [int[]]$LocalPort, $ErrorAction)
                if ($LocalPort -contains (Resolve-ApiConfiguration -RepoRoot $repoRoot).Port) {
                    return [pscustomobject]@{ OwningProcess = 202 }
                }
                return $null
            }
            function Get-ProcessIdentitySnapshot {
                param([int]$ProcessId)
                switch ($ProcessId) {
                    101 { return $null }
                    202 { return [pscustomobject](New-TestRecord -Role 'backend' -Pid 202 -Ticks 2002 -ExecutablePath 'C:\Python\python.exe' -CommandLine "C:\Python\python.exe $repoRoot\main.py --session session-b") }
                    default { return $null }
                }
            }
            function Get-CimInstance { param($ClassName, $Filter, $ErrorAction) [pscustomobject]@{ ParentProcessId = 0 } }
            Mock Request-GracefulBackendShutdown { }
            Mock Stop-RepoOwnedProcess { $true }

            { Stop-BackendStack -RequestedWebMode 'Bundled' } | Should Throw 'STOP_OWNERSHIP_UNKNOWN'
            Assert-MockCalled Request-GracefulBackendShutdown -Times 0 -Exactly
            Assert-MockCalled Stop-RepoOwnedProcess -Times 0 -Exactly
            Test-Path -LiteralPath $script:StatePath | Should Be $true
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'prevents Restart from starting a new stack after Stop ownership failure' {
        $tmpRoot = New-TestStackRoot
        try {
            $state = [ordered]@{
                sessionId = 'session-a'
                status = 'running'
                webMode = 'Bundled'
                updatedAt = [DateTime]::UtcNow.ToString('o')
                backend = New-TestRecord -Role 'backend' -Pid 101 -Ticks 1001 -ExecutablePath 'C:\Python\python.exe' -CommandLine "C:\Python\python.exe $repoRoot\main.py --session session-a"
                web = $null
                runtime = [ordered]@{ status = 'managed-by-backend' }
            }
            Save-LauncherState -State $state

            $script:Action = 'Restart'
            $script:WebMode = 'Bundled'

            function Get-NetTCPConnection {
                param([string]$State, [int[]]$LocalPort, $ErrorAction)
                if ($LocalPort -contains (Resolve-ApiConfiguration -RepoRoot $repoRoot).Port) {
                    return [pscustomobject]@{ OwningProcess = 202 }
                }
                return $null
            }
            function Get-ProcessIdentitySnapshot {
                param([int]$ProcessId)
                switch ($ProcessId) {
                    101 { return $null }
                    202 { return [pscustomobject](New-TestRecord -Role 'backend' -Pid 202 -Ticks 2002 -ExecutablePath 'C:\Python\python.exe' -CommandLine "C:\Python\python.exe $repoRoot\main.py --session session-b") }
                    default { return $null }
                }
            }
            function Get-CimInstance { param($ClassName, $Filter, $ErrorAction) [pscustomobject]@{ ParentProcessId = 0 } }
            Mock Request-GracefulBackendShutdown { }
            Mock Stop-RepoOwnedProcess { $true }
            Mock Start-ManagedProcess { throw 'must not start after stop ownership failure' }

            { Invoke-StartLocal | Out-Null } | Should Throw 'STOP_OWNERSHIP_UNKNOWN'
            Assert-MockCalled Start-ManagedProcess -Times 0 -Exactly
            ((Read-JsonFile -Path $script:StatePath).sessionId) | Should Be 'session-a'
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'keeps persisted backend identity and reports ownership unknown when listener belongs to another session' {
        $tmpRoot = New-TestStackRoot
        try {
            $state = [ordered]@{
                sessionId = 'session-a'
                status = 'running'
                webMode = 'Bundled'
                updatedAt = [DateTime]::UtcNow.ToString('o')
                backend = New-TestRecord -Role 'backend' -Pid 101 -Ticks 1001 -ExecutablePath 'C:\Python\python.exe' -CommandLine "C:\Python\python.exe $repoRoot\main.py --session session-a"
                web = $null
                runtime = [ordered]@{ status = 'managed-by-backend' }
            }
            Save-LauncherState -State $state

            function Get-NetTCPConnection {
                param([string]$State, [int[]]$LocalPort, $ErrorAction)
                if ($LocalPort -contains (Resolve-ApiConfiguration -RepoRoot $repoRoot).Port) {
                    return [pscustomobject]@{ OwningProcess = 202 }
                }
                return $null
            }
            function Get-ProcessIdentitySnapshot {
                param([int]$ProcessId)
                switch ($ProcessId) {
                    101 { return $null }
                    202 { return [pscustomobject](New-TestRecord -Role 'backend' -Pid 202 -Ticks 2002 -ExecutablePath 'C:\Python\python.exe' -CommandLine "C:\Python\python.exe $repoRoot\main.py --session session-b") }
                    default { return $null }
                }
            }
            function Get-CimInstance { param($ClassName, $Filter, $ErrorAction) [pscustomobject]@{ ParentProcessId = 0 } }
            function Invoke-WebRequest { throw 'health unavailable' }

            $status = Get-StackStatus -RequestedWebMode 'Bundled'

            $status.sessionId | Should Be 'session-a'
            $status.status | Should Be 'degraded'
            $status.ownership | Should Be 'unknown'
            $status.backend.pid | Should Be 101
            $status.backend.ownership | Should Be 'unknown'
            $status.detectedComponents.backend.pid | Should Be 202
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'fails repeated Bundled Start closed when bundled assets are missing before backend-only recovery' {
        $tmpRoot = New-TestStackRoot
        try {
            $state = [ordered]@{
                sessionId = 'session-process-up'
                status = 'running'
                webMode = 'Bundled'
                updatedAt = [DateTime]::UtcNow.ToString('o')
                backend = New-TestRecord -Role 'backend' -Pid 101 -Ticks 1001 -ExecutablePath 'C:\Python\python.exe' -CommandLine "C:\Python\python.exe $repoRoot\main.py --session session-process-up"
                web = $null
                runtime = [ordered]@{ status = 'managed-by-backend' }
            }
            Save-LauncherState -State $state

            function Get-NetTCPConnection { param([string]$State, [int[]]$LocalPort, $ErrorAction) $null }
            function Get-ProcessIdentitySnapshot {
                param([int]$ProcessId)
                if ($ProcessId -eq 101) {
                    return [pscustomobject](New-TestRecord -Role 'backend' -Pid 101 -Ticks 1001 -ExecutablePath 'C:\Python\python.exe' -CommandLine "C:\Python\python.exe $repoRoot\main.py --session session-process-up")
                }
                return $null
            }
            function Invoke-WebRequest { throw 'health failed' }
            Mock Start-ManagedProcess { throw 'must not spawn second backend' }

            { Start-BackendStack -WebModeValue 'Bundled' } | Should Throw 'Bundled frontend entry is missing'
            Assert-MockCalled Start-ManagedProcess -Times 0 -Exactly
            ((Read-JsonFile -Path $script:StatePath).sessionId) | Should Be 'session-process-up'
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'fails repeated Dev Start closed when web component is missing' {
        $tmpRoot = New-TestStackRoot
        try {
            $state = [ordered]@{
                sessionId = 'session-dev-missing-web'
                status = 'running'
                webMode = 'Dev'
                updatedAt = [DateTime]::UtcNow.ToString('o')
                backend = New-TestRecord -Role 'backend' -Pid 101 -Ticks 1001 -ExecutablePath 'C:\Python\python.exe' -CommandLine "C:\Python\python.exe $repoRoot\main.py --session session-dev-missing-web"
                web = New-TestRecord -Role 'web' -Pid 303 -Ticks 3003 -ExecutablePath 'C:\Windows\System32\cmd.exe' -CommandLine ('cmd.exe /d /s /c call "{0}\web\node_modules\vite\bin\vite.js"' -f $repoRoot)
                runtime = [ordered]@{ status = 'managed-by-backend' }
            }
            Save-LauncherState -State $state

            function Get-NetTCPConnection { param([string]$State, [int[]]$LocalPort, $ErrorAction) $null }
            function Get-ProcessIdentitySnapshot {
                param([int]$ProcessId)
                if ($ProcessId -eq 101) {
                    return [pscustomobject](New-TestRecord -Role 'backend' -Pid 101 -Ticks 1001 -ExecutablePath 'C:\Python\python.exe' -CommandLine "C:\Python\python.exe $repoRoot\main.py --session session-dev-missing-web")
                }
                return $null
            }
            function Invoke-WebRequest {
                [pscustomobject]@{
                    StatusCode = 200
                    Content = '{"code":0,"msg":"ok"}'
                }
            }
            Mock Start-ManagedProcess { throw 'must not auto-start missing web' }

            { Start-BackendStack -WebModeValue 'Dev' } | Should Throw 'STACK_NOT_HEALTHY'
            Assert-MockCalled Start-ManagedProcess -Times 0 -Exactly
            ((Read-JsonFile -Path $script:StatePath).sessionId) | Should Be 'session-dev-missing-web'
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'reports manual repo Vite without state as degraded ownership unknown and does not create state' {
        $tmpRoot = New-TestStackRoot
        try {
            function Get-NetTCPConnection {
                param([string]$State, [int[]]$LocalPort, $ErrorAction)
                if ($LocalPort -contains 3000) {
                    return [pscustomobject]@{ OwningProcess = 222 }
                }
                return $null
            }
            function Get-ProcessIdentitySnapshot {
                param([int]$ProcessId)
                if ($ProcessId -eq 222) {
                    return [pscustomobject](New-TestRecord -Role 'web' -Pid 222 -Ticks 2222 -ExecutablePath 'C:\Windows\System32\cmd.exe' -CommandLine ('cmd.exe /d /s /c call "{0}\web\node_modules\vite\bin\vite.js" --port 3000' -f $repoRoot))
                }
                return $null
            }
            function Get-CimInstance { param($ClassName, $Filter, $ErrorAction) [pscustomobject]@{ ParentProcessId = 0 } }

            $status = Get-StackStatus -RequestedWebMode 'Dev'

            $status.status | Should Be 'degraded'
            $status.ownership | Should Be 'unknown'
            $status.web.status | Should Be 'down'
            $status.detectedComponents.web.pid | Should Be 222
            Test-Path -LiteralPath $script:StatePath | Should Be $false
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'fails Stop closed for manual repo Vite without state' {
        $tmpRoot = New-TestStackRoot
        try {
            function Get-NetTCPConnection {
                param([string]$State, [int[]]$LocalPort, $ErrorAction)
                if ($LocalPort -contains 3000) {
                    return [pscustomobject]@{ OwningProcess = 222 }
                }
                return $null
            }
            function Get-ProcessIdentitySnapshot {
                param([int]$ProcessId)
                if ($ProcessId -eq 222) {
                    return [pscustomobject](New-TestRecord -Role 'web' -Pid 222 -Ticks 2222 -ExecutablePath 'C:\Windows\System32\cmd.exe' -CommandLine ('cmd.exe /d /s /c call "{0}\web\node_modules\vite\bin\vite.js" --port 3000' -f $repoRoot))
                }
                return $null
            }
            function Get-CimInstance { param($ClassName, $Filter, $ErrorAction) [pscustomobject]@{ ParentProcessId = 0 } }
            Mock Stop-RepoOwnedProcess { $true }

            { Stop-BackendStack -RequestedWebMode 'Dev' } | Should Throw 'STOP_OWNERSHIP_UNKNOWN'
            Assert-MockCalled Stop-RepoOwnedProcess -Times 0 -Exactly
            Test-Path -LiteralPath $script:StatePath | Should Be $false
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'reports manual repo backend without state as degraded ownership unknown and does not create state' {
        $tmpRoot = New-TestStackRoot
        try {
            function Get-NetTCPConnection {
                param([string]$State, [int[]]$LocalPort, $ErrorAction)
                if ($LocalPort -contains (Resolve-ApiConfiguration -RepoRoot $repoRoot).Port) {
                    return [pscustomobject]@{ OwningProcess = 333 }
                }
                return $null
            }
            function Get-ProcessIdentitySnapshot {
                param([int]$ProcessId)
                if ($ProcessId -eq 333) {
                    return [pscustomobject](New-TestRecord -Role 'backend' -Pid 333 -Ticks 3333 -ExecutablePath 'C:\Python\python.exe' -CommandLine "C:\Python\python.exe $repoRoot\main.py")
                }
                return $null
            }
            function Get-CimInstance { param($ClassName, $Filter, $ErrorAction) [pscustomobject]@{ ParentProcessId = 0 } }
            function Invoke-WebRequest {
                [pscustomobject]@{
                    StatusCode = 200
                    Content = '{"code":0,"msg":"ok"}'
                }
            }

            $status = Get-StackStatus -RequestedWebMode 'Bundled'

            $status.status | Should Be 'degraded'
            $status.ownership | Should Be 'unknown'
            $status.backend.status | Should Be 'down'
            $status.detectedComponents.backend.pid | Should Be 333
            Test-Path -LiteralPath $script:StatePath | Should Be $false
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'allows forced kill only after exact identity verification and graceful timeout' {
        $tmpRoot = New-TestStackRoot
        try {
            $state = [ordered]@{
                sessionId = 'session-owned'
                status = 'running'
                webMode = 'Bundled'
                updatedAt = [DateTime]::UtcNow.ToString('o')
                backend = New-TestRecord -Role 'backend' -Pid 101 -Ticks 1001 -ExecutablePath 'C:\Python\python.exe' -CommandLine "C:\Python\python.exe $repoRoot\main.py --session session-owned"
                web = $null
                runtime = [ordered]@{ status = 'managed-by-backend' }
            }
            Save-LauncherState -State $state

            function Get-NetTCPConnection { param([string]$State, [int[]]$LocalPort, $ErrorAction) $null }
            function Get-ProcessIdentitySnapshot {
                param([int]$ProcessId)
                if ($ProcessId -eq 101) {
                    return [pscustomobject](New-TestRecord -Role 'backend' -Pid 101 -Ticks 1001 -ExecutablePath 'C:\Python\python.exe' -CommandLine "C:\Python\python.exe $repoRoot\main.py --session session-owned")
                }
                return $null
            }
            $script:stopFlowCalls = New-Object System.Collections.Generic.List[string]
            function Request-GracefulBackendShutdown {
                $script:stopFlowCalls.Add('graceful') | Out-Null
            }
            function Wait-ForProcessExit {
                $script:stopFlowCalls.Add('wait') | Out-Null
                return $false
            }
            function Stop-RepoOwnedProcess {
                param($Identity)
                $script:stopFlowCalls.Add(("kill:{0}" -f [int]$Identity.pid)) | Out-Null
                return $true
            }
            function Invoke-WebRequest {
                [pscustomobject]@{
                    StatusCode = 200
                    Content = '{"code":0,"msg":"ok"}'
                }
            }

            Stop-BackendStack -RequestedWebMode 'Bundled' | Out-Null

            $script:stopFlowCalls[0] | Should Be 'graceful'
            $script:stopFlowCalls[1] | Should Be 'wait'
            $script:stopFlowCalls[2] | Should Be 'kill:101'
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'treats PID reuse as ownership unknown and never shuts it down' {
        $tmpRoot = New-TestStackRoot
        try {
            $state = [ordered]@{
                sessionId = 'session-a'
                status = 'running'
                webMode = 'Bundled'
                updatedAt = [DateTime]::UtcNow.ToString('o')
                backend = New-TestRecord -Role 'backend' -Pid 101 -Ticks 1001 -ExecutablePath 'C:\Python\python.exe' -CommandLine "C:\Python\python.exe $repoRoot\main.py --session session-a"
                web = $null
                runtime = [ordered]@{ status = 'managed-by-backend' }
            }
            Save-LauncherState -State $state

            function Get-NetTCPConnection {
                param([string]$State, [int[]]$LocalPort, $ErrorAction)
                if ($LocalPort -contains (Resolve-ApiConfiguration -RepoRoot $repoRoot).Port) {
                    return [pscustomobject]@{ OwningProcess = 101 }
                }
                return $null
            }
            function Get-ProcessIdentitySnapshot {
                param([int]$ProcessId)
                if ($ProcessId -eq 101) {
                    return [pscustomobject](New-TestRecord -Role 'backend' -Pid 101 -Ticks 9999 -ExecutablePath 'C:\Python\python.exe' -CommandLine "C:\Python\python.exe $repoRoot\main.py --session session-b")
                }
                return $null
            }
            function Get-CimInstance { param($ClassName, $Filter, $ErrorAction) [pscustomobject]@{ ParentProcessId = 0 } }
            Mock Request-GracefulBackendShutdown { }
            Mock Stop-RepoOwnedProcess { $true }

            { Stop-BackendStack -RequestedWebMode 'Bundled' } | Should Throw 'STOP_OWNERSHIP_UNKNOWN'
            Assert-MockCalled Request-GracefulBackendShutdown -Times 0 -Exactly
            Assert-MockCalled Stop-RepoOwnedProcess -Times 0 -Exactly
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'Status remains read-only when unmanaged components are observed' {
        $tmpRoot = New-TestStackRoot
        try {
            function Get-NetTCPConnection {
                param([string]$State, [int[]]$LocalPort, $ErrorAction)
                if ($LocalPort -contains (Resolve-ApiConfiguration -RepoRoot $repoRoot).Port) {
                    return [pscustomobject]@{ OwningProcess = 333 }
                }
                return $null
            }
            function Get-ProcessIdentitySnapshot {
                param([int]$ProcessId)
                if ($ProcessId -eq 333) {
                    return [pscustomobject](New-TestRecord -Role 'backend' -Pid 333 -Ticks 3333 -ExecutablePath 'C:\Python\python.exe' -CommandLine "C:\Python\python.exe $repoRoot\main.py")
                }
                return $null
            }
            function Get-CimInstance { param($ClassName, $Filter, $ErrorAction) [pscustomobject]@{ ParentProcessId = 0 } }
            function Invoke-WebRequest {
                [pscustomobject]@{
                    StatusCode = 200
                    Content = '{"code":0,"msg":"ok"}'
                }
            }
            Mock Remove-LauncherState { throw 'status must be read-only' }
            Mock Remove-StaleShutdownRequest { throw 'status must be read-only' }
            Mock Stop-RepoOwnedProcess { throw 'status must be read-only' }

            $status = Get-StackStatus -RequestedWebMode 'Bundled'

            $status.status | Should Be 'degraded'
            Test-Path -LiteralPath $script:StatePath | Should Be $false
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

Describe 'start-local stop failure guard' {
    It 'stop failure keeps state and returns non-stopped status' {
        . $scriptPath
        $script:WebMode = 'Bundled'
        $state = [pscustomobject]@{
            sessionId = 'session-stop-fail'
            status = 'running'
            webMode = 'Bundled'
            updatedAt = [DateTime]::UtcNow.ToString('o')
            backend = [pscustomobject]@{
                role = 'backend'
                status = 'running'
                pid = 999
                processStartTimeUtcTicks = 123
                executablePath = 'C:\Python\python.exe'
                commandLine = 'python main.py'
                repoRoot = $repoRoot
            }
            web = $null
            runtime = [pscustomobject]@{ status = 'managed-by-backend' }
        }

        $tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('start-local-tests-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmpRoot | Out-Null
        Mock Wait-ForProcessExit { $false }
        try {
            $script:StackRoot = $tmpRoot
            $script:ControlDir = Join-Path $script:StackRoot 'control'
            $script:LogsDir = Join-Path $script:StackRoot 'logs'
            $script:StatePath = Join-Path $script:StackRoot 'state.json'
            $script:ShutdownRequestPath = Join-Path $script:ControlDir 'shutdown.request.json'

            Save-LauncherState -State $state

        Mock Get-NetTCPConnection { param([string]$State, [int[]]$LocalPort, $ErrorAction) $null }
            Mock Get-ProcessIdentitySnapshot {
                param([int]$ProcessId)
                if ($ProcessId -eq 999) {
                    return [pscustomobject]@{
                        pid = 999
                        processStartTimeUtcTicks = 123
                        executablePath = 'C:\Python\python.exe'
                        commandLine = 'python main.py'
                        repoRoot = $repoRoot
                    }
                }
                return $null
            }
            Mock Invoke-WebRequest {
                [pscustomobject]@{
                    StatusCode = 200
                    Content = '{"code":0,"msg":"ok"}'
                }
            }
            Mock Stop-RepoOwnedProcess { $false }
            Mock Request-GracefulBackendShutdown { }
            Mock Remove-LauncherState { throw 'state must be preserved' }

            $didThrow = $false
            $message = ''
            try {
                Stop-BackendStack -RequestedWebMode 'Bundled' | Out-Null
            }
            catch {
                $didThrow = $true
                $message = $_.Exception.Message
            }
            Assert-MockCalled Stop-RepoOwnedProcess -Times 1 -Exactly
            $didThrow | Should Be $true
            $message | Should Match 'failed'
            Assert-MockCalled Remove-LauncherState -Times 0 -Exactly
        }
        finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
