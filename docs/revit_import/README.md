OccuCalc → Revit import

This folder contains a simple Dynamo-based import pattern for getting room tables exported from OccuCalc into a Revit schedule.

1) Export from OccuCalc

- Use the app Export → "Export for Revit (CSV)". This creates a CSV with header:
  Room Number,Room Name,Area_m2,Occupancy Type,Occupant Load

2) Dynamo script (manual run)

- Open Revit and the target project.
- Open Dynamo (Revit's Dynamo Player or Dynamo editor).
- Run a script that reads the CSV and maps rows into a schedule or creates new rooms/fills parameters.

Sample Dynamo/Python approach (pseudo):

- Use Python script node or CSV.ReadFile node to parse the CSV.
- For each row: find the schedule or element to update; create or update parameters (Area, Occupancy Type, Load).

3) Example: Python snippet for Dynamo (use within Python node)

# This is a simplified example and must be adapted in Dynamo environment

import csv
from System.IO import File
path = IN[0]  # path to CSV from Dynamo input
with open(path, newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        room_number = row.get('Room Number')
        room_name = row.get('Room Name')
        area = row.get('Area_m2')
        occ_type = row.get('Occupancy Type')
        load = row.get('Occupant Load')
        # perform lookup/update in Revit API (use Revit.Elements and RevitServices in Dynamo)

4) Notes & next steps

- This flow avoids installing Revit add-ins for initial testing.
- When you want a single-click flow, consider writing a small Revit add-in or local agent to watch a folder or handle a custom protocol and then automate the import using Revit API.
- If you want, I can create a sample Dynamo graph or a minimal signed Revit add-in blueprint next.
