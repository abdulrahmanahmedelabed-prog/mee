; Inno Setup script — builds a professional Windows installer (Setup.exe) for customers.
; 1) Build the program first:  build_exe.bat   (output: dist\ShopAccounting)
; 2) Install Inno Setup (free) and open this file, then press Compile.
; 3) Optional: sign Setup.exe with your code-signing certificate (signtool) to avoid SmartScreen warnings.

#define AppName "Shop Accounting & POS"
#define AppVersion "10.0"
#define AppPublisher "Your Company"
#define AppExe "ShopAccounting.exe"

[Setup]
AppId={{8F4C2B1E-6A3D-4E7B-9C21-5D0A7E3F1B64}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName=C:\ShopAccounting
DefaultGroupName={#AppName}
OutputDir=..\dist\installer
OutputBaseFilename=ShopAccounting-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
; data\ (database, backups, license) is never removed on uninstall or overwritten on update
UninstallDisplayIcon={app}\{#AppExe}

[Languages]
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\ShopAccounting\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "data\*"

[Dirs]
Name: "{app}\data"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{app}\demo_data"; Permissions: users-modify

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
; نسخة التدريب: بيانات سوبرماركت تجريبية في مجلد منفصل، لتعليم الموظفين دون المساس ببيانات المحل
Name: "{group}\{#AppName} (Training)"; Filename: "{app}\{#AppExe}"; Parameters: "--demo"

[Run]
; allow the local network service (multi-till, owner dashboard, online store, staff mobile app)
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""{#AppName}"" dir=in action=allow program=""{app}\{#AppExe}"" enable=yes profile=private"; Flags: runhidden
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
