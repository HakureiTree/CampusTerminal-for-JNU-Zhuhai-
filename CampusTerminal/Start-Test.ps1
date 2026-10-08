# SPDX-License-Identifier: GPL-3.0-or-later
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$csproj = Join-Path $root 'core\CampusTerminal.Core.csproj'
$config = Join-Path $root 'core\NuGet.Config'
dotnet build $csproj -c Release --configfile $config
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$env:PYTHONIOENCODING = 'utf-8'
python (Join-Path $root 'run.py') @args
