Set-StrictMode -Version Latest

if (-not ('ReInode.ProcessAccess' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
namespace ReInode {
    public static class ProcessAccess {
        [DllImport("kernel32.dll", SetLastError=true)]
        public static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        public static extern bool QueryFullProcessImageName(IntPtr h, uint flags, StringBuilder path, ref uint size);
        [DllImport("kernel32.dll")]
        public static extern bool CloseHandle(IntPtr h);
        public static string ImagePath(uint pid) {
            IntPtr h = OpenProcess(0x1000, false, pid);
            if (h == IntPtr.Zero) return null;
            try {
                var path = new StringBuilder(32768);
                uint size = 32768;
                return QueryFullProcessImageName(h, 0, path, ref size) ? path.ToString() : null;
            } finally { CloseHandle(h); }
        }
        [DllImport("advapi32.dll", SetLastError=true)] private static extern bool OpenProcessToken(IntPtr process, uint access, out IntPtr token);
        [DllImport("advapi32.dll", SetLastError=true)] private static extern bool GetTokenInformation(IntPtr token, int kind, IntPtr data, int length, out int needed);
        [DllImport("advapi32.dll")] private static extern IntPtr GetSidSubAuthorityCount(IntPtr sid);
        [DllImport("advapi32.dll")] private static extern IntPtr GetSidSubAuthority(IntPtr sid, uint index);
        public static int Integrity(uint pid) {
            IntPtr process=OpenProcess(0x1000,false,pid),token=IntPtr.Zero,data=IntPtr.Zero;
            if(process==IntPtr.Zero)return -1;
            try {
                if(!OpenProcessToken(process,8,out token))return -1;
                int length;GetTokenInformation(token,25,IntPtr.Zero,0,out length);
                if(length<=0)return -1;data=Marshal.AllocHGlobal(length);
                if(!GetTokenInformation(token,25,data,length,out length))return -1;
                IntPtr sid=Marshal.ReadIntPtr(data);byte count=Marshal.ReadByte(GetSidSubAuthorityCount(sid));
                return Marshal.ReadInt32(GetSidSubAuthority(sid,(uint)(count-1)));
            }finally{if(data!=IntPtr.Zero)Marshal.FreeHGlobal(data);if(token!=IntPtr.Zero)CloseHandle(token);CloseHandle(process);}
        }
    }
}
'@
}

$script:INodeClientPath = 'C:\Program Files (x86)\iNode\iNode Client\iNode Client.exe'
$script:INodeClientSha256 = '1712589D729482A21AFDA7E097D0BB863708BE17EFC15462427CB8A2D7A15CF1'

function Test-INodeClientBinary {
    param([string]$Path = $script:INodeClientPath)
    if (-not [IO.File]::Exists($Path)) { return $false }
    try {
        if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $script:INodeClientSha256) { return $false }
        # This exact hash was signature-verified during installation. Repeating
        # WinVerifyTrust here can block on certificate revocation while offline.
        return $true
    } catch { return $false }
}

function Get-INodeProcessInventory {
    $names = @('iNodeMon','iNodeImg','iNodeCmn','iNodeSec','iNode1x','iNodePortal','iNode Client')
    foreach ($name in $names) {
        foreach ($p in @(Get-Process -Name $name -ErrorAction SilentlyContinue)) {
            [pscustomobject]@{Name=$p.ProcessName;ProcessId=$p.Id;StartTime=$(try{$p.StartTime.ToUniversalTime().ToString('o')}catch{''})}
        }
    }
}
function Get-INodeSuiteInventory {
    @(Get-INodeProcessInventory | Where-Object { $_.Name -ne 'iNode Client' })
}
function Close-INodeGuiWindows {
    Initialize-INodeDesktop
    foreach ($p in @(Get-Process -Name 'iNode Client' -ErrorAction SilentlyContinue)) {
        try { [ReInode.Desktop]::CloseClientWindows($p.Id) } catch { }
    }
}

function Get-INodeClientProcess {
    $processes = @(Get-Process -Name 'iNode Client' -ErrorAction SilentlyContinue |
        Where-Object { -not $_.HasExited })
    if ($processes.Count -eq 0) { return $null }
    if ($processes.Count -ne 1) { throw "Expected one iNode Client process, found $($processes.Count)." }
    $p = $processes[0]
    $pathState = 'Unavailable'
    try {
        # Query limited information instead of enumerating protected process modules.
        $path = [ReInode.ProcessAccess]::ImagePath($p.Id)
        if ($path) {
            $pathState = 'Verified'
            if ([IO.Path]::GetFullPath($path) -ne [IO.Path]::GetFullPath($script:INodeClientPath)) {
                throw 'The iNode Client process path is not the pinned installation.'
            }
        }
    } catch [System.ComponentModel.Win32Exception] { $pathState = 'Unavailable' }
    catch [System.InvalidOperationException] { $pathState = 'Unavailable' }
    return [pscustomobject]@{Process=$p;PathState=$pathState;ProcessId=$p.Id;Integrity=[ReInode.ProcessAccess]::Integrity($p.Id);
        StartTimeUtc=$p.StartTime.ToUniversalTime().ToString('o');MainWindowHandle=[int64]$p.MainWindowHandle}
}

$script:ControllerVersion = '2026-09-16-menu-recovery-v2'
function Initialize-INodeDesktop {
    if (-not ('ReInode.Desktop' -as [type])) {
        Add-Type -Path (Join-Path $PSScriptRoot 'INodeDesktop.cs') -ReferencedAssemblies UIAutomationClient,UIAutomationTypes,WindowsBase,System.Drawing
    }
}
function Test-INodeDesktopReady {
    Initialize-INodeDesktop
    return [ReInode.Desktop]::Ready()
}
function Test-INodeProcessInteraction {
    param($Client)
    $ownIntegrity=[ReInode.ProcessAccess]::Integrity($PID)
    return $null -ne $Client -and $Client.Integrity -ge 0 -and $ownIntegrity -ge $Client.Integrity
}
function Get-INodeLaunchShortcut {
    if (-not (Test-INodeClientBinary)) { throw 'Pinned client binary changed.' }
    $shell = New-Object -ComObject WScript.Shell
    try {
        $root = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\iNode'
        $matches = @(Get-ChildItem -LiteralPath $root -Filter *.lnk -Recurse | ForEach-Object {
            $link=$shell.CreateShortcut($_.FullName)
            try {
                if ($link.TargetPath -eq $script:INodeClientPath -and -not $link.Arguments -and
                    $link.WorkingDirectory -eq [IO.Path]::GetDirectoryName($script:INodeClientPath) -and $link.WindowStyle -eq 1) { $_.FullName }
            } finally { $null=[Runtime.InteropServices.Marshal]::ReleaseComObject($link) }
        })
        if ($matches.Count -eq 1) { return $matches[0] }
        return $null
    } finally { $null=[Runtime.InteropServices.Marshal]::ReleaseComObject($shell) }
}
function Start-INodeClientNormal {
    if (-not (Test-INodeClientBinary)) { throw 'Pinned client binary changed.' }
    $shortcut = Get-INodeLaunchShortcut
    Initialize-INodeDesktop
    $dir = [IO.Path]::GetDirectoryName($script:INodeClientPath)
    if ($shortcut) {
        [ReInode.Desktop]::LaunchShortcut($shortcut,$dir)
        return
    }
    Start-Process -FilePath $script:INodeClientPath -WorkingDirectory $dir
}
function Confirm-INodeNormalExit {
    param($Identity,[switch]$ProbeOnly)
    $handle=[ReInode.Desktop]::FindExitConfirmation($Identity.ProcessId)
    if($handle -eq 0){return $null}
    $image=Join-Path ([IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\logs'))) ('confirm-'+[guid]::NewGuid().ToString('N')+'.png')
    $bounds=[ReInode.Desktop]::CaptureConfirmation($handle,$Identity.ProcessId,$image)
    $lines=@(Get-INodeMenuText $image -Kind dialog)
    $target=Get-INodeExitConfirmationTarget $lines
    if(-not $ProbeOnly){
        $latestBounds=[ReInode.Desktop]::CaptureConfirmation($handle,$Identity.ProcessId,$image)
        $latest=Get-INodeExitConfirmationTarget @(Get-INodeMenuText $image -Kind dialog)
        $current=Get-INodeClientProcess
        if($null -eq $current -or $current.ProcessId -ne $Identity.ProcessId -or $current.StartTimeUtc -ne $Identity.StartTimeUtc -or $current.PathState -ne 'Verified'){throw 'Client changed before exit confirmation.'}
        if($bounds -ne $latestBounds -or [math]::Abs($latest.X-$target.X) -gt 9 -or [math]::Abs($latest.Y-$target.Y) -gt 9){throw 'Exit confirmation moved.'}
        [ReInode.Desktop]::ConfirmExit($handle,$Identity.ProcessId,$bounds,[int]($latest.X/3),[int]($latest.Y/3))
    }
    return [pscustomobject]@{Method='VerifiedExitConfirmationOCR';Screenshot=$image;Lines=$lines;ProbeOnly=[bool]$ProbeOnly}
}
function Request-INodeNormalExit {
    param([int]$ExpectedProcessId,[switch]$ProbeOnly)
    $identity=Get-INodeClientProcess
    if($null -eq $identity -or $identity.ProcessId -ne $ExpectedProcessId -or $identity.PathState -ne 'Verified'){throw 'Client identity changed before menu lookup.'}
    if(-not (Test-INodeProcessInteraction $identity)){throw 'Executor needs the same Windows integrity level as iNode; administrator approval is required.'}
    Initialize-INodeDesktop
    Import-Module (Join-Path $PSScriptRoot 'INodeMenuOcr.psm1')
    $pending=Confirm-INodeNormalExit $identity -ProbeOnly:$ProbeOnly
    if($null -ne $pending){return $pending}
    $folder=Join-Path $PSScriptRoot '..\logs'
    $image=Join-Path ([IO.Path]::GetFullPath($folder)) ('menu-'+[guid]::NewGuid().ToString('N')+'.png')
    $handle=[ReInode.Desktop]::OpenPopup($ExpectedProcessId)
    $invoked=$false
    try {
        $bounds=[ReInode.Desktop]::CapturePopup($handle,$ExpectedProcessId,$image)
        $lines=@(Get-INodeMenuText $image)
        $target=Get-INodeExitTextTarget $lines
        # Probe and live execution share every check up to the final click.
        $checkBounds=[ReInode.Desktop]::CapturePopup($handle,$ExpectedProcessId,$image)
        $check=Get-INodeExitTextTarget @(Get-INodeMenuText $image)
        if($checkBounds -ne $bounds -or [math]::Abs($check.X-$target.X) -gt 9 -or [math]::Abs($check.Y-$target.Y) -gt 9){throw 'Menu changed during recognition.'}
        $current=Get-INodeClientProcess
        if($null -eq $current -or $current.ProcessId -ne $ExpectedProcessId -or $current.StartTimeUtc -ne $identity.StartTimeUtc -or $current.PathState -ne 'Verified'){throw 'Client identity changed before exit input.'}
        if($ProbeOnly){[ReInode.Desktop]::AimPopupText($handle,$ExpectedProcessId,$bounds,[int]($check.X/3),[int]($check.Y/3))}
        else{
            [ReInode.Desktop]::ClickPopupText($handle,$ExpectedProcessId,$bounds,[int]($check.X/3),[int]($check.Y/3))
            $invoked=$true
            for($i=0;$i -lt 30;$i++){
                Start-Sleep -Milliseconds 100
                if($identity.Process.HasExited){break}
                $confirmation=Confirm-INodeNormalExit $identity
                if($null -ne $confirmation){break}
            }
        }
        return [pscustomobject]@{Method='VerifiedQtMenuOCR';Lines=$lines;Screenshot=$image;ProbeOnly=[bool]$ProbeOnly}
    } finally {
        if(-not $invoked){[ReInode.Desktop]::DismissPopup($handle,$ExpectedProcessId)}
    }
}
function Get-INodeLogCheckpoint {
    $checkpoint=@{}
    Get-ChildItem (Join-Path ([IO.Path]::GetDirectoryName($script:INodeClientPath)) 'Log') -Filter 'iNode*.log' |
        Where-Object Name -match '^iNode(Cmn|1x)\.' | ForEach-Object { $checkpoint[$_.FullName]=$_.Length }
    if ($checkpoint.Count -eq 0) { throw 'Authentication logs unavailable.' }
    return $checkpoint
}
function Get-INodeAuthenticationEvidence {
    param([hashtable]$Checkpoint)
    $auto=$false; $active=$false
    $folder=Join-Path ([IO.Path]::GetDirectoryName($script:INodeClientPath)) 'Log'
    foreach ($file in @(Get-ChildItem $folder -Filter 'iNode*.log' | Where-Object Name -match '^iNode(Cmn|1x)\.')) {
        $offset=if($Checkpoint.ContainsKey($file.FullName)){[long]$Checkpoint[$file.FullName]}else{0L}
        if($file.Length -lt $offset){throw 'Authentication log truncated; evidence is ambiguous.'}
        if($file.Length -eq $offset){continue}
        if(($file.Length-$offset) -gt 1048576){throw 'Authentication log range exceeds bounded read.'}
        $stream=[IO.File]::Open($file.FullName,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
        try {
            $null=$stream.Seek($offset,[IO.SeekOrigin]::Begin)
            $reader=[IO.StreamReader]::new($stream,[Text.Encoding]::ASCII)
            try{$text=$reader.ReadToEnd()}finally{$reader.Dispose()}
        } finally{$stream.Dispose()}
        if($file.Name -like 'iNodeCmn.*' -and $text -match 'CInodeTask::onClientStart Auto connect'){ $auto=$true }
        if($file.Name -like 'iNode1x.*' -and $text -match 'CProtoBase::onClientStart have active non machine connection'){ $active=$true }
    }
    [pscustomobject]@{AutoConnect=$auto;ActiveConnection=$active;Verified=($auto -and $active)}
}
function Get-INodeTailAuthenticationEvidence {
    param([int]$TailBytes=262144)
    $checkpoint=@{}
    $folder=Join-Path ([IO.Path]::GetDirectoryName($script:INodeClientPath)) 'Log'
    foreach ($file in @(Get-ChildItem $folder -Filter 'iNode*.log' | Where-Object Name -match '^iNode(Cmn|1x)\.')) {
        $checkpoint[$file.FullName]=[Math]::Max(0L, $file.Length-$TailBytes)
    }
    if ($checkpoint.Count -eq 0) { throw 'Authentication logs unavailable.' }
    Get-INodeAuthenticationEvidence $checkpoint
}
function Get-INodeConnectedState {
    param([int]$ExpectedProcessId,[DateTimeOffset]$Since,[switch]$RevealFromTray)
    Initialize-INodeDesktop
    Import-Module (Join-Path $PSScriptRoot 'INodeMenuOcr.psm1')
    $before=Get-INodeClientProcess
    if($null -eq $before -or $before.ProcessId -ne $ExpectedProcessId -or $before.PathState -ne 'Verified'){throw 'Status client identity mismatch.'}
    $image=Join-Path ([IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\logs'))) ('status-'+[guid]::NewGuid().ToString('N')+'.png')
    $null=[ReInode.Desktop]::CaptureClientStatus($ExpectedProcessId,$image,[bool]$RevealFromTray)
    $lines=@(Get-INodeMenuText $image -Kind dialog)
    $connected=@($lines | Where-Object {$_.Text -ceq ([string][char]0x5df2+[char]0x8fde+[char]0x63a5) -and $_.Confidence -ge 0.7})
    $label=@($lines | Where-Object {$_.Text -ceq ([string][char]0x8fde+[char]0x63a5+[char]0x72b6+[char]0x6001) -and $_.Confidence -ge 0.7})
    $times=@($lines | Where-Object {$_.Text -match '^\d{4}-\d{1,2}-\d{1,2}\d{2}:\d{2}:\d{2}$' -and $_.Confidence -ge 0.7})
    $online=$null
    if($times.Count -eq 1){
        $m=[regex]::Match($times[0].Text,'^(\d{4}-\d{1,2}-\d{1,2})(\d{2}:\d{2}:\d{2})$')
        $date=[DateTime]::ParseExact(($m.Groups[1].Value+' '+$m.Groups[2].Value),'yyyy-M-d HH:mm:ss',[Globalization.CultureInfo]::InvariantCulture)
        $online=[DateTimeOffset]::new($date,[TimeZoneInfo]::Local.GetUtcOffset($date))
    }
    $after=Get-INodeClientProcess
    $matches=$null -ne $after -and $after.ProcessId -eq $ExpectedProcessId -and $after.StartTimeUtc -eq $before.StartTimeUtc -and $after.PathState -eq 'Verified'
    $verified=$matches -and $connected.Count -eq 1 -and $label.Count -eq 1 -and
        $connected[0].X -gt $label[0].X -and [math]::Abs($connected[0].Y-$label[0].Y) -le 40 -and
        $null -ne $online -and $online -ge $Since.AddSeconds(-1) -and $online -le [DateTimeOffset]::Now.AddSeconds(5)
    [pscustomobject]@{Verified=$verified;Method='ClientConnectedStateAndFreshOnlineTime';OnlineTime=$online;Screenshot=$image;ObservedProcessId=$ExpectedProcessId;
        IdentityVerified=$matches;ConnectedMatches=$connected.Count;LabelMatches=$label.Count;OnlineTimeMatches=$times.Count;Since=$Since}
}
function Invoke-INodeGuiRestart {
    param([Parameter(Mandatory)][ValidateRange(1,2147483647)][int]$ExpectedProcessId,
        [int]$WaitSeconds=30, [scriptblock]$RecordStage={param($stage,$details)})
    if (-not (Test-INodeClientBinary)) { throw 'Pinned client binary changed.' }
    $target=Get-INodeClientProcess
    if($null -eq $target -or $target.ProcessId -ne $ExpectedProcessId){throw 'Client identity changed before action.'}
    if($target.PathState -ne 'Verified'){throw 'Cannot verify the running client path; no process was stopped.'}
    if(-not (Test-INodeProcessInteraction $target)){throw 'Executor needs administrator approval to interact with this elevated iNode client.'}
    if(-not (Test-INodeDesktopReady)){throw 'Desktop locked or tray icon unavailable.'}
    $checkpoint=Get-INodeLogCheckpoint
    & $RecordStage 'PreflightPassed' @{ControllerVersion=$script:ControllerVersion;TargetProcessId=$ExpectedProcessId}
    $exitError=$null; $exited=$false
    try {
        & $RecordStage 'ExitRequested' @{}
        $menu=Request-INodeNormalExit $ExpectedProcessId
        & $RecordStage 'ExitMenuInvoked' @{Menu=$menu}
    } catch { $exitError=$_.Exception.Message }
    # An uncertain input result must still restore the client if it actually exited.
    $exited=$target.Process.WaitForExit(15000)
    if(-not $exited){throw "Normal exit did not finish; no force termination. $exitError"}
    $target.Process.Dispose()
    Start-Sleep -Seconds 3
    $after=$null; $launches=0; $launchError=$null
    for($attempt=0;$attempt -lt 2;$attempt++) {
        $existing=Get-INodeClientProcess
        if($null -eq $existing){
            $launches++
            try { Start-INodeClientNormal } catch { $launchError=$_.Exception.Message }
        }
        $stableId=0; $stableRounds=0
        for($round=0;$round -lt 20;$round++) {
            Start-Sleep -Milliseconds 500
            $after=Get-INodeClientProcess
            if($null -ne $after -and $after.PathState -eq 'Verified' -and $after.ProcessId -ne $ExpectedProcessId){
                if($stableId -eq $after.ProcessId){$stableRounds++}else{$stableId=$after.ProcessId;$stableRounds=1}
                if($stableRounds -ge 10){break}
            }else{$stableId=0;$stableRounds=0}
        }
        if($stableRounds -ge 10){break}
        if($null -ne $after){throw 'Existing client did not stabilize; no duplicate launch.'}
    }
    if($null -eq $after -or $stableRounds -lt 10){throw "Normal launch failed after at most two launches. $launchError"}
    & $RecordStage 'ClientStarted' @{ObservedProcessId=$after.ProcessId;LaunchAttempts=$launches;ExitWarning=$exitError}
    $auth=$null
    $authDeadline=[DateTimeOffset]::UtcNow.AddSeconds($WaitSeconds)
    for($round=0;$round -lt $WaitSeconds -and [DateTimeOffset]::UtcNow -lt $authDeadline;$round++){
        $auth=Get-INodeAuthenticationEvidence $checkpoint
        if($auth.Verified){break}
        if($auth.AutoConnect){
            try {
                $ui=Get-INodeConnectedState $after.ProcessId ([DateTimeOffset]$after.StartTimeUtc)
                if($ui.Verified){$auth | Add-Member -NotePropertyName ConnectedState -NotePropertyValue $ui;$auth.Verified=$true;break}
            }catch { }
        }
        Start-Sleep -Seconds 1
    }
    & $RecordStage 'AuthenticationChecked' $auth
    [pscustomobject]@{Accepted=$true;AuthenticationVerified=$auth.Verified;Authentication=$auth;
        ControllerVersion=$script:ControllerVersion;TargetProcessId=$ExpectedProcessId;ObservedProcessId=$after.ProcessId;
        LaunchAttempts=$launches;StartupStableSeconds=5;PathState=$after.PathState;ExitWarning=$exitError}
}

Export-ModuleMember -Function Test-INodeClientBinary, Get-INodeProcessInventory, Get-INodeSuiteInventory, Close-INodeGuiWindows, Get-INodeClientProcess,
    Initialize-INodeDesktop, Test-INodeDesktopReady, Test-INodeProcessInteraction, Get-INodeLaunchShortcut, Start-INodeClientNormal,
    Request-INodeNormalExit, Get-INodeLogCheckpoint, Get-INodeAuthenticationEvidence, Get-INodeTailAuthenticationEvidence, Get-INodeConnectedState, Invoke-INodeGuiRestart
