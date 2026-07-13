#requires -Version 5.1
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$webRoot = Join-Path $repoRoot 'web'

function Require-Command([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) { throw "$Name was not found on PATH." }
    return $command.Source
}

function Get-TextCommand([string]$FilePath, [string[]]$Arguments) {
    $output = & $FilePath @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $FilePath $($Arguments -join ' ')`n$output" }
    return ([string]($output | Select-Object -First 1)).Trim()
}

if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) {
    throw 'This source distribution supports Windows x64 only.'
}

$git = Require-Command 'git.exe'
$node = Require-Command 'node.exe'
$npm = Require-Command 'npm.cmd'
$uv = Require-Command 'uv.exe'
$nodeVersion = Get-TextCommand $node @('--version')
if ($nodeVersion -notmatch '^v22\.') { throw "Node.js 22.x is required; found $nodeVersion." }

foreach ($path in @(
    (Join-Path $repoRoot 'uv.lock'),
    (Join-Path $webRoot 'package-lock.json'),
    (Join-Path $repoRoot 'vendor\wechat_decrypt\connector_runtime.py'),
    (Join-Path $repoRoot 'vendor\wechat_decrypt\mcp_wxwork_http_server.py')
)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required source entry or lock file is missing: $path" }
}

$lockFiles = @((Join-Path $repoRoot 'uv.lock'), (Join-Path $webRoot 'package-lock.json'), (Join-Path $webRoot 'pnpm-lock.yaml')) |
    Where-Object { Test-Path -LiteralPath $_ }
$before = @{}
foreach ($lockFile in $lockFiles) { $before[$lockFile] = (Get-FileHash -LiteralPath $lockFile -Algorithm SHA256).Hash }

Push-Location $repoRoot
try {
    & $uv sync --frozen --dev
    if ($LASTEXITCODE -ne 0) { throw 'uv sync --frozen --dev failed.' }
}
finally { Pop-Location }

Push-Location $webRoot
try {
    & $npm ci
    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }
}
finally { Pop-Location }

foreach ($lockFile in $lockFiles) {
    $after = (Get-FileHash -LiteralPath $lockFile -Algorithm SHA256).Hash
    if ($before[$lockFile] -ne $after) { throw "Dependency installation modified lock file: $lockFile" }
}

$envStatus = if (Test-Path -LiteralPath (Join-Path $webRoot '.env')) { 'preserved' } else { 'not-created' }
[ordered]@{
    status = 'ok'
    git = (Get-TextCommand $git @('--version'))
    node = $nodeVersion
    npm = (Get-TextCommand $npm @('--version'))
    uv = (Get-TextCommand $uv @('--version'))
    environmentFile = $envStatus
    locks = 'verified-unchanged'
    wechatDecrypt = 'vendor/wechat_decrypt/mcp_wxwork_http_server.py'
} | ConvertTo-Json
