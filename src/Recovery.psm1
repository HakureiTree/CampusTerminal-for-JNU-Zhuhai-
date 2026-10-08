Set-StrictMode -Version Latest

function Test-PolicyWindow {
    param($Window, [DateTimeOffset]$Now)
    if (-not $Window.End) { return $true }
    $local = [TimeZoneInfo]::ConvertTime($Now, [TimeZoneInfo]::FindSystemTimeZoneById($Window.TimeZone))
    $time = $local.TimeOfDay
    $start = [TimeSpan]::Parse($Window.Start)
    $end = [TimeSpan]::Parse($Window.End)
    if ($start -eq $end) { return $true }
    if ($start -lt $end) { return $time -ge $start -and $time -lt $end }
    return $time -ge $start -or $time -lt $end
}

function Get-RecoveryDecision {
    param($Evidence, $Limits, $State, [DateTimeOffset]$Now)
    $mode = if ($Limits.PSObject.Properties['Mode']) { [string]$Limits.Mode } else { 'DryRun' }
    $reason = if ($Evidence.Paused) { 'Paused' }
        elseif ($Evidence.PSObject.Properties['ReplacementRunning'] -and $Evidence.ReplacementRunning) { 'ReplacementClientPresent' }
        elseif ($mode -eq 'GuiRestart' -and (-not $Limits.PSObject.Properties['Enabled'] -or -not $Limits.Enabled)) { 'RecoveryDisabled' }
        elseif ($Evidence.PolicyBlocked) { 'PolicyWindow' }
        elseif ($Evidence.Warmup) { 'StartupOrResumeGrace' }
        elseif ($Evidence.PSObject.Properties['PersistenceReady'] -and -not $Evidence.PersistenceReady) { 'SafetyStateUnavailable' }
        elseif ($Evidence.PSObject.Properties['ControllerReady'] -and -not $Evidence.ControllerReady) { 'ControllerUnavailable' }
        elseif ($Evidence.BackupPresent -or $Evidence.OtherDefaultRoute) { 'AlternativeNetworkPresent' }
        elseif ($Evidence.CampusAvailability -ne 'Ready') { 'CampusInterfaceUnavailable' }
        elseif (-not $Evidence.INodeRunning) { 'ClientNotRunning' }
        elseif ($Evidence.CampusStatus -ne 'SuspectedOutage') { 'NoSustainedCampusFailure' }
        elseif (-not $Evidence.HttpFresh) { 'StaleApplicationEvidence' }
        elseif ($Evidence.HttpReachableCount -gt 0) { 'ApplicationStillReachable' }
        elseif (-not $Evidence.HttpOnlyTransportFailures) { 'DnsTlsOrToolFailure' }
        elseif ($State.CircuitOpen) { 'CircuitOpen' }
        elseif ($State.IncidentAttempted) { 'AlreadyAttemptedThisIncident' }
        elseif ($State.AttemptsToday -ge $Limits.MaxAttemptsPerDay) { 'DailyLimit' }
        elseif ($State.LastAttemptUtc -and ($Now - [DateTimeOffset]$State.LastAttemptUtc).TotalSeconds -lt $Limits.CooldownSeconds) { 'Cooldown' }
        else { 'WouldRequestReconnect' }
    return [pscustomobject]@{ Decision=$reason; Eligible=($reason -eq 'WouldRequestReconnect'); Executed=$false; Mode=$mode; LiveControllerAvailable=($mode -eq 'GuiRestart') }
}

function New-RecoveryState {
    return [pscustomobject]@{ SchemaVersion=1; AttemptDate=''; CircuitOpen=$false; IncidentAttempted=$false; AttemptsToday=0; LastAttemptUtc=$null }
}

function Read-RecoveryState {
    param([string]$Path, [DateTimeOffset]$Now, [string]$TimeZone = 'China Standard Time')
    $state = New-RecoveryState
    if (Test-Path -LiteralPath $Path) {
        try {
            $saved = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach($required in @('SchemaVersion','CircuitOpen','IncidentAttempted','AttemptsToday','LastAttemptUtc','AttemptDate')) {
                if(-not $saved.PSObject.Properties[$required]) { return $null }
            }
            if($saved.SchemaVersion -ne 1 -or $saved.CircuitOpen -isnot [bool] -or $saved.IncidentAttempted -isnot [bool] -or
                $saved.AttemptsToday -is [string] -or $saved.AttemptsToday -lt 0 -or $saved.AttemptsToday -gt 3 -or
                $saved.AttemptDate -notmatch '^\d{4}-\d{2}-\d{2}$') { return $null }
            if($saved.LastAttemptUtc) { $null=[DateTimeOffset]::Parse($saved.LastAttemptUtc) }
            foreach ($name in @('CircuitOpen','IncidentAttempted','AttemptsToday','LastAttemptUtc','AttemptDate')) {
                if ($saved.PSObject.Properties[$name]) { $state.$name = $saved.$name }
            }
        } catch { return $null }
    }
    try { $localDate = [TimeZoneInfo]::ConvertTime($Now,[TimeZoneInfo]::FindSystemTimeZoneById($TimeZone)).ToString('yyyy-MM-dd') } catch { return $null }
    if ($state.AttemptDate -ne $localDate) { $state.AttemptDate=$localDate; $state.AttemptsToday=0 }
    return $state
}

function Write-RecoveryState {
    param([string]$Path, $State)
    if ($null -eq $State) { throw 'Recovery state is null.' }
    Write-AtomicJson $Path $State
}

function Reset-RecoveryIncident {
    param($State)
    $next = New-RecoveryState
    $next.AttemptDate=$State.AttemptDate; $next.AttemptsToday=$State.AttemptsToday; $next.LastAttemptUtc=$State.LastAttemptUtc
    return $next
}

function Invoke-SimulatedRecovery {
    param($Controller, [scriptblock]$ReadEvidence, $Limits, $State, [DateTimeOffset]$Now)
    # No production driver is provided. Only an explicitly simulated controller is accepted.
    if (-not $Controller.SimulationOnly -or -not $Controller.SupportsAtomicReconnect) {
        throw 'Only atomic simulated controllers are supported. Live iNode control is not implemented.'
    }
    $evidence = & $ReadEvidence
    $decision = Get-RecoveryDecision $evidence $Limits $State $Now
    if (-not $decision.Eligible) { return [pscustomobject]@{Decision=$decision;State=$State;Result='Suppressed'} }
    $next = New-RecoveryState
    $next.IncidentAttempted=$true; $next.AttemptsToday=$State.AttemptsToday+1; $next.LastAttemptUtc=$Now.ToString('o')
    # Recheck immediately before acting to cover route changes while deciding.
    $decision = Get-RecoveryDecision (& $ReadEvidence) $Limits $State $Now
    if (-not $decision.Eligible) { return [pscustomobject]@{Decision=$decision;State=$State;Result='SuppressedAfterRecheck'} }
    try {
        $accepted = & $Controller.Reconnect
        $healthy = $accepted -and (& $Controller.CheckNetwork)
        $next.CircuitOpen = -not $healthy
        $result = if ($healthy) { 'SimulatedRecoveryVerified' } else { 'SimulatedFailureCircuitOpen' }
    } catch { $next.CircuitOpen=$true; $result='SimulatedFailureCircuitOpen' }
    return [pscustomobject]@{Decision=$decision;State=$next;Result=$result}
}

function Invoke-LiveRecovery {
    param($Controller, [scriptblock]$ReadEvidence, [scriptblock]$PersistState, [scriptblock]$VerifyRecovery,
        $Limits, $State, [DateTimeOffset]$Now)
    if ($Limits.Mode -ne 'GuiRestart' -or $Controller.Name -ne 'INodeGuiRestart' -or
        -not $Controller.NormalExit -or -not $Controller.SupportsSingleRestart) {
        throw 'Only the normal-exit iNode recovery controller is supported.'
    }
    $evidence = & $ReadEvidence
    $decision = Get-RecoveryDecision $evidence $Limits $State $Now
    if (-not $decision.Eligible) { return [pscustomobject]@{Decision=$decision;State=$State;Result='Suppressed'} }
    $next = New-RecoveryState
    $next.AttemptDate=$State.AttemptDate; $next.IncidentAttempted=$true
    $next.AttemptsToday=[int]$State.AttemptsToday+1; $next.LastAttemptUtc=$Now.ToString('o')
    # Persist the circuit and attempt budget before dispatching the process action.
    try { & $PersistState $next }
    catch { return [pscustomobject]@{Decision=[pscustomobject]@{Decision='SafetyStateUnavailable';Eligible=$false;Executed=$false;Mode=$Limits.Mode;LiveControllerAvailable=$true};State=$next;Result='PersistenceFailure'} }
    $decision = Get-RecoveryDecision (& $ReadEvidence) $Limits $State $Now
    if (-not $decision.Eligible) { return [pscustomobject]@{Decision=$decision;State=$next;Result='SuppressedAfterRecheck'} }
    try {
        $controllerResult = & $Controller.Reconnect $evidence.TargetProcessId
        $healthy = & $VerifyRecovery $controllerResult
        $next.CircuitOpen = -not $healthy
        & $PersistState $next
        $result = if ($healthy) { 'GuiRestartVerified' } else { 'GuiRestartUnverifiedCircuitOpen' }
        return [pscustomobject]@{Decision=$decision;State=$next;Result=$result;Controller=$controllerResult}
    } catch {
        $next.CircuitOpen=$true
        try { & $PersistState $next } catch { }
        return [pscustomobject]@{Decision=$decision;State=$next;Result='GuiRestartFailedCircuitOpen';Error=$_.Exception.Message}
    }
}

function Get-ApplicationEvidence {
    param([object[]]$Results, $AgeSeconds, [int]$MaxAgeSeconds = 90)
    $fresh = $null -ne $AgeSeconds -and $AgeSeconds -ge 0 -and $AgeSeconds -le $MaxAgeSeconds -and $Results.Count -gt 0
    $reachable = @($Results | Where-Object Reachable).Count
    $summary = if (-not $fresh) { 'NotMeasuredOrStale' } elseif ($reachable -ge 2) { 'ApplicationReachable' }
        elseif ($reachable -eq 1) { 'PartialApplicationReachability' } else { 'ApplicationInconclusive' }
    return [pscustomobject]@{Summary=$summary;Fresh=$fresh;ReachableCount=$(if($fresh){$reachable}else{0})}
}

function Test-ApplicationProbeDue {
    param([string]$Status, [string]$PreviousStatus, [double]$Seconds, [double]$LastProbeSeconds, [int]$IntervalSeconds)
    if ($LastProbeSeconds -lt 0 -or $Seconds -lt $LastProbeSeconds) { return $true }
    $failing = $Status -in @('Suspect','SuspectedOutage')
    if ($failing -and $PreviousStatus -notin @('Suspect','SuspectedOutage')) { return $true }
    $interval = if ($failing) { [math]::Min(10,$IntervalSeconds) } else { $IntervalSeconds }
    return ($Seconds - $LastProbeSeconds) -ge $interval
}

function Get-RecoveryRouteAssessment {
    param($Context, [object[]]$KnownProxyAdapters = @())
    # Unknown topology remains blocking; a proxy identity is not an Internet backup.
    if ($null -eq $Context -or -not $Context.PSObject.Properties['OtherBroadRoutes']) {
        return [pscustomobject]@{Blocked=$true;KnownProxyRoutes=0;UnknownRoutes=0;Reason='UnknownTopology'}
    }
    $known = 0; $unknown = 0
    foreach ($route in @($Context.OtherBroadRoutes)) {
        $match = @($KnownProxyAdapters | Where-Object {
            $route.InterfaceGuid -and $_.InterfaceGuid -eq $route.InterfaceGuid -and
            $_.Name -ceq $route.Name -and $_.Description -ceq $route.Description -and
            $route.HardwareInterface -eq $false
        })
        if ($match.Count -eq 1) { $known++ } else { $unknown++ }
    }
    return [pscustomobject]@{Blocked=($unknown -gt 0);KnownProxyRoutes=$known;UnknownRoutes=$unknown;
        Reason=$(if($unknown -gt 0){'UnknownOrBackupRoute'}elseif($known -gt 0){'KnownProxyOnly'}else{'CampusOnly'})}
}
Export-ModuleMember -Function Test-PolicyWindow, Get-RecoveryDecision, New-RecoveryState, Invoke-SimulatedRecovery, Get-ApplicationEvidence,
    Test-ApplicationProbeDue, Get-RecoveryRouteAssessment, Read-RecoveryState, Write-RecoveryState,
    Reset-RecoveryIncident, Invoke-LiveRecovery
