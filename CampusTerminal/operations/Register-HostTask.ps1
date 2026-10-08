# SPDX-License-Identifier: GPL-3.0-or-later
param(
    [Parameter(Mandatory=$true)][string]$Exe,
    [string]$ReportPath
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=[Security.Principal.WindowsPrincipal]::new($identity)
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
    $args='-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "'+$PSCommandPath+'" -Exe "'+$Exe+'"'
    if($ReportPath){$args+=' -ReportPath "'+$ReportPath+'"'}
    try {
        $child=Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList $args -Verb RunAs -WindowStyle Hidden -Wait -PassThru
        exit $child.ExitCode
    }catch{exit 1}
}
$result=[ordered]@{Ok=$false;Error=$null}
try {
    if(-not (Test-Path -LiteralPath $Exe -PathType Leaf)){throw 'Host executable missing'}
    $name='ReInode-CampusTerminal-Host'
    $description='CampusTerminal host: '+$Exe
    $action=New-ScheduledTaskAction -Execute $Exe -Argument 'gui-host' -WorkingDirectory ([IO.Path]::GetDirectoryName($Exe))
    $trigger=New-ScheduledTaskTrigger -AtLogOn -User $identity.Name
    $trigger.Delay='PT20S'
    $owner=New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Highest
    $settings=New-ScheduledTaskSettingsSet -Hidden -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $null=Register-ScheduledTask -TaskName $name -TaskPath '\' -Action $action -Trigger $trigger -Principal $owner -Settings $settings -Description $description -Force
    $check=Get-ScheduledTask -TaskName $name -TaskPath '\'
    if($check.Principal.RunLevel -ne 'Highest' -or $check.Actions[0].Execute -ine $Exe){throw 'Host task verification failed'}
    $result.Ok=$true
}catch{$result.Error=$_.Exception.Message}
if($ReportPath){$result | ConvertTo-Json | Set-Content -LiteralPath $ReportPath -Encoding UTF8}
if(-not $result.Ok){exit 1}
