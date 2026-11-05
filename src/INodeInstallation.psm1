# SPDX-License-Identifier: GPL-3.0-or-later
Set-StrictMode -Version Latest

# The SCM registration is the installation authority. Never search PATH or run
# a command line taken from the registry; service transitions go through SCM.
function ConvertFrom-INodeServiceCommand {
    param([Parameter(Mandatory=$true)][string]$Command)
    $commandText=[Environment]::ExpandEnvironmentVariables($Command).Trim()
    if($commandText -match '[\r\n\x00]'){throw 'OriginalServiceCommandUnsupported'}
    if($commandText.StartsWith('"')){
        $match=[regex]::Match($commandText,'^"(?<binary>[^"]+)"(?:\s+(?<arguments>.*))?$')
    }else{
        $match=[regex]::Match($commandText,'^(?<binary>[a-z]:\\[^"\r\n]*?\\iNodeMon\.exe)(?:\s+(?<arguments>.*))?$','IgnoreCase')
    }
    if(-not $match.Success){throw 'OriginalServiceCommandUnsupported'}
    $binary=$match.Groups['binary'].Value
    if($binary -notmatch '^[a-z]:\\' -or [IO.Path]::GetFileName($binary) -ine 'iNodeMon.exe'){
        throw 'OriginalServiceCommandUnsupported'
    }
    try{$binary=[IO.Path]::GetFullPath($binary)}catch{throw 'OriginalServiceCommandUnsupported'}
    $arguments=$match.Groups['arguments'].Value.Trim()
    # Normalize the known switch, without changing arbitrary version-specific
    # arguments (which are retained and compared during this handoff).
    if($arguments -match '^(?:"([-/]startservice)"|([-/]startservice))$'){
        $arguments=($arguments.Trim('"')).ToLowerInvariant()
    }
    [pscustomobject]@{BinaryPath=$binary;Arguments=$arguments;Quoted=$commandText.StartsWith('"')}
}

function Get-INodeExecutableFingerprint {
    param([Parameter(Mandatory=$true)][string]$Path)
    if(-not [IO.File]::Exists($Path)){throw 'OriginalInstallationFileMissing'}
    $stream=$null;$reader=$null;$sha=$null
    try{
        $stream=[IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
        $reader=[IO.BinaryReader]::new($stream)
        if($stream.Length -lt 64 -or $reader.ReadUInt16() -ne 0x5A4D){throw 'OriginalInstallationFileInvalid'}
        $stream.Position=60
        $peOffset=$reader.ReadInt32()
        if($peOffset -lt 64 -or $peOffset -gt ($stream.Length-24)){throw 'OriginalInstallationFileInvalid'}
        $stream.Position=$peOffset
        if($reader.ReadUInt32() -ne 0x00004550){throw 'OriginalInstallationFileInvalid'}
        $stream.Position=0
        $sha=[Security.Cryptography.SHA256]::Create()
        return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','')
    }catch{
        if($_.Exception.Message -eq 'OriginalInstallationFileInvalid'){throw}
        throw 'OriginalInstallationUnreadable'
    }finally{
        if($null -ne $sha){$sha.Dispose()}
        if($null -ne $reader){$reader.Dispose()}elseif($null -ne $stream){$stream.Dispose()}
    }
}

function Get-INodeInstallation {
    try{$services=@(Get-CimInstance Win32_Service -Filter "Name='INODE_SVR_SERVICE'" -ErrorAction Stop)}
    catch{throw 'OriginalServiceQueryFailed'}
    if($services.Count -eq 0){throw 'OriginalServiceMissing'}
    if($services.Count -ne 1 -or $services[0].Name -ine 'INODE_SVR_SERVICE'){throw 'OriginalServiceIdentityChanged'}
    $service=$services[0]
    if([string]::IsNullOrWhiteSpace($service.PathName)){throw 'OriginalServiceCommandUnsupported'}
    $command=ConvertFrom-INodeServiceCommand $service.PathName
    if(-not $command.Quoted){
        # SCM accepts legacy unquoted paths. Refuse only when an existing file
        # could win Windows' executable-prefix resolution before iNodeMon.exe.
        foreach($space in [regex]::Matches($command.BinaryPath,'\s')){
            $prefix=$command.BinaryPath.Substring(0,$space.Index)
            if([IO.File]::Exists($prefix) -or [IO.File]::Exists($prefix+'.exe')){
                throw 'OriginalServicePathAmbiguous'
            }
        }
    }
    $fingerprint=Get-INodeExecutableFingerprint $command.BinaryPath
    # An unquoted path with spaces may resolve to a different executable in
    # Windows. Check the actual running image instead of trusting its name.
    if($service.PSObject.Properties['ProcessId'] -and $service.ProcessId -gt 0){
        try{$process=Get-CimInstance Win32_Process -Filter ("ProcessId="+[int]$service.ProcessId) -ErrorAction Stop}
        catch{throw 'OriginalServiceQueryFailed'}
        if($null -eq $process -or [string]::IsNullOrWhiteSpace($process.ExecutablePath)){
            throw 'OriginalInstallationUnreadable'
        }
        if([IO.Path]::GetFullPath($process.ExecutablePath) -ine $command.BinaryPath){throw 'OriginalServiceIdentityChanged'}
    }
    [pscustomobject]@{
        Service=$service;BinaryPath=$command.BinaryPath;Arguments=$command.Arguments;BinarySha256=$fingerprint
        ClientPath=(Join-Path ([IO.Path]::GetDirectoryName($command.BinaryPath)) 'iNode Client.exe')
    }
}

function Get-INodeClientPath { (Get-INodeInstallation).ClientPath }

function Test-INodeServiceIdentity {
    param([Parameter(Mandatory=$true)]$Original,[Parameter(Mandatory=$true)]$Current)
    if($Original.Name -ine $Current.Name -or $Original.StartMode -ine $Current.StartMode){return $false}
    try{
        $before=ConvertFrom-INodeServiceCommand $Original.Path
        $after=ConvertFrom-INodeServiceCommand $Current.Path
        if($before.BinaryPath -ine $after.BinaryPath -or $before.Arguments -cne $after.Arguments){return $false}
        # Older saved recovery reports have no fingerprint. Their registered
        # identity must still match; new reports also protect the actual file.
        if($Original.PSObject.Properties['BinarySha256']){
            if(-not $Current.PSObject.Properties['BinarySha256'] -or
                $Original.BinarySha256 -cne $Current.BinarySha256){return $false}
        }
        return $true
    }catch{return $false}
}

Export-ModuleMember -Function ConvertFrom-INodeServiceCommand,Get-INodeExecutableFingerprint,Get-INodeInstallation,Get-INodeClientPath,Test-INodeServiceIdentity
