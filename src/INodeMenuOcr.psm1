Set-StrictMode -Version Latest

function Get-INodeMenuText {
    param([string]$ImagePath,[ValidateSet('menu','dialog')][string]$Kind='menu')
    $python=$env:CAMPUS_TERMINAL_OCR_PYTHON
    if(-not $python){
        $command=Get-Command python.exe -ErrorAction SilentlyContinue
        if($command){$python=$command.Source}
    }
    if(-not $python){throw 'Local offline OCR runtime unavailable.'}
    if(-not [IO.File]::Exists($python)){throw 'Local offline OCR runtime unavailable.'}
    $start=[Diagnostics.ProcessStartInfo]::new()
    $start.FileName=$python
    $start.Arguments='"{0}" "{1}" {2}' -f (Join-Path $PSScriptRoot 'inode_menu_ocr.py'),$ImagePath,$Kind
    $start.UseShellExecute=$false;$start.CreateNoWindow=$true
    $start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    $p=[Diagnostics.Process]::Start($start)
    try {
        $stdout=$p.StandardOutput.ReadToEndAsync();$stderr=$p.StandardError.ReadToEndAsync()
        if(-not $p.WaitForExit(10000)){$p.Kill();$p.WaitForExit();throw 'Offline menu OCR timed out.'}
        if($p.ExitCode -ne 0){throw "Offline menu OCR failed: $($stderr.Result)"}
        $decoded=$stdout.Result | ConvertFrom-Json
        foreach($line in $decoded){$line}
    } finally {$p.Dispose()}
}
function Get-INodeExitTextTarget {
    param([object[]]$Lines)
    $expected=@("$([char]0x663e)$([char]0x793a)$([char]0x5feb)$([char]0x6377)$([char]0x680f)",
        "$([char]0x7f51)$([char]0x7edc)$([char]0x63a5)$([char]0x5165)","$([char]0x5173)$([char]0x4e8e)","$([char]0x9000)$([char]0x51fa)")
    if($Lines.Count -ne 4){throw 'Unrecognized menu: expected exactly four text lines.'}
    $ordered=@($Lines | Sort-Object Y)
    for($i=0;$i -lt 4;$i++){
        if($ordered[$i].Text -cne $expected[$i] -or $ordered[$i].Confidence -lt 0.60){throw "Unrecognized menu line $i"}
    }
    return $ordered[3]
}
function Get-INodeExitConfirmationTarget {
    param([object[]]$Lines)
    $expected=@([regex]::Unescape('\u66a8\u5357\u5927\u5b66\u6821\u56ed\u7f51'),
        [regex]::Unescape('\u76ee\u524d\u6709\u5728\u7ebf\u7684\u8fde\u63a5\uff0c\u9000\u51faiNode\u667a\u80fd\u5ba2\u6237\u7aef\u5c06\u65ad\u5f00\u4e0e\u7f51\u7edc\u7684\u8fde\u63a5\u3002'),
        [regex]::Unescape('\u786e\u5b9e\u8981\u9000\u51fa\u5417\uff1f'),
        [regex]::Unescape('\u662f(Y)'),
        [regex]::Unescape('\u5426(N)'))
    if($Lines.Count -ne 5){throw 'Unexpected exit confirmation content.'}
    foreach($text in @($expected[0],$expected[1],$expected[2],$expected[4])){
        $matching=@($Lines | Where-Object {$_.Text -ceq $text -and $_.Confidence -ge 0.7})
        if($matching.Count -ne 1){throw 'Exit warning or yes/no labels were not recognized exactly.'}
    }
    $yesPattern='^'+[char]0x662f+'(?:\([Yy]?\))?$'
    $yesMatches=@($Lines | Where-Object {$_.Text -match $yesPattern -and $_.Confidence -ge 0.6})
    if($yesMatches.Count -ne 1){throw 'Exit confirmation yes button is ambiguous.'}
    $yes=$yesMatches[0]
    $no=@($Lines | Where-Object Text -CEQ $expected[4])[0]
    if($yes.X -ge $no.X -or [math]::Abs($yes.Y-$no.Y) -gt 30){throw 'Unexpected confirmation button layout.'}
    return $yes
}
Export-ModuleMember -Function Get-INodeMenuText,Get-INodeExitTextTarget,Get-INodeExitConfirmationTarget
