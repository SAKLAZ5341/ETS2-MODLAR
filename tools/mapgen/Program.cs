// SAKLAZ Türkiye Map - TruckLib tabanlı harita üretici.
//
// Kullanım (proje kökünden):
//   dotnet run --project tools/mapgen -- list                 # def.scs'ten road_look / building / model adlarını dök (salt okunur)
//   dotnet run --project tools/mapgen -- build data/processed/map_export_s3.json
//
// - Oyun dosyaları yalnızca OKUNUR (HashFsReader). Hiçbir oyun dosyası yazılmaz.
// - Çıktı ayrı bir harita modülüdür: mapping.json -> output_map_dir / output_map_name (varsayılan saklaz_city).
//   Elle çizilen "saklaz" haritasına dokunulmaz.
// - Üretimden sonra editörde: Map > Recompute map, sonra Save (TruckLib README notu).
// Veri © OpenStreetMap katkıda bulunanlar, ODbL 1.0.

using System.Numerics;
using System.Text;
using System.Text.Json;
using TruckLib.HashFs;
using TruckLib.ScsMap;

namespace SaklazMapGen;

internal static class Program
{
    static readonly string Root = FindRoot();

    static int Main(string[] args)
    {
        Console.OutputEncoding = Encoding.UTF8;
        var cfg = JsonDocument.Parse(File.ReadAllText(Path.Combine(Root, "tools", "mapgen", "mapping.json"))).RootElement;
        if (args.Length == 0) { Console.WriteLine("Kullanım: list | build <map_export.json>"); return 2; }
        return args[0] switch
        {
            "list" => ListDefs(cfg),
            "build" => Build(cfg, args.Length > 1 ? args[1] : "data/processed/map_export_s3.json"),
            _ => 2,
        };
    }

    // ---------------------------------------------------------------- list
    static int ListDefs(JsonElement cfg)
    {
        var gameRoot = cfg.GetProperty("game_root").GetString();
        var outDir = Path.Combine(Root, "data", "processed", "game_defs");
        Directory.CreateDirectory(outDir);
        foreach (var pack in new[] { "def.scs", "base.scs" })
        {
            var path = Path.Combine(gameRoot, pack);
            if (!File.Exists(path)) { Console.WriteLine($"yok: {path}"); continue; }
            using var fs = HashFsReader.Open(path);
            foreach (var f in new[] { "/def/world/road_look.template.sii", "/def/world/road_look.sii",
                                      "/def/world/building_scheme.sii", "/def/world/model.sii",
                                      "/def/world/prefab.sii" })
            {
                if (!fs.FileExists(f)) continue;
                var bytes = fs.Extract(f)[0];
                var name = pack.Replace(".scs", "") + "_" + Path.GetFileName(f);
                File.WriteAllBytes(Path.Combine(outDir, name), bytes);
                Console.WriteLine($"{pack}:{f} -> {name} ({bytes.Length} bayt)");
            }
        }
        Console.WriteLine($"Tanım dosyaları: {outDir} (salt okunur kopya, depoya girmez)");
        return 0;
    }

    // ---------------------------------------------------------------- build
    static int Build(JsonElement cfg, string exportRel)
    {
        var export = JsonDocument.Parse(File.ReadAllText(Path.Combine(Root, exportRel))).RootElement;
        var meta = export.GetProperty("meta");
        float scale = (float)meta.GetProperty("scale_divisor").GetDouble();
        var types = cfg.GetProperty("road_types");
        var terrain = cfg.GetProperty("terrain_size");
        int maxRoads = cfg.GetProperty("limits").GetProperty("max_roads").GetInt32();
        int maxBuildings = cfg.GetProperty("limits").GetProperty("max_buildings").GetInt32();

        var map = new Map
        {
            NormalScale = scale,
            CityScale = scale,
        };

        int roads = 0, segs = 0, skipped = 0;
        foreach (var r in export.GetProperty("roads").EnumerateArray()
                     .OrderBy(r => r.GetProperty("prio").GetInt32()))
        {
            if (maxRoads > 0 && roads >= maxRoads) break;
            var kind = r.GetProperty("type").GetString();
            var token = types.TryGetProperty(kind, out var t) ? t.GetString() : "ger1";
            float ts = terrain.TryGetProperty(kind, out var tz) ? (float)tz.GetDouble() : (float)terrain.GetProperty("default").GetDouble();
            var pts = r.GetProperty("pts").EnumerateArray()
                       .Select(p => new Vector3((float)p[0].GetDouble(), 0f, (float)p[1].GetDouble())).ToList();
            if (r.GetProperty("reverse").GetBoolean()) pts.Reverse();
            if (pts.Count < 2) { skipped++; continue; }
            try
            {
                var road = Road.Add(map, pts[0], pts[1], token, ts, ts);
                segs++;
                for (int i = 2; i < pts.Count; i++) { road = road.Append(pts[i]); segs++; }
                roads++;
            }
            catch (Exception ex)
            {
                skipped++;
                if (skipped < 20) Console.WriteLine($"yol atlandı osm={r.GetProperty("osm")}: {ex.Message}");
            }
        }

        int buildings = 0;
        var b = cfg.GetProperty("buildings");
        if (export.TryGetProperty("buildings", out var blist))
        {
            foreach (var bl in blist.EnumerateArray())
            {
                if (maxBuildings > 0 && buildings >= maxBuildings) break;
                var model = PickModel(b, bl);
                if (string.IsNullOrEmpty(model)) continue;
                var pos = new Vector3((float)bl.GetProperty("x").GetDouble(), 0f, (float)bl.GetProperty("z").GetDouble());
                var m = Model.Add(map, pos, model, "default", "default");
                float yaw = (float)(bl.GetProperty("heading_deg").GetDouble() * Math.PI / 180.0);
                m.Node.Rotation = Quaternion.CreateFromYawPitchRoll(yaw, 0, 0);
                buildings++;
            }
        }

        var outDir = cfg.GetProperty("output_map_dir").GetString();
        var name = cfg.GetProperty("output_map_name").GetString();
        if (name == "saklaz" || name == "europe") throw new InvalidOperationException("Bu ad korumalı; mapping.json'da başka ad kullanın.");
        Directory.CreateDirectory(outDir);
        map.Save(outDir, name, true);
        Console.WriteLine($"Kaydedildi: {Path.Combine(outDir, name)}.mbd  yol zinciri={roads} segment={segs} atlanan={skipped} bina={buildings}");
        Console.WriteLine("Editörde: Map > Recompute map, ardından Save.");
        return 0;
    }

    static string PickModel(JsonElement b, JsonElement bl)
    {
        var kind = bl.GetProperty("kind").GetString() ?? "yes";
        string key = kind switch
        {
            "industrial" or "warehouse" or "factory" or "manufacture" => "industrial",
            "commercial" or "retail" or "office" or "supermarket" => "commercial",
            "apartments" or "residential" => "apartment",
            "house" or "detached" or "semidetached_house" => "small_house",
            _ => (bl.GetProperty("area_real_m2").GetDouble() > 400 ? "apartment" : "small_house"),
        };
        return b.TryGetProperty(key, out var v) ? v.GetString() : null;
    }

    static string FindRoot()
    {
        var d = new DirectoryInfo(AppContext.BaseDirectory);
        while (d != null && !File.Exists(Path.Combine(d.FullName, "config", "aoi.json"))) d = d.Parent;
        return d?.FullName ?? Directory.GetCurrentDirectory();
    }
}
