# SPDX-License-Identifier: GPL-3.0-or-later
param([Parameter(Mandatory=$true)][string]$SourceDir, [string]$OutputDir, [string]$Iscc)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$SourceDir=(Resolve-Path -LiteralPath $SourceDir).Path
if(-not $OutputDir){$OutputDir=Split-Path $SourceDir -Parent}
$OutputDir=[IO.Path]::GetFullPath($OutputDir)
$version=([IO.File]::ReadAllText((Join-Path $SourceDir 'version.txt'))).Trim()
if($version -notmatch '^\d+\.\d+\.\d+$'){throw 'Invalid version'}
foreach($required in @('CampusTerminal.exe','CampusTerminal.Core.exe','开源暨珠有线网络终端.exe','LICENSE','Remove-Installation.ps1')){
    if(-not (Test-Path -LiteralPath (Join-Path $SourceDir $required) -PathType Leaf)){throw "Missing $required"}
}
if(-not $Iscc){
    $command=Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if($command){$Iscc=$command.Source}
    else {
        foreach($base in @(${env:ProgramFiles(x86)},$env:ProgramFiles)){
            if(-not $base){continue}
            $candidate=Join-Path $base 'Inno Setup 6\ISCC.exe'
            if(Test-Path -LiteralPath $candidate){$Iscc=$candidate;break}
        }
    }
}
if(-not $Iscc -or -not (Test-Path -LiteralPath $Iscc)){throw 'Install Inno Setup 6.7.3 or pass -Iscc <ISCC.exe>'}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
& $Iscc ('/DSourceDir='+$SourceDir) ('/DOutputDir='+$OutputDir) ('/DAppVersion='+$version) (Join-Path $PSScriptRoot 'CampusTerminal.iss')
if($LASTEXITCODE -ne 0){throw 'Installer compilation failed'}
$setup=Join-Path $OutputDir "CampusTerminal-$version-windows-x64-setup.exe"
if(-not (Test-Path -LiteralPath $setup)){throw 'Installer not produced'}
Write-Output $setup
