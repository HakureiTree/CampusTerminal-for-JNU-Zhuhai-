Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'Runtime.psm1')

function Read-ObserverConfig {
    param([string]$Path)
    $c = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json
    if ($c.Mode -ne 'ObserveOnly') { throw 'Only ObserveOnly mode is implemented.' }
    $null = [guid]::Parse($c.AdapterGuid)
    foreach ($name in @('IntervalSeconds', 'TcpTimeoutMs', 'FailureRounds', 'FailureSeconds',
        'BaselineSeconds', 'ResumeGapSeconds', 'HttpIntervalSeconds', 'HttpTimeoutSeconds',
        'LogMaxBytes', 'LogFiles')) {
        $value = $c.$name
        if ($value -is [string] -or [double]$value -lt 1 -or [double]$value -gt 10000000 -or
            [double]$value -ne [math]::Floor([double]$value)) { throw "Invalid positive integer: $name" }
    }
    if ($c.LogFiles -gt 10 -or $c.TcpTimeoutMs -gt 10000 -or $c.HttpTimeoutSeconds -gt 30) {
        throw 'Timeout or log retention exceeds the allowed limit.'
    }
    $ids = @{}
    foreach ($t in $c.TcpTargets) {
        $ip = [Net.IPAddress]::Parse($t.Address)
        if ($ip.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or
            $t.Port -lt 1 -or $t.Port -gt 65535 -or -not $t.Group -or -not $t.Id -or $ids.ContainsKey($t.Id)) {
            throw 'Invalid or duplicate TCP target.'
        }
        $ids[$t.Id] = $true
    }
    if (@($c.TcpTargets.Group | Select-Object -Unique).Count -lt 2) {
        throw 'At least two independent TCP target groups are required.'
    }
    $ids = @{}
    foreach ($t in $c.HttpTargets) {
        $u = [uri]$t.Url
        if (-not $u.IsAbsoluteUri -or $u.Scheme -ne 'https' -or $u.UserInfo -or $u.Query -or
            $u.Fragment -or $t.Url -match '[\s"\\]' -or -not $t.Id -or $ids.ContainsKey($t.Id)) {
            throw 'HTTP targets must be unique public HTTPS URLs without credentials or query strings.'
        }
        $ids[$t.Id] = $true
    }
    if (@($c.HttpTargets).Count -lt 2) { throw 'At least two HTTP targets are required.' }
    if ($c.Recovery.Mode -notin @('DryRun','GuiRestart')) { throw 'Recovery.Mode must be DryRun or GuiRestart.' }
    if ($c.Recovery.Mode -eq 'GuiRestart' -and $c.Recovery.Controller -ne 'INodeGuiRestart') { throw 'GuiRestart requires the pinned INodeGuiRestart controller.' }
    if ($c.Recovery.Mode -eq 'GuiRestart' -and $c.Recovery.PSObject.Properties['Enabled'] -and $c.Recovery.Enabled -isnot [bool]) { throw 'GuiRestart Enabled must be boolean.' }
    if (-not $c.PolicyWindow.Start) { throw 'Policy start time is required.' }
    foreach ($time in @($c.PolicyWindow.Start, $c.PolicyWindow.End)) {
        if ($null -ne $time -and $time -notmatch '^(?:[01][0-9]|2[0-3]):[0-5][0-9]$') { throw 'Invalid policy time.' }
    }
    $null = [TimeZoneInfo]::FindSystemTimeZoneById($c.PolicyWindow.TimeZone)
    if ($c.Recovery.CooldownSeconds -lt 60 -or $c.Recovery.MaxAttemptsPerDay -lt 1 -or $c.Recovery.MaxAttemptsPerDay -gt 3) { throw 'Invalid recovery rate limits.' }
    return $c
}

function New-ObserverState {
    return [pscustomobject]@{
        Status = 'Starting'; LastSeconds = -1.0; NetworkKey = ''
        SuccessAt = @{}; FailureCount = 0; FailureSince = -1.0
    }
}

function Get-NextObserverState {
    param($Previous, $Sample, $Config, [double]$Seconds)
    # Copy all mutable data: callers can retain previous states for tests and logs.
    $s = New-ObserverState
    $s.NetworkKey = $Sample.NetworkKey
    $s.LastSeconds = $Seconds
    $reset = $Previous.LastSeconds -lt 0 -or $Sample.NetworkKey -ne $Previous.NetworkKey -or
        ($Seconds - $Previous.LastSeconds) -gt $Config.ResumeGapSeconds -or $Seconds -lt $Previous.LastSeconds
    if (-not $reset) {
        foreach ($key in $Previous.SuccessAt.Keys) { $s.SuccessAt[$key] = $Previous.SuccessAt[$key] }
        $s.FailureCount = $Previous.FailureCount
        $s.FailureSince = $Previous.FailureSince
    }
    if ($Sample.Availability -ne 'Ready') {
        $s.Status = $Sample.Availability
        $s.SuccessAt = @{}
        $s.FailureCount = 0
        $s.FailureSince = -1.0
        return $s
    }
    $expected = @($Config.TcpTargets.Id | Sort-Object)
    $actual = @($Sample.Tcp | ForEach-Object { $_.Id } | Sort-Object)
    if (($expected -join '|') -ne ($actual -join '|')) {
        $s.Status = 'Inconclusive'; $s.FailureCount = 0; $s.FailureSince = -1.0
        return $s
    }
    $successful = @($Sample.Tcp | Where-Object { $_.Success })
    foreach ($r in $successful) { $s.SuccessAt[$r.Id] = $Seconds }
    if ($successful.Count -gt 0) {
        $s.Status = if ($successful.Count -eq @($Sample.Tcp).Count) { 'TransportAvailable' } else { 'TransportDegraded' }
        $s.FailureCount = 0
        $s.FailureSince = -1.0
        return $s
    }
    # Local bind/configuration errors are not evidence of an upstream outage.
    if (@($Sample.Tcp | Where-Object { $_.Kind -eq 'LocalError' }).Count -gt 0) {
        $s.Status = 'Inconclusive'; $s.FailureCount = 0; $s.FailureSince = -1.0
        return $s
    }
    $groups = @($Config.TcpTargets | Where-Object {
        $s.SuccessAt.ContainsKey($_.Id) -and ($Seconds - $s.SuccessAt[$_.Id]) -le $Config.BaselineSeconds
    } | ForEach-Object { $_.Group } | Select-Object -Unique)
    if ($groups.Count -lt 2) {
        $s.Status = 'Uncalibrated'; $s.FailureCount = 0; $s.FailureSince = -1.0
        return $s
    }
    if ($s.FailureCount -eq 0) { $s.FailureSince = $Seconds }
    $s.FailureCount++
    $s.Status = 'Suspect'
    if ($s.FailureCount -ge $Config.FailureRounds -and ($Seconds - $s.FailureSince) -ge $Config.FailureSeconds) {
        $s.Status = 'SuspectedOutage'
    }
    return $s
}

function Get-ObserverNetwork {
    param([string]$AdapterGuid)
    $all = @(Get-NetAdapter -ErrorAction Stop)
    # Enumerate once instead of a filtered CIM query that throws on an addressless NIC.
    $ips = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop)
    $allRoutes = @(Get-NetRoute -ErrorAction Stop)
    $routes = @($allRoutes | Where-Object DestinationPrefix -eq '0.0.0.0/0' | Select-Object InterfaceIndex, NextHop, RouteMetric)
    $a = @($all | Where-Object { [guid]$_.InterfaceGuid -eq [guid]$AdapterGuid })
    $index = if ($a.Count -eq 1) { [int]$a[0].ifIndex } else { -1 }
    $addresses = @($ips | Where-Object InterfaceIndex -eq $index |
        Where-Object { $_.AddressState -eq 'Preferred' -and -not $_.SkipAsSource -and $_.IPAddress -notlike '169.254.*' })
    $availability = if ($a.Count -ne 1) { 'AdapterMissing' } elseif (-not $a[0].HardwareInterface) { throw 'Configured adapter is not a hardware interface.' }
        elseif ($a[0].Status -ne 'Up') { 'LinkUnavailable' } elseif ($addresses.Count -ne 1) { 'AddressUnavailable' } else { 'Ready' }
    $address = if ($addresses.Count -eq 1) { $addresses[0].IPAddress } else { '' }
    $other = @($all | Where-Object { $_.ifIndex -ne $index -and $_.Status -eq 'Up' -and
        ($_.HardwareInterface -or $_.InterfaceDescription -match 'RNDIS|Remote NDIS|USB|iPhone|Tether') })
    $backups = @($other | ForEach-Object {
        $adapter = $_
        $ip = @($ips | Where-Object { $_.InterfaceIndex -eq $adapter.ifIndex -and $_.AddressState -eq 'Preferred' -and
            -not $_.SkipAsSource -and $_.IPAddress -notlike '169.254.*' })
        if ($ip.Count -eq 1) { [pscustomobject]@{ Name=$adapter.Name; Description=$adapter.InterfaceDescription; InterfaceIndex=$adapter.ifIndex; Address=$ip[0].IPAddress } }
    })
    $context = [pscustomobject]@{
        InterfaceIndex = $index
        Address = $address
        DefaultRoutes = $routes
        BackupAdapters = $backups
        AlternativeAdapterPresent = ($other.Count -gt 0)
        OtherDefaultRoute = [bool]@($allRoutes | Where-Object { $_.InterfaceIndex -ne $index -and
            $_.DestinationPrefix -in @('0.0.0.0/0','::/0','0.0.0.0/1','128.0.0.0/1','::/1','8000::/1') }).Count
        OtherBroadRoutes = @($allRoutes | Where-Object { $_.InterfaceIndex -ne $index -and
            $_.DestinationPrefix -in @('0.0.0.0/0','::/0','0.0.0.0/1','128.0.0.0/1','::/1','8000::/1') } | ForEach-Object {
                $route = $_
                $owner = @($all | Where-Object ifIndex -eq $route.InterfaceIndex)
                [pscustomobject]@{InterfaceIndex=$route.InterfaceIndex;DestinationPrefix=$route.DestinationPrefix;
                    NextHop=$route.NextHop;RouteMetric=$route.RouteMetric;
                    InterfaceGuid=$(if($owner.Count -eq 1){([guid]$owner[0].InterfaceGuid).ToString('D')}else{''});
                    Name=$(if($owner.Count -eq 1){$owner[0].Name}else{''});
                    Description=$(if($owner.Count -eq 1){$owner[0].InterfaceDescription}else{''});
                    HardwareInterface=$(if($owner.Count -eq 1){[bool]$owner[0].HardwareInterface}else{$null})}
            })
        ActiveVirtualAdapters = @($all | Where-Object { $_.Status -eq 'Up' -and -not $_.HardwareInterface } |
            Select-Object Name, InterfaceDescription, ifIndex)
        INodeRunning = [bool](Get-Process -Name 'iNode Client' -ErrorAction SilentlyContinue)
    }
    $routeKey = ($routes | Sort-Object InterfaceIndex, NextHop | ConvertTo-Json -Compress)
    $backupKey = ($backups | Sort-Object InterfaceIndex | ConvertTo-Json -Compress)
    $otherRouteKey = ($context.OtherBroadRoutes | Sort-Object InterfaceIndex,DestinationPrefix,NextHop | ConvertTo-Json -Compress)
    return [pscustomobject]@{
        Availability = $availability
        NetworkKey = "$AdapterGuid|$($context.Address)|$routeKey|$backupKey|$otherRouteKey"
        Address = $context.Address
        Context = $context
    }
}

function Invoke-BoundTcpProbes {
    param([string]$LocalAddress, [object[]]$Targets, [int]$TimeoutMs)
    $pending = @()
    try {
        foreach ($t in $Targets) {
            $client = $null
            try {
                $client = New-Object Net.Sockets.TcpClient ([Net.IPEndPoint]::new([Net.IPAddress]::Parse($LocalAddress), 0))
                $task = $client.ConnectAsync([string]$t.Address, [int]$t.Port)
                $pending += [pscustomobject]@{ Target = $t; Client = $client; Task = $task; Start = [Diagnostics.Stopwatch]::StartNew() }
            } catch {
                if ($null -ne $client) { $client.Dispose() }
                [pscustomobject]@{ Id = $t.Id; Success = $false; Kind = 'LocalError'; Milliseconds = 0 }
            }
        }
        foreach ($p in $pending) {
            $success = $false
            $kind = 'Timeout'
            try {
                $remaining = [math]::Max(0, $TimeoutMs - [int]$p.Start.ElapsedMilliseconds)
                $success = $p.Task.Wait($remaining) -and $p.Client.Connected
                if ($success) { $kind = 'Connected' }
            } catch {
                $kind = 'ConnectFailed'
                $e = $_.Exception.GetBaseException()
                if ($e -is [Net.Sockets.SocketException] -and $e.SocketErrorCode -in @(
                    'AddressNotAvailable', 'AccessDenied', 'AddressFamilyNotSupported', 'InvalidArgument')) { $kind = 'LocalError' }
            }
            [pscustomobject]@{ Id = $p.Target.Id; Success = $success; Kind = $kind; Milliseconds = [int]$p.Start.ElapsedMilliseconds }
        }
    } finally {
        foreach ($p in $pending) { $p.Client.Dispose() }
    }
}

function Get-HttpProbeSummary {
    param([object[]]$Results)
    $ok = @($Results | Where-Object { $_.Reachable }).Count
    if ($ok -ge 2) { return 'ApplicationReachableViaDefaultRoute' }
    if ($ok -eq 1) { return 'PartialApplicationReachability' }
    return 'ApplicationInconclusive'
}

function Invoke-HttpDiagnostics {
    param([object[]]$Targets, [int]$TimeoutSeconds, [string]$LocalAddress = '')
    $curl = Join-Path $env:SystemRoot 'System32\curl.exe'
    $pending = @()
    try {
        foreach ($t in $Targets) {
            $p = New-Object Diagnostics.Process
            $p.StartInfo = New-Object Diagnostics.ProcessStartInfo
            $p.StartInfo.FileName = $curl
            # -q disables user curl configuration. No credentials, redirects or TLS bypasses.
            $p.StartInfo.Arguments = '-q --noproxy "*" --ipv4 --head --silent --output NUL --connect-timeout {0} --max-time {0} --write-out "%{{http_code}}" "{1}"' -f $TimeoutSeconds, $t.Url
            if ($LocalAddress) {
                $null = [Net.IPAddress]::Parse($LocalAddress)
                $p.StartInfo.Arguments += ' --interface "' + $LocalAddress + '"'
            }
            $p.StartInfo.UseShellExecute = $false
            $p.StartInfo.CreateNoWindow = $true
            $p.StartInfo.RedirectStandardOutput = $true
            $p.StartInfo.RedirectStandardError = $true
            try {
                $null = $p.Start()
                $pending += [pscustomobject]@{ Id = $t.Id; Process = $p; Start = [Diagnostics.Stopwatch]::StartNew() }
            } catch {
                $p.Dispose()
                [pscustomobject]@{ Id = $t.Id; Reachable = $false; HttpCode = 0; ExitCode = -1; Kind = 'ToolUnavailable' }
            }
        }
        foreach ($item in $pending) {
            $p = $item.Process
            $remaining = [math]::Max(0, (($TimeoutSeconds + 2) * 1000) - [int]$item.Start.ElapsedMilliseconds)
            $exited = $p.WaitForExit($remaining)
            $code = 0
            $exitCode = -1
            if (-not $exited) { $p.Kill(); $p.WaitForExit() } else {
                $null = [int]::TryParse($p.StandardOutput.ReadToEnd().Trim(), [ref]$code)
                $exitCode = $p.ExitCode
            }
            # A verified TLS HTTP 5xx response still proves transport reachability.
            $reachable = $exitCode -eq 0 -and $code -ge 200 -and $code -lt 600
            $kind = if ($reachable) { 'TlsHttpResponse' } elseif ($exitCode -in @(35, 60, 77, 80, 82, 83, 90, 91)) {
                'TlsOrCertificateError'
            } elseif ($exitCode -eq 6) { 'DnsError' } elseif (-not $exited) { 'ToolTimeout' } else { 'RequestFailed' }
            [pscustomobject]@{ Id = $item.Id; Reachable = $reachable; HttpCode = $code; ExitCode = $exitCode; Kind = $kind }
        }
    } finally {
        foreach ($item in $pending) {
            try { if (-not $item.Process.HasExited) { $item.Process.Kill(); $item.Process.WaitForExit() } } finally { $item.Process.Dispose() }
        }
    }
}

function Write-ObserverRecord {
    param([string]$Directory, $Record, [long]$MaxBytes, [int]$LogFiles, [string]$RunId = '')
    $null = [IO.Directory]::CreateDirectory($Directory)
    $path = Join-Path $Directory 'observations.jsonl'
    $json = $Record | ConvertTo-Json -Depth 10 -Compress
    $encoding = New-Object Text.UTF8Encoding $false
    $bytes = $encoding.GetByteCount($json + [Environment]::NewLine)
    if ((Test-Path -LiteralPath $path) -and ((Get-Item -LiteralPath $path).Length + $bytes) -gt $MaxBytes) {
        for ($i = $LogFiles - 1; $i -ge 1; $i--) {
            $source = if ($i -eq 1) { $path } else { "$path.$($i - 1)" }
            if (Test-Path -LiteralPath $source) { Move-Item -LiteralPath $source -Destination "$path.$i" -Force }
        }
        if (Test-Path -LiteralPath $path) { [IO.File]::WriteAllText($path, '', $encoding) }
    }
    [IO.File]::AppendAllText($path, $json + [Environment]::NewLine, $encoding)
    if ($RunId) {
        $safeId = [guid]::ParseExact($RunId,'N').ToString('N')
        $archive = Join-Path $Directory "runs\$safeId"
        $null = [IO.Directory]::CreateDirectory($archive)
        [IO.File]::AppendAllText((Join-Path $archive 'observations.jsonl'), $json + [Environment]::NewLine, $encoding)
    }
    Write-AtomicJson (Join-Path $Directory 'latest.json') $Record
}

Export-ModuleMember -Function Read-ObserverConfig, New-ObserverState, Get-NextObserverState,
    Get-ObserverNetwork, Invoke-BoundTcpProbes, Invoke-HttpDiagnostics, Get-HttpProbeSummary, Write-ObserverRecord
