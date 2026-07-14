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

function Test-PathWithinRoot([string]$CandidatePath, [string]$RootPath) {
    if ([string]::IsNullOrWhiteSpace($CandidatePath) -or [string]::IsNullOrWhiteSpace($RootPath)) { return $false }

    try {
        $candidate = [IO.Path]::GetFullPath($CandidatePath)
        $root = [IO.Path]::GetFullPath($RootPath).TrimEnd('\')
    }
    catch {
        return $false
    }

    if ([StringComparer]::OrdinalIgnoreCase.Equals($candidate, $root)) { return $true }
    return $candidate.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Get-RequiredProjectPython([string]$RepoRoot) {
    $python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Project Python executable is missing: $python"
    }

    $version = Get-TextCommand $python @('--version')
    if ($version -notmatch '^Python 3\.12\.') {
        throw "Expected Python 3.12 in .venv; found $version."
    }

    return [pscustomobject]@{
        Path = $python
        Version = $version
    }
}

function Invoke-WithManagedPythonEnvironment([string]$PythonPath, [scriptblock]$ScriptBlock) {
    $hadPython = Test-Path Env:PYTHON
    $hadNpmConfigPython = Test-Path Env:npm_config_python
    $previousPython = $env:PYTHON
    $previousNpmConfigPython = $env:npm_config_python

    try {
        $env:PYTHON = $PythonPath
        $env:npm_config_python = $PythonPath
        & $ScriptBlock
    }
    finally {
        if ($hadPython) {
            $env:PYTHON = $previousPython
        }
        else {
            Remove-Item Env:PYTHON -ErrorAction SilentlyContinue
        }

        if ($hadNpmConfigPython) {
            $env:npm_config_python = $previousNpmConfigPython
        }
        else {
            Remove-Item Env:npm_config_python -ErrorAction SilentlyContinue
        }
    }
}

function Invoke-ExternalCommand([string]$FilePath, [string[]]$Arguments) {
    $stdoutPath = [IO.Path]::GetTempFileName()
    $stderrPath = [IO.Path]::GetTempFileName()

    try {
        $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory (Get-Location).Path -NoNewWindow -PassThru -Wait -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
        $lines = @()
        if (Test-Path -LiteralPath $stdoutPath -PathType Leaf) {
            $lines += Get-Content -LiteralPath $stdoutPath
        }
        if (Test-Path -LiteralPath $stderrPath -PathType Leaf) {
            $lines += Get-Content -LiteralPath $stderrPath
        }

        $textLines = @($lines | ForEach-Object { [string]$_ })
        foreach ($line in $textLines) {
            Write-Host $line
        }

        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            Output = $textLines
        }
    }
    finally {
        Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Get-NpmLockErrorPaths([string[]]$CommandOutput) {
    $paths = New-Object System.Collections.Generic.List[string]
    foreach ($line in @($CommandOutput)) {
        if ($line -match '(?i)npm ERR!\s+path\s+(.+)$') {
            $path = $Matches[1].Trim().Trim('"')
            if (-not [string]::IsNullOrWhiteSpace($path) -and -not $paths.Contains($path)) {
                $paths.Add($path)
            }
        }
        elseif ($line -match "(?i)\b(?:EBUSY|EPERM)\b.*?['""]?([A-Z]:\\[^'""]+)") {
            $path = $Matches[1].Trim()
            if (-not [string]::IsNullOrWhiteSpace($path) -and -not $paths.Contains($path)) {
                $paths.Add($path)
            }
        }
        elseif ($line -match "(?i)npm ERR!.*?['""]?([A-Z]:\\[^'""]+)") {
            $path = $Matches[1].Trim()
            if (-not [string]::IsNullOrWhiteSpace($path) -and -not $paths.Contains($path)) {
                $paths.Add($path)
            }
        }
    }

    return @($paths)
}

function Write-NpmLockErrorHint([string[]]$CommandOutput) {
    $joinedOutput = (@($CommandOutput) -join [Environment]::NewLine)
    if ($joinedOutput -notmatch '(?i)\b(?:EBUSY|EPERM)\b') { return }

    $paths = Get-NpmLockErrorPaths $CommandOutput
    if ($paths.Count -gt 0) {
        Write-Warning ('Desktop Runtime npm ci hit a locked path: ' + ($paths -join '; '))
    }
    else {
        Write-Warning 'Desktop Runtime npm ci hit a locked path, but npm did not report the exact path.'
    }
    Write-Warning 'Close the previous Desktop Runtime from this repository and run scripts\setup-source.ps1 again.'
}

function Test-DesktopRuntimeProcess([object]$ProcessRecord, [string]$RuntimeRoot, [string]$RuntimeExecutable) {
    if ($null -eq $ProcessRecord) { return $false }

    $name = [string]$ProcessRecord.Name
    $exe = [string]$ProcessRecord.ExecutablePath
    $commandLine = [string]$ProcessRecord.CommandLine

    if (Test-PathWithinRoot $exe $RuntimeRoot) { return $true }
    if ([StringComparer]::OrdinalIgnoreCase.Equals($exe, $RuntimeExecutable)) { return $true }

    $allowedNames = @('node.exe', 'electron.exe', 'LangBot Desktop RPA Runtime.exe')
    return $allowedNames -contains $name -and -not [string]::IsNullOrWhiteSpace($commandLine) -and $commandLine.IndexOf($RuntimeRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0
}

function Stop-ExistingDesktopRuntimeProcesses([string]$RuntimeRoot, [string]$RuntimeExecutable) {
    $processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        Test-DesktopRuntimeProcess $_ $RuntimeRoot $RuntimeExecutable
    })

    foreach ($process in $processes | Sort-Object -Property ProcessId -Unique) {
        Write-Host ("Stopping Desktop Runtime process {0} ({1})" -f $process.ProcessId, $process.Name)
        & taskkill.exe /PID $process.ProcessId /T /F | Out-Null
    }
}

function Invoke-SetupSource {
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
    $managedPython = Get-RequiredProjectPython $repoRoot
    Stop-ExistingDesktopRuntimeProcesses $desktopRuntimeRoot $desktopRuntimeExecutable

    Push-Location $desktopRuntimeRoot
    try {
        Invoke-WithManagedPythonEnvironment $managedPython.Path {
            $runtimeInstall = Invoke-ExternalCommand $npm @('ci')
            if ($runtimeInstall.ExitCode -ne 0) {
                Write-NpmLockErrorHint $runtimeInstall.Output
                throw 'Desktop Runtime npm ci failed'
            }

            $nativeRebuild = Invoke-ExternalCommand $npm @('run', 'rebuild:native')
            if ($nativeRebuild.ExitCode -ne 0) { throw 'native rebuild failed' }

            $packageBuild = Invoke-ExternalCommand $npm @('run', 'package:win:dir')
            if ($packageBuild.ExitCode -ne 0) { throw 'package build failed' }
        }
    }
    finally { Pop-Location }

    if (-not (Test-Path -LiteralPath $desktopRuntimeExecutable -PathType Leaf)) {
        throw 'Runtime exe missing'
    }

    Write-Host '[6/6] Verifying environment...'
    $venvPython = Join-Path $venvPath 'Scripts\python.exe'
    $pythonVersion = Get-TextCommand $venvPython @('--version')
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
}

if ($MyInvocation.InvocationName -ne '.') {
    Invoke-SetupSource
}
