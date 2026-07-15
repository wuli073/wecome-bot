#requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$BuildDesktopRuntimeFromSource,
    [string]$DesktopRuntimeArchivePath,
    [string]$DesktopRuntimeManifestPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$webRoot = Join-Path $repoRoot 'web'
$desktopRuntimeRoot = Join-Path $repoRoot 'apps\desktop-rpa-runtime'
$desktopRuntimePackagePath = Join-Path $desktopRuntimeRoot 'package.json'
$desktopRuntimeLockPath = Join-Path $desktopRuntimeRoot 'package-lock.json'
$desktopRuntimeSourcePath = Join-Path $desktopRuntimeRoot 'src\main\index.ts'
$desktopRuntimeWinDir = Join-Path $desktopRuntimeRoot 'dist-phase2-official\win-dir'
$desktopRuntimeUnpackedPath = Join-Path $desktopRuntimeWinDir 'win-unpacked'
$desktopRuntimeExecutable = Join-Path $desktopRuntimeUnpackedPath 'LangBot Desktop RPA Runtime.exe'
$desktopRuntimeCacheRoot = Join-Path $repoRoot 'runtime\cache\desktop-runtime'
$desktopRuntimeReleaseDescriptorPath = Join-Path $repoRoot 'distribution\runtime\desktop-runtime-release.json'
$venvPath = [IO.Path]::GetFullPath((Join-Path $repoRoot '.venv'))
$setupLogPath = Join-Path $repoRoot 'runtime\logs\setup-source.log'
$script:setupStage = 'initializing'

function Write-SetupLog([string]$Message) {
    try {
        New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($setupLogPath)) -Force | Out-Null
        Add-Content -LiteralPath $setupLogPath -Value ("{0:o} {1}" -f [DateTime]::UtcNow, $Message) -Encoding utf8
    } catch {
        # Logging must never hide the installation failure that prompted it.
    }
}

function Get-SetupFailureCode([object]$ErrorRecord) {
    $message = [string]$ErrorRecord.Exception.Message
    $match = [regex]::Match($message, '(?m)\b(?:PREBUILT_RUNTIME|DESKTOP_RUNTIME|SETUP_SOURCE)_[A-Z0-9_]+\b')
    if ($match.Success) { return $match.Groups[1].Value }
    return 'SETUP_SOURCE_FAILED'
}

function Protect-SetupErrorMessage([string]$Message) {
    if ($null -eq $Message) { return '' }
    return [regex]::Replace($Message, '(?i)\b(token|password|secret|api[_-]?key)\s*([=:])\s*[^\s;]+', '$1$2[redacted]')
}

function Format-SetupFailure([string]$Code, [string]$Stage, [string]$Message, [string[]]$Paths) {
    $pathText = @($Paths | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join '; '
    if ([string]::IsNullOrWhiteSpace($pathText)) { $pathText = '(not applicable)' }
    return @(
        $Code,
        "Stage: $Stage",
        "Message: $(Protect-SetupErrorMessage $Message)",
        "Paths: $pathText",
        "Log: $setupLogPath"
    ) -join [Environment]::NewLine
}

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

function Assert-SafeCleanupDirectory([string]$Path, [string]$RepositoryRoot, [string[]]$AllowedRoots, [string]$ExpectedLeafPattern) {
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path.Trim() -in @('.', '..')) { throw 'REFUSING_UNSAFE_CLEANUP_PATH' }
    try {
        $fullPath = [IO.Path]::GetFullPath($Path)
        $repo = [IO.Path]::GetFullPath($RepositoryRoot).TrimEnd('\')
        $user = [Environment]::GetFolderPath('UserProfile').TrimEnd('\')
    } catch { throw 'REFUSING_UNSAFE_CLEANUP_PATH' }
    if ([string]::IsNullOrWhiteSpace($fullPath) -or [IO.Path]::GetPathRoot($fullPath) -eq $fullPath -or
        [StringComparer]::OrdinalIgnoreCase.Equals($fullPath, $repo) -or
        [StringComparer]::OrdinalIgnoreCase.Equals($fullPath, [IO.Path]::GetDirectoryName($repo)) -or
        [StringComparer]::OrdinalIgnoreCase.Equals($fullPath, $user)) { throw 'REFUSING_UNSAFE_CLEANUP_PATH' }
    $allowed = $false
    foreach ($rootPath in @($AllowedRoots)) {
        if ([string]::IsNullOrWhiteSpace($rootPath)) { continue }
        $root = [IO.Path]::GetFullPath($rootPath).TrimEnd('\')
        if ($fullPath.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { $allowed = $true; break }
    }
    if (-not $allowed -or [IO.Path]::GetFileName($fullPath) -notmatch $ExpectedLeafPattern) { throw 'REFUSING_UNSAFE_CLEANUP_PATH' }
    return $fullPath
}

function Test-RetryableDesktopRuntimeCleanupException([Exception]$Exception) {
    if ($null -eq $Exception) { return $false }
    if ($Exception.HResult -in @(-2147024864, -2147024891)) { return $true } # ERROR_SHARING_VIOLATION / ERROR_ACCESS_DENIED
    return $Exception.Message -match '(?i)\b(?:EBUSY|EPERM|sharing violation|being used by another process|access is denied)\b'
}

function Remove-SafeDesktopRuntimeDirectory([string]$Path, [string]$FailureCode = 'PREBUILT_RUNTIME_BACKUP_CLEANUP_FAILED', [switch]$RetryLockedFiles) {
    $maxRetries = if ($RetryLockedFiles) { 3 } else { 0 }
    Remove-SafeCleanupDirectory $Path $repoRoot @($desktopRuntimeWinDir, $desktopRuntimeCacheRoot) '^(?:win-unpacked|\.desktop-runtime-(?:staging|backup)-[0-9a-f]{32})$' $FailureCode $maxRetries
}

function Remove-SafeCleanupDirectory(
    [string]$Path,
    [string]$RepositoryRoot,
    [string[]]$AllowedRoots,
    [string]$ExpectedLeafPattern,
    [string]$FailureCode = 'PREBUILT_RUNTIME_BACKUP_CLEANUP_FAILED',
    [int]$MaxRetries = 0,
    [scriptblock]$DeleteAction = { param([string]$ExtendedPath) [IO.Directory]::Delete($ExtendedPath, $true) }
) {
    $safePath = Assert-SafeCleanupDirectory $Path $RepositoryRoot $AllowedRoots $ExpectedLeafPattern
    if (-not (Test-Path -LiteralPath $safePath -PathType Container)) { return }
    # The packaged native build tree can exceed the legacy PowerShell path
    # limit; the validated extended path keeps cleanup inside its boundary.
    $extendedPath = if ($safePath.StartsWith('\\?\')) { $safePath } else { '\\?\' + $safePath }
    for ($attempt = 0; $attempt -le $MaxRetries; $attempt++) {
        try {
            & $DeleteAction $extendedPath
            return
        } catch {
            $cleanupException = $_.Exception
            if (-not (Test-RetryableDesktopRuntimeCleanupException $cleanupException) -or $attempt -eq $MaxRetries) {
                throw "${FailureCode}: cleanup failed for $safePath after $attempt retries: $($cleanupException.Message)"
            }
            Start-Sleep -Milliseconds (250 * ($attempt + 1))
        }
    }
}

function Assert-EqualValue([string]$Name, [object]$Actual, [object]$Expected) {
    if ([string]::IsNullOrWhiteSpace([string]$Actual) -or [string]$Actual -ne [string]$Expected) {
        throw "PREBUILT_RUNTIME_MANIFEST_INVALID: $Name is invalid."
    }
}

function Get-DesktopRuntimeMetadata {
    foreach ($path in @($desktopRuntimePackagePath, $desktopRuntimeLockPath, $desktopRuntimeSourcePath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required Desktop Runtime file is missing: $path" }
    }

    $package = Get-Content -LiteralPath $desktopRuntimePackagePath -Raw | ConvertFrom-Json
    $source = Get-Content -LiteralPath $desktopRuntimeSourcePath -Raw
    $runtimeMatch = [regex]::Match($source, "(?m)^\s*const\s+RUNTIME_VERSION\s*=\s*'([^']+)'\s*;?")
    $protocolMatch = [regex]::Match($source, "(?m)^\s*const\s+PROTOCOL_VERSION\s*=\s*'([^']+)'\s*;?")
    if (-not $runtimeMatch.Success -or -not $protocolMatch.Success) { throw 'Desktop Runtime version constants are missing.' }
    if ([string]$package.version -ne $runtimeMatch.Groups[1].Value) { throw 'Desktop Runtime package.json version does not match RUNTIME_VERSION.' }

    [pscustomobject]@{
        RuntimeVersion = [string]$package.version
        ProtocolVersion = $protocolMatch.Groups[1].Value
        PackageLockSha256 = Get-Sha256 $desktopRuntimeLockPath
    }
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
    if (-not [StringComparer]::OrdinalIgnoreCase.Equals($fullPath, $venvPath) -or -not [StringComparer]::OrdinalIgnoreCase.Equals($parentPath, $repoRoot) -or -not [StringComparer]::OrdinalIgnoreCase.Equals([IO.Path]::GetFileName($fullPath), '.venv')) {
        throw "Refusing to remove a path outside the project virtual environment: $fullPath"
    }
    throw 'The incompatible virtual environment must be removed manually; recursive cleanup is restricted to managed Runtime directories.'
}

function Invoke-ManagedPythonSync([string]$UvPath) {
    & $UvPath sync --frozen --dev --python 3.12 --managed-python
    return $LASTEXITCODE
}

function Get-RequiredProjectPython([string]$RepoRoot) {
    $python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Project Python executable is missing: $python" }
    $version = Get-TextCommand $python @('--version')
    if ($version -notmatch '^Python 3\.12\.') { throw "Expected Python 3.12 in .venv; found $version." }
    return [pscustomobject]@{ Path = $python; Version = $version }
}

function Invoke-WithManagedPythonEnvironment([string]$PythonPath, [scriptblock]$ScriptBlock) {
    $hadPython = Test-Path Env:PYTHON; $hadNpmConfigPython = Test-Path Env:npm_config_python
    $previousPython = $env:PYTHON; $previousNpmConfigPython = $env:npm_config_python
    try { $env:PYTHON = $PythonPath; $env:npm_config_python = $PythonPath; & $ScriptBlock }
    finally {
        if ($hadPython) { $env:PYTHON = $previousPython } else { Remove-Item Env:PYTHON -ErrorAction SilentlyContinue }
        if ($hadNpmConfigPython) { $env:npm_config_python = $previousNpmConfigPython } else { Remove-Item Env:npm_config_python -ErrorAction SilentlyContinue }
    }
}

function Invoke-ExternalCommand([string]$FilePath, [string[]]$Arguments) {
    $stdoutPath = [IO.Path]::GetTempFileName(); $stderrPath = [IO.Path]::GetTempFileName()
    try {
        $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory (Get-Location).Path -NoNewWindow -PassThru -Wait -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
        $lines = @(); if (Test-Path -LiteralPath $stdoutPath) { $lines += Get-Content -LiteralPath $stdoutPath }; if (Test-Path -LiteralPath $stderrPath) { $lines += Get-Content -LiteralPath $stderrPath }
        $textLines = @($lines | ForEach-Object { [string]$_ }); foreach ($line in $textLines) { Write-Host $line }
        return [pscustomobject]@{ ExitCode = $process.ExitCode; Output = $textLines }
    } finally { Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue }
}

function Get-NpmLockErrorPaths([string[]]$CommandOutput) {
    $paths = New-Object System.Collections.Generic.List[string]
    foreach ($line in @($CommandOutput)) {
        if ($line -match '(?i)npm ERR!\s+path\s+(.+)$') { $path = $Matches[1].Trim().Trim('"') }
        elseif ($line -match '(?i)\b(?:EBUSY|EPERM)\b.*?([A-Z]:\\.+)$') { $path = $Matches[1].Trim().Trim('\"', "'") }
        elseif ($line -match '(?i)npm ERR!.*?([A-Z]:\\.+)$') { $path = $Matches[1].Trim().Trim('\"', "'") }
        else { continue }
        if (-not [string]::IsNullOrWhiteSpace($path) -and -not $paths.Contains($path)) { $paths.Add($path) }
    }
    return @($paths)
}

function Write-NpmLockErrorHint([string[]]$CommandOutput) {
    if ((@($CommandOutput) -join [Environment]::NewLine) -notmatch '(?i)\b(?:EBUSY|EPERM)\b') { return }
    $paths = @(Get-NpmLockErrorPaths $CommandOutput)
    if ($paths.Count -gt 0) { Write-Warning ('Desktop Runtime npm ci hit a locked path: ' + ($paths -join '; ')) } else { Write-Warning 'Desktop Runtime npm ci hit a locked path, but npm did not report the exact path.' }
    Write-Warning 'Close the previous Desktop Runtime from this repository and run scripts\setup-source.ps1 again.'
}

function Test-PathWithinRoot([string]$CandidatePath, [string]$RootPath) {
    if ([string]::IsNullOrWhiteSpace($CandidatePath) -or [string]::IsNullOrWhiteSpace($RootPath)) { return $false }
    try { $candidate = [IO.Path]::GetFullPath($CandidatePath); $root = [IO.Path]::GetFullPath($RootPath).TrimEnd('\') } catch { return $false }
    return [StringComparer]::OrdinalIgnoreCase.Equals($candidate, $root) -or $candidate.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Test-DesktopRuntimeProcess([object]$ProcessRecord, [string]$RuntimeRoot, [string]$RuntimeExecutable) {
    if ($null -eq $ProcessRecord) { return $false }
    $name = [string]$ProcessRecord.Name; $exe = [string]$ProcessRecord.ExecutablePath; $commandLine = [string]$ProcessRecord.CommandLine
    if (Test-PathWithinRoot $exe $RuntimeRoot) { return $true }
    if ([StringComparer]::OrdinalIgnoreCase.Equals($exe, $RuntimeExecutable)) { return $true }
    return @('node.exe', 'electron.exe', 'LangBot Desktop RPA Runtime.exe') -contains $name -and -not [string]::IsNullOrWhiteSpace($commandLine) -and $commandLine.IndexOf($RuntimeRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0
}

function Stop-ExistingDesktopRuntimeProcesses([string]$RuntimeRoot, [string]$RuntimeExecutable) {
    $processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { Test-DesktopRuntimeProcess $_ $RuntimeRoot $RuntimeExecutable })
    foreach ($process in $processes | Sort-Object -Property ProcessId -Unique) { Write-Host ("Stopping Desktop Runtime process {0} ({1})" -f $process.ProcessId, $process.Name); & taskkill.exe /PID $process.ProcessId /T /F | Out-Null }
}

function Assert-DesktopRuntimeReleaseField([object]$Object, [string]$Name, [string]$ErrorCode = 'DESKTOP_RUNTIME_RELEASE_DESCRIPTOR_INVALID') {
    if ($null -eq $Object -or $null -eq $Object.PSObject.Properties[$Name] -or [string]::IsNullOrWhiteSpace([string]$Object.$Name)) {
        throw "${ErrorCode}: missing $Name."
    }
    return [string]$Object.$Name
}

function Assert-DesktopRuntimeReleaseValue([string]$Name, [object]$Actual, [object]$Expected, [string]$ErrorCode) {
    if ([string]::IsNullOrWhiteSpace([string]$Actual) -or [string]$Actual -ne [string]$Expected) { throw "${ErrorCode}: $Name is invalid." }
}

function Test-DesktopRuntimeReleaseFileName([string]$Name) {
    return -not [string]::IsNullOrWhiteSpace($Name) -and $Name -match '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$' -and
        $Name.IndexOfAny([char[]]'\\/:*?"<>|') -lt 0 -and $Name -notmatch '\.\.'
}

function Read-DesktopRuntimeReleaseDescriptor([object]$Metadata, [string]$Path = $desktopRuntimeReleaseDescriptorPath) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "DESKTOP_RUNTIME_RELEASE_NOT_CONFIGURED: descriptor is missing: $Path" }
    try { $descriptor = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json } catch { throw "DESKTOP_RUNTIME_RELEASE_DESCRIPTOR_INVALID: $($_.Exception.Message)" }
    foreach ($field in @('schema_version', 'provider', 'repository', 'tag', 'runtime_version', 'protocol_version', 'platform', 'architecture', 'asset_name', 'manifest_asset_name', 'asset_sha256', 'package_lock_sha256')) {
        Assert-DesktopRuntimeReleaseField $descriptor $field | Out-Null
    }
    Assert-DesktopRuntimeReleaseValue 'schema_version' $descriptor.schema_version '1' 'DESKTOP_RUNTIME_RELEASE_DESCRIPTOR_INVALID'
    Assert-DesktopRuntimeReleaseValue 'provider' $descriptor.provider 'github-release' 'DESKTOP_RUNTIME_RELEASE_DESCRIPTOR_INVALID'
    if ([string]$descriptor.repository -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,38}/[A-Za-z0-9][A-Za-z0-9._-]{0,99}$') { throw 'DESKTOP_RUNTIME_RELEASE_DESCRIPTOR_INVALID: repository is invalid.' }
    if ([string]$descriptor.tag -match '(?i)^latest$' -or [string]$descriptor.tag -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') { throw 'DESKTOP_RUNTIME_RELEASE_DESCRIPTOR_INVALID: tag must be a fixed non-latest tag.' }
    foreach ($asset in @([string]$descriptor.asset_name, [string]$descriptor.manifest_asset_name)) {
        if (-not (Test-DesktopRuntimeReleaseFileName $asset)) { throw 'DESKTOP_RUNTIME_RELEASE_DESCRIPTOR_INVALID: asset name is invalid.' }
    }
    if ([string]$descriptor.asset_name -ne 'desktop-runtime-win-x64.zip' -or [string]$descriptor.manifest_asset_name -ne 'runtime-manifest.json') { throw 'DESKTOP_RUNTIME_RELEASE_DESCRIPTOR_INVALID: runtime asset names are invalid.' }
    foreach ($hashName in @('asset_sha256', 'package_lock_sha256')) {
        if ([string]$descriptor.$hashName -notmatch '^[A-Fa-f0-9]{64}$') { throw "DESKTOP_RUNTIME_RELEASE_DESCRIPTOR_INVALID: $hashName is invalid." }
        $descriptor.$hashName = ([string]$descriptor.$hashName).ToUpperInvariant()
    }
    Assert-DesktopRuntimeReleaseValue 'runtime_version' $descriptor.runtime_version $Metadata.RuntimeVersion 'DESKTOP_RUNTIME_RELEASE_DESCRIPTOR_INVALID'
    Assert-DesktopRuntimeReleaseValue 'protocol_version' $descriptor.protocol_version $Metadata.ProtocolVersion 'DESKTOP_RUNTIME_RELEASE_DESCRIPTOR_INVALID'
    Assert-DesktopRuntimeReleaseValue 'platform' $descriptor.platform 'win32' 'DESKTOP_RUNTIME_RELEASE_DESCRIPTOR_INVALID'
    Assert-DesktopRuntimeReleaseValue 'architecture' $descriptor.architecture 'x64' 'DESKTOP_RUNTIME_RELEASE_DESCRIPTOR_INVALID'
    Assert-DesktopRuntimeReleaseValue 'package_lock_sha256' $descriptor.package_lock_sha256 $Metadata.PackageLockSha256 'DESKTOP_RUNTIME_RELEASE_DESCRIPTOR_INVALID'
    if ($null -ne $descriptor.PSObject.Properties['release_available'] -and $descriptor.release_available -isnot [bool]) { throw 'DESKTOP_RUNTIME_RELEASE_DESCRIPTOR_INVALID: release_available is invalid.' }
    return $descriptor
}

function Get-DesktopRuntimeReleaseUri([object]$Descriptor, [string]$AssetName) {
    if (-not (Test-DesktopRuntimeReleaseFileName $AssetName)) { throw 'DESKTOP_RUNTIME_RELEASE_DESCRIPTOR_INVALID: asset name is invalid.' }
    return [Uri]::new(('https://github.com/{0}/releases/download/{1}/{2}' -f $Descriptor.repository, $Descriptor.tag, $AssetName))
}

function Test-ApprovedDesktopRuntimeDownloadUri([Uri]$Uri) {
    if ($null -eq $Uri -or -not $Uri.IsAbsoluteUri -or $Uri.Scheme -ne 'https') { return $false }
    return @('github.com', 'objects.githubusercontent.com', 'github-releases.githubusercontent.com') -contains $Uri.DnsSafeHost.ToLowerInvariant()
}

function Remove-SafeDesktopRuntimePartialFile([string]$Path) {
    $safePath = Assert-SafeCleanupDirectory $Path $repoRoot @($desktopRuntimeCacheRoot) '^(?:desktop-runtime-win-x64\.zip|runtime-manifest\.json|release-descriptor\.json)\.partial$'
    if (Test-Path -LiteralPath $safePath -PathType Leaf) { [IO.File]::Delete($safePath) }
}

function Acquire-DesktopRuntimeCacheLock([string]$CacheDir, [int]$TimeoutSeconds = 60) {
    New-Item -ItemType Directory -Path $CacheDir -Force | Out-Null
    $lockPath = Join-Path $CacheDir '.desktop-runtime-cache.lock'
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ($true) {
        try { return [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None) }
        catch [IO.IOException] {
            if ([DateTime]::UtcNow -ge $deadline) { throw "DESKTOP_RUNTIME_CACHE_LOCK_TIMEOUT: timed out waiting for $lockPath" }
            Start-Sleep -Milliseconds 250
        }
    }
}

function Move-InvalidDesktopRuntimeCacheFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return }
    $safePath = Assert-SafeCleanupDirectory $Path $repoRoot @($desktopRuntimeCacheRoot) '^(?:desktop-runtime-win-x64\.zip|runtime-manifest\.json|release-descriptor\.json)$'
    $preserved = "$safePath.invalid-$([guid]::NewGuid().ToString('N'))"
    Move-Item -LiteralPath $safePath -Destination $preserved -ErrorAction Stop
}

function Read-DesktopRuntimeManifest([string]$ManifestPath, [object]$Metadata, [object]$Descriptor = $null) {
    try { $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json } catch { throw "DESKTOP_RUNTIME_MANIFEST_INVALID: $($_.Exception.Message)" }
    foreach ($field in @('schema_version', 'runtime_version', 'protocol_version', 'platform', 'architecture', 'electron_version', 'package_lock_sha256', 'asset_name', 'asset_sha256', 'executable_relative_path', 'created_at')) {
        if ($null -eq $manifest.PSObject.Properties[$field] -or [string]::IsNullOrWhiteSpace([string]$manifest.$field)) { throw "DESKTOP_RUNTIME_MANIFEST_INVALID: missing $field." }
    }
    Assert-DesktopRuntimeReleaseValue 'schema_version' $manifest.schema_version '1' 'DESKTOP_RUNTIME_MANIFEST_INVALID'
    Assert-DesktopRuntimeReleaseValue 'runtime_version' $manifest.runtime_version $Metadata.RuntimeVersion 'DESKTOP_RUNTIME_MANIFEST_INVALID'
    Assert-DesktopRuntimeReleaseValue 'protocol_version' $manifest.protocol_version $Metadata.ProtocolVersion 'DESKTOP_RUNTIME_MANIFEST_INVALID'
    Assert-DesktopRuntimeReleaseValue 'platform' $manifest.platform 'win32' 'DESKTOP_RUNTIME_MANIFEST_INVALID'
    Assert-DesktopRuntimeReleaseValue 'architecture' $manifest.architecture 'x64' 'DESKTOP_RUNTIME_MANIFEST_INVALID'
    Assert-DesktopRuntimeReleaseValue 'package_lock_sha256' ([string]$manifest.package_lock_sha256).ToUpperInvariant() $Metadata.PackageLockSha256 'DESKTOP_RUNTIME_MANIFEST_INVALID'
    Assert-DesktopRuntimeReleaseValue 'executable_relative_path' $manifest.executable_relative_path 'LangBot Desktop RPA Runtime.exe' 'DESKTOP_RUNTIME_MANIFEST_INVALID'
    if ([string]$manifest.asset_sha256 -notmatch '^[A-Fa-f0-9]{64}$') { throw 'DESKTOP_RUNTIME_MANIFEST_INVALID: asset_sha256 is invalid.' }
    $manifest.asset_sha256 = ([string]$manifest.asset_sha256).ToUpperInvariant()
    if ($null -ne $Descriptor) {
        foreach ($field in @('runtime_version', 'protocol_version', 'platform', 'architecture', 'asset_name', 'asset_sha256', 'package_lock_sha256')) {
            Assert-DesktopRuntimeReleaseValue $field $manifest.$field $Descriptor.$field 'DESKTOP_RUNTIME_MANIFEST_INVALID'
        }
    }
    return $manifest
}

function Assert-DesktopRuntimeArtifact([string]$ArchivePath, [string]$ManifestPath, [object]$Metadata, [object]$Descriptor = $null) {
    if (-not (Test-Path -LiteralPath $ArchivePath -PathType Leaf) -or -not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { throw 'DESKTOP_RUNTIME_CACHE_INVALID: runtime archive or manifest is missing.' }
    $manifest = Read-DesktopRuntimeManifest $ManifestPath $Metadata $Descriptor
    $archiveName = [IO.Path]::GetFileName($ArchivePath)
    if ($archiveName.EndsWith('.partial', [StringComparison]::OrdinalIgnoreCase)) { $archiveName = $archiveName.Substring(0, $archiveName.Length - '.partial'.Length) }
    Assert-DesktopRuntimeReleaseValue 'asset_name' $manifest.asset_name $archiveName 'DESKTOP_RUNTIME_MANIFEST_INVALID'
    $actualHash = Get-Sha256 $ArchivePath
    if ($null -ne $Descriptor -and $actualHash -ne $Descriptor.asset_sha256) { throw 'DESKTOP_RUNTIME_ASSET_HASH_MISMATCH: descriptor hash does not match archive.' }
    if ($actualHash -ne $manifest.asset_sha256) { throw 'DESKTOP_RUNTIME_ASSET_HASH_MISMATCH: manifest hash does not match archive.' }
    return $manifest
}

function Get-VerifiedCachedDesktopRuntimeArtifact([object]$Descriptor, [object]$Metadata) {
    $cacheDir = Join-Path $desktopRuntimeCacheRoot ([string]$Descriptor.runtime_version)
    $archive = Join-Path $cacheDir ([string]$Descriptor.asset_name)
    $manifest = Join-Path $cacheDir ([string]$Descriptor.manifest_asset_name)
    $cachedDescriptor = Join-Path $cacheDir 'release-descriptor.json'
    try {
        $cacheDescriptor = Read-DesktopRuntimeReleaseDescriptor $Metadata $cachedDescriptor
        foreach ($field in @('repository', 'tag', 'asset_name', 'asset_sha256', 'package_lock_sha256')) {
            Assert-DesktopRuntimeReleaseValue $field $cacheDescriptor.$field $Descriptor.$field 'DESKTOP_RUNTIME_CACHE_INVALID'
        }
        Assert-DesktopRuntimeArtifact $archive $manifest $Metadata $Descriptor | Out-Null
        return [pscustomobject]@{ Archive = $archive; Manifest = $manifest; IsCache = $true }
    } catch {
        Write-SetupLog "DESKTOP_RUNTIME_CACHE_INVALID: $($_.Exception.Message)"
        return $null
    }
}

function Invoke-ApprovedDesktopRuntimeDownload([Uri]$InitialUri, [string]$PartialPath, [string]$FailureCode) {
    if (-not (Test-ApprovedDesktopRuntimeDownloadUri $InitialUri)) { throw 'DESKTOP_RUNTIME_RELEASE_REDIRECT_REJECTED: initial URL is not an approved HTTPS GitHub URL.' }
    Add-Type -AssemblyName System.Net.Http
    $handler = [System.Net.Http.HttpClientHandler]::new(); $handler.AllowAutoRedirect = $false
    $client = [System.Net.Http.HttpClient]::new($handler); $client.Timeout = [TimeSpan]::FromSeconds(60)
    $response = $null
    try {
        $currentUri = $InitialUri
        for ($redirects = 0; $redirects -le 5; $redirects++) {
            $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Get, $currentUri)
            $request.Headers.UserAgent.ParseAdd('wecome-bot-desktop-runtime-installer/1.0')
            $response = $client.SendAsync($request, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
            $statusCode = [int]$response.StatusCode
            if ($statusCode -in @(301, 302, 303, 307, 308)) {
                $location = $response.Headers.Location
                $response.Dispose(); $response = $null
                if ($null -eq $location) { throw "DESKTOP_RUNTIME_RELEASE_REDIRECT_REJECTED: HTTP $statusCode did not include a Location header." }
                $nextUri = [Uri]::new($currentUri, $location)
                if (-not (Test-ApprovedDesktopRuntimeDownloadUri $nextUri)) { throw "DESKTOP_RUNTIME_RELEASE_REDIRECT_REJECTED: redirect to $nextUri was rejected." }
                $currentUri = $nextUri
                continue
            }
            if (-not $response.IsSuccessStatusCode) { throw "${FailureCode}: HTTP $statusCode $($response.ReasonPhrase) for $currentUri" }
            if (-not (Test-ApprovedDesktopRuntimeDownloadUri $currentUri)) { throw "DESKTOP_RUNTIME_RELEASE_REDIRECT_REJECTED: final URL $currentUri was rejected." }
            Write-Host ("Downloading Desktop Runtime: {0}" -f $currentUri)
            $input = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
            try {
                $output = [IO.File]::Open($PartialPath, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
                try { $input.CopyTo($output) } finally { $output.Dispose() }
            } finally { $input.Dispose() }
            return
        }
        throw 'DESKTOP_RUNTIME_RELEASE_REDIRECT_REJECTED: redirect limit exceeded.'
    } catch [Threading.Tasks.TaskCanceledException] { throw "${FailureCode}: network timeout for $InitialUri" }
    catch { throw $_ }
    finally { if ($null -ne $response) { $response.Dispose() }; $client.Dispose(); $handler.Dispose() }
}

function Download-DesktopRuntimeReleaseToCache([object]$Descriptor, [object]$Metadata) {
    if ($null -ne $Descriptor.PSObject.Properties['release_available'] -and -not [bool]$Descriptor.release_available) { throw 'DESKTOP_RUNTIME_RELEASE_NOT_CONFIGURED: the administrator has not published the configured Desktop Runtime release.' }
    $cacheDir = Join-Path $desktopRuntimeCacheRoot ([string]$Descriptor.runtime_version)
    $lock = Acquire-DesktopRuntimeCacheLock $cacheDir
    try {
        $cached = Get-VerifiedCachedDesktopRuntimeArtifact $Descriptor $Metadata
        if ($null -ne $cached) { return $cached }
        $archive = Join-Path $cacheDir ([string]$Descriptor.asset_name); $manifest = Join-Path $cacheDir ([string]$Descriptor.manifest_asset_name); $cachedDescriptor = Join-Path $cacheDir 'release-descriptor.json'
        $archivePartial = "$archive.partial"; $manifestPartial = "$manifest.partial"; $descriptorPartial = "$cachedDescriptor.partial"
        try {
            Invoke-ApprovedDesktopRuntimeDownload (Get-DesktopRuntimeReleaseUri $Descriptor $Descriptor.asset_name) $archivePartial 'DESKTOP_RUNTIME_DOWNLOAD_FAILED'
            Invoke-ApprovedDesktopRuntimeDownload (Get-DesktopRuntimeReleaseUri $Descriptor $Descriptor.manifest_asset_name) $manifestPartial 'DESKTOP_RUNTIME_MANIFEST_DOWNLOAD_FAILED'
            [IO.File]::WriteAllText($descriptorPartial, (Get-Content -LiteralPath $desktopRuntimeReleaseDescriptorPath -Raw), (New-Object Text.UTF8Encoding($false)))
            Assert-DesktopRuntimeArtifact $archivePartial $manifestPartial $Metadata $Descriptor | Out-Null
            foreach ($existing in @($archive, $manifest, $cachedDescriptor)) { Move-InvalidDesktopRuntimeCacheFile $existing }
            Move-Item -LiteralPath $archivePartial -Destination $archive -ErrorAction Stop
            Move-Item -LiteralPath $manifestPartial -Destination $manifest -ErrorAction Stop
            Move-Item -LiteralPath $descriptorPartial -Destination $cachedDescriptor -ErrorAction Stop
            Assert-DesktopRuntimeArtifact $archive $manifest $Metadata $Descriptor | Out-Null
            return [pscustomobject]@{ Archive = $archive; Manifest = $manifest; IsCache = $true }
        } finally {
            foreach ($partial in @($archivePartial, $manifestPartial, $descriptorPartial)) { Remove-SafeDesktopRuntimePartialFile $partial }
        }
    } finally { $lock.Dispose() }
}

function Assert-SafeZipEntry([string]$EntryName, [string]$DestinationRoot) {
    $normalized = $EntryName.Replace('/', '\')
    if ([string]::IsNullOrWhiteSpace($normalized) -or $normalized.StartsWith('\') -or $normalized -match '^[A-Za-z]:') { throw "PREBUILT_RUNTIME_ZIP_UNSAFE_PATH: $EntryName" }
    foreach ($part in $normalized.Split('\')) { if ($part -eq '..') { throw "PREBUILT_RUNTIME_ZIP_UNSAFE_PATH: $EntryName" } }
    $target = [IO.Path]::GetFullPath((Join-Path $DestinationRoot $normalized))
    if (-not (Test-PathWithinRoot $target $DestinationRoot) -or [StringComparer]::OrdinalIgnoreCase.Equals($target, [IO.Path]::GetFullPath($DestinationRoot))) { throw "PREBUILT_RUNTIME_ZIP_UNSAFE_PATH: $EntryName" }
    return $target
}

function Test-DesktopRuntimePayload([string]$Root) {
    foreach ($relativePath in @('LangBot Desktop RPA Runtime.exe', 'resources\app.asar', 'chrome_100_percent.pak', 'icudtl.dat', 'resources.pak', 'libEGL.dll', 'libGLESv2.dll', 'ffmpeg.dll', 'resources\app.asar.unpacked\node_modules\@hurdlegroup', 'resources\app.asar.unpacked\node_modules\active-win', 'resources\app.asar.unpacked\node_modules\node-window-manager')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $relativePath))) { throw "PREBUILT_RUNTIME_PAYLOAD_INVALID: missing $relativePath" }
    }
}

function Test-DesktopRuntimePayloadIsValid([string]$Root) {
    try {
        Test-DesktopRuntimePayload $Root
        return $true
    } catch {
        return $false
    }
}

function Get-ManagedDesktopRuntimeDirectories([string]$Root, [string]$Kind) {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { return @() }
    $pattern = "^\.desktop-runtime-$Kind-[0-9a-f]{32}$"
    return @(Get-ChildItem -LiteralPath $Root -Force -Directory | Where-Object { $_.Name -match $pattern })
}

function Recover-DesktopRuntimeTransactions([string]$WinDir, [string]$UnpackedPath) {
    $managedPattern = '^(?:win-unpacked|\.desktop-runtime-(?:staging|backup)-[0-9a-f]{32})$'
    foreach ($staging in @(Get-ManagedDesktopRuntimeDirectories $WinDir 'staging')) {
        Remove-SafeCleanupDirectory $staging.FullName $repoRoot @($WinDir) $managedPattern 'PREBUILT_RUNTIME_STAGING_CLEANUP_FAILED' 3
    }

    $backups = @(Get-ManagedDesktopRuntimeDirectories $WinDir 'backup')
    $validBackups = @($backups | Where-Object { Test-DesktopRuntimePayloadIsValid $_.FullName })
    if (Test-DesktopRuntimePayloadIsValid $UnpackedPath) {
        foreach ($backup in $validBackups) {
            Remove-SafeCleanupDirectory $backup.FullName $repoRoot @($WinDir) $managedPattern 'PREBUILT_RUNTIME_BACKUP_CLEANUP_FAILED' 3
        }
        return
    }

    if ($validBackups.Count -gt 1) {
        throw "PREBUILT_RUNTIME_BACKUP_RECOVERY_AMBIGUOUS: multiple valid backups found: $($validBackups.FullName -join '; ')"
    }
    if ($validBackups.Count -eq 0) {
        if ($backups.Count -gt 0) { throw "PREBUILT_RUNTIME_BACKUP_RECOVERY_FAILED: no valid backup found: $($backups.FullName -join '; ')" }
        return
    }

    if (Test-Path -LiteralPath $UnpackedPath -PathType Container) {
        $quarantine = Join-Path $WinDir ('.desktop-runtime-staging-' + [guid]::NewGuid().ToString('N'))
        try {
            Move-Item -LiteralPath $UnpackedPath -Destination $quarantine -ErrorAction Stop
        } catch {
            throw "PREBUILT_RUNTIME_BACKUP_RECOVERY_FAILED: cannot preserve invalid runtime ${UnpackedPath}: $($_.Exception.Message)"
        }
    }
    try {
        Move-Item -LiteralPath $validBackups[0].FullName -Destination $UnpackedPath -ErrorAction Stop
    } catch {
        throw "PREBUILT_RUNTIME_BACKUP_RECOVERY_FAILED: cannot restore $($validBackups[0].FullName) to ${UnpackedPath}: $($_.Exception.Message)"
    }
}

function Expand-DesktopRuntimeArchiveSafely([string]$ArchivePath, [string]$StagingPath) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = $null
    try {
        $zip = [IO.Compression.ZipFile]::OpenRead($ArchivePath)
        foreach ($entry in $zip.Entries) {
            $target = Assert-SafeZipEntry $entry.FullName $StagingPath
            if ([string]::IsNullOrEmpty($entry.Name)) { New-Item -ItemType Directory -Path $target -Force | Out-Null; continue }
            New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($target)) -Force | Out-Null
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $true)
        }
    } catch { throw "PREBUILT_RUNTIME_ZIP_INVALID: $($_.Exception.Message)" }
    finally { if ($null -ne $zip) { $zip.Dispose() } }
    Test-DesktopRuntimePayload $StagingPath
}

function Install-PrebuiltDesktopRuntime([object]$Metadata) {
    if (($null -ne $DesktopRuntimeArchivePath) -xor ($null -ne $DesktopRuntimeManifestPath)) { throw 'DesktopRuntimeArchivePath and DesktopRuntimeManifestPath must be provided together.' }
    if ($DesktopRuntimeArchivePath) {
        $artifact = [pscustomobject]@{ Archive = [IO.Path]::GetFullPath($DesktopRuntimeArchivePath); Manifest = [IO.Path]::GetFullPath($DesktopRuntimeManifestPath); IsCache = $false }
        Assert-DesktopRuntimeArtifact $artifact.Archive $artifact.Manifest $Metadata | Out-Null
    } else {
        $descriptor = Read-DesktopRuntimeReleaseDescriptor $Metadata
        $artifact = Get-VerifiedCachedDesktopRuntimeArtifact $descriptor $Metadata
        if ($null -eq $artifact) { $artifact = Download-DesktopRuntimeReleaseToCache $descriptor $Metadata }
        Assert-DesktopRuntimeArtifact $artifact.Archive $artifact.Manifest $Metadata $descriptor | Out-Null
    }
    New-Item -ItemType Directory -Path $desktopRuntimeWinDir -Force | Out-Null
    Recover-DesktopRuntimeTransactions $desktopRuntimeWinDir $desktopRuntimeUnpackedPath
    # Keep extraction short enough for legacy Windows path limits; the final
    # move into win-unpacked remains transactional inside the Runtime output.
    $staging = Join-Path $desktopRuntimeCacheRoot ('.desktop-runtime-staging-' + [guid]::NewGuid().ToString('N'))
    $backup = Join-Path $desktopRuntimeWinDir ('.desktop-runtime-backup-' + [guid]::NewGuid().ToString('N'))
    $installationError = $null
    try {
        New-Item -ItemType Directory -Path $staging -Force | Out-Null
        Expand-DesktopRuntimeArchiveSafely $artifact.Archive $staging
        Stop-ExistingDesktopRuntimeProcesses $desktopRuntimeRoot $desktopRuntimeExecutable
        if (Test-Path -LiteralPath $desktopRuntimeUnpackedPath) { Move-Item -LiteralPath $desktopRuntimeUnpackedPath -Destination $backup -ErrorAction Stop }
        try {
            Move-Item -LiteralPath $staging -Destination $desktopRuntimeUnpackedPath -ErrorAction Stop
            Test-DesktopRuntimePayload $desktopRuntimeUnpackedPath
        } catch {
            $replacementFailure = $_.Exception
            try {
                if (Test-Path -LiteralPath $desktopRuntimeUnpackedPath -PathType Container) {
                    Remove-SafeDesktopRuntimeDirectory $desktopRuntimeUnpackedPath 'PREBUILT_RUNTIME_ROLLBACK_FAILED'
                }
                if (Test-Path -LiteralPath $backup -PathType Container) {
                    Move-Item -LiteralPath $backup -Destination $desktopRuntimeUnpackedPath -ErrorAction Stop
                }
            } catch {
                throw "PREBUILT_RUNTIME_ROLLBACK_FAILED: replacement failure: $($replacementFailure.Message); rollback failure: $($_.Exception.Message); paths: $desktopRuntimeUnpackedPath; $backup"
            }
            throw "PREBUILT_RUNTIME_FINAL_VALIDATION_FAILED: $($replacementFailure.Message); path: $desktopRuntimeUnpackedPath"
        }
        if (Test-Path -LiteralPath $backup -PathType Container) {
            Remove-SafeDesktopRuntimeDirectory $backup 'PREBUILT_RUNTIME_BACKUP_CLEANUP_FAILED' -RetryLockedFiles
        }
    } catch {
        $installationError = $_
    }
    try {
        if (Test-Path -LiteralPath $staging -PathType Container) {
            Remove-SafeDesktopRuntimeDirectory $staging 'PREBUILT_RUNTIME_STAGING_CLEANUP_FAILED' -RetryLockedFiles
        }
    } catch {
        if ($null -ne $installationError) {
            throw "PREBUILT_RUNTIME_STAGING_CLEANUP_FAILED: $($_.Exception.Message); original failure: $($installationError.Exception.Message)"
        }
        throw
    }
    if ($null -ne $installationError) { throw $installationError }
    try {
        Test-DesktopRuntimePayload $desktopRuntimeUnpackedPath
    } catch {
        throw "PREBUILT_RUNTIME_FINAL_VALIDATION_FAILED: $($_.Exception.Message); path: $desktopRuntimeUnpackedPath"
    }
    return $desktopRuntimeExecutable
}

function Install-DesktopRuntimeFromSource([string]$NpmPath, [object]$ManagedPython) {
    Stop-ExistingDesktopRuntimeProcesses $desktopRuntimeRoot $desktopRuntimeExecutable
    Push-Location $desktopRuntimeRoot
    try {
        Invoke-WithManagedPythonEnvironment $ManagedPython.Path {
            $runtimeInstall = Invoke-ExternalCommand $NpmPath @('ci')
            if ($runtimeInstall.ExitCode -ne 0) { Write-NpmLockErrorHint $runtimeInstall.Output; throw 'Desktop Runtime npm ci failed' }
            $nativeRebuild = Invoke-ExternalCommand $NpmPath @('run', 'rebuild:native'); if ($nativeRebuild.ExitCode -ne 0) { throw 'native rebuild failed' }
            $packageBuild = Invoke-ExternalCommand $NpmPath @('run', 'package:win:dir'); if ($packageBuild.ExitCode -ne 0) { throw 'package build failed' }
        }
    } finally { Pop-Location }
    if (-not (Test-Path -LiteralPath $desktopRuntimeExecutable -PathType Leaf)) { throw 'Runtime exe missing' }
}

function Invoke-SetupSource {
    $script:setupStage = 'source-prerequisites'
    if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) { throw 'This source distribution supports Windows x64 only.' }
    Write-Host '[1/6] Checking source prerequisites...'
    $git = Require-Command 'git.exe'; $node = Require-Command 'node.exe'; $npm = Require-Command 'npm.cmd'; $uv = Require-Command 'uv.exe'
    $nodeVersion = Get-TextCommand $node @('--version'); if ($nodeVersion -notmatch '^v22\.') { throw "Node.js 22.x is required; found $nodeVersion." }
    $metadata = Get-DesktopRuntimeMetadata
    foreach ($path in @((Join-Path $repoRoot 'uv.lock'), (Join-Path $webRoot 'package-lock.json'), (Join-Path $repoRoot 'vendor\wechat_decrypt\connector_runtime.py'), (Join-Path $repoRoot 'vendor\wechat_decrypt\mcp_wxwork_http_server.py'))) { if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required source entry or lock file is missing: $path" } }
    $lockFiles = @((Join-Path $repoRoot 'uv.lock'), (Join-Path $webRoot 'package-lock.json'), (Join-Path $webRoot 'pnpm-lock.yaml'), $desktopRuntimeLockPath) | Where-Object { Test-Path -LiteralPath $_ }; $before = @{}; foreach ($lockFile in $lockFiles) { $before[$lockFile] = Get-Sha256 $lockFile }
    $script:setupStage = 'managed-python'
    Write-Host '[2/6] Preparing managed Python 3.12...'; & $uv python install 3.12; if ($LASTEXITCODE -ne 0) { throw 'uv python install 3.12 failed.' }
    $existingVenvPython = Get-ExistingVenvPythonVersion $venvPath
    $script:setupStage = 'python-dependencies'
    Write-Host '[3/6] Installing Python dependencies...'; Push-Location $repoRoot; try { $syncExitCode = Invoke-ManagedPythonSync $uv; if ($syncExitCode -ne 0 -and $existingVenvPython -and $existingVenvPython -notmatch '^Python 3\.12\.') { Remove-IncompatibleProjectVenv $venvPath; $syncExitCode = Invoke-ManagedPythonSync $uv }; if ($syncExitCode -ne 0) { throw 'uv sync --frozen --dev --python 3.12 --managed-python failed.' } } finally { Pop-Location }
    $script:setupStage = 'web-dependencies'
    Write-Host '[4/6] Installing Web dependencies...'; Push-Location $webRoot; try { & $npm ci; if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' } } finally { Pop-Location }
    $script:setupStage = 'desktop-runtime-install'
    $desktopRuntime = if ($BuildDesktopRuntimeFromSource) { Write-Host '[5/6] Building Desktop Runtime from source...'; Install-DesktopRuntimeFromSource $npm (Get-RequiredProjectPython $repoRoot) } else { Write-Host '[5/6] Installing prebuilt Desktop Runtime...'; Install-PrebuiltDesktopRuntime $metadata }
    $script:setupStage = 'environment-verification'
    Write-Host '[6/6] Verifying environment...'; $venvPython = Join-Path $venvPath 'Scripts\python.exe'; $pythonVersion = Get-TextCommand $venvPython @('--version'); $onnxruntimeVersion = Get-TextCommand $venvPython @('-c', 'import onnxruntime; print(onnxruntime.__version__)')
    foreach ($lockFile in $lockFiles) { if ($before[$lockFile] -ne (Get-Sha256 $lockFile)) { throw "Dependency installation modified lock file: $lockFile" } }
    [ordered]@{ status = 'ok'; python = $pythonVersion; pythonExecutable = $venvPython; onnxruntime = $onnxruntimeVersion; git = (Get-TextCommand $git @('--version')); node = $nodeVersion; npm = (Get-TextCommand $npm @('--version')); uv = (Get-TextCommand $uv @('--version')); desktopRuntime = $desktopRuntime; desktopRuntimeMode = $(if ($BuildDesktopRuntimeFromSource) { 'source' } else { 'prebuilt' }); locks = 'verified-unchanged'; wechatDecrypt = 'vendor/wechat_decrypt/mcp_wxwork_http_server.py' } | ConvertTo-Json
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        Invoke-SetupSource
    } catch {
        $code = Get-SetupFailureCode $_
        $failure = Format-SetupFailure $code $script:setupStage $_.Exception.Message @($desktopRuntimeWinDir, $desktopRuntimeCacheRoot, $setupLogPath)
        Write-SetupLog $failure
        Write-Host $failure
        exit 1
    }
}
