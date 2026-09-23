#ifndef Payload
  #error Payload is required
#endif
#ifndef Output
  #error Output is required
#endif
[Setup]
AppId={{D6B4AC2E-5173-4FE7-AD87-B3E752602C5A}
AppName=SPIKES Studio
AppVersion=0.3.0-beta.1
AppVerName=SPIKES Studio 0.3.0-beta.1 Engineering Preview
DefaultDirName={localappdata}\Programs\SPIKES Studio
DefaultGroupName=SPIKES Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#Output}
OutputBaseFilename=SPIKES-Studio-0.3.0-beta.1-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=spikes-studio.ico
UninstallDisplayIcon={app}\SPIKES-Studio.exe
DisableProgramGroupPage=yes
CloseApplications=no
[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\SPIKES Studio"; Filename: "{app}\SPIKES-Studio.exe"
Name: "{autodesktop}\SPIKES Studio"; Filename: "{app}\SPIKES-Studio.exe"; Tasks: desktopicon
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
[Run]
Filename: "{app}\SPIKES-Studio.exe"; Description: "Launch SPIKES Studio"; Flags: nowait postinstall skipifsilent
