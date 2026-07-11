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

function Assert-NoReparsePointInPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    $normalizedPath = (Get-NormalizedPath -Path $Path).TrimEnd('\')
    $normalizedRoot = (Get-NormalizedPath -Path $Root).TrimEnd('\')
    $pathsToInspect = @($normalizedRoot)
    if ($normalizedPath.Length -gt $normalizedRoot.Length) {
        $relativeSegments = $normalizedPath.Substring($normalizedRoot.Length + 1).Split('\')
        $currentPath = $normalizedRoot
        foreach ($segment in $relativeSegments) {
            $currentPath = Join-Path $currentPath $segment
            $pathsToInspect += $currentPath
        }
    }

    foreach ($candidate in $pathsToInspect) {
        if (-not (Test-Path -LiteralPath $candidate)) { continue }
        $item = Get-Item -LiteralPath $candidate -Force -ErrorAction Stop
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing to remove path through reparse point: $candidate"
        }
    }
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

    $sessionId = [System.Guid]::NewGuid().ToString('N')
    $sessionShortId = $sessionId.Substring(0, 12)
    $sessionRoot = Join-Path (Join-Path $normalizedOutputRoot '.s') $sessionShortId
    Ensure-Directory -Path $sessionRoot
    $workDirectory = Join-Path $sessionRoot 'work'
    Ensure-Directory -Path $workDirectory

    $runtimeManifestPath = Join-Path $normalizedRepoRoot 'packaging\runtime-manifest.json'
    $portableLayoutPath = Join-Path $normalizedRepoRoot 'packaging\build\portable-layout.json'
    $runtimeManifest = Read-JsonFile -Path $runtimeManifestPath
    $portableLayout = Read-JsonFile -Path $portableLayoutPath

    $portableDirectoryName = 'portable'
    $sessionReleaseRoot = Join-Path $sessionRoot 'r'
    $releasePublishRoot = Join-Path $normalizedOutputRoot ("release-{0}" -f $Version)
    $internalRoot = Join-Path $sessionReleaseRoot 'internal'
    $publicRoot = Join-Path $sessionReleaseRoot 'public'
    $portableRoot = Join-Path $internalRoot $portableDirectoryName
    $portableZipStagingPath = Join-Path $internalRoot ("Chatbot-Trial-{0}-x64.zip" -f $Version)
    $portableZipSha256StagingPath = $portableZipStagingPath + '.sha256'
    $setupPublishPath = Join-Path $publicRoot ("Chatbot-Setup-{0}-x64.exe" -f $Version)
    $installerStageRoot = Join-Path $workDirectory 'installer-input'
    $installerInputRoot = Join-Path $installerStageRoot $portableDirectoryName
    $logPath = Join-Path $workDirectory 'build-trial-release.log'
    $runtimeCacheRoot = Resolve-BuildPath -BasePath $normalizedRepoRoot -Path $runtimeManifest.cache.root
    Ensure-Directory -Path $runtimeCacheRoot

    $context = @{
        RepoRoot = $normalizedRepoRoot
        OutputRoot = $normalizedOutputRoot
        SessionId = $sessionId
        SessionShortId = $sessionShortId
        SessionReleaseRoot = $sessionReleaseRoot
        ReleasePublishRoot = $releasePublishRoot
        InternalRoot = $internalRoot
        PublicRoot = $publicRoot
        PortableRoot = $portableRoot
        PortableZipStagingPath = $portableZipStagingPath
        PortableZipSha256StagingPath = $portableZipSha256StagingPath
        PortableZipPath = $null
        PortableZipSha256Path = $null
        SetupPublishPath = $setupPublishPath
        InstallerStageRoot = $installerStageRoot
        InstallerInputRoot = $installerInputRoot
        SetupPath = $null
        WorkDirectory = $workDirectory
        LogPath = $logPath
        RuntimeManifest = $runtimeManifest
        PortableLayout = $portableLayout
        RuntimeCacheRoot = $runtimeCacheRoot
        Offline = $Offline
        SkipTests = $SkipTests
        KeepWorkDirectory = $KeepWorkDirectory
        PortableOnly = $PortableOnly
        ReleasePublished = $false
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

    foreach ($root in $AllowedRoots) {
        if (Test-PathUnderRoot -Path $normalizedPath -Root $root) {
            Assert-NoReparsePointInPath -Path $normalizedPath -Root $root
            break
        }
    }

    if (Test-Path -LiteralPath $normalizedPath) {
        if (Test-Path -LiteralPath $normalizedPath -PathType Container) {
            $null = & cmd.exe /d /c "rmdir /s /q `"$normalizedPath`""
            if ($LASTEXITCODE -ne 0 -and (Test-Path -LiteralPath $normalizedPath)) {
                throw "Failed to remove directory: $normalizedPath"
            }
        }
        else {
            Remove-Item -LiteralPath $normalizedPath -Force -ErrorAction Stop
        }
    }
}

function Get-OutputPathConsumers {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $normalizedPath = Get-NormalizedPath -Path $Path
    $isDirectory = Test-Path -LiteralPath $normalizedPath -PathType Container

    $matches = foreach ($process in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) {
        if ([int]$process.ProcessId -eq $PID) {
            continue
        }
        $executablePath = [string]$process.ExecutablePath
        $commandLine = [string]$process.CommandLine
        $referencesPath = $false

        if ($executablePath) {
            if ($isDirectory) {
                $referencesPath = Test-PathUnderRoot -Path $executablePath -Root $normalizedPath
            }
            else {
                $referencesPath = $executablePath.Equals($normalizedPath, [System.StringComparison]::OrdinalIgnoreCase)
            }
        }

        if (-not $referencesPath -and $commandLine) {
            $referencesPath = $commandLine.IndexOf($normalizedPath, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
        }

        if (-not $referencesPath) {
            continue
        }

        [pscustomobject]@{
            ProcessId = [int]$process.ProcessId
            ParentProcessId = [int]$process.ParentProcessId
            Name = [string]$process.Name
            ExecutablePath = $executablePath
            CommandLine = $commandLine
            CreationTime = [string]$process.CreationDate
        }
    }

    return @($matches | Sort-Object ProcessId)
}

function Format-OutputConsumersSummary {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Consumers
    )

    return (($Consumers | ForEach-Object {
        "PID=$($_.ProcessId), ParentPID=$($_.ParentProcessId), ExecutablePath=$($_.ExecutablePath), CommandLine=$($_.CommandLine), CreationTime=$($_.CreationTime)"
    }) -join '; ')
}

function Assert-OutputPathNotInUse {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $consumers = @(Get-OutputPathConsumers -Path $Path)
    if ($consumers.Count -gt 0) {
        $summary = Format-OutputConsumersSummary -Consumers $consumers
        throw "RELEASE_OUTPUT_IN_USE: $Path; $summary"
    }
}

function Publish-StagedFile {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Context,

        [Parameter(Mandatory = $true)]
        [string]$StagingPath,

        [Parameter(Mandatory = $true)]
        [string]$DestinationPath
    )

    $normalizedStagingPath = Get-NormalizedPath -Path $StagingPath
    $normalizedDestinationPath = Get-NormalizedPath -Path $DestinationPath
    Assert-OutputPathNotInUse -Path $normalizedDestinationPath
    Ensure-Directory -Path ([System.IO.Path]::GetDirectoryName($normalizedDestinationPath))

    $previousPath = $normalizedDestinationPath + '.previous-' + $Context.SessionId
    if (Test-Path -LiteralPath $previousPath) {
        Reset-ManagedPath -Context $Context -Path $previousPath -AllowedRoots @($Context.OutputRoot)
    }

    try {
        if (Test-Path -LiteralPath $normalizedDestinationPath -PathType Leaf) {
            Move-Item -LiteralPath $normalizedDestinationPath -Destination $previousPath -Force -ErrorAction Stop
        }

        Move-Item -LiteralPath $normalizedStagingPath -Destination $normalizedDestinationPath -Force -ErrorAction Stop

        if (Test-Path -LiteralPath $previousPath) {
            Remove-Item -LiteralPath $previousPath -Force -ErrorAction Stop
        }
    }
    catch {
        if (-not (Test-Path -LiteralPath $normalizedDestinationPath) -and (Test-Path -LiteralPath $previousPath)) {
            Move-Item -LiteralPath $previousPath -Destination $normalizedDestinationPath -Force -ErrorAction SilentlyContinue
        }
        throw
    }
}

function Publish-StagedDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Context,

        [Parameter(Mandatory = $true)]
        [string]$StagingPath,

        [Parameter(Mandatory = $true)]
        [string]$DestinationPath
    )

    $normalizedStagingPath = Get-NormalizedPath -Path $StagingPath
    $normalizedDestinationPath = Get-NormalizedPath -Path $DestinationPath
    Assert-OutputPathNotInUse -Path $normalizedDestinationPath
    Ensure-Directory -Path ([System.IO.Path]::GetDirectoryName($normalizedDestinationPath))

    $previousPath = $normalizedDestinationPath + '.previous-' + $Context.SessionId
    if (Test-Path -LiteralPath $previousPath) {
        Reset-ManagedPath -Context $Context -Path $previousPath -AllowedRoots @($Context.OutputRoot)
    }

    try {
        if (Test-Path -LiteralPath $normalizedDestinationPath -PathType Container) {
            Move-Item -LiteralPath $normalizedDestinationPath -Destination $previousPath -Force -ErrorAction Stop
        }

        Move-Item -LiteralPath $normalizedStagingPath -Destination $normalizedDestinationPath -Force -ErrorAction Stop

        if (Test-Path -LiteralPath $previousPath) {
            Reset-ManagedPath -Context $Context -Path $previousPath -AllowedRoots @($Context.OutputRoot)
        }
    }
    catch {
        if (-not (Test-Path -LiteralPath $normalizedDestinationPath) -and (Test-Path -LiteralPath $previousPath)) {
            Move-Item -LiteralPath $previousPath -Destination $normalizedDestinationPath -Force -ErrorAction SilentlyContinue
        }
        throw
    }
}

function Publish-SessionReleaseDirectory {
    param([Parameter(Mandatory = $true)][hashtable]$Context)

    $stagingPath = Get-NormalizedPath -Path $Context.SessionReleaseRoot
    $destinationPath = Get-NormalizedPath -Path $Context.ReleasePublishRoot
    if (-not (Test-Path -LiteralPath $stagingPath -PathType Container)) {
        throw "RELEASE_STAGING_MISSING: $stagingPath"
    }
    if (Test-Path -LiteralPath $destinationPath) {
        throw "RELEASE_OUTPUT_ALREADY_EXISTS: $destinationPath"
    }
    Assert-OutputPathNotInUse -Path $destinationPath
    Move-Item -LiteralPath $stagingPath -Destination $destinationPath -ErrorAction Stop
    $Context.ReleasePublished = $true
    $Context.ReleasePublishRoot = $destinationPath
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
        '--no-compile',
        '--no-verify-hashes',
        '--link-mode', 'copy',
        '--no-python-downloads',
        '--cache-dir', $uvCacheRoot,
        '-r', $RequirementsPath
    )
    if ($Context.Offline) {
        $arguments += '--offline'
    }

    Invoke-ExternalCommand -Context $Context -FilePath 'uv' -WorkingDirectory $Context.RepoRoot -ArgumentList $arguments -Environment @{
        PYTHONDONTWRITEBYTECODE = '1'
        PYTHONUTF8 = '1'
        PYTHONIOENCODING = 'utf-8'
    }
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
    'Assert-OutputPathNotInUse',
    'Copy-FileWithParent',
    'Ensure-CommandAvailable',
    'Ensure-Directory',
    'Ensure-ExpandedRuntimeCache',
    'Ensure-RuntimeArchiveCached',
    'Ensure-Sha256Match',
    'Expand-TarGzArchive',
    'Format-OutputConsumersSummary',
    'Get-NormalizedPath',
    'Get-OutputPathConsumers',
    'Get-RelativePathCompat',
    'Get-RuntimeRoleManifest',
    'Install-LockedPythonDependencies',
    'Invoke-BuildStage',
    'Invoke-ExternalCommand',
    'Invoke-Robocopy',
    'New-BuildContext',
    'Publish-StagedDirectory',
    'Publish-SessionReleaseDirectory',
    'Publish-StagedFile',
    'Read-JsonFile',
    'Remove-WorkDirectoryIfNeeded',
    'Reset-ManagedPath',
    'Resolve-BuildPath',
    'Test-PathUnderRoot',
    'Write-BuildMessage'
)
