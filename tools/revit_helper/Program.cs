using System;
using System.IO;
using System.Linq;
using System.Net;
using System.Text;
using System.Text.RegularExpressions;
using System.Diagnostics;
using Microsoft.Win32;
using System.Collections.Generic;

// Minimal helper to handle occucalc-revit:// protocol on Windows.
// Behavior:
//  - Parse the incoming URL (args[0]). Expect either ?csv=... or ?token=...
//  - If csv payload present: decode and save to a per-user incoming folder.
//  - If token present: optionally fetch CSV from a configured server endpoint.
//  - Try to locate an installed Revit executable (search registry and common paths).
//  - If found and not running, start Revit.exe. Leave the CSV in the incoming folder for a Revit add-in to pick up.
//  - Exit.
//
// Build with: dotnet build -c Release
// Run example (for testing without protocol): dotnet run -- "occucalc-revit://import?csv=Room%201%2CTest%2C100%2COffice%2C1"

class Program
{
    static int Main(string[] args)
    {
        try
        {
            if (args.Length == 0)
            {
                Console.WriteLine("No URL provided.");
                return 1;
            }

            var raw = args[0];
            Console.WriteLine("Helper invoked with: " + raw);

            Uri uri;
            try
            {
                uri = new Uri(raw);
            }
            catch
            {
                // If the CLI stripped quotes, try percent-encoding a leading colon
                if (raw.StartsWith("occucalc-revit://", StringComparison.OrdinalIgnoreCase))
                {
                    var replaced = raw.Replace(" ", "%20");
                    uri = new Uri(replaced);
                }
                else throw;
            }

            var qs = System.Web.HttpUtility.ParseQueryString(uri.Query);

            string csv = null;
            if (!string.IsNullOrEmpty(qs["csv"]))
            {
                csv = Uri.UnescapeDataString(qs["csv"]);
            }
            else if (!string.IsNullOrEmpty(qs["token"]))
            {
                var token = qs["token"];
                // configurable server endpoint: try environment override
                var server = Environment.GetEnvironmentVariable("OCCUCALC_SERVER_URL") ?? "";
                if (!string.IsNullOrEmpty(server))
                {
                    var url = server.TrimEnd('/') + "/occucalc/download?token=" + Uri.EscapeDataString(token);
                    using (var wc = new WebClient())
                    {
                        csv = wc.DownloadString(url);
                    }
                }
                else
                {
                    Console.WriteLine("No server configured to fetch token payload. Set OCCUCALC_SERVER_URL env var.");
                }
            }

            // Save CSV to incoming folder even if null (we might still want to launch Revit)
            var incomingDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "OccuCalc", "incoming");
            Directory.CreateDirectory(incomingDir);
            if (!string.IsNullOrEmpty(csv))
            {
                var fname = "occucalc_" + DateTime.UtcNow.ToString("yyyyMMdd_HHmmss") + ".csv";
                var tempPath = Path.Combine(incomingDir, fname);
                File.WriteAllText(tempPath, csv, Encoding.UTF8);
                Console.WriteLine("Saved CSV to: " + tempPath);
            }
            else
            {
                Console.WriteLine("No CSV payload present in URL (token-only or missing). Saved nothing.");
            }

            // Find Revit installations
            var revitCandidates = FindRevitInstallations();
            if (revitCandidates.Count == 0)
            {
                Console.WriteLine("No Revit installations found on this machine.");
                return 0;
            }

            // Pick the highest version number (latest) or first candidate
            var selected = revitCandidates.OrderByDescending(r => r.Version).First();
            Console.WriteLine($"Selected Revit: {selected.Path} (v{selected.Version})");

            // If Revit not running, start it
            var exeName = Path.GetFileNameWithoutExtension(selected.Path)?.ToLowerInvariant();
            var running = Process.GetProcesses().Any(p =>
            {
                try { return string.Equals(Path.GetFileNameWithoutExtension(p.MainModule?.FileName ?? ""), exeName, StringComparison.OrdinalIgnoreCase); } catch { return false; }
            });

            if (!running)
            {
                try
                {
                    ProcessStartInfo psi = new ProcessStartInfo(selected.Path);
                    psi.UseShellExecute = true;
                    Process.Start(psi);
                    Console.WriteLine("Launched Revit.");
                }
                catch (Exception ex)
                {
                    Console.WriteLine("Failed to launch Revit: " + ex.Message);
                }
            }
            else
            {
                Console.WriteLine("Revit was already running.");
            }

            Console.WriteLine("Done.");
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex.ToString());
            return 2;
        }
    }

    class RevitInstall
    {
        public string Path { get; set; }
        public int Version { get; set; }
    }

    static List<RevitInstall> FindRevitInstallations()
    {
        var outList = new List<RevitInstall>();

        // Check registry both 64 and 32 view
        var views = new[] { RegistryView.Registry64, RegistryView.Registry32 };
        foreach (var view in views)
        {
            try
            {
                using (var baseKey = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, view))
                using (var revitRoot = baseKey.OpenSubKey("SOFTWARE\\Autodesk\\Revit"))
                {
                    if (revitRoot == null) continue;
                    foreach (var sub in revitRoot.GetSubKeyNames())
                    {
                        try
                        {
                            using (var sk = revitRoot.OpenSubKey(sub))
                            {
                                var installLoc = sk?.GetValue("InstallLocation") as string ?? sk?.GetValue("InstallPath") as string;
                                if (!string.IsNullOrEmpty(installLoc))
                                {
                                    // The InstallLocation may point to folder; try Revit.exe
                                    var candidate = Path.Combine(installLoc, "Revit.exe");
                                    if (!File.Exists(candidate))
                                    {
                                        // Sometimes InstallLocation already points to the exe
                                        if (File.Exists(installLoc)) candidate = installLoc;
                                    }

                                    if (File.Exists(candidate))
                                    {
                                        if (int.TryParse(Regex.Match(sub, "\\d{4}").Value, out int v))
                                        {
                                            outList.Add(new RevitInstall { Path = candidate, Version = v });
                                        }
                                        else
                                        {
                                            outList.Add(new RevitInstall { Path = candidate, Version = 0 });
                                        }
                                    }
                                }
                            }
                        }
                        catch { }
                    }
                }
            }
            catch { }
        }

        // Fallback: probe common program files names for 2017..2026
        var common = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        for (int year = 2017; year <= 2026; year++)
        {
            var path = Path.Combine(common, $"Autodesk", $"Revit {year}", "Revit.exe");
            if (File.Exists(path) && !outList.Any(x => string.Equals(Path.GetFullPath(x.Path), Path.GetFullPath(path), StringComparison.OrdinalIgnoreCase)))
            {
                outList.Add(new RevitInstall { Path = path, Version = year });
            }
        }

        return outList.DistinctBy(x => Path.GetFullPath(x.Path)).ToList();
    }
}
