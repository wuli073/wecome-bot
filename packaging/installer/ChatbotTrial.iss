#define AppName "Chatbot Trial"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourcePortableRoot
  #define SourcePortableRoot "C:\Chatbot-Trial-Portable"
#endif
#ifndef OutputRoot
  #define OutputRoot "C:\Chatbot-Trial-Output"
#endif

[Setup]
AppId={{2A66BFC0-65B1-4D2F-93A1-9B4A62A0C9C8}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=LangBot
DefaultDirName={localappdata}\Programs\Chatbot Trial
DefaultGroupName=Chatbot Trial
UninstallDisplayIcon={app}\ChatbotLauncher.exe
OutputDir={#OutputRoot}
OutputBaseFilename=Chatbot-Setup-{#AppVersion}-x64
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
WizardStyle=modern
DisableProgramGroupPage=no
CloseApplications=yes
CloseApplicationsFilter=ChatbotLauncher.exe
AppMutex=Local\ChatbotLauncher.Trial
ChangesAssociations=no
DisableDirPage=no
DisableReadyMemo=no
AllowNoIcons=yes

[Languages]
Name: "zhHans"; MessagesFile: "ChineseSimplified.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourcePortableRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Chatbot Trial"; Filename: "{app}\ChatbotLauncher.exe"
Name: "{autodesktop}\Chatbot Trial"; Filename: "{app}\ChatbotLauncher.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\prerequisites\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "{cm:InstallingPrerequisites}"; Flags: waituntilterminated runhidden; Check: ShouldRunVcRedist
Filename: "{app}\ChatbotLauncher.exe"; Description: "{cm:LaunchProgram,Chatbot Trial}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[CustomMessages]
en.InstallingPrerequisites=Installing VC++ prerequisite...
zhHans.InstallingPrerequisites=Installing VC++ prerequisite...
en.RemoveUserDataPrompt=Remove user data from {localappdata}\Chatbot as well?
zhHans.RemoveUserDataPrompt=Remove user data from {localappdata}\Chatbot as well?
en.SmartScreenNotice=This installer is unsigned. If SmartScreen warns, choose "More info" and then "Run anyway" only after verifying the file source.
zhHans.SmartScreenNotice=This installer is unsigned. If SmartScreen warns, choose "More info" and then "Run anyway" only after verifying the file source.

[Code]
function ShouldRunVcRedist(): Boolean;
var
  Installed: Cardinal;
begin
  Result :=
    FileExists(ExpandConstant('{app}\prerequisites\vc_redist.x64.exe')) and
    ((not RegQueryDWordValue(HKLM64, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Installed)) or (Installed <> 1));
end;

procedure InitializeWizard;
begin
  WizardForm.WelcomeLabel2.Caption :=
    WizardForm.WelcomeLabel2.Caption + #13#10#13#10 + ExpandConstant('{cm:SmartScreenNotice}');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    if MsgBox(ExpandConstant('{cm:RemoveUserDataPrompt}'), mbConfirmation, MB_YESNO) = IDYES then
    begin
      DelTree(ExpandConstant('{localappdata}\Chatbot'), True, True, True);
    end;
  end;
end;
