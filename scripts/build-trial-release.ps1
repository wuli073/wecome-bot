#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [string]$OutputRoot = '.\build\release',

    [string]$VcRedistPath = '',

    [switch]$SkipTests,

    [switch]$Offline,

    [switch]$KeepWorkDirectory,

    [switch]$PortableOnly,

    [string]$AuditWechatDecryptSource = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Import-Module (Join-Path $PSScriptRoot '..\packaging\build\BuildContext.psm1') -Force

function Resolve-InnoCompilerPath {
    param([hashtable]$Context)

    $candidates = @()
    if ($env:INNO_SETUP_COMPILER) {
        $candidates += $env:INNO_SETUP_COMPILER
    }

    $candidates += @(
        'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
        'C:\Program Files\Inno Setup 6\ISCC.exe'
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return $candidate
        }
    }

    throw 'Inno Setup compiler was not found. Set INNO_SETUP_COMPILER or install Inno Setup 6.'
}

function Get-AvailableSubstDriveRoot {
    $usedRoots = New-Object System.Collections.Generic.HashSet[string] ([System.StringComparer]::OrdinalIgnoreCase)

    foreach ($drive in @(Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue)) {
        if ($drive.Name) {
            [void]$usedRoots.Add(($drive.Name.TrimEnd(':') + ':'))
        }
    }

    foreach ($mapping in @(& subst 2>$null)) {
        if ($mapping -match '^([A-Z]:)\\: => ') {
            [void]$usedRoots.Add($matches[1])
        }
    }

    foreach ($code in 90..80) {
        $driveRoot = '{0}:' -f ([char]$code)
        if (-not $usedRoots.Contains($driveRoot)) {
            return $driveRoot
        }
    }

    throw 'No available drive letter was found for temporary installer path aliasing.'
}

function New-SubstDriveAlias {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetPath
    )

    $normalizedTargetPath = Get-NormalizedPath -Path $TargetPath
    $driveRoot = Get-AvailableSubstDriveRoot
    $null = & subst $driveRoot $normalizedTargetPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create subst alias $driveRoot for $normalizedTargetPath"
    }

    $aliasPath = $driveRoot + '\'
    if (-not (Test-Path -LiteralPath $aliasPath -PathType Container)) {
        & subst $driveRoot /d | Out-Null
        throw "subst alias did not become available: $driveRoot -> $normalizedTargetPath"
    }

    return [pscustomobject]@{
        DriveRoot = $driveRoot
        TargetPath = $normalizedTargetPath
        AliasPath = $aliasPath
    }
}

function Remove-SubstDriveAlias {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DriveRoot
    )

    $null = & subst $DriveRoot /d
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to remove subst alias: $DriveRoot"
    }
}

function Invoke-GitCapture {
    param([hashtable]$Context)

    $gitCapturePath = Join-Path $Context.WorkDirectory 'git-state.txt'
    $lines = @()
    $lines += 'branch:'
    $lines += (git -C $Context.RepoRoot branch --show-current)
    $lines += ''
    $lines += 'head:'
    $lines += (git -C $Context.RepoRoot rev-parse HEAD)
    $lines += ''
    $lines += 'status:'
    $lines += (git -C $Context.RepoRoot status --short)
    $lines += ''
    $lines += 'log:'
    $lines += (git -C $Context.RepoRoot log -5 --oneline)
    Set-Content -LiteralPath $gitCapturePath -Value $lines
}

function Invoke-EnvironmentCheck {
    param([hashtable]$Context)

    Ensure-CommandAvailable -CommandName git | Out-Null
    Ensure-CommandAvailable -CommandName npm | Out-Null
    Ensure-CommandAvailable -CommandName dotnet | Out-Null
    Ensure-CommandAvailable -CommandName tar | Out-Null
    Ensure-CommandAvailable -CommandName uv | Out-Null
    if (-not $Context.PortableOnly) {
        $Context.InnoCompilerPath = Resolve-InnoCompilerPath -Context $Context
    }

    if ($Context.VcRedistPath) {
        $resolvedVcRedistPath = Resolve-BuildPath -BasePath $Context.RepoRoot -Path $Context.VcRedistPath
        if (-not (Test-Path -LiteralPath $resolvedVcRedistPath -PathType Leaf)) {
            throw "VcRedistPath does not exist: $resolvedVcRedistPath"
        }

        $Context.VcRedistPath = $resolvedVcRedistPath
    }

    if ($Context.AuditWechatDecryptSource) {
        $resolvedAuditPath = Resolve-BuildPath -BasePath $Context.RepoRoot -Path $Context.AuditWechatDecryptSource
        if (-not (Test-Path -LiteralPath $resolvedAuditPath -PathType Container)) {
            throw "AuditWechatDecryptSource does not exist: $resolvedAuditPath"
        }

        $Context.AuditWechatDecryptSource = $resolvedAuditPath
    }

    Write-BuildMessage -Context $Context -Message ("Repo root: {0}" -f $Context.RepoRoot)
    Write-BuildMessage -Context $Context -Message ("Output root: {0}" -f $Context.OutputRoot)
    Write-BuildMessage -Context $Context -Message ("Portable root: {0}" -f $Context.PortableRoot)
    Write-BuildMessage -Context $Context -Message ("Offline mode: {0}" -f $Context.Offline)
    Write-BuildMessage -Context $Context -Message ("Skip tests: {0}" -f $Context.SkipTests)
}

function Invoke-FrontendBuild {
    param([hashtable]$Context)

    $webRoot = Join-Path $Context.RepoRoot 'web'
    Invoke-ExternalCommand -Context $Context -FilePath 'npm' -WorkingDirectory $webRoot -ArgumentList @('run', 'build')
}

function New-RuntimeAssembly {
    param(
        [hashtable]$Context,
        [ValidateSet('server', 'connector')]
        [string]$Role,
        [string]$RequirementsPath
    )

    $expandedRuntimeRoot = Ensure-ExpandedRuntimeCache -Context $Context -Role $Role
    $roleWorkRoot = Join-Path $Context.WorkDirectory ("assembled\" + $Role)
    $runtimeDestination = Join-Path $roleWorkRoot 'runtime'
    Reset-ManagedPath -Context $Context -Path $roleWorkRoot -AllowedRoots @($Context.WorkDirectory)
    Ensure-Directory -Path $runtimeDestination
    Invoke-Robocopy -Source $expandedRuntimeRoot -Destination $runtimeDestination
    Install-LockedPythonDependencies -Context $Context -Role $Role -RuntimeRoot $runtimeDestination -RequirementsPath $RequirementsPath
    $runtimeScriptsRoot = Join-Path $runtimeDestination 'python\Scripts'
    Reset-ManagedPath -Context $Context -Path $runtimeScriptsRoot -AllowedRoots @($roleWorkRoot)
    if ($Role -eq 'server') {
        $litellmBenchmarkRoot = Join-Path $runtimeDestination 'python\Lib\site-packages\litellm\proxy\guardrails\guardrail_hooks\litellm_content_filter\guardrail_benchmarks'
        Reset-ManagedPath -Context $Context -Path $litellmBenchmarkRoot -AllowedRoots @($roleWorkRoot)
    }

    return $roleWorkRoot
}

function Invoke-ServerRuntimeAssembly {
    param([hashtable]$Context)

    $requirementsPath = Join-Path $Context.RepoRoot 'packaging\server\requirements.lock.txt'
    $serverWorkRoot = New-RuntimeAssembly -Context $Context -Role server -RequirementsPath $requirementsPath
    $serverAppRoot = Join-Path $serverWorkRoot 'app'
    Ensure-Directory -Path $serverAppRoot

    foreach ($copySpec in $Context.PortableLayout.serverAppCopies) {
        $sourcePath = Resolve-BuildPath -BasePath $Context.RepoRoot -Path $copySpec.source
        $targetPath = Join-Path $serverAppRoot $copySpec.target
        if ($copySpec.type -eq 'directory') {
            Invoke-Robocopy -Source $sourcePath -Destination $targetPath
        }
        else {
            Copy-FileWithParent -Source $sourcePath -Destination $targetPath
        }
    }

    $sitePackagesPath = Join-Path $serverWorkRoot 'runtime\python\Lib\site-packages'
    Ensure-Directory -Path $sitePackagesPath
    $pthPath = Join-Path $sitePackagesPath 'chatbot-app.pth'
    $appSrcPath = Join-Path $serverAppRoot 'src'
    $appRootRelative = Get-RelativePathCompat -BasePath $sitePackagesPath -TargetPath $serverAppRoot
    $appSrcRelative = Get-RelativePathCompat -BasePath $sitePackagesPath -TargetPath $appSrcPath
    Set-Content -LiteralPath $pthPath -Value @(
        $appRootRelative,
        $appSrcRelative
    )

    $Context.ServerAssemblyRoot = $serverWorkRoot
}

function Invoke-ConnectorRuntimeAssembly {
    param([hashtable]$Context)

    $requirementsPath = Join-Path $Context.RepoRoot 'vendor\wechat_decrypt\requirements.lock.txt'
    $connectorWorkRoot = New-RuntimeAssembly -Context $Context -Role connector -RequirementsPath $requirementsPath
    $Context.ConnectorAssemblyRoot = $connectorWorkRoot
}

function Invoke-VendorTreeAssembly {
    param([hashtable]$Context)

    $vendorRoot = Join-Path $Context.RepoRoot 'vendor\wechat_decrypt'
    $manifest = Read-JsonFile -Path (Join-Path $vendorRoot 'source-manifest.json')
    $approvedFiles = @()
    $approvedFiles += $manifest.releaseScope.includedRuntimeEntrypoints
    $approvedFiles += $manifest.releaseScope.includedSupportFiles

    $destinationRoot = Join-Path $Context.ConnectorAssemblyRoot 'app\wechat-decrypt'
    Reset-ManagedPath -Context $Context -Path $destinationRoot -AllowedRoots @($Context.WorkDirectory)
    Ensure-Directory -Path $destinationRoot

    foreach ($relativePath in $approvedFiles | Sort-Object -Unique) {
        $sourcePath = Join-Path $vendorRoot $relativePath
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
            throw "Approved vendor file is missing: $sourcePath"
        }

        $targetPath = Join-Path $destinationRoot $relativePath
        Copy-FileWithParent -Source $sourcePath -Destination $targetPath
    }

    if (-not $Context.SkipTests) {
        Invoke-ExternalCommand -Context $Context -FilePath 'uv' -WorkingDirectory $Context.RepoRoot -ArgumentList @(
            'run', 'python', '-m', 'pytest', 'tests\vendor_wechat_decrypt\test_runtime_layout.py', '-q'
        )
    }

    if ($Context.AuditWechatDecryptSource) {
        $auditReport = @()
        foreach ($relativePath in $approvedFiles | Sort-Object -Unique) {
            $baselinePath = Join-Path $vendorRoot $relativePath
            $auditPath = Join-Path $Context.AuditWechatDecryptSource $relativePath
            $entry = [ordered]@{
                path = $relativePath
                approvedExists = Test-Path -LiteralPath $baselinePath
                auditExists = Test-Path -LiteralPath $auditPath
                sameSha256 = $false
            }

            if ($entry.approvedExists -and $entry.auditExists) {
                $entry.sameSha256 = ((Get-FileHash -LiteralPath $baselinePath -Algorithm SHA256).Hash -eq (Get-FileHash -LiteralPath $auditPath -Algorithm SHA256).Hash)
            }

            $auditReport += [pscustomobject]$entry
        }

        $auditPath = Join-Path $Context.WorkDirectory 'wechat-decrypt-audit.json'
        $auditReport | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $auditPath
        Write-BuildMessage -Context $Context -Message ("AuditWechatDecryptSource report written to: {0}" -f $auditPath)
    }
}

function Invoke-RpaRuntimeCopy {
    param([hashtable]$Context)

    $rpaRoot = Join-Path $Context.RepoRoot 'apps\desktop-rpa-runtime'
    Invoke-ExternalCommand -Context $Context -FilePath 'npm' -WorkingDirectory $rpaRoot -ArgumentList @('run', 'typecheck')
    Invoke-ExternalCommand -Context $Context -FilePath 'npm' -WorkingDirectory $rpaRoot -ArgumentList @('run', 'lint')
    if (-not $Context.SkipTests) {
        Invoke-ExternalCommand -Context $Context -FilePath 'npm' -WorkingDirectory $rpaRoot -ArgumentList @('test')
    }
    Invoke-ExternalCommand -Context $Context -FilePath 'npm' -WorkingDirectory $rpaRoot -ArgumentList @('run', 'rebuild:native')
    Invoke-ExternalCommand -Context $Context -FilePath 'npm' -WorkingDirectory $rpaRoot -ArgumentList @('run', 'package:win:dir')

    $rpaSource = Join-Path $rpaRoot 'dist-phase2-official\win-dir\win-unpacked'
    if (-not (Test-Path -LiteralPath (Join-Path $rpaSource 'LangBot Desktop RPA Runtime.exe') -PathType Leaf)) {
        throw "Deterministic RPA runtime was not produced at: $rpaSource"
    }

    $rpaDestination = Join-Path $Context.WorkDirectory 'assembled\runtime\desktop-rpa'
    Reset-ManagedPath -Context $Context -Path $rpaDestination -AllowedRoots @($Context.WorkDirectory)
    Ensure-Directory -Path $rpaDestination
    Invoke-Robocopy -Source $rpaSource -Destination $rpaDestination
    Get-ChildItem -LiteralPath $rpaDestination -Recurse -Filter '*.nativecodeanalysis.xml' -File | ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Force
    }
    $Context.RpaAssemblyRoot = $rpaDestination
}

function Invoke-LauncherPublish {
    param([hashtable]$Context)

    $solutionPath = Join-Path $Context.RepoRoot 'packaging\launcher\ChatbotLauncher.sln'
    $projectPath = Join-Path $Context.RepoRoot 'packaging\launcher\ChatbotLauncher\ChatbotLauncher.csproj'
    $launcherRoot = Join-Path $Context.RepoRoot 'packaging\launcher'
    $publishRoot = Join-Path $Context.WorkDirectory 'launcher-publish'
    Reset-ManagedPath -Context $Context -Path $publishRoot -AllowedRoots @($Context.WorkDirectory)

    $restoreArgs = @('restore', $solutionPath)
    if ($Context.Offline) {
        $restoreArgs += '--ignore-failed-sources'
    }

    Invoke-ExternalCommand -Context $Context -FilePath 'dotnet' -WorkingDirectory $launcherRoot -ArgumentList $restoreArgs
    if (-not $Context.SkipTests) {
        Invoke-ExternalCommand -Context $Context -FilePath 'dotnet' -WorkingDirectory $launcherRoot -ArgumentList @(
            'test', $solutionPath, '-c', 'Release', '--no-restore'
        )
    }

    Invoke-ExternalCommand -Context $Context -FilePath 'dotnet' -WorkingDirectory $launcherRoot -ArgumentList @(
        'publish', $projectPath,
        '-c', 'Release',
        '-r', 'win-x64',
        '--self-contained', 'true',
        '--no-restore',
        '-o', $publishRoot
    )

    if (-not (Test-Path -LiteralPath (Join-Path $publishRoot 'ChatbotLauncher.exe') -PathType Leaf)) {
        throw "Launcher publish output is missing ChatbotLauncher.exe"
    }

    $Context.LauncherPublishRoot = $publishRoot
}

function Invoke-PortableDirectoryAssembly {
    param([hashtable]$Context)

    Reset-ManagedPath -Context $Context -Path $Context.PortableRoot -AllowedRoots @($Context.WorkDirectory)
    Ensure-Directory -Path $Context.PortableRoot

    Invoke-Robocopy -Source $Context.LauncherPublishRoot -Destination $Context.PortableRoot

    $releaseLauncherJson = Join-Path $Context.PortableRoot 'launcher.json'
    Copy-FileWithParent -Source (Join-Path $Context.RepoRoot 'packaging\launcher\ChatbotLauncher\launcher.json') -Destination $releaseLauncherJson

    Invoke-Robocopy -Source (Join-Path $Context.ServerAssemblyRoot 'runtime') -Destination (Join-Path $Context.PortableRoot 'server\runtime')
    Invoke-Robocopy -Source (Join-Path $Context.ServerAssemblyRoot 'app') -Destination (Join-Path $Context.PortableRoot 'server\app')
    Invoke-Robocopy -Source (Join-Path $Context.ConnectorAssemblyRoot 'runtime') -Destination (Join-Path $Context.PortableRoot 'connectors\runtime')
    Invoke-Robocopy -Source (Join-Path $Context.ConnectorAssemblyRoot 'app\wechat-decrypt') -Destination (Join-Path $Context.PortableRoot 'connectors\app\wechat-decrypt')
    Invoke-Robocopy -Source $Context.RpaAssemblyRoot -Destination (Join-Path $Context.PortableRoot 'runtime\desktop-rpa')

    $webDistSource = Join-Path $Context.RepoRoot 'web\dist'
    Invoke-Robocopy -Source $webDistSource -Destination (Join-Path $Context.PortableRoot 'resources\web\dist')

    foreach ($resourceCopy in $Context.PortableLayout.resourceCopies) {
        $targetPath = Join-Path $Context.PortableRoot $resourceCopy.target
        $createIfMissing = ($resourceCopy.PSObject.Properties.Name -contains 'createIfMissing') -and [bool]$resourceCopy.createIfMissing
        if ($createIfMissing) {
            Ensure-Directory -Path $targetPath
            continue
        }

        $sourcePath = Resolve-BuildPath -BasePath $Context.RepoRoot -Path $resourceCopy.source
        if (-not (Test-Path -LiteralPath $sourcePath)) {
            if ($resourceCopy.required) {
                throw "Required resource source is missing: $sourcePath"
            }

            Ensure-Directory -Path $targetPath
            continue
        }

        Invoke-Robocopy -Source $sourcePath -Destination $targetPath
    }

    $prerequisitesRoot = Join-Path $Context.PortableRoot 'prerequisites'
    Ensure-Directory -Path $prerequisitesRoot
    if ($Context.VcRedistPath) {
        Copy-FileWithParent -Source $Context.VcRedistPath -Destination (Join-Path $prerequisitesRoot 'vc_redist.x64.exe')
    }

    foreach ($licenseCopy in $Context.PortableLayout.licenseCopies) {
        $sourcePath = Resolve-BuildPath -BasePath $Context.RepoRoot -Path $licenseCopy.source
        Copy-FileWithParent -Source $sourcePath -Destination (Join-Path $Context.PortableRoot $licenseCopy.target)
    }

    $serverPythonLicense = Join-Path $Context.ServerAssemblyRoot 'runtime\python\LICENSE.txt'
    $connectorPythonLicense = Join-Path $Context.ConnectorAssemblyRoot 'runtime\python\LICENSE.txt'
    if (Test-Path -LiteralPath $serverPythonLicense -PathType Leaf) {
        Copy-FileWithParent -Source $serverPythonLicense -Destination (Join-Path $Context.PortableRoot 'licenses\server-python-LICENSE.txt')
    }
    if (Test-Path -LiteralPath $connectorPythonLicense -PathType Leaf) {
        Copy-FileWithParent -Source $connectorPythonLicense -Destination (Join-Path $Context.PortableRoot 'licenses\connector-python-LICENSE.txt')
    }
}

function Invoke-SensitiveScan {
    param([hashtable]$Context)

    $scanReportPath = Join-Path $Context.PortableRoot 'build-sensitive-scan.json'
    $allowlistPath = Join-Path $Context.RepoRoot 'packaging\build\allowlist.json'
    $arguments = @(
        'run', '--no-sync', 'python',
        'packaging/build/sensitive-scan.py',
        '--bundle-root', $Context.PortableRoot,
        '--allowlist', $allowlistPath,
        '--blocked-literal', $Context.RepoRoot,
        '--blocked-literal', $env:USERPROFILE,
        '--blocked-literal', (Join-Path $env:USERPROFILE 'Desktop\wechat-decrypt.backup'),
        '--blocked-literal', 'C:\Users\runneradmin',
        '--blocked-literal', 'file:///C:/actions-runner/',
        '--blocked-literal', 'C:/actions-runner/',
        '--output', $scanReportPath
    )
    Invoke-ExternalCommand -Context $Context -FilePath 'uv' -WorkingDirectory $Context.RepoRoot -ArgumentList $arguments

    $Context.SensitiveScanPath = $scanReportPath
    $Context.SensitiveScanReport = Read-JsonFile -Path $scanReportPath
}

function Invoke-PortableSanitization {
    param([hashtable]$Context)

    $reportPath = Join-Path $Context.WorkDirectory 'sanitize-bundle-report.json'
    $arguments = @(
        'run', '--no-sync', 'python',
        'packaging/build/sanitize-bundle.py',
        '--bundle-root', $Context.PortableRoot,
        '--repo-root', $Context.RepoRoot,
        '--user-profile', $env:USERPROFILE,
        '--blocked-literal', 'C:\Users\runneradmin',
        '--blocked-literal', 'file:///C:/actions-runner/',
        '--blocked-literal', 'C:/actions-runner/',
        '--output', $reportPath
    )
    Invoke-ExternalCommand -Context $Context -FilePath 'uv' -WorkingDirectory $Context.RepoRoot -ArgumentList $arguments
    $report = Read-JsonFile -Path $reportPath
    if (@($report.remainingBytecodeFiles).Count -gt 0 -or @($report.remainingPycacheDirectories).Count -gt 0) {
        throw "Bundle sanitization left Python bytecode artifacts behind."
    }
    $Context.SanitizeReportPath = $reportPath
}

function Invoke-ManifestGeneration {
    param([hashtable]$Context)

    $manifestPath = Join-Path $Context.PortableRoot 'manifest.json'
    $sha256SumsPath = Join-Path $Context.PortableRoot 'SHA256SUMS.txt'

    Invoke-ExternalCommand -Context $Context -FilePath 'uv' -WorkingDirectory $Context.RepoRoot -ArgumentList @(
        'run', '--no-sync', 'python',
        'packaging/build/manifest.py',
        '--bundle-root', $Context.PortableRoot,
        '--version', $Context.Version,
        '--manifest-path', $manifestPath,
        '--sha256sums-path', $sha256SumsPath
    )

    $Context.ManifestPath = $manifestPath
    $Context.Sha256SumsPath = $sha256SumsPath
}

function Invoke-BuildReportGeneration {
    param([hashtable]$Context)

    $reportPath = Join-Path $Context.PortableRoot 'build-report.json'
    $stageItems = @()
    foreach ($result in $Context.StageResults) {
        $stageItems += [ordered]@{
            name = $result.Name
            startedAt = $result.StartedAt.ToString('o')
            completedAt = $result.CompletedAt.ToString('o')
            duration = $result.Duration.ToString()
            succeeded = [bool]$result.Succeeded
        }
    }

    $report = [ordered]@{
        schemaVersion = 1
        version = $Context.Version
        generatedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
        portableDirectory = Split-Path -Leaf $Context.PortableRoot
        portableZip = (Split-Path -Leaf (Join-Path $Context.OutputRoot ((Split-Path -Leaf $Context.PortableRoot) + '.zip')))
        git = [ordered]@{
            branch = (git -C $Context.RepoRoot branch --show-current)
            head = (git -C $Context.RepoRoot rev-parse HEAD)
        }
        sensitiveScan = [ordered]@{
            path = 'build-sensitive-scan.json'
            findingCount = $Context.SensitiveScanReport.summary.findingCount
            blocked = [bool]$Context.SensitiveScanReport.summary.blocked
        }
        manifest = [ordered]@{
            path = 'manifest.json'
        }
        sha256Sums = [ordered]@{
            path = 'SHA256SUMS.txt'
        }
        stages = $stageItems
    }

    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    $Context.BuildReportPath = $reportPath
}

function Invoke-PortableZipAssembly {
    param([hashtable]$Context)

    $zipPath = $Context.PortableZipStagingPath
    $zipSha256Path = $Context.PortableZipSha256StagingPath
    Reset-ManagedPath -Context $Context -Path $zipPath -AllowedRoots @($Context.WorkDirectory)
    Reset-ManagedPath -Context $Context -Path $zipSha256Path -AllowedRoots @($Context.WorkDirectory)
    Ensure-Directory -Path ([System.IO.Path]::GetDirectoryName($zipPath))
    $portableName = Split-Path -Leaf $Context.PortableRoot
    $portableParent = Split-Path -Parent $Context.PortableRoot
    Invoke-ExternalCommand -Context $Context -FilePath 'tar.exe' -WorkingDirectory $portableParent -ArgumentList @(
        '-a', '-cf', $zipPath, '-C', $portableParent, $portableName
    )
    $zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath $zipSha256Path -Value ("{0}  {1}" -f $zipHash, (Split-Path -Leaf $zipPath)) -Encoding ASCII
    $Context.PortableZipPath = $zipPath
    $Context.PortableZipSha256Path = $zipSha256Path
}

function Invoke-InstallerAssembly {
    param([hashtable]$Context)

    $issPath = Join-Path $Context.RepoRoot 'packaging\installer\ChatbotTrial.iss'
    $installerOutputRoot = $Context.InstallerStageRoot
    Reset-ManagedPath -Context $Context -Path $installerOutputRoot -AllowedRoots @($Context.WorkDirectory)
    Ensure-Directory -Path $installerOutputRoot
    $setupPath = Join-Path $installerOutputRoot ("Chatbot-Setup-{0}-x64.exe" -f $Context.Version)
    $portableRootParent = Split-Path -Path $Context.PortableRoot -Parent
    $installerRootParent = Split-Path -Path $installerOutputRoot -Parent
    $portableAlias = $null
    $installerAlias = $null

    try {
        $portableAlias = New-SubstDriveAlias -TargetPath $portableRootParent
        $aliasedPortableRoot = Join-Path $portableAlias.AliasPath (Split-Path -Path $Context.PortableRoot -Leaf)

        if ($installerRootParent.Equals($portableRootParent, [System.StringComparison]::OrdinalIgnoreCase)) {
            $installerAlias = $portableAlias
        }
        else {
            $installerAlias = New-SubstDriveAlias -TargetPath $installerRootParent
        }

        $aliasedInstallerRoot = Join-Path $installerAlias.AliasPath (Split-Path -Path $installerOutputRoot -Leaf)

        Write-BuildMessage -Context $Context -Message ("Installer source subst alias: {0} -> {1}" -f $portableAlias.DriveRoot, $portableAlias.TargetPath)
        Write-BuildMessage -Context $Context -Message ("Installer output subst alias: {0} -> {1}" -f $installerAlias.DriveRoot, $installerAlias.TargetPath)
        Write-BuildMessage -Context $Context -Message ("Installer source alias: {0}" -f $aliasedPortableRoot)
        Write-BuildMessage -Context $Context -Message ("Installer output alias: {0}" -f $aliasedInstallerRoot)

        Invoke-ExternalCommand -Context $Context -FilePath $Context.InnoCompilerPath -WorkingDirectory $Context.RepoRoot -ArgumentList @(
            '/Qp',
            "/DAppVersion=$($Context.Version)",
            "/DSourcePortableRoot=$aliasedPortableRoot",
            "/DOutputRoot=$aliasedInstallerRoot",
            $issPath
        )
    }
    finally {
        if ($installerAlias -and ($installerAlias.DriveRoot -ne $portableAlias.DriveRoot)) {
            Remove-SubstDriveAlias -DriveRoot $installerAlias.DriveRoot
        }

        if ($portableAlias) {
            Remove-SubstDriveAlias -DriveRoot $portableAlias.DriveRoot
        }
    }

    if (-not (Test-Path -LiteralPath $setupPath -PathType Leaf)) {
        throw "Installer output is missing: $setupPath"
    }

    $Context.SetupPath = $setupPath
}

function Invoke-PortableSanityCheck {
    param([hashtable]$Context)

    foreach ($relativePath in $Context.PortableLayout.portableRequiredPaths) {
        $path = Join-Path $Context.PortableRoot $relativePath
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Portable layout is missing required path: $relativePath"
        }
    }

    if ($Context.PortableOnly) {
        foreach ($relativePath in $Context.PortableLayout.portableForbiddenPaths) {
            $path = Join-Path $Context.PortableRoot $relativePath
            if (Test-Path -LiteralPath $path) {
                throw "PortableOnly mode must not generate: $relativePath"
            }
        }

        if ($Context.PortableZipPath) {
            throw "PortableOnly mode must not generate Portable ZIP: $($Context.PortableZipPath)"
        }

        if ($Context.SetupPath) {
            throw "PortableOnly mode must not generate installer package: $($Context.SetupPath)"
        }
    }
    else {
        foreach ($requiredGeneratedFile in @('manifest.json', 'build-sensitive-scan.json', 'build-report.json', 'SHA256SUMS.txt')) {
            if (-not (Test-Path -LiteralPath (Join-Path $Context.PortableRoot $requiredGeneratedFile) -PathType Leaf)) {
                throw "Full release build is missing generated artifact: $requiredGeneratedFile"
            }
        }

        $zipPath = $Context.PortableZipPath
        if (-not (Test-Path -LiteralPath $zipPath -PathType Leaf)) {
            throw "Full release build is missing Portable ZIP: $zipPath"
        }

        $zipSha256Path = $Context.PortableZipSha256Path
        if (-not (Test-Path -LiteralPath $zipSha256Path -PathType Leaf)) {
            throw "Full release build is missing Portable ZIP checksum: $zipSha256Path"
        }
    }
}

function Invoke-PortableArtifactPublish {
    param([hashtable]$Context)

    $publishTargets = @()
    if (-not $Context.PortablePublished) {
        $publishTargets += $Context.PortablePublishRoot
    }
    if ($Context.PortableZipPath -and ($Context.PortableZipPath -ne $Context.PortableZipPublishPath)) {
        $publishTargets += $Context.PortableZipPublishPath
    }
    if ($Context.PortableZipSha256Path -and ($Context.PortableZipSha256Path -ne $Context.PortableZipSha256PublishPath)) {
        $publishTargets += $Context.PortableZipSha256PublishPath
    }
    if ($Context.SetupPath -and ($Context.SetupPath -ne $Context.SetupPublishPath)) {
        $publishTargets += $Context.SetupPublishPath
    }

    foreach ($target in $publishTargets) {
        Assert-OutputPathNotInUse -Path $target
    }

    if ($Context.PortableZipPath -and ($Context.PortableZipPath -ne $Context.PortableZipPublishPath)) {
        Publish-StagedFile -Context $Context -StagingPath $Context.PortableZipPath -DestinationPath $Context.PortableZipPublishPath
        $Context.PortableZipPath = $Context.PortableZipPublishPath
    }

    if ($Context.PortableZipSha256Path -and ($Context.PortableZipSha256Path -ne $Context.PortableZipSha256PublishPath)) {
        Publish-StagedFile -Context $Context -StagingPath $Context.PortableZipSha256Path -DestinationPath $Context.PortableZipSha256PublishPath
        $Context.PortableZipSha256Path = $Context.PortableZipSha256PublishPath
    }

    if ($Context.SetupPath -and ($Context.SetupPath -ne $Context.SetupPublishPath)) {
        Publish-StagedFile -Context $Context -StagingPath $Context.SetupPath -DestinationPath $Context.SetupPublishPath
        $Context.SetupPath = $Context.SetupPublishPath
    }

    if (-not $Context.PortablePublished) {
        Publish-StagedDirectory -Context $Context -StagingPath $Context.PortableRoot -DestinationPath $Context.PortablePublishRoot
        $Context.PortableRoot = $Context.PortablePublishRoot
        $Context.PortablePublished = $true
    }
}

$repoRoot = Resolve-BuildPath -BasePath $PSScriptRoot -Path '..'
$context = New-BuildContext `
    -RepoRoot $repoRoot `
    -OutputRoot $OutputRoot `
    -Version $Version `
    -Offline ([bool]$Offline) `
    -SkipTests ([bool]$SkipTests) `
    -KeepWorkDirectory ([bool]$KeepWorkDirectory) `
    -PortableOnly ([bool]$PortableOnly) `
    -VcRedistPath $VcRedistPath `
    -AuditWechatDecryptSource $AuditWechatDecryptSource

try {
    Invoke-BuildStage -Context $context -Name 'environment check' -Action { Invoke-EnvironmentCheck -Context $context }
    Invoke-BuildStage -Context $context -Name 'git state capture' -Action { Invoke-GitCapture -Context $context }
    Invoke-BuildStage -Context $context -Name 'frontend build' -Action { Invoke-FrontendBuild -Context $context }
    Invoke-BuildStage -Context $context -Name 'server runtime assembly' -Action { Invoke-ServerRuntimeAssembly -Context $context }
    Invoke-BuildStage -Context $context -Name 'connector runtime assembly' -Action { Invoke-ConnectorRuntimeAssembly -Context $context }
    Invoke-BuildStage -Context $context -Name 'vendor tree assembly' -Action { Invoke-VendorTreeAssembly -Context $context }
    Invoke-BuildStage -Context $context -Name 'RPA runtime copy' -Action { Invoke-RpaRuntimeCopy -Context $context }
    Invoke-BuildStage -Context $context -Name 'launcher publish' -Action { Invoke-LauncherPublish -Context $context }
    Invoke-BuildStage -Context $context -Name 'portable directory assembly' -Action { Invoke-PortableDirectoryAssembly -Context $context }
    Invoke-BuildStage -Context $context -Name 'portable sanitization' -Action { Invoke-PortableSanitization -Context $context }
    if (-not $context.PortableOnly) {
        Invoke-BuildStage -Context $context -Name 'sensitive scan' -Action { Invoke-SensitiveScan -Context $context }
        Invoke-BuildStage -Context $context -Name 'build report generation' -Action { Invoke-BuildReportGeneration -Context $context }
    }
    Invoke-BuildStage -Context $context -Name 'manifest generation' -Action { Invoke-ManifestGeneration -Context $context }
    if (-not $context.PortableOnly) {
        Invoke-BuildStage -Context $context -Name 'portable zip assembly' -Action { Invoke-PortableZipAssembly -Context $context }
        Invoke-BuildStage -Context $context -Name 'minimal portable layout sanity check' -Action { Invoke-PortableSanityCheck -Context $context }
        Invoke-BuildStage -Context $context -Name 'portable artifact publish' -Action { Invoke-PortableArtifactPublish -Context $context }
        Invoke-BuildStage -Context $context -Name 'installer assembly' -Action { Invoke-InstallerAssembly -Context $context }
    }
    else {
        Invoke-BuildStage -Context $context -Name 'minimal portable layout sanity check' -Action { Invoke-PortableSanityCheck -Context $context }
    }

    if ($context.PortableOnly) {
        Write-BuildMessage -Context $context -Message 'PortableOnly requested: Task 15/16 outputs intentionally deferred.'
    }

    Invoke-BuildStage -Context $context -Name 'portable artifact publish' -Action { Invoke-PortableArtifactPublish -Context $context }
    Write-BuildMessage -Context $context -Message ("Portable release assembled at: {0}" -f $context.PortableRoot)
}
catch {
    Write-BuildMessage -Context $context -Message ("Build failed at stage: {0}" -f $context.FailedStage)
    Remove-WorkDirectoryIfNeeded -Context $context -PreserveOnFailure
    throw
}

Remove-WorkDirectoryIfNeeded -Context $context
