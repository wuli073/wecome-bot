#requires -Version 5.1
[CmdletBinding()]
param(
    [int]$BackendPort = 55300,
    [int]$WebPort = 55301,
    [switch]$KeepUserData
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$userDataRoot = Join-Path $env:TEMP ("wecome-source-smoke-" + [guid]::NewGuid().ToString('N'))
$baseUrl = "http://127.0.0.1:$BackendPort"
$workerProcess = $null
$started = $false
$result = [ordered]@{ status='fail'; userData=$userDataRoot; checks=@() }

function Add-Check([string]$Name, [string]$Detail) { $result.checks += [ordered]@{ name=$Name; status='pass'; detail=$Detail } }
function Invoke-Api([string]$Method, [string]$Path, $Body = $null) {
    $parameters = @{ Uri="$baseUrl$Path"; Method=$Method; TimeoutSec=15; ContentType='application/json' }
    if ($null -ne $Body) { $parameters.Body = $Body | ConvertTo-Json -Depth 8 -Compress }
    return Invoke-RestMethod @parameters
}
function Wait-Port([int]$Port, [int]$Seconds = 20) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) { return }
        Start-Sleep -Milliseconds 250
    }
    throw "Port $Port did not become ready."
}
function Assert-PortReleased([int]$Port) {
    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) { throw "Port $Port remains in use after shutdown." }
}

try {
    $startResult = & (Join-Path $PSScriptRoot 'start-source.ps1') -UserDataRoot $userDataRoot -BackendPort $BackendPort -WebPort $WebPort -NoBrowser -StartupTimeoutSeconds 180 | ConvertFrom-Json
    $started = $true
    if ($startResult.realSend -ne 'disabled') { throw 'Source startup did not disable real sending.' }
    Add-Check 'source-start' "backend PID $($startResult.backendPid), web PID $($startResult.webPid)"

    $platforms = Invoke-Api 'GET' '/api/v1/platform/adapters'
    if ($platforms.code -ne 0 -or @($platforms.data.adapters).Count -lt 1) { throw 'Platform list is unavailable.' }
    Add-Check 'platform-list' "count=$(@($platforms.data.adapters).Count)"

    $init = Invoke-Api 'POST' '/api/v1/user/init' @{ user='source-smoke@example.invalid'; password='source-smoke-password' }
    if ($init.code -ne 0) { throw "User initialization failed: $($init.msg)" }
    $progress = Invoke-Api 'PUT' '/api/v1/system/wizard/progress' @{ step=1; selected_adapter='wxwork_database'; created_bot_uuid=$null; bot_saved=$false; selected_runner=$null }
    if ($progress.code -ne 0) { throw 'Wizard progress API failed.' }
    $completed = Invoke-Api 'POST' '/api/v1/system/wizard/completed' @{ status='skipped' }
    if ($completed.code -ne 0) { throw 'Wizard completed API failed.' }
    $info = Invoke-Api 'GET' '/api/v1/system/info'
    if ($info.data.wizard_status -ne 'skipped' -or $null -ne $info.data.wizard_progress) { throw 'Wizard state was not persisted.' }
    Add-Check 'wizard-progress-completed' 'persisted skipped status and cleared progress'

    if (Get-NetTCPConnection -State Listen -LocalPort 5681 -ErrorAction SilentlyContinue) { throw 'Port 5681 is occupied; cannot verify the isolated wxwork MCP worker.' }
    $workerRoot = Join-Path $userDataRoot 'connectors\wxwork-local'
    New-Item -ItemType Directory -Force -Path (Join-Path $workerRoot 'config') | Out-Null
    $savedAppDir = [Environment]::GetEnvironmentVariable('WECHAT_DECRYPT_APP_DIR', 'Process')
    try {
        [Environment]::SetEnvironmentVariable('WECHAT_DECRYPT_APP_DIR', (Join-Path $workerRoot 'config'), 'Process')
        $workerProcess = Start-Process -FilePath (Join-Path $repoRoot '.venv\Scripts\python.exe') -ArgumentList @('-u', (Join-Path $repoRoot 'vendor\wechat_decrypt\mcp_wxwork_http_server.py')) -WorkingDirectory (Join-Path $repoRoot 'vendor\wechat_decrypt') -WindowStyle Hidden -PassThru
    }
    finally { [Environment]::SetEnvironmentVariable('WECHAT_DECRYPT_APP_DIR', $savedAppDir, 'Process') }
    Wait-Port 5681
    Add-Check 'wxwork-mcp-worker' "PID $($workerProcess.Id), port 5681"

    $bot = Invoke-Api 'POST' '/api/v1/platform/bots' @{ name='Source smoke wxwork'; description='Source smoke only'; adapter='wxwork_database'; adapter_config=@{ auto_generate_draft=$false }; enable=$false }
    if ($bot.code -ne 0 -or -not $bot.data.uuid) { throw "Could not create wxwork database bot: $($bot.msg)" }
    $scope = @{ bot_uuid=$bot.data.uuid; connector_id='wxwork-local' }
    $profile = Invoke-Api 'PUT' '/api/v1/broadcast/variable-profile' (@{ bot_uuid=$scope.bot_uuid; connector_id=$scope.connector_id; group_field='group_name'; mapping_rules=@(@{ source_field='customer_name'; variable_key='customer_name'; merge_mode='first'; order=1 }) })
    if ($profile.code -ne 0 -or $profile.data.group_field -ne 'group_name') { throw "Broadcast profile save failed: $($profile.msg)" }
    $savedProfile = Invoke-Api 'GET' ("/api/v1/broadcast/variable-profile?bot_uuid=$($scope.bot_uuid)&connector_id=$($scope.connector_id)")
    if ($savedProfile.code -ne 0 -or $savedProfile.data.group_field -ne 'group_name') { throw "Broadcast scope/group field was not persisted: $($savedProfile.msg)" }
    Add-Check 'broadcast-scope-group-field' "bot=$($scope.bot_uuid); connector=wxwork-local"

    $result.status='pass'
}
finally {
    if ($workerProcess -and -not $workerProcess.HasExited) { & taskkill.exe /PID $workerProcess.Id /T /F | Out-Null }
    if ($started) { & (Join-Path $PSScriptRoot 'stop-source.ps1') -UserDataRoot $userDataRoot | Out-Null }
    Assert-PortReleased $BackendPort; Assert-PortReleased $WebPort; Assert-PortReleased 5681
    if (-not $KeepUserData) { Remove-Item -LiteralPath $userDataRoot -Recurse -Force -ErrorAction SilentlyContinue }
}

$result | ConvertTo-Json -Depth 8
if ($result.status -ne 'pass') { exit 1 }
