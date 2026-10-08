# SPDX-License-Identifier: GPL-3.0-or-later
<#
.SYNOPSIS
Build the portable package and Windows installer from source.
.EXAMPLE
.\Build.ps1 -Iscc 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
.EXAMPLE
.\Build.ps1 -PortableOnly
#>
param(
    [string]$Python,
    [string]$OutputRoot,
    [string]$Iscc,
    [switch]$PortableOnly
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if(-not $OutputRoot){$OutputRoot=Join-Path $PSScriptRoot 'build'}
$OutputRoot=[IO.Path]::GetFullPath($OutputRoot)
if(-not $Python){
    $venvPython=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if(Test-Path -LiteralPath $venvPython -PathType Leaf){$Python=$venvPython}
    else {$Python='python'}
}
$pythonCommand=Get-Command $Python -CommandType Application -ErrorAction SilentlyContinue
if(-not $pythonCommand){throw 'Python not found. Prepare the Python environment described in README.md or pass -Python <python.exe>.'}
$Python=$pythonCommand.Source
if($Iscc){
    if(-not (Test-Path -LiteralPath $Iscc -PathType Leaf)){throw "Inno Setup compiler not found: $Iscc"}
    $Iscc=(Resolve-Path -LiteralPath $Iscc).Path
}

$pack=Join-Path $PSScriptRoot 'CampusTerminal\packaging'
& (Join-Path $pack 'Publish.ps1') -Python $Python -OutputRoot $OutputRoot
if(-not $PortableOnly){
    & (Join-Path $pack 'Build-Installer.ps1') -SourceDir (Join-Path $OutputRoot 'CampusTerminal') -OutputDir $OutputRoot -Iscc $Iscc
}
