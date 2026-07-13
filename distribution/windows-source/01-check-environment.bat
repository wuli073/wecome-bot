@echo off
chcp 65001 >nul
if errorlevel 1 goto :failed
setlocal EnableExtensions DisableDelayedExpansion

where powershell.exe >nul 2>&1
if errorlevel 1 goto :powershell_missing

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; if ($PSVersionTable.PSVersion.Major -lt 5) { throw 'PowerShell 5.1 or later is required.' }; if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 is required.' }; foreach ($name in @('git.exe','node.exe','npm.cmd','uv.exe')) { $command=Get-Command $name -ErrorAction SilentlyContinue; if ($null -eq $command) { throw ($name + ' was not found on PATH.') }; $output=& $command.Source --version 2>&1; if ($LASTEXITCODE -ne 0) { throw ($name + ' --version failed.') }; $version=([string]($output | Select-Object -First 1)).Trim(); if ($name -eq 'node.exe' -and $version -notmatch '^v22\.') { throw ('Node.js 22.x is required; found ' + $version + '.') }; Write-Output ($name + ': ' + $version) }; Write-Output 'Environment check passed.'"
if errorlevel 1 goto :failed

endlocal
exit /b 0

:powershell_missing
echo PowerShell was not found on PATH.
endlocal
exit /b 1

:failed
echo Environment check failed.
endlocal
exit /b 1
