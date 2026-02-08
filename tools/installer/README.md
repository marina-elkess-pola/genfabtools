OccuCalc one-step installer (per-user) - README

Goal

Provide a single installer that places the protocol helper and a small Revit add-in into per-user locations so users can click "Open in Revit (one-click)" from the web app and have the CSV imported into Revit (via the add-in watch).

What I added

- tools/revit_helper/Program.cs - protocol helper scaffold (already added earlier) - build with dotnet 6+
- tools/installer/occucalc_installer.iss - Inno Setup script (per-user installer)
- tools/revit_addin/ - minimal Revit add-in scaffold (net48): .csproj and source
- tools/revit_addin/addins/2023..2026/OccuCalcRevit.addin - .addin templates for Revit 2023-2026

Quick build & test steps

1) Build the helper
   - Install .NET SDK 6+
   - cd tools/revit_helper
   - dotnet build -c Release
   - Copy the EXE from bin\\Release\\net6.0\\OccuCalcRevitHelper.exe to a stable folder

2) Build the Revit add-in
   - Revit add-ins require .NET Framework 4.8 and references to RevitAPI.dll and RevitAPIUI.dll from your local Revit installation. Add HintPath references in OccuCalcRevit.csproj before building.
   - Open the add-in project in Visual Studio (target net48), add references to: C:\\Program Files\\Autodesk\\Revit <year>\\RevitAPI.dll and RevitAPIUI.dll
   - Build in Release and copy OccuCalcRevitAddin.dll to tools/revit_addin/bin/Release

3) Edit Inno script (tools/installer/occucalc_installer.iss)
   - Ensure the Source paths point to the produced files (helper EXE and add-in DLL). Adjust years if needed.

4) Build installer (Inno Setup)
   - Install Inno Setup on Windows
   - Open occucalc_installer.iss in Inno Setup Compiler and Build
   - This produces occucalc_installer.exe

5) Run installer (per-user)
   - Double-click occucalc_installer.exe on the target machine.
   - It will copy the helper to %LOCALAPPDATA%\\OccuCalc and install .addin files into %APPDATA%\\Autodesk\\Revit\\Addins\\<year> (per-user).

6) Test one-click flow
   - In the web app, choose "Open in Revit (one-click)". The browser will call occucalc-revit://import?csv=... or a token URL.
   - Windows will launch the helper EXE which saves CSV to %LOCALAPPDATA%\\OccuCalc\\incoming and attempts to start Revit.
   - The Revit add-in's FileSystemWatcher will see the CSV and queue an ExternalEvent; the ExternalEvent handler runs on Revit's main thread and processes the CSV (see CsvProcessor.cs). You must implement mapping to your model in CsvProcessor.Execute.

Notes & next steps

- The scaffold includes a placeholder CSV processing handler (CsvProcessor) that currently only shows where to implement mapping logic. I can implement a concrete importer (map by Room Number to Revit Room elements, set parameters, or populate a schedule) if you provide the exact mapping you need.
- For reliability/token approach: it's recommended the web app uploads CSV to a server and returns a short token. Update Program.cs to fetch CSV from OCCUCALC_SERVER_URL + token.
- For signing: sign the helper EXE and installer to avoid SmartScreen warnings.

If you want, I can now:

- Implement the CSV-to-Revit mapping (set room parameters or create schedule rows) — tell me the target behavior.
- Produce the Inno installer after you build the helper and add-in binaries (or I can add build hooks if you want me to attempt to build here).
- Create a small test script or token server endpoint to support token-based payloads.
