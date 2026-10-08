# SPDX-License-Identifier: GPL-3.0-or-later
# Open the GUI only. Does not rebuild, stop iNode, or start a live trial.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONIOENCODING = 'utf-8'
$pythonw = Join-Path (Split-Path (Get-Command python).Source) 'pythonw.exe'
if (-not (Test-Path $pythonw)) { $pythonw = (Get-Command python).Source }
Start-Process -FilePath $pythonw -ArgumentList "`"$root\run.py`"" -WorkingDirectory (Split-Path $root)
