# SPDX-License-Identifier: GPL-3.0-or-later
# Replace only the files named in a transaction, then relaunch. Never touches user state.
param([Parameter(Mandatory=$true)][string]$Transaction)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-Inside([string]$Child, [string]$Parent) {
    $full = [IO.Path]::GetFullPath($Child)
    $root = [IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    return $full.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)
}

function Test-Protected([string]$Install, [string]$Dest) {
    $root = [IO.Path]::GetFullPath($Install).TrimEnd('\')
    $full = [IO.Path]::GetFullPath($Dest)
    $rel = $full.Substring($root.Length).TrimStart('\')
    $leaf = [IO.Path]::GetFileName($rel)
    if ($leaf -eq 'edition.txt' -or $leaf -eq 'CampusTerminal.portable') { return $true }
    $first = $rel.Split('\')[0]
    return $first -in @('state', 'logs', 'payload')
}

function Write-Result([string]$Path, [bool]$Ok, [string]$ErrorText) {
    $dir = Split-Path -Parent $Path
    if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $payload = @{ ok = $Ok; error = $ErrorText } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText($Path, $payload, [Text.UTF8Encoding]::new($false))
}

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
    } finally {
        $algorithm.Dispose()
        $stream.Dispose()
    }
}

function Start-Relaunch($Spec) {
    $exe = [string]$Spec.relaunch
    if (-not $exe -or -not (Test-Path -LiteralPath $exe)) { return }
    $args = @()
    if ($Spec.relaunch_args) { $args = @($Spec.relaunch_args) }
    Start-Process -FilePath $exe -ArgumentList $args -WorkingDirectory ([string]$Spec.install_root) | Out-Null
}

$spec = [IO.File]::ReadAllText((Resolve-Path -LiteralPath $Transaction), [Text.UTF8Encoding]::new($false)) | ConvertFrom-Json
$install = [IO.Path]::GetFullPath([string]$spec.install_root)
$staging = [IO.Path]::GetFullPath([string]$spec.staging_root)
$result = [string]$spec.result_path
$backup = [IO.Path]::GetFullPath([string]$spec.backup_root)
if (-not $result) { throw 'result_path missing' }

try {
    foreach ($file in @($spec.files)) {
        $src = [IO.Path]::GetFullPath([string]$file.src)
        $dest = [IO.Path]::GetFullPath([string]$file.dest)
        if (-not (Test-Inside $src $staging) -or -not (Test-Inside $dest $install)) { throw 'path escape' }
        if (Test-Protected $install $dest) { throw 'protected path' }
        if (-not (Test-Path -LiteralPath $src -PathType Leaf)) { throw 'source missing' }
        $expect = ([string]$file.sha256).ToLowerInvariant()
        if ($expect -notmatch '^[0-9a-f]{64}$') { throw 'bad hash' }
    }
    $deadline = (Get-Date).AddSeconds(90)
    foreach ($procId in @($spec.wait_pids)) {
        if (-not $procId) { continue }
        while (Get-Process -Id ([int]$procId) -ErrorAction SilentlyContinue) {
            if ((Get-Date) -gt $deadline) { throw 'wait timeout' }
            Start-Sleep -Milliseconds 200
        }
    }
    foreach ($name in @($spec.wait_names)) {
        if (-not $name) { continue }
        $pending = $true
        while ($pending) {
            $pending = $false
            foreach ($proc in @(Get-Process -Name ([string]$name) -ErrorAction SilentlyContinue)) {
                $path = $null
                try { $path = $proc.Path } catch { $path = $null }
                if ($path -and (Test-Inside $path $install)) { $pending = $true }
            }
            if ($pending) {
                if ((Get-Date) -gt $deadline) { throw 'wait timeout' }
                Start-Sleep -Milliseconds 200
            }
        }
    }
    New-Item -ItemType Directory -Force -Path $backup | Out-Null
    $records = New-Object System.Collections.Generic.List[object]
    try {
        foreach ($file in @($spec.files)) {
            $dest = [IO.Path]::GetFullPath([string]$file.dest)
            $src = [IO.Path]::GetFullPath([string]$file.src)
            $existed = Test-Path -LiteralPath $dest -PathType Leaf
            $saved = $null
            if ($existed) {
                $saved = Join-Path $backup ([guid]::NewGuid().ToString('N'))
                Copy-Item -LiteralPath $dest -Destination $saved -Force
            } else {
                New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
            }
            $records.Add([pscustomobject]@{ dest = $dest; backup = $saved; existed = $existed })
            Copy-Item -LiteralPath $src -Destination $dest -Force
            $hash = Get-Sha256 $dest
            if ($hash -ne ([string]$file.sha256).ToLowerInvariant()) { throw 'hash mismatch' }
        }
    } catch {
        foreach ($record in $records) {
            if ($record.existed -and $record.backup) {
                Copy-Item -LiteralPath $record.backup -Destination $record.dest -Force
            } elseif (-not $record.existed -and (Test-Path -LiteralPath $record.dest)) {
                Remove-Item -LiteralPath $record.dest -Force
            }
        }
        throw
    }
    Write-Result $result $true ''
    if (Test-Path -LiteralPath $backup) {
        Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue
    }
    Start-Relaunch $spec
} catch {
    Write-Result $result $false ([string]$_.Exception.Message)
    Start-Relaunch $spec
    exit 1
}
