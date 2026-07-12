#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ReleasePath,
    [string]$ZipPath,
    [switch]$MinimizedPath,
    [switch]$SkipLaunch,
    [int]$StartupTimeoutSeconds = 90,
    [int]$RuntimeTestPort = 0,
    [int]$PortConflictTestPort = 0
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$script:Results = @()
$script:ReleaseRoot = [System.IO.Path]::GetFullPath($ReleasePath).TrimEnd('\')
$script:SessionRoot = Join-Path $env:TEMP ("ChatbotTrialVerify\" + [guid]::NewGuid().ToString("N"))
$script:IsolatedReleaseRoot = Join-Path $script:SessionRoot "Release"
$script:UserDataRoot = Join-Path $script:SessionRoot "UserData"
$script:LogRoot = Join-Path $script:SessionRoot "Logs"
$script:ResultPath = Join-Path $script:LogRoot "verify-trial-release-result.json"
$script:ProcessLogPath = Join-Path $script:LogRoot "processes.json"
$script:LauncherProcess = $null
$script:ImmutableBaseline = @{}
$script:VerificationStartedAt = Get-Date
$script:VerificationStartedUtc = $script:VerificationStartedAt.ToUniversalTime().ToString("o")
$script:HttpDiagnostics = @()
$script:LauncherDiagnostics = $null
$script:RuntimeTestPort = 0
$script:PortConflictTestPort = 0
$script:DefaultLauncherPort = 0

function Ensure-Directory([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function FullPath([string]$Path) {
    return [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
}

function Test-UnderRoot([string]$Root, [string]$Path) {
    $rootFull = FullPath $Root
    $pathFull = FullPath $Path
    return ($pathFull.Equals($rootFull, [System.StringComparison]::OrdinalIgnoreCase) -or $pathFull.StartsWith($rootFull + '\', [System.StringComparison]::OrdinalIgnoreCase))
}

function Assert-UnderRoot([string]$Root, [string]$Path, [string]$Message) {
    if (-not (Test-UnderRoot $Root $Path)) { throw "$Message`: $Path" }
}

function RelPath([string]$Path) {
    $full = FullPath $Path
    Assert-UnderRoot $script:ReleaseRoot $full "Path escaped release root"
    if ($full.Equals($script:ReleaseRoot, [System.StringComparison]::OrdinalIgnoreCase)) { return "" }
    return $full.Substring($script:ReleaseRoot.Length + 1).Replace('\', '/')
}

function Sha256([string]$Path) {
    return ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash).ToLowerInvariant()
}

function Read-Json([string]$Path) {
    return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
}

# .NET Framework's ProcessStartInfo has no ArgumentList.  This escaping matches
# the Windows command-line parser rules used by CreateProcess.
function ConvertTo-ProcessArgument {
    param([AllowNull()][AllowEmptyString()][string]$Value)

    if ($null -eq $Value -or $Value.Length -eq 0) { return '""' }
    if ($Value -notmatch '[\s"]') { return $Value }
    return '"' + ($Value -replace '(\\*)"', '$1$1\\"' -replace '(\\+)$', '$1$1') + '"'
}

function Redact-VerificationText([AllowEmptyString()][string]$Text) {
    if ($null -eq $Text) { return "" }
    $result = $Text
    $result = [regex]::Replace($result, '(?im)\b(token|cookie|api[_ -]?key|authorization|password|secret|connector[_ -]?key)\b\s*([:=])\s*[^\s,;\r\n]+', '$1$2[REDACTED]')
    $result = [regex]::Replace($result, '(?im)^(.*)(message|content)(.*)$', '$1$2=[REDACTED]')
    return $result
}

function Write-RedactedText([string]$Path, [AllowEmptyString()][string]$Text) {
    Redact-VerificationText $Text | Set-Content -LiteralPath $Path -Encoding UTF8
    return $Path
}

function Get-ProcessRecord([int]$ProcessId) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $proc) { return $null }
    return [pscustomobject]@{
        pid = [int]$proc.ProcessId
        parentPid = [int]$proc.ParentProcessId
        name = [string]$proc.Name
        executablePath = [string]$proc.ExecutablePath
        commandLine = Redact-VerificationText ([string]$proc.CommandLine)
        creationTime = [string]$proc.CreationDate
    }
}

function Get-ProcessExitCode([int]$ProcessId) {
    try {
        $process = [System.Diagnostics.Process]::GetProcessById($ProcessId)
        if ($process.HasExited) { return $process.ExitCode }
    }
    catch {}
    return $null
}

function ConvertFrom-ProcessCreationTime($CreationTime) {
    if ($null -eq $CreationTime) {
        return $null
    }

    if ($CreationTime -is [datetime]) {
        return [datetime]$CreationTime
    }

    $text = [string]$CreationTime
    if ([string]::IsNullOrWhiteSpace($text)) {
        return $null
    }

    try {
        return [System.Management.ManagementDateTimeConverter]::ToDateTime($text)
    }
    catch {}

    $parsed = [datetime]::MinValue
    if ([datetime]::TryParse($text, [ref]$parsed)) {
        return $parsed
    }

    return $null
}

function Test-ProcessBelongsToSession($Process, [int]$RootProcessId = 0) {
    if ($null -eq $Process) { return $false }
    $commandLine = [string]$Process.commandLine
    $created = ConvertFrom-ProcessCreationTime $Process.creationTime
    $matchesRelease = $commandLine.IndexOf($script:IsolatedReleaseRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -or
        (([string]$Process.executablePath) -and (Test-UnderRoot $script:IsolatedReleaseRoot ([string]$Process.executablePath)))
    $inWindow = $null -ne $created -and $created -ge $script:VerificationStartedAt.AddSeconds(-2)
    $inTree = $RootProcessId -gt 0 -and ([int]$Process.parentPid -eq $RootProcessId -or [int]$Process.pid -eq $RootProcessId)
    return $matchesRelease -and $inWindow -and $inTree
}

function New-StatusObject([string]$Status, [string]$Evidence = "", [string]$LogPath = "", [string]$Message = "") {
    return [pscustomobject]@{ Status = $Status; Evidence = $Evidence; LogPath = $LogPath; Message = $Message }
}

function Add-Result([string]$Name, [ValidateSet("PASS", "FAIL", "UNVERIFIED")][string]$Status, [string]$Evidence, [string]$LogPath, [string]$Message, [double]$DurationSeconds) {
    $script:Results += [pscustomobject]@{
        name = $Name
        status = $Status
        durationSeconds = [Math]::Round($DurationSeconds, 3)
        evidence = $Evidence
        logPath = $LogPath
        message = $Message
    }
}

function Invoke-Check([string]$Name, [scriptblock]$Action) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $value = & $Action
        $sw.Stop()
        if ($null -ne $value -and $value.PSObject.Properties.Name -contains "Status") {
            Add-Result $Name ([string]$value.Status) ([string]$value.Evidence) ([string]$value.LogPath) ([string]$value.Message) $sw.Elapsed.TotalSeconds
        }
        else {
            Add-Result $Name "PASS" ([string]$value) "" "" $sw.Elapsed.TotalSeconds
        }
    }
    catch {
        $sw.Stop()
        Add-Result $Name "FAIL" "" "" $_.Exception.Message $sw.Elapsed.TotalSeconds
    }
}

function Get-LauncherConfig {
    param([string]$LauncherConfigPath = (Join-Path $script:ReleaseRoot "launcher.json"))
    $path = $LauncherConfigPath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "launcher.json is missing" }
    $config = Read-Json $path
    foreach ($key in @("host", "port", "healthPath", "runtimeStatusPath")) {
        if (-not ($config.backend.PSObject.Properties.Name -contains $key)) { throw "launcher.json backend missing $key" }
    }
    return $config
}

function Get-IsolatedLauncherConfigPath {
    return Join-Path $script:IsolatedReleaseRoot "launcher.json"
}

function Get-FreeLoopbackPort([int[]]$ReservedPorts = @()) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    try {
        $listener.Start()
        $candidate = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    }
    finally {
        $listener.Stop()
    }

    if ($ReservedPorts -contains $candidate) {
        throw "Selected loopback port collided with reserved set: $candidate"
    }

    try {
        if (@(Get-NetTCPConnection -LocalPort $candidate -State Listen -ErrorAction SilentlyContinue).Count -gt 0) {
            throw "Loopback port was already listening after selection: $candidate"
        }
    }
    catch [System.Management.Automation.CommandNotFoundException] {}

    return $candidate
}

function Select-VerificationPorts {
    $reserved = @()
    if ($RuntimeTestPort -gt 0) {
        $script:RuntimeTestPort = $RuntimeTestPort
    }
    else {
        $script:RuntimeTestPort = Get-FreeLoopbackPort -ReservedPorts $reserved
    }
    $reserved += $script:RuntimeTestPort

    if ($PortConflictTestPort -gt 0) {
        if ($reserved -contains $PortConflictTestPort) {
            throw "PortConflictTestPort must differ from RuntimeTestPort"
        }
        $script:PortConflictTestPort = $PortConflictTestPort
    }
    else {
        $script:PortConflictTestPort = Get-FreeLoopbackPort -ReservedPorts $reserved
    }

    if ($script:RuntimeTestPort -eq $script:PortConflictTestPort) {
        throw "RuntimeTestPort and PortConflictTestPort must be distinct"
    }

    $selection = [pscustomobject]@{
        defaultLauncherPort = $script:DefaultLauncherPort
        runtimeTestPort = $script:RuntimeTestPort
        portConflictTestPort = $script:PortConflictTestPort
        selectedAtUtc = [DateTime]::UtcNow.ToString("o")
        host = "127.0.0.1"
        reason = "runtime test port and port-conflict test port selected for verifier explicit isolated copy configuration"
    }
    $selection | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $script:LogRoot "port-selection.json") -Encoding UTF8
}

function Initialize-IsolatedRelease {
    Reset-IsolatedRelease
    Ensure-Directory $script:IsolatedReleaseRoot
    Ensure-Directory $script:UserDataRoot
    $null = & robocopy $script:ReleaseRoot $script:IsolatedReleaseRoot /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP
    if ($LASTEXITCODE -ge 8) {
        throw "Failed to copy release into isolated verifier session: $script:ReleaseRoot -> $script:IsolatedReleaseRoot"
    }

    $originalLauncherPath = Join-Path $script:ReleaseRoot "launcher.json"
    $isolatedLauncherPath = Get-IsolatedLauncherConfigPath
    Copy-Item -LiteralPath $originalLauncherPath -Destination (Join-Path $script:LogRoot "launcher.original.json") -Force
    Update-IsolatedLauncherConfig -Port $script:RuntimeTestPort
}

function Reset-IsolatedRelease {
    if (Test-Path -LiteralPath $script:IsolatedReleaseRoot) {
        Remove-Item -LiteralPath $script:IsolatedReleaseRoot -Recurse -Force -ErrorAction Stop
    }
    if (Test-Path -LiteralPath $script:UserDataRoot) {
        Remove-Item -LiteralPath $script:UserDataRoot -Recurse -Force -ErrorAction Stop
    }
}

function Update-IsolatedLauncherConfig([int]$Port) {
    $isolatedLauncherPath = Get-IsolatedLauncherConfigPath
    $config = Get-LauncherConfig -LauncherConfigPath $isolatedLauncherPath
    $config.backend.host = "127.0.0.1"
    $config.backend.port = $Port
    $config.backend.startupTimeoutSeconds = [Math]::Max([int]$config.backend.startupTimeoutSeconds, 120)
    $config | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $isolatedLauncherPath -Encoding UTF8
    Copy-Item -LiteralPath $isolatedLauncherPath -Destination (Join-Path $script:LogRoot "isolated-launcher.json") -Force
    Update-IsolatedLauncherManifest -LauncherConfigPath $isolatedLauncherPath
}

function Update-IsolatedLauncherManifest([string]$LauncherConfigPath) {
    $manifestPath = Join-Path $script:IsolatedReleaseRoot "manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Isolated release is missing manifest.json: $manifestPath"
    }

    $manifest = Read-Json $manifestPath
    $launcherEntry = @($manifest.entries | Where-Object { $_.path -eq "launcher.json" } | Select-Object -First 1)
    if ($launcherEntry.Count -eq 0) {
        throw "Isolated release manifest is missing launcher.json entry."
    }

    $launcherSize = (Get-Item -LiteralPath $LauncherConfigPath).Length
    $launcherSha256 = Sha256 $LauncherConfigPath
    $launcherEntry[0].size = $launcherSize
    $launcherEntry[0].sha256 = $launcherSha256
    $manifest | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $script:LogRoot "isolated-manifest.json") -Force
}

function Get-MinimizedPathValue([string]$RuntimeReleaseRoot = $script:IsolatedReleaseRoot) {
    $windowsRoot = $env:SystemRoot
    if ([string]::IsNullOrWhiteSpace($windowsRoot)) { $windowsRoot = "C:\Windows" }
    $parts = @(
        (Join-Path $windowsRoot "System32"),
        $windowsRoot,
        (Join-Path $windowsRoot "System32\WindowsPowerShell\v1.0"),
        (Join-Path $RuntimeReleaseRoot "server\runtime\python"),
        (Join-Path $RuntimeReleaseRoot "connectors\runtime\python"),
        (Join-Path $RuntimeReleaseRoot "runtime\desktop-rpa"),
        $RuntimeReleaseRoot
    )
    $existing = @()
    foreach ($part in $parts) { if ($part -and (Test-Path -LiteralPath $part -PathType Container)) { $existing += (FullPath $part) } }
    return (($existing | Select-Object -Unique) -join ";")
}

function Assert-MinimizedPathSafe([string]$PathValue, [string]$RuntimeReleaseRoot = $script:IsolatedReleaseRoot) {
    foreach ($segment in ($PathValue -split ";")) {
        if ([string]::IsNullOrWhiteSpace($segment)) { continue }
        $insideRelease = Test-UnderRoot $RuntimeReleaseRoot $segment
        if (-not $insideRelease -and $segment -match '(?i)(Python|nodejs|\bnpm\b|pnpm|Git|\buv\b)') {
            throw "Minimized PATH contains a development tool segment: $segment"
        }
    }
}

function Get-ControlledProcesses([int[]]$ProcessIds = @()) {
    $all = @(Get-CimInstance Win32_Process)
    if ($ProcessIds.Count -gt 0) {
        $queue = New-Object System.Collections.Queue
        foreach ($id in $ProcessIds) { $queue.Enqueue([int]$id) }
        $seen = @{}
        $selected = @()
        while ($queue.Count -gt 0) {
            $processIdToInspect = [int]$queue.Dequeue()
            if ($seen.ContainsKey($processIdToInspect)) { continue }
            $seen[$processIdToInspect] = $true
            foreach ($proc in ($all | Where-Object { $_.ProcessId -eq $processIdToInspect })) { $selected += $proc }
            foreach ($child in ($all | Where-Object { $_.ParentProcessId -eq $processIdToInspect })) { $queue.Enqueue([int]$child.ProcessId) }
        }
    }
    else {
        $selected = $all | Where-Object {
            ($_.ExecutablePath -and (Test-UnderRoot $script:IsolatedReleaseRoot $_.ExecutablePath)) -or
            ($_.CommandLine -and $_.CommandLine.IndexOf($script:IsolatedReleaseRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
        }
    }
    return @($selected | Select-Object @{n="pid";e={$_.ProcessId}}, @{n="parentPid";e={$_.ParentProcessId}}, @{n="name";e={$_.Name}}, @{n="executablePath";e={$_.ExecutablePath}}, @{n="commandLine";e={$_.CommandLine}}, @{n="creationTime";e={$_.CreationDate}})
}

function Write-ProcessEvidence([object[]]$Processes, [string]$Name = "processes") {
    $path = if ($Name -eq "processes") { $script:ProcessLogPath } else { Join-Path $script:LogRoot ($Name + ".json") }
    $Processes | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $path -Encoding UTF8
    return $path
}

function Get-ReleaseFileSnapshot {
    $snapshot = @{}
    foreach ($file in Get-ChildItem -LiteralPath $script:ReleaseRoot -Force -File -Recurse -ErrorAction SilentlyContinue) {
        $relative = RelPath $file.FullName
        $snapshot[$relative] = [pscustomobject]@{
            size = $file.Length
            sha256 = Sha256 $file.FullName
        }
    }
    return $snapshot
}

function Compare-ReleaseSnapshots($Baseline, $Current) {
    $added = @()
    $removed = @()
    $modified = @()
    foreach ($path in $Baseline.Keys) {
        if (-not $Current.ContainsKey($path)) {
            $removed += $path
            continue
        }
        if ($Baseline[$path].sha256 -ne $Current[$path].sha256) {
            $modified += $path
        }
    }
    foreach ($path in $Current.Keys) {
        if (-not $Baseline.ContainsKey($path)) {
            $added += $path
        }
    }
    return [pscustomobject]@{
        Added = @($added | Sort-Object)
        Removed = @($removed | Sort-Object)
        Modified = @($modified | Sort-Object)
    }
}

function Assert-NoForbiddenTools([object[]]$Processes) {
    foreach ($proc in $Processes) {
        $name = [string]$proc.name
        $path = [string]$proc.executablePath
        if ($name -match '^(python|pythonw)\.exe$') {
            $serverRuntime = Join-Path $script:IsolatedReleaseRoot "server\runtime"
            $connectorRuntime = Join-Path $script:IsolatedReleaseRoot "connectors\runtime"
            if (-not (Test-UnderRoot $serverRuntime $path) -and -not (Test-UnderRoot $connectorRuntime $path)) { throw "Python process is outside packaged runtimes: pid=$($proc.pid) path=$path" }
        }
        if ($name -match '^node\.exe$') { throw "System node.exe was used: pid=$($proc.pid) path=$path" }
        if ($name -match '^(uv|pnpm|git)\.exe$') { throw "Development tool process was used: pid=$($proc.pid) path=$path" }
    }
}

function Stop-ControlledProcesses([string]$Reason = "verify-cleanup") {
    $shutdownPath = Join-Path $script:UserDataRoot "runtime\backend-shutdown.json"
    Ensure-Directory (Split-Path -Parent $shutdownPath)
    @{ action = "shutdown"; reason = $Reason; requestedAtUtc = [DateTime]::UtcNow.ToString("o") } | ConvertTo-Json | Set-Content -LiteralPath $shutdownPath -Encoding UTF8
    Start-Sleep -Seconds 5
    if ($script:LauncherProcess) {
        $launcherRecord = Get-ProcessRecord $script:LauncherProcess.Id
        if ($launcherRecord -and (Test-ProcessBelongsToSession $launcherRecord $script:LauncherProcess.Id)) {
            try {
                $live = [System.Diagnostics.Process]::GetProcessById($script:LauncherProcess.Id)
                if (-not $live.HasExited) { $live.CloseMainWindow() | Out-Null }
            }
            catch {}
        }
    }
    Start-Sleep -Seconds 1
    if ($script:LauncherProcess) {
        $launcherRecord = Get-ProcessRecord $script:LauncherProcess.Id
        if ($launcherRecord -and (Test-ProcessBelongsToSession $launcherRecord $script:LauncherProcess.Id)) {
            try {
                $live = [System.Diagnostics.Process]::GetProcessById($script:LauncherProcess.Id)
                if (-not $live.HasExited) { Stop-Process -Id $live.Id -Force -ErrorAction Stop }
            }
            catch {}
        }
    }
    Stop-RemainingControlledProcesses -Reason $Reason
}

function Stop-RemainingControlledProcesses([string]$Reason = "verify-cleanup") {
    $deadline = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $deadline) {
        if (@(Get-ControlledProcesses).Count -eq 0) {
            return
        }
        Start-Sleep -Milliseconds 500
    }

    $remaining = @(Get-ControlledProcesses)
    if ($remaining.Count -eq 0) {
        return
    }

    $evidencePath = Write-ProcessEvidence $remaining "process-snapshot-cleanup-force"
    foreach ($proc in $remaining) {
        try {
            $null = & taskkill.exe /PID ([int]$proc.pid) /T /F
        }
        catch {}
    }

    $afterDeadline = (Get-Date).AddSeconds(5)
    while ((Get-Date) -lt $afterDeadline) {
        if (@(Get-ControlledProcesses).Count -eq 0) {
            return
        }
        Start-Sleep -Milliseconds 500
    }

    $stillRunning = @(Get-ControlledProcesses)
    if ($stillRunning.Count -gt 0) {
        $stillRunningPath = Write-ProcessEvidence $stillRunning "process-snapshot-cleanup-still-running"
        throw "Controlled processes remained after cleanup; reason=$Reason; forceEvidence=$evidencePath; remainingEvidence=$stillRunningPath"
    }
}

function Wait-Http([string]$Uri, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $last = $null
    while ((Get-Date) -lt $deadline) {
        try { return Invoke-RestMethod -Uri $Uri -TimeoutSec 3 }
        catch {
            $responseStatus = $null
            $responseBody = ""
            try {
                if ($_.Exception.Response) {
                    $responseStatus = [int]$_.Exception.Response.StatusCode
                    $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
                    try { $responseBody = $reader.ReadToEnd() } finally { $reader.Dispose() }
                }
            }
            catch {}
            $last = [pscustomobject]@{
                url = $Uri
                timestampUtc = [DateTime]::UtcNow.ToString("o")
                exceptionType = $_.Exception.GetType().FullName
                httpStatus = $responseStatus
                responseSnippet = (Redact-VerificationText $responseBody).Substring(0, [Math]::Min(500, (Redact-VerificationText $responseBody).Length))
                message = Redact-VerificationText $_.Exception.Message
                launcherAlive = $script:LauncherProcess -and -not $script:LauncherProcess.HasExited
            }
            $script:HttpDiagnostics += $last
            Start-Sleep -Milliseconds 500
        }
    }
    throw "Timed out waiting for $Uri. Last error: $($last.message)"
}

function Get-LauncherStateEvidence([string]$UserData) {
    $statePath = Join-Path $UserData "runtime\launcher-state.json"
    $evidence = [ordered]@{
        path = $statePath
        exists = (Test-Path -LiteralPath $statePath -PathType Leaf)
        parseable = $false
        schemaValid = $false
        schemaError = ""
        backend = $null
    }
    if ($evidence.exists) {
        try {
            $state = Read-Json $statePath
            $evidence.parseable = $true
            if ($state.PSObject.Properties.Name -notcontains "backend") {
                $evidence.schemaError = "LAUNCHER_STATE_SCHEMA_INVALID"
            }
            elseif ($null -eq $state.backend) {
                $evidence.schemaValid = $true
            }
            else {
                $backend = $state.backend
                $required = @("pid", "processCreateTimeUtc", "executablePath", "sessionId")
                $missing = @($required | Where-Object { $backend.PSObject.Properties.Name -notcontains $_ -or [string]::IsNullOrWhiteSpace([string]$backend.$_) })
                if ($missing.Count -gt 0) {
                    $evidence.schemaError = "LAUNCHER_STATE_SCHEMA_INVALID"
                    $evidence.missingFields = @($missing | ForEach-Object { "backend.$_" })
                }
                else {
                    $evidence.schemaValid = $true
                    $evidence.backend = [pscustomobject]@{
                        pid = [int]$backend.pid
                        processCreateTimeUtc = [string]$backend.processCreateTimeUtc
                        executablePath = [string]$backend.executablePath
                        sessionId = [string]$backend.sessionId
                    }
                }
            }
            Copy-Item -LiteralPath $statePath -Destination (Join-Path $script:LogRoot "launcher-state-copy.json") -Force
        }
        catch { $evidence.parseError = Redact-VerificationText $_.Exception.Message }
    }
    return [pscustomobject]$evidence
}

function Get-PortEvidence([int]$Port, [int]$LauncherPid) {
    $items = @()
    try {
        $controlled = @(Get-ControlledProcesses @($LauncherPid) | ForEach-Object { [int]$_.pid })
        foreach ($connection in @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)) {
            $record = Get-ProcessRecord ([int]$connection.OwningProcess)
            $items += [pscustomobject]@{
                port = $Port
                pid = [int]$connection.OwningProcess
                localAddress = [string]$connection.LocalAddress
                executablePath = if ($record) { $record.executablePath } else { "" }
                commandLine = if ($record) { $record.commandLine } else { "" }
                isCurrentSession = $controlled -contains [int]$connection.OwningProcess
            }
        }
    }
    catch [System.Management.Automation.CommandNotFoundException] {}
    return @($items)
}

function Copy-LauncherDiagnostics([string]$UserData) {
    $files = @{
        "launcher.log" = Join-Path $UserData "logs\launcher.log"
        "backend.stdout.log" = Join-Path $UserData "logs\backend.stdout.log"
        "backend.stderr.log" = Join-Path $UserData "logs\backend.stderr.log"
        "backend.log" = Join-Path $UserData "logs\backend.log"
        "runtime.log" = Join-Path $UserData "runtime\runtime.log"
    }
    foreach ($name in $files.Keys) {
        $target = Join-Path $script:LogRoot $name
        if (Test-Path -LiteralPath $files[$name] -PathType Leaf) {
            Write-RedactedText $target (Get-Content -LiteralPath $files[$name] -Raw -ErrorAction SilentlyContinue) | Out-Null
        }
        elseif (-not (Test-Path -LiteralPath $target -PathType Leaf)) { Set-Content -LiteralPath $target -Value "" -Encoding UTF8 }
    }
}

function Capture-LauncherOutput {
    if ($null -eq $script:LauncherProcess) { return }
    $stdout = Join-Path $script:LogRoot "launcher.stdout.log"
    $stderr = Join-Path $script:LogRoot "launcher.stderr.log"
    try {
        if ($script:LauncherProcess.HasExited) {
            Write-RedactedText $stdout $script:LauncherProcess.StandardOutput.ReadToEnd() | Out-Null
            Write-RedactedText $stderr $script:LauncherProcess.StandardError.ReadToEnd() | Out-Null
        }
    }
    catch {}
    foreach ($path in @($stdout, $stderr)) { if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { Set-Content -LiteralPath $path -Value "" -Encoding UTF8 } }
}

function Capture-ProcessOutput($Process, [string]$StdoutPath, [string]$StderrPath) {
    if ($null -eq $Process) { return }
    try {
        Write-RedactedText $StdoutPath $Process.StandardOutput.ReadToEnd() | Out-Null
        Write-RedactedText $StderrPath $Process.StandardError.ReadToEnd() | Out-Null
    }
    catch {}
    foreach ($path in @($StdoutPath, $StderrPath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            Set-Content -LiteralPath $path -Value "" -Encoding UTF8
        }
    }
}

function Test-LauncherPortAvailability([int]$Port, [int]$TimeoutSeconds = 30, [string]$StageName = "launcher-port-check") {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $listeners = @(Get-PortEvidence $Port $(if ($script:LauncherProcess) { $script:LauncherProcess.Id } else { 0 }))
        $launcherAlive = $false
        if ($script:LauncherProcess) {
            try { $launcherAlive = -not $script:LauncherProcess.HasExited } catch { $launcherAlive = $false }
        }
        if (-not $launcherAlive -and $listeners.Count -eq 0) {
            return "stage=$StageName; port=$Port; listeners=0; launcherAlive=false"
        }
        Start-Sleep -Milliseconds 500
    }

    $diagnosticPath = Join-Path $script:LogRoot ("$StageName-port-snapshot.json")
    @(Get-PortEvidence $Port $(if ($script:LauncherProcess) { $script:LauncherProcess.Id } else { 0 })) |
        ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath $diagnosticPath -Encoding UTF8
    throw "Timed out waiting for port $Port to become available after $StageName. Diagnostics: $diagnosticPath"
}

function Get-HealthFailureClassification([string]$UserData, [int]$Port) {
    if ($null -eq $script:LauncherProcess) { return "LAUNCHER_NOT_STARTED" }
    if ($script:LauncherProcess.HasExited) { return "LAUNCHER_EXITED_EARLY" }
    $state = Get-LauncherStateEvidence $UserData
    if (-not $state.parseable -or -not $state.schemaValid) { return "LAUNCHER_STATE_SCHEMA_INVALID" }
    if ($null -eq $state.backend) { return "BACKEND_NOT_CREATED" }
    $backend = Get-ProcessRecord ([int]$state.backend.pid)
    if ($null -eq $backend) { return "BACKEND_EXITED_EARLY" }
    $listeners = @(Get-PortEvidence $Port $script:LauncherProcess.Id)
    if ($listeners.Count -eq 0) { return "PORT_NOT_LISTENING" }
    if (@($listeners | Where-Object { -not $_.isCurrentSession }).Count -gt 0) { return "PORT_OWNED_BY_OTHER_PROCESS" }
    if ($script:HttpDiagnostics.Count -gt 0 -and @($script:HttpDiagnostics | Where-Object { $null -ne $_.httpStatus }).Count -gt 0) { return "HEALTH_HTTP_ERROR" }
    return "BACKEND_HEALTH_TIMEOUT"
}

function Write-LauncherFailureDiagnostics([string]$UserData, [int]$Port, [string]$Failure) {
    $launcher = if ($script:LauncherProcess) { Get-ProcessRecord $script:LauncherProcess.Id } else { $null }
    $state = Get-LauncherStateEvidence $UserData
    $backend = if ($state.backend) { Get-ProcessRecord ([int]$state.backend.pid) } else { $null }
    $rpa = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.ExecutablePath -and (Test-UnderRoot (Join-Path $script:IsolatedReleaseRoot "runtime\desktop-rpa") $_.ExecutablePath) } | ForEach-Object { Get-ProcessRecord ([int]$_.ProcessId) })
    $ports5302 = Get-PortEvidence $Port $(if ($script:LauncherProcess) { $script:LauncherProcess.Id } else { 0 })
    $ports3000 = Get-PortEvidence 3000 $(if ($script:LauncherProcess) { $script:LauncherProcess.Id } else { 0 })
    $snapshot = [pscustomobject]@{ failure = $Failure; launcher = $launcher; backend = $backend; rpa = $rpa; state = $state; http = $script:HttpDiagnostics; port5302 = $ports5302; port3000 = $ports3000 }
    $snapshot | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $script:LogRoot "process-snapshot-failure.json") -Encoding UTF8
    [pscustomobject]@{ port5302 = $ports5302; port3000 = $ports3000 } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $script:LogRoot "port-snapshot.json") -Encoding UTF8
    Copy-LauncherDiagnostics $UserData
    return (Join-Path $script:LogRoot "process-snapshot-failure.json")
}

function Test-PortableStructure {
    $required = @(
        "ChatbotLauncher.exe", "launcher.json", "manifest.json",
        "server\runtime", "server\app", "connectors\runtime", "connectors\app\wechat-decrypt",
        "resources\web\dist\index.html", "resources\templates", "resources\migrations", "resources\defaults",
        "runtime\desktop-rpa", "licenses", "prerequisites"
    )
    $missing = @()
    foreach ($relative in $required) { if (-not (Test-Path -LiteralPath (Join-Path $script:ReleaseRoot $relative))) { $missing += $relative } }
    if ($missing.Count -gt 0) { throw "Missing required portable paths: $($missing -join ', ')" }
    return "Required portable paths are present."
}

function Test-LauncherConfiguration {
    $config = Get-LauncherConfig
    $script:DefaultLauncherPort = [int]$config.backend.port
    if ([string]$config.backend.host -ne "127.0.0.1") { throw "launcher host must be 127.0.0.1" }
    if ([int]$config.backend.port -ne 5302) { throw "launcher default port must be 5302" }
    return "host=$($config.backend.host); port=$($config.backend.port); healthPath=$($config.backend.healthPath); runtimeStatusPath=$($config.backend.runtimeStatusPath)"
}

function Test-Manifest {
    $manifest = Read-Json (Join-Path $script:ReleaseRoot "manifest.json")
    if ([int]$manifest.schemaVersion -ne 1) { throw "Unexpected manifest schemaVersion: $($manifest.schemaVersion)" }
    $entries = @($manifest.entries)
    if ($entries.Count -eq 0) { throw "manifest contains no entries" }
    $critical = @($entries | Where-Object { $_.critical -eq $true })
    if ($critical.Count -eq 0) { throw "manifest contains no critical entries" }
    foreach ($requiredEntry in @("ChatbotLauncher.exe", "launcher.json")) {
        if (@($entries | Where-Object { $_.path -eq $requiredEntry }).Count -ne 1) {
            throw "manifest must contain exactly one $requiredEntry entry"
        }
    }
    foreach ($entry in $entries) {
        $relative = ([string]$entry.path).Replace('/', '\')
        if ([System.IO.Path]::IsPathRooted($relative) -or $relative -match '(^|\\)\.\.(\\|$)') { throw "Unsafe manifest path: $($entry.path)" }
        $path = Join-Path $script:ReleaseRoot $relative
        Assert-UnderRoot $script:ReleaseRoot $path "Manifest entry escaped release root"
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Manifest file is missing: $($entry.path)" }
        if ([int64](Get-Item -LiteralPath $path).Length -ne [int64]$entry.size) { throw "Manifest size mismatch: $($entry.path)" }
        if ($entry.critical -eq $true -and (Sha256 $path) -ne ([string]$entry.sha256).ToLowerInvariant()) { throw "Critical manifest hash mismatch: $($entry.path)" }
    }
    $evidence = "version=$($manifest.version); criticalHashes=$($critical.Count)"
    if (($manifest.PSObject.Properties.Name -notcontains "product") -or ($manifest.PSObject.Properties.Name -notcontains "architecture")) {
        return New-StatusObject "UNVERIFIED" $evidence "" "manifest lacks explicit product/architecture fields; critical hashes were verified."
    }
    return $evidence
}

function Test-Sha256Sums {
    $sumsPath = Join-Path $script:ReleaseRoot "SHA256SUMS.txt"
    if (-not (Test-Path -LiteralPath $sumsPath -PathType Leaf)) { throw "SHA256SUMS.txt is missing" }
    $checked = 0
    foreach ($line in (Get-Content -LiteralPath $sumsPath -Encoding UTF8)) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($line -notmatch '^([0-9A-Fa-f]{64})\s+\*?(.+)$') { throw "Invalid SHA256SUMS line: $line" }
        $expected = $matches[1].ToLowerInvariant()
        $relative = $matches[2].Trim().Replace('/', '\')
        if ([System.IO.Path]::IsPathRooted($relative) -or $relative -match '(^|\\)\.\.(\\|$)') { throw "Unsafe SHA256SUMS path: $relative" }
        $path = Join-Path $script:ReleaseRoot $relative
        Assert-UnderRoot $script:ReleaseRoot $path "SHA256SUMS entry escaped release root"
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "SHA256SUMS file is missing: $relative" }
        if ((Sha256 $path) -ne $expected) { throw "SHA256SUMS hash mismatch: $relative" }
        $checked++
    }
    if ($ZipPath) {
        $zipFull = FullPath $ZipPath
        if (-not (Test-Path -LiteralPath $zipFull -PathType Leaf)) { throw "ZipPath does not exist: $zipFull" }
        $zipHash = Sha256 $zipFull
        $zipSha256Path = $zipFull + '.sha256'
        if (-not (Test-Path -LiteralPath $zipSha256Path -PathType Leaf)) { throw "ZIP checksum sidecar is missing: $zipSha256Path" }
        $sidecarText = Get-Content -LiteralPath $zipSha256Path -Raw -Encoding ASCII
        if ($sidecarText -notmatch '^\s*([0-9A-Fa-f]{64})\s+(.+?)\s*$') { throw "ZIP checksum sidecar has invalid format: $zipSha256Path" }
        $expectedZipHash = $matches[1].ToLowerInvariant()
        if ($zipHash -ne $expectedZipHash) { throw "ZIP checksum mismatch: expected $expectedZipHash, got $zipHash" }
        return "files=$checked; zipSha256=$zipHash; zipSha256Path=$zipSha256Path"
    }
    return "files=$checked"
}

function Test-ZipContents {
    if (-not $ZipPath) { return "ZipPath was not provided; direct portable layout is the verification target." }
    $zipFull = FullPath $ZipPath
    if (-not (Test-Path -LiteralPath $zipFull -PathType Leaf)) { throw "ZipPath does not exist: $zipFull" }
    $rawNames = @(& tar -tf $zipFull 2>$null)
    $tarExitCode = $LASTEXITCODE
    if ($tarExitCode -gt 1) {
        throw "Failed to enumerate ZIP contents with tar.exe (exit code $tarExitCode): $zipFull"
    }

    $names = @($rawNames | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object {
        $_.Trim().TrimEnd('/').Replace('/', '\')
    })
    if ($names.Count -eq 0) {
        throw "ZIP contained no readable entries: $zipFull"
    }

    $root = Split-Path -Leaf $script:ReleaseRoot
    foreach ($relative in @("ChatbotLauncher.exe", "launcher.json", "manifest.json", "resources\web\dist\index.html")) {
        $expected = $root + "\" + $relative
        if (-not ($names -contains $expected)) { throw "ZIP missing entry: $expected" }
    }

    return "zipEntries=$($names.Count); tarExitCode=$tarExitCode"
}

function Test-SensitiveScan {
    $path = Join-Path $script:ReleaseRoot "build-sensitive-scan.json"
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        return "PortableOnly release has no sensitive scan artifact; forbidden-content and manifest checks remain required."
    }
    $scan = Read-Json $path
    if ($null -eq $scan.summary) { throw "sensitive scan summary missing" }
    if ($scan.summary.blocked -eq $true) { throw "sensitive scan is blocked" }
    $findings = @($scan.findings)
    $high = @($findings | Where-Object { (([string]$_.severity).ToLowerInvariant() -eq "high" -or ([string]$_.severity).ToLowerInvariant() -eq "critical") -and $_.allowed -ne $true })
    if ($high.Count -gt 0) { throw "sensitive scan contains unresolved high-risk findings" }
    $rendered = Get-Content -LiteralPath $path -Raw -Encoding UTF8
    if ($rendered -match '(?i)(token|password|secret|authorization)["''\s:=]+[A-Za-z0-9_\-]{20,}') { throw "sensitive scan appears to contain a full secret value" }
    return "blocked=false; findings=$($findings.Count)"
}

function Test-ForbiddenContent {
    $bad = @()
    foreach ($dirName in @(".git", ".venv")) {
        $bad += @(Get-ChildItem -LiteralPath $script:ReleaseRoot -Force -Directory -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq $dirName } | ForEach-Object { RelPath $_.FullName })
    }
    foreach ($pattern in @("*.db", "*.sqlite", "*.sqlite3", "*.pyc", "*.pyo", "*.pdb", "*.map")) {
        $bad += @(Get-ChildItem -LiteralPath $script:ReleaseRoot -Force -File -Recurse -Filter $pattern -ErrorAction SilentlyContinue | ForEach-Object { RelPath $_.FullName })
    }
    $bad += @(Get-ChildItem -LiteralPath $script:ReleaseRoot -Force -Directory -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq "__pycache__" } | ForEach-Object { RelPath $_.FullName })
    $bad += @(Get-ChildItem -LiteralPath $script:ReleaseRoot -Force -File -Recurse -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -eq 'direct_url.json' -or ($_.Name -eq 'RECORD' -and $_.DirectoryName -match '\\.dist-info(\\|$)')
    } | ForEach-Object { RelPath $_.FullName })
    $bad += @(Get-ChildItem -LiteralPath $script:ReleaseRoot -Force -Recurse -ErrorAction SilentlyContinue | Where-Object {
        $rel = (RelPath $_.FullName)
        $rel -match '(?i)(^logs(/|$)|launcher-state\.json|runtime-state|WeChat Files|Desktop backup)'
    } | ForEach-Object { RelPath $_.FullName })
    if ($bad.Count -gt 0) { $sample = (($bad | Select-Object -First 20) -join ', '); throw "Forbidden release content found: $sample" }
    return "No forbidden content detected."
}

function Test-SafetyDefaults {
    $required = @(
        "LANGBOT_BROADCAST_SEND_ENABLED",
        "LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS",
        "LANGBOT_RPA_ALLOW_AUTO_SEND",
        "LANGBOT_RPA_FORCE_DISABLE_SEND",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONUTF8",
        "PYTHONIOENCODING"
    )
    $repoRoot = FullPath (Join-Path (Split-Path -Parent $script:ReleaseRoot) "..\..")
    $source = Join-Path $repoRoot "packaging\launcher\ChatbotLauncher\LauncherProcessManager.cs"
    if (Test-Path -LiteralPath $source -PathType Leaf) {
        $text = Get-Content -LiteralPath $source -Raw -Encoding UTF8
        $missing = @($required | Where-Object { $text -notmatch [regex]::Escape($_) })
        if ($missing.Count -gt 0) { throw "Launcher source missing safety env defaults: $($missing -join ', ')" }
        return "Launcher source sets real-send defaults closed."
    }
    return New-StatusObject "UNVERIFIED" "binary launcher present" "" "Runtime verification is required to prove real-send defaults."
}

function Invoke-ConnectorSmoke {
    $python = Join-Path $script:IsolatedReleaseRoot "connectors\runtime\python\python.exe"
    $appDir = Join-Path $script:IsolatedReleaseRoot "connectors\app\wechat-decrypt"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "connector python missing" }
    Assert-UnderRoot (Join-Path $script:IsolatedReleaseRoot "connectors\runtime") $python "Connector python escaped runtime"
    if (-not (Test-Path -LiteralPath (Join-Path $appDir "connector_runtime.py") -PathType Leaf)) { throw "connector_runtime.py missing" }
    $stdout = Join-Path $script:LogRoot "connector-smoke.stdout.log"
    $stderr = Join-Path $script:LogRoot "connector-smoke.stderr.log"
    $smokeScript = Join-Path $script:LogRoot "connector-smoke.py"
    @"
import json
import os
import pathlib
import sys
sys.path.insert(0, r'''$appDir''')
import connector_runtime
print(json.dumps({
    'ok': True,
    'action': 'smoke',
    'executable': sys.executable,
    'module': str(pathlib.Path(connector_runtime.__file__).resolve()),
    'pythondontwritebytecode': os.environ.get('PYTHONDONTWRITEBYTECODE', ''),
    'pythonutf8': os.environ.get('PYTHONUTF8', ''),
    'pythonioencoding': os.environ.get('PYTHONIOENCODING', ''),
}, ensure_ascii=False))
"@ | Set-Content -LiteralPath $smokeScript -Encoding UTF8
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $python
    $psi.WorkingDirectory = $appDir
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $processArguments = @("-X", "utf8", $smokeScript)
    $psi.Arguments = ($processArguments | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' '
    $psi.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1"
    $psi.EnvironmentVariables["PYTHONUTF8"] = "1"
    $psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"
    $proc = [System.Diagnostics.Process]::Start($psi)
    if (-not $proc.WaitForExit(120000)) {
        $record = Get-ProcessRecord $proc.Id
        if ($record -and (Test-UnderRoot (Join-Path $script:ReleaseRoot "connectors\runtime") ([string]$record.executablePath))) {
            try { Stop-Process -Id $proc.Id -Force -ErrorAction Stop } catch {}
        }
        Write-RedactedText $stdout $proc.StandardOutput.ReadToEnd() | Out-Null
        Write-RedactedText $stderr $proc.StandardError.ReadToEnd() | Out-Null
        throw "connector smoke process timed out: pid=$($proc.Id); executable=$python; stdout=$stdout; stderr=$stderr"
    }
    Write-RedactedText $stdout $proc.StandardOutput.ReadToEnd() | Out-Null
    Write-RedactedText $stderr $proc.StandardError.ReadToEnd() | Out-Null
    $proc.Refresh()
    if ($null -eq $proc.ExitCode) { $proc.WaitForExit(); $proc.Refresh() }
    $exitCode = $proc.ExitCode
    if ($null -eq $exitCode -and (Test-Path -LiteralPath $stdout -PathType Leaf) -and ((Get-Item -LiteralPath $stdout).Length -gt 0)) { $exitCode = 0 }
    if ($exitCode -ne 0) { $err = Get-Content -LiteralPath $stderr -Raw -ErrorAction SilentlyContinue; throw "connector smoke failed with exit code $exitCode; executable=$python; stdout=$stdout; stderr=$stderr; error=$err" }
    $payload = Read-Json $stdout
    if ($payload.ok -ne $true) { throw "connector smoke payload was not ok" }
    if (-not (Test-UnderRoot (Join-Path $script:IsolatedReleaseRoot "connectors\runtime") ([string]$payload.executable))) { throw "connector smoke used python outside connector runtime: $($payload.executable)" }
    if (-not (Test-UnderRoot $appDir ([string]$payload.module))) { throw "connector smoke imported module outside connector app: $($payload.module)" }
    if ([string]$payload.pythondontwritebytecode -ne "1") { throw "connector smoke did not inherit PYTHONDONTWRITEBYTECODE=1" }
    if ([string]$payload.pythonutf8 -ne "1") { throw "connector smoke did not inherit PYTHONUTF8=1" }
    if ([string]$payload.pythonioencoding -ne "utf-8") { throw "connector smoke did not inherit PYTHONIOENCODING=utf-8" }
    return New-StatusObject "PASS" "pid=$($proc.Id); executable=$($payload.executable); module=$($payload.module); pythondontwritebytecode=$($payload.pythondontwritebytecode)" $stdout ""
}

function Test-PackagedServerImports {
    $python = Join-Path $script:ReleaseRoot "server\runtime\python\python.exe"
    $entrypoint = Join-Path $script:ReleaseRoot "server\app\packaging\server\entrypoint.py"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "server packaged python is missing" }
    if (-not (Test-Path -LiteralPath $entrypoint -PathType Leaf)) { throw "server entrypoint is missing" }
    Assert-UnderRoot (Join-Path $script:ReleaseRoot "server\runtime") $python "Server python escaped release runtime"
    Assert-UnderRoot (Join-Path $script:ReleaseRoot "server\app") $entrypoint "Server entrypoint escaped release app"

    $stdout = Join-Path $script:LogRoot "server-imports.stdout.log"
    $stderr = Join-Path $script:LogRoot "server-imports.stderr.log"
    $smokeScript = Join-Path $script:LogRoot "server-imports.py"
    @"
import importlib
import importlib.util
import json
import pathlib
import sys

entrypoint_path = pathlib.Path(r'''$entrypoint''').resolve()
spec = importlib.util.spec_from_file_location('packaged_entrypoint_smoke', entrypoint_path)
if spec is None or spec.loader is None:
    raise RuntimeError('unable to load packaged backend entrypoint')
entrypoint = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = entrypoint
spec.loader.exec_module(entrypoint)
lark = importlib.import_module('lark_oapi')
corehr = importlib.import_module('lark_oapi.api.corehr.v2')
try:
    importlib.import_module('lark_oapi.api.core.hr')
except ModuleNotFoundError:
    legacy_core_hr_available = False
else:
    legacy_core_hr_available = True
print(json.dumps({
    'ok': True,
    'python': str(pathlib.Path(sys.executable).resolve()),
    'entrypoint': str(entrypoint_path),
    'lark': str(pathlib.Path(lark.__file__).resolve()),
    'corehr': str(pathlib.Path(corehr.__file__).resolve()),
    'legacy_core_hr_available': legacy_core_hr_available,
}, ensure_ascii=False))
"@ | Set-Content -LiteralPath $smokeScript -Encoding UTF8
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $python
    $psi.WorkingDirectory = $script:ReleaseRoot
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.Arguments = (@("-B", "-X", "utf8", $smokeScript) | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' '
    $psi.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1"
    $psi.EnvironmentVariables["PYTHONUTF8"] = "1"
    $psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"
    $proc = [System.Diagnostics.Process]::Start($psi)
    if (-not $proc.WaitForExit(30000)) {
        try { Stop-Process -Id $proc.Id -Force -ErrorAction Stop } catch {}
        Capture-ProcessOutput $proc $stdout $stderr
        throw "packaged server import smoke timed out; stdout=$stdout; stderr=$stderr"
    }
    Capture-ProcessOutput $proc $stdout $stderr
    if ($proc.ExitCode -ne 0) { throw "packaged server import smoke failed with exit code $($proc.ExitCode); stdout=$stdout; stderr=$stderr" }
    $payload = Read-Json $stdout
    if ($payload.ok -ne $true) { throw "packaged server import smoke payload was not ok" }
    foreach ($path in @($payload.python, $payload.entrypoint, $payload.lark, $payload.corehr)) {
        if (-not (Test-UnderRoot $script:ReleaseRoot ([string]$path))) { throw "packaged server import used a path outside final release root: $path" }
    }
    if ($payload.legacy_core_hr_available -eq $true) { throw "lark_oapi.api.core.hr must not be used; the SDK namespace is lark_oapi.api.corehr" }
    return New-StatusObject "PASS" "python=$($payload.python); lark=$($payload.lark); corehr=$($payload.corehr)" $stdout ""
}

function Stop-PackagedBackendChildren([int[]]$ProcessIds) {
    $remaining = @()
    foreach ($processId in @($ProcessIds | Sort-Object -Unique)) {
        $record = Get-ProcessRecord $processId
        if ($null -eq $record) { continue }
        $executable = [string]$record.executablePath
        $isOwnedRuntime = (Test-UnderRoot (Join-Path $script:ReleaseRoot "server\runtime") $executable) -or
            (Test-UnderRoot (Join-Path $script:ReleaseRoot "runtime\desktop-rpa") $executable)
        if (-not $isOwnedRuntime) { continue }
        $null = & taskkill.exe /PID $processId /T /F 2>$null
        if ($LASTEXITCODE -ne 0 -and (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
            $remaining += $processId
        }
    }
    Start-Sleep -Seconds 1
    foreach ($processId in @($ProcessIds | Sort-Object -Unique)) {
        if (Get-Process -Id $processId -ErrorAction SilentlyContinue) { $remaining += $processId }
    }
    $remaining = @($remaining | Sort-Object -Unique)
    if ($remaining.Count -gt 0) {
        throw "packaged backend child process remained after shutdown: $($remaining -join ', ')"
    }
}

function Test-PackagedBackendBoot {
    if ($SkipLaunch) { return New-StatusObject "UNVERIFIED" "" "" "SkipLaunch was specified." }
    $python = Join-Path $script:ReleaseRoot "server\runtime\python\python.exe"
    $entrypoint = Join-Path $script:ReleaseRoot "server\app\packaging\server\entrypoint.py"
    $userData = Join-Path $script:SessionRoot "PackagedBackendUserData"
    $runtimeRoot = Join-Path $userData "runtime"
    $shutdownPath = Join-Path $runtimeRoot "backend-shutdown.json"
    $rpaRuntime = Join-Path $script:ReleaseRoot "runtime\desktop-rpa\LangBot Desktop RPA Runtime.exe"
    $port = $script:RuntimeTestPort
    Ensure-Directory $runtimeRoot

    $stdout = Join-Path $script:LogRoot "packaged-backend.stdout.log"
    $stderr = Join-Path $script:LogRoot "packaged-backend.stderr.log"
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $python
    $psi.WorkingDirectory = $script:ReleaseRoot
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $false
    $psi.RedirectStandardError = $false
    $arguments = @($entrypoint, "--install-root", $script:ReleaseRoot, "--user-data-root", $userData, "--host", "127.0.0.1", "--port", "$port", "--shutdown-request-path", $shutdownPath, "--rpa-runtime-path", $rpaRuntime)
    $psi.Arguments = (@("-B") + $arguments | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' '
    $psi.EnvironmentVariables["LOCALAPPDATA"] = $userData
    $psi.EnvironmentVariables["CHATBOT_USER_DATA_ROOT"] = $userData
    $psi.EnvironmentVariables["LANGBOT_DATA_ROOT"] = Join-Path $userData "data"
    $psi.EnvironmentVariables["LANGBOT_BROADCAST_SEND_ENABLED"] = "0"
    $psi.EnvironmentVariables["LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS"] = ""
    $psi.EnvironmentVariables["LANGBOT_RPA_ALLOW_AUTO_SEND"] = "0"
    $psi.EnvironmentVariables["LANGBOT_RPA_FORCE_DISABLE_SEND"] = "1"
    $psi.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1"
    $psi.EnvironmentVariables["PYTHONUTF8"] = "1"
    $psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"
    $proc = [System.Diagnostics.Process]::Start($psi)
    $childProcessIds = @()
    try {
        $health = Wait-Http "http://127.0.0.1:$port/healthz" $StartupTimeoutSeconds
        $healthJson = $health | ConvertTo-Json -Compress
        if ($healthJson -notmatch '"code"\s*:\s*0' -and $healthJson -notmatch '"msg"\s*:\s*"ok"') { throw "packaged backend health response was invalid: $healthJson" }
        $runtime = Wait-Http "http://127.0.0.1:$port/api/v1/desktop-automation/runtime/status" $StartupTimeoutSeconds
        $runtimeJson = $runtime | ConvertTo-Json -Compress
        if ($runtimeJson -match '"send_enabled"\s*:\s*true') { throw "RPA_STATUS_WAIT reported real send enabled" }
        $childProcessIds += @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { [int]$_.ParentProcessId -eq $proc.Id } | ForEach-Object { [int]$_.ProcessId })
        @{ action = "shutdown"; reason = "packaged-backend-verifier"; requestedAtUtc = [DateTime]::UtcNow.ToString("o") } | ConvertTo-Json | Set-Content -LiteralPath $shutdownPath -Encoding UTF8
        if (-not $proc.WaitForExit(90000)) { throw "packaged backend did not exit after shutdown request" }
        if ($proc.ExitCode -ne 0) { throw "packaged backend exited with code $($proc.ExitCode); backendLog=$(Join-Path $userData 'logs\\backend.log')" }
        return New-StatusObject "PASS" "pid=$($proc.Id); health=$healthJson; RPA_STATUS_WAIT=$runtimeJson; shutdown=$shutdownPath" (Join-Path $userData "logs\\backend.log") ""
    }
    finally {
        $childProcessIds += @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { [int]$_.ParentProcessId -eq $proc.Id } | ForEach-Object { [int]$_.ProcessId })
        if (-not $proc.HasExited) {
            @{ action = "shutdown"; reason = "packaged-backend-verifier-cleanup"; requestedAtUtc = [DateTime]::UtcNow.ToString("o") } | ConvertTo-Json | Set-Content -LiteralPath $shutdownPath -Encoding UTF8
            if (-not $proc.WaitForExit(10000)) { try { Stop-Process -Id $proc.Id -Force -ErrorAction Stop } catch {} }
        }
        Stop-PackagedBackendChildren -ProcessIds $childProcessIds
        if (-not $proc.HasExited) { throw "packaged backend process remained after cleanup: $($proc.Id)" }
    }
}

function Test-MinimizedPathMode {
    if (-not $MinimizedPath) { return New-StatusObject "UNVERIFIED" "" "" "MinimizedPath was not specified." }
    $value = Get-MinimizedPathValue -RuntimeReleaseRoot $script:IsolatedReleaseRoot
    Assert-MinimizedPathSafe -PathValue $value -RuntimeReleaseRoot $script:IsolatedReleaseRoot
    return "PATH=$value"
}

function Invoke-LauncherVerification {
    if ($SkipLaunch) { return New-StatusObject "UNVERIFIED" "" "" "SkipLaunch was specified." }
    $config = Get-LauncherConfig -LauncherConfigPath (Get-IsolatedLauncherConfigPath)
    $backendHost = [string]$config.backend.host
    $port = [int]$config.backend.port
    $userData = $script:UserDataRoot
    Ensure-Directory $userData
    $pathValue = $env:Path
    if ($MinimizedPath) { $pathValue = Get-MinimizedPathValue -RuntimeReleaseRoot $script:IsolatedReleaseRoot; Assert-MinimizedPathSafe -PathValue $pathValue -RuntimeReleaseRoot $script:IsolatedReleaseRoot }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = Join-Path $script:IsolatedReleaseRoot "ChatbotLauncher.exe"
    $psi.WorkingDirectory = $script:IsolatedReleaseRoot
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.EnvironmentVariables["LOCALAPPDATA"] = $userData
    $psi.EnvironmentVariables["CHATBOT_USER_DATA_ROOT"] = $userData
    $psi.EnvironmentVariables["LANGBOT_DATA_ROOT"] = Join-Path $userData "data"
    $psi.EnvironmentVariables["LANGBOT_BROADCAST_SEND_ENABLED"] = "0"
    $psi.EnvironmentVariables["LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS"] = ""
    $psi.EnvironmentVariables["LANGBOT_RPA_ALLOW_AUTO_SEND"] = "0"
    $psi.EnvironmentVariables["LANGBOT_RPA_FORCE_DISABLE_SEND"] = "1"
    $psi.EnvironmentVariables["CHATBOT_LAUNCHER_NONINTERACTIVE"] = "1"
    $psi.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1"
    $psi.EnvironmentVariables["PYTHONUTF8"] = "1"
    $psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"
    if ($MinimizedPath) { $psi.EnvironmentVariables["PATH"] = $pathValue }
    Write-ProcessEvidence @(Get-ControlledProcesses) "process-snapshot-before" | Out-Null
    $script:LauncherProcess = [System.Diagnostics.Process]::Start($psi)
    $launcherRecord = Get-ProcessRecord $script:LauncherProcess.Id
        $script:LauncherDiagnostics = [pscustomobject]@{
        launcherPath = $psi.FileName
        pid = $script:LauncherProcess.Id
        creationTime = if ($launcherRecord) { $launcherRecord.creationTime } else { "" }
        workingDirectory = $psi.WorkingDirectory
        arguments = $psi.Arguments
        environment = [ordered]@{
            LOCALAPPDATA = $userData
            CHATBOT_USER_DATA_ROOT = $userData
            LANGBOT_DATA_ROOT = (Join-Path $userData "data")
            LANGBOT_BROADCAST_SEND_ENABLED = "0"
            LANGBOT_RPA_ALLOW_AUTO_SEND = "0"
            LANGBOT_RPA_FORCE_DISABLE_SEND = "1"
            CHATBOT_LAUNCHER_NONINTERACTIVE = "1"
            PYTHONDONTWRITEBYTECODE = "1"
            PYTHONUTF8 = "1"
            PYTHONIOENCODING = "utf-8"
            RuntimeTestPort = $script:RuntimeTestPort
            PortConflictTestPort = $script:PortConflictTestPort
        }
    }
    $script:LauncherDiagnostics | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $script:LogRoot "launcher-start.json") -Encoding UTF8
    try {
        $healthUri = "http://${backendHost}:$port$($config.backend.healthPath)"
        $statusUri = "http://${backendHost}:$port$($config.backend.runtimeStatusPath)"
        try { $health = Wait-Http $healthUri $StartupTimeoutSeconds }
        catch {
            $classification = Get-HealthFailureClassification $userData $port
            $diagnosticPath = Write-LauncherFailureDiagnostics $userData $port $classification
            return New-StatusObject "FAIL" "classification=$classification; launcherPid=$($script:LauncherProcess.Id)" $diagnosticPath (Redact-VerificationText $_.Exception.Message)
        }
        $healthJson = $health | ConvertTo-Json -Compress
        if ($healthJson -notmatch '"code"\s*:\s*0' -and $healthJson -notmatch '"msg"\s*:\s*"ok"') {
            $diagnosticPath = Write-LauncherFailureDiagnostics $userData $port "HEALTH_RESPONSE_INVALID"
            return New-StatusObject "FAIL" "classification=HEALTH_RESPONSE_INVALID; launcherPid=$($script:LauncherProcess.Id)" $diagnosticPath "health response did not match expected semantics: $(Redact-VerificationText $healthJson)"
        }
        $homeResponse = Invoke-WebRequest -Uri "http://${backendHost}:$port/" -UseBasicParsing -TimeoutSec 10
        if ([int]$homeResponse.StatusCode -ne 200 -or $homeResponse.Content -notmatch '<html|<div|root') { throw "frontend home did not return expected HTML" }
        $spa = Invoke-WebRequest -Uri "http://${backendHost}:$port/apps" -UseBasicParsing -TimeoutSec 10
        if ([int]$spa.StatusCode -ne 200) { throw "SPA child route refresh returned $($spa.StatusCode)" }
        $runtime = Invoke-RestMethod -Uri $statusUri -TimeoutSec 10
        $runtimeJson = $runtime | ConvertTo-Json -Compress
        if ($runtimeJson -match '"send_enabled"\s*:\s*true') { throw "real send is enabled in runtime status" }
        try {
            $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction Stop)
            foreach ($listener in $listeners) { if ([string]$listener.LocalAddress -eq "0.0.0.0") { throw "release port is listening on 0.0.0.0" } }
            if (@(Get-NetTCPConnection -State Listen -LocalPort 3000 -ErrorAction SilentlyContinue).Count -gt 0) { throw "port 3000 is listening during trial verification" }
        } catch [System.Management.Automation.CommandNotFoundException] {}
        $processes = Get-ControlledProcesses @($script:LauncherProcess.Id)
        $processLog = Write-ProcessEvidence $processes
        Assert-NoForbiddenTools $processes
        return New-StatusObject "PASS" "launcherPid=$($script:LauncherProcess.Id); health=$healthJson; runtime=$runtimeJson" $processLog ""
    }
    finally {
        Stop-ControlledProcesses "verify-launcher"
        Capture-LauncherOutput
        Copy-LauncherDiagnostics $userData
    }
}

function Test-PortConflict {
    if ($SkipLaunch) { return New-StatusObject "UNVERIFIED" "" "" "SkipLaunch was specified." }
    Update-IsolatedLauncherConfig -Port $script:PortConflictTestPort
    $config = Get-LauncherConfig -LauncherConfigPath (Get-IsolatedLauncherConfigPath)
    $port = [int]$config.backend.port
    $userData = $script:UserDataRoot
    Ensure-Directory $userData
    $listener = New-Object System.Net.Sockets.TcpListener ([System.Net.IPAddress]::Parse("127.0.0.1"), $port)
    $listener.Start()
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = Join-Path $script:IsolatedReleaseRoot "ChatbotLauncher.exe"
        $psi.WorkingDirectory = $script:IsolatedReleaseRoot
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.EnvironmentVariables["LOCALAPPDATA"] = $userData
        $psi.EnvironmentVariables["CHATBOT_USER_DATA_ROOT"] = $userData
        $psi.EnvironmentVariables["LANGBOT_DATA_ROOT"] = Join-Path $userData "data"
        $psi.EnvironmentVariables["LANGBOT_BROADCAST_SEND_ENABLED"] = "0"
        $psi.EnvironmentVariables["LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS"] = ""
        $psi.EnvironmentVariables["LANGBOT_RPA_ALLOW_AUTO_SEND"] = "0"
        $psi.EnvironmentVariables["LANGBOT_RPA_FORCE_DISABLE_SEND"] = "1"
        $psi.EnvironmentVariables["CHATBOT_LAUNCHER_NONINTERACTIVE"] = "1"
        $psi.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1"
        $psi.EnvironmentVariables["PYTHONUTF8"] = "1"
        $psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"
        $proc = [System.Diagnostics.Process]::Start($psi)
        $script:LauncherProcess = $proc
        $stdout = Join-Path $script:LogRoot "port-conflict-launcher.stdout.log"
        $stderr = Join-Path $script:LogRoot "port-conflict-launcher.stderr.log"
        if (-not $proc.WaitForExit(120000)) {
            try { Stop-Process -Id $proc.Id -Force -ErrorAction Stop } catch {}
            Capture-ProcessOutput $proc $stdout $stderr
            throw "port-conflict launcher did not exit within 30 seconds"
        }
        Capture-ProcessOutput $proc $stdout $stderr
        try { if (@(Get-NetTCPConnection -State Listen -LocalPort 3000 -ErrorAction SilentlyContinue).Count -gt 0) { throw "launcher started development port 3000 during port conflict" } } catch [System.Management.Automation.CommandNotFoundException] {}
        if ([int]$proc.ExitCode -ne 20) {
            throw "port-conflict launcher exited with unexpected code $($proc.ExitCode); stdout=$stdout; stderr=$stderr"
        }
        $stderrText = Get-Content -LiteralPath $stderr -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        $launcherLogPath = Join-Path $userData "logs\launcher.log"
        $launcherLog = if (Test-Path -LiteralPath $launcherLogPath -PathType Leaf) { Get-Content -LiteralPath $launcherLogPath -Raw -Encoding UTF8 } else { "" }
        if (($stderrText -notmatch 'PORT_OWNED_BY_OTHER_PROCESS') -and ($launcherLog -notmatch 'PORT_OWNED_BY_OTHER_PROCESS')) {
            throw "port-conflict launcher did not report PORT_OWNED_BY_OTHER_PROCESS; stderr=$stderr; launcherLog=$launcherLogPath"
        }
        return New-StatusObject "PASS" "exitCode=$($proc.ExitCode); stderr=$stderr; launcherLog=$launcherLogPath; port-conflict test port=$port" $stderr ""
    }
    finally {
        $listener.Stop()
        Update-IsolatedLauncherConfig -Port $script:RuntimeTestPort
        Test-LauncherPortAvailability -Port $port -StageName "port-conflict" | Out-Null
    }
}

function Test-NoResidualProcesses {
    $processes = @()
    if ($script:LauncherProcess) {
        $processes = @(Get-ControlledProcesses @($script:LauncherProcess.Id) | Where-Object { Test-ProcessBelongsToSession $_ $script:LauncherProcess.Id })
    }
    $processLog = Write-ProcessEvidence $processes
    if ($processes.Count -gt 0) {
        $pids = (($processes | ForEach-Object { $_.pid }) -join ', ')
        throw "Controlled release processes remain: $pids"
    }
    return New-StatusObject "PASS" "No controlled processes remain." $processLog ""
}

function Test-ReleaseImmutability {
    $current = Get-ReleaseFileSnapshot
    $diff = Compare-ReleaseSnapshots $script:ImmutableBaseline $current
    if ($diff.Added.Count -gt 0 -or $diff.Removed.Count -gt 0 -or $diff.Modified.Count -gt 0) {
        $message = @(
            "added=$($diff.Added -join ', ')",
            "removed=$($diff.Removed -join ', ')",
            "modified=$($diff.Modified -join ', ')"
        ) -join '; '
        throw "Release directory changed during verification: $message"
    }
    return "added=0; removed=0; modified=0"
}

try {
    Ensure-Directory $script:LogRoot
    if (-not (Test-Path -LiteralPath $script:ReleaseRoot -PathType Container)) { throw "ReleasePath does not exist: $script:ReleaseRoot" }
    Invoke-Check "portable-structure" { Test-PortableStructure }
    Invoke-Check "launcher-config" { Test-LauncherConfiguration }
    Select-VerificationPorts
    Initialize-IsolatedRelease
    Invoke-Check "manifest-critical-sha" { Test-Manifest }
    Invoke-Check "sha256sums" { Test-Sha256Sums }
    Invoke-Check "zip-contents" { Test-ZipContents }
    Invoke-Check "sensitive-scan" { Test-SensitiveScan }
    Invoke-Check "forbidden-content" { Test-ForbiddenContent }
    $script:ImmutableBaseline = Get-ReleaseFileSnapshot
    Invoke-Check "real-send-defaults" { Test-SafetyDefaults }
    Invoke-Check "packaged-server-imports" { Test-PackagedServerImports }
    Invoke-Check "connector-smoke" { Invoke-ConnectorSmoke }
    Invoke-Check "minimized-path" { Test-MinimizedPathMode }
    Invoke-Check "packaged-backend-boot" { Test-PackagedBackendBoot }
    if ($script:Results[-1].status -ne "PASS") {
        throw "packaged-backend-boot failed; skipping launcher runtime and subsequent launch-dependent checks."
    }
    Invoke-Check "launcher-runtime" { Invoke-LauncherVerification }
    if ($script:Results[-1].status -ne "PASS") {
        throw "launcher-runtime failed; skipping port-conflict and subsequent launch-dependent checks."
    }
    Invoke-Check "launcher-runtime-port-release" { Test-LauncherPortAvailability -Port $script:RuntimeTestPort -StageName "launcher-runtime" }
    Invoke-Check "port-conflict" { Test-PortConflict }
    Invoke-Check "post-port-conflict-port-release" { Test-LauncherPortAvailability -Port $script:PortConflictTestPort -StageName "post-port-conflict" }
    Invoke-Check "no-residual-processes" { Test-NoResidualProcesses }
    Invoke-Check "release-immutable" { Test-ReleaseImmutability }
}
catch {
    Add-Result "verification" "FAIL" "" "" (Redact-VerificationText $_.Exception.Message) 0
}
finally {
    try { Stop-ControlledProcesses "verify-finally" } catch {}
    try { Capture-LauncherOutput } catch {}
    try { Reset-IsolatedRelease } catch {}
    $summaryStatus = "PASS"
    if (@($script:Results | Where-Object { $_.status -eq "FAIL" }).Count -gt 0) { $summaryStatus = "FAIL" }
    elseif (@($script:Results | Where-Object { $_.status -eq "UNVERIFIED" }).Count -gt 0) { $summaryStatus = "UNVERIFIED" }
    $script:Summary = [pscustomobject]@{
        status = $summaryStatus
        releasePath = $script:ReleaseRoot
        zipPath = $ZipPath
        sessionRoot = $script:SessionRoot
        logPath = $script:ResultPath
        generatedAtUtc = [DateTime]::UtcNow.ToString("o")
        results = $script:Results
    }
    try { $script:Summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $script:ResultPath -Encoding UTF8 } catch {}
}

$script:Summary | ConvertTo-Json -Depth 8
if ($script:Summary.status -eq "FAIL") { exit 1 }
exit 0
