; Inno Setup: installs Bilge for the current user, without administrator rights.
;   iscc /DVersion=0.1.0 packaging\windows\bilge.iss
#ifndef Version
  #define Version "0.1.0"
#endif

[Setup]
AppId={{6C0F2A8E-6F0B-4C3B-9C51-2B1D0E7A4B11}
AppName=Bilge
AppVersion={#Version}
AppPublisher=Coders Society
AppPublisherURL=https://github.com/coderssociety/bilge-desktop
DefaultDirName={localappdata}\Programs\Bilge
DefaultGroupName=Bilge
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=Bilge-Setup-{#Version}
SetupIconFile=..\..\build\bilge.ico
UninstallDisplayIcon={app}\Bilge.exe
LicenseFile=..\..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
; Bilge holds this while it runs, so setup and uninstall ask to close it first.
AppMutex=BilgeAppMutex

[Languages]
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "{cm:AutoStart}"; Flags: checkedonce

[CustomMessages]
tr.AutoStart=Bilgisayar açılınca Bilge'yi başlat
en.AutoStart=Start Bilge when the computer starts
tr.Launch=Bilge'yi şimdi başlat
en.Launch=Start Bilge now

[Files]
Source: "..\..\dist\Bilge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; The app id lets Windows show Bilge's notifications under its own name.
Name: "{userprograms}\Bilge"; Filename: "{app}\Bilge.exe"; AppUserModelID: "CodersSociety.Bilge"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Bilge"; \
    ValueData: """{app}\Bilge.exe"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Bilge.exe"; Description: "{cm:Launch}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c taskkill /im Bilge.exe /f & taskkill /im bilge-cli.exe /f"; Flags: runhidden; \
    RunOnceId: "StopBilge"
