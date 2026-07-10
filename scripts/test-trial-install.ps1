#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SetupPath,

    [string]$ExpectedInstallRoot = "$env:LOCALAPPDATA\Programs\Chatbot",

    [string]$UpgradeSetupPath,

    [switch]$Silent,

    [int]$StartupTimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$script:Results = @()
$script:SessionRoot = Join-Path $env:TEMP ("ChatbotTrialInstallVerify\" + [guid]::NewGuid().ToString("N"))
$script:LogRoot = Join-Path $script:SessionRoot "logs"
$script:ResultPath = Join-Path $script:LogRoot "test-trial-install-result.json"
$script:ProcessLogPath = Join-Path $script:LogRoot "processes.json"
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

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash).ToLowerInvariant()
}

function Read-JsonFile {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Add-VerificationResult {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][ValidateSet("PASS", "FAIL", "UNVERIFIED")][string]$Status,
        [string]$Evidence = "",
        [string]$LogPath = "",
        [string]$Message = "",
        [double]$DurationSeconds = 0
    )
    $script:Results += [pscustomobject]@{
        name = $Name
        status = $Status
        durationSeconds = [Math]::Round($DurationSeconds, 3)
        evidence = $Evidence
        logPath = $LogPath
        message = $Message
    }
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

function Invoke-Check {
    param([Parameter(Mandatory = $true)][string]$Name, [Parameter(Mandatory = $true)][scriptblock]$Action)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $value = & $Action
        $sw.Stop()
        if ($null -ne $value -and $value.PSObject.Properties.Name -contains "Status") {
            Add-VerificationResult -Name $Name -Status $value.Status -Evidence ([string]$value.Evidence) -LogPath ([string]$value.LogPath) -Message ([string]$value.Message) -DurationSeconds $sw.Elapsed.TotalSeconds
        }
        else {
            Add-VerificationResult -Name $Name -Status "PASS" -Evidence ([string]$value) -DurationSeconds $sw.Elapsed.TotalSeconds
        }
    }
    catch {
        $sw.Stop()
        Add-VerificationResult -Name $Name -Status "FAIL" -Message $_.Exception.Message -DurationSeconds $sw.Elapsed.TotalSeconds
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
            $pid = [int]$queue.Dequeue()
            if ($seen.ContainsKey($pid)) { continue }
            $seen[$pid] = $true
            foreach ($item in ($all | Where-Object { $_.ProcessId -eq $pid })) { $selected += $item }
            foreach ($child in ($all | Where-Object { $_.ParentProcessId -eq $pid })) { $queue.Enqueue([int]$child.ProcessId) }
        }
    }
    else {
        $selected = $all | Where-Object {
            ($_.ExecutablePath -and $script:InstallRoot -and (Test-PathUnderRoot -Root $script:InstallRoot -Path $_.ExecutablePath))
        }
    }
    return @($selected | Select-Object @{n="pid";e={$_.ProcessId}}, @{n="parentPid";e={$_.ParentProcessId}}, @{n="name";e={$_.Name}}, @{n="executablePath";e={$_.ExecutablePath}}, @{n="commandLine";e={$_.CommandLine}}, @{n="creationTime";e={$_.CreationDate}})
}

function Write-ProcessEvidence {
    param([object[]]$Processes)
    $Processes | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $script:ProcessLogPath -Encoding UTF8
    return $script:ProcessLogPath
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
                if ($displayName -like "Chatbot Trial*" -or $installLocation -eq $script:InstallRoot) { return $props }
            }
        }
    }
    return $null
}

function Get-ShortcutEvidence {
    $desktop = [Environment]::GetFolderPath("DesktopDirectory")
    $startMenu = [Environment]::GetFolderPath("Programs")
    $shortcuts = @(
        (Join-Path $desktop "Chatbot Trial.lnk"),
        (Join-Path $startMenu "Chatbot Trial.lnk")
    )
    $missing = @()
    foreach ($shortcut in $shortcuts) {
        if (-not (Test-Path -LiteralPath $shortcut -PathType Leaf)) { $missing += $shortcut }
    }
    if ($missing.Count -gt 0) { throw "Missing shortcuts: $($missing -join ', ')" }
    return $shortcuts
}

function Start-LauncherFromShortcutTarget {
    $shortcuts = Get-ShortcutEvidence
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($shortcuts[0])
    $target = [string]$link.TargetPath
    if (-not (Test-PathUnderRoot -Root $script:InstallRoot -Path $target)) { throw "Shortcut target is outside install root: $target" }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $target
    $psi.WorkingDirectory = $script:InstallRoot
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $isolatedLocalAppData = Join-Path $script:SessionRoot "LocalAppData"
    New-DirectoryIfMissing -Path $isolatedLocalAppData
    $psi.EnvironmentVariables["LOCALAPPDATA"] = $isolatedLocalAppData
    $psi.EnvironmentVariables["CHATBOT_USER_DATA_ROOT"] = Join-Path $isolatedLocalAppData "Chatbot"
    $psi.EnvironmentVariables["LANGBOT_BROADCAST_SEND_ENABLED"] = "0"
    $psi.EnvironmentVariables["LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS"] = ""
    $psi.EnvironmentVariables["LANGBOT_RPA_ALLOW_AUTO_SEND"] = "0"
    $psi.EnvironmentVariables["LANGBOT_RPA_FORCE_DISABLE_SEND"] = "1"
    $script:LauncherProcess = [System.Diagnostics.Process]::Start($psi)
    return $script:LauncherProcess
}

function Wait-ForHttpReady {
    param([Parameter(Mandatory = $true)][string]$Uri, [int]$TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = ""
    while ((Get-Date) -lt $deadline) {
        try { return Invoke-RestMethod -Uri $Uri -TimeoutSec 3 }
        catch { $lastError = $_.Exception.Message; Start-Sleep -Milliseconds 500 }
    }
    throw "Timed out waiting for $Uri. Last error: $lastError"
}

function Stop-Launcher {
    $localAppData = Join-Path $script:SessionRoot "LocalAppData"
    $shutdown = Join-Path $localAppData "Chatbot\runtime\backend-shutdown.json"
    New-DirectoryIfMissing -Path (Split-Path -Parent $shutdown)
    @{ action = "shutdown"; reason = "install-verify"; requestedAtUtc = [DateTime]::UtcNow.ToString("o") } | ConvertTo-Json | Set-Content -LiteralPath $shutdown -Encoding UTF8
    Start-Sleep -Seconds 3
    if ($script:LauncherProcess -and -not $script:LauncherProcess.HasExited) {
        try { $script:LauncherProcess.CloseMainWindow() | Out-Null } catch {}
        Start-Sleep -Seconds 2
        if (-not $script:LauncherProcess.HasExited) { try { $script:LauncherProcess.Kill() } catch {} }
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
    return $log
}

function Test-SetupFile {
    $full = Normalize-FullPath -Path $SetupPath
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { throw "SetupPath does not exist: $full" }
    return "setupSha256=$(Get-Sha256 -Path $full); path=$full"
}

function Test-InstallBeforeState {
    Assert-TestInstallRootSafe -Path $script:InstallRoot
    $processes = @(Get-ProcessDetails)
    $processLog = Write-ProcessEvidence -Processes $processes
    if ($processes.Count -gt 0) { throw "Controlled processes already running for install root" }
    return New-StatusObject -Status "PASS" -Evidence "installRootExists=$(Test-Path -LiteralPath $script:InstallRoot); userDataRoot=$env:LOCALAPPDATA\Chatbot" -LogPath $processLog
}

function Test-InstallFlow {
    $log = Invoke-Setup -Path (Normalize-FullPath -Path $SetupPath) -Label "install"
    foreach ($relative in @("ChatbotLauncher.exe", "launcher.json", "manifest.json")) {
        if (-not (Test-Path -LiteralPath (Join-Path $script:InstallRoot $relative) -PathType Leaf)) { throw "Installed file missing: $relative" }
    }
    Get-ShortcutEvidence | Out-Null
    $entry = Find-UninstallEntry
    if ($null -eq $entry) { throw "Uninstall entry was not found" }
    return New-StatusObject -Status "PASS" -Evidence "installRoot=$script:InstallRoot; uninstall=$($entry.UninstallString)" -LogPath $log
}

function Test-VcPrerequisiteBehavior {
    $iss = Join-Path (Split-Path -Parent $PSScriptRoot) "packaging\installer\ChatbotTrial.iss"
    if (Test-Path -LiteralPath $iss -PathType Leaf) {
        $content = Get-Content -LiteralPath $iss -Raw -Encoding UTF8
        if ($content -notmatch "vc_redist\.x64\.exe" -or $content -notmatch "ShouldRunVcRedist") { throw "Installer spec lacks VC++ prerequisite gating" }
        if ($content -notmatch "1223|UAC|MB_YESNO|PrivilegesRequired=lowest") {
            return New-StatusObject -Status "UNVERIFIED" -Evidence "VC++ prerequisite is gated by installer spec." -Message "VC++ missing/UAC-cancel simulation was not run on this machine."
        }
        return New-StatusObject -Status "UNVERIFIED" -Evidence "VC++ prerequisite is defined in installer spec." -Message "VC++ missing/UAC-cancel simulation requires a clean machine snapshot."
    }
    return New-StatusObject -Status "UNVERIFIED" -Message "Installer source spec is unavailable during installed-package verification."
}

function Test-FirstLaunchFromShortcut {
    $config = Read-JsonFile -Path (Join-Path $script:InstallRoot "launcher.json")
    $backendHost = [string]$config.backend.host
    $port = [int]$config.backend.port
    $healthUri = "http://${backendHost}:$port$($config.backend.healthPath)"
    $statusUri = "http://${backendHost}:$port$($config.backend.runtimeStatusPath)"
    $proc = Start-LauncherFromShortcutTarget
    try {
        $health = Wait-ForHttpReady -Uri $healthUri -TimeoutSeconds $StartupTimeoutSeconds
        $healthJson = $health | ConvertTo-Json -Compress
        $status = Invoke-RestMethod -Uri $statusUri -TimeoutSec 10
        $statusJson = $status | ConvertTo-Json -Compress
        if ($statusJson -match '"send_enabled"\s*:\s*true') { throw "real send is enabled" }
        $processes = Get-ProcessDetails -ProcessIds @($proc.Id)
        $log = Write-ProcessEvidence -Processes $processes
        return New-StatusObject -Status "PASS" -Evidence "launcherPid=$($proc.Id); health=$healthJson; runtime=$statusJson" -LogPath $log
    }
    finally {
        Stop-Launcher
    }
}

function Test-UpgradeFlow {
    $path = $SetupPath
    if (-not [string]::IsNullOrWhiteSpace($UpgradeSetupPath)) { $path = $UpgradeSetupPath }
    $userData = Join-Path $script:SessionRoot "LocalAppData\Chatbot"
    New-DirectoryIfMissing -Path $userData
    $marker = Join-Path $userData "data-preservation-marker.txt"
    "preserve" | Set-Content -LiteralPath $marker -Encoding UTF8
    $log = Invoke-Setup -Path (Normalize-FullPath -Path $path) -Label "upgrade"
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) { throw "User data marker was not preserved across upgrade" }
    return New-StatusObject -Status "PASS" -Evidence "upgradeSetup=$path; markerPreserved=true" -LogPath $log
}

function Test-UninstallFlow {
    $entry = Find-UninstallEntry
    if ($null -eq $entry) { throw "Uninstall entry not found before uninstall" }
    $uninstall = [string]$entry.UninstallString
    if ([string]::IsNullOrWhiteSpace($uninstall)) { throw "UninstallString is empty" }
    $exe = $uninstall
    $baseArgs = @()
    if ($uninstall.StartsWith('"')) {
        $second = $uninstall.IndexOf('"', 1)
        $exe = $uninstall.Substring(1, $second - 1)
        $remaining = $uninstall.Substring($second + 1).Trim()
        if ($remaining) { $baseArgs += $remaining }
    }
    $args = $baseArgs + @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")
    $proc = Start-Process -FilePath $exe -ArgumentList $args -Wait -PassThru -WindowStyle Hidden
    if ($proc.ExitCode -ne 0) { throw "Uninstaller failed with exit code $($proc.ExitCode)" }
    Start-Sleep -Seconds 2
    if (Test-Path -LiteralPath (Join-Path $script:InstallRoot "ChatbotLauncher.exe")) { throw "Install program files remain after uninstall" }
    $userData = Join-Path $script:SessionRoot "LocalAppData\Chatbot"
    $retained = Test-Path -LiteralPath $userData
    $processes = @(Get-ProcessDetails)
    $log = Write-ProcessEvidence -Processes $processes
    if ($processes.Count -gt 0) { throw "Controlled processes remain after uninstall" }
    return New-StatusObject -Status "PASS" -Evidence "programFilesRemoved=true; isolatedUserDataRetained=$retained" -LogPath $log
}

try {
    New-DirectoryIfMissing -Path $script:LogRoot
    $script:InstallRoot = Normalize-FullPath -Path $ExpectedInstallRoot
    Invoke-Check -Name "setup-file" -Action { Test-SetupFile }
    Invoke-Check -Name "preinstall-state" -Action { Test-InstallBeforeState }
    Invoke-Check -Name "install" -Action { Test-InstallFlow }
    Invoke-Check -Name "vc-prerequisite" -Action { Test-VcPrerequisiteBehavior }
    Invoke-Check -Name "first-launch-shortcut" -Action { Test-FirstLaunchFromShortcut }
    Invoke-Check -Name "upgrade" -Action { Test-UpgradeFlow }
    Invoke-Check -Name "uninstall-user-data-retention" -Action { Test-UninstallFlow }
}
finally {
    try { Stop-Launcher } catch {}
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
    generatedAtUtc = [DateTime]::UtcNow.ToString("o")
    results = $script:Results
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $script:ResultPath -Encoding UTF8
$summary | ConvertTo-Json -Depth 8
if ($summaryStatus -eq "FAIL") { exit 1 }
exit 0
