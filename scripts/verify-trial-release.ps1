#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ReleasePath,
    [string]$ZipPath,
    [switch]$MinimizedPath,
    [switch]$SkipLaunch,
    [int]$StartupTimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$script:Results = @()
$script:ReleaseRoot = [System.IO.Path]::GetFullPath($ReleasePath).TrimEnd('\')
$script:SessionRoot = Join-Path $env:TEMP ("ChatbotTrialVerify\" + [guid]::NewGuid().ToString("N"))
$script:LogRoot = Join-Path $script:SessionRoot "logs"
$script:ResultPath = Join-Path $script:LogRoot "verify-trial-release-result.json"
$script:ProcessLogPath = Join-Path $script:LogRoot "processes.json"
$script:LauncherProcess = $null

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
    $path = Join-Path $script:ReleaseRoot "launcher.json"
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "launcher.json is missing" }
    $config = Read-Json $path
    foreach ($key in @("host", "port", "healthPath", "runtimeStatusPath")) {
        if (-not ($config.backend.PSObject.Properties.Name -contains $key)) { throw "launcher.json backend missing $key" }
    }
    return $config
}

function Get-MinimizedPathValue {
    $windowsRoot = $env:SystemRoot
    if ([string]::IsNullOrWhiteSpace($windowsRoot)) { $windowsRoot = "C:\Windows" }
    $parts = @(
        (Join-Path $windowsRoot "System32"),
        $windowsRoot,
        (Join-Path $windowsRoot "System32\WindowsPowerShell\v1.0"),
        (Join-Path $script:ReleaseRoot "server\runtime\python"),
        (Join-Path $script:ReleaseRoot "connectors\runtime\python"),
        (Join-Path $script:ReleaseRoot "runtime\desktop-rpa"),
        $script:ReleaseRoot
    )
    $existing = @()
    foreach ($part in $parts) { if ($part -and (Test-Path -LiteralPath $part -PathType Container)) { $existing += (FullPath $part) } }
    return (($existing | Select-Object -Unique) -join ";")
}

function Assert-MinimizedPathSafe([string]$PathValue) {
    foreach ($segment in ($PathValue -split ";")) {
        if ([string]::IsNullOrWhiteSpace($segment)) { continue }
        $insideRelease = Test-UnderRoot $script:ReleaseRoot $segment
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
            $pid = [int]$queue.Dequeue()
            if ($seen.ContainsKey($pid)) { continue }
            $seen[$pid] = $true
            foreach ($proc in ($all | Where-Object { $_.ProcessId -eq $pid })) { $selected += $proc }
            foreach ($child in ($all | Where-Object { $_.ParentProcessId -eq $pid })) { $queue.Enqueue([int]$child.ProcessId) }
        }
    }
    else {
        $selected = $all | Where-Object {
            ($_.ExecutablePath -and (Test-UnderRoot $script:ReleaseRoot $_.ExecutablePath)) -or
            ($_.CommandLine -and $_.CommandLine.IndexOf($script:ReleaseRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
        }
    }
    return @($selected | Select-Object @{n="pid";e={$_.ProcessId}}, @{n="parentPid";e={$_.ParentProcessId}}, @{n="name";e={$_.Name}}, @{n="executablePath";e={$_.ExecutablePath}}, @{n="commandLine";e={$_.CommandLine}}, @{n="creationTime";e={$_.CreationDate}})
}

function Write-ProcessEvidence([object[]]$Processes) {
    $Processes | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $script:ProcessLogPath -Encoding UTF8
    return $script:ProcessLogPath
}

function Assert-NoForbiddenTools([object[]]$Processes) {
    foreach ($proc in $Processes) {
        $name = [string]$proc.name
        $path = [string]$proc.executablePath
        if ($name -match '^(python|pythonw)\.exe$') {
            $serverRuntime = Join-Path $script:ReleaseRoot "server\runtime"
            $connectorRuntime = Join-Path $script:ReleaseRoot "connectors\runtime"
            if (-not (Test-UnderRoot $serverRuntime $path) -and -not (Test-UnderRoot $connectorRuntime $path)) { throw "Python process is outside packaged runtimes: pid=$($proc.pid) path=$path" }
        }
        if ($name -match '^node\.exe$') { throw "System node.exe was used: pid=$($proc.pid) path=$path" }
        if ($name -match '^(uv|pnpm|git)\.exe$') { throw "Development tool process was used: pid=$($proc.pid) path=$path" }
    }
}

function Stop-ControlledProcesses([string]$Reason = "verify-cleanup") {
    $shutdownPath = Join-Path $script:SessionRoot "UserData\runtime\backend-shutdown.json"
    Ensure-Directory (Split-Path -Parent $shutdownPath)
    @{ action = "shutdown"; reason = $Reason; requestedAtUtc = [DateTime]::UtcNow.ToString("o") } | ConvertTo-Json | Set-Content -LiteralPath $shutdownPath -Encoding UTF8
    Start-Sleep -Seconds 2
    if ($script:LauncherProcess -and -not $script:LauncherProcess.HasExited) {
        try { $script:LauncherProcess.CloseMainWindow() | Out-Null } catch {}
        Start-Sleep -Seconds 1
        if (-not $script:LauncherProcess.HasExited) { try { $script:LauncherProcess.Kill() } catch {} }
    }
}

function Wait-Http([string]$Uri, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $last = ""
    while ((Get-Date) -lt $deadline) {
        try { return Invoke-RestMethod -Uri $Uri -TimeoutSec 3 }
        catch { $last = $_.Exception.Message; Start-Sleep -Milliseconds 500 }
    }
    throw "Timed out waiting for $Uri. Last error: $last"
}

function Test-PortableStructure {
    $required = @(
        "ChatbotLauncher.exe", "launcher.json", "manifest.json", "build-report.json", "build-sensitive-scan.json",
        "server\runtime", "server\app", "connectors\runtime", "connectors\app\wechat-decrypt",
        "resources\web\dist\index.html", "runtime\desktop-rpa", "licenses"
    )
    $missing = @()
    foreach ($relative in $required) { if (-not (Test-Path -LiteralPath (Join-Path $script:ReleaseRoot $relative))) { $missing += $relative } }
    if ($missing.Count -gt 0) { throw "Missing required portable paths: $($missing -join ', ')" }
    return "Required portable paths are present."
}

function Test-LauncherConfiguration {
    $config = Get-LauncherConfig
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
    foreach ($entry in $critical) {
        $relative = ([string]$entry.path).Replace('/', '\')
        if ([System.IO.Path]::IsPathRooted($relative) -or $relative -match '(^|\\)\.\.(\\|$)') { throw "Unsafe manifest path: $($entry.path)" }
        $path = Join-Path $script:ReleaseRoot $relative
        Assert-UnderRoot $script:ReleaseRoot $path "Manifest entry escaped release root"
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Critical manifest file is missing: $($entry.path)" }
        if ((Sha256 $path) -ne ([string]$entry.sha256).ToLowerInvariant()) { throw "Critical manifest hash mismatch: $($entry.path)" }
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
        return New-StatusObject "UNVERIFIED" "files=$checked; zipSha256=$zipHash" "" "ZIP exists and was hashed; release SHA256SUMS covers portable contents only."
    }
    return "files=$checked"
}

function Test-ZipContents {
    if (-not $ZipPath) { return New-StatusObject "UNVERIFIED" "" "" "ZipPath was not provided." }
    $zipFull = FullPath $ZipPath
    if (-not (Test-Path -LiteralPath $zipFull -PathType Leaf)) { throw "ZipPath does not exist: $zipFull" }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($zipFull)
    try {
        $names = @($zip.Entries | ForEach-Object { $_.FullName.Replace('/', '\') })
        $root = Split-Path -Leaf $script:ReleaseRoot
        foreach ($relative in @("ChatbotLauncher.exe", "launcher.json", "manifest.json", "resources\web\dist\index.html")) {
            $expected = $root + "\" + $relative
            if (-not ($names -contains $expected)) { throw "ZIP missing entry: $expected" }
        }
        return "zipEntries=$($names.Count)"
    }
    finally { $zip.Dispose() }
}

function Test-SensitiveScan {
    $path = Join-Path $script:ReleaseRoot "build-sensitive-scan.json"
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
    foreach ($pattern in @("*.db", "*.sqlite", "*.sqlite3")) {
        $bad += @(Get-ChildItem -LiteralPath $script:ReleaseRoot -Force -File -Recurse -Filter $pattern -ErrorAction SilentlyContinue | ForEach-Object { RelPath $_.FullName })
    }
    $bad += @(Get-ChildItem -LiteralPath $script:ReleaseRoot -Force -Recurse -ErrorAction SilentlyContinue | Where-Object {
        $rel = (RelPath $_.FullName)
        $rel -match '(?i)(^logs(/|$)|launcher-state\.json|runtime-state|WeChat Files|Desktop backup)'
    } | ForEach-Object { RelPath $_.FullName })
    if ($bad.Count -gt 0) { $sample = (($bad | Select-Object -First 20) -join ', '); throw "Forbidden release content found: $sample" }
    $textExtensions = @(".json", ".txt", ".yaml", ".yml", ".py", ".md", ".html", ".js", ".css", ".xml", ".config")
    $leaks = @()
    foreach ($file in Get-ChildItem -LiteralPath $script:ReleaseRoot -Force -File -Recurse -ErrorAction SilentlyContinue) {
        if ($textExtensions -notcontains $file.Extension.ToLowerInvariant()) { continue }
        if ($file.Length -gt 1048576) { continue }
        $content = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($content -match 'C:\\Users\\|Desktop\\bot|Desktop backup\\|WeChat Files\\') { $leaks += (RelPath $file.FullName) }
    }
    if ($leaks.Count -gt 0) { throw "Forbidden absolute/developer paths found: $($leaks -join ', ')" }
    return "No forbidden content detected."
}

function Test-SafetyDefaults {
    $required = @("LANGBOT_BROADCAST_SEND_ENABLED", "LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS", "LANGBOT_RPA_ALLOW_AUTO_SEND", "LANGBOT_RPA_FORCE_DISABLE_SEND")
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
    $python = Join-Path $script:ReleaseRoot "connectors\runtime\python\python.exe"
    $appDir = Join-Path $script:ReleaseRoot "connectors\app\wechat-decrypt"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "connector python missing" }
    Assert-UnderRoot (Join-Path $script:ReleaseRoot "connectors\runtime") $python "Connector python escaped runtime"
    if (-not (Test-Path -LiteralPath (Join-Path $appDir "connector_runtime.py") -PathType Leaf)) { throw "connector_runtime.py missing" }
    $stdout = Join-Path $script:LogRoot "connector-smoke-stdout.json"
    $stderr = Join-Path $script:LogRoot "connector-smoke-stderr.txt"
    $smokeScript = Join-Path $script:LogRoot "connector-smoke.py"
    @"
import json
import pathlib
import sys
sys.path.insert(0, r'''$appDir''')
import connector_runtime
print(json.dumps({
    'ok': True,
    'action': 'smoke',
    'executable': sys.executable,
    'module': str(pathlib.Path(connector_runtime.__file__).resolve()),
}, ensure_ascii=False))
"@ | Set-Content -LiteralPath $smokeScript -Encoding UTF8
    $proc = Start-Process -FilePath $python -ArgumentList @("-X", "utf8", $smokeScript) -WorkingDirectory $appDir -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
    if (-not $proc.WaitForExit(30000)) { try { $proc.Kill() } catch {}; throw "connector smoke process timed out" }
    $proc.Refresh()
    if ($null -eq $proc.ExitCode) { $proc.WaitForExit(); $proc.Refresh() }
    $exitCode = $proc.ExitCode
    if ($null -eq $exitCode -and (Test-Path -LiteralPath $stdout -PathType Leaf) -and ((Get-Item -LiteralPath $stdout).Length -gt 0)) { $exitCode = 0 }
    if ($exitCode -ne 0) { $err = Get-Content -LiteralPath $stderr -Raw -ErrorAction SilentlyContinue; throw "connector smoke failed with exit code $exitCode`: $err" }
    $payload = Read-Json $stdout
    if ($payload.ok -ne $true) { throw "connector smoke payload was not ok" }
    if (-not (Test-UnderRoot (Join-Path $script:ReleaseRoot "connectors\runtime") ([string]$payload.executable))) { throw "connector smoke used python outside connector runtime: $($payload.executable)" }
    if (-not (Test-UnderRoot $appDir ([string]$payload.module))) { throw "connector smoke imported module outside connector app: $($payload.module)" }
    return New-StatusObject "PASS" "pid=$($proc.Id); executable=$($payload.executable); module=$($payload.module)" $stdout ""
}

function Test-MinimizedPathMode {
    if (-not $MinimizedPath) { return New-StatusObject "UNVERIFIED" "" "" "MinimizedPath was not specified." }
    $value = Get-MinimizedPathValue
    Assert-MinimizedPathSafe $value
    return "PATH=$value"
}

function Invoke-LauncherVerification {
    if ($SkipLaunch) { return New-StatusObject "UNVERIFIED" "" "" "SkipLaunch was specified." }
    $config = Get-LauncherConfig
    $host = [string]$config.backend.host
    $port = [int]$config.backend.port
    $userData = Join-Path $script:SessionRoot "UserData"
    Ensure-Directory $userData
    $pathValue = $env:Path
    if ($MinimizedPath) { $pathValue = Get-MinimizedPathValue; Assert-MinimizedPathSafe $pathValue }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = Join-Path $script:ReleaseRoot "ChatbotLauncher.exe"
    $psi.WorkingDirectory = $script:ReleaseRoot
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.EnvironmentVariables["LOCALAPPDATA"] = $userData
    $psi.EnvironmentVariables["CHATBOT_USER_DATA_ROOT"] = $userData
    $psi.EnvironmentVariables["LANGBOT_DATA_ROOT"] = Join-Path $userData "data"
    $psi.EnvironmentVariables["LANGBOT_BROADCAST_SEND_ENABLED"] = "0"
    $psi.EnvironmentVariables["LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS"] = ""
    $psi.EnvironmentVariables["LANGBOT_RPA_ALLOW_AUTO_SEND"] = "0"
    $psi.EnvironmentVariables["LANGBOT_RPA_FORCE_DISABLE_SEND"] = "1"
    if ($MinimizedPath) { $psi.EnvironmentVariables["PATH"] = $pathValue }
    $script:LauncherProcess = [System.Diagnostics.Process]::Start($psi)
    try {
        $healthUri = "http://${host}:$port$($config.backend.healthPath)"
        $statusUri = "http://${host}:$port$($config.backend.runtimeStatusPath)"
        $health = Wait-Http $healthUri $StartupTimeoutSeconds
        $healthJson = $health | ConvertTo-Json -Compress
        if ($healthJson -notmatch '"code"\s*:\s*0' -and $healthJson -notmatch '"msg"\s*:\s*"ok"') { throw "health response did not match expected semantics: $healthJson" }
        $home = Invoke-WebRequest -Uri "http://${host}:$port/" -UseBasicParsing -TimeoutSec 10
        if ([int]$home.StatusCode -ne 200 -or $home.Content -notmatch '<html|<div|root') { throw "frontend home did not return expected HTML" }
        $spa = Invoke-WebRequest -Uri "http://${host}:$port/apps" -UseBasicParsing -TimeoutSec 10
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
    finally { Stop-ControlledProcesses "verify-launcher" }
}

function Test-PortConflict {
    if ($SkipLaunch) { return New-StatusObject "UNVERIFIED" "" "" "SkipLaunch was specified." }
    $config = Get-LauncherConfig
    $port = [int]$config.backend.port
    $listener = New-Object System.Net.Sockets.TcpListener ([System.Net.IPAddress]::Parse("127.0.0.1"), $port)
    $listener.Start()
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = Join-Path $script:ReleaseRoot "ChatbotLauncher.exe"
        $psi.WorkingDirectory = $script:ReleaseRoot
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $psi.EnvironmentVariables["LOCALAPPDATA"] = Join-Path $script:SessionRoot "PortConflictUserData"
        $proc = [System.Diagnostics.Process]::Start($psi)
        Start-Sleep -Seconds 8
        try { if (@(Get-NetTCPConnection -State Listen -LocalPort 3000 -ErrorAction SilentlyContinue).Count -gt 0) { throw "launcher started development port 3000 during port conflict" } } catch [System.Management.Automation.CommandNotFoundException] {}
        if (-not $proc.HasExited) { try { $proc.Kill() } catch {} }
        return "Port $port was occupied; launcher did not switch to port 3000."
    }
    finally { $listener.Stop() }
}

function Test-NoResidualProcesses {
    $processes = @(Get-ControlledProcesses)
    $processLog = Write-ProcessEvidence $processes
    if ($processes.Count -gt 0) {
        $pids = (($processes | ForEach-Object { $_.pid }) -join ', ')
        throw "Controlled release processes remain: $pids"
    }
    return New-StatusObject "PASS" "No controlled processes remain." $processLog ""
}

try {
    Ensure-Directory $script:LogRoot
    if (-not (Test-Path -LiteralPath $script:ReleaseRoot -PathType Container)) { throw "ReleasePath does not exist: $script:ReleaseRoot" }
    Invoke-Check "portable-structure" { Test-PortableStructure }
    Invoke-Check "launcher-config" { Test-LauncherConfiguration }
    Invoke-Check "manifest-critical-sha" { Test-Manifest }
    Invoke-Check "sha256sums" { Test-Sha256Sums }
    Invoke-Check "zip-contents" { Test-ZipContents }
    Invoke-Check "sensitive-scan" { Test-SensitiveScan }
    Invoke-Check "forbidden-content" { Test-ForbiddenContent }
    Invoke-Check "real-send-defaults" { Test-SafetyDefaults }
    Invoke-Check "connector-smoke" { Invoke-ConnectorSmoke }
    Invoke-Check "minimized-path" { Test-MinimizedPathMode }
    Invoke-Check "launcher-runtime" { Invoke-LauncherVerification }
    Invoke-Check "port-conflict" { Test-PortConflict }
    Invoke-Check "no-residual-processes" { Test-NoResidualProcesses }
}
finally {
    try { Stop-ControlledProcesses "verify-finally" } catch {}
}

$summaryStatus = "PASS"
if (@($script:Results | Where-Object { $_.status -eq "FAIL" }).Count -gt 0) { $summaryStatus = "FAIL" }
elseif (@($script:Results | Where-Object { $_.status -eq "UNVERIFIED" }).Count -gt 0) { $summaryStatus = "UNVERIFIED" }
$summary = [pscustomobject]@{
    status = $summaryStatus
    releasePath = $script:ReleaseRoot
    zipPath = $ZipPath
    sessionRoot = $script:SessionRoot
    logPath = $script:ResultPath
    generatedAtUtc = [DateTime]::UtcNow.ToString("o")
    results = $script:Results
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $script:ResultPath -Encoding UTF8
$summary | ConvertTo-Json -Depth 8
if ($summaryStatus -eq "FAIL") { exit 1 }
exit 0
