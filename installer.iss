; installer.iss
; Inno Setup Script for InsituMicron GUI v3.1.2
; Bundles the PyInstaller output, executes NI-DAQmx minimal install via nipkg, and STM32 VCP install.

#define MyAppName "InsituMicron GUI"
#define MyAppVersion "3.1.2"
#define MyAppPublisher "InsituMicron"
#define MyAppExeName "InsituMicronGUI.exe"

[Setup]
; App Information
AppId={{D1B4F4A5-E1A7-44E2-81D6-8F8D0B7A5C22}}
AppName={#MyAppName} Version {#MyAppVersion}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
; Output configuration
OutputDir=Output
OutputBaseFilename=InsituMicron_GUI_v{#MyAppVersion}_Setup
SetupIconFile=app_icon.ico
Compression=lzma
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
; Driver Installers (extracted to temp dir during install)
Source: "drivers\stsw-stm32102\VCP_V1.5.0_Setup_W8_x64_64bits.exe"; DestDir: "{tmp}"; Flags: ignoreversion
Source: "drivers\NIPackageManager26.0.0_online.exe"; DestDir: "{tmp}"; Flags: ignoreversion; DestName: "nipkgsetup.exe"; Check: NeedsNipkg

[Icons]
; Start Menu Shortcut
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; IconIndex: 0
; Desktop Shortcut
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"; IconIndex: 0

[Run]
; 1. Run the STM32 VCP Driver installer silently
Filename: "{tmp}\VCP_V1.5.0_Setup_W8_x64_64bits.exe"; Parameters: "/S"; StatusMsg: "Installing STM32 Virtual COM Port Driver..."; Flags: waituntilterminated; Check: NeedsSTM32Driver

[Messages]
FinishedHeadingLabel=Setup has finished installing [name].
FinishedLabel=Please Note:%n%n1. CAMERA DRIVER (Required for imaging):%n   The Spinnaker SDK is NOT included. Download from Teledyne FLIR.%n%n2. LGPL COMPLIANCE:%n   PySide6 is licensed under LGPL v3. See {app}\LICENSES\ for details.%n%nA system restart may be required before first use.

[Code]
function NeedsSTM32Driver(): Boolean;
var
  Installed: Boolean;
begin
  Installed := 
    RegKeyExists(HKLM, 'SOFTWARE\STMicroelectronics\Virtual COM Port Driver') or
    RegKeyExists(HKLM, 'SOFTWARE\WOW6432Node\STMicroelectronics\Virtual COM Port Driver');

  if Installed then
    Log('NeedsSTM32Driver: STM32 VCP driver already installed — skipping.')
  else
    Log('NeedsSTM32Driver: STM32 VCP driver not found — will install.');

  Result := not Installed;
end;

function NeedsNIDAQmx(): Boolean;
var
  Installed: Boolean;
begin
  Installed := RegKeyExists(HKLM, 'SOFTWARE\National Instruments\NI-DAQmx') or
               RegKeyExists(HKLM, 'SOFTWARE\WOW6432Node\National Instruments\NI-DAQmx');
  
  if Installed then
    Log('NeedsNIDAQmx: NI-DAQmx is already installed.')
  else
    Log('NeedsNIDAQmx: NI-DAQmx is NOT installed. Proceeding with installation.');
    
  Result := not Installed;
end;

function NeedsNipkg(): Boolean;
var
  NipkgExists: Boolean;
begin
  // Check standard installation paths for nipkg.exe
  NipkgExists := FileExists(ExpandConstant('{pf}\National Instruments\NI Package Manager\nipkg.exe')) or
                 FileExists(ExpandConstant('{pf32}\National Instruments\NI Package Manager\nipkg.exe'));
                 
  if NipkgExists then
    Log('NeedsNipkg: NI Package Manager is already installed.')
  else
    Log('NeedsNipkg: NI Package Manager is NOT installed.');
    
  Result := (not NipkgExists) and NeedsNIDAQmx();
end;

function GetNipkgPath(Param: String): String;
var
  Path64, Path32: String;
begin
  Path64 := ExpandConstant('{pf}\National Instruments\NI Package Manager\nipkg.exe');
  Path32 := ExpandConstant('{pf32}\National Instruments\NI Package Manager\nipkg.exe');
  
  if FileExists(Path64) then
  begin
    Log('GetNipkgPath: Found nipkg.exe at: ' + Path64);
    Result := Path64;
  end
  else if FileExists(Path32) then
  begin
    Log('GetNipkgPath: Found nipkg.exe at: ' + Path32);
    Result := Path32;
  end
  else
  begin
    Log('GetNipkgPath: ERROR: nipkg.exe not found in standard paths. Falling back to PATH lookup.');
    Result := 'nipkg.exe';
  end;
end;

procedure InstallNIDrivers();
var
  ResultCode: Integer;
  NipkgPath: String;
begin
  // 1. Install NI Package Manager
  if NeedsNipkg() then
  begin
    WizardForm.StatusLabel.Caption := 'Installing NI Package Manager...';
    if Exec(ExpandConstant('{tmp}\nipkgsetup.exe'), '--quiet --accept-eulas --prevent-reboot', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    begin
      if ResultCode <> 0 then
        Log('NI Package Manager install failed with code: ' + IntToStr(ResultCode));
    end;
  end;

  // 2. Install NI-DAQmx Packages
  if NeedsNIDAQmx() then
  begin
    NipkgPath := GetNipkgPath('');
    // SW_SHOW without -y allows the user to see and accept the NI EULA manually (Legal Requirement)
    if Exec(NipkgPath, 'install ni-daqmx-runtime ni-daqmx-system-api ni-daqmx-usb-support --prevent-reboot', '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then
    begin
      if ResultCode = 0 then
        Log('NI-DAQmx Drivers installed successfully.')
      else
        MsgBox('Warning: NI-DAQmx driver installation failed (Code: ' + IntToStr(ResultCode) + ').' + #13#10 + 
               'Please ensure you have internet access and try running the installer again.', mbCriticalError, MB_OK);
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    // Run after internal files are extracted but before the progress page finishes
    InstallNIDrivers();
  end;
end;
