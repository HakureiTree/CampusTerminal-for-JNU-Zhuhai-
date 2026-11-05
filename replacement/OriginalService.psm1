Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot '..\src\INodeInstallation.psm1')

function Get-CampusOriginalService {
    $installation=Get-INodeInstallation
    $service=$installation.Service
    try{$controller=Get-Service -Name INODE_SVR_SERVICE -ErrorAction Stop}
    catch{throw 'OriginalServiceQueryFailed'}
    try {
        $dependents=@($controller.DependentServices | Where-Object Status -NE Stopped)
        [pscustomobject]@{Name=$service.Name;Path=$service.PathName;StartMode=$service.StartMode;State=$service.State;AcceptStop=$service.AcceptStop;RunningDependents=$dependents.Count;
            BinaryPath=$installation.BinaryPath;BinarySha256=$installation.BinarySha256}
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
    if(-not (Test-INodeServiceIdentity $Original $before)){throw 'OriginalServiceIdentityChanged'}
    if($before.State -eq $State){return $before}
    if($before.State -notin @('Running','Stopped')){throw 'OriginalServiceBusy'}
    if($State -eq 'Stopped' -and (-not $before.AcceptStop -or $before.RunningDependents -ne 0)){throw 'OriginalServiceStopUnavailable'}
    $null=& $Operations.Request $State
    $after=& $Operations.Read
    if(-not (Test-INodeServiceIdentity $Original $after) -or $after.State -ne $State){throw 'OriginalServiceTransitionUnverified'}
    return $after
}
Export-ModuleMember -Function Get-CampusOriginalService,Set-CampusOriginalServiceState
