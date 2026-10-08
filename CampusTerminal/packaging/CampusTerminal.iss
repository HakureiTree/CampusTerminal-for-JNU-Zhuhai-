; SPDX-License-Identifier: GPL-3.0-or-later
#ifndef SourceDir
  #error SourceDir must point to a Publish.ps1 output directory
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
#ifndef AppVersion
  #error AppVersion is required
#endif

[Setup]
AppId={{22A00E5D-F71E-46CC-91B7-492D85C8622D}
AppName=开源暨珠有线网络终端
AppVersion={#AppVersion}
AppVerName=开源暨珠有线网络终端 {#AppVersion}
DefaultDirName={localappdata}\Programs\CampusTerminal
DefaultGroupName=开源暨珠有线网络终端
AllowNoIcons=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=CampusTerminal-{#AppVersion}-windows-x64-setup
SetupIconFile=..\gui\assets\icons\app\app.ico
UninstallDisplayIcon={app}\开源暨珠有线网络终端.exe
LicenseFile={#SourceDir}\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "\edition.txt,\CampusTerminal.portable,\state,\logs,\payload,*.pdb,*.pyc,__pycache__"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "installed-edition.txt"; DestDir: "{app}"; DestName: "edition.txt"; Flags: ignoreversion

[Dirs]
Name: "{app}\payload"

[Icons]
Name: "{group}\开源暨珠有线网络终端"; Filename: "{app}\开源暨珠有线网络终端.exe"; WorkingDir: "{app}"
Name: "{group}\卸载开源暨珠有线网络终端"; Filename: "{uninstallexe}"
Name: "{userdesktop}\开源暨珠有线网络终端"; Filename: "{app}\开源暨珠有线网络终端.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\开源暨珠有线网络终端.exe"; Description: "启动开源暨珠有线网络终端"; Flags: postinstall nowait skipifsilent unchecked

[UninstallRun]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\Remove-Installation.ps1"" -Root ""{app}"""; Flags: runhidden waituntilterminated; RunOnceId: "RemoveOwnedStartup"

[Code]
function CheckStopped(Root: String): Boolean;
var
  ExitCode: Integer;
begin
  Result := True;
  if FileExists(Root + '\Remove-Installation.ps1') then
    Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "' +
      Root + '\Remove-Installation.ps1" -Root "' + Root + '" -CheckOnly',
      Root, SW_HIDE, ewWaitUntilTerminated, ExitCode) and (ExitCode = 0);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not CheckStopped(ExpandConstant('{app}')) then
    Result := '请先从托盘退出此目录的终端，等待后台停止后再安装。';
end;

function InitializeUninstall: Boolean;
begin
  Result := CheckStopped(ExpandConstant('{app}'));
  if not Result then
    SuppressibleMsgBox('请先从托盘退出终端，等待后台停止后再卸载。', mbError, MB_OK, IDOK);
end;
