# Revit add-in debug snapshot — 2025-11-25

**Saved:** 2025-11-25

This file is a concise snapshot of the in-progress debugging conversation for the OccuCalc → Revit integration. It was saved from the assistant conversation and is intended to help resume work later.

---

## Short summary

- Goal: One-click flow from the web app to Revit (CSV → Revit model) via a local helper + Revit add-in.
- Work completed: Frontend export prototype, local helper scaffold, Revit add-in scaffold with FileSystemWatcher and ExternalEvent, per-user `.addin` manifests, Inno installer scaffold, x64 build adjustments, diagnostic helpers (log + journal search scripts).
- Current blocker (paused): Revit is not loading the add-in (no `GenFabTools` tab visible, empty `%LOCALAPPDATA%\\OccuCalc\\log.txt`, and no Revit journal evidence). Investigation was paused per user request.

## Key artifacts (paths relative to repo root)

- Add-in project: `tools/revit_addin/OccuCalcRevit.csproj`
- Add-in source: `tools/revit_addin/src/App.cs`, `tools/revit_addin/src/CsvProcessor.cs`, `tools/revit_addin/src/ImportCommand.cs`
- Addin manifests (deployed): `tools/revit_addin/addins/2024/OccuCalcRevit.addin`, `tools/revit_addin/addins/2025/OccuCalcRevit.addin`
- Build output (local): `tools/revit_addin/bin/Release/net48/OccuCalcRevitAddin.dll`
- Incoming folder (runtime): `%LOCALAPPDATA%\\OccuCalc\\incoming`
- Runtime log (runtime): `%LOCALAPPDATA%\\OccuCalc\\log.txt` (empty at time of save)
- Diagnostics scripts (repo root): `.tools_list_journals.ps1`, `.tools_debug_search_journal.ps1`, `.tools_debug_read_log.ps1`

## What was tried

- Built the add-in and forced x64 target to avoid MSB3270 processor warnings.
- Copied `.dll` and `.addin` to per-user Addins folders for Revit 2024/2025 (`%APPDATA%\\Autodesk\\Revit\\Addins\\2025`).
- Added temporary visible diagnostics inside `App.OnStartup` (TaskDialog and writing a startup line to `%LOCALAPPDATA%\\OccuCalc\\log.txt`) to detect whether Revit executed the add-in.
- Created PowerShell helper scripts to find Revit journals and read the OccuCalc log.
- Observed: add-in files present on disk; Revit process running; `log.txt` exists but is 0 bytes; no recent journal files found.

## Immediate next steps (when resuming)

1. Fully close Revit and re-open it to force a journal write. Then run the journal-search script or ask the assistant to run it. This usually captures load-time errors.
2. If journals are missing, add an additional low-risk visible startup artifact (for troubleshooting only) such as writing a small file to the Desktop from `App.OnStartup` to confirm if `OnStartup` runs.
3. Inspect Windows Application event logs for .NET or Revit loader errors if journals don't show the problem.
4. Once the add-in load is confirmed, implement CSV→Revit mapping (match by Room Number → set Occupant Load parameter) and finish README + installer packaging.

## Commands you can run locally to collect logs

Open PowerShell and run these from the repo root to list journals and print the OccuCalc log (the helper scripts already exist in the repo and avoid quoting issues):

```powershell
# list Revit journals (repo root helper)
.\.tools_list_journals.ps1

# search journal files for OccuCalc-related errors
.\.tools_debug_search_journal.ps1

# print the OccuCalc startup log
.\.tools_debug_read_log.ps1
```

## Notes

- File saved by the assistant as requested. The investigation task in the todo list is marked "in-progress" and paused.
- If you want the full raw chat transcript exported here instead of this concise snapshot, let me know and I will add it (long files are fine).

---

_File saved by the assistant on 2025-11-25. Resume instructions are in the "Immediate next steps" section above._
