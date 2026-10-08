Set-StrictMode -Version Latest
function Test-INodeVerificationRound {
    param($Round)
    return $Round.Availability -eq 'Ready' -and -not $Round.AlternativeRoute -and
        $Round.ExpectedTcpCount -ge 2 -and @($Round.Tcp).Count -eq $Round.ExpectedTcpCount -and
        @($Round.Tcp | Where-Object Success).Count -eq $Round.ExpectedTcpCount -and
        @($Round.CampusHttp | Where-Object Reachable).Count -ge 2 -and
        @($Round.DefaultHttp | Where-Object Reachable).Count -ge 2 -and $Round.ClientMatches
}
function Test-INodeVerificationResult {
    param([bool]$AuthenticationVerified,[object[]]$Rounds)
    if(-not $AuthenticationVerified -or $Rounds.Count -lt 2){return $false}
    return (Test-INodeVerificationRound $Rounds[-1]) -and (Test-INodeVerificationRound $Rounds[-2]) -and
        $Rounds[-1].NetworkKey -eq $Rounds[-2].NetworkKey
}
function Invoke-INodeNetworkVerification {
    param($Config,$ClientResult,[scriptblock]$RecordStage)
    $rounds=@();$known=@()
    if($Config.PSObject.Properties['KnownProxyAdapters']){$known=@($Config.KnownProxyAdapters)}
    for($i=0;$i -lt 3;$i++){
        Start-Sleep -Seconds 5
        $network=Get-ObserverNetwork $Config.AdapterGuid
        $round=[pscustomobject]@{Availability=$network.Availability;NetworkKey=$network.NetworkKey;
            AlternativeRoute=$true;ExpectedTcpCount=@($Config.TcpTargets).Count;Tcp=@();CampusHttp=@();DefaultHttp=@();ClientMatches=$false}
        if($network.Availability -eq 'Ready'){
            $round.AlternativeRoute=$network.Context.AlternativeAdapterPresent -or (Get-RecoveryRouteAssessment $network.Context $known).Blocked
            $round.Tcp=@(Invoke-BoundTcpProbes $network.Address $Config.TcpTargets $Config.TcpTimeoutMs)
            $round.CampusHttp=@(Invoke-HttpDiagnostics $Config.HttpTargets $Config.HttpTimeoutSeconds $network.Address)
            $round.DefaultHttp=@(Invoke-HttpDiagnostics $Config.HttpTargets $Config.HttpTimeoutSeconds)
            $client=Get-INodeClientProcess
            $after=Get-ObserverNetwork $Config.AdapterGuid
            $round.ClientMatches=$null -ne $client -and $client.PathState -eq 'Verified' -and $client.ProcessId -eq $ClientResult.ObservedProcessId
            $round.AlternativeRoute=$round.AlternativeRoute -or $after.Availability -ne 'Ready' -or $after.NetworkKey -ne $network.NetworkKey -or
                $after.Context.AlternativeAdapterPresent -or (Get-RecoveryRouteAssessment $after.Context $known).Blocked
        }
        $rounds+=,$round
        & $RecordStage 'NetworkRound' $round
        if(Test-INodeVerificationResult $ClientResult.AuthenticationVerified $rounds){break}
    }
    [pscustomobject]@{Verified=(Test-INodeVerificationResult $ClientResult.AuthenticationVerified $rounds);Rounds=$rounds}
}
Export-ModuleMember -Function Test-INodeVerificationRound,Test-INodeVerificationResult,Invoke-INodeNetworkVerification
