# SPDX-License-Identifier: GPL-3.0-or-later
# Versions come from the two manifests. This script does not invent a version number.
param(
    [Parameter(Mandatory=$true)][string]$BaseManifest,
    [Parameter(Mandatory=$true)][string]$NewManifest,
    [Parameter(Mandatory=$true)][string]$NewTree,
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [string]$Python='python'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
& $Python (Join-Path $PSScriptRoot 'update_package.py') delta `
    --base-manifest $BaseManifest --new-manifest $NewManifest --new-tree $NewTree --output $OutputDir
if ($LASTEXITCODE -ne 0) { throw 'Delta package failed' }
Get-Item -LiteralPath (Join-Path $OutputDir 'update-manifest.json')
