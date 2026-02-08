# ParkCore Revit Add-in

This directory contains the Revit add-in for ParkCore. It provides commands and a ribbon to support precise architectural drawing workflows integrated with the web app.

## Structure

- `ParkCore.RevitAddin/` — C# project for the add-in
- `ParkCore.RevitAddin.addin` — Revit add-in manifest file

## Build Targets

Revit requires .NET Framework and version-specific targeting. We'll initially scaffold for Revit 2024/2025 and adjust as needed.

## Next Steps

- Confirm target Revit versions (e.g., 2023–2025)
- Generate the C# project and wire up `ExternalApplication` and a sample `ExternalCommand`
- Implement localhost bridge messaging
