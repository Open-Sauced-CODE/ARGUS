; ARGUS Desktop User-Mode Windows Installer (Zero Admin UAC Prompt)
#define MyAppName "ARGUS Desktop"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "ARGUS Zero-Egress Security"
#define MyAppURL "http://ec2-13-201-224-53.ap-south-1.compute.amazonaws.com/"
#define MyAppExeName "ARGUS.exe"

[Setup]
AppId={{8E9A54D1-7C1E-4249-9B83-A1C9E2026A01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={localappdata}\ARGUS-Desktop
DisableDirPage=no
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
OutputDir=..\releases\files
OutputBaseFilename=ARGUS-Desktop-Setup-v2.0.0-win64
SetupIconFile=argus.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\ARGUS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
