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

$script:RepoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $UserDataRoot) { $UserDataRoot = Join-Path $script:RepoRoot '.tmp\source-runtime\user-data' }
$script:UserDataRoot = [IO.Path]::GetFullPath($UserDataRoot)
$script:StatePath = Join-Path $script:UserDataRoot 'runtime\source-stack-state.json'
$script:LogsRoot = Join-Path $script:UserDataRoot 'logs\source'
$script:ControlRoot = Join-Path $script:RepoRoot '.tmp\local-stack\control'
$script:BaseUrl = "http://127.0.0.1:$BackendPort"
$script:WebUrl = "http://127.0.0.1:$WebPort"
. (Join-Path $PSScriptRoot 'source-state.ps1')

function Ensure-Directory([string]$Path) { New-Item -ItemType Directory -Force -Path $Path | Out-Null }
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
function Assert-PortFree([int]$Port) {
    $owner = Get-PortOwner $Port
    if ($null -ne $owner) { throw "Port $Port is already listening (PID $owner). Stop that process or choose another port." }
}
function Invoke-JsonGet([string]$Url) { return Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 5 }
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
    throw "Backend did not reach health/runtime/ready within $Timeout seconds: $lastError. See $Path"
}
function Wait-ForWeb([int]$Timeout) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Timeout)
    while ([DateTime]::UtcNow -lt $deadline) {
        try { if ((Invoke-WebRequest -Uri $script:WebUrl -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) { return } } catch {}
        Start-Sleep -Milliseconds 500
    }
    throw "Web server did not become ready: $script:WebUrl"
}
function Start-Source {
    $existing = Read-ManagedSourceState $script:StatePath
    if ($existing -and -not (Test-CurrentRepoState $existing)) { throw 'Refusing to replace a managed source state owned by a different repository.' }
    $existingRecords = @()
    if ($existing) {
        foreach ($recordName in @('backend', 'web', 'backendListener')) {
            $record = Get-ManagedSourceStateProperty -Object $existing -Name $recordName
            if (Test-ProcessRecord $record) { $existingRecords += $record }
        }
    }
    if ($existingRecords.Count -gt 0) {
        $pids = @($existingRecords | ForEach-Object { Get-ProcessRecordId $_ }) -join ', '
        throw "A managed source stack is already running (PID $pids). Use stop-source.ps1 first."
    }
    Assert-PortFree $BackendPort; Assert-PortFree $WebPort
    $python = Join-Path $script:RepoRoot '.venv\Scripts\python.exe'
    $vite = Join-Path $script:RepoRoot 'web\node_modules\vite\bin\vite.js'
    foreach ($path in @($python, $vite, (Join-Path $script:RepoRoot 'vendor\wechat_decrypt\mcp_wxwork_http_server.py'))) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Source setup is incomplete: $path. Run .\scripts\setup-source.ps1." }
    }
    Ensure-Directory $script:UserDataRoot; Ensure-Directory $script:LogsRoot; Ensure-Directory $script:ControlRoot
    $sessionId = [guid]::NewGuid().ToString('N')
    $shutdownPath = Join-Path $script:ControlRoot "source-$sessionId.shutdown.json"
    $environment = @{ PYTHONPATH=(Join-Path $script:RepoRoot 'src'); CHATBOT_USER_DATA_ROOT=$script:UserDataRoot; LANGBOT_DATA_ROOT=$script:UserDataRoot; API__PORT=[string]$BackendPort; API__WEBHOOK_PREFIX=$script:BaseUrl; LANGBOT_RPA_FORCE_DISABLE_SEND='1'; LANGBOT_RPA_ALLOW_AUTO_SEND='0'; LANGBOT_BROADCAST_SEND_ENABLED='0'; LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS=''; LANGBOT_LOCAL_STACK_SESSION_ID=$sessionId; LANGBOT_LOCAL_SHUTDOWN_REQUEST_PATH=$shutdownPath }
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
    $state = [ordered]@{ schema=1; sessionId=$sessionId; repoRoot=$script:RepoRoot; userDataRoot=$script:UserDataRoot; backendPort=$BackendPort; webPort=$WebPort; logsRoot=$script:LogsRoot; shutdownPath=$shutdownPath; backend=(Get-ProcessRecord $backend.Id 'backend'); backendListener=$null; web=$null }
    Write-ManagedSourceState $script:StatePath $state
    try {
        $readiness = Wait-ForBackend (Join-Path $script:LogsRoot 'backend.stderr.log') $StartupTimeoutSeconds
        $backendListenerPid = Get-PortOwner $BackendPort
        if ($null -eq $backendListenerPid) { throw "Backend health succeeded but port $BackendPort has no listener." }
        $state.backendListener = Get-ProcessRecord $backendListenerPid 'backend-listener'
        Write-ManagedSourceState $script:StatePath $state
        $webEnvironment = @{ VITE_API_BASE_URL=$script:BaseUrl }
        $savedWeb = @{}; foreach ($key in $webEnvironment.Keys) { $savedWeb[$key] = [Environment]::GetEnvironmentVariable($key, 'Process'); [Environment]::SetEnvironmentVariable($key, $webEnvironment[$key], 'Process') }
        try {
            $web = Start-LoggedProcess `
                -FilePath (Get-Command node.exe -ErrorAction Stop).Source `
                -ArgumentList @($vite, '--host', '127.0.0.1', '--port', $WebPort, '--strictPort') `
                -WorkingDirectory (Join-Path $script:RepoRoot 'web') `
                -StdoutLogPath (Join-Path $script:LogsRoot 'web.stdout.log') `
                -StderrLogPath (Join-Path $script:LogsRoot 'web.stderr.log')
        }
        finally { foreach ($key in $webEnvironment.Keys) { [Environment]::SetEnvironmentVariable($key, $savedWeb[$key], 'Process') } }
        $state.web = Get-ProcessRecord $web.Id 'web'; Write-ManagedSourceState $script:StatePath $state; Wait-ForWeb 45
        $result = [ordered]@{ status='running'; url=$script:WebUrl; api=$script:BaseUrl; backendPid=(Get-ProcessRecordId (Get-ManagedSourceStateProperty -Object $state -Name 'backend')); webPid=(Get-ProcessRecordId (Get-ManagedSourceStateProperty -Object $state -Name 'web')); backendPort=$BackendPort; webPort=$WebPort; logs=$script:LogsRoot; userData=$script:UserDataRoot; realSend='disabled'; runtimeState=$readiness.runtime.state }
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
    $backendListener = Get-ManagedSourceStateProperty -Object $state -Name 'backendListener'
    $shutdownPath = Get-ManagedSourceStateProperty -Object $state -Name 'shutdownPath'
    $sessionId = Get-ManagedSourceStateProperty -Object $state -Name 'sessionId'
    if ((Test-ControlPath $shutdownPath) -and (Test-ProcessRecord $backend)) { Write-ManagedSourceState $shutdownPath ([ordered]@{ sessionId=$sessionId; action='shutdown'; reason='source-stop'; requestedAt=[DateTime]::UtcNow.ToString('o') }); Start-Sleep -Seconds 2 }
    foreach ($record in @($web, $backend, $backendListener)) { [void](Stop-VerifiedProcess $record) }
    $backendPort = Get-StatePort $state 'backendPort'
    $webPort = Get-StatePort $state 'webPort'
    Remove-Item -LiteralPath $script:StatePath -Force -ErrorAction SilentlyContinue
    if (Test-ControlPath $shutdownPath) { Remove-Item -LiteralPath $shutdownPath -Force -ErrorAction SilentlyContinue }
    return [ordered]@{ status='stopped'; backendPort=$backendPort; webPort=$webPort }
}
function Get-SourceStatus {
    $state = Read-ManagedSourceState $script:StatePath -Quiet
    if ($null -eq $state) { return [ordered]@{ status='stopped'; detail='no-managed-source-state'; backendPid=$null; webPid=$null; userData=$script:UserDataRoot } }
    if (-not (Test-CurrentRepoState $state)) { return [ordered]@{ status='stopped'; detail='foreign-managed-source-state'; backendPid=$null; webPid=$null; userData=$script:UserDataRoot } }
    $backend = Get-ManagedSourceStateProperty -Object $state -Name 'backend'
    $web = Get-ManagedSourceStateProperty -Object $state -Name 'web'
    $backendValid = Test-ProcessRecord $backend
    $webValid = Test-ProcessRecord $web
    $backendPid = if ($backendValid) { Get-ProcessRecordId $backend } else { $null }
    $webPid = if ($webValid) { Get-ProcessRecordId $web } else { $null }
    $detail = if ($backendValid -and $webValid) { 'running' } elseif ($backendValid -or $webValid) { 'partial-managed-source-state' } elseif ($null -eq $backend -and $null -eq $web) { 'partial-managed-source-state' } else { 'stale-managed-source-state' }
    $status = if ($backendValid -and $webValid) { 'running' } elseif ($backendValid -or $webValid) { 'degraded' } else { 'stopped' }
    return [ordered]@{ status=$status; detail=$detail; backendPid=$backendPid; webPid=$webPid; backendPort=(Get-StatePort $state 'backendPort'); webPort=(Get-StatePort $state 'webPort'); logs=(Get-ManagedSourceStateProperty -Object $state -Name 'logsRoot'); userData=(Get-ManagedSourceStateProperty -Object $state -Name 'userDataRoot') }
}

try {
    $result = switch ($Action) { 'Start' { Start-Source }; 'Stop' { Stop-Source }; 'Status' { Get-SourceStatus } }
    $result | ConvertTo-Json -Depth 8
}
catch {
    Write-Error $_
    throw
}
