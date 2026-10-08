param([Parameter(Mandatory=$true)][string]$ExpectedAddress,[Parameter(Mandatory=$true)][string]$ReportPath)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'src\Observer.psm1')
$config=Read-ObserverConfig (Join-Path $PSScriptRoot 'config.json')
$expected=[Net.IPAddress]::Parse($ExpectedAddress)
if($expected.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork){throw 'IPv4 required.'}
$result=[ordered]@{Scope='NetworkOnly';StartedUtc=[DateTimeOffset]::UtcNow.ToString('o');FinishedUtc=$null;Verified=$false;ReplacementAuthenticationVerified=$false;Rounds=@();Error=$null}
function Test-ProxyPath {
    $settings=Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
    if(-not $settings.PSObject.Properties['ProxyEnable'] -or $settings.ProxyEnable -ne 1){return [pscustomobject]@{Required=$false;Verified=$true}}
    $proxy=[string]$settings.ProxyServer
    if($proxy.Contains('=')){
        $entries=@{};foreach($entry in $proxy.Split(';')){$pair=$entry.Split('=',2);if($pair.Count -eq 2){$entries[$pair[0].Trim()]=$pair[1].Trim()}}
        if($entries.ContainsKey('https')){$proxy=$entries['https']}elseif($entries.ContainsKey('http')){$proxy=$entries['http']}else{throw 'No HTTP proxy endpoint.'}
    }
    if($proxy -notmatch '^https?://'){$proxy='http://'+$proxy}
    $uri=[uri]$proxy
    if($uri.Scheme -notin @('http','https') -or $uri.UserInfo -or -not $uri.Host){throw 'Unsupported proxy endpoint.'}
    $output=& "$env:SystemRoot\System32\curl.exe" -q --proxy $uri.AbsoluteUri --head --silent --output NUL --connect-timeout 5 --max-time 5 --write-out '%{http_code}' 'https://www.baidu.com/'
    $exitCode=$LASTEXITCODE;$status=0;$null=[int]::TryParse(($output -join '').Trim(),[ref]$status)
    return [pscustomobject]@{Required=$true;Verified=($exitCode -eq 0 -and $status -ge 200 -and $status -lt 600);HttpCode=$status;ExitCode=$exitCode}
}
try {
    $initial=Get-ObserverNetwork $config.AdapterGuid
    for($round=0;$round -lt 2;$round++){
        $before=Get-ObserverNetwork $config.AdapterGuid
        if($before.Availability -ne 'Ready' -or $before.Address -ne $ExpectedAddress -or $before.NetworkKey -ne $initial.NetworkKey){throw 'Campus identity changed or unavailable.'}
        if($before.Context.AlternativeAdapterPresent -or $before.Context.OtherDefaultRoute){throw 'Alternative network path; cannot attribute success to campus.'}
        $tcp=@(Invoke-BoundTcpProbes -LocalAddress $ExpectedAddress -Targets $config.TcpTargets -TimeoutMs $config.TcpTimeoutMs)
        $campus=@(Invoke-HttpDiagnostics -Targets $config.HttpTargets -TimeoutSeconds $config.HttpTimeoutSeconds -LocalAddress $ExpectedAddress)
        $default=@(Invoke-HttpDiagnostics -Targets $config.HttpTargets -TimeoutSeconds $config.HttpTimeoutSeconds)
        $proxy=Test-ProxyPath
        $after=Get-ObserverNetwork $config.AdapterGuid
        $verified=$tcp.Count -eq @($config.TcpTargets).Count -and @($tcp | Where-Object Success).Count -eq $tcp.Count -and @($campus | Where-Object Reachable).Count -ge 2 -and @($default | Where-Object Reachable).Count -ge 2 -and $proxy.Verified -and $after.NetworkKey -eq $initial.NetworkKey -and $after.Availability -eq 'Ready'
        $result.Rounds+=@([pscustomobject]@{Verified=$verified;Tcp=$tcp;CampusHttp=$campus;DefaultHttp=$default;Proxy=$proxy;IdentityStable=($after.NetworkKey -eq $initial.NetworkKey)})
        if(-not $verified){throw 'Connectivity verification failed.'}
        if($round -eq 0){Start-Sleep -Seconds 2}
    }
    $result.Verified=$true
}catch{$result.Error=$_.Exception.Message}
finally{
    $result.FinishedUtc=[DateTimeOffset]::UtcNow.ToString('o')
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
}
if(-not $result.Verified){exit 1}
