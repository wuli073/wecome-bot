@echo off
chcp 65001 >nul
if errorlevel 1 goto :failed
setlocal EnableExtensions DisableDelayedExpansion

set "LB_REPO_ROOT=%~dp0"
set "LB_START_SCRIPT=%LB_REPO_ROOT%scripts\start-source.ps1"
set "LB_DOCTOR_SCRIPT=%LB_REPO_ROOT%scripts\doctor-source.ps1"

where powershell.exe >nul 2>&1
if errorlevel 1 goto :powershell_missing
if not exist "%LB_START_SCRIPT%" goto :start_missing
if not exist "%LB_DOCTOR_SCRIPT%" goto :doctor_missing

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $root=[IO.Path]::GetFullPath($env:LB_REPO_ROOT); $scriptPath=$env:LB_START_SCRIPT; Set-Location -LiteralPath $root; $statusOutput=& $scriptPath -Action Status; if (-not $?) { throw 'scripts\\start-source.ps1 -Action Status failed.' }; $status=$statusOutput | ConvertFrom-Json; if ($status.status -ne 'running') { & $scriptPath -Action Start; if (-not $?) { throw 'scripts\\start-source.ps1 failed.' } }"
if errorlevel 1 goto :failed

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $root=[IO.Path]::GetFullPath($env:LB_REPO_ROOT); $scriptPath=$env:LB_DOCTOR_SCRIPT; Set-Location -LiteralPath $root; & $scriptPath; if (-not $?) { throw 'scripts\\doctor-source.ps1 failed.' }"
if errorlevel 1 goto :failed

start "" "http://127.0.0.1:3000"

endlocal
exit /b 0

:powershell_missing
echo PowerShell was not found on PATH.
pause
endlocal
exit /b 1

:start_missing
echo Missing scripts\start-source.ps1.
pause
endlocal
exit /b 1

:doctor_missing
echo Missing scripts\doctor-source.ps1.
pause
endlocal
exit /b 1

:failed
echo Start or doctor check failed.
echo Logs: %LB_REPO_ROOT%.tmp\source-runtime\user-data\logs\source
pause
endlocal
exit /b 1
