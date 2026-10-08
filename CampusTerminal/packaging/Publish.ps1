# SPDX-License-Identifier: GPL-3.0-or-later
# Build the public portable distribution. No private state or third-party installers.
param([string]$OutputRoot, [string]$Python='python')
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$pack=$PSScriptRoot
$ct=[IO.Path]::GetFullPath((Join-Path $pack '..'))
$repo=[IO.Path]::GetFullPath((Join-Path $ct '..'))
if(-not $OutputRoot){$OutputRoot=Join-Path $repo 'build'}
$OutputRoot=[IO.Path]::GetFullPath($OutputRoot)
if($OutputRoot.StartsWith((Join-Path $repo 'release')+'\',[StringComparison]::OrdinalIgnoreCase)){
    throw 'OutputRoot must not overwrite the versioned release archive'
}
$version=[regex]::Match([IO.File]::ReadAllText((Join-Path $ct 'gui\theme.py')), 'APP_VERSION = "([0-9.]+)"').Groups[1].Value
if(-not $version){throw 'APP_VERSION missing'}
$out=Join-Path $OutputRoot 'CampusTerminal'
$stage=Join-Path $OutputRoot '_stage'
# Never delete source files or the repository's versioned release archive.
foreach($protected in @($repo,$ct,(Join-Path $repo 'release'))){
    if($OutputRoot -ieq $protected -or $protected.StartsWith($OutputRoot+'\',[StringComparison]::OrdinalIgnoreCase)){
        throw 'OutputRoot must be a dedicated build directory'
    }
}
if($OutputRoot.StartsWith($ct+'\',[StringComparison]::OrdinalIgnoreCase) -and
   -not $OutputRoot.StartsWith((Join-Path $ct 'release')+'\',[StringComparison]::OrdinalIgnoreCase)){
    throw 'OutputRoot must not be inside the source tree'
}
$resolvedOut=[IO.Path]::GetFullPath($out)
if(-not $resolvedOut.StartsWith($OutputRoot+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Unsafe output path'}
if(Test-Path -LiteralPath $out){Remove-Item -LiteralPath $out -Recurse -Force}
New-Item -ItemType Directory -Force -Path $out,$stage | Out-Null
& $Python -c 'import PyQt5, psutil, PyInstaller'
if($LASTEXITCODE -ne 0){throw 'Install requirements.txt with the selected Python first'}

$coreOut=Join-Path $stage 'core'
dotnet build (Join-Path $ct 'core\CampusTerminal.Core.csproj') -c Release --configfile (Join-Path $ct 'core\NuGet.Config') -o $coreOut
if($LASTEXITCODE -ne 0){throw 'Core build failed'}
Copy-Item -Path (Join-Path $coreOut '*') -Destination $out -Exclude *.pdb,*.xml -Force

& $Python -m PyInstaller --noconfirm --clean --distpath (Join-Path $stage 'gui') --workpath (Join-Path $stage 'pyi') (Join-Path $pack 'CampusTerminal.spec')
if($LASTEXITCODE -ne 0){throw 'GUI build failed'}
$guiDir=Join-Path $stage 'gui\CampusTerminal'
Copy-Item -LiteralPath (Join-Path $guiDir 'CampusTerminal.exe') -Destination $out
Copy-Item -LiteralPath (Join-Path $guiDir '_internal') -Destination $out -Recurse

dotnet build (Join-Path $pack 'Launch\Launch.csproj') -c Release --configfile (Join-Path $pack 'NuGet.Config')
if($LASTEXITCODE -ne 0){throw 'Launcher build failed'}
Get-ChildItem -LiteralPath (Join-Path $pack 'Launch\bin\Release') -File |
    Where-Object { $_.Extension -in '.exe','.config' } | Copy-Item -Destination $out -Force

foreach($folder in @('CampusTerminal\core\handoff','CampusTerminal\operations','src','replacement','operations','handoff','payload')){
    New-Item -ItemType Directory -Force -Path (Join-Path $out $folder) | Out-Null
}
foreach($folder in @('CampusTerminal\core\handoff','handoff')){
    Copy-Item -LiteralPath (Join-Path $ct 'core\handoff\Invoke-OriginalHandoffStage.ps1') -Destination (Join-Path $out $folder)
}
foreach($folder in @('CampusTerminal\operations','operations')){
    foreach($name in @('Register-HostTask.ps1','Install-Startup.ps1')){
        Copy-Item -LiteralPath (Join-Path $ct ('operations\'+$name)) -Destination (Join-Path $out $folder)
    }
}
Copy-Item -Path (Join-Path $repo 'src\*') -Destination (Join-Path $out 'src') -Exclude __pycache__ -Recurse
foreach($name in @('OriginalService.psm1','TrialWorkflow.psm1')){
    Copy-Item -LiteralPath (Join-Path $repo ('replacement\'+$name)) -Destination (Join-Path $out 'replacement')
}
foreach($name in @('Supervise-Observation.ps1','Watch-Network.ps1','Invoke-INodeRecovery.ps1','Test-CampusAuthNetwork.ps1','LICENSE','THIRD-PARTY.md')){
    Copy-Item -LiteralPath (Join-Path $repo $name) -Destination $out
}
Copy-Item -LiteralPath (Join-Path $pack 'README.txt'),(Join-Path $pack 'Remove-Installation.ps1') -Destination $out
Copy-Item -LiteralPath (Join-Path $repo 'licenses') -Destination $out -Recurse
Set-Content -LiteralPath (Join-Path $out 'CampusTerminal.portable') -Value 'CampusTerminal portable' -Encoding ascii
Set-Content -LiteralPath (Join-Path $out 'edition.txt') -Value 'portable' -Encoding ascii
Set-Content -LiteralPath (Join-Path $out 'version.txt') -Value $version -Encoding ascii
$zip=Join-Path $OutputRoot "CampusTerminal-$version-windows-x64-portable.zip"
Compress-Archive -LiteralPath $out -DestinationPath $zip -Force
Write-Output "Portable folder: $out"
Write-Output "Portable zip: $zip"
