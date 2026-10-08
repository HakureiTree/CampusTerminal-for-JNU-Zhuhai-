param(
    [ValidateSet('Enable','Disable')][string]$Mode='Enable',
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$ReportPath,
    [switch]$SilentStart
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=[Security.Principal.WindowsPrincipal]::new($identity)
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
    $args='-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "'+$PSCommandPath+'" -Mode '+$Mode+' -Python "'+$Python+'" -ReportPath "'+$ReportPath+'"'
    if($SilentStart){$args+=' -SilentStart'}
    try {
        $child=Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList $args -Verb RunAs -WindowStyle Hidden -Wait -PassThru
        exit $child.ExitCode
    }catch{exit 1}
}
$result=[ordered]@{Ok=$false;Mode=$Mode;Error=$null;At=[DateTimeOffset]::UtcNow.ToString('o')}
try {
    if(-not (Test-Path -LiteralPath $Python -PathType Leaf) -or -not (Test-Path (Join-Path $root 'run.py'))){throw 'Launch files missing'}
    $name='ReInode-CampusTerminal'
    $description='CampusTerminal managed logon: '+$root
    $existing=Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue
    if($existing){
        $sid=if($existing.Principal.UserId -match '^S-1-'){$existing.Principal.UserId}else{([Security.Principal.NTAccount]::new($existing.Principal.UserId)).Translate([Security.Principal.SecurityIdentifier]).Value}
        if($existing.Description -cne $description -or $sid -ne $identity.User.Value){throw 'Existing startup task is not owned by this installation'}
    }
    if($Mode -eq 'Enable'){
        $arguments='"'+(Join-Path $root 'run.py')+'"'
        if($SilentStart){$arguments+=' --silent'}
        $action=New-ScheduledTaskAction -Execute $Python -Argument $arguments -WorkingDirectory $root
        $trigger=New-ScheduledTaskTrigger -AtLogOn -User $identity.Name
        $trigger.Delay='PT90S'
        $owner=New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Highest
        $settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        $null=Register-ScheduledTask -TaskName $name -TaskPath '\' -Action $action -Trigger $trigger -Principal $owner -Settings $settings -Description $description -Force
        $check=Get-ScheduledTask -TaskName $name -TaskPath '\'
        if($check.Principal.RunLevel -ne 'Highest' -or $check.Actions[0].Execute -ine $Python -or $check.Actions[0].Arguments -cne $arguments){throw 'Startup task verification failed'}
        $hostExe=Join-Path $root 'core\bin\Release\net10.0-windows\CampusTerminal.Core.exe'
        if(Test-Path -LiteralPath $hostExe -PathType Leaf){
            & (Join-Path $PSScriptRoot 'Register-HostTask.ps1') -Exe $hostExe
        }
    }elseif($existing){Unregister-ScheduledTask -TaskName $name -TaskPath '\' -Confirm:$false}
    # Remove only this application's old duplicate HKCU launch entry.
    $run='HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    if(Get-ItemProperty -LiteralPath $run -Name CampusTerminal -ErrorAction SilentlyContinue){
        Remove-ItemProperty -LiteralPath $run -Name CampusTerminal
    }
    $result.Ok=$true
}catch{$result.Error=$_.Exception.Message}
$result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
if(-not $result.Ok){exit 1}
