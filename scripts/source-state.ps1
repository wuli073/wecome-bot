#requires -Version 5.1

function Write-ManagedSourceState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [object]$Value
    )

    $directory = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
    }

    $temporary = "$Path.tmp"
    try {
        [IO.File]::WriteAllText(
            $temporary,
            ($Value | ConvertTo-Json -Depth 8),
            (New-Object Text.UTF8Encoding($true))
        )
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        }
    }
}

function Read-ManagedSourceState {
    param(
        [string]$Path,
        [switch]$Quiet
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    try {
        # UTF8Encoding recognizes a BOM and accepts legacy UTF-8 files without one.
        $content = [IO.File]::ReadAllText($Path, (New-Object Text.UTF8Encoding($false, $true)))
        if ([string]::IsNullOrWhiteSpace($content)) {
            if (-not $Quiet) { Write-Warning "Ignoring empty managed source state file: $Path" }
            return $null
        }

        $state = ConvertFrom-Json -InputObject $content -ErrorAction Stop
        if ($null -eq $state -or $state -is [System.Array] -or $state -isnot [PSCustomObject]) {
            if (-not $Quiet) { Write-Warning "Ignoring non-object managed source state file: $Path" }
            return $null
        }

        $repoRoot = Get-ManagedSourceStateProperty -Object $state -Name 'repoRoot'
        if ($repoRoot -isnot [string] -or [string]::IsNullOrWhiteSpace($repoRoot)) {
            if (-not $Quiet) { Write-Warning "Ignoring managed source state without repoRoot: $Path" }
            return $null
        }

        return $state
    }
    catch {
        if (-not $Quiet) { Write-Warning "Ignoring unreadable managed source state file '$Path': $($_.Exception.Message)" }
        return $null
    }
}

function Get-ManagedSourceStateProperty {
    param(
        [object]$Object,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if ($null -eq $Object) {
        return $null
    }

    if ($Object -is [System.Collections.IDictionary]) {
        if (-not $Object.Contains($Name)) {
            return $null
        }
        return $Object[$Name]
    }

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }

    return $property.Value
}

function Test-ManagedSourceStateProperty {
    param(
        [object]$Object,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if ($null -eq $Object) {
        return $false
    }

    if ($Object -is [System.Collections.IDictionary]) {
        return $Object.Contains($Name)
    }

    return $null -ne $Object.PSObject.Properties[$Name]
}
