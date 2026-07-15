#requires -Version 5.1
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtimeRoot = Join-Path $repoRoot 'apps\desktop-rpa-runtime'
$packagePath = Join-Path $runtimeRoot 'package.json'
$lockPath = Join-Path $runtimeRoot 'package-lock.json'
$entryPath = Join-Path $runtimeRoot 'src\main\index.ts'
$winUnpackedPath = Join-Path $runtimeRoot 'dist-phase2-official\win-dir\win-unpacked'
$outputDir = Join-Path $repoRoot 'distribution\packages\desktop-runtime'
$assetName = 'desktop-runtime-win-x64.zip'

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

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Get-RuntimeMetadata {
    foreach ($path in @($packagePath, $lockPath, $entryPath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required Desktop Runtime file is missing: $path" }
    }
    $package = Get-Content -LiteralPath $packagePath -Raw | ConvertFrom-Json
    $source = Get-Content -LiteralPath $entryPath -Raw
    $runtimeMatch = [regex]::Match($source, "(?m)^\s*const\s+RUNTIME_VERSION\s*=\s*'([^']+)'\s*;?")
    $protocolMatch = [regex]::Match($source, "(?m)^\s*const\s+PROTOCOL_VERSION\s*=\s*'([^']+)'\s*;?")
    if (-not $runtimeMatch.Success -or -not $protocolMatch.Success) { throw 'Desktop Runtime version constants are missing.' }
    if ([string]$package.version -ne $runtimeMatch.Groups[1].Value) { throw 'Desktop Runtime package.json version does not match RUNTIME_VERSION.' }
    [pscustomobject]@{
        RuntimeVersion = [string]$package.version
        ProtocolVersion = $protocolMatch.Groups[1].Value
        ElectronVersion = [string]$package.devDependencies.electron
        PackageLockSha256 = Get-Sha256 $lockPath
    }
}

function Assert-DesktopRuntimePayload([string]$Root) {
    foreach ($relativePath in @('LangBot Desktop RPA Runtime.exe', 'resources\app.asar', 'chrome_100_percent.pak', 'icudtl.dat', 'resources.pak', 'libEGL.dll', 'libGLESv2.dll', 'ffmpeg.dll', 'resources\app.asar.unpacked\node_modules\@hurdlegroup', 'resources\app.asar.unpacked\node_modules\active-win', 'resources\app.asar.unpacked\node_modules\node-window-manager')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $relativePath))) { throw "Desktop Runtime package is incomplete: missing $relativePath" }
    }
}

function Test-PathWithinRoot([string]$CandidatePath, [string]$RootPath) {
    if ([string]::IsNullOrWhiteSpace($CandidatePath) -or [string]::IsNullOrWhiteSpace($RootPath)) { return $false }
    try { $candidate = [IO.Path]::GetFullPath($CandidatePath); $root = [IO.Path]::GetFullPath($RootPath).TrimEnd('\') } catch { return $false }
    return [StringComparer]::OrdinalIgnoreCase.Equals($candidate, $root) -or $candidate.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Test-DesktopRuntimeProcess([object]$ProcessRecord) {
    if ($null -eq $ProcessRecord) { return $false }
    if (Test-PathWithinRoot ([string]$ProcessRecord.ExecutablePath) $runtimeRoot) { return $true }
    return @('node.exe', 'electron.exe', 'LangBot Desktop RPA Runtime.exe') -contains ([string]$ProcessRecord.Name) -and ([string]$ProcessRecord.CommandLine).IndexOf($runtimeRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0
}

function Stop-ExistingDesktopRuntimeProcesses {
    $processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { Test-DesktopRuntimeProcess $_ })
    foreach ($process in $processes | Sort-Object -Property ProcessId -Unique) { & taskkill.exe /PID $process.ProcessId /T /F | Out-Null }
}

function Invoke-RuntimeNpmCommand([string]$NpmPath, [string[]]$Arguments, [string]$FailureMessage) {
    $maxRetries = 3
    for ($attempt = 0; $attempt -le $maxRetries; $attempt++) {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            # npm writes ordinary diagnostics to stderr; collect them so EBUSY/EPERM
            # can be classified instead of becoming a PowerShell terminating error.
            $ErrorActionPreference = 'Continue'
            $output = @(& $NpmPath @Arguments 2>&1)
            $exitCode = $LASTEXITCODE
        } finally { $ErrorActionPreference = $previousErrorActionPreference }
        $output | ForEach-Object { Write-Host $_ }
        if ($exitCode -eq 0) { return }
        $locked = (@($output) -join [Environment]::NewLine) -match '(?i)\b(?:EBUSY|EPERM)\b'
        if (-not $locked -or $attempt -eq $maxRetries) { throw $FailureMessage }
        Stop-ExistingDesktopRuntimeProcesses
        Start-Sleep -Seconds 1
    }
}

function Ensure-OptionalFseventsDirectory {
    # npm omits this macOS-only optional dependency on Windows, while some
    # electron-builder versions still lstat every lockfile entry.
    $optionalPath = Join-Path $runtimeRoot 'node_modules\fsevents'
    if (-not (Test-Path -LiteralPath $optionalPath)) { New-Item -ItemType Directory -Path $optionalPath -Force | Out-Null }
}

function Write-AtomicText([string]$Path, [string]$Content) {
    $temporary = "$Path.partial"
    try { [IO.File]::WriteAllText($temporary, $Content, [Text.UTF8Encoding]::new($false)); Move-Item -LiteralPath $temporary -Destination $Path -Force }
    finally { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
}

function Invoke-BuildDesktopRuntimeBundle {
    if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) { throw 'Desktop Runtime bundles can only be built on Windows x64.' }
    $node = Require-Command 'node.exe'; $npm = Require-Command 'npm.cmd'; $git = Require-Command 'git.exe'
    $nodeVersion = Get-TextCommand $node @('--version')
    if ($nodeVersion -notmatch '^v22\.') { throw "Node.js 22.x is required; found $nodeVersion." }
    Get-TextCommand $npm @('--version') | Out-Null
    $metadata = Get-RuntimeMetadata

    Push-Location $runtimeRoot
    try {
        Invoke-RuntimeNpmCommand $npm @('ci') 'Desktop Runtime npm ci failed.'
        Ensure-OptionalFseventsDirectory
        Invoke-RuntimeNpmCommand $npm @('run', 'rebuild:native') 'Desktop Runtime native rebuild failed.'
        Invoke-RuntimeNpmCommand $npm @('run', 'package:win:dir') 'Desktop Runtime package build failed.'
    } finally { Pop-Location }

    Assert-DesktopRuntimePayload $winUnpackedPath
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
    $archivePath = Join-Path $outputDir $assetName
    $hashPath = "$archivePath.sha256"
    $manifestPath = Join-Path $outputDir 'runtime-manifest.json'
    $temporaryArchive = "$archivePath.partial"
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    try {
        Remove-Item -LiteralPath $temporaryArchive -Force -ErrorAction SilentlyContinue
        [IO.Compression.ZipFile]::CreateFromDirectory($winUnpackedPath, $temporaryArchive, [IO.Compression.CompressionLevel]::Optimal, $false)
        Move-Item -LiteralPath $temporaryArchive -Destination $archivePath -Force
    } finally { Remove-Item -LiteralPath $temporaryArchive -Force -ErrorAction SilentlyContinue }
    $assetSha256 = Get-Sha256 $archivePath
    $gitCommit = Get-TextCommand $git @('-C', $repoRoot, 'rev-parse', 'HEAD')
    $manifest = [ordered]@{
        schema_version = 1
        runtime_version = $metadata.RuntimeVersion
        protocol_version = $metadata.ProtocolVersion
        git_commit = $gitCommit
        platform = 'win32'
        architecture = 'x64'
        electron_version = $metadata.ElectronVersion
        package_lock_sha256 = $metadata.PackageLockSha256
        asset_name = $assetName
        asset_sha256 = $assetSha256
        executable_relative_path = 'LangBot Desktop RPA Runtime.exe'
        created_at = [DateTime]::UtcNow.ToString('o')
    }
    Write-AtomicText $hashPath ("$assetSha256 *$assetName`r`n")
    Write-AtomicText $manifestPath (($manifest | ConvertTo-Json) + "`r`n")
    [ordered]@{ archive = $archivePath; sha256 = $hashPath; manifest = $manifestPath; runtimeVersion = $metadata.RuntimeVersion } | ConvertTo-Json
}

if ($MyInvocation.InvocationName -ne '.') { Invoke-BuildDesktopRuntimeBundle }
