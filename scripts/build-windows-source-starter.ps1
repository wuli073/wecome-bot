[CmdletBinding()]
param(
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version = '0.1.0',
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$defaultOutputDirectory = Join-Path $repoRoot 'distribution\packages\windows-source-starter'
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = $defaultOutputDirectory
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Assert-SafeStarterStagingDirectory([string]$Path, [string]$AllowedRoot) {
    if ([string]::IsNullOrWhiteSpace($Path)) { throw 'Starter staging path is empty.' }
    $fullPath = [IO.Path]::GetFullPath($Path)
    $fullAllowedRoot = [IO.Path]::GetFullPath($AllowedRoot).TrimEnd('\')
    $repo = [IO.Path]::GetFullPath($repoRoot).TrimEnd('\')
    $repoParent = [IO.Path]::GetFullPath((Split-Path -Parent $repoRoot)).TrimEnd('\')
    $driveRoot = [IO.Path]::GetPathRoot($fullPath).TrimEnd('\')
    $userProfile = [IO.Path]::GetFullPath([Environment]::GetFolderPath('UserProfile')).TrimEnd('\')
    if ($fullPath -in @($fullAllowedRoot, $repo, $repoParent, $driveRoot, $userProfile)) { throw 'Starter staging path is outside the permitted cleanup boundary.' }
    if (-not $fullPath.StartsWith($fullAllowedRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Starter staging path must be beneath the output directory.' }
    if ([IO.Path]::GetFileName($fullPath) -notmatch '^\.starter-staging-[0-9a-f]{32}$') { throw 'Starter staging path name is invalid.' }
}

function Remove-SafeStarterStagingDirectory([string]$Path, [string]$AllowedRoot) {
    Assert-SafeStarterStagingDirectory $Path $AllowedRoot
    if (Test-Path -LiteralPath $Path -PathType Container) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Convert-ToUtf8NoBomCrLf([string]$SourcePath, [string]$DestinationPath) {
    $content = [IO.File]::ReadAllText($SourcePath)
    $content = [regex]::Replace($content, "`r?`n", "`r`n")
    [IO.File]::WriteAllText($DestinationPath, $content, [Text.UTF8Encoding]::new($false))
}

function Assert-BatchSource([string]$Path) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) { throw "Batch source contains a UTF-8 BOM: $Path" }
    $text = [Text.UTF8Encoding]::new($false, $true).GetString($bytes)
    if (-not $text.StartsWith('@echo off')) { throw "Batch source does not start with @echo off: $Path" }
    if ($text -match '(?m)(?<!\r)\n') { throw "Batch source must use CRLF: $Path" }
    if ($text -match '[A-Za-z]:\\Users\\|C:\\Users\\') { throw "Batch source contains an absolute personal path: $Path" }
}

function Assert-RuntimeReleaseContract([string]$Path) {
    $descriptor = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if ($descriptor.release_available -ne $true) { throw 'Desktop Runtime Release must be marked available.' }
    if ([string]::IsNullOrWhiteSpace($descriptor.tag) -or $descriptor.tag -eq 'latest') { throw 'Desktop Runtime Release must use a fixed tag.' }
    foreach ($property in @('runtime_version', 'protocol_version', 'asset_name', 'asset_sha256')) {
        if ($null -eq $descriptor.$property -or [string]::IsNullOrWhiteSpace([string]$descriptor.$property)) { throw "Desktop Runtime Release descriptor is missing $property." }
    }
    return $descriptor
}

if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 is required to build the Windows Source Starter.' }
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot '.git') -PathType Container)) { throw "Repository root was not found: $repoRoot" }

$sourceDirectory = Join-Path $repoRoot 'distribution\windows-source'
$fileNames = @('01-check-environment.bat', '02-install-wecome-bot.bat', '03-start-wecome-bot.bat', 'README-安装说明.txt')
foreach ($name in $fileNames) {
    $sourcePath = Join-Path $sourceDirectory $name
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) { throw "Missing Starter source file: $sourcePath" }
    if ($name -like '*.bat') { Assert-BatchSource $sourcePath }
}

$releaseDescriptor = Assert-RuntimeReleaseContract (Join-Path $repoRoot 'distribution\runtime\desktop-runtime-release.json')
$startSource = Get-Content -LiteralPath (Join-Path $repoRoot 'scripts\start-source.ps1') -Raw
foreach ($setting in @("LANGBOT_RPA_FORCE_DISABLE_SEND='0'", "LANGBOT_RPA_ALLOW_AUTO_SEND='1'", "LANGBOT_BROADCAST_SEND_ENABLED='1'", "LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS='*'", "realSend='enabled'")) {
    if ($startSource -notmatch [regex]::Escape($setting)) { throw "Required real-send default is missing: $setting" }
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$staging = Join-Path $OutputDirectory ('.starter-staging-' + [guid]::NewGuid().ToString('N'))
Assert-SafeStarterStagingDirectory $staging $OutputDirectory
New-Item -ItemType Directory -Path $staging -Force | Out-Null

try {
    $zipInput = Join-Path $staging 'zip-input'
    New-Item -ItemType Directory -Path $zipInput -Force | Out-Null
    foreach ($name in $fileNames) {
        $sourcePath = Join-Path $sourceDirectory $name
        $destinationPath = Join-Path $zipInput $name
        if ($name -like '*.bat') { Convert-ToUtf8NoBomCrLf $sourcePath $destinationPath }
        else { [IO.File]::WriteAllText($destinationPath, [IO.File]::ReadAllText($sourcePath), [Text.UTF8Encoding]::new($false)) }
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $assetName = "Wecome-Bot-Source-Starter-v$Version.zip"
    $stagedZip = Join-Path $staging $assetName
    [IO.Compression.ZipFile]::CreateFromDirectory($zipInput, $stagedZip, [IO.Compression.CompressionLevel]::Optimal, $false)
    $assetHash = Get-Sha256 $stagedZip
    $fileMetadata = foreach ($name in $fileNames) {
        $filePath = Join-Path $zipInput $name
        [ordered]@{ relative_path = $name; size = ([IO.FileInfo]$filePath).Length; sha256 = Get-Sha256 $filePath }
    }
    $manifest = [ordered]@{
        schema_version = 1
        product = 'Wecome Bot Source Starter'
        starter_version = $Version
        source_repository = 'wuli073/wecome-bot'
        source_branch = 'main'
        source_commit = (& git -C $repoRoot rev-parse HEAD).Trim()
        runtime_release_tag = $releaseDescriptor.tag
        runtime_version = $releaseDescriptor.runtime_version
        protocol_version = $releaseDescriptor.protocol_version
        real_send_default_enabled = $true
        asset_name = $assetName
        asset_sha256 = $assetHash
        asset_size = ([IO.FileInfo]$stagedZip).Length
        files = @($fileMetadata)
        created_at = [DateTime]::UtcNow.ToString('o')
    }
    if ($LASTEXITCODE -ne 0) { throw 'Unable to read the current source commit.' }
    $stagedSha = Join-Path $staging ($assetName + '.sha256')
    [IO.File]::WriteAllText($stagedSha, "$assetHash  $assetName`r`n", [Text.UTF8Encoding]::new($false))
    $stagedManifest = Join-Path $staging 'starter-manifest.json'
    [IO.File]::WriteAllText($stagedManifest, ($manifest | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))

    Copy-Item -LiteralPath $stagedZip -Destination (Join-Path $OutputDirectory $assetName) -Force
    Copy-Item -LiteralPath $stagedSha -Destination (Join-Path $OutputDirectory ($assetName + '.sha256')) -Force
    Copy-Item -LiteralPath $stagedManifest -Destination (Join-Path $OutputDirectory 'starter-manifest.json') -Force
} finally {
    Remove-SafeStarterStagingDirectory $staging $OutputDirectory
}
