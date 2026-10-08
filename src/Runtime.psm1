Set-StrictMode -Version Latest
function Write-RuntimeEvent {
    param([string]$Directory, [string]$Stream, [string]$Event, $Details)
    $null = [IO.Directory]::CreateDirectory($Directory)
    $path = Join-Path $Directory "$Stream.jsonl"
    if ((Test-Path -LiteralPath $path) -and (Get-Item -LiteralPath $path).Length -gt 2097152) {
        Move-Item -LiteralPath $path -Destination "$path.1" -Force
    }
    $record = [ordered]@{ TimestampUtc = [DateTimeOffset]::UtcNow.ToString('o'); ProcessId = $PID; Event = $Event; Details = $Details }
    [IO.File]::AppendAllText($path, (($record | ConvertTo-Json -Depth 6 -Compress) + [Environment]::NewLine), [Text.UTF8Encoding]::new($false))
}
function Get-WorkerHealth {
    param([bool]$Exited, [double]$AgeSeconds, [double]$LimitSeconds)
    if ($Exited) { return 'Exited' }
    if ($AgeSeconds -gt $LimitSeconds) { return 'Stalled' }
    return 'Running'
}
function Write-AtomicJson {
    param([string]$Path, $Value)
    $temporary = "$Path.$PID.tmp"
    [IO.File]::WriteAllText($temporary, ($Value | ConvertTo-Json -Depth 12 -Compress), [Text.UTF8Encoding]::new($false))
    try {
        for ($attempt=0; $attempt -lt 6; $attempt++) {
            try {
                if ([IO.File]::Exists($Path)) { [IO.File]::Replace($temporary, $Path, [NullString]::Value) }
                else { [IO.File]::Move($temporary, $Path) }
                return
            } catch [IO.IOException] {
                if ($attempt -eq 5) { throw }
                Start-Sleep -Milliseconds 100
            }
        }
    } finally {
        if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
    }
}
function Get-NextProgress {
    param($Previous, [long]$Sequence, [double]$Seconds, [bool]$Valid)
    $next = [pscustomobject]@{ Sequence=$Previous.Sequence; ChangedAt=$Previous.ChangedAt }
    if ($Valid -and $Sequence -gt $Previous.Sequence) { $next.Sequence=$Sequence; $next.ChangedAt=$Seconds }
    return $next
}
Export-ModuleMember -Function Write-RuntimeEvent, Get-WorkerHealth, Write-AtomicJson, Get-NextProgress
