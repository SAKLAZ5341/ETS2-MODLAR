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
            "extract" => Extract(cfg, args.Skip(1).ToArray()),
            "build" => Build(cfg, args.Length > 1 ? args[1] : "data/processed/map_export_s3.json"),
            "reflect" => Reflect(args.Skip(1).ToArray()),
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

    // ---------------------------------------------------------------- extract
    // extract <pack.scs> <yol>...  : dosyayı game_defs'e kopyalar; klasörse içeriğini listeler (salt okunur).
    static int Extract(JsonElement cfg, string[] a)
    {
        var gameRoot = cfg.GetProperty("game_root").GetString();
        var outDir = Path.Combine(Root, "data", "processed", "game_defs");
        using var fs = HashFsReader.Open(Path.Combine(gameRoot, a[0]));
        foreach (var p in a.Skip(1))
        {
            if (fs.DirectoryExists(p))
            {
                var l = fs.GetDirectoryListing(p);
                foreach (var d in l.Subdirectories) Console.WriteLine("D " + d);
                foreach (var x in l.Files) Console.WriteLine("F " + x);
            }
            else if (fs.FileExists(p))
            {
                var bytes = fs.Extract(p)[0];
                var name = Path.GetFileNameWithoutExtension(a[0]) + "_" + p.Trim('/').Replace('/', '_');
                File.WriteAllBytes(Path.Combine(outDir, name), bytes);
                Console.WriteLine($"{p} -> {name} ({bytes.Length} bayt)");
            }
            else Console.WriteLine("yok: " + p);
        }
        return 0;
    }

    // ---------------------------------------------------------------- reflect (API keşfi)
    static int Reflect(string[] names)
    {
        var asm = names.Length > 0 && names[0].StartsWith("map") ? typeof(TruckLib.ScsMap.Map).Assembly : typeof(TruckLib.Models.Model).Assembly;
        if (names.Length > 0 && names[0].StartsWith("map")) names = names[0] == "map" ? new[] { "?" } : names.Skip(1).ToArray();
        if (names.Length == 1 && names[0] == "?") { foreach (var t in asm.GetExportedTypes().OrderBy(t => t.FullName)) Console.WriteLine(t.FullName); return 0; }
        foreach (var t in asm.GetExportedTypes().Where(t => names.Length == 0 ? t.Name is "Model" or "Look" or "Variant" or "Part" : names.Contains(t.Name) || names.Contains("*")))
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
        // base.scs + harita DLC'leri: modelin bulunduğu ilk arşiv kullanılır
        var packs = new[] { "base.scs", "dlc_balkan_e.scs", "dlc_balkan_w.scs", "dlc_greece.scs", "dlc_east.scs", "dlc_it.scs" }
            .Select(f => Path.Combine(gameRoot, f)).Where(File.Exists).Select(f => (name: Path.GetFileName(f), fs: HashFsReader.Open(f))).ToList();
        foreach (var p in pmds)
        {
            var hit = packs.FirstOrDefault(k => k.fs.FileExists(p));
            if (hit.fs == null) { Console.WriteLine($"{p}: YOK"); continue; }
            try
            {
                var m = TruckLib.Models.Model.Open(p, hit.fs);
                Console.WriteLine($"{p} [{hit.name}]: looks=[{string.Join(",", m.Looks.Select(l => l.Name))}] variants=[{string.Join(",", m.Variants.Select(v => v.Name))}] boyut={m.BoundingBox}");
            }
            catch (Exception ex) { Console.WriteLine($"{p}: HATA {ex.GetType().Name}: {ex.Message}"); }
        }
        foreach (var k in packs) k.fs.Dispose();
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
        var noBuild = new List<(Vector3 c, float r)>(); // bina konmayacak daireler (kavşak, depo)

        // 0) başlangıç noktası: önizleme tırı (0,0,0)'a, -Z yönüne bakarak koyar. Haritayı, düz ve
        //    boş bir şehir yolu parçasının ortası orijine gelecek şekilde kaydırırız.
        var off = FindSpawnOffset(graph, cfg);
        Vector3 V(double x, double z) => new Vector3((float)x + off.X, 0, (float)z + off.Y);

        // 1) kavşak prefabları: en iyi dönüş + kol/düğüm eşlemesi
        var attach = new Dictionary<(int edge, string end), (Prefab p, Vector3 nodePos, Vector3 center, float radius)>();
        int placed = 0, rejected = 0;
        var byToken = new Dictionary<string, int>();
        foreach (var jn in graph.GetProperty("junctions").EnumerateArray())
        {
            var arms = jn.GetProperty("arms").EnumerateArray().ToList();
            var armCls = arms.Select(a => a.TryGetProperty("cls", out var c) ? c.GetString() : "r1").ToArray();
            var center = V(jn.GetProperty("x").GetDouble(), jn.GetProperty("z").GetDouble());
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
                    if (i == 0) noBuild.Add((center, radius + 6));
                }
                byToken[spec.token] = byToken.GetValueOrDefault(spec.token) + 1;
                placed++;
            }
            catch (Exception ex) { rejected++; if (rejected < 10) Console.WriteLine($"kavşak {jn.GetProperty("id")}: {ex.Message}"); }
        }

        // 1b) şirket depoları (iki düğümlü prefab, yol ikiye bölünmüş) + Company öğeleri
        int depots = 0;
        if (cfg.TryGetProperty("depots", out var dcfg) && graph.TryGetProperty("depots", out var dlist))
        {
            var city = dcfg.GetProperty("city").GetString();
            foreach (var d in dlist.EnumerateArray())
            {
                try
                {
                    var kind = dcfg.GetProperty("kinds").GetProperty(d.GetProperty("kind").GetString());
                    var company = d.GetProperty("company").GetString();
                    var ppd = TruckLib.Models.Ppd.PrefabDescriptor.Open(kind.GetProperty("ppd").GetString(), fs);
                    Vector3 P(JsonElement a) => V(a[0].GetDouble(), a[1].GetDouble());
                    Vector3 n0 = P(d.GetProperty("n0")), n1 = P(d.GetProperty("n1")), body = P(d.GetProperty("body"));
                    Vector3 p0 = ppd.Nodes[0].Position, p1 = ppd.Nodes[1].Position;
                    static float H(Vector3 v) => MathF.Atan2(v.X, v.Z);
                    (Quaternion q, Vector3 origin, Vector3 first) best = default; float bestD = float.MaxValue;
                    foreach (var (a, b) in new[] { (n0, n1), (n1, n0) })
                    {
                        var q = Quaternion.CreateFromYawPitchRoll(H(b - a) - H(p1 - p0), 0, 0);
                        var origin = a - Vector3.Transform(p0, q);
                        // depo gövdesi düğüm hattının diğer yanında: prefab merkezi (0,0) gövdeye yakın olmalı
                        float dist = Vector3.Distance(origin, body);
                        if (dist < bestD) { bestD = dist; best = (q, origin, a); }
                    }
                    var pf = Prefab.Add(map, best.first, kind.GetProperty("token").GetString(), ppd, best.q);
                    pf.Look = kind.GetProperty("look").GetString();
                    if (dcfg.GetProperty("variants").TryGetProperty(company, out var vr)) pf.Variant = vr.GetString();
                    foreach (var (arm, want) in new[] { (d.GetProperty("arm0"), n0), (d.GetProperty("arm1"), n1) })
                    {
                        var actual = pf.Nodes.OrderBy(n => Vector3.DistanceSquared(n.Position, want)).First().Position;
                        attach[(arm.GetProperty("edge").GetInt32(), arm.GetProperty("end").GetString())] = (pf, actual, actual, 1f);
                    }
                    var co = Company.Add(map, pf, best.origin);
                    noBuild.Add((best.origin, 75f));
                    co.CompanyName = company;
                    co.CityName = d.TryGetProperty("city", out var dc) ? dc.GetString() : city;
                    foreach (var sp in ppd.SpawnPoints)
                    {
                        var (dt, diff) = sp.Type switch
                        {
                            TruckLib.Models.Ppd.SpawnPointType.CompanyPoint => (CompanyDepotType.Load, CompanyUnloadDifficulty.None),
                            TruckLib.Models.Ppd.SpawnPointType.UnloadEasy => (CompanyDepotType.Unload, CompanyUnloadDifficulty.Easy),
                            TruckLib.Models.Ppd.SpawnPointType.UnloadMedium => (CompanyDepotType.Unload, CompanyUnloadDifficulty.Medium),
                            TruckLib.Models.Ppd.SpawnPointType.UnloadHard => (CompanyDepotType.Unload, CompanyUnloadDifficulty.Hard),
                            _ => ((CompanyDepotType)(-1), CompanyUnloadDifficulty.None),
                        };
                        if ((int)dt < 0) continue;
                        co.SpawnPoints.Add(best.origin + Vector3.Transform(sp.Position, best.q), best.q * sp.Rotation, dt, diff);
                    }
                    depots++;
                    Console.WriteLine($"depo {d.GetProperty("id")}: {company} ({d.GetProperty("kind")}) noktalar={co.SpawnPoints.Count}");
                }
                catch (Exception ex) { Console.WriteLine($"depo {d.GetProperty("id")} atlandı: {ex.Message}"); }
            }
            if (dcfg.GetProperty("city_area").GetBoolean() && graph.TryGetProperty("cities", out var clist))
            {
                // CityArea konumu alanın MERKEZİ (oyunda doğrulandı: köşe sanılınca doğu yarısı dışarıda kalıyordu)
                foreach (var c in clist.EnumerateArray())
                {
                    double x0 = c.GetProperty("x0").GetDouble(), x1 = c.GetProperty("x1").GetDouble();
                    double z0 = c.GetProperty("z0").GetDouble(), z1 = c.GetProperty("z1").GetDouble();
                    var ca = CityArea.Add(map, V((x0 + x1) / 2, (z0 + z1) / 2), c.GetProperty("token").GetString(), (float)(x1 - x0), (float)(z1 - z0));
                    ca.ShowInUi = true;
                }
            }
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
            var pts = e.GetProperty("pts").EnumerateArray().Select(p => V(p[0].GetDouble(), p[1].GetDouble())).ToList();
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
            // oyun sınırı: tek yol parçası ≤ 1000 m; uzun parçaları ≤ 400 m'ye böl
            for (int i = seq.Count - 1; i > 0; i--)
            {
                float L = Vector3.Distance(seq[i - 1], seq[i]);
                int k = (int)MathF.Ceiling(L / 400f);
                for (int s = 1; s < k; s++) seq.Insert(i, seq[i - 1]); // yer tutucu, aşağıda doldurulur
                if (k > 1)
                {
                    var a0 = seq[i - 1]; var b0 = seq[i + k - 1];
                    for (int s = 1; s < k; s++) seq[i - 1 + s] = Vector3.Lerp(a0, b0, s / (float)k);
                }
            }
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
        int buildings = AddBuildings(map, cfg, Path.Combine(Root, exportRel), new Vector3(off.X, 0, off.Y), noBuild);

        // 4) zemin: ground_s3.json sütun parçaları → Terrain öğeleri (yolların biraz altında)
        int ground = AddGround(map, cfg, Path.Combine(Root, "data", "processed", "ground_s3.json"), new Vector3(off.X, 0, off.Y));

        var outDir = cfg.GetProperty("output_map_dir").GetString();
        var name = cfg.GetProperty("output_map_name").GetString();
        if (name == "saklaz" || name == "europe") throw new InvalidOperationException("Korumalı ad.");
        map.Save(outDir, name, true);
        Console.WriteLine("Prefab dağılımı: " + string.Join(", ", byToken.Select(kv => $"{kv.Key}={kv.Value}")));
        Console.WriteLine($"Kaydedildi: {name}.mbd  kavşak={placed} (reddedilen {rejected})  yol={roads} segment={segs} bağlantı={connected} atlanan={skipped} bina={buildings} zemin={ground} depo={depots}");
        return 0;
    }

    // Düz (Z eksenine paralel), kavşaklardan ve diğer yollardan uzak bir şehir yolu parçası bulur;
    // ortasını orijine taşıyacak kaydırmayı (X, Z) döndürür.
    static Vector2 FindSpawnOffset(JsonElement graph, JsonElement cfg)
    {
        var sp = cfg.TryGetProperty("spawn", out var s) ? s : default;
        double Opt(string k, double d) => sp.ValueKind == JsonValueKind.Object && sp.TryGetProperty(k, out var v) ? v.GetDouble() : d;
        double minLen = Opt("min_len", 50), maxErr = Opt("max_dir_err_deg", 4), clear = Opt("clearance", 25), junc = Opt("junction_clearance", 60);
        var okTypes = sp.ValueKind == JsonValueKind.Object && sp.TryGetProperty("types", out var tt)
            ? tt.EnumerateArray().Select(x => x.GetString()).ToHashSet() : new HashSet<string> { "r1_city", "r2_divided" };

        var segs = new List<(int edge, Vector2 a, Vector2 b)>();
        var edges = graph.GetProperty("edges").EnumerateArray().ToList();
        foreach (var e in edges)
        {
            var pts = e.GetProperty("pts").EnumerateArray().Select(p => new Vector2((float)p[0].GetDouble(), (float)p[1].GetDouble())).ToList();
            for (int i = 1; i < pts.Count; i++) segs.Add((e.GetProperty("id").GetInt32(), pts[i - 1], pts[i]));
        }
        var juncs = graph.GetProperty("junctions").EnumerateArray().Select(j => new Vector2((float)j.GetProperty("x").GetDouble(), (float)j.GetProperty("z").GetDouble())).ToList();
        static float SegDist(Vector2 p, Vector2 a, Vector2 b)
        {
            var ab = b - a; float t = ab.LengthSquared() < 1e-6f ? 0 : Math.Clamp(Vector2.Dot(p - a, ab) / ab.LengthSquared(), 0, 1);
            return Vector2.Distance(p, a + t * ab);
        }
        var typeOf = edges.ToDictionary(e => e.GetProperty("id").GetInt32(), e => e.GetProperty("type").GetString());
        var best = (d: float.MaxValue, mid: Vector2.Zero, edge: -1);
        foreach (var (edge, a, b) in segs)
        {
            if (!okTypes.Contains(typeOf[edge])) continue;
            var d = b - a; float len = d.Length();
            if (len < minLen) continue;
            float err = MathF.Acos(MathF.Abs(d.Y) / len) * 180f / MathF.PI;
            if (err > maxErr) continue;
            var mid = (a + b) / 2;
            if (mid.Length() >= best.d) continue;
            if (juncs.Any(j => Vector2.Distance(j, mid) < junc)) continue;
            // aynı parçanın uçları hariç, başka hiçbir yol parçası 'clear' m içinde olmamalı (yan yola ve paralel yollara karşı)
            bool busy = segs.Any(o => o.edge != edge && SegDist(mid, o.a, o.b) < clear);
            if (busy) continue;
            best = (mid.Length(), mid, edge);
        }
        if (best.edge < 0) { Console.WriteLine("Başlangıç: uygun yol bulunamadı, kaydırma yok."); return Vector2.Zero; }
        Console.WriteLine($"Başlangıç: kenar {best.edge} ({typeOf[best.edge]}), eski konum ({best.mid.X:F1}, {best.mid.Y:F1}) → (0,0)");
        return -best.mid;
    }

    static int AddGround(Map map, JsonElement cfg, string groundPath, Vector3 off)
    {
        if (!File.Exists(groundPath) || !cfg.TryGetProperty("ground", out var g)) return 0;
        var ground = JsonDocument.Parse(File.ReadAllText(groundPath)).RootElement;
        float half = (float)ground.GetProperty("meta").GetProperty("cell").GetDouble() / 2f;
        float y = (float)g.GetProperty("y").GetDouble();
        float maxSeg = (float)g.GetProperty("max_segment").GetDouble();
        var classes = g.GetProperty("classes");
        int n = 0, bad = 0;

        foreach (var r in ground.GetProperty("runs").EnumerateArray())
        {
            var cls = r.GetProperty("cls").GetString();
            if (!classes.TryGetProperty(cls, out var cc)) continue;
            bool trees = r.GetProperty("trees").GetBoolean();
            float x = (float)r.GetProperty("x").GetDouble(), z0 = (float)r.GetProperty("z0").GetDouble(), z1 = (float)r.GetProperty("z1").GetDouble();
            // -Z yönünde ilerle (z1 → z0): sol taraf -X, sağ taraf +X
            int segs = Math.Max(1, (int)MathF.Ceiling((z1 - z0) / maxSeg));
            try
            {
                var mat = cc.GetProperty("material").GetString();
                var t = Terrain.Add(map, off + new Vector3(x, y, z1), off + new Vector3(x, y, z1 - (z1 - z0) / segs), mat, half, half);
                var items = new List<Terrain> { t };
                for (int k = 2; k <= segs; k++) { t = t.Append(off + new Vector3(x, y, z1 - (z1 - z0) * k / segs), mat, half, half); items.Add(t); }
                foreach (var it in items)
                {
                    it.StepSize = StepSize.Meters16;
                    it.Collision = true;
                    foreach (var side in new[] { it.Left, it.Right })
                    {
                        side.Terrain.Noise = TerrainNoise.Percent0;
                        if (trees && cc.TryGetProperty("vegetation", out var veg))
                        {
                            side.Vegetation[0].Name = veg.GetString();
                            side.Vegetation[0].Density = (float)cc.GetProperty("density").GetDouble();
                            side.Vegetation[0].Scale = VegetationScale.Percent80to120;
                            side.Vegetation[0].From = 0;
                            side.Vegetation[0].To = half;
                        }
                        side.DetailVegetation = cls is "grass" or "park" or "farm" or "forest" or "scrub";
                    }
                }
                n += items.Count;
            }
            catch (Exception ex) { if (bad++ < 5) Console.WriteLine($"zemin atlandı: {ex.Message}"); }
        }
        return n;
    }

    static int AddBuildings(Map map, JsonElement cfg, string exportPath, Vector3 off, List<(Vector3 c, float r)> noBuild = null)
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
            var pos = off + new Vector3((float)bl.GetProperty("x").GetDouble(), 0f, (float)bl.GetProperty("z").GetDouble());
            if (noBuild != null && noBuild.Any(z => Vector3.DistanceSquared(z.c, pos) < z.r * z.r)) continue;
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
            "house" or "detached" or "semidetached_house" or "bungalow" or "terrace" => "small_house",
            "mosque" or "religious" => "mosque",
            _ => (bl.GetProperty("area_real_m2").GetDouble() > 250 ? "apartment" : "small_house"),
        };
        if (!b.TryGetProperty(key, out var v)) return null;
        if (v.ValueKind == JsonValueKind.String) return v.GetString();
        // liste: OSM id'ye göre sabit ama çeşitli seçim
        var arr = v.EnumerateArray().ToArray();
        long osm = Math.Abs(bl.GetProperty("osm").GetInt64());
        return arr.Length == 0 ? null : arr[(int)((osm / 7) % arr.Length)].GetString();
    }

    static string FindRoot()
    {
        var d = new DirectoryInfo(AppContext.BaseDirectory);
        while (d != null && !File.Exists(Path.Combine(d.FullName, "config", "aoi.json"))) d = d.Parent;
        return d?.FullName ?? Directory.GetCurrentDirectory();
    }
}
