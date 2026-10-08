# Isolated executor-test platform. No service, network or task commands are called.
Set-StrictMode -Version Latest
$script:Root=Split-Path $PSScriptRoot -Parent
function Read-Fixture { Get-Content (Join-Path $script:Root 'fixture.json') -Raw | ConvertFrom-Json }
function Write-Action([string]$Name) { [IO.File]::AppendAllText((Join-Path $script:Root 'actions.log'),$Name+"`n") }
function Get-NetAdapter {
    $f=Read-Fixture
    [pscustomobject]@{InterfaceGuid=('{'+$f.Adapter+'}');MacAddress=$f.Mac;ifIndex=7}
}
function Get-NetIPAddress {
    param($InterfaceIndex,$AddressFamily)
    [pscustomobject]@{IPAddress='198.51.100.1';AddressState='Preferred'}
}
function Get-INodeLaunchShortcut { return 'verified-fixture-shortcut' }
function Get-CampusOriginalService { [pscustomobject]@{Name='INODE_SVR_SERVICE';State='Stopped';StartMode='Auto';Path='fixture'} }
function Set-CampusOriginalServiceState {
    param($Original,$State)
    Write-Action 'service'
    if((Read-Fixture).Failure -eq 'service'){throw 'ServiceFixtureFailure'}
    if($State -eq 'Stopped'){
        $f=Read-Fixture
        if(-not ($f.PSObject.Properties['KeepClientOnStop'] -and $f.KeepClientOnStop)){$f.Client=$false}
        $f | ConvertTo-Json | Set-Content (Join-Path $script:Root 'fixture.json') -Encoding UTF8
    }
}
function Get-INodeProcessInventory { if((Read-Fixture).Client){Get-INodeClientProcess} }
function Get-INodeSuiteInventory { @() }
function Close-INodeGuiWindows { Write-Action 'close-gui' }
function Request-INodeNormalExit {
    param($ExpectedProcessId)
    if($ExpectedProcessId -ne 1234){throw 'ClientFixtureIdentityChanged'}
    Write-Action 'normal-exit'
    $f=Read-Fixture
    if($f.Failure -eq 'normal-exit'){throw 'PopupChanged'}
    $f.Client=$false
    $f | ConvertTo-Json | Set-Content (Join-Path $script:Root 'fixture.json') -Encoding UTF8
    [pscustomobject]@{Method='VerifiedMenuFixture'}
}
function Get-INodeClientProcess {
    $f=Read-Fixture
    if($f.Client){
        $id=1234;$started=$f.StartedUtc
        if($f.PSObject.Properties['ReplaceAfterReads']){
            $f.ClientReads++
            if($f.ClientReads -ge $f.ReplaceAfterReads){$id=5678;$started=$f.ReplacementStartedUtc}
            $f | ConvertTo-Json | Set-Content (Join-Path $script:Root 'fixture.json') -Encoding UTF8
        }
        [pscustomobject]@{ProcessId=$id;PathState='Verified';StartTimeUtc=$started}
    }
}
function Start-INodeClientNormal {
    Write-Action 'start'
    $f=Read-Fixture
    $f.Client=$true
    $f | ConvertTo-Json | Set-Content (Join-Path $script:Root 'fixture.json') -Encoding UTF8
}
function Get-INodeLogCheckpoint { @{ 'fixture.log' = 0 } }
function Get-INodeAuthenticationEvidence {
    param($Checkpoint)
    Write-Action 'log-evidence'
    [pscustomobject]@{AutoConnect=$true;ActiveConnection=$true;Verified=$true}
}
function Get-INodeTailAuthenticationEvidence {
    Get-INodeAuthenticationEvidence @{}
}
function Get-INodeConnectedState {
    param($ExpectedProcessId,$Since,[switch]$RevealFromTray)
    Write-Action 'authentication'
    $f=Read-Fixture
    if($f.Failure -eq 'occlusion'){throw 'PopupOccluded: Chrome_RenderWidgetHostHWND'}
    $fresh=if($f.PSObject.Properties['OnlineUtc']){[DateTimeOffset]$f.OnlineUtc -ge [DateTimeOffset]$Since}else{$true}
    $online=if($f.PSObject.Properties['OnlineUtc']){$f.OnlineUtc}else{$null}
    [pscustomobject]@{Verified=($f.Failure -ne 'authentication' -and $fresh);ObservedProcessId=$ExpectedProcessId;Since=$Since;
        IdentityVerified=$true;ConnectedMatches=1;LabelMatches=1;OnlineTimeMatches=1;OnlineTime=$online}
}
function Get-ScheduledTask {
    param($TaskName,$TaskPath)
    $f=Read-Fixture
    [pscustomobject]@{
        Actions=@([pscustomobject]@{
            Execute=(Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe')
            Arguments=('-NoProfile -NonInteractive -WindowStyle Hidden -File "'+(Join-Path $script:Root 'Supervise-Observation.ps1')+'" -RunId '+$f.RunId)
            WorkingDirectory=$script:Root
        })
        Principal=[pscustomobject]@{RunLevel='Highest';LogonType='Interactive';UserId=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value}
        Settings=[pscustomobject]@{MultipleInstances='IgnoreNew'}
        State='Running'
    }
}
function Start-ScheduledTask {
    param($TaskName,$TaskPath)
    Write-Action 'resume'
    $f=Read-Fixture
    if($f.Failure -eq 'monitor'){throw 'MonitorFixtureFailure'}
    $record=@{TimestampUtc=[DateTimeOffset]::UtcNow.ToString('o');RunId=$f.RunId;ProcessId=$PID;
        Recovery=@{Decision='NoSustainedCampusFailure';Mode='GuiRestart'};ControllerReady=$true;ControllerVersion='2026-09-16-menu-recovery-v2'}
    $record | ConvertTo-Json | Set-Content (Join-Path $script:Root 'logs\latest.json') -Encoding UTF8
    $record | ConvertTo-Json | Set-Content (Join-Path $script:Root 'logs\heartbeat.json') -Encoding UTF8
    @{RunId=$f.RunId;ProcessId=$PID;StartedUtc=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o')} |
        ConvertTo-Json | Set-Content (Join-Path $script:Root 'logs\worker.json') -Encoding UTF8
}
function Start-Process {
    param($FilePath,$ArgumentList,$WindowStyle,[switch]$PassThru,[switch]$Wait)
    Write-Action 'network'
    $matched=[regex]::Match($ArgumentList,'-ReportPath "([^"]+)"')
    if(-not $matched.Success){throw 'FixtureReportPathMissing'}
    $verified=(Read-Fixture).Failure -ne 'network'
    @{Verified=$verified;Rounds=@(@{Verified=$verified},@{Verified=$verified})} | ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath $matched.Groups[1].Value -Encoding UTF8
    $result=[pscustomobject]@{ExitCode=$(if($verified){0}else{1})}
    $result | Add-Member ScriptMethod Dispose {}
    return $result
}
function Start-Sleep { param($Milliseconds,$Seconds) }
Export-ModuleMember -Function Get-NetAdapter,Get-NetIPAddress,Get-INodeLaunchShortcut,Get-CampusOriginalService,
    Set-CampusOriginalServiceState,Get-INodeClientProcess,Start-INodeClientNormal,Get-INodeConnectedState,
    Get-INodeLogCheckpoint,Get-INodeAuthenticationEvidence,Get-INodeTailAuthenticationEvidence,
    Get-ScheduledTask,Start-ScheduledTask,Start-Process,Start-Sleep,Get-INodeProcessInventory,Get-INodeSuiteInventory,Close-INodeGuiWindows,Request-INodeNormalExit
