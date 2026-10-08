Set-StrictMode -Version Latest
function Invoke-INodeRecoveryExecutor {
    param([int]$ExpectedProcessId,[string]$ConfigPath,[string]$LogDirectory,[scriptblock]$Progress={},[switch]$Acceptance,[switch]$ProbeOnly,[string]$ResumeReportPath)
    $folder=Join-Path $LogDirectory 'recovery-actions'
    $null=[IO.Directory]::CreateDirectory($folder)
    $reportPath=Join-Path $folder ([guid]::NewGuid().ToString('N')+'.json')
    $scriptPath=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\Invoke-INodeRecovery.ps1'))
    $start=[Diagnostics.ProcessStartInfo]::new()
    $start.FileName=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $start.Arguments='-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -ExpectedProcessId {1} -ReportPath "{2}" -ConfigPath "{3}"' -f $scriptPath,$ExpectedProcessId,$reportPath,$ConfigPath
    if($Acceptance){$start.Arguments+=' -Acceptance'}
    if($ProbeOnly){$start.Arguments+=' -ProbeOnly'}
    if($ResumeReportPath){$start.Arguments+=' -ResumeReportPath "'+$ResumeReportPath+'"'}
    $start.WorkingDirectory=[IO.Path]::GetDirectoryName($scriptPath)
    $start.UseShellExecute=$false;$start.CreateNoWindow=$true
    $start.RedirectStandardError=$true
    $child=[Diagnostics.Process]::Start($start)
    $stderr=$child.StandardError.ReadToEndAsync()
    try {
        $deadline=[DateTimeOffset]::UtcNow.AddSeconds(240)
        while(-not $child.WaitForExit(2000)){
            if([DateTimeOffset]::UtcNow -gt $deadline){throw "Executor timed out; it was not terminated. Inspect $reportPath"}
            & $Progress
        }
        if(-not (Test-Path -LiteralPath $reportPath)){throw "Executor did not write report: $($stderr.Result)"}
        $report=Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if($report.ExecutorId -ne $child.Id -or $report.TargetProcessId -ne $ExpectedProcessId -or -not $report.FinishedUtc){throw 'Executor report identity mismatch.'}
        [pscustomobject]@{Accepted=($null -ne $report.Client);Verified=$report.Verified;
            ControllerVersion=$report.ControllerVersion;ReportPath=$reportPath;Report=$report}
    }finally{$child.Dispose()}
}
Export-ModuleMember -Function Invoke-INodeRecoveryExecutor
