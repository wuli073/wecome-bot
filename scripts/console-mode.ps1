#requires -Version 5.1

function Disable-ConsoleQuickEdit {
    [CmdletBinding()]
    param()

    if ($env:OS -ne 'Windows_NT') { return $false }
    try {
        if ($null -eq ('LangBot.ConsoleMode.NativeMethods' -as [type])) {
            Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

namespace LangBot.ConsoleMode {
    public static class NativeMethods {
        [DllImport("Kernel32.dll", SetLastError = true)]
        public static extern IntPtr GetStdHandle(int nStdHandle);

        [DllImport("Kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool GetConsoleMode(IntPtr hConsoleHandle, out uint lpMode);

        [DllImport("Kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool SetConsoleMode(IntPtr hConsoleHandle, uint dwMode);
    }
}
'@
        }

        $STD_INPUT_HANDLE = -10
        $ENABLE_QUICK_EDIT_MODE = 0x0040
        $ENABLE_EXTENDED_FLAGS = 0x0080
        $handle = [LangBot.ConsoleMode.NativeMethods]::GetStdHandle($STD_INPUT_HANDLE)
        if ($handle -eq [IntPtr]::Zero -or $handle.ToInt64() -eq -1) { return $false }

        [uint32]$mode = 0
        if (-not [LangBot.ConsoleMode.NativeMethods]::GetConsoleMode($handle, [ref]$mode)) { return $false }
        [uint32]$updatedMode = (($mode -band (-bnot $ENABLE_QUICK_EDIT_MODE)) -bor $ENABLE_EXTENDED_FLAGS)
        if (-not [LangBot.ConsoleMode.NativeMethods]::SetConsoleMode($handle, $updatedMode)) { return $false }
        return $true
    }
    catch {
        Write-Verbose 'Console QuickEdit could not be disabled for this process.'
        return $false
    }
}

function Get-ConsoleSelectionModeHint {
    return ' If the console title contains "Select", press Esc or right-click once to exit selection mode.'
}
