Set-StrictMode -Version Latest

function Get-NormalizedPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    return [System.IO.Path]::GetFullPath($Path)
}

function Resolve-BuildPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BasePath,

        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return Get-NormalizedPath -Path $Path
    }

    return Get-NormalizedPath -Path (Join-Path $BasePath $Path)
}

function Test-PathUnderRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    $normalizedPath = (Get-NormalizedPath -Path $Path).TrimEnd('\')
    $normalizedRoot = (Get-NormalizedPath -Path $Root).TrimEnd('\')

    return ($normalizedPath -eq $normalizedRoot) -or $normalizedPath.StartsWith($normalizedRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)
}

function Ensure-Directory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Read-JsonFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    return (Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json)
}

function New-BuildContext {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,

        [Parameter(Mandatory = $true)]
        [string]$OutputRoot,

        [Parameter(Mandatory = $true)]
        [string]$Version,

        [Parameter(Mandatory = $true)]
        [bool]$Offline,

        [Parameter(Mandatory = $true)]
        [bool]$SkipTests,

        [Parameter(Mandatory = $true)]
        [bool]$KeepWorkDirectory,

        [Parameter(Mandatory = $true)]
        [bool]$PortableOnly,

        [Parameter(Mandatory = $false)]
        [AllowEmptyString()]
        [string]$VcRedistPath,

        [Parameter(Mandatory = $false)]
        [AllowEmptyString()]
        [string]$AuditWechatDecryptSource
    )

    $normalizedRepoRoot = Get-NormalizedPath -Path $RepoRoot
    $normalizedOutputRoot = Resolve-BuildPath -BasePath $normalizedRepoRoot -Path $OutputRoot
    Ensure-Directory -Path $normalizedOutputRoot

    $workDirectory = Join-Path $normalizedOutputRoot ("task14-work-" + [System.Guid]::NewGuid().ToString('N'))
    Ensure-Directory -Path $workDirectory

    $runtimeManifestPath = Join-Path $normalizedRepoRoot 'packaging\runtime-manifest.json'
    $portableLayoutPath = Join-Path $normalizedRepoRoot 'packaging\build\portable-layout.json'
    $runtimeManifest = Read-JsonFile -Path $runtimeManifestPath
    $portableLayout = Read-JsonFile -Path $portableLayoutPath

    $portableDirectoryName = $portableLayout.portableDirectoryNameTemplate.Replace('{version}', $Version)
    $portableRoot = Join-Path $normalizedOutputRoot $portableDirectoryName
    $logPath = Join-Path $workDirectory 'build-trial-release.log'
    $runtimeCacheRoot = Resolve-BuildPath -BasePath $normalizedRepoRoot -Path $runtimeManifest.cache.root
    Ensure-Directory -Path $runtimeCacheRoot

    $context = @{
        RepoRoot = $normalizedRepoRoot
        OutputRoot = $normalizedOutputRoot
        PortableRoot = $portableRoot
        WorkDirectory = $workDirectory
        LogPath = $logPath
        RuntimeManifest = $runtimeManifest
        PortableLayout = $portableLayout
        RuntimeCacheRoot = $runtimeCacheRoot
        Offline = $Offline
        SkipTests = $SkipTests
        KeepWorkDirectory = $KeepWorkDirectory
        PortableOnly = $PortableOnly
        Version = $Version
        VcRedistPath = $VcRedistPath
        AuditWechatDecryptSource = $AuditWechatDecryptSource
        StageResults = New-Object System.Collections.ArrayList
        FailedStage = $null
    }

    return $context
}

function Write-BuildMessage {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Context,

        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $timestamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $line = "[{0}] {1}" -f $timestamp, $Message
    Write-Host $line
    Add-Content -LiteralPath $Context.LogPath -Value $line
}

function Invoke-BuildStage {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Context,

        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [scriptblock]$Action
    )

    $start = Get-Date
    Write-BuildMessage -Context $Context -Message ("Stage: {0} | Started: {1}" -f $Name, $start.ToString('s'))

    try {
        & $Action
        $end = Get-Date
        $duration = New-TimeSpan -Start $start -End $end
        Write-BuildMessage -Context $Context -Message ("Stage: {0} | Completed: {1} | Duration: {2}" -f $Name, $end.ToString('s'), $duration.ToString())
        [void]$Context.StageResults.Add([pscustomobject]@{
            Name = $Name
            StartedAt = $start
            CompletedAt = $end
            Duration = $duration
            Succeeded = $true
        })
    }
    catch {
        $end = Get-Date
        $duration = New-TimeSpan -Start $start -End $end
        $Context.FailedStage = $Name
        Write-BuildMessage -Context $Context -Message ("Stage: {0} | Failed: {1} | Duration: {2}" -f $Name, $end.ToString('s'), $duration.ToString())
        Write-BuildMessage -Context $Context -Message ("Stage error detail: {0}" -f $_.Exception.ToString())
        [void]$Context.StageResults.Add([pscustomobject]@{
            Name = $Name
            StartedAt = $start
            CompletedAt = $end
            Duration = $duration
            Succeeded = $false
        })
        throw
    }
}

function Ensure-CommandAvailable {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandName
    )

    $resolved = Get-Command $CommandName -ErrorAction SilentlyContinue
    if (-not $resolved) {
        throw "Required command not found: $CommandName"
    }

    return $resolved.Source
}

function Invoke-ExternalCommand {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Context,

        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [string[]]$ArgumentList = @(),

        [string]$WorkingDirectory = $Context.RepoRoot,

        [hashtable]$Environment = @{},

        [int[]]$AllowedExitCodes = @(0)
    )

    $oldValues = @{}
    foreach ($key in $Environment.Keys) {
        $oldValues[$key] = [System.Environment]::GetEnvironmentVariable($key, 'Process')
        [System.Environment]::SetEnvironmentVariable($key, [string]$Environment[$key], 'Process')
    }

    Push-Location $WorkingDirectory
    try {
        & $FilePath @ArgumentList
        $exitCode = if ($LASTEXITCODE -is [int]) { $LASTEXITCODE } else { 0 }
        if ($AllowedExitCodes -notcontains $exitCode) {
            throw "Command failed with exit code ${exitCode}: $FilePath $($ArgumentList -join ' ')"
        }
    }
    finally {
        Pop-Location
        foreach ($key in $oldValues.Keys) {
            [System.Environment]::SetEnvironmentVariable($key, $oldValues[$key], 'Process')
        }
    }
}

function Reset-ManagedPath {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Context,

        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string[]]$AllowedRoots
    )

    $normalizedPath = Get-NormalizedPath -Path $Path
    $allowed = $false
    foreach ($root in $AllowedRoots) {
        if (Test-PathUnderRoot -Path $normalizedPath -Root $root) {
            $allowed = $true
            break
        }
    }

    if (-not $allowed) {
        throw "Refusing to remove unmanaged path: $normalizedPath"
    }

    if (Test-Path -LiteralPath $normalizedPath) {
        if (Test-Path -LiteralPath $normalizedPath -PathType Container) {
            $null = & cmd.exe /d /c "rmdir /s /q `"$normalizedPath`""
            if ($LASTEXITCODE -ne 0 -and (Test-Path -LiteralPath $normalizedPath)) {
                throw "Failed to remove directory: $normalizedPath"
            }
        }
        else {
            Remove-Item -LiteralPath $normalizedPath -Force
        }
    }
}

function Invoke-Robocopy {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,

        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    Ensure-Directory -Path $Destination
    $null = & robocopy $Source $Destination /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP
    $exitCode = $LASTEXITCODE
    if ($exitCode -ge 8) {
        throw "robocopy failed with exit code $exitCode from $Source to $Destination"
    }
}

function Copy-FileWithParent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,

        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    Ensure-Directory -Path ([System.IO.Path]::GetDirectoryName($Destination))
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

function Get-RelativePathCompat {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BasePath,

        [Parameter(Mandatory = $true)]
        [string]$TargetPath
    )

    $baseUri = New-Object System.Uri(((Get-NormalizedPath -Path $BasePath).TrimEnd('\') + '\'))
    $targetUri = New-Object System.Uri((Get-NormalizedPath -Path $TargetPath))
    return [System.Uri]::UnescapeDataString($baseUri.MakeRelativeUri($targetUri).ToString()).Replace('/', '\')
}

function Ensure-Sha256Match {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedSha256
    )

    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    $expected = $ExpectedSha256.ToLowerInvariant()
    if ($actual -ne $expected) {
        throw "SHA-256 mismatch for $Path. Expected $expected, got $actual"
    }
}

function Expand-TarGzArchive {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ArchivePath,

        [Parameter(Mandatory = $true)]
        [string]$DestinationPath
    )

    Ensure-Directory -Path $DestinationPath
    $null = & tar -xzf $ArchivePath -C $DestinationPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to extract archive: $ArchivePath"
    }
}

function Get-RuntimeRoleManifest {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Context,

        [Parameter(Mandatory = $true)]
        [ValidateSet('server', 'connector')]
        [string]$Role
    )

    return $Context.RuntimeManifest.$Role
}

function Ensure-RuntimeArchiveCached {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Context,

        [Parameter(Mandatory = $true)]
        [ValidateSet('server', 'connector')]
        [string]$Role
    )

    $roleManifest = Get-RuntimeRoleManifest -Context $Context -Role $Role
    $archiveRelative = $Context.RuntimeManifest.cache.archivePathTemplate.Replace('{artifactName}', $roleManifest.artifactName)
    $archivePath = Resolve-BuildPath -BasePath $Context.RuntimeCacheRoot -Path $archiveRelative
    Ensure-Directory -Path ([System.IO.Path]::GetDirectoryName($archivePath))

    if (-not (Test-Path -LiteralPath $archivePath)) {
        if ($Context.Offline) {
            throw "Offline mode requires cached runtime archive for ${Role}: $archivePath"
        }

        Write-BuildMessage -Context $Context -Message ("Downloading runtime archive for {0}: {1}" -f $Role, $roleManifest.url)
        Invoke-WebRequest -Uri $roleManifest.url -OutFile $archivePath
    }

    Ensure-Sha256Match -Path $archivePath -ExpectedSha256 $roleManifest.sha256
    return $archivePath
}

function Ensure-ExpandedRuntimeCache {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Context,

        [Parameter(Mandatory = $true)]
        [ValidateSet('server', 'connector')]
        [string]$Role
    )

    $roleManifest = Get-RuntimeRoleManifest -Context $Context -Role $Role
    $archivePath = Ensure-RuntimeArchiveCached -Context $Context -Role $Role
    $expandedRelative = $Context.RuntimeManifest.cache.extractionPathTemplate.Replace('{role}', $Role).Replace('{version}', $roleManifest.version)
    $expandedPath = Resolve-BuildPath -BasePath $Context.RuntimeCacheRoot -Path $expandedRelative
    $expectedPython = Resolve-BuildPath -BasePath $expandedPath -Path $roleManifest.extractedLayout.pythonExe

    if (Test-Path -LiteralPath $expectedPython) {
        return $expandedPath
    }

    Reset-ManagedPath -Context $Context -Path $expandedPath -AllowedRoots @($Context.RuntimeCacheRoot)
    Ensure-Directory -Path $expandedPath

    $tempExtractPath = Join-Path $Context.WorkDirectory ("extract-" + $Role)
    Reset-ManagedPath -Context $Context -Path $tempExtractPath -AllowedRoots @($Context.WorkDirectory)
    Ensure-Directory -Path $tempExtractPath

    Expand-TarGzArchive -ArchivePath $archivePath -DestinationPath $tempExtractPath
    Invoke-Robocopy -Source $tempExtractPath -Destination $expandedPath

    if (-not (Test-Path -LiteralPath $expectedPython)) {
        throw "Expanded runtime for $Role is missing python executable: $expectedPython"
    }

    return $expandedPath
}

function Install-LockedPythonDependencies {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Context,

        [Parameter(Mandatory = $true)]
        [ValidateSet('server', 'connector')]
        [string]$Role,

        [Parameter(Mandatory = $true)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory = $true)]
        [string]$RequirementsPath
    )

    $runtimeManifest = Get-RuntimeRoleManifest -Context $Context -Role $Role
    $pythonExe = Resolve-BuildPath -BasePath $RuntimeRoot -Path $runtimeManifest.extractedLayout.pythonExe
    $uvCacheRoot = Join-Path $Context.RuntimeCacheRoot ('uv-cache\' + $Role)
    Ensure-Directory -Path $uvCacheRoot

    if ($Context.Offline) {
        $cacheEntries = Get-ChildItem -LiteralPath $uvCacheRoot -Force -ErrorAction SilentlyContinue
        if (-not $cacheEntries) {
            throw "Offline mode requires cached uv artifacts for ${Role}: $uvCacheRoot"
        }
    }

    $arguments = @(
        'pip', 'install',
        '--python', $pythonExe,
        '--no-verify-hashes',
        '--link-mode', 'copy',
        '--no-python-downloads',
        '--cache-dir', $uvCacheRoot,
        '-r', $RequirementsPath
    )
    if ($Context.Offline) {
        $arguments += '--offline'
    }

    Invoke-ExternalCommand -Context $Context -FilePath 'uv' -WorkingDirectory $Context.RepoRoot -ArgumentList $arguments
}

function Remove-WorkDirectoryIfNeeded {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Context,

        [switch]$PreserveOnFailure
    )

    if ($Context.KeepWorkDirectory) {
        Write-BuildMessage -Context $Context -Message ("Keeping work directory: {0}" -f $Context.WorkDirectory)
        return
    }

    if ($PreserveOnFailure) {
        Write-BuildMessage -Context $Context -Message ("Build failed; preserving work directory for diagnostics: {0}" -f $Context.WorkDirectory)
        return
    }

    if (Test-Path -LiteralPath $Context.WorkDirectory) {
        $null = & cmd.exe /d /c "rmdir /s /q `"$($Context.WorkDirectory)`""
        if ($LASTEXITCODE -ne 0 -and (Test-Path -LiteralPath $Context.WorkDirectory)) {
            Write-BuildMessage -Context $Context -Message ("Work directory cleanup failed; preserving path: {0}" -f $Context.WorkDirectory)
        }
    }
}

Export-ModuleMember -Function @(
    'Copy-FileWithParent',
    'Ensure-CommandAvailable',
    'Ensure-Directory',
    'Ensure-ExpandedRuntimeCache',
    'Ensure-RuntimeArchiveCached',
    'Ensure-Sha256Match',
    'Expand-TarGzArchive',
    'Get-NormalizedPath',
    'Get-RelativePathCompat',
    'Get-RuntimeRoleManifest',
    'Install-LockedPythonDependencies',
    'Invoke-BuildStage',
    'Invoke-ExternalCommand',
    'Invoke-Robocopy',
    'New-BuildContext',
    'Read-JsonFile',
    'Remove-WorkDirectoryIfNeeded',
    'Reset-ManagedPath',
    'Resolve-BuildPath',
    'Test-PathUnderRoot',
    'Write-BuildMessage'
)
