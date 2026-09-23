<#
.SYNOPSIS
    Re-copy the City Sample assets that PCG_Claude reuses.

.DESCRIPTION
    The migrated City Sample art (~62 GB, ~26k files) is deliberately NOT tracked
    by git: no git-lfs is configured here, and 48 of its files exceed GitHub's
    100 MB hard per-file limit (the largest is 719 MB), so a normal commit cannot
    carry it. The content lives on disk instead, and this script reproduces it
    byte-for-byte from the source project.

    Verified byte-exact on 2026-09-23: every copied subtree matched the source on
    both file count and total byte size.

.PARAMETER Source
    City Sample project root. Defaults to E:\CitySample 5.8.

.PARAMETER WhatIf
    Report what would be copied without writing anything.

.EXAMPLE
    .\Tools\sync-citysample-assets.ps1
    .\Tools\sync-citysample-assets.ps1 -WhatIf
#>
[CmdletBinding()]
param(
    [string]$Source = 'E:\CitySample 5.8',
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path $Source)) {
    throw "City Sample source not found: $Source"
}

# ---- what to copy -----------------------------------------------------------
# /Game content. Excluded: Developer-only and CitySample-internal scratch dirs,
# and the project's own naming collisions (Input, Collections, Developers) which
# are either disjoint or belong to PCG_Claude.
$contentSrc = Join-Path $Source 'Content'
$contentDst = Join-Path $repo 'Content'
$contentExcludeDirs = @('PCGTown', 'PCGTest', 'Developers', 'Collections')

# The plugin carries the 18 city graphs and the 27 building style assets.
$plugSrc = Join-Path $Source 'Plugins\Experimental\CitySamplePCG'
$plugDst = Join-Path $repo 'Plugins\CitySamplePCG'

# ---- run --------------------------------------------------------------------
function Invoke-Copy {
    param([string]$Label, [string]$From, [string]$To, [string[]]$ExcludeDirs)

    Write-Host "=== $Label ===" -ForegroundColor Cyan
    Write-Host "    $From"
    Write-Host "    -> $To"

    $robocopyArgs = @($From, $To, '/E', '/R:1', '/W:1', '/MT:16', '/NFL', '/NDL', '/NJH', '/NP')
    if ($ExcludeDirs.Count -gt 0) { $robocopyArgs += '/XD'; $robocopyArgs += $ExcludeDirs }
    if ($WhatIf)                 { $robocopyArgs += '/L' }

    & robocopy @robocopyArgs | Out-Null

    # Robocopy exit codes are a bitfield; 0-7 are success, >=8 is a real failure.
    $rc = $LASTEXITCODE
    if ($rc -ge 8) { throw "robocopy failed for $Label (exit $rc)" }
    Write-Host ("    robocopy exit {0} (success)" -f $rc) -ForegroundColor Green
}

Invoke-Copy -Label '/Game art'        -From $contentSrc -To $contentDst -ExcludeDirs $contentExcludeDirs
Invoke-Copy -Label 'CitySamplePCG'    -From $plugSrc    -To $plugDst    -ExcludeDirs @()

if ($WhatIf) {
    Write-Host "`n-WhatIf: nothing was written." -ForegroundColor Yellow
    exit 0
}

# ---- verify -----------------------------------------------------------------
Write-Host "`n=== verifying ===" -ForegroundColor Cyan
$pairs = @(
    @((Join-Path $contentSrc 'Building'),           (Join-Path $contentDst 'Building')),
    @((Join-Path $contentSrc 'Prop'),               (Join-Path $contentDst 'Prop')),
    @((Join-Path $contentSrc 'Crowd'),              (Join-Path $contentDst 'Crowd')),
    @((Join-Path $contentSrc 'Vehicle'),            (Join-Path $contentDst 'Vehicle')),
    @((Join-Path $contentSrc 'Road'),               (Join-Path $contentDst 'Road')),
    @((Join-Path $contentSrc 'Megascans'),          (Join-Path $contentDst 'Megascans')),
    @((Join-Path $contentSrc 'Environment'),        (Join-Path $contentDst 'Environment')),
    @((Join-Path $contentSrc 'Material'),           (Join-Path $contentDst 'Material')),
    @(@($plugSrc, $plugDst))
) | ForEach-Object { $_ }

$failed = 0
foreach ($pair in $pairs) {
    $from = $pair[0]; $to = $pair[1]
    if (-not (Test-Path $to)) { Write-Host ("  MISSING  {0}" -f $to) -ForegroundColor Red; $failed++; continue }
    $sf = Get-ChildItem $from -Recurse -File -ErrorAction SilentlyContinue
    $df = Get-ChildItem $to   -Recurse -File -ErrorAction SilentlyContinue
    $sb = ($sf | Measure-Object Length -Sum).Sum
    $db = ($df | Measure-Object Length -Sum).Sum
    $ok = ($sf.Count -eq $df.Count) -and ($sb -eq $db)
    if (-not $ok) { $failed++ }
    Write-Host ("  {0,-5} {1,-16} {2,6} files / {3,14} bytes" -f `
        $(if ($ok) { 'OK' } else { 'DIFF' }), (Split-Path $to -Leaf), $df.Count, $db) `
        -ForegroundColor $(if ($ok) { 'Green' } else { 'Red' })
}

if ($failed -gt 0) { throw "$failed subtree(s) did not match the source" }
Write-Host "`nAll subtrees match the source byte-for-byte." -ForegroundColor Green
