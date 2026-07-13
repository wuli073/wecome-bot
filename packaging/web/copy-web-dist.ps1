[CmdletBinding()]
param(
    [string]$SourceDist = (Join-Path $PSScriptRoot '..\..\web\dist'),
    [string]$ResourcesRoot,
    [switch]$VerifyOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-AbsolutePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathValue
    )

    $item = Get-Item -LiteralPath $PathValue -ErrorAction Stop
    return $item.FullName
}

function Assert-FrontendDist {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DistRoot
    )

    $indexPath = Join-Path $DistRoot 'index.html'
    if (-not (Test-Path -LiteralPath $indexPath -PathType Leaf)) {
        throw "Frontend dist is missing index.html: $indexPath"
    }

    $sampleAsset = Get-ChildItem -LiteralPath $DistRoot -Recurse -File |
        Where-Object { $_.Name -notin @('index.html', '404.html') } |
        Select-Object -First 1

    if ($null -eq $sampleAsset) {
        throw "Frontend dist does not contain any static assets: $DistRoot"
    }

    return [pscustomobject]@{
        IndexPath   = $indexPath
        SampleAsset = $sampleAsset.FullName
    }
}

$resolvedSourceDist = Resolve-AbsolutePath -PathValue $SourceDist
$sourceVerification = Assert-FrontendDist -DistRoot $resolvedSourceDist

if ([string]::IsNullOrWhiteSpace($ResourcesRoot)) {
    throw 'ResourcesRoot is required'
}

$resourcesRootPath = [System.IO.Path]::GetFullPath($ResourcesRoot)
$targetWebRoot = Join-Path $resourcesRootPath 'web'
$targetDist = Join-Path $targetWebRoot 'dist'

if (-not $VerifyOnly) {
    New-Item -ItemType Directory -Force -Path $targetWebRoot | Out-Null
    if (Test-Path -LiteralPath $targetDist) {
        Remove-Item -LiteralPath $targetDist -Recurse -Force
    }
    Copy-Item -LiteralPath $resolvedSourceDist -Destination $targetWebRoot -Recurse -Force
}

$targetVerification = Assert-FrontendDist -DistRoot $targetDist

[pscustomobject]@{
    SourceDist        = $resolvedSourceDist
    TargetDist        = $targetDist
    SourceIndexPath   = $sourceVerification.IndexPath
    TargetIndexPath   = $targetVerification.IndexPath
    SampleStaticAsset = $targetVerification.SampleAsset
    VerifiedOnly      = [bool]$VerifyOnly
} | ConvertTo-Json -Depth 3
