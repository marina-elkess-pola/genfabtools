; Inno Setup script: per-user installer for OccuCalc Revit integration
; Build with Inno Setup (Inno Setup 6+)

[Setup]
AppName=OccuCalc Revit Integration
AppVersion=0.1
DefaultDirName={localappdata}\OccuCalc
DisableProgramGroupPage=yes
Uninstallable=yes
Compression=lzma
SolidCompression=yes
DefaultGroupName=OccuCalc

[Files]
; Helper EXE (built from tools/revit_helper)
Source: "..\revit_helper\bin\Release\net6.0\OccuCalcRevitHelper.exe"; DestDir: "{localappdata}\OccuCalc"; Flags: ignoreversion; Check: FileExists("..\revit_helper\bin\Release\net6.0\OccuCalcRevitHelper.exe")

; Revit add-in DLL and manifest - adjust paths to your built DLL(s)
; This installs the add-in into the per-user Addins folders for each year (2023-2026).
Source: "..\revit_addin\bin\Release\OccuCalcRevitAddin.dll"; DestDir: "{userappdata}\Autodesk\Revit\Addins\2023"; Flags: ignoreversion; Check: FileExists("..\revit_addin\bin\Release\OccuCalcRevitAddin.dll")
Source: "..\revit_addin\addins\2023\OccuCalcRevit.addin"; DestDir: "{userappdata}\Autodesk\Revit\Addins\2023"; Flags: ignoreversion
Source: "..\revit_addin\bin\Release\OccuCalcRevitAddin.dll"; DestDir: "{userappdata}\Autodesk\Revit\Addins\2024"; Flags: ignoreversion; Check: FileExists("..\revit_addin\bin\Release\OccuCalcRevitAddin.dll")
Source: "..\revit_addin\addins\2024\OccuCalcRevit.addin"; DestDir: "{userappdata}\Autodesk\Revit\Addins\2024"; Flags: ignoreversion
Source: "..\revit_addin\bin\Release\OccuCalcRevitAddin.dll"; DestDir: "{userappdata}\Autodesk\Revit\Addins\2025"; Flags: ignoreversion; Check: FileExists("..\revit_addin\bin\Release\OccuCalcRevitAddin.dll")
Source: "..\revit_addin\addins\2025\OccuCalcRevit.addin"; DestDir: "{userappdata}\Autodesk\Revit\Addins\2025"; Flags: ignoreversion
Source: "..\revit_addin\bin\Release\OccuCalcRevitAddin.dll"; DestDir: "{userappdata}\Autodesk\Revit\Addins\2026"; Flags: ignoreversion; Check: FileExists("..\revit_addin\bin\Release\OccuCalcRevitAddin.dll")
Source: "..\revit_addin\addins\2026\OccuCalcRevit.addin"; DestDir: "{userappdata}\Autodesk\Revit\Addins\2026"; Flags: ignoreversion

[Dirs]
Name: "{localappdata}\OccuCalc"; Flags: uninsalwaysuninstall
Name: "{localappdata}\OccuCalc\incoming"; Flags: uninsalwaysuninstall

[Registry]
; Per-user protocol registration (HKCU) so no admin is required
Root: HKCU; Subkey: "Software\Classes\occucalc-revit"; ValueType: string; ValueName: ""; ValueData: "URL:OccuCalc Revit Protocol"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\occucalc-revit"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\occucalc-revit\shell\open\command"; ValueType: string; ValueName: ""; ValueData: '""{localappdata}\OccuCalc\OccuCalcRevitHelper.exe"" ""%1""'; Flags: uninsdeletekey

[Icons]
Name: "{userdesktop}\OccuCalc Revit Helper"; Filename: "{localappdata}\OccuCalc\OccuCalcRevitHelper.exe"; WorkingDir: "{localappdata}\OccuCalc"

[Run]
; Not running Revit on install; helper will launch Revit on protocol activation.
Filename: "{localappdata}\OccuCalc\OccuCalcRevitHelper.exe"; Description: "OccuCalc Revit helper (optional startup)"; Flags: shellexec postinstall skipifsilent
