using System;
using System.IO;
using System.Linq;
using Autodesk.Revit.UI;
using Autodesk.Revit.DB;

namespace OccuCalcRevit
{
    [Autodesk.Revit.Attributes.Transaction(Autodesk.Revit.Attributes.TransactionMode.Manual)]
    public class ImportCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            try
            {
                var incoming = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "OccuCalc", "incoming");
                if (!Directory.Exists(incoming))
                {
                    TaskDialog.Show("OccuCalc", "Incoming folder not found: " + incoming);
                    return Result.Failed;
                }

                var files = Directory.GetFiles(incoming, "*.csv").OrderBy(f => f).ToArray();
                if (files.Length == 0)
                {
                    TaskDialog.Show("OccuCalc", "No CSV files found in: " + incoming);
                    return Result.Succeeded;
                }

                // Enqueue all files for processing by CsvProcessor (which uses ExternalEvent to run on main thread)
                foreach (var f in files)
                {
                    CsvProcessor.QueueFile(f);
                }

                TaskDialog.Show("OccuCalc", $"Queued {files.Length} CSV file(s) for import.");
                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                TaskDialog.Show("OccuCalc", "Import command failed: " + ex.Message);
                return Result.Failed;
            }
        }
    }
}
