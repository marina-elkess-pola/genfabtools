using System;
using System.IO;
using System.Collections.Concurrent;
using Autodesk.Revit.UI;
using Autodesk.Revit.DB;
using Autodesk.Revit.Attributes;

namespace OccuCalcRevit
{
    public class App : IExternalApplication
    {
        private FileSystemWatcher _watcher;
        private static readonly string Incoming = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "OccuCalc", "incoming");
        private static readonly string LogFile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "OccuCalc", "log.txt");

        public Result OnStartup(UIControlledApplication application)
        {
            try
            {
                // Ensure log directory exists and write a startup marker so we can detect whether OnStartup ran
                try
                {
                    var logDir = Path.GetDirectoryName(LogFile);
                    if (!Directory.Exists(logDir)) Directory.CreateDirectory(logDir);
                    File.AppendAllText(LogFile, DateTime.UtcNow.ToString("o") + " - App.OnStartup invoked\r\n");
                }
                catch { }

                if (!Directory.Exists(Incoming)) Directory.CreateDirectory(Incoming);

                // Setup FileSystemWatcher to monitor incoming CSVs
                _watcher = new FileSystemWatcher(Incoming, "*.csv");
                _watcher.Created += (s, e) => CsvProcessor.QueueFile(e.FullPath);
                _watcher.EnableRaisingEvents = true;

                // Create a ribbon tab and panel for GenFabTools -> OccuCalc
                try
                {
                    string tabName = "GenFabTools";
                    // If the tab already exists this will throw; catch and ignore
                    application.CreateRibbonTab(tabName);
                }
                catch { }

                try
                {
                    RibbonPanel panel = null;
                    string panelName = "OccuCalc";
                    var existing = application.GetRibbonPanels("GenFabTools");
                    foreach (var p in existing) if (p.Name == panelName) panel = p;
                    if (panel == null) panel = application.CreateRibbonPanel("GenFabTools", panelName);

                    // Add a simple Import button that triggers a manual import command
                    var assembly = System.Reflection.Assembly.GetExecutingAssembly().Location;
                    var pushData = new PushButtonData("OccuCalcImport", "Import", assembly, "OccuCalcRevit.ImportCommand")
                    {
                        ToolTip = "Import CSV files from GenFabTools/OccuCalc incoming folder",
                    };
                    panel.AddItem(pushData);
                }
                catch (Exception ex)
                {
                    // Ribbon failures shouldn't prevent addin startup
                    TaskDialog.Show("OccuCalc", "Failed to create ribbon UI: " + ex.Message);
                }
                // Visible startup confirmation for diagnostics (temporary)
                try
                {
                    TaskDialog.Show("OccuCalc", "OccuCalc add-in loaded (startup diagnostic).\nIf you see this, the add-in is running.");
                }
                catch { }
            }
            catch (Exception ex)
            {
                TaskDialog.Show("OccuCalc", "Failed to start watcher: " + ex.Message);
            }
            return Result.Succeeded;
        }

        public Result OnShutdown(UIControlledApplication application)
        {
            try { _watcher?.Dispose(); } catch { }
            return Result.Succeeded;
        }
    }
}
