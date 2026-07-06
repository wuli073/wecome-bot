[CmdletBinding()]
param(
    [ValidateSet('Start', 'Stop', 'Restart', 'Status')]
    [string]$Action = 'Start',

    [ValidateSet('Bundled', 'Dev')]
    [string]$WebMode = 'Bundled',

    [int]$BackendHealthTimeoutSeconds = 120,
    [int]$WebHealthTimeoutSeconds = 60,

    [switch]$DryRun,
    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$script:StackRoot = Join-Path $script:RepoRoot '.tmp\local-stack'
$script:ControlDir = Join-Path $script:StackRoot 'control'
$script:LogsDir = Join-Path $script:StackRoot 'logs'
$script:StatePath = Join-Path $script:StackRoot 'state.json'
$script:ShutdownRequestPath = Join-Path $script:ControlDir 'shutdown.request.json'
$script:Action = $Action
$script:WebMode = $WebMode
$script:DryRun = [bool]$DryRun
$script:DefaultHealthPollIntervalMilliseconds = 500
$script:BackendHealthTimeoutSeconds = $BackendHealthTimeoutSeconds
$script:WebHealthTimeoutSeconds = $WebHealthTimeoutSeconds

function Get-LauncherMutexName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,

        [string]$Action = ''
    )

    $normalized = [System.IO.Path]::GetFullPath($RepoRoot).TrimEnd('\').ToLowerInvariant()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($normalized)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = ($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) -join ''
    }
    finally {
        $sha.Dispose()
    }

    return "Local\LangBot-Launcher-$($hash.Substring(0, 24))"
}

function Acquire-LauncherMutex {
    param(
        [Parameter(Mandatory = $true)]
        [string]$MutexName,

        [int]$TimeoutMs = 15000
    )

    $mutex = New-Object System.Threading.Mutex($false, $MutexName)
    $locked = $false
    try {
        try {
            $locked = $mutex.WaitOne($TimeoutMs)
        }
        catch [System.Threading.AbandonedMutexException] {
            $locked = $true
        }

        if (-not $locked) {
            throw 'Another launcher operation is already in progress.'
        }

        return $mutex
    }
    catch {
        if ($mutex -ne $null) {
            $mutex.Dispose()
        }
        throw
    }
}

function Release-LauncherMutex {
    param([System.Threading.Mutex]$Mutex)

    if ($null -eq $Mutex) {
        return
    }

    try {
        $Mutex.ReleaseMutex() | Out-Null
    }
    catch {
    }
    finally {
        $Mutex.Dispose()
    }
}

function Ensure-Directory {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Write-JsonAtomically {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [object]$Data
    )

    $directory = Split-Path -Parent $Path
    if ($directory) {
        Ensure-Directory -Path $directory
    }

    $tmp = "$Path.tmp"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)

    try {
        [System.IO.File]::WriteAllText($tmp, ($Data | ConvertTo-Json -Depth 8), $utf8NoBom)
        if (Test-Path -LiteralPath $Path) {
            $backup = "$Path.bak"
            [System.IO.File]::Replace($tmp, $Path, $backup, $true)
            if (Test-Path -LiteralPath $backup) {
                Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
            }
        }
        else {
            [System.IO.File]::Move($tmp, $Path)
        }
    }
    finally {
        if (Test-Path -LiteralPath $tmp) {
            Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
        }
    }
}

function Read-JsonFile {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
}

function Remove-LauncherState {
    if (Test-Path -LiteralPath $script:StatePath) {
        Remove-Item -LiteralPath $script:StatePath -Force -ErrorAction SilentlyContinue
    }
}

function Remove-StaleShutdownRequest {
    param([string]$Path = $script:ShutdownRequestPath)

    if (-not $Path) {
        return
    }

    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    }
}

function Assert-BundledFrontendReady {
    param([string]$RepoRoot = $script:RepoRoot)

    $indexPath = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot 'web\\dist\\index.html'))
    if (-not (Test-Path -LiteralPath $indexPath)) {
        throw "Bundled frontend entry is missing: $indexPath"
    }
    return $indexPath
}

function Resolve-ApiConfiguration {
    param([string]$RepoRoot = $script:RepoRoot)

    $configPath = Join-Path $RepoRoot 'data\config.yaml'
    $port = 5300
    $apiHost = '127.0.0.1'
    $baseUrl = $null

    if (Test-Path -LiteralPath $configPath) {
        $lines = Get-Content -LiteralPath $configPath
        $inApi = $false
        foreach ($line in $lines) {
            if ($line -match '^api:\s*$') {
                $inApi = $true
                continue
            }

            if ($inApi -and $line -match '^\S') {
                break
            }

            if (-not $inApi) {
                continue
            }

            if ($line -match '^\s+port:\s*(\d+)\s*$') {
                $port = [int]$matches[1]
                continue
            }

            if ($line -match '^\s+webhook_prefix:\s*(.+?)\s*$') {
                $candidate = $matches[1].Trim().Trim("'`"")
                if ($candidate) {
                    try {
                        $uri = [System.Uri]$candidate
                        $baseUrl = $uri.GetLeftPart([System.UriPartial]::Authority)
                        $apiHost = $uri.Host
                        if ($uri.Port -gt 0) {
                            $port = $uri.Port
                        }
                    }
                    catch {
                    }
                }
            }
        }
    }

    if (-not $baseUrl) {
        $baseUrl = "http://$apiHost`:$port"
    }

    [pscustomobject]@{
        Host = $apiHost
        Port = $port
        BaseUrl = $baseUrl
        HealthUrl = "$baseUrl/healthz"
        ConfigPath = $configPath
    }
}

function Test-TcpPortListening {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Address,

        [Parameter(Mandatory = $true)]
        [int]$Port,

        [int]$TimeoutMs = 500
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $asyncResult = $client.BeginConnect($Address, $Port, $null, $null)
        if (-not $asyncResult.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            return $false
        }

        $client.EndConnect($asyncResult)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Get-ListeningProcessId {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $connections = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if ($null -eq $connections) {
        return $null
    }

    $first = $connections | Select-Object -First 1
    if ($null -eq $first) {
        return $null
    }

    return [int]$first.OwningProcess
}

function Resolve-ListenerOwnedSnapshot {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,

        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,

        [string]$ExpectedCommandFragment = ''
    )

    $ownerPid = Get-ListeningProcessId -Port $Port
    if (-not $ownerPid) {
        return $null
    }

    $snapshot = Get-ProcessIdentitySnapshot -ProcessId $ownerPid
    if ($null -eq $snapshot) {
        return $null
    }

    $repoLower = [System.IO.Path]::GetFullPath($RepoRoot).TrimEnd('\').ToLowerInvariant()
    $commandLine = [string]$snapshot.commandLine
    $executablePath = [string]$snapshot.executablePath
    $commandLower = $commandLine.ToLowerInvariant()
    $exeLower = $executablePath.ToLowerInvariant()

    if (-not ($commandLower.Contains($repoLower) -or $exeLower.Contains($repoLower))) {
        return $null
    }

    if ($ExpectedCommandFragment) {
        $fragmentLower = $ExpectedCommandFragment.ToLowerInvariant()
        if (-not ($commandLower.Contains($fragmentLower) -or $exeLower.Contains($fragmentLower))) {
            return $null
        }
    }

    return $snapshot
}

function Get-ProcessStartTimeUtcTicks {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    return [System.Diagnostics.Process]::GetProcessById($ProcessId).StartTime.ToUniversalTime().Ticks
}

function Get-ProcessIdentitySnapshot {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    try {
        $process = [System.Diagnostics.Process]::GetProcessById($ProcessId)
    }
    catch {
        return $null
    }

    $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $cim) {
        return [pscustomobject]@{
            pid = $ProcessId
            processStartTimeUtcTicks = $process.StartTime.ToUniversalTime().Ticks
            executablePath = $null
            commandLine = $null
            repoRoot = $null
        }
    }

    [pscustomobject]@{
        pid = $ProcessId
        processStartTimeUtcTicks = $process.StartTime.ToUniversalTime().Ticks
        executablePath = $cim.ExecutablePath
        commandLine = $cim.CommandLine
        repoRoot = $null
    }
}

function Resolve-RepoProcessRootSnapshot {
    param(
        [Parameter(Mandatory = $true)]
        $Snapshot,

        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    if ($null -eq $Snapshot) {
        return $null
    }

    $repoLower = [System.IO.Path]::GetFullPath($RepoRoot).TrimEnd('\').ToLowerInvariant()
    $current = $Snapshot

    while ($true) {
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $($current.pid)" -ErrorAction SilentlyContinue
        if ($null -eq $cim -or -not $cim.ParentProcessId -or [int]$cim.ParentProcessId -le 0) {
            return $current
        }

        $parentSnapshot = Get-ProcessIdentitySnapshot -ProcessId ([int]$cim.ParentProcessId)
        if ($null -eq $parentSnapshot) {
            return $current
        }

        $parentCommand = [string]$parentSnapshot.commandLine
        $parentExe = [string]$parentSnapshot.executablePath
        $inRepo = $false
        if ($parentCommand -and $parentCommand.ToLowerInvariant().Contains($repoLower)) {
            $inRepo = $true
        }
        elseif ($parentExe -and $parentExe.ToLowerInvariant().Contains($repoLower)) {
            $inRepo = $true
        }

        if (-not $inRepo) {
            return $current
        }

        $current = $parentSnapshot
    }
}

function Test-ManagedProcessOwnership {
    param(
        [Parameter(Mandatory = $true)]
        $Identity,

        [Parameter(Mandatory = $true)]
        $Snapshot
    )

    if ($null -eq $Snapshot) {
        return $false
    }

    if ([int64]$Identity.pid -ne [int64]$Snapshot.pid) {
        return $false
    }

    if ([int64]$Identity.processStartTimeUtcTicks -ne [int64]$Snapshot.processStartTimeUtcTicks) {
        return $false
    }

    $identityExe = [string]$Identity.executablePath
    if ($null -eq $Identity.executablePath) { $identityExe = '' }
    $snapshotExe = [string]$Snapshot.executablePath
    if ($null -eq $Snapshot.executablePath) { $snapshotExe = '' }
    if ($identityExe -and $snapshotExe -and ($identityExe.ToLowerInvariant() -ne $snapshotExe.ToLowerInvariant())) {
        return $false
    }

    $identityCmd = [string]$Identity.commandLine
    if ($null -eq $Identity.commandLine) { $identityCmd = '' }
    $snapshotCmd = [string]$Snapshot.commandLine
    if ($null -eq $Snapshot.commandLine) { $snapshotCmd = '' }
    if ($identityCmd -and $snapshotCmd -and ($identityCmd.ToLowerInvariant() -ne $snapshotCmd.ToLowerInvariant())) {
        return $false
    }

    $repoRoot = [string]$Identity.repoRoot
    if ($null -eq $Identity.repoRoot) { $repoRoot = '' }
    if ($repoRoot) {
        $repoLower = [System.IO.Path]::GetFullPath($repoRoot).TrimEnd('\').ToLowerInvariant()
        $snapshotRepo = [string]$Snapshot.repoRoot
        if ($null -eq $Snapshot.repoRoot) { $snapshotRepo = '' }
        $snapshotRepoLower = if ($snapshotRepo) { [System.IO.Path]::GetFullPath($snapshotRepo).TrimEnd('\').ToLowerInvariant() } else { '' }
        $containsRepo = $false
        if ($snapshotRepoLower -and $snapshotRepoLower -eq $repoLower) {
            $containsRepo = $true
        }
        elseif ($snapshotCmd -and $snapshotCmd.ToLowerInvariant().Contains($repoLower)) {
            $containsRepo = $true
        }
        elseif ($snapshotExe -and $snapshotExe.ToLowerInvariant().Contains($repoLower)) {
            $containsRepo = $true
        }

        if (-not $containsRepo) {
            return $false
        }
    }

    return $true
}

function Test-BackendOwnership {
    param(
        [Parameter(Mandatory = $true)]
        $Identity,

        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,

        [Parameter(Mandatory = $true)]
        [string]$PythonPath,

        [Parameter(Mandatory = $true)]
        [string]$MainPath,

        [double]$ProcessCreatedAt
    )

    $snapshot = Get-ProcessIdentitySnapshot -ProcessId ([int]$Identity.pid)
    if ($null -eq $snapshot) {
        return $false
    }

    $expected = [pscustomobject]@{
        pid = [int]$Identity.pid
        processStartTimeUtcTicks = [int64]$Identity.processStartTimeUtcTicks
        executablePath = $PythonPath
        commandLine = [string]$Identity.commandLine
        repoRoot = $RepoRoot
    }

    return (Test-ManagedProcessOwnership -Identity $expected -Snapshot $snapshot)
}

function Assert-PortAvailableOrOwned {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Address,

        [Parameter(Mandatory = $true)]
        [int]$Port,

        [Parameter(Mandatory = $true)]
        [scriptblock]$OwnerCheck
    )

    if (-not (Test-TcpPortListening -Address $Address -Port $Port)) {
        return
    }

    if (-not (& $OwnerCheck)) {
        throw "Port $Port is already in use by a non-repo-owned process."
    }
}

function Start-ManagedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList,

        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,

        [hashtable]$Environment = @{},

        [Parameter(Mandatory = $true)]
        [string]$StdoutLogPath,

        [Parameter(Mandatory = $true)]
        [string]$StderrLogPath
    )

    Ensure-Directory -Path (Split-Path -Parent $StdoutLogPath)
    Ensure-Directory -Path (Split-Path -Parent $StderrLogPath)

    $savedEnv = @{}
    try {
        foreach ($key in $Environment.Keys) {
            $savedEnv[$key] = [System.Environment]::GetEnvironmentVariable($key, 'Process')
            [System.Environment]::SetEnvironmentVariable($key, [string]$Environment[$key], 'Process')
        }

        return Start-Process `
            -FilePath $FilePath `
            -ArgumentList $ArgumentList `
            -WorkingDirectory $WorkingDirectory `
            -RedirectStandardOutput $StdoutLogPath `
            -RedirectStandardError $StderrLogPath `
            -WindowStyle Hidden `
            -PassThru
    }
    finally {
        foreach ($key in $Environment.Keys) {
            [System.Environment]::SetEnvironmentVariable($key, $savedEnv[$key], 'Process')
        }
    }
}

function Read-CurrentProcessIdentity {
    param([int]$ProcessId)

    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        $snapshot = Get-ProcessIdentitySnapshot -ProcessId $ProcessId
        if ($null -ne $snapshot -and $snapshot.processStartTimeUtcTicks) {
            return $snapshot
        }
        Start-Sleep -Milliseconds 200
    }

    throw "Unable to read process identity for PID $ProcessId."
}

function New-ProcessRecord {
    param(
        [Parameter(Mandatory = $true)]
        $Snapshot,

        [Parameter(Mandatory = $true)]
        [string]$Status,

        [Parameter(Mandatory = $true)]
        [string]$Role
    )

    [ordered]@{
        role = $Role
        status = $Status
        pid = [int]$Snapshot.pid
        processStartTimeUtcTicks = [int64]$Snapshot.processStartTimeUtcTicks
        executablePath = $Snapshot.executablePath
        commandLine = $Snapshot.commandLine
        repoRoot = $script:RepoRoot
    }
}

function New-LauncherState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SessionId,

        $BackendRecord = $null,
        $WebRecord = $null,

        [string]$Status = 'running',

        [string]$WebModeValue = $WebMode
    )

    [ordered]@{
        sessionId = $SessionId
        status = $Status
        webMode = $WebModeValue
        updatedAt = [DateTime]::UtcNow.ToString('o')
        backend = $BackendRecord
        web = $WebRecord
        runtime = [ordered]@{
            status = 'managed-by-backend'
        }
    }
}

function Save-LauncherState {
    param([Parameter(Mandatory = $true)]$State)

    Write-JsonAtomically -Path $script:StatePath -Data $State
}

function New-LauncherDiagnostics {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SessionId,

        [Parameter(Mandatory = $true)]
        [string]$WebModeValue
    )

    [ordered]@{
        sessionId = $SessionId
        webMode = $WebModeValue
        launcherStartAtUtc = [DateTime]::UtcNow.ToString('o')
        timeout = [ordered]@{
            backendHealthTimeoutSeconds = $script:BackendHealthTimeoutSeconds
            webHealthTimeoutSeconds = $script:WebHealthTimeoutSeconds
            pollIntervalMilliseconds = $script:DefaultHealthPollIntervalMilliseconds
        }
        backend = [ordered]@{
            spawnedAtUtc = $null
            pid = $null
            processStartTimeUtcTicks = $null
            firstTcpListeningAtUtc = $null
            firstHttpResponseAtUtc = $null
            firstValidHealthResponseAtUtc = $null
            exitAtUtc = $null
            exitCode = $null
        }
        web = [ordered]@{
            spawnedAtUtc = $null
            pid = $null
            processStartTimeUtcTicks = $null
            firstHttpResponseAtUtc = $null
        }
        rollback = [ordered]@{
            startedAtUtc = $null
            endedAtUtc = $null
        }
    }
}

function Write-LauncherDiagnostics {
    param(
        [Parameter(Mandatory = $true)]
        $Diagnostics
    )

    Ensure-Directory -Path $script:LogsDir
    Write-JsonAtomically -Path (Join-Path $script:LogsDir 'launcher.timeline.json') -Data $Diagnostics
}

function Request-GracefulBackendShutdown {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ControlPath,

        [Parameter(Mandatory = $true)]
        [string]$SessionId
    )

    $payload = [ordered]@{
        sessionId = $SessionId
        action = 'shutdown'
        requestedAt = [DateTime]::UtcNow.ToString('o')
        reason = 'launcher-stop'
    }

    Write-JsonAtomically -Path $ControlPath -Data $payload
}

function Resolve-PnpmCmdPath {
    $cmd = Get-Command pnpm.cmd -ErrorAction Stop
    return $cmd.Source
}

function Resolve-NodeExePath {
    $cmd = Get-Command node.exe -ErrorAction Stop
    return $cmd.Source
}

function New-WebDevCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,

        [Parameter(Mandatory = $true)]
        [string]$BackendUrl,

        [string]$PnpmCmdPath = $(Resolve-PnpmCmdPath),
        [string]$NodeExePath = $(Resolve-NodeExePath)
    )

    $webPath = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot 'web'))
    $viteCliPath = [System.IO.Path]::GetFullPath((Join-Path $webPath 'node_modules\vite\bin\vite.js'))
    $commandText = ('call "{0}" "{1}" --host 127.0.0.1 --port 3000 --strictPort' -f $NodeExePath, $viteCliPath)

    [pscustomobject]@{
        FilePath = 'cmd.exe'
        ArgumentList = @('/d', '/s', '/c', $commandText)
        WorkingDirectory = $webPath
        Environment = @{
            VITE_API_BASE_URL = $BackendUrl
        }
        WebPath = $webPath
        PnpmCmdPath = $PnpmCmdPath
        NodeExePath = $NodeExePath
        ViteCliPath = $viteCliPath
    }
}

function New-BackendCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,

        [Parameter(Mandatory = $true)]
        [string]$SessionId,

        [Parameter(Mandatory = $true)]
        [string]$ShutdownRequestPath
    )

    $pythonPath = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot '.venv\Scripts\python.exe'))
    $mainPath = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot 'main.py'))

    [pscustomobject]@{
        FilePath = $pythonPath
        ArgumentList = @($mainPath)
        WorkingDirectory = $RepoRoot
        Environment = @{
            LANGBOT_RPA_FORCE_DISABLE_SEND = '1'
            LANGBOT_RPA_ALLOW_AUTO_SEND = '0'
            LANGBOT_BROADCAST_SEND_ENABLED = '0'
            PYTHONPATH = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot 'src'))
            LANGBOT_LOCAL_STACK_SESSION_ID = $SessionId
            LANGBOT_LOCAL_SHUTDOWN_REQUEST_PATH = $ShutdownRequestPath
        }
        PythonPath = $pythonPath
        MainPath = $mainPath
    }
}

function Get-StateOwnedWebCheck {
    param($State)

    $capturedWeb = if ($null -ne $State) {
        $State.web
    }
    else {
        $null
    }

    $capturedSnapshotReader = ${function:Get-ProcessIdentitySnapshot}
    $capturedOwnershipChecker = ${function:Test-ManagedProcessOwnership}

    return {
        if ($null -eq $capturedWeb -or -not $capturedWeb.pid) {
            return $false
        }

        $snapshot = & $capturedSnapshotReader -ProcessId ([int]$capturedWeb.pid)
        if ($null -eq $snapshot) {
            return $false
        }

        return (& $capturedOwnershipChecker -Identity $capturedWeb -Snapshot $snapshot)
    }.GetNewClosure()
}

function Wait-ForHttpOk {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,

        [int]$TimeoutSeconds = 45
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -Method Get -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                return $true
            }
        }
        catch {
        }

        Start-Sleep -Milliseconds 500
    }

    return $false
}

function Get-ManagedProcessLifecycleStatus {
    param(
        [Parameter(Mandatory = $true)]
        $Identity
    )

    try {
        $process = [System.Diagnostics.Process]::GetProcessById([int]$Identity.pid)
        if ($process.HasExited) {
            return [ordered]@{
                state = 'exited'
                exitCode = $process.ExitCode
                exitedAtUtc = [DateTime]::UtcNow.ToString('o')
            }
        }

        $snapshot = Get-ProcessIdentitySnapshot -ProcessId ([int]$Identity.pid)
        if (-not (Test-ManagedProcessOwnership -Identity $Identity -Snapshot $snapshot)) {
            return [ordered]@{
                state = 'reused'
                exitCode = $null
                exitedAtUtc = $null
            }
        }

        return [ordered]@{
            state = 'running'
            exitCode = $null
            exitedAtUtc = $null
        }
    }
    catch {
        return [ordered]@{
            state = 'exited'
            exitCode = $null
            exitedAtUtc = [DateTime]::UtcNow.ToString('o')
        }
    }
}

function Get-LogTail {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [int]$Tail = 40
    )

    try {
        return @(Get-Content -LiteralPath $Path -Tail $Tail -ErrorAction Stop)
    }
    catch {
        return @()
    }
}

function Invoke-BackendHealthProbe {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -Method Get -UseBasicParsing -TimeoutSec 3
        $payload = $null
        try {
            $payload = $response.Content | ConvertFrom-Json
        }
        catch {
        }

        $code = if ($null -ne $payload -and $payload.PSObject.Properties.Name -contains 'code') { $payload.code } else { $null }
        $msg = if ($null -ne $payload -and $payload.PSObject.Properties.Name -contains 'msg') { [string]$payload.msg } else { $null }

        return [ordered]@{
            ready = ($response.StatusCode -eq 200 -and [int]$code -eq 0 -and $msg -eq 'ok')
            responded = $true
            statusCode = [int]$response.StatusCode
            code = $code
            msg = $msg
        }
    }
    catch {
        return [ordered]@{
            ready = $false
            responded = $false
            statusCode = $null
            code = $null
            msg = $null
            error = $_.Exception.Message
        }
    }
}

function Wait-ForBackendHealth {
    param(
        [Parameter(Mandatory = $true)]
        $BackendIdentity,

        [Parameter(Mandatory = $true)]
        [string]$HealthUrl,

        [Parameter(Mandatory = $true)]
        [string]$Address,

        [Parameter(Mandatory = $true)]
        [int]$Port,

        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds,

        [int]$PollIntervalMilliseconds = $script:DefaultHealthPollIntervalMilliseconds,

        [string]$StdoutLogPath = '',
        [string]$StderrLogPath = '',
        $Diagnostics = $null
    )

    $startedAt = [DateTime]::UtcNow
    $deadline = $startedAt.AddSeconds([Math]::Max(0, $TimeoutSeconds))

    while ($true) {
        if ([DateTime]::UtcNow -ge $deadline) {
            return [ordered]@{
                status = 'timeout'
                waitedSeconds = [Math]::Round(([DateTime]::UtcNow - $startedAt).TotalSeconds, 3)
                stdoutTail = @(Get-LogTail -Path $StdoutLogPath)
                stderrTail = @(Get-LogTail -Path $StderrLogPath)
            }
        }

        $lifecycle = Get-ManagedProcessLifecycleStatus -Identity $BackendIdentity
        $lifecycleState = if ($lifecycle -is [System.Collections.IDictionary]) { [string]$lifecycle['state'] } else { [string]$lifecycle.state }
        $lifecycleExitCode = if ($lifecycle -is [System.Collections.IDictionary]) { $lifecycle['exitCode'] } else { $lifecycle.exitCode }
        $lifecycleExitedAtUtc = if ($lifecycle -is [System.Collections.IDictionary]) { $lifecycle['exitedAtUtc'] } else { $lifecycle.exitedAtUtc }

        if ($lifecycleState -eq 'exited') {
            if ($null -ne $Diagnostics) {
                $Diagnostics.backend.exitAtUtc = $lifecycleExitedAtUtc
                $Diagnostics.backend.exitCode = $lifecycleExitCode
            }

            return [ordered]@{
                status = 'exited'
                exitCode = $lifecycleExitCode
                waitedSeconds = [Math]::Round(([DateTime]::UtcNow - $startedAt).TotalSeconds, 3)
                stdoutTail = @(Get-LogTail -Path $StdoutLogPath)
                stderrTail = @(Get-LogTail -Path $StderrLogPath)
            }
        }

        if ($lifecycleState -eq 'reused') {
            return [ordered]@{
                status = 'reused'
                exitCode = $null
                waitedSeconds = [Math]::Round(([DateTime]::UtcNow - $startedAt).TotalSeconds, 3)
                stdoutTail = @(Get-LogTail -Path $StdoutLogPath)
                stderrTail = @(Get-LogTail -Path $StderrLogPath)
            }
        }

        if ((Test-TcpPortListening -Address $Address -Port $Port) -and $null -ne $Diagnostics -and -not $Diagnostics.backend.firstTcpListeningAtUtc) {
            $Diagnostics.backend.firstTcpListeningAtUtc = [DateTime]::UtcNow.ToString('o')
        }

        $probe = Invoke-BackendHealthProbe -Url $HealthUrl
        if ($probe.responded -and $null -ne $Diagnostics -and -not $Diagnostics.backend.firstHttpResponseAtUtc) {
            $Diagnostics.backend.firstHttpResponseAtUtc = [DateTime]::UtcNow.ToString('o')
        }

        if ($probe.ready) {
            if ($null -ne $Diagnostics -and -not $Diagnostics.backend.firstValidHealthResponseAtUtc) {
                $Diagnostics.backend.firstValidHealthResponseAtUtc = [DateTime]::UtcNow.ToString('o')
            }

            return [ordered]@{
                status = 'ready'
                waitedSeconds = [Math]::Round(([DateTime]::UtcNow - $startedAt).TotalSeconds, 3)
                probe = $probe
            }
        }

        Start-Sleep -Milliseconds $PollIntervalMilliseconds
    }
}

function Wait-ForProcessExit {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ProcessId,

        [int]$TimeoutSeconds = 20
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $process = [System.Diagnostics.Process]::GetProcessById($ProcessId)
            if ($process.HasExited) {
                return $true
            }
        }
        catch {
            return $true
        }

        Start-Sleep -Milliseconds 500
    }

    return $false
}

function Stop-RepoOwnedProcess {
    param(
        [Parameter(Mandatory = $true)]
        $Identity
    )

    $snapshot = Get-ProcessIdentitySnapshot -ProcessId ([int]$Identity.pid)
    if (-not (Test-ManagedProcessOwnership -Identity $Identity -Snapshot $snapshot)) {
        return $false
    }

    & taskkill.exe /T /F /PID ([int]$Identity.pid) | Out-Null
    Start-Sleep -Milliseconds 500
    try {
        [System.Diagnostics.Process]::GetProcessById([int]$Identity.pid) | Out-Null
        return $false
    }
    catch {
        return $true
    }
}

function Get-RepoOwnedRunningStack {
    param([string]$RepoRoot = $script:RepoRoot)

    $backendListener = Resolve-ListenerOwnedSnapshot -Port (Resolve-ApiConfiguration -RepoRoot $RepoRoot).Port -RepoRoot $RepoRoot -ExpectedCommandFragment 'main.py'
    $webListener = Resolve-ListenerOwnedSnapshot -Port 3000 -RepoRoot $RepoRoot -ExpectedCommandFragment 'vite.js'

    $backendRoot = if ($null -ne $backendListener) { Resolve-RepoProcessRootSnapshot -Snapshot $backendListener -RepoRoot $RepoRoot } else { $null }
    $webRoot = if ($null -ne $webListener) { Resolve-RepoProcessRootSnapshot -Snapshot $webListener -RepoRoot $RepoRoot } else { $null }

    [ordered]@{
        backend = if ($null -ne $backendRoot) { New-ProcessRecord -Snapshot $backendRoot -Status 'running' -Role 'backend' } else { $null }
        web = if ($null -ne $webRoot) { New-ProcessRecord -Snapshot $webRoot -Status 'running' -Role 'web' } else { $null }
    }
}

function Rollback-PartialStart {
    param(
        $BackendIdentity = $null,
        $WebIdentity = $null,
        [string]$SessionId = '',
        $Diagnostics = $null
    )

    if ($null -ne $Diagnostics) {
        $Diagnostics.rollback.startedAtUtc = [DateTime]::UtcNow.ToString('o')
    }

    if ($null -ne $WebIdentity) {
        Stop-RepoOwnedProcess -Identity $WebIdentity | Out-Null
    }

    if ($null -ne $BackendIdentity) {
        if ($SessionId) {
            Request-GracefulBackendShutdown -ControlPath $script:ShutdownRequestPath -SessionId $SessionId
            if (-not (Wait-ForProcessExit -ProcessId ([int]$BackendIdentity.pid) -TimeoutSeconds 10)) {
                Stop-RepoOwnedProcess -Identity $BackendIdentity | Out-Null
            }
        }
        else {
            Stop-RepoOwnedProcess -Identity $BackendIdentity | Out-Null
        }
    }

    Remove-LauncherState
    Remove-StaleShutdownRequest
    if ($null -ne $Diagnostics) {
        $Diagnostics.rollback.endedAtUtc = [DateTime]::UtcNow.ToString('o')
    }
    Remove-StaleShutdownRequest
}

function Get-StateOwnedBackendCheck {
    param($State)

    $capturedBackend = if ($null -ne $State) {
        $State.backend
    }
    else {
        $null
    }

    $capturedRepoRoot = if ($script:RepoRoot) {
        [string]$script:RepoRoot
    }
    else {
        ''
    }

    $capturedPythonPath = if ($null -ne $capturedBackend -and $capturedBackend.executablePath) {
        [string]$capturedBackend.executablePath
    }
    else {
        ''
    }

    $capturedMainPath = if ($capturedRepoRoot) {
        [System.IO.Path]::GetFullPath((Join-Path $capturedRepoRoot 'main.py'))
    }
    else {
        ''
    }

    $capturedOwnershipChecker = ${function:Test-BackendOwnership}

    return {
        if (
            $null -eq $capturedBackend -or
            -not $capturedBackend.pid -or
            -not $capturedBackend.processStartTimeUtcTicks -or
            -not $capturedRepoRoot -or
            -not $capturedPythonPath -or
            -not $capturedMainPath
        ) {
            return $false
        }

        return (& $capturedOwnershipChecker `
            -Identity $capturedBackend `
            -RepoRoot $capturedRepoRoot `
            -PythonPath $capturedPythonPath `
            -MainPath $capturedMainPath `
            -ProcessCreatedAt 0)
    }.GetNewClosure()
}

function Resolve-OwnedStateRecord {
    param(
        $PreferredRecord = $null,
        $DetectedRecord = $null
    )

    $resolution = [ordered]@{
        Record = $PreferredRecord
        VerifiedRecord = $null
        VerifiedSnapshot = $null
        DetectedRecord = $null
        Ownership = 'none'
        Status = 'absent'
    }

    $hasPreferred = ($null -ne $PreferredRecord -and $PreferredRecord.pid)
    $hasDetected = ($null -ne $DetectedRecord -and $DetectedRecord.pid)

    if (-not $hasPreferred) {
        if ($hasDetected) {
            $resolution.DetectedRecord = $DetectedRecord
            $resolution.Ownership = 'unknown'
            $resolution.Status = 'detected-unmanaged'
        }

        return [pscustomobject]$resolution
    }

    $snapshot = Get-ProcessIdentitySnapshot -ProcessId ([int]$PreferredRecord.pid)
    $snapshotMatches = ($null -ne $snapshot -and (Test-ManagedProcessOwnership -Identity $PreferredRecord -Snapshot $snapshot))
    $detectedMatches = ($hasDetected -and (Test-ManagedProcessOwnership -Identity $PreferredRecord -Snapshot $DetectedRecord))

    if ($snapshotMatches) {
        $resolution.VerifiedRecord = $PreferredRecord
        $resolution.VerifiedSnapshot = $snapshot

        if ($hasDetected -and -not $detectedMatches) {
            $resolution.DetectedRecord = $DetectedRecord
            $resolution.Ownership = 'unknown'
            $resolution.Status = 'identity-mismatch'
        }
        else {
            $resolution.Ownership = 'owned'
            $resolution.Status = 'verified'
        }

        return [pscustomobject]$resolution
    }

    if ($hasDetected) {
        $resolution.DetectedRecord = $DetectedRecord
        $resolution.Ownership = 'unknown'
        $resolution.Status = 'identity-mismatch'
        return [pscustomobject]$resolution
    }

    if ($null -ne $snapshot) {
        $resolution.Ownership = 'unknown'
        $resolution.Status = 'identity-mismatch'
        return [pscustomobject]$resolution
    }

    $resolution.Status = 'missing'
    return [pscustomobject]$resolution
}

function Resolve-EffectiveLauncherState {
    param(
        [string]$RepoRoot = $script:RepoRoot,
        [string]$RequestedWebMode = $script:WebMode
    )

    $persistedState = Read-JsonFile -Path $script:StatePath
    $detected = Get-RepoOwnedRunningStack -RepoRoot $RepoRoot
    $state = $persistedState

    $backendResolution = Resolve-OwnedStateRecord `
        -PreferredRecord $(if ($null -ne $state) { $state.backend } else { $null }) `
        -DetectedRecord $detected.backend

    $webResolution = Resolve-OwnedStateRecord `
        -PreferredRecord $(if ($null -ne $state) { $state.web } else { $null }) `
        -DetectedRecord $detected.web

    $effectiveWebMode = if ($null -ne $state -and $state.webMode) {
        [string]$state.webMode
    }
    else {
        $RequestedWebMode
    }

    [pscustomobject]@{
        PersistedState = $persistedState
        State = $state
        Detected = $detected
        BackendResolution = $backendResolution
        WebResolution = $webResolution
        BackendRecord = $backendResolution.VerifiedRecord
        WebRecord = $webResolution.VerifiedRecord
        WebMode = $effectiveWebMode
    }
}

function Get-AggregateStackStatus {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WebModeValue,

        [Parameter(Mandatory = $true)]
        [string]$BackendStatus,

        [Parameter(Mandatory = $true)]
        [string]$WebStatus,

        [bool]$HasPersistedState = $false,

        [bool]$HasOwnershipUnknown = $false,

        [bool]$HasDetectedComponents = $false
    )

    if (-not $HasPersistedState) {
        if ($HasOwnershipUnknown -or $HasDetectedComponents) {
            return 'degraded'
        }

        return 'stopped'
    }

    if ($WebModeValue -eq 'Bundled') {
        if ($HasOwnershipUnknown) {
            return 'degraded'
        }

        switch ($BackendStatus) {
            'running' { return 'running' }
            'process-up' { return 'degraded' }
            default { return 'stopped' }
        }
    }

    $backendUp = @('running', 'process-up') -contains $BackendStatus
    $webUp = $WebStatus -eq 'running'

    if ($HasOwnershipUnknown) {
        return 'degraded'
    }

    if ($BackendStatus -eq 'running' -and $webUp) {
        return 'running'
    }

    if (-not $backendUp -and -not $webUp) {
        return 'stopped'
    }

    return 'degraded'
}

function Assert-RequestedModeMatchesStatus {
    param(
        $Status,

        [Parameter(Mandatory = $true)]
        [string]$RequestedWebMode
    )

    if ($null -eq $Status) {
        return
    }

    $currentStatus = [string]$Status.status
    if (-not $currentStatus -or $currentStatus -eq 'stopped') {
        return
    }

    $currentMode = [string]$Status.webMode
    if (-not $currentMode -or $currentMode -eq $RequestedWebMode) {
        return
    }

    throw "STACK_MODE_MISMATCH`nStack is already running in $currentMode mode. Use Restart -WebMode $RequestedWebMode."
}

function Test-StackHealthyForStart {
    param(
        $Status,

        [Parameter(Mandatory = $true)]
        [string]$RequestedWebMode
    )

    if ($null -eq $Status) {
        return $false
    }

    if ([string]$Status.status -ne 'running') {
        return $false
    }

    if ([string]$Status.ownership -ne 'owned') {
        return $false
    }

    if ([string]$Status.webMode -ne $RequestedWebMode) {
        return $false
    }

    if ([string]$Status.backend.status -ne 'running' -or [string]$Status.backend.ownership -ne 'owned') {
        return $false
    }

    if ($RequestedWebMode -eq 'Bundled') {
        return ([string]$Status.web.status -eq 'not-used')
    }

    return ([string]$Status.web.status -eq 'running' -and [string]$Status.web.ownership -eq 'owned')
}

function Get-StackStatus {
    param(
        [string]$RepoRoot = $script:RepoRoot,
        [string]$RequestedWebMode = $WebMode
    )

    $apiConfig = Resolve-ApiConfiguration -RepoRoot $RepoRoot
    $resolvedState = Resolve-EffectiveLauncherState -RepoRoot $RepoRoot -RequestedWebMode $RequestedWebMode
    $state = $resolvedState.State
    $backendResolution = $resolvedState.BackendResolution
    $webResolution = $resolvedState.WebResolution

    $backendStatus = [ordered]@{
        status = 'down'
        ownership = if ($backendResolution.Ownership -eq 'unknown') { 'unknown' } elseif ($backendResolution.Ownership -eq 'owned') { 'owned' } else { 'none' }
        url = $apiConfig.BaseUrl
        healthUrl = $apiConfig.HealthUrl
        pid = if ($null -ne $backendResolution.Record -and $backendResolution.Record.pid) { [int]$backendResolution.Record.pid } else { $null }
        processStartTimeUtcTicks = if ($null -ne $backendResolution.Record -and $backendResolution.Record.processStartTimeUtcTicks) { [int64]$backendResolution.Record.processStartTimeUtcTicks } else { $null }
    }

    $effectiveWebMode = [string]$resolvedState.WebMode

    $webStatus = [ordered]@{
        status = if ($effectiveWebMode -eq 'Dev') { 'down' } else { 'not-used' }
        ownership = if ($webResolution.Ownership -eq 'unknown') { 'unknown' } elseif ($webResolution.Ownership -eq 'owned') { 'owned' } else { 'none' }
        url = if ($effectiveWebMode -eq 'Dev') { 'http://127.0.0.1:3000' } else { $null }
        pid = if ($null -ne $webResolution.Record -and $webResolution.Record.pid) { [int]$webResolution.Record.pid } else { $null }
        processStartTimeUtcTicks = if ($null -ne $webResolution.Record -and $webResolution.Record.processStartTimeUtcTicks) { [int64]$webResolution.Record.processStartTimeUtcTicks } else { $null }
    }

    if ($null -ne $backendResolution.VerifiedRecord -and $backendResolution.VerifiedRecord.pid) {
        if ($backendResolution.VerifiedRecord.pid) {
            $backendStatus.status = if (Wait-ForHttpOk -Url $apiConfig.HealthUrl -TimeoutSeconds 1) { 'running' } else { 'process-up' }
        }
    }

    if ($effectiveWebMode -eq 'Dev' -and $null -ne $webResolution.VerifiedRecord -and $webResolution.VerifiedRecord.pid) {
            $webStatus.status = 'running'
    }

    $detectedComponents = [ordered]@{}
    if ($null -ne $backendResolution.DetectedRecord -and $backendResolution.DetectedRecord.pid) {
        $detectedComponents.backend = [ordered]@{
            pid = [int]$backendResolution.DetectedRecord.pid
            processStartTimeUtcTicks = [int64]$backendResolution.DetectedRecord.processStartTimeUtcTicks
            executablePath = $backendResolution.DetectedRecord.executablePath
            commandLine = $backendResolution.DetectedRecord.commandLine
            repoRoot = $backendResolution.DetectedRecord.repoRoot
        }
    }
    if ($null -ne $webResolution.DetectedRecord -and $webResolution.DetectedRecord.pid) {
        $detectedComponents.web = [ordered]@{
            pid = [int]$webResolution.DetectedRecord.pid
            processStartTimeUtcTicks = [int64]$webResolution.DetectedRecord.processStartTimeUtcTicks
            executablePath = $webResolution.DetectedRecord.executablePath
            commandLine = $webResolution.DetectedRecord.commandLine
            repoRoot = $webResolution.DetectedRecord.repoRoot
        }
    }

    $hasOwnershipUnknown = ($backendResolution.Ownership -eq 'unknown' -or $webResolution.Ownership -eq 'unknown')
    $hasDetectedComponents = ($detectedComponents.Count -gt 0)
    $aggregateStatus = Get-AggregateStackStatus `
        -WebModeValue $effectiveWebMode `
        -BackendStatus ([string]$backendStatus.status) `
        -WebStatus ([string]$webStatus.status) `
        -HasPersistedState ($null -ne $state) `
        -HasOwnershipUnknown $hasOwnershipUnknown `
        -HasDetectedComponents $hasDetectedComponents

    [ordered]@{
        repoRoot = $RepoRoot
        sessionId = if ($null -ne $state) { [string]$state.sessionId } else { $null }
        status = $aggregateStatus
        ownership = if ($hasOwnershipUnknown -or $hasDetectedComponents) { 'unknown' } elseif ([string]$aggregateStatus -eq 'running') { 'owned' } else { 'none' }
        webMode = $effectiveWebMode
        backend = $backendStatus
        web = $webStatus
        detectedComponents = $detectedComponents
        runtime = [ordered]@{
            status = 'managed-by-backend'
        }
    }
}

function New-StartDryRunSummary {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WebModeValue
    )

    $apiConfig = Resolve-ApiConfiguration -RepoRoot $script:RepoRoot
    $sessionId = [guid]::NewGuid().ToString('N')
    $backendCommand = New-BackendCommand -RepoRoot $script:RepoRoot -SessionId $sessionId -ShutdownRequestPath $script:ShutdownRequestPath

    $summary = [ordered]@{
        action = 'Start'
        mode = $WebModeValue
        dryRun = $true
        realSend = 'disabled'
        timeout = [ordered]@{
            backendHealthTimeoutSeconds = $script:BackendHealthTimeoutSeconds
            webHealthTimeoutSeconds = $script:WebHealthTimeoutSeconds
            pollIntervalMilliseconds = $script:DefaultHealthPollIntervalMilliseconds
        }
        runtime = [ordered]@{ status = 'managed-by-backend' }
        backend = [ordered]@{
            filePath = $backendCommand.FilePath
            argumentList = $backendCommand.ArgumentList
            workingDirectory = $backendCommand.WorkingDirectory
            stdoutLogPath = (Join-Path $script:LogsDir 'backend.stdout.log')
            stderrLogPath = (Join-Path $script:LogsDir 'backend.stderr.log')
            url = $apiConfig.BaseUrl
            healthUrl = $apiConfig.HealthUrl
            port = $apiConfig.Port
        }
        statePath = $script:StatePath
        shutdownRequestPath = $script:ShutdownRequestPath
    }

    if ($WebModeValue -eq 'Dev') {
        $webCommand = New-WebDevCommand -RepoRoot $script:RepoRoot -BackendUrl $apiConfig.BaseUrl
        $summary.web = [ordered]@{
            filePath = $webCommand.FilePath
            argumentList = $webCommand.ArgumentList
            workingDirectory = $webCommand.WorkingDirectory
            webPath = $webCommand.WebPath
            pnpmCmdPath = $webCommand.PnpmCmdPath
            stdoutLogPath = (Join-Path $script:LogsDir 'web.stdout.log')
            stderrLogPath = (Join-Path $script:LogsDir 'web.stderr.log')
        }
    }
    else {
        $summary.web = [ordered]@{
            status = 'not-used'
            bundledEntry = [System.IO.Path]::GetFullPath((Join-Path $script:RepoRoot 'web\\dist\\index.html'))
        }
    }

    return $summary
}

function Start-BackendStack {
    param([Parameter(Mandatory = $true)][string]$WebModeValue)

    if ($DryRun) {
        return (New-StartDryRunSummary -WebModeValue $WebModeValue)
    }

    Ensure-Directory -Path $script:StackRoot
    Ensure-Directory -Path $script:ControlDir
    Ensure-Directory -Path $script:LogsDir
    Remove-StaleShutdownRequest
    if ($WebModeValue -eq 'Bundled') {
        Assert-BundledFrontendReady -RepoRoot $script:RepoRoot | Out-Null
    }

    $apiConfig = Resolve-ApiConfiguration -RepoRoot $script:RepoRoot
    $currentStatus = Get-StackStatus -RepoRoot $script:RepoRoot -RequestedWebMode $WebModeValue
    if ([string]$currentStatus.status -ne 'stopped') {
        Assert-RequestedModeMatchesStatus -Status $currentStatus -RequestedWebMode $WebModeValue
        if (Test-StackHealthyForStart -Status $currentStatus -RequestedWebMode $WebModeValue) {
            return $currentStatus
        }

        throw 'STACK_NOT_HEALTHY`nStack is not healthy. Use Status for diagnostics, then Stop or Restart after resolving ownership.'
    }

    $state = Read-JsonFile -Path $script:StatePath
    $ownerCheck = Get-StateOwnedBackendCheck -State $state
    Assert-PortAvailableOrOwned -Address $apiConfig.Host -Port $apiConfig.Port -OwnerCheck $ownerCheck

    if (Test-TcpPortListening -Address $apiConfig.Host -Port $apiConfig.Port) {
        return (Get-StackStatus -RequestedWebMode $WebModeValue)
    }

    $sessionId = [guid]::NewGuid().ToString('N')
    $diagnostics = New-LauncherDiagnostics -SessionId $sessionId -WebModeValue $WebModeValue
    $backendCommand = New-BackendCommand -RepoRoot $script:RepoRoot -SessionId $sessionId -ShutdownRequestPath $script:ShutdownRequestPath
    $backendProc = $null
    $backendIdentity = $null
    $webIdentity = $null

    try {
        $backendProc = Start-ManagedProcess `
            -FilePath $backendCommand.FilePath `
            -ArgumentList $backendCommand.ArgumentList `
            -WorkingDirectory $backendCommand.WorkingDirectory `
            -Environment $backendCommand.Environment `
            -StdoutLogPath (Join-Path $script:LogsDir 'backend.stdout.log') `
            -StderrLogPath (Join-Path $script:LogsDir 'backend.stderr.log')

        $backendIdentity = New-ProcessRecord -Snapshot (Read-CurrentProcessIdentity -ProcessId $backendProc.Id) -Status 'starting' -Role 'backend'
        $diagnostics.backend.spawnedAtUtc = [DateTime]::UtcNow.ToString('o')
        $diagnostics.backend.pid = [int]$backendIdentity.pid
        $diagnostics.backend.processStartTimeUtcTicks = [int64]$backendIdentity.processStartTimeUtcTicks
        $stateData = New-LauncherState -SessionId $sessionId -BackendRecord $backendIdentity -WebRecord $null -Status 'starting' -WebModeValue $WebModeValue
        Save-LauncherState -State $stateData
        Write-LauncherDiagnostics -Diagnostics $diagnostics

        $backendHealth = Wait-ForBackendHealth `
            -BackendIdentity $backendIdentity `
            -HealthUrl $apiConfig.HealthUrl `
            -Address $apiConfig.Host `
            -Port $apiConfig.Port `
            -TimeoutSeconds $script:BackendHealthTimeoutSeconds `
            -PollIntervalMilliseconds $script:DefaultHealthPollIntervalMilliseconds `
            -StdoutLogPath (Join-Path $script:LogsDir 'backend.stdout.log') `
            -StderrLogPath (Join-Path $script:LogsDir 'backend.stderr.log') `
            -Diagnostics $diagnostics
        Write-LauncherDiagnostics -Diagnostics $diagnostics

        if ($backendHealth.status -ne 'ready') {
            $tailText = @(
                if ($backendHealth.stdoutTail) { "stdout tail:`n$($backendHealth.stdoutTail -join [Environment]::NewLine)" }
                if ($backendHealth.stderrTail) { "stderr tail:`n$($backendHealth.stderrTail -join [Environment]::NewLine)" }
            ) -join [Environment]::NewLine

            switch ($backendHealth.status) {
                'exited' {
                    throw "Backend exited before health became ready (PID $($backendIdentity.pid), exit code $($backendHealth.exitCode), waited $($backendHealth.waitedSeconds)s). $tailText"
                }
                'reused' {
                    throw "Backend PID $($backendIdentity.pid) no longer belongs to this session during health wait. $tailText"
                }
                default {
                    throw "Backend health timed out after $($backendHealth.waitedSeconds)s (PID $($backendIdentity.pid), URL $($apiConfig.HealthUrl)). $tailText"
                }
            }
        }

        $backendListenerSnapshot = Resolve-ListenerOwnedSnapshot -Port $apiConfig.Port -RepoRoot $script:RepoRoot -ExpectedCommandFragment 'main.py'
        if ($null -ne $backendListenerSnapshot) {
            $backendRootSnapshot = Resolve-RepoProcessRootSnapshot -Snapshot $backendListenerSnapshot -RepoRoot $script:RepoRoot
            if ($null -ne $backendRootSnapshot) {
                $backendListenerSnapshot = $backendRootSnapshot
            }
            $backendIdentity = New-ProcessRecord -Snapshot $backendListenerSnapshot -Status 'running' -Role 'backend'
            $stateData.backend = $backendIdentity
        }
        $stateData.backend.status = 'running'

        if ($WebModeValue -eq 'Dev') {
            $currentState = Read-JsonFile -Path $script:StatePath
            $webOwnerCheck = Get-StateOwnedWebCheck -State $currentState
            Assert-PortAvailableOrOwned -Address '127.0.0.1' -Port 3000 -OwnerCheck $webOwnerCheck
            $webCommand = New-WebDevCommand -RepoRoot $script:RepoRoot -BackendUrl $apiConfig.BaseUrl
            $webProc = Start-ManagedProcess `
                -FilePath $webCommand.FilePath `
                -ArgumentList $webCommand.ArgumentList `
                -WorkingDirectory $webCommand.WorkingDirectory `
                -Environment $webCommand.Environment `
                -StdoutLogPath (Join-Path $script:LogsDir 'web.stdout.log') `
                -StderrLogPath (Join-Path $script:LogsDir 'web.stderr.log')

            $webIdentity = New-ProcessRecord -Snapshot (Read-CurrentProcessIdentity -ProcessId $webProc.Id) -Status 'running' -Role 'web'
            $diagnostics.web.spawnedAtUtc = [DateTime]::UtcNow.ToString('o')
            $diagnostics.web.pid = [int]$webIdentity.pid
            $diagnostics.web.processStartTimeUtcTicks = [int64]$webIdentity.processStartTimeUtcTicks
            Write-LauncherDiagnostics -Diagnostics $diagnostics
            if (-not (Wait-ForHttpOk -Url 'http://127.0.0.1:3000' -TimeoutSeconds $script:WebHealthTimeoutSeconds)) {
                throw 'Dev web server health check failed: http://127.0.0.1:3000'
            }
            $webListenerSnapshot = Resolve-ListenerOwnedSnapshot -Port 3000 -RepoRoot $script:RepoRoot -ExpectedCommandFragment 'vite.js'
            if ($null -ne $webListenerSnapshot) {
                $webRootSnapshot = Resolve-RepoProcessRootSnapshot -Snapshot $webListenerSnapshot -RepoRoot $script:RepoRoot
                if ($null -ne $webRootSnapshot) {
                    $webListenerSnapshot = $webRootSnapshot
                }
                $webIdentity = New-ProcessRecord -Snapshot $webListenerSnapshot -Status 'running' -Role 'web'
            }
            $diagnostics.web.firstHttpResponseAtUtc = [DateTime]::UtcNow.ToString('o')
            $stateData.web = $webIdentity
        }
        else {
            $stateData.web = [ordered]@{
                role = 'web'
                status = 'not-used'
                pid = $null
                processStartTimeUtcTicks = $null
                executablePath = $null
                commandLine = $null
                repoRoot = $script:RepoRoot
            }
        }

        $stateData.status = 'running'
        $stateData.updatedAt = [DateTime]::UtcNow.ToString('o')
        Save-LauncherState -State $stateData
        Write-LauncherDiagnostics -Diagnostics $diagnostics
        return $stateData
    }
    catch {
        Rollback-PartialStart -BackendIdentity $backendIdentity -WebIdentity $webIdentity -SessionId $sessionId -Diagnostics $diagnostics
        Write-LauncherDiagnostics -Diagnostics $diagnostics
        throw
    }
}

function Stop-BackendStack {
    param([string]$RequestedWebMode = $script:WebMode)

    $resolvedState = Resolve-EffectiveLauncherState -RepoRoot $script:RepoRoot -RequestedWebMode $RequestedWebMode
    $state = $resolvedState.State
    $persistedState = $resolvedState.PersistedState
    $backendIdentity = $resolvedState.BackendRecord
    $webIdentity = $resolvedState.WebRecord
    $status = Get-StackStatus -RequestedWebMode $RequestedWebMode
    if ($script:DryRun) {
        return [ordered]@{
            action = 'Stop'
            dryRun = $true
            sessionId = if ($null -ne $state) { $state.sessionId } else { $null }
            statePath = $script:StatePath
            shutdownRequestPath = $script:ShutdownRequestPath
            runtime = [ordered]@{ status = 'managed-by-backend' }
        }
    }

    if ($null -eq $state) {
        if ([string]$status.ownership -eq 'unknown') {
            throw 'STOP_OWNERSHIP_UNKNOWN`nLauncher ownership could not be proven for the detected stack.'
        }

        return $status
    }

    if (
        $resolvedState.BackendResolution.Ownership -eq 'unknown' -or
        $resolvedState.WebResolution.Ownership -eq 'unknown'
    ) {
        throw 'STOP_OWNERSHIP_UNKNOWN`nLauncher ownership could not be proven for the persisted stack.'
    }

    $stopFailed = $false

    if ($null -ne $webIdentity -and $webIdentity.pid) {
        if (-not (Stop-RepoOwnedProcess -Identity $webIdentity)) {
            $stopFailed = $true
        }
    }

    if ($null -ne $backendIdentity -and $backendIdentity.pid) {
        if ($null -ne $persistedState -and $persistedState.sessionId) {
            Request-GracefulBackendShutdown -ControlPath $script:ShutdownRequestPath -SessionId ([string]$persistedState.sessionId)
            if (-not (Wait-ForProcessExit -ProcessId ([int]$backendIdentity.pid) -TimeoutSeconds 20)) {
                if (Stop-RepoOwnedProcess -Identity $backendIdentity) {
                    Write-Output 'graceful shutdown timed out'
                }
                else {
                    $stopFailed = $true
                }
            }
        }
        else {
            if (-not (Stop-RepoOwnedProcess -Identity $backendIdentity)) {
                $stopFailed = $true
            }
        }
    }

    if ($stopFailed) {
        throw 'Stop failed; launcher state was preserved.'
    }

    Remove-LauncherState
    Remove-StaleShutdownRequest
    return (Get-StackStatus -RequestedWebMode $RequestedWebMode)
}

function Invoke-StartLocal {
    $mutexName = Get-LauncherMutexName -RepoRoot $script:RepoRoot -Action $script:Action
    $mutex = Acquire-LauncherMutex -MutexName $mutexName
    try {
        switch ($script:Action) {
            'Start' {
                return Start-BackendStack -WebModeValue $script:WebMode
            }
            'Stop' {
                return Stop-BackendStack -RequestedWebMode $script:WebMode
            }
            'Restart' {
                if ($script:DryRun) {
                    return [ordered]@{
                        action = 'Restart'
                        dryRun = $true
                        stop = [ordered]@{
                            statePath = $script:StatePath
                            shutdownRequestPath = $script:ShutdownRequestPath
                        }
                        start = New-StartDryRunSummary -WebModeValue $script:WebMode
                        runtime = [ordered]@{ status = 'managed-by-backend' }
                    }
                }

                Stop-BackendStack -RequestedWebMode $script:WebMode | Out-Null
                return Start-BackendStack -WebModeValue $script:WebMode
            }
            'Status' {
                return Get-StackStatus -RequestedWebMode $script:WebMode
            }
            default {
                throw "Unsupported action: $($script:Action)"
            }
        }
    }
    finally {
        Release-LauncherMutex -Mutex $mutex
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        $result = Invoke-StartLocal
        if ($null -ne $result) {
            $result | ConvertTo-Json -Depth 8
        }
        exit 0
    }
    catch {
        Write-Error $_
        exit 1
    }
}
