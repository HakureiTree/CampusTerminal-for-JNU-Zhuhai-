Set-StrictMode -Version Latest

function Get-CampusOriginalService {
    $service=Get-CimInstance Win32_Service -Filter "Name='INODE_SVR_SERVICE'"
    if($null -eq $service){throw 'Pinned original service missing.'}
    $binary='C:\Program Files (x86)\iNode\iNode Client\iNodeMon.exe'
    $expected='"'+$binary+'" -startService'
    if($service.PathName -cne $expected -or (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash -ne '55BA4AC24E619D7C6D2E8889DB783F44FC2644089A25B5D0351FD77C38B5F89F'){
        throw 'Original service binary or command changed.'
    }
    $controller=Get-Service -Name INODE_SVR_SERVICE
    try {
        $dependents=@($controller.DependentServices | Where-Object Status -NE Stopped)
        [pscustomobject]@{Name=$service.Name;Path=$service.PathName;StartMode=$service.StartMode;State=$service.State;AcceptStop=$service.AcceptStop;RunningDependents=$dependents.Count}
    }finally{$controller.Dispose()}
}

function Set-CampusOriginalServiceState {
    param([Parameter(Mandatory=$true)]$Original,[ValidateSet('Running','Stopped')][string]$State,
        [hashtable]$Operations)
    if($null -eq $Operations){
        $Operations=@{
            Read={Get-CampusOriginalService}
            Request={param($target)
                $controller=Get-Service -Name INODE_SVR_SERVICE
                try {
                    if($target -eq 'Stopped'){$controller.Stop()}else{$controller.Start()}
                    $desired=[System.ServiceProcess.ServiceControllerStatus]::$target
                    $controller.WaitForStatus($desired,[TimeSpan]::FromSeconds(30))
                }finally{$controller.Dispose()}
            }
        }
    }
    $before=& $Operations.Read
    if($before.Name -ne $Original.Name -or $before.Path -cne $Original.Path -or $before.StartMode -ne $Original.StartMode){throw 'Service identity or startup mode changed; no transition requested.'}
    if($before.State -eq $State){return $before}
    if($before.State -notin @('Running','Stopped')){throw 'Service transition already in progress.'}
    if($State -eq 'Stopped' -and (-not $before.AcceptStop -or $before.RunningDependents -ne 0)){throw 'Normal service stop not available without affecting dependents.'}
    $null=& $Operations.Request $State
    $after=& $Operations.Read
    if($after.Name -ne $Original.Name -or $after.Path -cne $Original.Path -or $after.StartMode -ne $Original.StartMode -or $after.State -ne $State){throw 'Service transition not verified.'}
    return $after
}
Export-ModuleMember -Function Get-CampusOriginalService,Set-CampusOriginalServiceState
