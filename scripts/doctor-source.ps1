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
$results = [System.Collections.Generic.List[object]]::new()

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

$state = if (Test-Path -LiteralPath $statePath) { Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json } else { $null }
if ($null -eq $state) { Add-Result 'managed-source-stack' 'warn' "not started; state=$statePath" }
else { Add-Result 'managed-source-stack' 'pass' "backend PID $($state.backend.pid), web PID $($state.web.pid), logs $($state.logsRoot)" }

$health = Test-HttpJson '/healthz'; $runtime = Test-HttpJson '/api/v1/system/runtime/status'; $ready = Test-HttpJson '/readyz'
Add-Result 'health' $(if ($health -and $health.code -eq 0) {'pass'} else {'fail'}) $(if ($health) { "state=$($health.state)" } else { 'endpoint unavailable' })
Add-Result 'runtime' $(if ($runtime -and $runtime.state -in @('CORE_READY', 'READY', 'DEGRADED')) {'pass'} else {'fail'}) $(if ($runtime) { "state=$($runtime.state)" } else { 'endpoint unavailable' })
Add-Result 'ready' $(if ($ready -and $ready.state -in @('CORE_READY', 'READY', 'DEGRADED')) {'pass'} else {'fail'}) $(if ($ready) { "state=$($ready.state)" } else { 'endpoint unavailable' })

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
