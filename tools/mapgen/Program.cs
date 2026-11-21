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
            "reflect" => Reflect(),
            "modelinfo" => ModelInfo(cfg, args.Skip(1).ToArray()),
            "prefabinfo" => PrefabInfo(cfg, args.Skip(1).ToArray()),
            "buildgraph" => BuildGraph(cfg, args.Length > 1 ? args[1] : "data/processed/map_graph_s3.json",
                                       args.Length > 2 ? args[2] : "data/processed/map_export_s3.json"),
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

    // ---------------------------------------------------------------- reflect (API keşfi)
    static int Reflect()
    {
        var asm = typeof(TruckLib.Models.Model).Assembly;
        foreach (var t in asm.GetExportedTypes().Where(t => t.Name is "Model" or "Look" or "Variant" or "Part"))
        {
            Console.WriteLine($"== {t.FullName}");
            foreach (var m in t.GetMembers(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.DeclaredOnly))
                Console.WriteLine("   " + m);
        }
        return 0;
    }

    // ---------------------------------------------------------------- modelinfo
    // Model .pmd dosyalarındaki gerçek look/variant adlarını yazdırır (oyun dosyası yalnızca okunur).
    static int ModelInfo(JsonElement cfg, string[] pmds)
    {
        var gameRoot = cfg.GetProperty("game_root").GetString();
        using var fs = HashFsReader.Open(Path.Combine(gameRoot, "base.scs"));
        foreach (var p in pmds)
        {
            try
            {
                var m = TruckLib.Models.Model.Open(p, fs);
                Console.WriteLine($"{p}: looks=[{string.Join(",", m.Looks.Select(l => l.Name))}] variants=[{string.Join(",", m.Variants.Select(v => v.Name))}]");
            }
            catch (Exception ex) { Console.WriteLine($"{p}: HATA {ex.GetType().Name}: {ex.Message}"); }
        }
        return 0;
    }

    // ---------------------------------------------------------------- prefabinfo
    // .ppd düğümlerini (konum, yön) ve prefab modelinin look/variant adlarını yazdırır.
    static int PrefabInfo(JsonElement cfg, string[] ppds)
    {
        var gameRoot = cfg.GetProperty("game_root").GetString();
        using var fs = HashFsReader.Open(Path.Combine(gameRoot, "base.scs"));
        foreach (var p in ppds)
        {
            try
            {
                var d = TruckLib.Models.Ppd.PrefabDescriptor.Open(p, fs);
                Console.WriteLine($"{p}: düğüm={d.Nodes.Count}");
                for (int i = 0; i < d.Nodes.Count; i++)
                    Console.WriteLine($"  node{i} pos={d.Nodes[i].Position} dir={d.Nodes[i].Direction}");
                var pmd = Path.ChangeExtension(p, ".pmd");
                var m = TruckLib.Models.Model.Open(pmd, fs);
                Console.WriteLine($"  looks=[{string.Join(",", m.Looks.Select(l => l.Name))}] variants=[{string.Join(",", m.Variants.Select(v => v.Name))}]");
            }
            catch (Exception ex) { Console.WriteLine($"{p}: HATA {ex.GetType().Name}: {ex.Message}"); }
        }
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
                if (bl.TryGetProperty("place", out var pl) && !pl.GetBoolean()) continue;
                var spec = PickModel(b, bl);
                if (string.IsNullOrEmpty(spec)) continue;
                // biçim: "model|variant1,variant2|look1,look2" -> OSM id'ye göre sabit seçim
                var parts = spec.Split('|');
                long osm = bl.GetProperty("osm").GetInt64();
                string Pick(int i, string fallback)
                {
                    if (parts.Length <= i || parts[i].Length == 0) return fallback;
                    var opts = parts[i].Split(',');
                    return opts[(int)(Math.Abs(osm) % opts.Length)];
                }
                var pos = new Vector3((float)bl.GetProperty("x").GetDouble(), 0f, (float)bl.GetProperty("z").GetDouble());
                var m = Model.Add(map, pos, parts[0], Pick(1, "default"), Pick(2, "default"));
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

    // ---------------------------------------------------------------- buildgraph
    // map_graph_s3.json (kavşaktan kavşağa bölünmüş ağ) + kavşak prefabları + map_export binaları.
    static int BuildGraph(JsonElement cfg, string graphRel, string exportRel)
    {
        var graph = JsonDocument.Parse(File.ReadAllText(Path.Combine(Root, graphRel))).RootElement;
        float scale = (float)graph.GetProperty("meta").GetProperty("scale_divisor").GetDouble();
        var types = cfg.GetProperty("road_types");
        var terrain = cfg.GetProperty("terrain_size");
        var jcfg = cfg.GetProperty("junctions");
        var gameRoot = cfg.GetProperty("game_root").GetString();
        using var fs = HashFsReader.Open(Path.Combine(gameRoot, "base.scs"));

        // prefab listesi: her birinin düğüm sınıfları (r1/r2) .ppd düğüm sırasıyla
        var specList = new List<(string token, TruckLib.Models.Ppd.PrefabDescriptor ppd, string[] cls, string variant)>();
        foreach (var j in jcfg.GetProperty("prefabs").EnumerateArray())
            specList.Add((j.GetProperty("token").GetString(),
                          TruckLib.Models.Ppd.PrefabDescriptor.Open(j.GetProperty("ppd").GetString(), fs),
                          j.GetProperty("classes").EnumerateArray().Select(c => c.GetString()).ToArray(),
                          j.TryGetProperty("variant", out var vv) ? vv.GetString() : null));
        string look = jcfg.GetProperty("look").GetString(), variant = jcfg.GetProperty("variant").GetString();
        float maxErr = (float)jcfg.GetProperty("max_angle_error_deg").GetDouble();

        var map = new Map { NormalScale = scale, CityScale = scale };

        // 1) kavşak prefabları: en iyi dönüş + kol/düğüm eşlemesi
        var attach = new Dictionary<(int edge, string end), (Prefab p, Vector3 nodePos, Vector3 center, float radius)>();
        int placed = 0, rejected = 0;
        var byToken = new Dictionary<string, int>();
        foreach (var jn in graph.GetProperty("junctions").EnumerateArray())
        {
            var arms = jn.GetProperty("arms").EnumerateArray().ToList();
            var armCls = arms.Select(a => a.TryGetProperty("cls", out var c) ? c.GetString() : "r1").ToArray();
            var center = new Vector3((float)jn.GetProperty("x").GetDouble(), 0, (float)jn.GetProperty("z").GetDouble());
            var armDir = arms.Select(a => Vector2.Normalize(new Vector2((float)a.GetProperty("dir")[0].GetDouble(), (float)a.GetProperty("dir")[1].GetDouble()))).ToList();

            float bestCost = float.MaxValue, bestMax = 0; int bestYaw = 0; int[] bestPerm = null;
            (string token, TruckLib.Models.Ppd.PrefabDescriptor ppd, string[] cls, string variant) spec = default;
            foreach (var sp in specList.Where(s => s.cls.Length == arms.Count))
            {
                if (!sp.cls.OrderBy(x => x).SequenceEqual(armCls.OrderBy(x => x))) continue;
                var nodeP = sp.ppd.Nodes.Select(nd => nd.Position).ToList();
                var perms = Permutations(Enumerable.Range(0, nodeP.Count).ToArray())
                    .Where(pm => Enumerable.Range(0, armCls.Length).All(i => sp.cls[pm[i]] == armCls[i])).ToList();
                for (int yawDeg = 0; yawDeg < 360; yawDeg++)
                {
                    var q = Quaternion.CreateFromYawPitchRoll(yawDeg * MathF.PI / 180f, 0, 0);
                    var nd = nodeP.Select(p => { var v = Vector3.Transform(p, q); return Vector2.Normalize(new Vector2(v.X, v.Z)); }).ToList();
                    foreach (var perm in perms)
                    {
                        float cost = 0, mx = 0;
                        for (int i = 0; i < armDir.Count; i++)
                        {
                            float ang = MathF.Acos(Math.Clamp(Vector2.Dot(armDir[i], nd[perm[i]]), -1f, 1f)) * 180f / MathF.PI;
                            cost += ang; mx = MathF.Max(mx, ang);
                        }
                        if (cost < bestCost) { bestCost = cost; bestMax = mx; bestYaw = yawDeg; bestPerm = perm; spec = sp; }
                    }
                }
            }
            if (bestPerm == null || bestMax > maxErr) { rejected++; continue; }
            var nodePos = spec.ppd.Nodes.Select(nd => nd.Position).ToList();
            float radius = nodePos.Max(p => new Vector2(p.X, p.Z).Length()) + 3f;
            try
            {
                var qb = Quaternion.CreateFromYawPitchRoll(bestYaw * MathF.PI / 180f, 0, 0);
                var node0World = center + Vector3.Transform(nodePos[0], qb);
                var pf = Prefab.Add(map, node0World, spec.token, spec.ppd, qb);
                pf.Look = look;
                pf.Variant = spec.variant ?? variant;
                for (int i = 0; i < arms.Count; i++)
                {
                    var want = center + Vector3.Transform(nodePos[bestPerm[i]], qb);
                    var actual = pf.Nodes.OrderBy(n => Vector3.DistanceSquared(n.Position, want)).First().Position;
                    attach[(arms[i].GetProperty("edge").GetInt32(), arms[i].GetProperty("end").GetString())] = (pf, actual, center, radius);
                }
                byToken[spec.token] = byToken.GetValueOrDefault(spec.token) + 1;
                placed++;
            }
            catch (Exception ex) { rejected++; if (rejected < 10) Console.WriteLine($"kavşak {jn.GetProperty("id")}: {ex.Message}"); }
        }

        // 2) yollar
        float R = (float)graph.GetProperty("meta").GetProperty("prefab_radius").GetDouble() + 3f;
        int roads = 0, segs = 0, skipped = 0, connected = 0;
        foreach (var e in graph.GetProperty("edges").EnumerateArray().OrderBy(e => e.GetProperty("prio").GetInt32()))
        {
            int id = e.GetProperty("id").GetInt32();
            var kind = e.GetProperty("type").GetString();
            var token = types.TryGetProperty(kind, out var t) ? t.GetString() : "ger1";
            float ts = terrain.TryGetProperty(kind, out var tz) ? (float)tz.GetDouble() : (float)terrain.GetProperty("default").GetDouble();
            var pts = e.GetProperty("pts").EnumerateArray().Select(p => new Vector3((float)p[0].GetDouble(), 0, (float)p[1].GetDouble())).ToList();
            attach.TryGetValue((id, "a"), out var sa);
            attach.TryGetValue((id, "b"), out var sb);
            bool hasA = sa.p != null, hasB = sb.p != null;
            if (hasA && hasB && ReferenceEquals(sa.p, sb.p)) { hasB = false; }
            // ters yönlü tek yönlüler yalnızca kavşaksız kenarlarda çevrilir
            if (!hasA && !hasB && e.GetProperty("reverse").GetBoolean()) pts.Reverse();
            var mid = pts.Where(p => (!hasA || Vector3.Distance(p, sa.center) > sa.radius) && (!hasB || Vector3.Distance(p, sb.center) > sb.radius)).ToList();
            var seq = new List<Vector3>();
            if (hasA) seq.Add(sa.nodePos);
            foreach (var p in mid) if (seq.Count == 0 || Vector3.Distance(seq[^1], p) > 3f) seq.Add(p);
            if (hasB) { if (seq.Count > 0 && Vector3.Distance(seq[^1], sb.nodePos) < 3f) seq.RemoveAt(seq.Count - 1); seq.Add(sb.nodePos); }
            if (seq.Count < 2) { skipped++; continue; }
            try
            {
                Road road;
                if (hasA)
                {
                    ushort ni = (ushort)sa.p.Nodes.FindIndex(n => Vector3.DistanceSquared(n.Position, sa.nodePos) < 0.01f);
                    road = sa.p.AppendRoad(ni, seq[1], token, ts, ts);
                    connected++;
                }
                else road = Road.Add(map, seq[0], seq[1], token, ts, ts);
                segs++;
                for (int i = 2; i < seq.Count; i++) { road = road.Append(seq[i]); segs++; }
                if (hasB) { sb.p.Attach(road); connected++; }
                roads++;
            }
            catch (Exception ex)
            {
                skipped++;
                if (skipped < 15) Console.WriteLine($"kenar {id} atlandı: {ex.Message}");
            }
        }

        // 3) binalar (map_export'tan, place=true olanlar)
        int buildings = AddBuildings(map, cfg, Path.Combine(Root, exportRel));

        var outDir = cfg.GetProperty("output_map_dir").GetString();
        var name = cfg.GetProperty("output_map_name").GetString();
        if (name == "saklaz" || name == "europe") throw new InvalidOperationException("Korumalı ad.");
        map.Save(outDir, name, true);
        Console.WriteLine("Prefab dağılımı: " + string.Join(", ", byToken.Select(kv => $"{kv.Key}={kv.Value}")));
        Console.WriteLine($"Kaydedildi: {name}.mbd  kavşak={placed} (reddedilen {rejected})  yol={roads} segment={segs} bağlantı={connected} atlanan={skipped} bina={buildings}");
        return 0;
    }

    static int AddBuildings(Map map, JsonElement cfg, string exportPath)
    {
        if (!File.Exists(exportPath)) return 0;
        var export = JsonDocument.Parse(File.ReadAllText(exportPath)).RootElement;
        var b = cfg.GetProperty("buildings");
        int n = 0;
        if (!export.TryGetProperty("buildings", out var blist)) return 0;
        foreach (var bl in blist.EnumerateArray())
        {
            if (bl.TryGetProperty("place", out var pl) && !pl.GetBoolean()) continue;
            var spec = PickModel(b, bl);
            if (string.IsNullOrEmpty(spec)) continue;
            var parts = spec.Split('|');
            long osm = bl.GetProperty("osm").GetInt64();
            string Pick(int i, string fb) => parts.Length <= i || parts[i].Length == 0 ? fb : parts[i].Split(',')[(int)(Math.Abs(osm) % parts[i].Split(',').Length)];
            var pos = new Vector3((float)bl.GetProperty("x").GetDouble(), 0f, (float)bl.GetProperty("z").GetDouble());
            var m = Model.Add(map, pos, parts[0], Pick(1, "default"), Pick(2, "default"));
            m.Node.Rotation = Quaternion.CreateFromYawPitchRoll((float)(bl.GetProperty("heading_deg").GetDouble() * Math.PI / 180.0), 0, 0);
            n++;
        }
        return n;
    }

    static IEnumerable<int[]> Permutations(int[] items)
    {
        if (items.Length <= 1) { yield return items; yield break; }
        for (int i = 0; i < items.Length; i++)
            foreach (var rest in Permutations(items.Where((_, k) => k != i).ToArray()))
                yield return new[] { items[i] }.Concat(rest).ToArray();
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
