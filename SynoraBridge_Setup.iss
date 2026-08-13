; Synora Bridge — setup installer (Inno Setup 6)
;
; Wraps the ALL-IN-ONE PyInstaller build (dist\allinone\SynoraBridge\ — the
; exe + backend + every dependency + frontend build + node, self-contained)
; into a setup wizard.
;
; Version/names come from launcher\build.properties (single source of truth) —
; build_installer.bat reads them and passes them here via /D overrides.
;
; Compile:  build_installer.bat

#define MyAppName "Synora Bridge"
#ifndef MyAppVersion
  #define MyAppVersion "6.0"
#endif
#ifndef MyExeName
  #define MyExeName "SynoraBridge_Launcher.exe"
#endif

[Setup]
AppId={{B3E1D2A0-5C4B-4E7F-9A8C-2D1F0A3B6C4D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=SynoraStudio
AppVerName={#MyAppName} {#MyAppVersion}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=SynoraBridge_Setup_{#MyAppVersion}
OutputDir=dist
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; The complete all-in-one folder (launcher + backend + deps + frontend + node)
Source: "dist\allinone\SynoraBridge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
