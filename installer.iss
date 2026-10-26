; Inno Setup script for LuckyTwitch (Windows installer)
; Build with:  iscc /DAppVersion=1.0 installer.iss   (run after PyInstaller)
; Pre-release versions (containing '-', e.g. v0.8.0-beta.1) get their own AppId and install folder
; so they can be installed side-by-side without overwriting a stable LuckyTwitch installation.
#ifndef AppVersion
  #define AppVersion "1.0"
#endif

#if Pos("-", AppVersion) > 0
  #define EffectiveAppId "{{9C4A8D2E-7B1F-4E63-8A5D-3F2E1C9B7D44}"
  #define EffectiveAppName "LuckyTwitch (Beta)"
  #define EffectiveDirName "LuckyTwitch-Beta"
#else
  #define EffectiveAppId "{{6E2B6B0C-3F0D-4C57-9B6A-1A7C2E0D4F11}"
  #define EffectiveAppName "LuckyTwitch"
  #define EffectiveDirName "LuckyTwitch"
#endif

[Setup]
AppId={#EffectiveAppId}
AppName={#EffectiveAppName}
AppVersion={#AppVersion}
AppPublisher=LuckyTwitch
; Per-user install: no admin rights needed, goes to %LOCALAPPDATA%\Programs\LuckyTwitch (or LuckyTwitch-Beta)
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#EffectiveDirName}
DefaultGroupName={#EffectiveAppName}
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
Name: "weblinks"; Description: "Open luckytwitch:// links from web pages with LuckyTwitch"; GroupDescription: "Links:"

[Files]
Source: "dist\LuckyTwitch\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

; Web pages can offer luckytwitch:// links. Per user (HKCU), so no admin rights; the app writes the same
; entries from Options > Tools > Links from web pages (see weblink.py: the command must stay identical).
[Registry]
Root: HKCU; Subkey: "Software\Classes\luckytwitch"; ValueType: string; ValueName: ""; ValueData: "URL:LuckyTwitch Link"; Flags: uninsdeletekey; Tasks: weblinks
Root: HKCU; Subkey: "Software\Classes\luckytwitch"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""; Tasks: weblinks
Root: HKCU; Subkey: "Software\Classes\luckytwitch\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\LuckyTwitch.exe,0"; Tasks: weblinks
Root: HKCU; Subkey: "Software\Classes\luckytwitch\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\LuckyTwitch.exe"" ""%1"""; Tasks: weblinks

[Icons]
Name: "{autoprograms}\{#EffectiveAppName}"; Filename: "{app}\LuckyTwitch.exe"
Name: "{autodesktop}\{#EffectiveAppName}"; Filename: "{app}\LuckyTwitch.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\LuckyTwitch.exe"; Description: "Launch {#EffectiveAppName}"; Flags: nowait postinstall skipifsilent
