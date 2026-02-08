OccuCalc Revit helper (prototype)

What this helper does

- Handles the custom protocol occucalc-revit:// (after you register it).
- Accepts either a CSV payload (encoded in the URL) or a short token used to fetch the CSV from a server (optional).
- Saves the CSV to %LOCALAPPDATA%\\OccuCalc\\incoming\ as a timestamped .csv file.
- Attempts to locate an installed Revit on the machine (registry + common Program Files paths) and launches the latest one if it's not already running.
- A Revit add-in can watch the incoming folder and process new CSV files.

Files

- Program.cs - C# console app source (dotnet 6+). Build with `dotnet build -c Release`.
- register_occucalc_revit.reg - Per-user registry entry that points the protocol to the helper. Edit the path in the file before running.

How to build

1. Install .NET SDK (6.0 or later).
2. From this folder run:

   dotnet build -c Release

3. The built EXE will be in bin\\Release\\net6.0 (or similar). Copy the EXE to a permanent folder and update register_occucalc_revit.reg with that path.

Register the protocol (per-user, no admin required)

1. Edit `register_occucalc_revit.reg` to replace `C:\\path\\to\\OccuCalcRevitHelper.exe` with the full path to the built EXE.
2. Double-click the .reg file or run `reg import register_occucalc_revit.reg` from cmd

Testing locally

- You can test the helper manually from a command prompt:

  "C:\path\to\OccuCalcRevitHelper.exe" "occucalc-revit://import?csv=Room%201%2CMyRoom%2C50%2COffice%2C1"

- The helper should save a CSV into %LOCALAPPDATA%\\OccuCalc\\incoming and try to start Revit.

Next steps to make one-click import complete

1. Create a Revit add-in (IExternalApplication) that watches %LOCALAPPDATA%\\OccuCalc\\incoming for new CSV files. When a new CSV appears, parse it and update the model (either set room parameters or populate a schedule).
2. Optionally make the web app POST the CSV to a server and have the protocol call pass a short token instead of the whole CSV. The helper can then fetch the CSV securely.

Security notes

- Treat the incoming folder as a trusted channel; validate CSV contents before applying changes.
- Use TLS and short-lived tokens if you implement token-based downloads.

If you want, I can scaffold the Revit add-in (C#) that processes the incoming CSV files and demonstrate importing into a schedule or setting room parameters. Tell me which Revit versions you need to support.
