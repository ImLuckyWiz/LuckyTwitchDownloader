; Inno Setup script for LuckyTwitch (Windows installer)
; Build with:  iscc /DAppVersion=1.0 installer.iss   (run after PyInstaller)
#ifndef AppVersion
  #define AppVersion "1.0"
#endif

[Setup]
AppId={{6E2B6B0C-3F0D-4C57-9B6A-1A7C2E0D4F11}
AppName=LuckyTwitch
AppVersion={#AppVersion}
AppPublisher=LuckyTwitch
; Per-user install: no admin rights needed, goes to %LOCALAPPDATA%\Programs\LuckyTwitch
PrivilegesRequired=lowest
DefaultDirName={autopf}\LuckyTwitch
DefaultGroupName=LuckyTwitch
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=LuckyTwitch-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\LuckyTwitch.exe
SetupIconFile=assets\icon.ico
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\LuckyTwitch\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\LuckyTwitch"; Filename: "{app}\LuckyTwitch.exe"
Name: "{autodesktop}\LuckyTwitch"; Filename: "{app}\LuckyTwitch.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\LuckyTwitch.exe"; Description: "Launch LuckyTwitch"; Flags: nowait postinstall skipifsilent
