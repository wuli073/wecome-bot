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
        $config.Port | Should Be 5302
    }

    It 'forces safe-send environment variables in backend launch command without setting runtime token' {
        Test-Path -LiteralPath $scriptPath | Should Be $true
        . $scriptPath

        $command = New-BackendCommand -RepoRoot $repoRoot -SessionId 'session-safe' -ShutdownRequestPath 'C:\tmp\shutdown.request.json'

        $command.Environment.LANGBOT_RPA_FORCE_DISABLE_SEND | Should Be '1'
        $command.Environment.LANGBOT_RPA_ALLOW_AUTO_SEND | Should Be '0'
        $command.Environment.LANGBOT_BROADCAST_SEND_ENABLED | Should Be '0'
        $command.Environment.PYTHONPATH | Should Be (Join-Path $repoRoot 'src')
        ($command.Environment.ContainsKey('LANGBOT_RPA_TOKEN')) | Should Be $false
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

        Mock Read-JsonFile { $state }
        Mock Wait-ForProcessExit { $false }
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
}
