@echo off
chcp 65001 >nul
if errorlevel 1 goto :failed
setlocal EnableExtensions DisableDelayedExpansion

where powershell.exe >nul 2>&1
if errorlevel 1 goto :powershell_missing

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; function Get-Tool([string]$Name) { $command=Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue; if ($null -eq $command) { return $null }; $output=& $command.Source --version 2>&1; if ($LASTEXITCODE -ne 0) { return $null }; $version=([string]($output | Select-Object -First 1)).Trim(); if ([string]::IsNullOrWhiteSpace($version)) { return $null }; return [pscustomobject]@{ Source=$command.Source; Version=$version } }; if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 is required.' }; if ($PSVersionTable.PSVersion.Major -lt 5) { throw 'PowerShell 5.1 or later is required.' }; $git=Get-Tool 'git.exe'; $node=Get-Tool 'node.exe'; $npm=Get-Tool 'npm.cmd'; $uv=Get-Tool 'uv.exe'; $needs=New-Object System.Collections.Generic.List[object]; if ($null -eq $git) { $needs.Add([pscustomobject]@{ Name='Git'; Id='Git.Git' }) }; if ($null -eq $node -or $node.Version -notmatch '^v22\.') { $needs.Add([pscustomobject]@{ Name='Node.js 22'; Id='OpenJS.NodeJS.22' }) }; if ($null -eq $uv) { $needs.Add([pscustomobject]@{ Name='uv'; Id='astral-sh.uv' }) }; Write-Output 'Already satisfied:'; Write-Output '- Windows x64'; Write-Output ('- PowerShell ' + $PSVersionTable.PSVersion); if ($null -ne $git) { Write-Output ('- Git: ' + $git.Version) }; if ($null -ne $node -and $node.Version -match '^v22\.') { Write-Output ('- Node.js: ' + $node.Version) }; if ($null -ne $npm) { Write-Output ('- npm: ' + $npm.Version) }; if ($null -ne $uv) { Write-Output ('- uv: ' + $uv.Version) }; if ($needs.Count -eq 0 -and $null -eq $npm) { throw 'npm is missing although Node.js 22.x is available. The Node.js installation is incomplete.' }; if ($needs.Count -eq 0) { exit 0 }; $winget=Get-Command winget.exe -CommandType Application -ErrorAction SilentlyContinue; if ($null -eq $winget) { throw 'Windows Package Manager (winget.exe) is missing. Install or update App Installer from Microsoft Store, then run this script again.' }; Write-Output 'Needs installation:'; foreach ($item in $needs) { Write-Output ('- ' + $item.Name) }; $answer=Read-Host 'Continue with installation? [Y/N]'; if ($answer -notmatch '^[Yy]$') { throw 'Installation was cancelled by the user.' }; Write-Output 'The installers may trigger Windows UAC prompts.'; foreach ($item in $needs) { Write-Output ('Installing ' + $item.Name + '...'); & $winget.Source install --id $item.Id --exact --source winget --accept-package-agreements --accept-source-agreements; if ($LASTEXITCODE -ne 0) { throw ('winget install failed for ' + $item.Name + ' with exit code ' + $LASTEXITCODE + '.') } }; exit 10"
set "LB_INSTALL_RESULT=%ERRORLEVEL%"
if "%LB_INSTALL_RESULT%"=="10" goto :refresh_path
if "%LB_INSTALL_RESULT%"=="0" goto :final_check
goto :failed

:refresh_path
set "LB_PATH_FILE=%TEMP%\langbot-environment-path-%RANDOM%-%RANDOM%.txt"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $machine=[Environment]::GetEnvironmentVariable('Path', 'Machine'); $user=[Environment]::GetEnvironmentVariable('Path', 'User'); $path=@($machine,$user | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join ';'; if ([string]::IsNullOrWhiteSpace($path)) { throw 'The refreshed PATH is empty.' }; [IO.File]::WriteAllText($env:LB_PATH_FILE, $path, (New-Object Text.UTF8Encoding($false)))"
if errorlevel 1 goto :path_refresh_failed
if not exist "%LB_PATH_FILE%" goto :path_refresh_failed
set /p "PATH="<"%LB_PATH_FILE%"
del /q "%LB_PATH_FILE%" >nul 2>&1
if not defined PATH goto :path_refresh_failed
goto :final_check

:final_check
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; function Get-RequiredTool([string]$Name) { $command=Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue; if ($null -eq $command) { throw ($Name + ' was not found on PATH.') }; $output=& $command.Source --version 2>&1; if ($LASTEXITCODE -ne 0) { throw ($Name + ' --version failed.') }; $version=([string]($output | Select-Object -First 1)).Trim(); if ([string]::IsNullOrWhiteSpace($version)) { throw ($Name + ' --version returned no version.') }; return [pscustomobject]@{ Source=$command.Source; Version=$version } }; if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 is required.' }; if ($PSVersionTable.PSVersion.Major -lt 5) { throw 'PowerShell 5.1 or later is required.' }; $git=Get-RequiredTool 'git.exe'; $node=Get-RequiredTool 'node.exe'; if ($node.Version -notmatch '^v22\.') { throw ('Node.js 22.x is required; found ' + $node.Version + '. Check PATH, NVM, or shim priority.') }; $npm=Get-RequiredTool 'npm.cmd'; $uv=Get-RequiredTool 'uv.exe'; & $git.Source -c credential.helper= ls-remote https://github.com/wuli073/wecome-bot.git refs/heads/main | Out-Null; if ($LASTEXITCODE -ne 0) { throw 'GitHub repository access failed. Check network, proxy, TLS, or GitHub access, then try again.' }; Write-Output ('Git: ' + $git.Version); Write-Output ('Node.js: ' + $node.Version); Write-Output ('npm: ' + $npm.Version); Write-Output ('uv: ' + $uv.Version); Write-Output 'GitHub: reachable'; Write-Output 'Desktop Runtime uses a verified prebuilt package; C++ build tools are not required.'"
if errorlevel 1 goto :failed

echo Environment setup completed successfully.
echo You can now run 02-install-wecome-bot.bat.
endlocal
exit /b 0

:powershell_missing
echo PowerShell was not found on PATH.
endlocal
exit /b 1

:path_refresh_failed
if defined LB_PATH_FILE del /q "%LB_PATH_FILE%" >nul 2>&1
echo PATH refresh failed. Close this window and run 01-check-environment.bat again.
endlocal
exit /b 1

:failed
echo Environment check or setup failed.
endlocal
exit /b 1
