using Autodesk.Revit.UI;
using System.Reflection;

namespace ParkCore.RevitAddin
{
    public class Application : IExternalApplication
    {
        public Result OnStartup(UIControlledApplication application)
        {
            string tabName = "ParkCore";
            try { application.CreateRibbonTab(tabName); } catch { /* Tab may already exist */ }
            RibbonPanel panel = application.CreateRibbonPanel(tabName, "Tools");

            string assemblyPath = Assembly.GetExecutingAssembly().Location;
            PushButtonData btnData = new PushButtonData(
                "ParkCoreCommand",
                "ParkCore",
                assemblyPath,
                "ParkCore.RevitAddin.Commands.ParkCoreCommand"
            );
            panel.AddItem(btnData);
            return Result.Succeeded;
        }

        public Result OnShutdown(UIControlledApplication application)
        {
            return Result.Succeeded;
        }
    }
}
