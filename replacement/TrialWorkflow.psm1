Set-StrictMode -Version Latest

function Test-CampusTrialPolicyHorizon {
    param([Parameter(Mandatory=$true)][scriptblock]$IsExcluded,
        [Parameter(Mandatory=$true)][DateTimeOffset]$Now,
        [ValidateRange(1,30)][int]$Minutes)
    for($minute=0;$minute -le $Minutes;$minute++){
        if(& $IsExcluded ($Now.AddMinutes($minute))){return $false}
    }
    return $true
}

function New-CampusAuthMaintenanceMarker {
    param([string]$Path,[string]$Marker)
    $temporary=$Path+'.'+[guid]::NewGuid().ToString('N')+'.tmp'
    try {
        [IO.File]::WriteAllText($temporary,$Marker,[Text.UTF8Encoding]::new($false))
        # Same-directory move publishes the complete marker without overwriting an owner.
        [IO.File]::Move($temporary,$Path)
    }finally{
        if([IO.File]::Exists($temporary)){[IO.File]::Delete($temporary)}
    }
}

# Platform operations are injected so ordering and rollback can be tested without
# manipulating the real client, desktop, adapter or monitor.
function Invoke-CampusAuthTrialWorkflow {
    param([Parameter(Mandatory=$true)][hashtable]$Operations,[scriptblock]$OnStage={param($Stage)})
    foreach($name in @('Preflight','PrepareHost','AcquireMaintenance','ExitOriginal','RunReplacement','StopReplacement','RestoreOriginal','ResumeMonitor')){
        if(-not $Operations.ContainsKey($name) -or $Operations[$name] -isnot [scriptblock]){throw "Missing trial operation: $name"}
    }
    $report=[ordered]@{Trial=$null;Error=$null;StopError=$null;RollbackError=$null;ResumeError=$null;CleanupReportingErrors=@();ReplacementStopped=$false;OriginalRestored=$false;MonitorResumed=$false;Verified=$false}
    $hostAttempted=$false;$maintenanceAttempted=$false;$exitAttempted=$false
    try {
        & $OnStage 'Preflight';$null=& $Operations.Preflight
        $hostAttempted=$true
        & $OnStage 'PreparingLocalCredentials';$null=& $Operations.PrepareHost
        & $OnStage 'AcquiringMaintenance'
        $maintenanceAttempted=$true
        $null=& $Operations.AcquireMaintenance
        & $OnStage 'ExitingOriginal'
        $exitAttempted=$true
        $null=& $Operations.ExitOriginal
        & $OnStage 'RunningReplacement';$report.Trial=& $Operations.RunReplacement
    }catch{$report.Error=$_.Exception.Message}
    finally {
        if($hostAttempted){
            try {
                try{& $OnStage 'StoppingReplacement'}catch{$report.CleanupReportingErrors+=@($_.Exception.Message)}
                $report.ReplacementStopped=[bool](& $Operations.StopReplacement)
                if(-not $report.ReplacementStopped){$report.StopError='Replacement process exit not verified.'}
            }catch{$report.StopError=$_.Exception.Message}
        }
        if($exitAttempted -and $report.ReplacementStopped){
            try {
                try{& $OnStage 'RestoringOriginal'}catch{$report.CleanupReportingErrors+=@($_.Exception.Message)}
                $report.OriginalRestored=[bool](& $Operations.RestoreOriginal)
                if(-not $report.OriginalRestored){$report.RollbackError='Original connectivity not verified.'}
            }catch{$report.RollbackError=$_.Exception.Message}
        }
        if($maintenanceAttempted -and $report.ReplacementStopped -and (-not $exitAttempted -or $report.OriginalRestored)){
            try {
                try{& $OnStage 'ResumingMonitor'}catch{$report.CleanupReportingErrors+=@($_.Exception.Message)}
                $report.MonitorResumed=[bool](& $Operations.ResumeMonitor)
                if(-not $report.MonitorResumed){$report.ResumeError='Owned maintenance state was not resumed.'}
            }catch{$report.ResumeError=$_.Exception.Message}
        }
    }
    $report.Verified=$null -ne $report.Trial -and [bool]$report.Trial.Verified -and $report.ReplacementStopped -and $report.OriginalRestored -and $report.MonitorResumed -and -not $report.Error
    return [pscustomobject]$report
}
function Test-CampusAuthGenerationEvidence {
    param([int]$FinalGeneration,[int]$VerifierGeneration,[bool]$NetworkVerified,[bool]$EapAuthenticated,[int]$Heartbeats,[bool]$RecoveryVerified)
    return $FinalGeneration -ge 0 -and $FinalGeneration -eq $VerifierGeneration -and $NetworkVerified -and $EapAuthenticated -and $Heartbeats -ge 3 -and ($FinalGeneration -eq 0 -or $RecoveryVerified)
}
Export-ModuleMember -Function Invoke-CampusAuthTrialWorkflow,New-CampusAuthMaintenanceMarker,Test-CampusTrialPolicyHorizon,Test-CampusAuthGenerationEvidence
