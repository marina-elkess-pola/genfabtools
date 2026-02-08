using System;
using System.IO;
using System.Collections.Concurrent;
using Autodesk.Revit.UI;
using Autodesk.Revit.DB;

namespace OccuCalcRevit
{
    // ExternalEvent handler to process queued CSV imports on Revit's main thread
    public class CsvExternalEventHandler : IExternalEventHandler
    {
        public void Execute(UIApplication app)
        {
            while (CsvProcessor.TryDequeue(out var path))
            {
                try
                {
                    // Wait briefly for file write completion
                    System.Threading.Thread.Sleep(200);
                    var lines = File.ReadAllLines(path);
                    // Very simple CSV parsing - production should use a robust parser
                    for (int i = 1; i < lines.Length; i++)
                    {
                        var cols = SplitCsvLine(lines[i]);
                        // cols[0] = Room Number, cols[1] = Room Name, cols[2] = Area_m2, cols[3] = Occupancy Type, cols[4] = Occupant Load
                        // TODO: map to Revit elements (Rooms/Parameters) or create a schedule row
                        // This is intentionally left as a placeholder. Implement mapping to your model here.
                    }

                    // Optionally delete processed file
                    // File.Delete(path);
                }
                catch (Exception ex)
                {
                    TaskDialog.Show("OccuCalc", "CSV processing failed: " + ex.Message);
                }
            }
        }

        public string GetName()
        {
            return "OccuCalc CSV ExternalEvent Handler";
        }

        private string[] SplitCsvLine(string line)
        {
            // Very naive split for the scaffold. Replace with a robust CSV parser if needed.
            return line.Split(',');
        }
    }

    public static class CsvProcessor
    {
        private static readonly ConcurrentQueue<string> _queue = new ConcurrentQueue<string>();
        private static ExternalEvent _ev;

        public static void QueueFile(string path)
        {
            _queue.Enqueue(path);
            EnsureEvent();
            _ev.Raise();
        }

        public static bool TryDequeue(out string path) => _queue.TryDequeue(out path);

        private static void EnsureEvent()
        {
            if (_ev == null)
            {
                var handler = new CsvExternalEventHandler();
                _ev = ExternalEvent.Create(handler);
            }
        }
    }
}
