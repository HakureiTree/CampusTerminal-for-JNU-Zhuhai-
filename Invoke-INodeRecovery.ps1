[CmdletBinding()]
param([Parameter(Mandatory)][int]$ExpectedProcessId,[Parameter(Mandatory)][string]$ReportPath,
    [string]$ConfigPath,[switch]$Acceptance,[switch]$ProbeOnly,[string]$ResumeReportPath)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if(-not $ConfigPath){$ConfigPath=Join-Path $PSScriptRoot 'config.json'}
Import-Module (Join-Path $PSScriptRoot 'src\Runtime.psm1')
Import-Module (Join-Path $PSScriptRoot 'src\Observer.psm1')
Import-Module (Join-Path $PSScriptRoot 'src\Recovery.psm1')
Import-Module (Join-Path $PSScriptRoot 'src\INodeController.psm1')
Import-Module (Join-Path $PSScriptRoot 'src\INodeVerification.psm1')
$report=[ordered]@{ControllerVersion='2026-09-16-menu-recovery-v2';ExecutorId=$PID;TargetProcessId=$ExpectedProcessId;
    StartedUtc=[DateTimeOffset]::UtcNow.ToString('o');FinishedUtc=$null;Stage='Preflight';Events=@();Client=$null;Network=$null;Verified=$false;Error=$null}
$record={param($stage,$details)
    $report.Stage=$stage
    $report.Events+=@([pscustomobject]@{TimestampUtc=[DateTimeOffset]::UtcNow.ToString('o');Stage=$stage;Details=$details})
    Write-AtomicJson $ReportPath $report
}.GetNewClosure()
$mutex=[Threading.Mutex]::new($false,'Local\ReInode-NormalExit')
$owned=$false
try {
    try{$owned=$mutex.WaitOne(0)}catch [Threading.AbandonedMutexException]{$owned=$true}
    if(-not $owned){throw 'Another normal-exit transaction is already running.'}
    $config=Read-ObserverConfig $ConfigPath
    $pause=Test-Path (Join-Path $PSScriptRoot 'logs\pause-recovery.signal')
    if($Acceptance -and -not $pause){throw 'Acceptance requires automatic recovery to be paused.'}
    if(-not $Acceptance -and ($pause -or -not $config.Recovery.Enabled -or (Test-PolicyWindow $config.PolicyWindow ([DateTimeOffset]::UtcNow)))){throw 'Recovery paused, disabled or policy blocked.'}
    $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($ReportPath))
    & $record 'ExecutorReady' @{Acceptance=[bool]$Acceptance}
    if($ProbeOnly){
        $client=Get-INodeClientProcess
        if($null -eq $client -or $client.ProcessId -ne $ExpectedProcessId -or $client.PathState -ne 'Verified'){throw 'Probe target changed.'}
        $probe=Request-INodeNormalExit $ExpectedProcessId -ProbeOnly
        & $record 'MenuProbePassed' $probe
        return
    }
    if($ResumeReportPath){
        if(-not $Acceptance){throw 'Verification-only continuation is available only for attended acceptance.'}
        $root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'logs\recovery-actions'))+[IO.Path]::DirectorySeparatorChar
        $sourcePath=[IO.Path]::GetFullPath($ResumeReportPath)
        if(-not $sourcePath.StartsWith($root,[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetExtension($sourcePath) -ne '.json'){throw 'Continuation report must belong to this recovery log directory.'}
        $source=Get-Content -LiteralPath $sourcePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $current=Get-INodeClientProcess
        $started=@($source.Events | Where-Object Stage -eq 'ClientStarted')
        if($null -eq $source.Client -or -not $source.Client.Accepted -or -not $source.FinishedUtc -or $started.Count -ne 1 -or
            $null -eq $current -or $current.PathState -ne 'Verified' -or $current.ProcessId -ne $ExpectedProcessId -or
            $source.Client.ObservedProcessId -ne $ExpectedProcessId -or [DateTimeOffset]$current.StartTimeUtc -lt [DateTimeOffset]$source.StartedUtc -or
            [DateTimeOffset]$current.StartTimeUtc -gt [DateTimeOffset]$started[0].TimestampUtc){throw 'Continuation does not match the already-started client.'}
        & $record 'VerificationResumedWithoutExit' @{OriginalReport=$sourcePath;ObservedProcessId=$ExpectedProcessId}
        $ui=Get-INodeConnectedState $ExpectedProcessId ([DateTimeOffset]$current.StartTimeUtc)
        $report.Client=$source.Client
        $report.Client.AuthenticationVerified=$ui.Verified
        $report.Client.Authentication | Add-Member -NotePropertyName ConnectedState -NotePropertyValue $ui -Force
        $report.Client.Authentication.Verified=$ui.Verified
        & $record 'AuthenticationChecked' $ui
    }else{
        $report.Client=Invoke-INodeGuiRestart -ExpectedProcessId $ExpectedProcessId -RecordStage $record
    }
    $report.Network=Invoke-INodeNetworkVerification $config $report.Client $record
    $report.Verified=$report.Network.Verified
    if($report.Verified){
        $current=Get-INodeClientProcess
        if($null -ne $current -and $current.PathState -eq 'Verified' -and $current.ProcessId -eq $report.Client.ObservedProcessId){
            [ReInode.Desktop]::HideClientWindow($current.ProcessId)
        }
        & $record 'Verified' @{}
    } else { & $record 'Unverified' @{} }
} catch {$report.Error=$_.Exception.ToString();$report.Stage='Failed'}
finally {
    $report.FinishedUtc=[DateTimeOffset]::UtcNow.ToString('o')
    try{Write-AtomicJson $ReportPath $report}finally{if($owned){$mutex.ReleaseMutex()};$mutex.Dispose()}
}
if(-not $report.Verified){exit 1}
