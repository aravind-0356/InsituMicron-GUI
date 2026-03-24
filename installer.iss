; InsituMicron GUI Installer Script
; Inno Setup Script - Version 6.x

#define MyAppName "InsituMicron GUI"
#define MyAppVersion "2.1.1"
#define MyAppPublisher "InsituMicron"
#define MyAppURL "https://insitumicron.com/"
#define MyAppExeName "InsituMicronGUI.exe"

[Setup]
; Application info
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Installation settings
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=LICENSES\LICENSE.txt

; Output settings
OutputDir=installer_output
OutputBaseFilename=InsituMicronGUI_Setup_{#MyAppVersion}

; Compression
Compression=lzma2/ultra64
SolidCompression=yes

; Appearance - Icons and branding
SetupIconFile=app_icon.ico
WizardStyle=modern
WizardImageFile=wizard_image.bmp
WizardSmallImageFile=wizard_small.bmp

; Privileges
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; Architecture
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main application files from PyInstaller output
Source: "dist\InsituMicronGUI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Copy icon to root of app folder for shortcuts
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start menu shortcut - use EXE's embedded icon
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; IconIndex: 0
; Uninstall shortcut in Start menu
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
; Desktop shortcut
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; IconIndex: 0; Tasks: desktopicon

[Run]
; Option to launch app after installation
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up log files on uninstall
Type: filesandordirs; Name: "{app}\logs"

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nFor camera functionality, please ensure the FLIR Spinnaker SDK is installed separately from https://www.flir.com/products/spinnaker-sdk/
