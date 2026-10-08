# SPDX-License-Identifier: GPL-3.0-or-later
# Remove only startup entries belonging to this installation. Preserve user data.
param([Parameter(Mandatory=$true)][string]$Root, [switch]$CheckOnly)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$Root=[IO.Path]::GetFullPath($Root).TrimEnd('\')
$core=Join-Path $Root 'CampusTerminal.Core.exe'
$launcher=Join-Path $Root '开源暨珠有线网络终端.exe'
if(-not (Test-Path -LiteralPath (Join-Path $Root 'version.txt'))){throw 'Installation identity missing'}
# A loaded Windows image cannot be opened for writing. Probe only this directory;
# WMI may hide an elevated process's path, including an unrelated portable copy.
foreach($name in @('CampusTerminal.exe','CampusTerminal.Core.exe','CampusTerminal.Core.dll')){
    $file=Join-Path $Root $name
    if(-not (Test-Path -LiteralPath $file)){continue}
    try {
        $probe=[IO.File]::Open($file,[IO.FileMode]::Open,[IO.FileAccess]::Write,[IO.FileShare]::Read)
        $probe.Dispose()
    }catch{exit 1}
}
if($CheckOnly){exit 0}
$run='HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$entry=Get-ItemProperty -LiteralPath $run -Name CampusTerminal -ErrorAction SilentlyContinue
if($entry){
    $command=[string]$entry.CampusTerminal
    if($command.StartsWith('"'+$launcher+'"',[StringComparison]::OrdinalIgnoreCase) -or
       $command.StartsWith('"'+(Join-Path $Root 'CampusTerminal.exe')+'"',[StringComparison]::OrdinalIgnoreCase)){
        Remove-ItemProperty -LiteralPath $run -Name CampusTerminal
    }
}
$name='ReInode-CampusTerminal-Host'
$task=Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue
if($task -and @($task.Actions).Count -eq 1 -and $task.Actions[0].Execute -ieq $core){
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
    try {
        $principal=[Security.Principal.WindowsPrincipal]::new($identity)
        if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
            $parameters='-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "'+$PSCommandPath+'" -Root "'+$Root+'"'
            $child=Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList $parameters -Verb RunAs -WindowStyle Hidden -Wait -PassThru
            exit $child.ExitCode
        }
        $owner=if($task.Principal.UserId -match '^S-1-'){$task.Principal.UserId}else{
            ([Security.Principal.NTAccount]::new($task.Principal.UserId)).Translate([Security.Principal.SecurityIdentifier]).Value
        }
        if($owner -ne $identity.User.Value){throw 'Task owner differs from the current user'}
        Unregister-ScheduledTask -TaskName $name -TaskPath '\' -Confirm:$false
    }finally{$identity.Dispose()}
}
