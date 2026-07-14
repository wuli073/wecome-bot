#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$UserDataRoot,
    [int]$BackendPort = 5300,
    [int]$WebPort = 3000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $UserDataRoot) { $UserDataRoot = Join-Path $repoRoot '.tmp\source-runtime\user-data' }
$userDataRoot = [IO.Path]::GetFullPath($UserDataRoot)
$statePath = Join-Path $userDataRoot 'runtime\source-stack-state.json'
$baseUrl = "http://127.0.0.1:$BackendPort"
$runtimeExecutable = Join-Path $repoRoot 'apps\desktop-rpa-runtime\dist-phase2-official\win-dir\win-unpacked\LangBot Desktop RPA Runtime.exe'
$results = [System.Collections.Generic.List[object]]::new()
. (Join-Path $PSScriptRoot 'source-state.ps1')

function Add-Result([string]$Name, [ValidateSet('pass', 'warn', 'fail')][string]$Status, [string]$Detail) {
    $results.Add([pscustomobject]@{ check=$Name; status=$Status; detail=$Detail })
}
function Get-PortOwner([int]$Port) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }; return $null
}
function Test-HttpJson([string]$Path) {
    try { return Invoke-RestMethod -Uri "$baseUrl$Path" -Method Get -TimeoutSec 5 } catch { return $null }
}

try {
    $node = Get-Command node.exe -ErrorAction Stop
    $nodeVersion = (& $node.Source --version).Trim()
    Add-Result 'node' $(if ($nodeVersion -match '^v22\.') {'pass'} else {'fail'}) $nodeVersion
}
catch { Add-Result 'node' 'fail' $_.Exception.Message }
foreach ($name in @('git.exe', 'npm.cmd', 'uv.exe')) {
    try { $cmd = Get-Command $name -ErrorAction Stop; $version = (& $cmd.Source --version 2>&1 | Select-Object -First 1).ToString().Trim(); Add-Result $name 'pass' $version }
    catch { Add-Result $name 'fail' $_.Exception.Message }
}
foreach ($path in @(
    (Join-Path $repoRoot 'uv.lock'),
    (Join-Path $repoRoot 'web\package-lock.json'),
    (Join-Path $repoRoot '.venv\Scripts\python.exe'),
    (Join-Path $repoRoot 'web\node_modules\vite\bin\vite.js'),
    (Join-Path $repoRoot 'apps\desktop-rpa-runtime\package.json'),
    (Join-Path $repoRoot 'apps\desktop-rpa-runtime\package-lock.json'),
    $runtimeExecutable,
    (Join-Path $repoRoot 'vendor\wechat_decrypt\connector_runtime.py'),
    (Join-Path $repoRoot 'vendor\wechat_decrypt\mcp_wxwork_http_server.py'),
    (Join-Path $repoRoot 'vendor\wechat_decrypt\wxwork_message_monitor.py')
)) { Add-Result "path:$([IO.Path]::GetFileName($path))" $(if (Test-Path -LiteralPath $path) {'pass'} else {'fail'}) $path }

foreach ($port in @($BackendPort, $WebPort, 5681)) {
    $owner = Get-PortOwner $port
    $status = if ($owner) { 'warn' } elseif ($port -eq 5681) { 'warn' } else { 'pass' }
    $detail = if ($owner) { "listening PID $owner" } elseif ($port -eq 5681) { 'not listening; expected until a configured wxwork-local worker is started' } else { 'available' }
    Add-Result "port:$port" $status $detail
}

$state = Read-ManagedSourceState $statePath
if ($null -eq $state) { Add-Result 'managed-source-stack' 'warn' "not started; state=$statePath" }
else {
    $backend = Get-ManagedSourceStateProperty -Object $state -Name 'backend'
    $web = Get-ManagedSourceStateProperty -Object $state -Name 'web'
    $runtime = Get-ManagedSourceStateProperty -Object $state -Name 'runtime'
    Add-Result 'managed-source-stack' 'pass' "backend PID $(Get-ManagedSourceStateProperty -Object $backend -Name 'pid'), web PID $(Get-ManagedSourceStateProperty -Object $web -Name 'pid'), runtime PID $(Get-ManagedSourceStateProperty -Object $runtime -Name 'pid'), logs $(Get-ManagedSourceStateProperty -Object $state -Name 'logsRoot')"
}

$health = Test-HttpJson '/healthz'; $runtime = Test-HttpJson '/api/v1/system/runtime/status'; $ready = Test-HttpJson '/readyz'
Add-Result 'health' $(if ($health -and $health.code -eq 0) {'pass'} else {'fail'}) $(if ($health) { "state=$($health.state)" } else { 'endpoint unavailable' })
Add-Result 'runtime' $(if ($runtime -and $runtime.state -in @('CORE_READY', 'READY', 'DEGRADED')) {'pass'} else {'fail'}) $(if ($runtime) { "state=$($runtime.state)" } else { 'endpoint unavailable' })
Add-Result 'ready' $(if ($ready -and $ready.state -in @('CORE_READY', 'READY', 'DEGRADED')) {'pass'} else {'fail'}) $(if ($ready) { "state=$($ready.state)" } else { 'endpoint unavailable' })

$desktopRuntimeResponse = Test-HttpJson '/api/v1/desktop-automation/runtime/status'
$runtimeData = Get-ManagedSourceStateProperty -Object $desktopRuntimeResponse -Name 'data'
$desktopRuntime = if ($null -ne $runtimeData) { $runtimeData } else { $desktopRuntimeResponse }
if ($null -eq $desktopRuntime) {
    Add-Result 'desktop-runtime' 'fail' 'RUNTIME_CONNECTION_FAILED: status endpoint unavailable'
    Add-Result 'desktop-runtime-paste' 'fail' 'RUNTIME_CONNECTION_FAILED'
    Add-Result 'desktop-runtime-send' 'fail' 'RUNTIME_CONNECTION_FAILED'
}
else {
    $runtimeCode = [string](Get-ManagedSourceStateProperty -Object $desktopRuntime -Name 'errorCode')
    $runtimeStatus = [string](Get-ManagedSourceStateProperty -Object $desktopRuntime -Name 'status')
    $runtimeReachable = Get-ManagedSourceStateProperty -Object $desktopRuntime -Name 'runtime_reachable'
    $runtimeVersion = Get-ManagedSourceStateProperty -Object $desktopRuntime -Name 'runtimeVersion'
    $runtimeReady = $runtimeStatus -eq 'ready' -and $runtimeReachable -eq $true
    $runtimeDetail = "status=$runtimeStatus; code=$runtimeCode; version=$runtimeVersion; logs=$(Join-Path $userDataRoot 'logs\source')"
    Add-Result 'desktop-runtime' $(if ($runtimeReady) {'pass'} else {'fail'}) $(if ($runtimeReady) { $runtimeDetail } elseif ($runtimeCode) { $runtimeDetail } elseif (-not (Test-Path -LiteralPath $runtimeExecutable)) { 'RUNTIME_NOT_INSTALLED: runtime executable is missing' } else { 'RUNTIME_CONNECTION_FAILED: runtime is not reachable' })
    $pasteReady = $runtimeReady -and (Get-ManagedSourceStateProperty -Object $desktopRuntime -Name 'inputAvailable') -eq $true
    $sendReady = $runtimeReady -and (Get-ManagedSourceStateProperty -Object $desktopRuntime -Name 'send_enabled') -eq $true
    Add-Result 'desktop-runtime-paste' $(if ($pasteReady) {'pass'} else {'fail'}) $(if ($pasteReady) {'Paste: enabled'} else {'RUNTIME_CAPABILITY_UNAVAILABLE: paste capability is unavailable'})
    Add-Result 'desktop-runtime-send' $(if ($sendReady) {'pass'} else {'fail'}) $(if ($sendReady) {'Send: enabled'} else {'RUNTIME_CAPABILITY_UNAVAILABLE: send capability is unavailable'})
}

$adapters = Test-HttpJson '/api/v1/platform/adapters'
if ($adapters -and $adapters.code -eq 0 -and @($adapters.data.adapters).Count -gt 0) { Add-Result 'platform-list' 'pass' "adapters=$(@($adapters.data.adapters).Count)" } else { Add-Result 'platform-list' 'fail' 'platform adapter API unavailable or empty' }

$connectorRoot = Join-Path $userDataRoot 'connectors\wxwork-local'
$workerState = Join-Path $connectorRoot 'process.mcp.json'
$workerDetail = if (Test-Path -LiteralPath $workerState) { "worker record=$workerState" } else { "not configured; source worker will use $connectorRoot after setup" }
Add-Result 'wxwork-mcp-worker' $(if (Test-Path -LiteralPath $workerState) {'pass'} else {'warn'}) $workerDetail

try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/api/v1/broadcast/variable-profile?bot_uuid=doctor&connector_id=wxwork-local" -TimeoutSec 5 -ErrorAction Stop
    Add-Result 'broadcast-config-api' 'pass' "HTTP $($response.StatusCode)"
}
catch {
    $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
    if ($code -in @(400, 401, 403, 404)) { Add-Result 'broadcast-config-api' 'pass' "route responded HTTP $code (scope/login required)" } else { Add-Result 'broadcast-config-api' 'fail' $_.Exception.Message }
}

$summary = [ordered]@{ status=if (@($results | Where-Object status -eq 'fail').Count) {'fail'} else {'ok'}; userData=$userDataRoot; results=$results }
$summary | ConvertTo-Json -Depth 6
if ($summary.status -eq 'fail') { exit 1 }
exit 0
