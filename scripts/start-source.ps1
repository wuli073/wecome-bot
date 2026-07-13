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

function Ensure-Directory([string]$Path) { New-Item -ItemType Directory -Force -Path $Path | Out-Null }
function Write-Json([string]$Path, $Value) {
    Ensure-Directory (Split-Path -Parent $Path)
    $temporary = "$Path.tmp"
    [IO.File]::WriteAllText($temporary, ($Value | ConvertTo-Json -Depth 8), (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}
function Read-Json([string]$Path) { if (Test-Path -LiteralPath $Path) { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }; return $null }
function Get-ProcessRecord([int]$ProcessId, [string]$Role) {
    $process = Get-Process -Id $ProcessId -ErrorAction Stop
    $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
    return [ordered]@{ role=$Role; pid=$ProcessId; startTicks=$process.StartTime.ToUniversalTime().Ticks; executable=[string]$cim.ExecutablePath; commandLine=[string]$cim.CommandLine }
}
function Test-ProcessRecord($Record) {
    if ($null -eq $Record -or -not $Record.pid) { return $false }
    try {
        $process = Get-Process -Id ([int]$Record.pid) -ErrorAction Stop
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $($Record.pid)" -ErrorAction Stop
        if ($process.StartTime.ToUniversalTime().Ticks -ne [int64]$Record.startTicks) { return $false }
        $marker = $script:RepoRoot.ToLowerInvariant()
        return ([string]$cim.CommandLine).ToLowerInvariant().Contains($marker)
    }
    catch { return $false }
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
    $existing = Read-Json $script:StatePath
    if ($existing -and (Test-ProcessRecord $existing.backend)) { throw "A managed source stack is already running (backend PID $($existing.backend.pid)). Use stop-source.ps1 first." }
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
        $backend = Start-Process -FilePath $python -ArgumentList @((Join-Path $script:RepoRoot 'main.py')) -WorkingDirectory $script:UserDataRoot -RedirectStandardOutput (Join-Path $script:LogsRoot 'backend.stdout.log') -RedirectStandardError (Join-Path $script:LogsRoot 'backend.stderr.log') -WindowStyle Hidden -PassThru
    }
    finally { foreach ($key in $environment.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key], 'Process') } }
    $state = [ordered]@{ schema=1; sessionId=$sessionId; repoRoot=$script:RepoRoot; userDataRoot=$script:UserDataRoot; backendPort=$BackendPort; webPort=$WebPort; logsRoot=$script:LogsRoot; shutdownPath=$shutdownPath; backend=(Get-ProcessRecord $backend.Id 'backend'); backendListener=$null; web=$null }
    Write-Json $script:StatePath $state
    try {
        $readiness = Wait-ForBackend (Join-Path $script:LogsRoot 'backend.stderr.log') $StartupTimeoutSeconds
        $backendListenerPid = Get-PortOwner $BackendPort
        if ($null -eq $backendListenerPid) { throw "Backend health succeeded but port $BackendPort has no listener." }
        $state.backendListener = Get-ProcessRecord $backendListenerPid 'backend-listener'
        Write-Json $script:StatePath $state
        $webEnvironment = @{ VITE_API_BASE_URL=$script:BaseUrl }
        $savedWeb = @{}; foreach ($key in $webEnvironment.Keys) { $savedWeb[$key] = [Environment]::GetEnvironmentVariable($key, 'Process'); [Environment]::SetEnvironmentVariable($key, $webEnvironment[$key], 'Process') }
        try { $web = Start-Process -FilePath (Get-Command node.exe -ErrorAction Stop).Source -ArgumentList @($vite, '--host', '127.0.0.1', '--port', $WebPort, '--strictPort') -WorkingDirectory (Join-Path $script:RepoRoot 'web') -RedirectStandardOutput (Join-Path $script:LogsRoot 'web.stdout.log') -RedirectStandardError (Join-Path $script:LogsRoot 'web.stderr.log') -WindowStyle Hidden -PassThru }
        finally { foreach ($key in $webEnvironment.Keys) { [Environment]::SetEnvironmentVariable($key, $savedWeb[$key], 'Process') } }
        $state.web = Get-ProcessRecord $web.Id 'web'; Write-Json $script:StatePath $state; Wait-ForWeb 45
        $result = [ordered]@{ status='running'; url=$script:WebUrl; api=$script:BaseUrl; backendPid=$state.backend.pid; webPid=$state.web.pid; backendPort=$BackendPort; webPort=$WebPort; logs=$script:LogsRoot; userData=$script:UserDataRoot; realSend='disabled'; runtimeState=$readiness.runtime.state }
        if (-not $NoBrowser) { Start-Process $script:WebUrl }
        return $result
    }
    catch { Stop-Source | Out-Null; throw }
}
function Stop-Source {
    $state = Read-Json $script:StatePath
    if ($null -eq $state) { return [ordered]@{ status='stopped'; detail='no-managed-source-state' } }
    if ($state.repoRoot -ne $script:RepoRoot) { throw 'Refusing to stop a source stack owned by a different repository.' }
    if ($state.shutdownPath -and (Test-ProcessRecord $state.backend)) { Write-Json $state.shutdownPath ([ordered]@{ sessionId=$state.sessionId; action='shutdown'; reason='source-stop'; requestedAt=[DateTime]::UtcNow.ToString('o') }); Start-Sleep -Seconds 2 }
    foreach ($record in @($state.web, $state.backend)) {
        if (Test-ProcessRecord $record) {
            # The backend can fork a Hypercorn child. Terminate only this
            # verified root and its descendants, never processes by image name.
            & taskkill.exe /PID ([int]$record.pid) /T /F | Out-Null
        }
    }
    if (Test-ProcessRecord $state.backendListener) {
        & taskkill.exe /PID ([int]$state.backendListener.pid) /T /F | Out-Null
    }
    foreach ($port in @([int]$state.backendPort, [int]$state.webPort)) { $deadline=[DateTime]::UtcNow.AddSeconds(15); while ((Get-PortOwner $port) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 250 }; if (Get-PortOwner $port) { throw "Managed source stack did not release port $port." } }
    Remove-Item -LiteralPath $script:StatePath -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $state.shutdownPath -Force -ErrorAction SilentlyContinue
    return [ordered]@{ status='stopped'; backendPort=$state.backendPort; webPort=$state.webPort }
}
function Get-SourceStatus {
    $state = Read-Json $script:StatePath
    if ($null -eq $state) { return [ordered]@{ status='stopped'; userData=$script:UserDataRoot } }
    return [ordered]@{ status=if ((Test-ProcessRecord $state.backend) -and (Test-ProcessRecord $state.web)) {'running'} else {'degraded'}; backendPid=$state.backend.pid; webPid=$state.web.pid; backendPort=$state.backendPort; webPort=$state.webPort; logs=$state.logsRoot; userData=$state.userDataRoot }
}

try {
    $result = switch ($Action) { 'Start' { Start-Source }; 'Stop' { Stop-Source }; 'Status' { Get-SourceStatus } }
    $result | ConvertTo-Json -Depth 8
}
catch {
    Write-Error $_
    throw
}
