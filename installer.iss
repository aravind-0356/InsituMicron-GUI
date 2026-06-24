; installer.iss
; Inno Setup Script for InsituMicron GUI v3.2
; Bundles the PyInstaller output, executes NI-DAQmx minimal install via nipkg, and STM32 VCP install.

#define MyAppName "InsituMicron GUI"
#define MyAppVersion "3.2"
#define MyAppPublisher "InsituMicron"
#define MyAppExeName "InsituMicronGUI.exe"

[Setup]
; App Information
AppId={{D1B4F4A5-E1A7-44E2-81D6-8F8D0B7A5C22}}
AppName={#MyAppName} Version {#MyAppVersion}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://insitumicron.com/
AppSupportURL=https://insitumicron.com/
AppUpdatesURL=https://insitumicron.com/
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=LICENSES\LICENSE.txt
SetupMutex=InsituMicronGUISetupMutex

; Installer executable metadata
VersionInfoVersion=3.2.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Installer
VersionInfoCopyright=Copyright (C) 2026 {#MyAppPublisher}

; Output configuration
OutputDir=Output
OutputBaseFilename=InsituMicron_GUI_v{#MyAppVersion}_Setup
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; Requires admin privileges to install drivers
PrivilegesRequired=admin
MinVersion=10.0
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Main PyInstaller Output Directory
Source: "dist\InsituMicronGUI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; License Files
Source: "LICENSES\*"; DestDir: "{app}\LICENSES"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu Shortcut
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; IconIndex: 0
; Desktop Shortcut
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"; IconIndex: 0

[Run]

[Messages]
FinishedHeadingLabel=Setup has finished installing [name].
FinishedLabel=Please Note:%n%n1. CAMERA DRIVER (Required for imaging):%n   The Spinnaker SDK is NOT included. Download from Teledyne FLIR.%n%n2. LGPL COMPLIANCE:%n   PySide6 is licensed under LGPL v3. See {app}\LICENSES\ for details.%n%nA system restart may be required before first use.

[Code]
