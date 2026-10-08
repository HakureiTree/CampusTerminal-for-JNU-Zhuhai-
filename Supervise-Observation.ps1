[CmdletBinding()]
param([Parameter(Mandatory)][string]$RunId)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$directory = Join-Path $PSScriptRoot 'logs'
Import-Module (Join-Path $PSScriptRoot 'src\Runtime.psm1') -Force
$runId = [guid]::ParseExact($RunId, 'N').ToString('N')
$control = Get-Content (Join-Path $directory 'control.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($control.RunId -ne $runId) { throw 'Run identity mismatch.' }
$stopFile = Join-Path $directory "stop-$runId.signal"
$persistent = $control.PSObject.Properties['Persistent'] -and $control.Persistent
$expires = if ($persistent) { [DateTimeOffset]::MaxValue } else { [DateTimeOffset]$control.ExpiresUtc }
$worker = $null
$errorRead = $null
$progressClock = [Diagnostics.Stopwatch]::StartNew()
$progress = [pscustomobject]@{Sequence=-1L;ChangedAt=0.0}
$lastTick = 0.0
$readErrors = 0
$owned = $false
$mutex = [Threading.Mutex]::new($false, 'Local\ReInode-Supervisor-' + $runId)
try {
    try { $owned = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $owned = $true }
    if (-not $owned) { return }
    Write-RuntimeEvent $directory 'supervisor-events' 'SupervisorStarted' @{RunId=$runId}
    $config = Get-Content (Join-Path $PSScriptRoot 'config.json') -Raw | ConvertFrom-Json
    $limit = [math]::Max(90, 3 * ($config.IntervalSeconds + $config.HttpTimeoutSeconds + 2))
    $restarts = 0
    while ([DateTimeOffset]::UtcNow -lt $expires -and -not (Test-Path -LiteralPath $stopFile)) {
        # Reattach orphan workers only after matching PID, creation time and command line.
        if ($null -eq $worker -and (Test-Path (Join-Path $directory 'worker.json'))) {
            $identity = Get-Content (Join-Path $directory 'worker.json') -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($identity.RunId -eq $runId) {
                $candidate = Get-Process -Id $identity.ProcessId -ErrorAction SilentlyContinue
                if ($candidate -and ([DateTimeOffset]$candidate.StartTime.ToUniversalTime()) -eq ([DateTimeOffset]$identity.StartedUtc)) {
                    $info = Get-CimInstance Win32_Process -Filter "ProcessId = $($candidate.Id)" -ErrorAction Stop
                    if ($info.CommandLine -and $info.CommandLine.Contains($stopFile) -and
                        $info.CommandLine.Contains((Join-Path $PSScriptRoot 'Watch-Network.ps1'))) {
                        $worker = $candidate
                        $null = $worker.Handle
                        $progressClock.Restart(); $progress=[pscustomobject]@{Sequence=-1L;ChangedAt=0.0}; $lastTick=0.0
                        Write-RuntimeEvent $directory 'supervisor-events' 'WorkerReattached' @{WorkerId=$worker.Id}
                    }
                }
            }
        }
        if ($null -eq $worker) {
            $remaining = if ($persistent) { 86400 } else { [math]::Max(1, [int]($expires - [DateTimeOffset]::UtcNow).TotalSeconds) }
            $arguments = '-NoProfile -NonInteractive -File "{0}" -DurationSeconds {1} -StopFile "{2}" -RunId {3}' -f (Join-Path $PSScriptRoot 'Watch-Network.ps1'), $remaining, $stopFile, $runId
            $startInfo = [Diagnostics.ProcessStartInfo]::new()
            $startInfo.FileName = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
            $startInfo.Arguments = $arguments
            $startInfo.UseShellExecute = $false
            $startInfo.CreateNoWindow = $true
            $startInfo.RedirectStandardError = $true
            $worker = [Diagnostics.Process]::Start($startInfo)
            $errorRead = $worker.StandardError.ReadToEndAsync()
            $null = $worker.Handle
            $identity = [ordered]@{RunId=$runId;ProcessId=$worker.Id;StartedUtc=$worker.StartTime.ToUniversalTime().ToString('o')}
            [IO.File]::WriteAllText((Join-Path $directory 'worker.json'), ($identity | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
            Write-RuntimeEvent $directory 'supervisor-events' 'WorkerStarted' @{WorkerId=$worker.Id;Restarts=$restarts}
            $progressClock.Restart(); $progress=[pscustomobject]@{Sequence=-1L;ChangedAt=0.0}; $lastTick=0.0
        }
        $seconds = $progressClock.Elapsed.TotalSeconds
        if (($seconds - $lastTick) -gt 30) {
            Write-RuntimeEvent $directory 'supervisor-events' 'SupervisorSchedulingGap' @{Seconds=($seconds-$lastTick)}
            $progress.ChangedAt=$seconds
        }
        $lastTick=$seconds
        try {
            $heartbeat = Get-Content (Join-Path $directory 'heartbeat.json') -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json
            $valid = $heartbeat.ProcessId -eq $worker.Id -and $heartbeat.RunId -eq $runId
            $progress = Get-NextProgress $progress $heartbeat.Sequence $seconds $valid
            $readErrors=0
        } catch {
            $readErrors++
            if ($readErrors -eq 1 -or $readErrors % 30 -eq 0) {
                Write-RuntimeEvent $directory 'supervisor-events' 'HeartbeatReadError' @{Consecutive=$readErrors;Message=$_.Exception.Message}
            }
        }
        $age = $seconds - $progress.ChangedAt
        $health = Get-WorkerHealth $worker.HasExited $age $limit
        Write-AtomicJson (Join-Path $directory 'supervisor-heartbeat.json') @{RunId=$runId;ProcessId=$PID;WorkerId=$worker.Id;TimestampUtc=[DateTimeOffset]::UtcNow.ToString('o');ProgressAgeSeconds=$age;WorkerHealth=$health;ReadErrors=$readErrors}
        if ($health -ne 'Running') {
            if ($health -eq 'Stalled') { $worker.Kill(); $worker.WaitForExit() }
            $worker.WaitForExit()
            $stderr = 'Unavailable for reattached worker; consult worker-events.jsonl.'
            if ($null -ne $errorRead -and $errorRead.Wait(2000)) {
                $stderr = $errorRead.GetAwaiter().GetResult()
                if ($stderr.Length -gt 8192) { $stderr = $stderr.Substring(0,8192) }
                [IO.File]::WriteAllText((Join-Path $directory 'worker-stderr.txt'), $stderr, [Text.UTF8Encoding]::new($false))
            }
            Write-RuntimeEvent $directory 'supervisor-events' $health @{WorkerId=$worker.Id;ExitCode=$worker.ExitCode;SampleAgeSeconds=$age;StandardError=$stderr}
            $worker.Dispose(); $worker = $null; $errorRead = $null; $restarts++
            $delay = [math]::Min(60, 5 * $restarts)
            for ($i=0; $i -lt $delay -and [DateTimeOffset]::UtcNow -lt $expires -and -not (Test-Path $stopFile); $i++) { Start-Sleep -Seconds 1 }
        } else { Start-Sleep -Seconds 2 }
    }
    Write-RuntimeEvent $directory 'supervisor-events' 'SupervisorCompleted' @{RunId=$runId}
} catch {
    try { Write-RuntimeEvent $directory 'supervisor-events' 'SupervisorError' @{Message=$_.Exception.ToString();Stack=$_.ScriptStackTrace} } catch { }
    throw
} finally {
    if ($owned) {
        # Unexpected supervisor failure leaves a live worker for its replacement.
        if ([DateTimeOffset]::UtcNow -ge $expires -or (Test-Path $stopFile)) {
            [IO.File]::WriteAllText($stopFile, 'stop')
            if ($worker -and -not $worker.HasExited -and -not $worker.WaitForExit(15000)) { $worker.Kill(); $worker.WaitForExit() }
        }
        $mutex.ReleaseMutex()
    }
    if ($worker) { $worker.Dispose() }
    $mutex.Dispose()
}
