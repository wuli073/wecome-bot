@echo off
chcp 65001 >nul
if errorlevel 1 goto :failed
setlocal EnableExtensions DisableDelayedExpansion

set "LB_SOURCE_DIR=%~dp0"
set "LB_INSTALL_DIR=%~1"
if defined LB_INSTALL_DIR goto :install_dir_set
set "LB_INSTALL_DIR=%USERPROFILE%\wecome-bot"
:install_dir_set
if "%~2"=="" goto :arguments_ok
echo Usage: %~nx0 [installation-directory]
endlocal
exit /b 1

:arguments_ok
where powershell.exe >nul 2>&1
if errorlevel 1 goto :powershell_missing

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $repoUrl='https://github.com/wuli073/wecome-bot.git'; $target=$env:LB_INSTALL_DIR; $sourceDir=$env:LB_SOURCE_DIR; if ([string]::IsNullOrWhiteSpace($target)) { throw 'Installation directory is empty.' }; if ($target.IndexOfAny([char[]]'*?') -ge 0) { throw 'Installation directory must not contain * or ?.' }; $target=[IO.Path]::GetFullPath($target); $sourceDir=[IO.Path]::GetFullPath($sourceDir); $git=Get-Command git.exe -ErrorAction Stop; function Invoke-Git([string[]]$Arguments, [string]$WorkingDirectory) { if ($WorkingDirectory) { & $git.Source -C $WorkingDirectory @Arguments } else { & $git.Source @Arguments }; if ($LASTEXITCODE -ne 0) { throw ('git ' + ($Arguments -join ' ') + ' failed.') } }; function Set-DistributionExclusions([string]$RepoRoot) { $exclude=Join-Path $RepoRoot '.git\info\exclude'; if (-not (Test-Path -LiteralPath $exclude -PathType Leaf)) { throw ('Missing Git exclude file: ' + $exclude) }; $entries=@('/01-check-environment.bat','/02-install-wecome-bot.bat','/03-start-wecome-bot.bat'); $existing=[IO.File]::ReadAllLines($exclude); foreach ($entry in $entries) { if ($existing -notcontains $entry) { Add-Content -LiteralPath $exclude -Value $entry -Encoding utf8; $existing += $entry } } }; function Assert-CleanWorkingTree([string]$RepoRoot) { $changes=& $git.Source -C $RepoRoot status --porcelain --untracked-files=all; if ($LASTEXITCODE -ne 0) { throw 'git status --porcelain failed.' }; if (@($changes).Count -ne 0) { throw 'Refusing to update because the working tree contains tracked or untracked files.' } }; if (Test-Path -LiteralPath $target) { if (-not (Test-Path -LiteralPath $target -PathType Container)) { throw ('Installation path is not a directory: ' + $target) }; Invoke-Git -Arguments @('rev-parse','--is-inside-work-tree') -WorkingDirectory $target; $remote=(& $git.Source -C $target remote get-url origin).Trim(); if ($LASTEXITCODE -ne 0) { throw 'git remote get-url origin failed.' }; if ($remote.TrimEnd('/') -ne $repoUrl.TrimEnd('/')) { throw ('Existing repository origin does not match ' + $repoUrl + '.') }; $branch=(& $git.Source -C $target symbolic-ref --quiet --short HEAD).Trim(); if ($LASTEXITCODE -ne 0 -or $branch -ne 'main') { throw 'Existing repository must be on branch main.' }; Set-DistributionExclusions $target; Assert-CleanWorkingTree $target; Invoke-Git -Arguments @('fetch','--prune','origin','+refs/heads/main:refs/remotes/origin/main') -WorkingDirectory $target; Invoke-Git -Arguments @('merge','--ff-only','origin/main') -WorkingDirectory $target } else { $parent=Split-Path -Parent $target; if (-not (Test-Path -LiteralPath $parent -PathType Container)) { throw ('Installation parent directory does not exist: ' + $parent) }; Invoke-Git -Arguments @('clone','--branch','main','--single-branch',$repoUrl,$target) -WorkingDirectory $null; Set-DistributionExclusions $target }; $setupScript=Join-Path $target 'scripts\setup-source.ps1'; if (-not (Test-Path -LiteralPath $setupScript -PathType Leaf)) { throw ('Missing setup script: ' + $setupScript) }; $setupLog=Join-Path $target 'setup-source.log'; if (Test-Path -LiteralPath $setupLog -PathType Leaf) { Remove-Item -LiteralPath $setupLog -Force }; Write-Output 'Preparing Python, Web, and Desktop Runtime dependencies...'; try { & $setupScript *>&1 | Tee-Object -FilePath $setupLog -Append; $setupExit=$LASTEXITCODE } catch { $_ | Out-String | Tee-Object -FilePath $setupLog -Append | Write-Output; throw }; if ($setupExit -ne 0) { throw 'Dependency installation failed. Review the error above or setup-source.log.' }; foreach ($name in @('01-check-environment.bat','02-install-wecome-bot.bat','03-start-wecome-bot.bat')) { $source=Join-Path $sourceDir $name; $destination=Join-Path $target $name; if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw ('Missing distribution script: ' + $source) }; if ([IO.Path]::GetFullPath($source) -ne [IO.Path]::GetFullPath($destination)) { Copy-Item -LiteralPath $source -Destination $destination -Force } }; Write-Output ('Installed or updated: ' + $target); Write-Output 'Run 03-start-wecome-bot.bat from the installed project directory.'"
if errorlevel 1 goto :failed

endlocal
exit /b 0

:powershell_missing
echo PowerShell was not found on PATH.
endlocal
exit /b 1

:failed
echo Installation failed.
echo Review the error above or setup-source.log.
pause
endlocal
exit /b 1
