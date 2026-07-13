#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SetupPath,

    [string]$ExpectedInstallRoot = "$env:TEMP\ChatbotTrialInstall\Chatbot",

    [string]$UpgradeSetupPath,

    [switch]$Silent,

    [int]$StartupTimeoutSeconds = 90,

    [ValidateSet("All", "Install", "FirstLaunch", "Upgrade", "Uninstall")]
    [string]$Phase = "All",

    [switch]$KeepWorkDirectory,

    [switch]$SkipUpgrade,

    [switch]$SkipUninstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$script:Results = @()
$script:SessionRoot = Join-Path $env:TEMP ("ChatbotTrialInstallVerify\" + [guid]::NewGuid().ToString("N"))
$script:LogRoot = Join-Path $script:SessionRoot "logs"
$script:ResultPath = Join-Path $script:LogRoot "test-trial-install-result.json"
$script:InstallRoot = $null
$script:LauncherProcess = $null

function New-DirectoryIfMissing {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Normalize-FullPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
}

function Test-PathUnderRoot {
    param([Parameter(Mandatory = $true)][string]$Root, [Parameter(Mandatory = $true)][string]$Path)
    $rootFull = Normalize-FullPath -Path $Root
    $pathFull = Normalize-FullPath -Path $Path
    return ($pathFull.Equals($rootFull, [System.StringComparison]::OrdinalIgnoreCase) -or $pathFull.StartsWith($rootFull + '\', [System.StringComparison]::OrdinalIgnoreCase))
}

function Get-IsolatedLocalAppData {
    return Join-Path $script:SessionRoot "LocalAppData"
}

function Get-IsolatedUserDataRoot {
    return Join-Path (Get-IsolatedLocalAppData) "Chatbot"
}

function Get-LauncherLogPath {
    return Join-Path (Get-IsolatedUserDataRoot) "logs\launcher.log"
}

function Get-BackendLogPath {
    return Join-Path (Get-IsolatedUserDataRoot) "logs\backend.log"
}

function Get-LauncherStatePath {
    return Join-Path (Get-IsolatedUserDataRoot) "runtime\launcher-state.json"
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash).ToLowerInvariant()
}

function Read-JsonFile {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Get-InstalledStartupTimeoutSeconds {
    param([Parameter(Mandatory = $true)][object]$Config)
    $configured = [int]$Config.backend.startupTimeoutSeconds
    if ($configured -lt 1) { throw "launcher.json startupTimeoutSeconds must be positive" }
    return [Math]::Max($StartupTimeoutSeconds, $configured)
}

function New-StatusObject {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("PASS", "FAIL", "UNVERIFIED")][string]$Status,
        [string]$Evidence = "",
        [string]$LogPath = "",
        [string]$Message = ""
    )
    return [pscustomobject]@{ Status = $Status; Evidence = $Evidence; LogPath = $LogPath; Message = $Message }
}

function Add-VerificationResult {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][ValidateSet("PASS", "FAIL", "UNVERIFIED")][string]$Status,
        [string]$Evidence = "",
        [string]$LogPath = "",
        [string]$Message = "",
        [double]$DurationSeconds = 0,
        [string]$StartedAtUtc = "",
        [string]$CompletedAtUtc = "",
        [int]$TimeoutSeconds = 0
    )
    $script:Results += [pscustomobject]@{
        name = $Name
        status = $Status
        startedAtUtc = $StartedAtUtc
        completedAtUtc = $CompletedAtUtc
        timeoutSeconds = $TimeoutSeconds
        durationSeconds = [Math]::Round($DurationSeconds, 3)
        evidence = $Evidence
        logPath = $LogPath
        message = $Message
    }
}

function Invoke-Stage {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action,
        [int]$TimeoutSeconds = 0
    )
    $start = [DateTime]::UtcNow
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $value = & $Action
        $watch.Stop()
        if ($null -ne $value -and $value.PSObject.Properties.Name -contains "Status") {
            Add-VerificationResult -Name $Name -Status $value.Status -Evidence ([string]$value.Evidence) -LogPath ([string]$value.LogPath) -Message ([string]$value.Message) -DurationSeconds $watch.Elapsed.TotalSeconds -StartedAtUtc $start.ToString("o") -CompletedAtUtc ([DateTime]::UtcNow.ToString("o")) -TimeoutSeconds $TimeoutSeconds
        }
        else {
            Add-VerificationResult -Name $Name -Status "PASS" -Evidence ([string]$value) -DurationSeconds $watch.Elapsed.TotalSeconds -StartedAtUtc $start.ToString("o") -CompletedAtUtc ([DateTime]::UtcNow.ToString("o")) -TimeoutSeconds $TimeoutSeconds
        }
    }
    catch {
        $watch.Stop()
        Add-VerificationResult -Name $Name -Status "FAIL" -Message $_.Exception.Message -DurationSeconds $watch.Elapsed.TotalSeconds -StartedAtUtc $start.ToString("o") -CompletedAtUtc ([DateTime]::UtcNow.ToString("o")) -TimeoutSeconds $TimeoutSeconds
    }
}

function Assert-TestInstallRootSafe {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = Normalize-FullPath -Path $Path
    $localPrograms = Normalize-FullPath -Path (Join-Path $env:LOCALAPPDATA "Programs")
    $tempRoot = Normalize-FullPath -Path $env:TEMP
    if ((Test-Path -LiteralPath $full) -and -not (Test-PathUnderRoot -Root $script:SessionRoot -Path $full) -and -not (Test-PathUnderRoot -Root $tempRoot -Path $full)) {
        throw "Refusing to overwrite existing non-isolated install root: $full"
    }
    if ($full.Equals((Normalize-FullPath -Path (Join-Path $localPrograms "Chatbot")), [System.StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $full)) {
        throw "Refusing to use default install root because it already exists: $full"
    }
}

function Get-ProcessDetails {
    param([int[]]$ProcessIds = @())
    $all = @(Get-CimInstance Win32_Process)
    if ($ProcessIds.Count -gt 0) {
        $selected = @()
        $queue = New-Object System.Collections.Queue
        foreach ($id in $ProcessIds) { $queue.Enqueue([int]$id) }
        $seen = @{}
        while ($queue.Count -gt 0) {
            $processId = [int]$queue.Dequeue()
            if ($seen.ContainsKey($processId)) { continue }
            $seen[$processId] = $true
            foreach ($item in ($all | Where-Object { $_.ProcessId -eq $processId })) { $selected += $item }
            foreach ($child in ($all | Where-Object { $_.ParentProcessId -eq $processId })) { $queue.Enqueue([int]$child.ProcessId) }
        }
    }
    else {
        $selected = $all | Where-Object {
            ($_.ExecutablePath -and $script:InstallRoot -and (Test-PathUnderRoot -Root $script:InstallRoot -Path $_.ExecutablePath)) -or
            ($_.CommandLine -and $script:InstallRoot -and $_.CommandLine.IndexOf($script:InstallRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
        }
    }
    return @($selected | Select-Object @{n="pid";e={$_.ProcessId}}, @{n="parentPid";e={$_.ParentProcessId}}, @{n="name";e={$_.Name}}, @{n="executablePath";e={$_.ExecutablePath}}, @{n="commandLine";e={$_.CommandLine}}, @{n="creationTime";e={$_.CreationDate}})
}

function Write-ProcessEvidence {
    param([Parameter(Mandatory = $true)][string]$Name, [object[]]$Processes)
    $path = Join-Path $script:LogRoot ($Name + "-processes.json")
    $Processes | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $path -Encoding UTF8
    return $path
}

function Write-JsonEvidence {
    param([Parameter(Mandatory = $true)][string]$Name, [Parameter(Mandatory = $true)]$Payload)
    $path = Join-Path $script:LogRoot ($Name + ".json")
    $Payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding UTF8
    return $path
}

function Find-UninstallEntry {
    $roots = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
    )
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        foreach ($key in Get-ChildItem $root -ErrorAction SilentlyContinue) {
            $props = Get-ItemProperty -LiteralPath $key.PSPath -ErrorAction SilentlyContinue
            if ($props) {
                $displayName = if ($props.PSObject.Properties.Name -contains "DisplayName") { [string]$props.DisplayName } else { "" }
                $installLocation = if ($props.PSObject.Properties.Name -contains "InstallLocation") { [string]$props.InstallLocation } else { "" }
                if ($displayName -like "Chatbot Trial*" -or ($installLocation -and $installLocation -eq $script:InstallRoot)) { return $props }
            }
        }
    }
    return $null
}

function Find-UninstallExecutable {
    $candidates = @(Get-ChildItem -LiteralPath $script:InstallRoot -Filter "unins*.exe" -File -ErrorAction SilentlyContinue | Sort-Object Name)
    if ($candidates.Count -gt 0) { return $candidates[0].FullName }
    $entry = Find-UninstallEntry
    if ($null -eq $entry) { return $null }
    $uninstall = [string]$entry.UninstallString
    if ([string]::IsNullOrWhiteSpace($uninstall)) { return $null }
    if ($uninstall.StartsWith('"')) {
        $second = $uninstall.IndexOf('"', 1)
        if ($second -gt 1) { return $uninstall.Substring(1, $second - 1) }
    }
    return ($uninstall -split '\s+', 2)[0]
}

function Get-ShortcutEvidence {
    $desktop = [Environment]::GetFolderPath("DesktopDirectory")
    $startMenu = [Environment]::GetFolderPath("Programs")
    $desktopShortcut = Join-Path $desktop "Chatbot Trial.lnk"
    $startMenuShortcut = Join-Path $startMenu "Chatbot Trial.lnk"
    if (-not (Test-Path -LiteralPath $startMenuShortcut -PathType Leaf)) {
        throw "Missing Start Menu shortcut: $startMenuShortcut"
    }
    $shortcuts = @($startMenuShortcut)
    if (Test-Path -LiteralPath $desktopShortcut -PathType Leaf) {
        $shortcuts += $desktopShortcut
    }
    return $shortcuts
}

function Start-LauncherFromShortcut {
    $shortcuts = @(Get-ShortcutEvidence)
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($shortcuts[0])
    $target = [string]$link.TargetPath
    if (-not (Test-PathUnderRoot -Root $script:InstallRoot -Path $target)) { throw "Shortcut target is outside install root: $target" }
    $isolatedLocalAppData = Get-IsolatedLocalAppData
    $isolatedUserDataRoot = Get-IsolatedUserDataRoot
    New-DirectoryIfMissing -Path $isolatedLocalAppData
    New-DirectoryIfMissing -Path $isolatedUserDataRoot
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $target
    $psi.WorkingDirectory = $script:InstallRoot
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.EnvironmentVariables["LOCALAPPDATA"] = $isolatedLocalAppData
    $psi.EnvironmentVariables["CHATBOT_USER_DATA_ROOT"] = $isolatedUserDataRoot
    $psi.EnvironmentVariables["LANGBOT_BROADCAST_SEND_ENABLED"] = "0"
    $psi.EnvironmentVariables["LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS"] = ""
    $psi.EnvironmentVariables["LANGBOT_RPA_ALLOW_AUTO_SEND"] = "0"
    $psi.EnvironmentVariables["LANGBOT_RPA_FORCE_DISABLE_SEND"] = "1"
    $psi.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1"
    $psi.EnvironmentVariables["PYTHONUTF8"] = "1"
    $psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"
    $script:LauncherProcess = [System.Diagnostics.Process]::Start($psi)
    return $script:LauncherProcess
}

function Wait-Until {
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Condition,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds,
        [int]$SleepMilliseconds = 500
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastValue = $null
    while ((Get-Date) -lt $deadline) {
        $lastValue = & $Condition
        if ($null -ne $lastValue) { return $lastValue }
        Start-Sleep -Milliseconds $SleepMilliseconds
    }
    return $null
}

function Wait-ForHttpReady {
    param([Parameter(Mandatory = $true)][string]$Uri, [int]$TimeoutSeconds)
    $lastError = ""
    $result = Wait-Until -TimeoutSeconds $TimeoutSeconds -Condition {
        try { return Invoke-RestMethod -Uri $Uri -TimeoutSec 3 }
        catch { $script:lastHttpError = $_.Exception.Message; return $null }
    }
    if ($null -eq $result) {
        $lastError = if ($script:lastHttpError) { [string]$script:lastHttpError } else { "" }
        throw "Timed out waiting for $Uri. Last error: $lastError"
    }
    return $result
}

function Invoke-HttpWithRetry {
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Request,
        [int]$DeadlineSeconds = 60,
        [int]$SleepMilliseconds = 500
    )
    $deadline = (Get-Date).AddSeconds($DeadlineSeconds)
    $lastError = ""
    while ((Get-Date) -lt $deadline) {
        try { return & $Request }
        catch {
            $lastError = $_.Exception.Message
            Start-Sleep -Milliseconds $SleepMilliseconds
        }
    }
    throw "HTTP request did not succeed before its deadline. Last error: $lastError"
}

function Collect-LaunchDiagnostics {
    param([Parameter(Mandatory = $true)][string]$Name, [string]$HealthUri = "", [string]$StatusUri = "")
    $config = $null
    if (Test-Path -LiteralPath (Join-Path $script:InstallRoot "launcher.json") -PathType Leaf) {
        $config = Read-JsonFile -Path (Join-Path $script:InstallRoot "launcher.json")
    }
    $launcherPid = if ($script:LauncherProcess) { $script:LauncherProcess.Id } else { $null }
    $processes = if ($launcherPid) { @(Get-ProcessDetails -ProcessIds @($launcherPid)) } else { @(Get-ProcessDetails) }
    $ports = @()
    if ($config -and $config.backend -and $config.backend.port) {
        try { $ports = @(Get-NetTCPConnection -LocalPort ([int]$config.backend.port) -ErrorAction Stop | Select-Object LocalAddress, LocalPort, State, OwningProcess) } catch {}
    }
    $payload = [ordered]@{
        launcherPid = $launcherPid
        healthUri = $HealthUri
        statusUri = $StatusUri
        launcherStatePath = Get-LauncherStatePath
        launcherLogPath = Get-LauncherLogPath
        backendLogPath = Get-BackendLogPath
        processes = $processes
        listeners = $ports
    }
    return Write-JsonEvidence -Name $Name -Payload $payload
}

function Wait-ForControlledProcessesExit {
    param([int]$TimeoutSeconds = 15)
    $remaining = Wait-Until -TimeoutSeconds $TimeoutSeconds -SleepMilliseconds 500 -Condition {
        $items = @(Get-ProcessDetails)
        if ($items.Count -eq 0) { return @() }
        return $null
    }
    if ($null -eq $remaining) { return @(Get-ProcessDetails) }
    return @()
}

function Stop-LauncherGracefully {
    param([int]$TimeoutSeconds = 10)
    $shutdown = Join-Path (Get-IsolatedUserDataRoot) "runtime\backend-shutdown.json"
    New-DirectoryIfMissing -Path (Split-Path -Parent $shutdown)
    @{ action = "shutdown"; reason = "install-verify"; requestedAtUtc = [DateTime]::UtcNow.ToString("o") } | ConvertTo-Json | Set-Content -LiteralPath $shutdown -Encoding UTF8
    if ($script:LauncherProcess -and -not $script:LauncherProcess.HasExited) {
        try { $script:LauncherProcess.CloseMainWindow() | Out-Null } catch {}
        if (-not $script:LauncherProcess.WaitForExit($TimeoutSeconds * 1000)) {
            try { $script:LauncherProcess.Kill() } catch {}
        }
    }
    $remaining = @(Wait-ForControlledProcessesExit -TimeoutSeconds 15)
    if ($remaining.Count -gt 0) {
        foreach ($proc in $remaining) {
            try { Stop-Process -Id ([int]$proc.pid) -Force -ErrorAction SilentlyContinue } catch {}
        }
        Start-Sleep -Seconds 2
    }
}

function Invoke-Setup {
    param([Parameter(Mandatory = $true)][string]$Path, [string]$Label = "install")
    $log = Join-Path $script:LogRoot ("setup-$Label.log")
    $dirArg = "/DIR=`"$script:InstallRoot`""
    $logArg = "/LOG=`"$log`""
    $args = @("/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", $dirArg, $logArg)
    if ($Silent) { $args = @("/VERYSILENT") + $args } else { $args = @("/SILENT") + $args }
    $proc = Start-Process -FilePath $Path -ArgumentList $args -Wait -PassThru -WindowStyle Hidden
    if ($proc.ExitCode -ne 0) { throw "Setup $Label failed with exit code $($proc.ExitCode). Log: $log" }
    return [pscustomobject]@{ Path = $log; ExitCode = $proc.ExitCode }
}

function Invoke-Uninstall {
    $uninstallExe = Find-UninstallExecutable
    if ([string]::IsNullOrWhiteSpace($uninstallExe)) { throw "Uninstall executable was not found" }
    if (-not (Test-PathUnderRoot -Root $script:InstallRoot -Path $uninstallExe)) { throw "Uninstall executable is outside install root: $uninstallExe" }
    $log = Join-Path $script:LogRoot "setup-uninstall.log"
    $args = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=`"$log`"")
    $proc = Start-Process -FilePath $uninstallExe -ArgumentList $args -Wait -PassThru -WindowStyle Hidden
    return [pscustomobject]@{
        Path = $log
        ExitCode = $proc.ExitCode
        Command = ('"{0}" {1}' -f $uninstallExe, ($args -join ' '))
    }
}

function Stage-Precheck {
    Assert-TestInstallRootSafe -Path $script:InstallRoot
    if ((Test-Path -LiteralPath $script:InstallRoot) -and (Test-PathUnderRoot -Root $env:TEMP -Path $script:InstallRoot)) {
        Remove-Item -LiteralPath $script:InstallRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    $processes = @(Get-ProcessDetails)
    $processLog = Write-ProcessEvidence -Name "precheck" -Processes $processes
    if ($processes.Count -gt 0) { throw "Controlled processes already running for install root. Evidence: $processLog" }
    return New-StatusObject -Status "PASS" -Evidence "installRoot=$script:InstallRoot; isolatedUserDataRoot=$(Get-IsolatedUserDataRoot)" -LogPath $processLog
}

function Stage-Install {
    $log = Invoke-Setup -Path (Normalize-FullPath -Path $SetupPath) -Label "install"
    return New-StatusObject -Status "PASS" -Evidence "installExitCode=$($log.ExitCode); installRoot=$script:InstallRoot" -LogPath $log.Path
}

function Stage-VerifyFiles {
    foreach ($relative in @("ChatbotLauncher.exe", "launcher.json", "manifest.json")) {
        if (-not (Test-Path -LiteralPath (Join-Path $script:InstallRoot $relative) -PathType Leaf)) { throw "Installed file missing: $relative" }
    }
    $entry = Find-UninstallEntry
    if ($null -eq $entry) { throw "Uninstall entry was not found" }
    return "installRoot=$script:InstallRoot; uninstall=$($entry.UninstallString)"
}

function Stage-VerifyShortcuts {
    $shortcuts = Get-ShortcutEvidence
    return "shortcuts=$($shortcuts -join '; ')"
}

function Stage-FirstLaunch {
    $proc = Start-LauncherFromShortcut
    return "launcherPid=$($proc.Id)"
}

function Stage-HealthWait {
    $config = Read-JsonFile -Path (Join-Path $script:InstallRoot "launcher.json")
    $startupTimeoutSeconds = Get-InstalledStartupTimeoutSeconds -Config $config
    $backendHost = [string]$config.backend.host
    $port = [int]$config.backend.port
    $healthUri = "http://${backendHost}:$port$($config.backend.healthPath)"
    try {
        $health = Wait-ForHttpReady -Uri $healthUri -TimeoutSeconds $startupTimeoutSeconds
        return New-StatusObject -Status "PASS" -Evidence ("health=" + ($health | ConvertTo-Json -Compress))
    }
    catch {
        $log = Collect-LaunchDiagnostics -Name "health-timeout" -HealthUri $healthUri
        throw ("HEALTH_WAIT failed. " + $_.Exception.Message + " Diagnostics: " + $log)
    }
}

function Stage-RuntimeStatusWait {
    $config = Read-JsonFile -Path (Join-Path $script:InstallRoot "launcher.json")
    $startupTimeoutSeconds = Get-InstalledStartupTimeoutSeconds -Config $config
    $backendHost = [string]$config.backend.host
    $port = [int]$config.backend.port
    $statusUri = "http://${backendHost}:$port$($config.backend.runtimeStatusPath)"
    $result = Wait-Until -TimeoutSeconds $startupTimeoutSeconds -Condition {
        try {
            $status = Invoke-RestMethod -Uri $statusUri -TimeoutSec 5
            if ($status.state -eq "FAILED") {
                return $status
            }
            if ($status.state -notin @("CORE_READY", "READY", "DEGRADED")) {
                return $null
            }
            return $status
        }
        catch {
            $script:lastStatusError = $_.Exception.Message
            return $null
        }
    }
    if ($result -and $result.state -eq "FAILED") {
        $log = Collect-LaunchDiagnostics -Name "runtime-failed" -StatusUri $statusUri
        throw "RUNTIME_STATUS_WAIT failed. Backend lifecycle failed. Diagnostics: $log"
    }
    if ($null -eq $result) {
        $log = Collect-LaunchDiagnostics -Name "runtime-timeout" -StatusUri $statusUri
        $lastError = if ($script:lastStatusError) { [string]$script:lastStatusError } else { "" }
        throw "RUNTIME_STATUS_WAIT failed. Timed out waiting for a core-usable backend state. Last error: $lastError Diagnostics: $log"
    }
    return New-StatusObject -Status "PASS" -Evidence ("runtime=" + ($result | ConvertTo-Json -Compress))
}

function Stage-OnboardingApi {
    $config = Read-JsonFile -Path (Join-Path $script:InstallRoot "launcher.json")
    $backendHost = [string]$config.backend.host
    $port = [int]$config.backend.port
    $baseUri = "http://${backendHost}:$port"
    $origin = "http://127.0.0.1:58751"
    $corsHeaders = @{ Origin = $origin }
    $preflightEvidence = @()

    foreach ($request in @(
        @{ Path = "/api/v1/platform/adapters"; Method = "GET" },
        @{ Path = "/api/v1/system/wizard/progress"; Method = "PUT" },
        @{ Path = "/api/v1/system/wizard/completed"; Method = "POST" }
    )) {
        $preflight = Invoke-HttpWithRetry -Request { Invoke-WebRequest -UseBasicParsing -Method OPTIONS -Uri ($baseUri + $request.Path) -Headers @{
            Origin = $origin
            "Access-Control-Request-Method" = $request.Method
            "Access-Control-Request-Headers" = "content-type"
        } -TimeoutSec 10 -ErrorAction Stop }
        if ($preflight.Headers["Access-Control-Allow-Origin"] -ne $origin) {
            throw "CORS origin was not accepted for $($request.Method) $($request.Path)"
        }
        if ([string]$preflight.Headers["Access-Control-Allow-Methods"] -notmatch [regex]::Escape($request.Method)) {
            throw "CORS method was not accepted for $($request.Method) $($request.Path)"
        }
        $preflightEvidence += [ordered]@{
            path = $request.Path
            method = $request.Method
            status = [int]$preflight.StatusCode
            allowOrigin = [string]$preflight.Headers["Access-Control-Allow-Origin"]
            allowMethods = [string]$preflight.Headers["Access-Control-Allow-Methods"]
            allowHeaders = [string]$preflight.Headers["Access-Control-Allow-Headers"]
        }
    }

    $ready = Invoke-HttpWithRetry -Request { Invoke-WebRequest -UseBasicParsing -Uri "$baseUri/readyz" -Headers $corsHeaders -TimeoutSec 10 -ErrorAction Stop }
    $readyBody = $ready.Content | ConvertFrom-Json
    if ($readyBody.status -ne "ready") { throw "readyz did not report ready" }

    $platform = Invoke-HttpWithRetry -Request { Invoke-WebRequest -UseBasicParsing -Uri "$baseUri/api/v1/platform/adapters" -Headers $corsHeaders -TimeoutSec 10 -ErrorAction Stop }
    $platformBody = $platform.Content | ConvertFrom-Json
    $platformCount = @($platformBody.data.adapters).Count
    if ($platformBody.code -ne 0 -or $platformCount -lt 1) { throw "platform adapter catalog is unavailable" }

    $progressPayload = @{ step = 0; selected_adapter = $null; created_bot_uuid = $null; bot_saved = $false; selected_runner = $null } | ConvertTo-Json -Compress
    $progress = Invoke-HttpWithRetry -Request { Invoke-WebRequest -UseBasicParsing -Method PUT -Uri "$baseUri/api/v1/system/wizard/progress" -Headers $corsHeaders -ContentType "application/json" -Body $progressPayload -TimeoutSec 10 -ErrorAction Stop }
    $progressBody = $progress.Content | ConvertFrom-Json
    if ($progressBody.code -ne 0) { throw "wizard progress update failed" }

    $completedPayload = @{ status = "skipped" } | ConvertTo-Json -Compress
    $completed = Invoke-HttpWithRetry -Request { Invoke-WebRequest -UseBasicParsing -Method POST -Uri "$baseUri/api/v1/system/wizard/completed" -Headers $corsHeaders -ContentType "application/json" -Body $completedPayload -TimeoutSec 10 -ErrorAction Stop }
    $completedBody = $completed.Content | ConvertFrom-Json
    if ($completedBody.code -ne 0) { throw "wizard completed update failed" }
    $completedRepeat = Invoke-HttpWithRetry -Request { Invoke-WebRequest -UseBasicParsing -Method POST -Uri "$baseUri/api/v1/system/wizard/completed" -Headers $corsHeaders -ContentType "application/json" -Body $completedPayload -TimeoutSec 10 -ErrorAction Stop }
    $completedRepeatBody = $completedRepeat.Content | ConvertFrom-Json
    if ($completedRepeatBody.code -ne 0) { throw "wizard completed update is not idempotent" }

    $systemInfo = Invoke-HttpWithRetry -Request { Invoke-WebRequest -UseBasicParsing -Uri "$baseUri/api/v1/system/info" -Headers $corsHeaders -TimeoutSec 10 -ErrorAction Stop }
    $systemInfoBody = $systemInfo.Content | ConvertFrom-Json
    if ($systemInfoBody.data.wizard_status -ne "skipped" -or $null -ne $systemInfoBody.data.wizard_progress) {
        throw "wizard state was not persisted"
    }

    $evidence = Write-JsonEvidence -Name "onboarding-api" -Payload ([ordered]@{
        origin = $origin
        ready = @{ url = "$baseUri/readyz"; status = [int]$ready.StatusCode; body = $readyBody; allowOrigin = [string]$ready.Headers["Access-Control-Allow-Origin"] }
        platform = @{ url = "$baseUri/api/v1/platform/adapters"; status = [int]$platform.StatusCode; count = $platformCount; allowOrigin = [string]$platform.Headers["Access-Control-Allow-Origin"] }
        progress = @{ url = "$baseUri/api/v1/system/wizard/progress"; status = [int]$progress.StatusCode; allowOrigin = [string]$progress.Headers["Access-Control-Allow-Origin"] }
        completed = @{ url = "$baseUri/api/v1/system/wizard/completed"; status = [int]$completed.StatusCode; repeatStatus = [int]$completedRepeat.StatusCode; allowOrigin = [string]$completed.Headers["Access-Control-Allow-Origin"] }
        persistence = @{ status = $systemInfoBody.data.wizard_status; progress = $systemInfoBody.data.wizard_progress }
        preflight = $preflightEvidence
    })
    return New-StatusObject -Status "PASS" -Evidence "ready=200; platformCount=$platformCount; progress=200; completed=200" -LogPath $evidence
}

function Stage-Stop {
    Stop-LauncherGracefully -TimeoutSeconds 10
    $processes = @(Get-ProcessDetails)
    $processLog = Write-ProcessEvidence -Name "stop" -Processes $processes
    if ($processes.Count -gt 0) { throw "Controlled processes remain after stop. Evidence: $processLog" }
    return New-StatusObject -Status "PASS" -Evidence "controlledProcesses=0" -LogPath $processLog
}

function Stage-Upgrade {
    $upgradePath = if ([string]::IsNullOrWhiteSpace($UpgradeSetupPath)) { $SetupPath } else { $UpgradeSetupPath }
    $userData = Get-IsolatedUserDataRoot
    New-DirectoryIfMissing -Path $userData
    $marker = Join-Path $userData "data-preservation-marker.txt"
    "preserve" | Set-Content -LiteralPath $marker -Encoding UTF8
    $log = Invoke-Setup -Path (Normalize-FullPath -Path $upgradePath) -Label "upgrade"
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) { throw "User data marker was not preserved across upgrade" }
    return New-StatusObject -Status "PASS" -Evidence "upgradeExitCode=$($log.ExitCode); markerPreserved=true" -LogPath $log.Path
}

function Stage-Uninstall {
    Stop-LauncherGracefully -TimeoutSeconds 10
    $result = Invoke-Uninstall
    if ($result.ExitCode -ne 0) { throw "Uninstaller failed with exit code $($result.ExitCode). Log: $($result.Path)" }
    return New-StatusObject -Status "PASS" -Evidence "command=$($result.Command); exitCode=$($result.ExitCode)" -LogPath $result.Path
}

function Stage-VerifyRetention {
    $userData = Get-IsolatedUserDataRoot
    if (-not (Test-Path -LiteralPath $userData -PathType Container)) { throw "Isolated user data directory was not retained" }
    if (Test-Path -LiteralPath (Join-Path $script:InstallRoot "ChatbotLauncher.exe")) { throw "Install program files remain after uninstall" }
    return "isolatedUserDataRetained=true"
}

function Stage-VerifyNoResidue {
    $desktop = [Environment]::GetFolderPath("DesktopDirectory")
    $startMenu = [Environment]::GetFolderPath("Programs")
    foreach ($shortcut in @((Join-Path $desktop "Chatbot Trial.lnk"), (Join-Path $startMenu "Chatbot Trial.lnk"))) {
        if (Test-Path -LiteralPath $shortcut -PathType Leaf) { throw "Shortcut remains after uninstall: $shortcut" }
    }
    $processes = @(Get-ProcessDetails)
    $processLog = Write-ProcessEvidence -Name "no-residue" -Processes $processes
    if ($processes.Count -gt 0) { throw "Controlled processes remain after uninstall. Evidence: $processLog" }
    return New-StatusObject -Status "PASS" -Evidence "controlledProcesses=0" -LogPath $processLog
}

try {
    New-DirectoryIfMissing -Path $script:LogRoot
    $script:InstallRoot = Normalize-FullPath -Path $ExpectedInstallRoot

    if ($Phase -eq "All" -or $Phase -eq "Install") {
        Invoke-Stage -Name "PRECHECK" -TimeoutSeconds 30 -Action { Stage-Precheck }
        Invoke-Stage -Name "INSTALL" -TimeoutSeconds 180 -Action { Stage-Install }
        Invoke-Stage -Name "VERIFY_FILES" -TimeoutSeconds 30 -Action { Stage-VerifyFiles }
        Invoke-Stage -Name "VERIFY_SHORTCUTS" -TimeoutSeconds 30 -Action { Stage-VerifyShortcuts }
    }

    if ($Phase -eq "All" -or $Phase -eq "FirstLaunch") {
        $installedConfig = Read-JsonFile -Path (Join-Path $script:InstallRoot "launcher.json")
        $installedStartupTimeoutSeconds = Get-InstalledStartupTimeoutSeconds -Config $installedConfig
        Invoke-Stage -Name "FIRST_LAUNCH" -TimeoutSeconds 30 -Action { Stage-FirstLaunch }
        Invoke-Stage -Name "HEALTH_WAIT" -TimeoutSeconds $installedStartupTimeoutSeconds -Action { Stage-HealthWait }
        Invoke-Stage -Name "RUNTIME_STATUS_WAIT" -TimeoutSeconds $installedStartupTimeoutSeconds -Action { Stage-RuntimeStatusWait }
        Invoke-Stage -Name "ONBOARDING_API" -TimeoutSeconds 60 -Action { Stage-OnboardingApi }
        Invoke-Stage -Name "STOP" -TimeoutSeconds 20 -Action { Stage-Stop }
    }

    if (($Phase -eq "All" -or $Phase -eq "Upgrade") -and -not $SkipUpgrade) {
        Invoke-Stage -Name "UPGRADE" -TimeoutSeconds 180 -Action { Stage-Upgrade }
        Invoke-Stage -Name "RESTART_AFTER_UPGRADE" -TimeoutSeconds 20 -Action { Stage-Stop }
    }

    if (($Phase -eq "All" -or $Phase -eq "Uninstall") -and -not $SkipUninstall) {
        Invoke-Stage -Name "UNINSTALL" -TimeoutSeconds 120 -Action { Stage-Uninstall }
        Invoke-Stage -Name "VERIFY_RETENTION" -TimeoutSeconds 30 -Action { Stage-VerifyRetention }
        Invoke-Stage -Name "VERIFY_NO_RESIDUE" -TimeoutSeconds 30 -Action { Stage-VerifyNoResidue }
    }
}
finally {
    try { Stop-LauncherGracefully -TimeoutSeconds 5 } catch {}
}

$summaryStatus = "PASS"
if (@($script:Results | Where-Object { $_.status -eq "FAIL" }).Count -gt 0) { $summaryStatus = "FAIL" }
elseif (@($script:Results | Where-Object { $_.status -eq "UNVERIFIED" }).Count -gt 0) { $summaryStatus = "UNVERIFIED" }
$summary = [pscustomobject]@{
    status = $summaryStatus
    setupPath = (Normalize-FullPath -Path $SetupPath)
    installRoot = $script:InstallRoot
    sessionRoot = $script:SessionRoot
    logPath = $script:ResultPath
    phase = $Phase
    generatedAtUtc = [DateTime]::UtcNow.ToString("o")
    results = $script:Results
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $script:ResultPath -Encoding UTF8
$summary | ConvertTo-Json -Depth 8
if ($summaryStatus -eq "FAIL") { exit 1 }
exit 0
