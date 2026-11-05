# SPDX-License-Identifier: GPL-3.0-or-later
param([Parameter(Mandatory=$true)][string]$RepoRoot,
      [Parameter(Mandatory=$true)][string]$FixtureRoot,
      [ValidateSet('Parsing','Discovery','Transitions','Client')][string]$Suite)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
Import-Module (Join-Path $RepoRoot 'src\INodeInstallation.psm1') -Force
Import-Module (Join-Path $RepoRoot 'replacement\OriginalService.psm1') -Force
$checks=0
function Assert($value,[string]$label){if(-not $value){throw "FAILED: $label"};$script:checks++}
function Assert-Error([scriptblock]$action,[string]$code){
    $errorCode=''
    try{$null=& $action}catch{$errorCode=$_.Exception.Message}
    Assert ($errorCode -eq $code) "expected $code, got $errorCode"
}
function Write-Executable([string]$path,[byte]$version=1){
    $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path))
    $bytes=New-Object byte[] 160
    $bytes[0]=0x4D;$bytes[1]=0x5A;$bytes[60]=64;$bytes[64]=0x50;$bytes[65]=0x45;$bytes[159]=$version
    [IO.File]::WriteAllBytes($path,$bytes)
}
$directory=Join-Path $FixtureRoot ('custom '+[char]0x5B66+[char]0x6821+' installation')
$binary=Join-Path $directory 'iNodeMon.exe'
$client=Join-Path $directory 'iNode Client.exe'
Write-Executable $binary
Write-Executable $client
$command='"'+$binary+'" -startService'

if($Suite -eq 'Parsing'){
    foreach($text in @($command,('  "'+$binary.ToUpperInvariant()+'"   -STARTSERVICE  '),
                      ($binary+' -startService'),('"'+$binary+'" "-startService"'))){
        $parsed=ConvertFrom-INodeServiceCommand $text
        Assert ($parsed.BinaryPath -ieq $binary -and $parsed.Arguments -ceq '-startservice') 'quotes, whitespace and casing'
    }
    $env:CAMPUS_TEST_INODE_DIRECTORY=$directory
    try{
        $parsed=ConvertFrom-INodeServiceCommand '"%CAMPUS_TEST_INODE_DIRECTORY%\iNodeMon.exe" -startService'
        Assert ($parsed.BinaryPath -eq $binary) 'environment expansion'
    }finally{Remove-Item Env:\CAMPUS_TEST_INODE_DIRECTORY}
    $parsed=ConvertFrom-INodeServiceCommand ('"'+$binary+'"')
    Assert ($parsed.Arguments -eq '') 'SCM installations without service arguments'
    $parsed=ConvertFrom-INodeServiceCommand ('"'+$binary+'" --vendor-option "a  b"')
    Assert ($parsed.Arguments -ceq '--vendor-option "a  b"') 'preserve version-specific arguments verbatim'
    foreach($text in @('iNodeMon.exe -startService','C:relative\iNodeMon.exe','"\\server\share\iNodeMon.exe"',
        '"C:\wrong.exe" -startService',('"'+$binary+' -startService'),('"'+$binary+'"suffix'),
        ('"'+$binary+'"'+"`r`n"+'anything'),'cmd.exe /c "C:\iNodeMon.exe"')){
        Assert-Error {ConvertFrom-INodeServiceCommand $text} 'OriginalServiceCommandUnsupported'
    }
}

if($Suite -eq 'Discovery'){
    $module=Get-Module INodeInstallation
    & $module {
        param($command,$binary)
        $script:fixture=@{Services=@([pscustomobject]@{Name='INODE_SVR_SERVICE';PathName=$command;ProcessId=0});
            ProcessPath=$binary;QueryFails=$false}
        function script:Get-CimInstance {
            param($ClassName,$Filter,$ErrorAction)
            if($script:fixture.QueryFails){throw 'fixture query failure'}
            if($ClassName -eq 'Win32_Service'){return $script:fixture.Services}
            if($ClassName -eq 'Win32_Process'){return [pscustomobject]@{ExecutablePath=$script:fixture.ProcessPath}}
            throw 'Unexpected platform query'
        }
        function script:Get-AuthenticodeSignature {throw 'No online signature checks allowed'}
        function script:Get-FileHash {throw 'Use the offline .NET SHA-256 implementation'}
    } $command $binary
    $first=Get-INodeInstallation
    Assert ($first.ClientPath -eq $client -and $first.BinaryPath -eq $binary) 'discover custom directory and companion client'
    Assert ($first.BinarySha256.Length -eq 64) 'capture local SHA-256'
    & $module {param($binary) $script:fixture.Services[0].PathName=$binary+' -startService'} $binary
    Assert ((Get-INodeInstallation).BinaryPath -eq $binary) 'accept unquoted paths without executable ambiguity'
    $prefix=$binary.Substring(0,$binary.IndexOf(' ',$FixtureRoot.Length))+'.exe'
    Write-Executable $prefix
    Assert-Error {Get-INodeInstallation} 'OriginalServicePathAmbiguous'
    [IO.File]::Delete($prefix)
    & $module {param($command) $script:fixture.Services[0].PathName=$command} $command
    Write-Executable $binary 2
    $second=Get-INodeInstallation
    Assert ($second.BinarySha256 -ne $first.BinarySha256) 'accept another installed version, record its own hash'
    & $module {$script:fixture.Services[0].ProcessId=123}
    Assert ((Get-INodeInstallation).BinaryPath -eq $binary) 'verify running service image'
    & $module {$script:fixture.ProcessPath='C:\foreign\iNodeMon.exe'}
    Assert-Error {Get-INodeInstallation} 'OriginalServiceIdentityChanged'
    & $module {$script:fixture.ProcessPath=''}
    Assert-Error {Get-INodeInstallation} 'OriginalInstallationUnreadable'
    & $module {$script:fixture.Services[0].ProcessId=0;$script:fixture.QueryFails=$true}
    Assert-Error {Get-INodeInstallation} 'OriginalServiceQueryFailed'
    & $module {$script:fixture.QueryFails=$false;$script:fixture.Services=@()}
    Assert-Error {Get-INodeInstallation} 'OriginalServiceMissing'
    & $module {param($command) $script:fixture.Services=@([pscustomobject]@{Name='foreign';PathName=$command;ProcessId=0})} $command
    Assert-Error {Get-INodeInstallation} 'OriginalServiceIdentityChanged'
    & $module {$script:fixture.Services[0].Name='INODE_SVR_SERVICE';$script:fixture.Services+= $script:fixture.Services[0]}
    Assert-Error {Get-INodeInstallation} 'OriginalServiceIdentityChanged'
    Assert-Error {Get-INodeExecutableFingerprint (Join-Path $directory 'missing.exe')} 'OriginalInstallationFileMissing'
    foreach($variant in @('short','not-pe','bad-offset','bad-pe')){
        Write-Executable $binary
        $bytes=[IO.File]::ReadAllBytes($binary)
        switch($variant){
            short{$bytes=New-Object byte[] 2}
            not-pe{$bytes[0]=0}
            bad-offset{$bytes[60]=255}
            bad-pe{$bytes[64]=0}
        }
        [IO.File]::WriteAllBytes($binary,$bytes)
        Assert-Error {Get-INodeExecutableFingerprint $binary} 'OriginalInstallationFileInvalid'
    }
    Write-Executable $binary
    $locked=[IO.File]::Open($binary,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    try{Assert-Error {Get-INodeExecutableFingerprint $binary} 'OriginalInstallationUnreadable'}finally{$locked.Dispose()}
}

if($Suite -eq 'Transitions'){
    foreach($case in @('Stop','Start','AlreadyStopped','Formatting','Legacy','ForeignPath','ChangedHash',
        'ChangedMode','ForeignService','ChangedArguments','Dependents','CannotStop','Pending','RequestFailure','NoTransition','ChangedAfterRequest')){
        $original=[pscustomobject]@{Name='INODE_SVR_SERVICE';Path=$command;BinarySha256='same-file';
            StartMode='Auto';State='Running';AcceptStop=$true;RunningDependents=0}
        $current=$original.PSObject.Copy()
        $fixture=@{Current=$current;Requests=0;Case=$case}
        $target='Stopped'
        switch($case){
            Start{$current.State='Stopped';$target='Running'}
            AlreadyStopped{$current.State='Stopped'}
            Formatting{$current.Path='  '+$binary.ToUpperInvariant()+'    -STARTSERVICE  '}
            Legacy{$original.PSObject.Properties.Remove('BinarySha256')}
            ForeignPath{$current.Path='"C:\foreign\iNodeMon.exe" -startService'}
            ChangedHash{$current.BinarySha256='different-file'}
            ChangedMode{$current.StartMode='Disabled'}
            ForeignService{$current.Name='foreign'}
            ChangedArguments{$current.Path='"'+$binary+'" -other'}
            Dependents{$current.RunningDependents=1}
            CannotStop{$current.AcceptStop=$false}
            Pending{$current.State='Stop Pending'}
        }
        $operations=@{
            Read={return $fixture.Current}.GetNewClosure()
            Request={param($desired)
                $fixture.Requests++
                if($fixture.Case -eq 'RequestFailure'){throw 'fixture SCM failure'}
                if($fixture.Case -ne 'NoTransition'){$fixture.Current.State=$desired}
                if($fixture.Case -eq 'ChangedAfterRequest'){$fixture.Current.BinarySha256='replaced-file'}
            }.GetNewClosure()
        }
        $failed=$false
        try{$null=Set-CampusOriginalServiceState -Original $original -State $target -Operations $operations}catch{$failed=$true}
        $success=$case -in @('Stop','Start','AlreadyStopped','Formatting','Legacy')
        Assert ($failed -ne $success) "transition outcome: $case"
        $requested=$case -in @('Stop','Start','Formatting','Legacy','RequestFailure','NoTransition','ChangedAfterRequest')
        Assert ($fixture.Requests -eq [int]$requested) "no unsafe or redundant service action: $case"
    }
}

if($Suite -eq 'Client'){
    Import-Module (Join-Path $RepoRoot 'src\INodeController.psm1') -Force
    $controller=Get-Module INodeController
    & $controller {
        param($client)
        $script:fixture=@{Client=$client;Launches=0;Path='';Directory='';MissingShortcut=$false}
        function script:Get-INodeClientPath {$script:fixture.Client}
        function script:Get-INodeLaunchShortcut {if($script:fixture.MissingShortcut){throw 'shortcut missing'};return $null}
        function script:Initialize-INodeDesktop {}
        function script:Start-Process {param($FilePath,$WorkingDirectory)
            $script:fixture.Launches++;$script:fixture.Path=$FilePath;$script:fixture.Directory=$WorkingDirectory
        }
        function script:Get-AuthenticodeSignature {throw 'No online signature checks allowed'}
    } $client
    Assert (Test-INodeClientBinary) 'accept discovered client PE'
    Write-Executable $client 2
    Assert (Test-INodeClientBinary) 'accept another client version without a compiled-in hash'
    $foreign=Join-Path $FixtureRoot 'foreign\iNode Client.exe'
    Write-Executable $foreign
    Assert (-not (Test-INodeClientBinary $foreign)) 'reject client from another installation'
    Start-INodeClientNormal
    & $controller {$script:fixture.MissingShortcut=$true}
    Start-INodeClientNormal
    $launch=& $controller {$script:fixture}
    Assert ($launch.Launches -eq 2 -and $launch.Path -eq $client -and $launch.Directory -eq $directory) 'missing shortcuts use discovered client, mocked launch only'
    [IO.File]::WriteAllText($client,'invalid binary')
    Assert (-not (Test-INodeClientBinary)) 'reject invalid client'
    Assert-Error {Start-INodeClientNormal} 'OriginalClientIdentityUnavailable'
    Assert ((& $controller {$script:fixture.Launches}) -eq 2) 'invalid client never launched'
}
Write-Output "PASS $Suite`: $checks checks; isolated files and mocked platform operations only."
