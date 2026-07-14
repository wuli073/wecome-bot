#requires -Version 5.1
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$webRoot = Join-Path $repoRoot 'web'
$desktopRuntimeRoot = Join-Path $repoRoot 'apps\desktop-rpa-runtime'
$desktopRuntimeExecutable = Join-Path $desktopRuntimeRoot 'dist-phase2-official\win-dir\win-unpacked\LangBot Desktop RPA Runtime.exe'
$venvPath = [IO.Path]::GetFullPath((Join-Path $repoRoot '.venv'))

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

function Get-ExistingVenvPythonVersion([string]$VenvPath) {
    $python = Join-Path $VenvPath 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { return $null }

    $output = & $python --version 2>&1
    if ($LASTEXITCODE -ne 0) { return $null }
    return ([string]($output | Select-Object -First 1)).Trim()
}

function Remove-IncompatibleProjectVenv([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { throw 'Virtual environment path is empty.' }

    $fullPath = [IO.Path]::GetFullPath($Path)
    $parentPath = [IO.Path]::GetDirectoryName($fullPath)
    $expectedName = '.venv'
    if (
        -not [StringComparer]::OrdinalIgnoreCase.Equals($fullPath, $venvPath) -or
        -not [StringComparer]::OrdinalIgnoreCase.Equals($parentPath, $repoRoot) -or
        -not [StringComparer]::OrdinalIgnoreCase.Equals([IO.Path]::GetFileName($fullPath), $expectedName)
    ) {
        throw "Refusing to remove a path outside the project virtual environment: $fullPath"
    }

    if (Test-Path -LiteralPath $fullPath -PathType Container) {
        Remove-Item -LiteralPath $fullPath -Recurse -Force
    }
}

function Invoke-ManagedPythonSync([string]$UvPath) {
    & $UvPath sync --frozen --dev --python 3.12 --managed-python
    return $LASTEXITCODE
}

if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) {
    throw 'This source distribution supports Windows x64 only.'
}

Write-Host '[1/6] Checking source prerequisites...'
$git = Require-Command 'git.exe'
$node = Require-Command 'node.exe'
$npm = Require-Command 'npm.cmd'
$uv = Require-Command 'uv.exe'
$nodeVersion = Get-TextCommand $node @('--version')
if ($nodeVersion -notmatch '^v22\.') { throw "Node.js 22.x is required; found $nodeVersion." }

foreach ($path in @(
    (Join-Path $repoRoot 'uv.lock'),
    (Join-Path $webRoot 'package-lock.json'),
    (Join-Path $desktopRuntimeRoot 'package.json'),
    (Join-Path $desktopRuntimeRoot 'package-lock.json'),
    (Join-Path $repoRoot 'vendor\wechat_decrypt\connector_runtime.py'),
    (Join-Path $repoRoot 'vendor\wechat_decrypt\mcp_wxwork_http_server.py')
)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required source entry or lock file is missing: $path" }
}

$lockFiles = @((Join-Path $repoRoot 'uv.lock'), (Join-Path $webRoot 'package-lock.json'), (Join-Path $webRoot 'pnpm-lock.yaml'), (Join-Path $desktopRuntimeRoot 'package-lock.json')) |
    Where-Object { Test-Path -LiteralPath $_ }
$before = @{}
foreach ($lockFile in $lockFiles) { $before[$lockFile] = (Get-FileHash -LiteralPath $lockFile -Algorithm SHA256).Hash }

Write-Host '[2/6] Preparing managed Python 3.12...'
& $uv python install 3.12
if ($LASTEXITCODE -ne 0) { throw 'uv python install 3.12 failed.' }

$existingVenvPython = Get-ExistingVenvPythonVersion $venvPath
Write-Host '[3/6] Installing Python dependencies...'
Push-Location $repoRoot
try {
    $syncExitCode = Invoke-ManagedPythonSync $uv
    if ($syncExitCode -ne 0 -and $existingVenvPython -and $existingVenvPython -notmatch '^Python 3\.12\.') {
        Write-Host "Rebuilding incompatible project virtual environment ($existingVenvPython)..."
        Remove-IncompatibleProjectVenv $venvPath
        $syncExitCode = Invoke-ManagedPythonSync $uv
    }
    if ($syncExitCode -ne 0) { throw 'uv sync --frozen --dev --python 3.12 --managed-python failed.' }
}
finally { Pop-Location }

Write-Host '[4/6] Installing Web dependencies...'
Push-Location $webRoot
try {
    & $npm ci
    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }
}
finally { Pop-Location }

Write-Host '[5/6] Installing Desktop Runtime dependencies...'
Push-Location $desktopRuntimeRoot
try {
    & $npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Desktop Runtime dependency installation failed.' }
    & $npm run rebuild:native
    if ($LASTEXITCODE -ne 0) { throw 'Desktop Runtime native dependency rebuild failed.' }
    & $npm run package:win:dir
    if ($LASTEXITCODE -ne 0) { throw 'Desktop Runtime package build failed.' }
}
catch {
    Write-Error 'Desktop Runtime dependency installation failed.'
    throw
}
finally { Pop-Location }

if (-not (Test-Path -LiteralPath $desktopRuntimeExecutable -PathType Leaf)) {
    throw "Desktop Runtime entry is missing after installation: $desktopRuntimeExecutable"
}

Write-Host '[6/6] Verifying environment...'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) { throw "Project Python executable is missing: $venvPython" }
$pythonVersion = Get-TextCommand $venvPython @('--version')
if ($pythonVersion -notmatch '^Python 3\.12\.') { throw "Expected Python 3.12 in .venv; found $pythonVersion." }
$onnxruntimeVersion = Get-TextCommand $venvPython @('-c', 'import onnxruntime; print(onnxruntime.__version__)')

foreach ($lockFile in $lockFiles) {
    $after = (Get-FileHash -LiteralPath $lockFile -Algorithm SHA256).Hash
    if ($before[$lockFile] -ne $after) { throw "Dependency installation modified lock file: $lockFile" }
}

$envStatus = if (Test-Path -LiteralPath (Join-Path $webRoot '.env')) { 'preserved' } else { 'not-created' }
[ordered]@{
    status = 'ok'
    python = $pythonVersion
    pythonExecutable = $venvPython
    onnxruntime = $onnxruntimeVersion
    git = (Get-TextCommand $git @('--version'))
    node = $nodeVersion
    npm = (Get-TextCommand $npm @('--version'))
    uv = (Get-TextCommand $uv @('--version'))
    environmentFile = $envStatus
    desktopRuntime = $desktopRuntimeExecutable
    locks = 'verified-unchanged'
    wechatDecrypt = 'vendor/wechat_decrypt/mcp_wxwork_http_server.py'
} | ConvertTo-Json
