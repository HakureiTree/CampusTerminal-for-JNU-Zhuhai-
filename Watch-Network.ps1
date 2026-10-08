[CmdletBinding()]
param(
    [string]$ConfigPath,
    [string]$LogDirectory,
    [string]$StopFile,
    [string]$RunId = '',
    [switch]$Once,
    [ValidateRange(0, 86400)][int]$DurationSeconds = 0
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $ConfigPath) { $ConfigPath = Join-Path $PSScriptRoot 'config.json' }
if (-not $LogDirectory) { $LogDirectory = Join-Path $PSScriptRoot 'logs' }
Import-Module (Join-Path $PSScriptRoot 'src\Runtime.psm1') -Force
$mutex = $null
$owned = $false
$exitReason = 'Completed'
try {
    Write-RuntimeEvent $LogDirectory 'worker-events' 'Started' @{ConfigPath=$ConfigPath}
    Import-Module (Join-Path $PSScriptRoot 'src\Observer.psm1') -Force
    Import-Module (Join-Path $PSScriptRoot 'src\Recovery.psm1') -Force
    Import-Module (Join-Path $PSScriptRoot 'src\INodeController.psm1') -Force
    Import-Module (Join-Path $PSScriptRoot 'src\INodeExecutor.psm1') -Force
    $config = Read-ObserverConfig $ConfigPath
    $mutex = New-Object Threading.Mutex($false, "Local\ReInode-Observer-$($config.AdapterGuid)")
    try { $owned = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $owned = $true }
    if (-not $owned) { throw 'An observer for this adapter is already running in this user session.' }
    $state = New-ObserverState
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $lastHttp = -1.0
    $http = @()
    $campusHttp = @()
    $knownProxies = @()
    if ($config.PSObject.Properties['KnownProxyAdapters']) { $knownProxies = @($config.KnownProxyAdapters) }
    $backupHttp = @{}
    $httpNetworkKey = ''
    $sequence = 0L
    $recoveryStatePath = Join-Path $LogDirectory 'recovery-state.json'
    $recoveryState = Read-RecoveryState $recoveryStatePath ([DateTimeOffset]::UtcNow) $config.PolicyWindow.TimeZone
    $statePersistenceReady = $null -ne $recoveryState
    if ($null -eq $recoveryState) { $recoveryState = New-RecoveryState }
    if ($statePersistenceReady -and $config.Recovery.Mode -eq 'GuiRestart') {
        try { Write-RecoveryState $recoveryStatePath $recoveryState } catch { $statePersistenceReady=$false }
    }
    $controller = $null
    if ($config.Recovery.Mode -eq 'GuiRestart') {
        $controller = [pscustomobject]@{
            Name='INodeGuiRestart'; NormalExit=$true; SupportsSingleRestart=$true
            Reconnect={ param($targetPid) Invoke-INodeRecoveryExecutor -ExpectedProcessId $targetPid -ConfigPath $ConfigPath -LogDirectory $LogDirectory -Progress $executorProgress }
        }
    }
    $graceUntil = 120.0
    $previousRound = 0.0
    do {
        if ($StopFile -and (Test-Path -LiteralPath $StopFile)) { $exitReason = 'StopRequested'; break }
        $roundStart = $timer.Elapsed.TotalSeconds
        if (($roundStart - $previousRound) -gt $config.ResumeGapSeconds) { $graceUntil=$roundStart+120 }
        $previousRound = $roundStart
        $collectorError = $null
        $script:inodeTargetPid = 0
        $controllerResult = $null
        try {
            $network = Get-ObserverNetwork $config.AdapterGuid
            $tcp = @()
            if ($network.Availability -eq 'Ready') {
                $tcp = @(Invoke-BoundTcpProbes $network.Address $config.TcpTargets $config.TcpTimeoutMs)
            }
        } catch {
            $collectorError = $_.Exception.ToString()
            $network = [pscustomobject]@{ Availability = 'CollectorError'; NetworkKey = ''; Context = $null }
            $tcp = @()
        }
        $sample = [pscustomobject]@{ Availability = $network.Availability; NetworkKey = $network.NetworkKey; Tcp = $tcp }
        $next = Get-NextObserverState $state $sample $config $timer.Elapsed.TotalSeconds
        $changed = $next.Status -ne $state.Status
        $previousStatus = $state.Status
        $state = $next
        $httpFresh = $false
        if ($httpNetworkKey -ne $network.NetworkKey) { $lastHttp=-1; $http=@(); $campusHttp=@(); $backupHttp=@{}; $httpNetworkKey=$network.NetworkKey; $graceUntil=$roundStart+120 }
        if (Test-ApplicationProbeDue $state.Status $previousStatus $timer.Elapsed.TotalSeconds $lastHttp $config.HttpIntervalSeconds) {
            $lastHttp = $timer.Elapsed.TotalSeconds
            $http = @(Invoke-HttpDiagnostics $config.HttpTargets $config.HttpTimeoutSeconds)
            $campusHttp = @()
            if ($network.Availability -eq 'Ready') {
                $campusHttp = @(Invoke-HttpDiagnostics $config.HttpTargets $config.HttpTimeoutSeconds $network.Address)
            }
            $httpFresh = $true
        }
        $backups = @()
        if ($null -ne $network.Context) {
            foreach ($adapter in @($network.Context.BackupAdapters | Select-Object -First 2)) {
                $bTcp = @(Invoke-BoundTcpProbes $adapter.Address $config.TcpTargets $config.TcpTimeoutMs)
                $key = "$($adapter.InterfaceIndex)|$($adapter.Address)"
                if ($httpFresh -or -not $backupHttp.ContainsKey($key)) {
                    $bHttp = @(Invoke-HttpDiagnostics $config.HttpTargets $config.HttpTimeoutSeconds $adapter.Address)
                    $backupHttp[$key] = @{Results=$bHttp;At=$timer.Elapsed.TotalSeconds}
                }
                $bAge = [math]::Round($timer.Elapsed.TotalSeconds-$backupHttp[$key].At,1)
                $backups += [pscustomobject]@{Adapter=$adapter;Tcp=$bTcp;Http=$backupHttp[$key].Results;HttpAgeSeconds=$bAge;
                    Application=(Get-ApplicationEvidence $backupHttp[$key].Results $bAge)}
            }
        }
        $age = if ($lastHttp -lt 0) { $null } else { [math]::Round($timer.Elapsed.TotalSeconds-$lastHttp,1) }
        $application = Get-ApplicationEvidence $http $age
        $campusApplication = Get-ApplicationEvidence $campusHttp $age 30
        $routeAssessment = Get-RecoveryRouteAssessment $network.Context $knownProxies
        $controllerReady = $true
        if ($config.Recovery.Mode -eq 'GuiRestart') {
            $controllerReady = Test-INodeClientBinary
            if ($controllerReady -and $null -ne $network.Context -and $network.Context.INodeRunning) {
                try {
                    $client = Get-INodeClientProcess
                    if ($null -ne $client -and $client.PathState -eq 'Verified' -and (Test-INodeProcessInteraction $client) -and (Test-INodeDesktopReady)) { $script:inodeTargetPid = $client.ProcessId }
                    else { $controllerReady=$false }
                } catch { $controllerReady=$false }
            }
        }
        if ($state.Status -eq 'TransportAvailable' -and $application.Fresh -and $application.ReachableCount -ge 2 -and ($recoveryState.IncidentAttempted -or $recoveryState.CircuitOpen)) {
            $recoveryState = Reset-RecoveryIncident $recoveryState
            if ($statePersistenceReady -and $config.Recovery.Mode -eq 'GuiRestart') {
                try { Write-RecoveryState $recoveryStatePath $recoveryState } catch { $statePersistenceReady=$false }
            }
        }
        $policyBlocked = Test-PolicyWindow $config.PolicyWindow ([DateTimeOffset]::UtcNow)
        $localDate=[TimeZoneInfo]::ConvertTime([DateTimeOffset]::UtcNow,[TimeZoneInfo]::FindSystemTimeZoneById($config.PolicyWindow.TimeZone)).ToString('yyyy-MM-dd')
        if($recoveryState.AttemptDate -ne $localDate) {
            $recoveryState.AttemptDate=$localDate; $recoveryState.AttemptsToday=0
            if($config.Recovery.Mode -eq 'GuiRestart' -and $statePersistenceReady) {
                try { Write-RecoveryState $recoveryStatePath $recoveryState } catch { $statePersistenceReady=$false }
            }
        }
        $evidence = [pscustomobject]@{
            Paused=(Test-Path (Join-Path $LogDirectory 'pause-recovery.signal'));PolicyBlocked=$policyBlocked
            Warmup=($timer.Elapsed.TotalSeconds -lt $graceUntil);CampusAvailability=$network.Availability;CampusStatus=$state.Status
            BackupPresent=($null -ne $network.Context -and $network.Context.AlternativeAdapterPresent)
            OtherDefaultRoute=$routeAssessment.Blocked
            ReplacementRunning=[bool](Get-Process -Name 'CampusTerminal.Core' -ErrorAction SilentlyContinue)
            INodeRunning=($null -ne $network.Context -and $network.Context.INodeRunning)
            HttpFresh=($application.Fresh -and $campusApplication.Fresh)
            HttpReachableCount=($application.ReachableCount + $campusApplication.ReachableCount)
            HttpOnlyTransportFailures=($http.Count -ge 2 -and $campusHttp.Count -ge 2 -and
                @(@($http) + @($campusHttp) | Where-Object { $_.ExitCode -notin @(7,28) }).Count -eq 0)
            PersistenceReady=$statePersistenceReady;ControllerReady=$controllerReady
            TargetProcessId=$script:inodeTargetPid
        }
        $decision = Get-RecoveryDecision $evidence $config.Recovery $recoveryState ([DateTimeOffset]::UtcNow)
        $action = 'None'
        $recoveryResult = $null
        if ($decision.Eligible -and $config.Recovery.Mode -eq 'GuiRestart' -and $statePersistenceReady -and $null -ne $controller) {
            $readEvidence = {
                $fresh = $evidence.PSObject.Copy()
                $fresh.Paused=Test-Path (Join-Path $LogDirectory 'pause-recovery.signal')
                $fresh.ReplacementRunning=[bool](Get-Process -Name 'CampusTerminal.Core' -ErrorAction SilentlyContinue)
                $fresh.PolicyBlocked=Test-PolicyWindow $config.PolicyWindow ([DateTimeOffset]::UtcNow)
                try {
                    $check=Get-ObserverNetwork $config.AdapterGuid
                    $fresh.CampusAvailability=$check.Availability
                    $fresh.Warmup=$fresh.Warmup -or $check.NetworkKey -ne $network.NetworkKey
                    $fresh.BackupPresent=$check.Context.AlternativeAdapterPresent
                    $fresh.OtherDefaultRoute=(Get-RecoveryRouteAssessment $check.Context $knownProxies).Blocked
                    $client=Get-INodeClientProcess
                    $fresh.ControllerReady=$null -ne $client -and $client.PathState -eq 'Verified' -and $client.ProcessId -eq $fresh.TargetProcessId -and (Test-INodeProcessInteraction $client) -and (Test-INodeDesktopReady)
                    if($check.Availability -eq 'Ready') {
                        $probes=@(Invoke-BoundTcpProbes $check.Address $config.TcpTargets $config.TcpTimeoutMs)
                        if(@($probes | Where-Object Success).Count -gt 0){$fresh.CampusStatus='TransportAvailable'}
                        if(@($probes | Where-Object Kind -eq 'LocalError').Count -gt 0){$fresh.CampusStatus='Inconclusive'}
                    }
                } catch { $fresh.ControllerReady=$false }
                return $fresh
            }.GetNewClosure()
            $persistState = { param($next) Write-RecoveryState $recoveryStatePath $next }.GetNewClosure()
            $progressCounter=[pscustomobject]@{Sequence=$sequence}
            $executorProgress={
                $progressCounter.Sequence++
                Write-AtomicJson (Join-Path $LogDirectory 'heartbeat.json') @{ProcessId=$PID;RunId=$RunId;
                    Sequence=$progressCounter.Sequence;TimestampUtc=[DateTimeOffset]::UtcNow.ToString('o');Activity='RecoveryExecutor'}
            }.GetNewClosure()
            $verifyRecovery = { param($result) return $result.Accepted -and $result.Verified }
            $recoveryResult = Invoke-LiveRecovery $controller $readEvidence $persistState $verifyRecovery $config.Recovery $recoveryState ([DateTimeOffset]::UtcNow)
            $sequence=$progressCounter.Sequence
            $recoveryState = $recoveryResult.State
            $action = $recoveryResult.Result
            if ($recoveryResult.Result -eq 'PersistenceFailure') { $statePersistenceReady=$false }
            if ($recoveryResult.PSObject.Properties['Controller']) { $controllerResult=$recoveryResult.Controller } else { $controllerResult=$null }
            if ($recoveryResult.Result -in @('GuiRestartVerified','GuiRestartUnverifiedCircuitOpen','GuiRestartFailedCircuitOpen')) { $decision.Executed=$true }
        }
        $sequence++
        $record = [pscustomobject]@{
            SchemaVersion = 3; ObserverVersion='2026-09-16-menu-recovery-v2'; ControllerVersion='2026-09-16-menu-recovery-v2'; TimestampUtc = [DateTimeOffset]::UtcNow.ToString('o'); Mode = 'ObserveOnly'; ProcessId = $PID; RunId=$RunId; Sequence=$sequence
            Status = $state.Status; StateChanged = $changed; FailureCount = $state.FailureCount
            Network = $network.Context; CollectorError = $collectorError; Tcp = $tcp
            Http = $http; HttpFresh = $httpFresh
            HttpAgeSeconds = $age
            HttpSummary = $application.Summary
            CampusHttp=$campusHttp;CampusHttpSummary=$campusApplication.Summary;RouteAssessment=$routeAssessment
            Backups=$backups; PolicyExcluded=$policyBlocked; Recovery=$decision; RecoveryResult=$recoveryResult
            ControllerResult=$controllerResult
            ControllerReady=$controllerReady;RecoveryGraceRemainingSeconds=[math]::Max(0,($graceUntil-$timer.Elapsed.TotalSeconds))
            Action = $action
        }
        Write-ObserverRecord $LogDirectory $record $config.LogMaxBytes $config.LogFiles $RunId
        Write-AtomicJson (Join-Path $LogDirectory 'heartbeat.json') @{ProcessId=$PID;RunId=$RunId;Sequence=$sequence;TimestampUtc=$record.TimestampUtc}
        if ($Once -or $changed) { $record | ConvertTo-Json -Depth 10 -Compress | Write-Output }
        if ($Once -or ($DurationSeconds -gt 0 -and $timer.Elapsed.TotalSeconds -ge $DurationSeconds)) { break }
        $sleep = [math]::Max(0, $config.IntervalSeconds - ($timer.Elapsed.TotalSeconds - $roundStart))
        if ($DurationSeconds -gt 0) { $sleep = [math]::Min($sleep, [math]::Max(0, $DurationSeconds - $timer.Elapsed.TotalSeconds)) }
        if ($sleep -gt 0) { Start-Sleep -Milliseconds ([int]($sleep * 1000)) }
    } while ($DurationSeconds -eq 0 -or $timer.Elapsed.TotalSeconds -lt $DurationSeconds)
} catch {
    $exitReason = 'UnhandledError'
    try { Write-RuntimeEvent $LogDirectory 'worker-events' 'UnhandledError' @{
        Message=$_.Exception.ToString(); Position=$_.InvocationInfo.PositionMessage; Stack=$_.ScriptStackTrace
    } } catch { [Console]::Error.WriteLine($_.Exception.ToString()) }
    throw
} finally {
    if ($owned) { $mutex.ReleaseMutex() }
    if ($null -ne $mutex) { $mutex.Dispose() }
    try { Write-RuntimeEvent $LogDirectory 'worker-events' 'Exiting' @{Reason=$exitReason} } catch { [Console]::Error.WriteLine($_.Exception.ToString()) }
}
