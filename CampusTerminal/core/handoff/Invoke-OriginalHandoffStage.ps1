param(
    [Parameter(Mandatory=$true)][ValidateSet('Preflight','RecoveryPreflight','StopOriginal','StopOriginalService','RestoreService','ClientExists','StartClient','WaitClient','Authentication','Network','ResumeMonitor')][string]$Stage,
    [Parameter(Mandatory=$true)][string]$ContextPath,
    [int]$CallerProcessId=0,
    [string]$CallerStartedUtc
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if($CallerProcessId -gt 0){
    # Publish before checking the caller: a recovery process can either see this
    # helper or know it cannot act after its original caller has died.
    $self=Get-Process -Id $PID
    $identity=@{ProcessId=$PID;StartedUtc=$self.StartTime.ToUniversalTime().ToString('o');Stage=$Stage} | ConvertTo-Json -Compress
    $file=Join-Path ([IO.Path]::GetDirectoryName($ContextPath)) ('helper-'+$PID+'.json')
    [IO.File]::WriteAllText($file+'.tmp',$identity)
    [IO.File]::Move($file+'.tmp',$file)
    $caller=Get-Process -Id $CallerProcessId -ErrorAction Stop
    if($caller.HasExited -or $caller.StartTime.ToUniversalTime().Ticks -ne ([DateTimeOffset]$CallerStartedUtc).UtcDateTime.Ticks){throw 'HandoffCallerChanged'}
}
$context=Get-Content -LiteralPath $ContextPath -Raw | ConvertFrom-Json
$root=[IO.Path]::GetFullPath($context.Root)
function Resolve-PackFile([string]$Rel){
    $here=$PSScriptRoot
    foreach($base in @($root,$here,(Split-Path $here -Parent),(Split-Path (Split-Path $here -Parent) -Parent))){
        if(-not $base){continue}
        $candidate=Join-Path $base $Rel
        if(Test-Path -LiteralPath $candidate){return $candidate}
    }
    throw "HandoffExecutorMissing:$Rel"
}
$logs=Join-Path $root 'logs'
$pause=Join-Path $logs 'pause-recovery.signal'
$statePath=Join-Path ([IO.Path]::GetDirectoryName($ContextPath)) 'original-state.json'
Import-Module (Resolve-PackFile 'src\Runtime.psm1')
Import-Module (Resolve-PackFile 'src\INodeController.psm1')
Import-Module (Resolve-PackFile 'replacement\OriginalService.psm1')

function Assert-OwnedPause {
    if(-not [IO.File]::Exists($pause) -or [IO.File]::ReadAllText($pause) -cne $context.Marker){throw 'MaintenanceOwnershipLost'}
}
function Read-OriginalState { Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json }
function Get-VerifiedClient {
    $client=Get-INodeClientProcess
    if($null -ne $client -and $client.PathState -ne 'Verified'){throw 'OriginalClientIdentityUnavailable'}
    return $client
}
function Observer-Available { Test-Path -LiteralPath (Join-Path $root 'config.json') }
function Get-VerifiedMonitor {
    if(-not (Observer-Available)){return $null}
    $settings=Get-Content -LiteralPath (Join-Path $root 'config.json') -Raw | ConvertFrom-Json
    if(-not $settings.Recovery.Enabled -or $settings.Recovery.Mode -cne 'GuiRestart'){throw 'ObserverRecoveryNotEnabled'}
    $control=Get-Content -LiteralPath (Join-Path $logs 'control.json') -Raw | ConvertFrom-Json
    if($control.TaskName -cne 'ReInode-Observer' -or $control.RunId -notmatch '^[a-f0-9]{32}$'){throw 'ObserverTaskIdentityChanged'}
    $task=Get-ScheduledTask -TaskName ReInode-Observer -TaskPath '\'
    $actions=@($task.Actions)
    $executable=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $arguments='-NoProfile -NonInteractive -WindowStyle Hidden -File "'+(Join-Path $root 'Supervise-Observation.ps1')+'" -RunId '+$control.RunId
    if($actions.Count -ne 1 -or $actions[0].Execute -ine $executable -or $actions[0].Arguments -cne $arguments -or
        [IO.Path]::GetFullPath($actions[0].WorkingDirectory) -ine $root -or $task.Principal.RunLevel -ne 'Highest' -or
        $task.Principal.LogonType -ne 'Interactive' -or $task.State -eq 'Disabled' -or $task.Settings.MultipleInstances -ne 'IgnoreNew'){
        throw 'ObserverTaskIdentityChanged'
    }
    $account=[Security.Principal.WindowsIdentity]::GetCurrent()
    try {
        $taskSid=if($task.Principal.UserId -match '^S-1-'){$task.Principal.UserId}else{([Security.Principal.NTAccount]::new($task.Principal.UserId)).Translate([Security.Principal.SecurityIdentifier]).Value}
        if($taskSid -ne $account.User.Value){throw 'ObserverTaskOwnerChanged'}
    }finally{$account.Dispose()}
    return $control
}
function Test-FreshMonitor($Control,[DateTimeOffset]$Since) {
    try {
        $latest=Get-Content -LiteralPath (Join-Path $logs 'latest.json') -Raw | ConvertFrom-Json
        $heart=Get-Content -LiteralPath (Join-Path $logs 'heartbeat.json') -Raw | ConvertFrom-Json
        $identity=Get-Content -LiteralPath (Join-Path $logs 'worker.json') -Raw | ConvertFrom-Json
        $now=[DateTimeOffset]::UtcNow
        foreach($record in @($latest,$heart)){
            $time=[DateTimeOffset]$record.TimestampUtc
            if($record.RunId -cne $Control.RunId -or $time -lt $Since -or $time -gt $now.AddSeconds(2) -or $time -lt $now.AddSeconds(-15)){return $false}
        }
        if($identity.RunId -cne $Control.RunId -or $latest.ProcessId -ne $heart.ProcessId -or $heart.ProcessId -ne $identity.ProcessId -or
            $latest.Recovery.Decision -eq 'Paused' -or $latest.Recovery.Mode -ne 'GuiRestart' -or -not $latest.ControllerReady -or
            $latest.ControllerVersion -cne '2026-09-16-menu-recovery-v2'){return $false}
        $worker=Get-Process -Id $heart.ProcessId -ErrorAction Stop
        try {
            $start=[DateTimeOffset]$worker.StartTime.ToUniversalTime()
            $expected=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
            return -not $worker.HasExited -and $worker.Path -ieq $expected -and [math]::Abs(($start-([DateTimeOffset]$identity.StartedUtc)).TotalSeconds) -le 1
        }finally{$worker.Dispose()}
    }catch{return $false}
}
function Assert-Adapter {
    $nic=@(Get-NetAdapter | Where-Object { [guid]$_.InterfaceGuid -eq [guid]$context.Adapter })
    if($nic.Count -ne 1 -or ($nic[0].MacAddress -replace '[-:]','') -ine $context.Mac){throw 'InterfaceIdentityChanged'}
    if(-not (Observer-Available)){return}
    $config=Get-Content -LiteralPath (Join-Path $root 'config.json') -Raw | ConvertFrom-Json
    if([guid]$config.AdapterGuid -ne [guid]$context.Adapter){throw 'ObserverAdapterMismatch'}
}
function Save-Client($Client) {
    $state=Read-OriginalState
    $state.ClientId=$Client.ProcessId
    $state.ClientStartedUtc=$Client.StartTimeUtc
    Write-AtomicJson $statePath $state
}
function Convert-LogCheckpoint($raw) {
    $checkpoint=@{}
    if($null -eq $raw){return $checkpoint}
    if($raw -is [hashtable]){return $raw}
    foreach($p in $raw.PSObject.Properties){ $checkpoint[$p.Name]=[long]$p.Value }
    return $checkpoint
}
function Test-LogAndAddressAuthentication($State) {
    try {
        $checkpoint=Convert-LogCheckpoint $State.LogCheckpoint
        $evidence=$null
        if($checkpoint.Count -gt 0){ $evidence=Get-INodeAuthenticationEvidence $checkpoint }
        if(-not $evidence -or -not $evidence.ActiveConnection){ $evidence=Get-INodeTailAuthenticationEvidence }
        $nic=@(Get-NetAdapter | Where-Object { [guid]$_.InterfaceGuid -eq [guid]$context.Adapter })
        if($nic.Count -ne 1){return $false}
        $addresses=@(Get-NetIPAddress -InterfaceIndex $nic[0].ifIndex -AddressFamily IPv4 |
            Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.AddressState -eq 'Preferred' })
        return [bool]($evidence.ActiveConnection -and $addresses.Count -eq 1)
    }catch{return $false}
}
function Wait-StableClient {
    $deadline=[DateTimeOffset]::UtcNow.AddSeconds(25)
    $identity='';$rounds=0
    do {
        Assert-OwnedPause
        $client=Get-VerifiedClient
        if($null -ne $client){
            $current=[string]$client.ProcessId+'|'+$client.StartTimeUtc
            if($current -ceq $identity){$rounds++}else{$identity=$current;$rounds=1}
            # The service can replace its first GUI during startup. Do not bind
            # authentication evidence until one verified identity has settled.
            if($rounds -ge 21){Save-Client $client;return $true}
        }else{$identity='';$rounds=0}
        Start-Sleep -Milliseconds 500
    }while([DateTimeOffset]::UtcNow -lt $deadline)
    return $false
}
function Assert-SameClient {
    $state=Read-OriginalState
    $client=Get-VerifiedClient
    if($null -eq $client -or $client.ProcessId -ne $state.ClientId -or $client.StartTimeUtc -cne $state.ClientStartedUtc){throw 'OriginalClientIdentityChanged'}
    return $client
}
function Find-VerifiedAuthenticationBaseline($State,$Auth) {
    if(-not $Auth.IdentityVerified -or $Auth.ConnectedMatches -ne 1 -or $Auth.LabelMatches -ne 1 -or
        $Auth.OnlineTimeMatches -ne 1 -or $null -eq $Auth.OnlineTime){return $null}
    $history=Join-Path $logs 'campus-terminal'
    if(-not (Test-Path -LiteralPath $history)){return $null}
    foreach($folder in @(Get-ChildItem -LiteralPath $history -Directory | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 30)){
        try {
            $result=Get-Content (Join-Path $folder.FullName 'result.json') -Raw | ConvertFrom-Json
            $previous=Get-Content (Join-Path $folder.FullName 'original-state.json') -Raw | ConvertFrom-Json
            $identity=Get-Content (Join-Path $folder.FullName 'context.json') -Raw | ConvertFrom-Json
            $proof=Get-Content (Join-Path $folder.FullName 'authentication-evidence.json') -Raw | ConvertFrom-Json
            if($result.Succeeded -and $result.Stage -eq 'Complete' -and $proof.Verified -and $proof.IdentityVerified -and
                [guid]$identity.Adapter -eq [guid]$context.Adapter -and $identity.Mac -ceq $context.Mac -and
                $previous.ClientId -eq $State.ClientId -and $proof.ObservedProcessId -eq $State.ClientId -and
                $previous.ClientStartedUtc -ceq $State.ClientStartedUtc -and $previous.RunId -ceq $State.RunId -and
                [DateTimeOffset]$proof.OnlineTime -eq [DateTimeOffset]$Auth.OnlineTime -and
                [DateTimeOffset]$previous.AuthenticationSinceUtc -le [DateTimeOffset]$Auth.OnlineTime){
                return [pscustomobject]@{Since=$previous.AuthenticationSinceUtc;Source=$folder.FullName}
            }
        }catch{continue}
    }
    return $null
}

$result=[ordered]@{Ok=$false;Value=$false;Stage=$Stage;Error=$null;TimestampUtc=[DateTimeOffset]::UtcNow.ToString('o')}
try {
    Assert-OwnedPause
    Assert-Adapter
    switch($Stage){
        RecoveryPreflight {
            $state=Read-OriginalState
            $control=Get-VerifiedMonitor
            $service=Get-CampusOriginalService
            $runId=if($null -eq $control){'none'}else{$control.RunId}
            if($runId -cne $state.RunId -or $service.Name -cne $state.Service.Name -or
                $service.Path -cne $state.Service.Path -or $service.StartMode -cne $state.Service.StartMode){throw 'RecoveryBaselineChanged'}
        }
        Preflight {
            $control=Get-VerifiedMonitor
            $service=Get-CampusOriginalService
            $started=[DateTimeOffset]::UtcNow.ToString('o')
            $existing=Get-VerifiedClient
            $since=if($null -ne $existing){$existing.StartTimeUtc}else{$started}
            $runId=if($null -eq $control){'none'}else{$control.RunId}
            $state=[ordered]@{Service=$service;RunId=$runId;ClientId=0;ClientStartedUtc='';StartedUtc=$started;AuthenticationSinceUtc=$since}
            Write-AtomicJson $statePath $state
        }
        StopOriginal {
            $state=Read-OriginalState
            $client=Get-VerifiedClient
            if($null -ne $client){
                Assert-OwnedPause
                # Verify normal GUI exit before changing the service. A rejected
                # menu action must not unnecessarily drop the working connection.
                $exit=Request-INodeNormalExit -ExpectedProcessId $client.ProcessId
                Write-AtomicJson (Join-Path ([IO.Path]::GetDirectoryName($ContextPath)) 'normal-exit-evidence.json') $exit
            }
            Assert-OwnedPause
            $null=Set-CampusOriginalServiceState -Original $state.Service -State Stopped
            $deadline=[DateTimeOffset]::UtcNow.AddSeconds(30)
            while(@(Get-INodeProcessInventory).Count -gt 0){
                Assert-OwnedPause
                if([DateTimeOffset]::UtcNow -ge $deadline){throw 'OriginalNormalStopTimeout'}
                Start-Sleep -Milliseconds 250
            }
        }
        StopOriginalService {
            $state=Read-OriginalState
            Assert-OwnedPause
            $null=Set-CampusOriginalServiceState -Original $state.Service -State Stopped
            try { Close-INodeGuiWindows } catch {}
            $deadline=[DateTimeOffset]::UtcNow.AddSeconds(30)
            while(@(Get-INodeSuiteInventory).Count -gt 0){
                Assert-OwnedPause
                try { Close-INodeGuiWindows } catch {}
                if([DateTimeOffset]::UtcNow -ge $deadline){
                    try { $null=Set-CampusOriginalServiceState -Original $state.Service -State Running } catch {}
                    throw 'OriginalNormalStopTimeout'
                }
                Start-Sleep -Milliseconds 250
            }
        }
        RestoreService {
            $state=Read-OriginalState
            $null=Set-CampusOriginalServiceState -Original $state.Service -State Running
        }
        ClientExists {
            $client=Get-VerifiedClient
            $result.Value=$null -ne $client
            if($result.Value -and -not (Wait-StableClient)){throw 'ExistingOriginalClientNotStable'}
        }
        StartClient {
            $client=Get-VerifiedClient
            $state=Read-OriginalState
            try { $state | Add-Member NoteProperty LogCheckpoint (Get-INodeLogCheckpoint) -Force } catch {}
            Write-AtomicJson $statePath $state
            if($null -eq $client){
                try {Start-INodeClientNormal}catch{throw 'OriginalLaunchRequestFailed'}
            }else{Save-Client $client}
        }
        WaitClient {
            $result.Value=Wait-StableClient
        }
        Authentication {
            $client=Assert-SameClient
            $state=Read-OriginalState
            $since=if($state.PSObject.Properties['AuthenticationSinceUtc']){$state.AuthenticationSinceUtc}else{$state.StartedUtc}
            $verified=$false
            for($attempt=0;$attempt -lt 3;$attempt++){
                try {
                    $auth=Get-INodeConnectedState $client.ProcessId ([DateTimeOffset]$since) -RevealFromTray
                } catch {
                    $auth=[pscustomobject]@{Verified=$false;Method='CaptureFailed';Error=$_.Exception.Message;
                        IdentityVerified=$false;ConnectedMatches=0;LabelMatches=0;OnlineTimeMatches=0;OnlineTime=$null;
                        ObservedProcessId=$client.ProcessId;Since=$since}
                    if($_.Exception.Message -notmatch 'PopupOccluded|ClientStatusWindowNotUnique|WindowChanged|PopupChanged|TargetOccluded|PointerDidNotReachTarget|OpenPopup'){throw}
                    if(Test-LogAndAddressAuthentication $state){
                        $auth.Verified=$true
                        $auth.Method='LogAndAddress'
                    }
                }
                if(-not $auth.Verified){
                    $baseline=Find-VerifiedAuthenticationBaseline $state $auth
                    if($null -ne $baseline){
                        $null=Assert-SameClient
                        $auth=Get-INodeConnectedState $client.ProcessId ([DateTimeOffset]$baseline.Since) -RevealFromTray
                        if($auth.Verified){
                            $state.AuthenticationSinceUtc=$baseline.Since
                            $state | Add-Member NoteProperty BaselineSource $baseline.Source -Force
                            Write-AtomicJson $statePath $state
                        }
                    }
                }
                Write-AtomicJson (Join-Path ([IO.Path]::GetDirectoryName($ContextPath)) 'authentication-evidence.json') $auth
                if($auth.Verified){$verified=$true;break}
                Start-Sleep -Seconds 2
            }
            if(-not $verified){throw 'OriginalAuthenticationNotVerified'}
            $null=Assert-SameClient
        }
        Network {
            $null=Assert-SameClient
            $addresses=@(Get-NetIPAddress -InterfaceIndex (Get-NetAdapter | Where-Object { [guid]$_.InterfaceGuid -eq [guid]$context.Adapter }).ifIndex -AddressFamily IPv4 |
                Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.AddressState -eq 'Preferred' })
            if($addresses.Count -ne 1){throw 'OriginalAddressAmbiguous'}
            $report=Join-Path ([IO.Path]::GetDirectoryName($ContextPath)) 'network-evidence.json'
            $arguments='-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "'+(Join-Path $root 'Test-CampusAuthNetwork.ps1')+'" -ExpectedAddress '+$addresses[0].IPAddress+' -ReportPath "'+$report+'"'
            $child=Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -ArgumentList $arguments -WindowStyle Hidden -PassThru -Wait
            try {if($child.ExitCode -ne 0){throw 'OriginalNetworkNotVerified'}}finally{$child.Dispose()}
            $network=Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
            if(-not $network.Verified -or @($network.Rounds).Count -ne 2){throw 'OriginalNetworkNotVerified'}
            $null=Assert-SameClient
        }
        ResumeMonitor {
            $state=Read-OriginalState
            $control=Get-VerifiedMonitor
            if($null -eq $control -or $state.RunId -eq 'none'){
                if([IO.File]::Exists($pause)){[IO.File]::Delete($pause)}
                break
            }
            if($control.RunId -cne $state.RunId){throw 'ObserverRunChanged'}
            $null=Assert-SameClient
            $released=[DateTimeOffset]::UtcNow
            Assert-OwnedPause
            [IO.File]::Delete($pause)
            try {
                Start-ScheduledTask -TaskName ReInode-Observer -TaskPath '\'
                $verified=$false
                $deadline=[DateTimeOffset]::UtcNow.AddSeconds(45)
                do {
                    Start-Sleep -Milliseconds 500
                    if(Test-FreshMonitor $control $released){$verified=$true;break}
                }while([DateTimeOffset]::UtcNow -lt $deadline)
                if(-not $verified){throw 'ObserverResumeNotVerified'}
            }catch {
                Import-Module (Resolve-PackFile 'replacement\TrialWorkflow.psm1')
                if(-not [IO.File]::Exists($pause)){New-CampusAuthMaintenanceMarker $pause $context.Marker}
                throw
            }
        }
    }
    $result.Ok=$true
}catch{$result.Error=$_.Exception.Message}
Write-AtomicJson (Join-Path ([IO.Path]::GetDirectoryName($ContextPath)) ($Stage+'.json')) $result
if(-not $result.Ok){exit 1}
