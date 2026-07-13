#requires -Version 5.1
[CmdletBinding()]
param([string]$UserDataRoot)

if ($UserDataRoot) {
    & (Join-Path $PSScriptRoot 'start-source.ps1') -Action Stop -UserDataRoot $UserDataRoot
}
else {
    & (Join-Path $PSScriptRoot 'start-source.ps1') -Action Stop
}
