#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('Start', 'Stop', 'Status')]
    [string]$Action = 'Start',
    [string]$UserDataRoot,
    [int]$BackendPort = 5300,
    [int]$WebPort = 3000,
    [int]$StartupTimeoutSeconds = 120,
    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'console-mode.ps1')
Disable-ConsoleQuickEdit | Out-Null

$script:RepoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $UserDataRoot) { $UserDataRoot = Join-Path $script:RepoRoot '.tmp\source-runtime\user-data' }
$script:UserDataRoot = [IO.Path]::GetFullPath($UserDataRoot)
$script:StatePath = Join-Path $script:UserDataRoot 'runtime\source-stack-state.json'
$script:LogsRoot = Join-Path $script:UserDataRoot 'logs\source'
$script:ControlRoot = Join-Path $script:RepoRoot '.tmp\local-stack\control'
$script:BaseUrl = "http://127.0.0.1:$BackendPort"
$script:WebUrl = "http://127.0.0.1:$WebPort"
$script:RuntimeRoot = Join-Path $script:RepoRoot 'apps\desktop-rpa-runtime'
$script:RuntimeExecutable = [IO.Path]::GetFullPath((Join-Path $script:RuntimeRoot 'dist-phase2-official\win-dir\win-unpacked\LangBot Desktop RPA Runtime.exe'))
$script:RuntimeUserDataRoot = Join-Path $script:UserDataRoot 'desktop-runtime'
. (Join-Path $PSScriptRoot 'source-state.ps1')

function Ensure-Directory([string]$Path) { New-Item -ItemType Directory -Force -Path $Path | Out-Null }
function Write-DesktopRuntimeEvent([string]$EventName, $RuntimeRecord, [string]$Status = '') {
    $logPath = Join-Path $script:LogsRoot 'desktop-runtime.stdout.log'
    $payload = [ordered]@{
        event = $EventName
        status = $Status
        pid = if ($null -ne $RuntimeRecord) { Get-ManagedSourceStateProperty -Object $RuntimeRecord -Name 'pid' } else { $null }
        endpoint = if ($null -ne $RuntimeRecord) { Get-ManagedSourceStateProperty -Object $RuntimeRecord -Name 'endpoint' } else { $null }
        paste = if ($null -ne $RuntimeRecord) { Get-ManagedSourceStateProperty -Object (Get-ManagedSourceStateProperty -Object $RuntimeRecord -Name 'capabilities') -Name 'paste' } else { $null }
        send = if ($null -ne $RuntimeRecord) { Get-ManagedSourceStateProperty -Object (Get-ManagedSourceStateProperty -Object $RuntimeRecord -Name 'capabilities') -Name 'send' } else { $null }
        runtimeVersion = if ($null -ne $RuntimeRecord) { Get-ManagedSourceStateProperty -Object (Get-ManagedSourceStateProperty -Object $RuntimeRecord -Name 'capabilities') -Name 'version' } else { $null }
    }
    Add-Content -LiteralPath $logPath -Value (($payload | ConvertTo-Json -Compress)) -Encoding utf8
}
function Start-LoggedProcess([string]$FilePath, [string[]]$ArgumentList, [string]$WorkingDirectory, [string]$StdoutLogPath, [string]$StderrLogPath) {
    Ensure-Directory (Split-Path -Parent $StdoutLogPath)
    Ensure-Directory (Split-Path -Parent $StderrLogPath)
    $quote = { param([string]$Value) '"{0}"' -f $Value.Replace('"', '""') }
    $command = 'call {0} {1} 1>>{2} 2>>{3} <nul' -f `
        (& $quote $FilePath), `
        ((@($ArgumentList | ForEach-Object { & $quote $_ }) -join ' ')), `
        (& $quote $StdoutLogPath), `
        (& $quote $StderrLogPath)
    return Start-Process -FilePath $env:ComSpec -ArgumentList @('/d', '/s', '/c', $command) -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru
}
function Get-ProcessRecord([int]$ProcessId, [string]$Role) {
    $process = Get-Process -Id $ProcessId -ErrorAction Stop
    $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
    return [ordered]@{ role=$Role; pid=$ProcessId; startTicks=$process.StartTime.ToUniversalTime().Ticks; executable=[string]$cim.ExecutablePath; commandLine=[string]$cim.CommandLine }
}
function Test-ProcessRecord($Record) {
    if ($null -eq $Record) { return $false }
    foreach ($name in @('pid', 'startTicks', 'executable', 'commandLine')) {
        if (-not (Test-ManagedSourceStateProperty -Object $Record -Name $name)) { return $false }
    }

    $processId = 0
    $startTicks = [int64]0
    $pidValue = Get-ManagedSourceStateProperty -Object $Record -Name 'pid'
    $startTicksValue = Get-ManagedSourceStateProperty -Object $Record -Name 'startTicks'
    $executable = Get-ManagedSourceStateProperty -Object $Record -Name 'executable'
    $commandLine = Get-ManagedSourceStateProperty -Object $Record -Name 'commandLine'
    if ($null -eq $pidValue -or $null -eq $startTicksValue -or [string]::IsNullOrWhiteSpace([string]$executable) -or [string]::IsNullOrWhiteSpace([string]$commandLine)) { return $false }
    if (-not [int]::TryParse([string]$pidValue, [ref]$processId) -or $processId -le 0) { return $false }
    if (-not [int64]::TryParse([string]$startTicksValue, [ref]$startTicks) -or $startTicks -le 0) { return $false }

    try {
        $process = Get-Process -Id $processId -ErrorAction Stop
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction Stop
        if ($process.StartTime.ToUniversalTime().Ticks -ne $startTicks) { return $false }
        $marker = $script:RepoRoot.ToLowerInvariant()
        return ([string]$cim.CommandLine).ToLowerInvariant().Contains($marker)
    }
    catch { return $false }
}
function Get-ProcessRecordId($Record) {
    $processId = 0
    $pidValue = Get-ManagedSourceStateProperty -Object $Record -Name 'pid'
    if ($null -eq $pidValue -or -not [int]::TryParse([string]$pidValue, [ref]$processId) -or $processId -le 0) { return $null }
    return $processId
}
function Get-StatePort($State, [string]$Name) {
    $port = 0
    $value = Get-ManagedSourceStateProperty -Object $State -Name $Name
    if ($null -eq $value -or -not [int]::TryParse([string]$value, [ref]$port) -or $port -lt 1 -or $port -gt 65535) { return $null }
    return $port
}
function Test-CurrentRepoState($State) {
    $repoRoot = Get-ManagedSourceStateProperty -Object $State -Name 'repoRoot'
    if ($repoRoot -isnot [string] -or [string]::IsNullOrWhiteSpace($repoRoot)) { return $false }
    try {
        return [IO.Path]::GetFullPath($repoRoot).Equals($script:RepoRoot, [StringComparison]::OrdinalIgnoreCase)
    }
    catch { return $false }
}
function Test-ControlPath($Path) {
    if ($Path -isnot [string] -or -not [IO.Path]::IsPathRooted($Path)) { return $false }
    try {
        $root = [IO.Path]::GetFullPath($script:ControlRoot).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
        $candidate = [IO.Path]::GetFullPath($Path)
        return $candidate.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
    }
    catch { return $false }
}
function Stop-VerifiedProcess($Record) {
    if (-not (Test-ProcessRecord $Record)) { return $false }
    $processId = Get-ProcessRecordId $Record
    if ($null -eq $processId -or -not (Test-ProcessRecord $Record)) { return $false }
    # Terminate only a process that passed PID, start time, and repository command-line validation.
    & taskkill.exe /PID $processId /T /F | Out-Null
    return $true
}
function Get-PortOwner([int]$Port) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $listener) { return $null }
    return [int]$listener.OwningProcess
}
function Get-ListenerProcessRecord([int]$Port, [int]$ProcessId = 0) {
    $owner = if ($ProcessId -gt 0) { $ProcessId } else { Get-PortOwner $Port }
    if ($null -eq $owner -or $owner -le 0) { return $null }
    try {
        $record = Get-ProcessRecord $owner "listener-$Port"
        $record.port = $Port
        return $record
    }
    catch { return $null }
}
function Test-CurrentRepoListener($Record) {
    return Test-ProcessRecord $Record
}
function Assert-PortFree([int]$Port) {
    $owner = Get-PortOwner $Port
    if ($null -ne $owner) {
        $record = Get-ListenerProcessRecord -Port $Port -ProcessId $owner
        if ($null -ne $record) {
            throw "Port $Port is already listening (PID $owner, process $($record.executable), command $($record.commandLine)). Stop that process or choose another port."
        }
        throw "Port $Port is already listening (PID $owner). Stop that process or choose another port."
    }
}
function Invoke-JsonGet([string]$Url) { return Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 5 }
function Test-BackendHealthy {
    try {
        $health = Invoke-JsonGet "$script:BaseUrl/healthz"
        $runtime = Invoke-JsonGet "$script:BaseUrl/api/v1/system/runtime/status"
        $ready = Invoke-JsonGet "$script:BaseUrl/readyz"
        return $health.code -eq 0 -and $runtime.state -in @('CORE_READY', 'READY', 'DEGRADED') -and $ready.state -in @('CORE_READY', 'READY', 'DEGRADED')
    }
    catch { return $false }
}
function Test-WebHealthy {
    try { return (Invoke-WebRequest -Uri $script:WebUrl -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 }
    catch { return $false }
}
function Get-DesktopRuntimeStatus {
    try {
        $response = Invoke-JsonGet "$script:BaseUrl/api/v1/desktop-automation/runtime/status"
        $data = Get-ManagedSourceStateProperty -Object $response -Name 'data'
        if ($null -ne $data) { return $data }
        return $response
    }
    catch { return $null }
}
function Test-DesktopRuntimeHealthy($RuntimeStatus) {
    if ($null -eq $RuntimeStatus) { return $false }
    $runtimePhase = [string](Get-ManagedSourceStateProperty -Object $RuntimeStatus -Name 'status')
    $reachable = Get-ManagedSourceStateProperty -Object $RuntimeStatus -Name 'runtime_reachable'
    $inputAvailable = Get-ManagedSourceStateProperty -Object $RuntimeStatus -Name 'inputAvailable'
    $sendEnabled = Get-ManagedSourceStateProperty -Object $RuntimeStatus -Name 'send_enabled'
    $isReady = ($runtimePhase -eq 'ready')
    $hasReachability = ($reachable -eq $true)
    $hasInput = ($inputAvailable -eq $true)
    $hasSend = ($sendEnabled -eq $true)
    return ($isReady -and $hasReachability -and $hasInput -and $hasSend)
}
function Get-DesktopRuntimeProcessRecord($Status) {
    if (-not (Test-Path -LiteralPath $script:RuntimeExecutable -PathType Leaf)) { return $null }
    $process = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ExecutablePath -and
        [StringComparer]::OrdinalIgnoreCase.Equals([IO.Path]::GetFullPath([string]$_.ExecutablePath), $script:RuntimeExecutable) -and
        ([string]$_.CommandLine) -notmatch '\s--type='
    } | Select-Object -First 1
    if ($null -eq $process) { return $null }
    try {
        $record = Get-ProcessRecord ([int]$process.ProcessId) 'desktop-runtime'
        $record.repoRoot = $script:RepoRoot
        $record.logPath = Join-Path $script:LogsRoot 'desktop-runtime.stderr.log'
        $record.endpoint = "http://127.0.0.1:$([string](Get-ManagedSourceStateProperty -Object $Status -Name 'port'))"
        $record.status = [string](Get-ManagedSourceStateProperty -Object $Status -Name 'status')
        $record.capabilities = [ordered]@{
            paste = (Get-ManagedSourceStateProperty -Object $Status -Name 'inputAvailable') -eq $true
            send = (Get-ManagedSourceStateProperty -Object $Status -Name 'send_enabled') -eq $true
            version = Get-ManagedSourceStateProperty -Object $Status -Name 'runtimeVersion'
        }
        return $record
    }
    catch { return $null }
}
function Test-DesktopRuntimeRecord($Record) {
    if ($null -eq $Record) { return $false }
    foreach ($name in @('pid', 'startTicks', 'executable')) {
        if (-not (Test-ManagedSourceStateProperty -Object $Record -Name $name)) { return $false }
    }
    $processId = 0
    $startTicks = [int64]0
    $pidValue = Get-ManagedSourceStateProperty -Object $Record -Name 'pid'
    $startTicksValue = Get-ManagedSourceStateProperty -Object $Record -Name 'startTicks'
    $executable = [string](Get-ManagedSourceStateProperty -Object $Record -Name 'executable')
    if ($null -eq $pidValue -or $null -eq $startTicksValue -or [string]::IsNullOrWhiteSpace($executable)) { return $false }
    if (-not [int]::TryParse([string]$pidValue, [ref]$processId) -or $processId -le 0) { return $false }
    if (-not [int64]::TryParse([string]$startTicksValue, [ref]$startTicks) -or $startTicks -le 0) { return $false }
    try {
        $process = Get-Process -Id $processId -ErrorAction Stop
        if ($process.StartTime.ToUniversalTime().Ticks -ne $startTicks) { return $false }
        if (-not [StringComparer]::OrdinalIgnoreCase.Equals([IO.Path]::GetFullPath($executable), $script:RuntimeExecutable)) { return $false }
        $repoRoot = [string](Get-ManagedSourceStateProperty -Object $Record -Name 'repoRoot')
        if (-not [string]::IsNullOrWhiteSpace($repoRoot)) {
            if (-not [IO.Path]::GetFullPath($repoRoot).Equals($script:RepoRoot, [StringComparison]::OrdinalIgnoreCase)) { return $false }
        }
        return $true
    }
    catch { return $false }
}
function Wait-ForDesktopRuntime([int]$Timeout) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Timeout)
    $lastDetail = 'runtime status endpoint unavailable'
    while ([DateTime]::UtcNow -lt $deadline) {
        $status = Get-DesktopRuntimeStatus
        if (Test-DesktopRuntimeHealthy $status) {
            $record = Get-DesktopRuntimeProcessRecord $status
            if ($null -ne $record -and (Test-DesktopRuntimeRecord $record)) {
                return [ordered]@{ status=$status; record=$record }
            }
            $lastDetail = 'runtime reported ready but its owned process record was not found'
        }
        elseif ($null -ne $status) {
            $lastDetail = "status=$([string](Get-ManagedSourceStateProperty -Object $status -Name 'status')); errorCode=$([string](Get-ManagedSourceStateProperty -Object $status -Name 'errorCode'))"
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Desktop Runtime did not become ready with paste/send capabilities within $Timeout seconds: $lastDetail. Logs: $script:LogsRoot.$(Get-ConsoleSelectionModeHint)"
}
function Start-WebSourceProcess {
    $vite = Join-Path $script:RepoRoot 'web\node_modules\vite\bin\vite.js'
    $webEnvironment = @{ VITE_API_BASE_URL=$script:BaseUrl }
    $savedWeb = @{}
    foreach ($key in $webEnvironment.Keys) {
        $savedWeb[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        [Environment]::SetEnvironmentVariable($key, $webEnvironment[$key], 'Process')
    }
    try {
        $web = Start-LoggedProcess `
            -FilePath (Get-Command node.exe -ErrorAction Stop).Source `
            -ArgumentList @($vite, '--host', '127.0.0.1', '--port', $WebPort, '--strictPort') `
            -WorkingDirectory (Join-Path $script:RepoRoot 'web') `
            -StdoutLogPath (Join-Path $script:LogsRoot 'web.stdout.log') `
            -StderrLogPath (Join-Path $script:LogsRoot 'web.stderr.log')
    }
    finally { foreach ($key in $webEnvironment.Keys) { [Environment]::SetEnvironmentVariable($key, $savedWeb[$key], 'Process') } }
    Wait-ForWeb 45
    $webListenerPid = Get-PortOwner $WebPort
    if ($null -eq $webListenerPid) { throw "Web server reported ready but port $WebPort has no listener." }
    return Get-ProcessRecord $webListenerPid 'web'
}
function New-RecoveredSourceState($BackendRecord, $WebRecord, $RuntimeRecord) {
    return [ordered]@{
        schema=2; sessionId=[guid]::NewGuid().ToString('N'); repoRoot=$script:RepoRoot; userDataRoot=$script:UserDataRoot
        backendPort=$BackendPort; webPort=$WebPort; logsRoot=$script:LogsRoot; shutdownPath=$null
        backend=$BackendRecord; backendListener=$BackendRecord; web=$WebRecord; runtime=$RuntimeRecord
    }
}
function Wait-ForBackend([string]$Path, [int]$Timeout) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Timeout)
    $lastError = ''
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $health = Invoke-JsonGet "$script:BaseUrl/healthz"
            $runtime = Invoke-JsonGet "$script:BaseUrl/api/v1/system/runtime/status"
            $ready = Invoke-JsonGet "$script:BaseUrl/readyz"
            if ($health.code -eq 0 -and $runtime.state -in @('CORE_READY', 'READY', 'DEGRADED') -and $ready.state -in @('CORE_READY', 'READY', 'DEGRADED')) {
                return [ordered]@{ health=$health; runtime=$runtime; ready=$ready }
            }
            $lastError = "health=$($health.state); runtime=$($runtime.state); ready=$($ready.state)"
        }
        catch { $lastError = $_.Exception.Message }
        Start-Sleep -Milliseconds 500
    }
    throw "Backend did not reach health/runtime/ready within $Timeout seconds: $lastError. See $Path.$(Get-ConsoleSelectionModeHint)"
}
function Wait-ForWeb([int]$Timeout) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Timeout)
    while ([DateTime]::UtcNow -lt $deadline) {
        try { if ((Invoke-WebRequest -Uri $script:WebUrl -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) { return } } catch {}
        Start-Sleep -Milliseconds 500
    }
    throw "Web server did not become ready: $script:WebUrl.$(Get-ConsoleSelectionModeHint)"
}
function Start-Source {
    $existing = Read-ManagedSourceState $script:StatePath
    if ($existing -and -not (Test-CurrentRepoState $existing)) { throw 'Refusing to replace a managed source state owned by a different repository.' }
    Ensure-Directory $script:UserDataRoot; Ensure-Directory $script:LogsRoot; Ensure-Directory $script:ControlRoot; Ensure-Directory $script:RuntimeUserDataRoot
    $backendListener = Get-ListenerProcessRecord -Port $BackendPort
    $webListener = Get-ListenerProcessRecord -Port $WebPort
    $backendOwned = Test-CurrentRepoListener $backendListener
    $webOwned = Test-CurrentRepoListener $webListener
    if ($backendOwned -and (Test-BackendHealthy)) {
        if ($webOwned -and (Test-WebHealthy)) {
            $runtimeReady = Wait-ForDesktopRuntime $StartupTimeoutSeconds
            $recovered = New-RecoveredSourceState $backendListener $webListener $runtimeReady.record
            Write-ManagedSourceState $script:StatePath $recovered
            Write-DesktopRuntimeEvent -EventName 'runtime_recovered' -RuntimeRecord $runtimeReady.record -Status $runtimeReady.status.status
            $result = [ordered]@{ status='running'; url=$script:WebUrl; api=$script:BaseUrl; backendPid=$backendListener.pid; webPid=$webListener.pid; runtimePid=$runtimeReady.record.pid; backendPort=$BackendPort; webPort=$WebPort; logs=$script:LogsRoot; userData=$script:UserDataRoot; realSend='enabled'; runtimeState='recovered' }
            if (-not $NoBrowser) { Start-Process $script:WebUrl }
            return $result
        }
        if ($webOwned) { [void](Stop-VerifiedProcess $webListener) }
        Assert-PortFree $WebPort
        $recoveredWeb = Start-WebSourceProcess
        $runtimeReady = Wait-ForDesktopRuntime $StartupTimeoutSeconds
        $recovered = New-RecoveredSourceState $backendListener $recoveredWeb $runtimeReady.record
        Write-ManagedSourceState $script:StatePath $recovered
        Write-DesktopRuntimeEvent -EventName 'runtime_recovered' -RuntimeRecord $runtimeReady.record -Status $runtimeReady.status.status
        $result = [ordered]@{ status='running'; url=$script:WebUrl; api=$script:BaseUrl; backendPid=$backendListener.pid; webPid=$recoveredWeb.pid; runtimePid=$runtimeReady.record.pid; backendPort=$BackendPort; webPort=$WebPort; logs=$script:LogsRoot; userData=$script:UserDataRoot; realSend='enabled'; runtimeState='recovered' }
        if (-not $NoBrowser) { Start-Process $script:WebUrl }
        return $result
    }
    foreach ($record in @($backendListener, $webListener)) {
        if ($null -ne $record -and (Test-CurrentRepoListener $record)) { [void](Stop-VerifiedProcess $record) }
    }
    Assert-PortFree $BackendPort; Assert-PortFree $WebPort
    $python = Join-Path $script:RepoRoot '.venv\Scripts\python.exe'
    $vite = Join-Path $script:RepoRoot 'web\node_modules\vite\bin\vite.js'
    foreach ($path in @($python, $vite, $script:RuntimeExecutable, (Join-Path $script:RepoRoot 'vendor\wechat_decrypt\mcp_wxwork_http_server.py'))) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Source setup is incomplete: $path. Run .\scripts\setup-source.ps1." }
    }
    $sessionId = [guid]::NewGuid().ToString('N')
    $shutdownPath = Join-Path $script:ControlRoot "source-$sessionId.shutdown.json"
    $environment = @{ PYTHONPATH=(Join-Path $script:RepoRoot 'src'); CHATBOT_USER_DATA_ROOT=$script:UserDataRoot; LANGBOT_DATA_ROOT=$script:UserDataRoot; API__PORT=[string]$BackendPort; API__WEBHOOK_PREFIX=$script:BaseUrl; DESKTOP_AUTOMATION__ENABLED='true'; LANGBOT_RPA_LOG_DIR=$script:LogsRoot; LANGBOT_RPA_USER_DATA_DIR=$script:RuntimeUserDataRoot; LANGBOT_RPA_FORCE_DISABLE_SEND='0'; LANGBOT_RPA_ALLOW_AUTO_SEND='1'; LANGBOT_BROADCAST_SEND_ENABLED='1'; LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS='*'; LANGBOT_LOCAL_STACK_SESSION_ID=$sessionId; LANGBOT_LOCAL_SHUTDOWN_REQUEST_PATH=$shutdownPath }
    $saved = @{}; foreach ($key in $environment.Keys) { $saved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process'); [Environment]::SetEnvironmentVariable($key, $environment[$key], 'Process') }
    try {
        $backend = Start-LoggedProcess `
            -FilePath $python `
            -ArgumentList @((Join-Path $script:RepoRoot 'main.py')) `
            -WorkingDirectory $script:UserDataRoot `
            -StdoutLogPath (Join-Path $script:LogsRoot 'backend.stdout.log') `
            -StderrLogPath (Join-Path $script:LogsRoot 'backend.stderr.log')
    }
    finally { foreach ($key in $environment.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key], 'Process') } }
    Set-Content -LiteralPath (Join-Path $script:LogsRoot 'desktop-runtime.stdout.log') -Value 'runtime launch managed by backend' -Encoding utf8
    if (-not (Test-Path -LiteralPath (Join-Path $script:LogsRoot 'desktop-runtime.stderr.log'))) { New-Item -ItemType File -Path (Join-Path $script:LogsRoot 'desktop-runtime.stderr.log') -Force | Out-Null }
    $state = [ordered]@{ schema=2; sessionId=$sessionId; repoRoot=$script:RepoRoot; userDataRoot=$script:UserDataRoot; backendPort=$BackendPort; webPort=$WebPort; logsRoot=$script:LogsRoot; shutdownPath=$shutdownPath; backend=(Get-ProcessRecord $backend.Id 'backend'); backendListener=$null; web=$null; runtime=$null }
    Write-ManagedSourceState $script:StatePath $state
    try {
        $readiness = Wait-ForBackend (Join-Path $script:LogsRoot 'backend.stderr.log') $StartupTimeoutSeconds
        $backendListenerPid = Get-PortOwner $BackendPort
        if ($null -eq $backendListenerPid) { throw "Backend health succeeded but port $BackendPort has no listener." }
        $state.backend = Get-ProcessRecord $backendListenerPid 'backend'
        $state.backendListener = Get-ProcessRecord $backendListenerPid 'backend-listener'
        Write-ManagedSourceState $script:StatePath $state
        $state.web = Start-WebSourceProcess; Write-ManagedSourceState $script:StatePath $state
        $runtimeReady = Wait-ForDesktopRuntime $StartupTimeoutSeconds
        $state.runtime = $runtimeReady.record; Write-ManagedSourceState $script:StatePath $state
        Write-DesktopRuntimeEvent -EventName 'runtime_ready' -RuntimeRecord $runtimeReady.record -Status $runtimeReady.status.status
        $result = [ordered]@{ status='running'; url=$script:WebUrl; api=$script:BaseUrl; backendPid=(Get-ProcessRecordId (Get-ManagedSourceStateProperty -Object $state -Name 'backend')); webPid=(Get-ProcessRecordId (Get-ManagedSourceStateProperty -Object $state -Name 'web')); runtimePid=$runtimeReady.record.pid; backendPort=$BackendPort; webPort=$WebPort; logs=$script:LogsRoot; userData=$script:UserDataRoot; realSend='enabled'; runtimeState=$runtimeReady.status.status }
        if (-not $NoBrowser) { Start-Process $script:WebUrl }
        return $result
    }
    catch { Stop-Source | Out-Null; throw }
}
function Stop-Source {
    $state = Read-ManagedSourceState $script:StatePath
    if ($null -eq $state) { return [ordered]@{ status='stopped'; detail='no-managed-source-state' } }
    if (-not (Test-CurrentRepoState $state)) { throw 'Refusing to stop a source stack owned by a different repository.' }
    $backend = Get-ManagedSourceStateProperty -Object $state -Name 'backend'
    $web = Get-ManagedSourceStateProperty -Object $state -Name 'web'
    $runtime = Get-ManagedSourceStateProperty -Object $state -Name 'runtime'
    $backendListener = Get-ManagedSourceStateProperty -Object $state -Name 'backendListener'
    $shutdownPath = Get-ManagedSourceStateProperty -Object $state -Name 'shutdownPath'
    $sessionId = Get-ManagedSourceStateProperty -Object $state -Name 'sessionId'
    if ((Test-ControlPath $shutdownPath) -and (Test-ProcessRecord $backend)) { Write-ManagedSourceState $shutdownPath ([ordered]@{ sessionId=$sessionId; action='shutdown'; reason='source-stop'; requestedAt=[DateTime]::UtcNow.ToString('o') }); Start-Sleep -Seconds 2 }
    # Backend shutdown closes task admission and asks its owned runtime to exit.
    # The explicit runtime fallback is limited to the exact packaged executable.
    if (Test-DesktopRuntimeRecord $runtime) { [void](Stop-VerifiedProcess $runtime) }
    foreach ($record in @($web, $backend, $backendListener)) { [void](Stop-VerifiedProcess $record) }
    $backendPort = Get-StatePort $state 'backendPort'
    $webPort = Get-StatePort $state 'webPort'
    Remove-Item -LiteralPath $script:StatePath -Force -ErrorAction SilentlyContinue
    if (Test-ControlPath $shutdownPath) { Remove-Item -LiteralPath $shutdownPath -Force -ErrorAction SilentlyContinue }
    return [ordered]@{ status='stopped'; backendPort=$backendPort; webPort=$webPort }
}
function Get-SourceStatus {
    $state = Read-ManagedSourceState $script:StatePath -Quiet
    if ($null -eq $state) { return [ordered]@{ status='stopped'; detail='no-managed-source-state'; backendPid=$null; webPid=$null; runtimePid=$null; userData=$script:UserDataRoot } }
    if (-not (Test-CurrentRepoState $state)) { return [ordered]@{ status='stopped'; detail='foreign-managed-source-state'; backendPid=$null; webPid=$null; runtimePid=$null; userData=$script:UserDataRoot } }
    $backend = Get-ManagedSourceStateProperty -Object $state -Name 'backend'
    $web = Get-ManagedSourceStateProperty -Object $state -Name 'web'
    $runtime = Get-ManagedSourceStateProperty -Object $state -Name 'runtime'
    $backendValid = Test-ProcessRecord $backend
    $webValid = Test-ProcessRecord $web
    $runtimeValid = Test-DesktopRuntimeRecord $runtime
    $backendPid = if ($backendValid) { Get-ProcessRecordId $backend } else { $null }
    $webPid = if ($webValid) { Get-ProcessRecordId $web } else { $null }
    $runtimePid = if ($runtimeValid) { Get-ProcessRecordId $runtime } else { $null }
    $detail = if ($backendValid -and $webValid -and $runtimeValid) { 'running' } elseif ($backendValid -or $webValid -or $runtimeValid) { 'partial-managed-source-state' } else { 'stale-managed-source-state' }
    $status = if ($backendValid -and $webValid -and $runtimeValid) { 'running' } elseif ($backendValid -or $webValid -or $runtimeValid) { 'degraded' } else { 'stopped' }
    return [ordered]@{ status=$status; detail=$detail; backendPid=$backendPid; webPid=$webPid; runtimePid=$runtimePid; backendPort=(Get-StatePort $state 'backendPort'); webPort=(Get-StatePort $state 'webPort'); logs=(Get-ManagedSourceStateProperty -Object $state -Name 'logsRoot'); userData=(Get-ManagedSourceStateProperty -Object $state -Name 'userDataRoot') }
}

try {
    $result = switch ($Action) { 'Start' { Start-Source }; 'Stop' { Stop-Source }; 'Status' { Get-SourceStatus } }
    $result | ConvertTo-Json -Depth 8
}
catch {
    Write-Error $_
    throw
}
