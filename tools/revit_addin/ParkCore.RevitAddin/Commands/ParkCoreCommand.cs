using Autodesk.Revit.UI;
using Autodesk.Revit.DB;
using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Web.Script.Serialization;

namespace ParkCore.RevitAddin.Commands
{
    [Autodesk.Revit.Attributes.Transaction(Autodesk.Revit.Attributes.TransactionMode.Manual)]
    public class ParkCoreCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            UIDocument uidoc = commandData.Application.ActiveUIDocument;
            Document doc = uidoc.Document;

            try
            {
                var segments = FetchCirculationSegments();
                if (segments == null || segments.Count == 0)
                {
                    TaskDialog.Show("ParkCore", "No segments returned from generator.");
                    return Result.Succeeded;
                }

                using (Transaction tx = new Transaction(doc, "ParkCore Circulation"))
                {
                    tx.Start();
                    var plane = Plane.CreateByNormalAndOrigin(XYZ.BasisZ, XYZ.Zero);
                    var sk = SketchPlane.Create(doc, plane);
                    foreach (var seg in segments)
                    {
                        XYZ p = new XYZ(seg.from.x, seg.from.y, 0);
                        XYZ q = new XYZ(seg.to.x, seg.to.y, 0);
                        var line = Line.CreateBound(p, q);
                        doc.Create.NewModelCurve(line, sk);
                    }
                    tx.Commit();
                }
                TaskDialog.Show("ParkCore", $"Placed {segments.Count} segments.");
                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                message = ex.Message;
                return Result.Failed;
            }
        }

        private class PointDto { public double x { get; set; } public double y { get; set; } }
        private class SegmentDto { public PointDto from { get; set; } public PointDto to { get; set; } }

        private List<SegmentDto> FetchCirculationSegments()
        {
            var url = "http://127.0.0.1:5050/api/circulation/generate";
            using (var http = new HttpClient())
            {
                var payload = new Dictionary<string, object>
                {
                    { "siteRect", new Dictionary<string, object> { {"minX", 0}, {"minY", 0}, {"maxX", 100}, {"maxY", 60} } },
                    { "constraints", new Dictionary<string, object> { {"stallWidth", 9}, {"stallLength", 18}, {"aisleWidth", 24}, {"angleDeg", 90} } }
                };
                var serializer = new JavaScriptSerializer();
                var json = serializer.Serialize(payload);
                var content = new StringContent(json, Encoding.UTF8, "application/json");
                var resp = http.PostAsync(url, content).GetAwaiter().GetResult();
                if (!resp.IsSuccessStatusCode) return new List<SegmentDto>();
                var respText = resp.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                var data = serializer.Deserialize<Dictionary<string, object>>(respText);
                if (data == null || !data.ContainsKey("segments")) return new List<SegmentDto>();

                var segList = new List<SegmentDto>();
                var segmentsObj = data["segments"] as object[];
                if (segmentsObj == null)
                {
                    // JavaScriptSerializer may return ArrayList
                    var arrList = data["segments"] as System.Collections.ArrayList;
                    if (arrList != null)
                    {
                        foreach (var item in arrList)
                        {
                            var dict = item as Dictionary<string, object>;
                            if (dict == null) continue;
                            var from = dict["from"] as Dictionary<string, object>;
                            var to = dict["to"] as Dictionary<string, object>;
                            if (from == null || to == null) continue;
                            segList.Add(new SegmentDto
                            {
                                from = new PointDto { x = ToDouble(from, "x"), y = ToDouble(from, "y") },
                                to = new PointDto { x = ToDouble(to, "x"), y = ToDouble(to, "y") }
                            });
                        }
                    }
                    return segList;
                }
                foreach (var item in segmentsObj)
                {
                    var dict = item as Dictionary<string, object>;
                    if (dict == null) continue;
                    var from = dict["from"] as Dictionary<string, object>;
                    var to = dict["to"] as Dictionary<string, object>;
                    if (from == null || to == null) continue;
                    segList.Add(new SegmentDto
                    {
                        from = new PointDto { x = ToDouble(from, "x"), y = ToDouble(from, "y") },
                        to = new PointDto { x = ToDouble(to, "x"), y = ToDouble(to, "y") }
                    });
                }
                return segList;
            }
        }

        private double ToDouble(Dictionary<string, object> dict, string key)
        {
            if (!dict.ContainsKey(key) || dict[key] == null) return 0.0;
            if (dict[key] is double d) return d;
            if (dict[key] is float f) return (double)f;
            if (dict[key] is decimal m) return (double)m;
            if (dict[key] is int i) return (double)i;
            if (dict[key] is long l) return (double)l;
            double.TryParse(dict[key].ToString(), out var r);
            return r;
        }
    }
}
