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
            "modelinfo" => ModelInfo(cfg, args.Skip(1).SelectMany(a => a.StartsWith("@") ? File.ReadAllLines(a[1..]) : new[] { a }).Where(s => s.Length > 0).ToArray()),
            "prefabinfo" => PrefabInfo(cfg, args.Skip(1).ToArray()),
            "ppdnav" => PpdNav(cfg, args.Skip(1).ToArray()),
            "companyprefabs" => CompanyPrefabs(cfg),
            "nodetest" => NodeTest(cfg, args.Skip(1).ToArray()),
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
                var bb = m.BoundingBox; Console.WriteLine($"{p} [{hit.name}]: parça={m.Parts.Sum(pt => pt.Pieces.Count)} looks=[{string.Join(",", m.Looks.Select(l => l.Name))}] variants=[{string.Join(",", m.Variants.Select(v => v.Name))}] boyut={bb.End - bb.Start}");
            }
            catch (Exception ex) { Console.WriteLine($"{p}: HATA {ex.GetType().Name}: {ex.Message}"); }
        }
        foreach (var k in packs) k.fs.Dispose();
        return 0;
    }

    // ---------------------------------------------------------------- companyprefabs
    // def.scs + dlc'siz: her şirketin editor/*.sii dosyalarındaki prefab tokenlarını sayar (salt okunur).
    static int CompanyPrefabs(JsonElement cfg)
    {
        var gameRoot = cfg.GetProperty("game_root").GetString();
        using var fs = HashFsReader.Open(Path.Combine(gameRoot, "def.scs"));
        var rows = new List<string>();
        foreach (var c in fs.GetDirectoryListing("/def/company").Subdirectories)
        {
            var ed = c.TrimEnd('/') + "/editor";
            if (!fs.DirectoryExists(ed)) continue;
            var cnt = new Dictionary<string, int>();
            foreach (var f in fs.GetDirectoryListing(ed).Files)
            {
                var txt = Encoding.UTF8.GetString(fs.Extract(f)[0]);
                foreach (System.Text.RegularExpressions.Match m in System.Text.RegularExpressions.Regex.Matches(txt, @"prefab:\s*([A-Za-z0-9_\.]+)"))
                    cnt[m.Groups[1].Value] = cnt.GetValueOrDefault(m.Groups[1].Value) + 1;
            }
            var name = c.TrimEnd('/').Split('/').Last();
            foreach (var kv in cnt) rows.Add($"{name}\t{kv.Key}\t{kv.Value}");
        }
        var outp = Path.Combine(Root, "data", "processed", "game_defs", "company_prefabs.tsv");
        File.WriteAllLines(outp, rows);
        Console.WriteLine($"{rows.Count} satır -> {outp}");
        return 0;
    }

    // ---------------------------------------------------------------- ppdnav
    // .ppd düğümlerini ve navigasyon eğrilerini (başlangıç/bitiş konumu) yazdırır: akış yönünü bulmak için.
    static int PpdNav(JsonElement cfg, string[] ppds)
    {
        var gameRoot = cfg.GetProperty("game_root").GetString();
        using var fs = HashFsReader.Open(Path.Combine(gameRoot, "base.scs"));
        foreach (var p in ppds)
        {
            var d = TruckLib.Models.Ppd.PrefabDescriptor.Open(p, fs);
            Console.WriteLine($"== {p}");
            for (int i = 0; i < d.Nodes.Count; i++)
            {
                var n = d.Nodes[i];
                Console.WriteLine($"  node{i} pos={n.Position} dir={n.Direction} " +
                    string.Join(" ", n.GetType().GetProperties().Where(pr => pr.Name.Contains("Lane") || pr.Name.Contains("Curve"))
                        .Select(pr => $"{pr.Name}={Fmt(pr.GetValue(n))}")));
            }
            var navProp = d.GetType().GetProperties().FirstOrDefault(pr => pr.Name.Contains("Nav"));
            if (navProp?.GetValue(d) is System.Collections.IEnumerable curves)
            {
                int k = 0;
                foreach (var c in curves)
                {
                    var t = c.GetType();
                    string F(string name) => t.GetProperty(name) is { } pi ? Fmt(pi.GetValue(c)) : "-";
                    Console.WriteLine($"  nav{k++} start={F("StartPosition")} end={F("EndPosition")} next={F("NextLines")} prev={F("PreviousLines")}");
                }
                if (k == 0) Console.WriteLine($"  ({navProp.Name} boş) özellikler: {string.Join(",", curves.GetType().GetProperties().Select(x => x.Name))}");
            }
            else Console.WriteLine("  özellikler: " + string.Join(",", d.GetType().GetProperties().Select(x => x.Name)));
        }
        return 0;
    }

    // Prefab düğümlerinde ileri/geri öğe durumu ve AppendRoad/Attach denemesi (TruckLib davranışını ölçmek için)
    static int NodeTest(JsonElement cfg, string[] args)
    {
        var gameRoot = cfg.GetProperty("game_root").GetString();
        using var fs = HashFsReader.Open(Path.Combine(gameRoot, "base.scs"));
        {
            var ppd = TruckLib.Models.Ppd.PrefabDescriptor.Open(args[1], fs);
            var map = new Map();
            var pf = Prefab.Add(map, Vector3.Zero, args[0], ppd, Quaternion.Identity);
            var before = pf.Nodes.Select(n => n.Position).ToList();
            pf.ChangeOrigin(1);
            Console.WriteLine($"ChangeOrigin(1): Origin={pf.Origin} sıra=" + string.Join(",", pf.Nodes.Select(n => before.FindIndex(b => Vector3.Distance(b, n.Position) < 0.01f))));
            for (int k = 0; k < pf.Nodes.Count; k++)
            {
                var m2 = new Map();
                var p2 = Prefab.Add(m2, Vector3.Zero, args[0], ppd, Quaternion.Identity);
                p2.ChangeOrigin(1);
                var n = p2.Nodes[k];
                var c2 = p2.Nodes.Aggregate(Vector3.Zero, (a, x) => a + x.Position) / p2.Nodes.Count;
                var r = p2.AppendRoad((ushort)k, n.Position + Vector3.Normalize(n.Position - c2) * 30, "ger1", 0, 0);
                Console.WriteLine($"  idx{k}: yolBaşı={(Vector3.Distance(r.Node.Position, n.Position) < 0.1f ? "prefab" : "uzak")}");
            }
        }
        for (int i = 2; i + 1 < args.Length; i += 2)
        {
            var ppd = TruckLib.Models.Ppd.PrefabDescriptor.Open(args[i + 1], fs);
            var c = ppd.Nodes.Aggregate(Vector3.Zero, (acc, n) => acc + n.Position) / ppd.Nodes.Count;
            for (int ni = 0; ni < ppd.Nodes.Count; ni++)
            {
                foreach (var outward in new[] { true, false })
                {
                    var map = new Map();
                    var pf = Prefab.Add(map, new Vector3(0, 0, 0), args[i], ppd, Quaternion.Identity);
                    var n = pf.Nodes[ni];
                    var dirOut = Vector3.Normalize(new Vector3(n.Position.X - c.X, 0, n.Position.Z - c.Z));
                    var rotF = Vector3.Transform(Vector3.UnitZ, n.Rotation);
                    var tgt = n.Position + (outward ? dirOut : -dirOut) * 30;
                    string st = $"{args[i]} n{ni} {(outward ? "dış" : "iç ")} rotF·out={Vector3.Dot(rotF, dirOut):F2}";
                    try
                    {
                        var r = pf.AppendRoad((ushort)ni, tgt, "ger16", 0, 0);
                        bool startAtPrefab = Vector3.Distance(r.Node.Position, n.Position) < 0.1f;
                        st += $" AppendRoad=OK yolBaşı={(startAtPrefab ? "prefab" : "uzak")}";
                        try { r.Append(tgt + (tgt - n.Position)); st += " +Append=OK"; } catch (Exception ex) { st += " +Append=FAIL"; }
                    }
                    catch (Exception ex) { st += " AppendRoad=FAIL(" + ex.Message + ")"; }
                    Console.WriteLine(st);
                }
            }
        }
        return 0;
    }

    // TruckLib Prefab.Add dönüşü düğüm 0'ın ppd yönüne göre uygular; düğüm 0'ı farklı yöne bakan prefablarda
    // (ör. ch_4202j) prefab ters yerleşir. Boş bir haritada deneyerek düğümleri istenen konumlara oturtan
    // yaw düzeltmesini bulur. maxDev: en kötü düğüm sapması (m).
    static readonly Dictionary<string, float> prefabYawFix = new();
    static int prefabFixed = 0;
    static float worstPrefabDev = 0;
    static Prefab AddPrefabChecked(Map map, string token, TruckLib.Models.Ppd.PrefabDescriptor ppd, Quaternion q, List<Vector3> want)
    {
        float Dev(Prefab p) => Enumerable.Range(0, want.Count).Max(k => Vector3.Distance(p.Nodes[k].Position, want[k]));
        Quaternion Fix(float deg) => Quaternion.CreateFromYawPitchRoll(deg * MathF.PI / 180f, 0, 0) * q;
        // düzeltme açısı prefab tipine özgü ve sabit; önbellekte yoksa ara
        string key = token + "|" + ppd.Nodes.Count;
        if (!prefabYawFix.TryGetValue(key, out var fix) || Dev(Prefab.Add(new Map(), want[0], token, ppd, Fix(fix))) > 0.5f)
        {
            float best = 0, bestDev = float.MaxValue;
            for (float d = 0; d < 360; d += 0.5f)
            {
                float dv = Dev(Prefab.Add(new Map(), want[0], token, ppd, Fix(d)));
                if (dv < bestDev) { bestDev = dv; best = d; }
            }
            fix = best; prefabYawFix[key] = fix;
        }
        var pf = Prefab.Add(map, want[0], token, ppd, Fix(fix));
        float dev = Dev(pf);
        if (fix != 0) prefabFixed++;
        worstPrefabDev = MathF.Max(worstPrefabDev, dev);
        if (dev > 1f) throw new InvalidOperationException($"{token} düğümleri yerine oturmadı (sapma {dev:F1} m)");
        return pf;
    }

    static string Fmt(object o) => o switch
    {
        null => "null",
        string s => s,
        System.Collections.IEnumerable e => "[" + string.Join(",", e.Cast<object>().Take(8)) + "]",
        _ => o.ToString(),
    };

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
        var rejectedNodes = new List<int>();
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
            if (bestPerm == null || bestMax > maxErr) { rejected++; rejectedNodes.Add(jn.GetProperty("node").GetInt32()); continue; }
            var nodePos = spec.ppd.Nodes.Select(nd => nd.Position).ToList();
            float radius = nodePos.Max(p => new Vector2(p.X, p.Z).Length()) + 3f;
            try
            {
                var qb = Quaternion.CreateFromYawPitchRoll(bestYaw * MathF.PI / 180f, 0, 0);
                var pf = AddPrefabChecked(map, spec.token, spec.ppd, qb, nodePos.Select(p => center + Vector3.Transform(p, qb)).ToList());
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
            catch (Exception ex) { rejected++; rejectedNodes.Add(jn.GetProperty("node").GetInt32()); if (rejected < 10) Console.WriteLine($"kavşak {jn.GetProperty("id")}: {ex.Message}"); }
        }

        // 1b) şirket depoları (iki düğümlü prefab, yol ikiye bölünmüş) + Company öğeleri
        // 1b) Otoyol çıkış / katılma prefabları (ppdnav ile akış yönü doğrulandı: node0 giriş, node1 ana çıkış,
        //     node2 rampa; rampa sağda). anchor = OSM ayrılma/katılma düğümüne oturan prefab düğümü.
        int hwPlaced = 0, hwRejected = 0;
        if (cfg.TryGetProperty("hw_junctions", out var hcfg) && graph.TryGetProperty("hw_junctions", out var hlist))
        {
            var hspec = new Dictionary<string, (string token, TruckLib.Models.Ppd.PrefabDescriptor ppd, int anchor, string look, string variant)>();
            foreach (var hp in hcfg.EnumerateObject().Where(o => !o.Name.StartsWith("_")))
            {
                var kind = hp.Name; var h = hp.Value;
                hspec[kind] = (h.GetProperty("token").GetString(),
                               TruckLib.Models.Ppd.PrefabDescriptor.Open(h.GetProperty("ppd").GetString(), fs),
                               h.GetProperty("anchor").GetInt32(), h.GetProperty("look").GetString(), h.GetProperty("variant").GetString());
            }
            foreach (var hj in hlist.EnumerateArray())
            {
                try
                {
                    var sp = hspec[hj.TryGetProperty("variant", out var hv) ? hv.GetString() : hj.GetProperty("kind").GetString() + "_hi"];
                    var np = sp.ppd.Nodes.Select(n => n.Position).ToList();
                    var J = V(hj.GetProperty("x").GetDouble(), hj.GetProperty("z").GetDouble());
                    var travel = Vector2.Normalize(new Vector2((float)hj.GetProperty("travel")[0].GetDouble(), (float)hj.GetProperty("travel")[1].GetDouble()));
                    // akış yönü = node0'ın prefab içine bakan yönü (lo prefablarında node0-node1 hattı yanal kaymalı)
                    var d0 = sp.ppd.Nodes[0].Direction;
                    var localT = Vector2.Normalize(new Vector2(d0.X, d0.Z));
                    int bestYaw = 0; float bestDot = -2;
                    for (int yd = 0; yd < 360; yd++)
                    {
                        var v = Vector3.Transform(new Vector3(localT.X, 0, localT.Y), Quaternion.CreateFromYawPitchRoll(yd * MathF.PI / 180f, 0, 0));
                        float dot = Vector2.Dot(new Vector2(v.X, v.Z), travel);
                        if (dot > bestDot) { bestDot = dot; bestYaw = yd; }
                    }
                    var q = Quaternion.CreateFromYawPitchRoll(bestYaw * MathF.PI / 180f, 0, 0);
                    var origin = J - Vector3.Transform(np[sp.anchor], q);
                    var w = np.Select(p => origin + Vector3.Transform(p, q)).ToList();
                    // rampa düğümü şeride göre sağda mı? (sağ = (-tz, tx), +Z güney)
                    var right = new Vector2(-travel.Y, travel.X);
                    var mid01 = (w[0] + w[1]) / 2;
                    float side = Vector2.Dot(new Vector2(w[2].X - mid01.X, w[2].Z - mid01.Z), right);
                    if (side <= 0) { hwRejected++; continue; }
                    var pf = AddPrefabChecked(map, sp.token, sp.ppd, q, w);
                    if (Environment.GetEnvironmentVariable("SAKLAZ_DEBUG") == "1")
                        Console.WriteLine($"hw {hj.GetProperty("id")} {sp.token}: " + string.Join(" ", Enumerable.Range(0, w.Count).Select(k => $"n{k}Δ={Vector3.Distance(pf.Nodes[k].Position, w[k]):F1}")));
                    pf.Look = sp.look;
                    pf.Variant = sp.variant;
                    var mid = (w[0] + w[1]) / 2;
                    foreach (var arm in hj.GetProperty("arms").EnumerateArray())
                    {
                        int ni = arm.GetProperty("role").GetString() switch { "in" => 0, "out" => 1, _ => 2 };
                        var actual = pf.Nodes.OrderBy(n => Vector3.DistanceSquared(n.Position, w[ni])).First().Position;
                        attach[(arm.GetProperty("edge").GetInt32(), arm.GetProperty("end").GetString())] = (pf, actual, mid, 26f);
                    }
                    hwPlaced++;
                }
                catch (Exception ex) { hwRejected++; if (hwRejected < 10) Console.WriteLine($"otoyol kavşağı {hj.GetProperty("id")}: {ex.Message}"); }
            }
            Console.WriteLine($"otoyol çıkış/katılma prefabı: {hwPlaced} (reddedilen {hwRejected})");
        }

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
                    var pf = AddPrefabChecked(map, kind.GetProperty("token").GetString(), ppd, best.q,
                                              ppd.Nodes.Select(n => best.origin + Vector3.Transform(n.Position, best.q)).ToList());
                    pf.Look = kind.GetProperty("look").GetString();
                    pf.Variant = dcfg.GetProperty("variants").TryGetProperty(d.GetProperty("kind").GetString(), out var vk) && vk.TryGetProperty(company, out var vr) ? vr.GetString() : "default";
                    foreach (var (arm, want) in new[] { (d.GetProperty("arm0"), n0), (d.GetProperty("arm1"), n1) })
                    {
                        var actual = pf.Nodes.OrderBy(n => Vector3.DistanceSquared(n.Position, want)).First().Position;
                        attach[(arm.GetProperty("edge").GetInt32(), arm.GetProperty("end").GetString())] = (pf, actual, actual, 1f);
                    }
                    var co = Company.Add(map, pf, best.origin);
                    noBuild.Add((best.origin, 75f));
                    co.CompanyName = company;
                    co.CityName = d.TryGetProperty("city", out var dc) ? dc.GetString() : city;
                    // oyun şehri öğenin konumundaki CityArea'dan belirler; ızgara alanıyla karşılaştır
                    if (graph.TryGetProperty("city_areas", out var cal))
                    {
                        var o = best.origin; string areaTok = null;
                        foreach (var a in cal.EnumerateArray())
                        {
                            var (ax0, az0) = (V(a.GetProperty("x0").GetDouble(), a.GetProperty("z0").GetDouble()).X, V(a.GetProperty("x0").GetDouble(), a.GetProperty("z0").GetDouble()).Z);
                            var (ax1, az1) = (V(a.GetProperty("x1").GetDouble(), a.GetProperty("z1").GetDouble()).X, V(a.GetProperty("x1").GetDouble(), a.GetProperty("z1").GetDouble()).Z);
                            if (o.X >= Math.Min(ax0, ax1) && o.X <= Math.Max(ax0, ax1) && o.Z >= Math.Min(az0, az1) && o.Z <= Math.Max(az0, az1)) { areaTok = a.GetProperty("token").GetString(); break; }
                        }
                        if (areaTok == null) Console.WriteLine($"UYARI depo {d.GetProperty("id")}: şirket öğesi hiçbir şehir alanında değil");
                        else if (areaTok != co.CityName) { Console.WriteLine($"UYARI depo {d.GetProperty("id")}: grafik şehri {co.CityName}, oyun alanı {areaTok} → {areaTok}"); co.CityName = areaTok; }
                    }
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
            if (dcfg.GetProperty("city_area").GetBoolean() && graph.TryGetProperty("city_areas", out var alist))
            {
                // Üst üste binmeyen ızgara alanları (build_city_graph.city_grid); her şehrin en büyük alanı UI'da adını gösterir
                var areas = alist.EnumerateArray().Select(c => (tok: c.GetProperty("token").GetString(),
                    x0: c.GetProperty("x0").GetDouble(), z0: c.GetProperty("z0").GetDouble(),
                    x1: c.GetProperty("x1").GetDouble(), z1: c.GetProperty("z1").GetDouble())).ToList();
                var label = areas.GroupBy(a => a.tok).ToDictionary(g => g.Key, g => g.OrderByDescending(a => (a.x1 - a.x0) * (a.z1 - a.z0)).First());
                foreach (var a in areas)
                {
                    var ca = CityArea.Add(map, V((a.x0 + a.x1) / 2, (a.z0 + a.z1) / 2), a.tok, (float)(a.x1 - a.x0), (float)(a.z1 - a.z0));
                    ca.ShowInUi = label[a.tok].Equals(a);
                }
                Console.WriteLine($"şehir alanı: {areas.Count} dikdörtgen ({string.Join(", ", areas.GroupBy(a => a.tok).Select(g => $"{g.Key}={g.Count()}"))})");
            }
            else if (dcfg.GetProperty("city_area").GetBoolean() && graph.TryGetProperty("cities", out var clist))
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

        // 1c) origin seçimi: TruckLib/ETS2'de prefab origin düğümüne yalnızca yolun BİTİŞ ucu bağlanabilir.
        //     Her prefab için origin = boş kol > gelen tek yönlü yol > öbür ucu origin olmayan çift yönlü yol.
        int originChanged = 0;
        {
            var kindOf = graph.GetProperty("edges").EnumerateArray().ToDictionary(x => x.GetProperty("id").GetInt32(), x => x.GetProperty("type").GetString());
            bool OneWay(string k) => k.EndsWith("_oneway") || k == "ramp_1lane";
            var byPf = attach.Where(kv => kv.Value.radius > 1f).GroupBy(kv => kv.Value.p, ReferenceEqualityComparer.Instance)
                             .ToDictionary(g => (Prefab)g.Key, g => g.ToList());
            int IdxAt(Prefab p, Vector3 pos) => p.Nodes.FindIndex(n => Vector3.DistanceSquared(n.Position, pos) < 0.01f);
            bool OtherEndIsOrigin(int edge, string end)
            {
                var o = end == "a" ? "b" : "a";
                return attach.TryGetValue((edge, o), out var x) && x.p != null && IdxAt(x.p, x.nodePos) == 0;
            }
            int Score(Prefab p, int k)
            {
                var pos = p.Nodes[k].Position;
                var arms = byPf[p].Where(kv => Vector3.DistanceSquared(kv.Value.nodePos, pos) < 0.01f).ToList();
                if (arms.Count == 0) return 3;
                var (edge, end) = arms[0].Key;
                if (OneWay(kindOf[edge])) return end == "b" ? 2 : -10;
                return OtherEndIsOrigin(edge, end) ? 0 : 1;
            }
            for (int pass = 0; pass < 3; pass++)
                foreach (var p in byPf.Keys)
                {
                    int cur = Score(p, 0), best = 0, bestS = cur;
                    for (int k = 1; k < p.Nodes.Count; k++) { int sc = Score(p, k); if (sc > bestS) { bestS = sc; best = k; } }
                    if (best != 0 && bestS > cur)
                    {
                        var want = p.Nodes[best].Position;
                        p.ChangeOrigin((ushort)((p.Origin + best) % p.Nodes.Count)); // ChangeOrigin mutlak ppd indeksi alır
                        if (Vector3.DistanceSquared(p.Nodes[0].Position, want) > 0.01f)
                            throw new InvalidOperationException("ChangeOrigin beklenen düğümü origin yapmadı");
                        originChanged++;
                    }
                }
        }
        Console.WriteLine($"prefab origin değiştirilen: {originChanged}");

        // 2) yollar
        float R = (float)graph.GetProperty("meta").GetProperty("prefab_radius").GetDouble() + 3f;
        var shortSkip = new Dictionary<string, int>();
        var roadEnds = new Dictionary<(int, string), INode>();
        // 2a) r1↔r2 bağlantıları için yön ön planı: bağlantı noktasında yollardan biri bitmeli, öbürü başlamalı.
        //     Origin düğümüne dokunmayan çift yönlü yol serbestçe ters kurulabilir.
        var extraFlip = new HashSet<int>();
        int linkPlanFail = 0;
        {
            var edgeById = graph.GetProperty("edges").EnumerateArray().ToDictionary(x => x.GetProperty("id").GetInt32());
            bool OneWayKind(string k) => k.EndsWith("_oneway") || k == "ramp_1lane";
            bool OriginEnd(int id, string end) => attach.TryGetValue((id, end), out var x) && x.p != null &&
                x.p.Nodes.FindIndex(n => Vector3.DistanceSquared(n.Position, x.nodePos) < 0.01f) == 0;
            bool Has(int id, string end) => attach.TryGetValue((id, end), out var x) && x.p != null;
            bool NaturalFlip(int id)
            {
                var ed = edgeById[id]; bool ow = OneWayKind(ed.GetProperty("type").GetString());
                bool hA = Has(id, "a"), hB = Has(id, "b");
                bool f = !hA && !hB && ed.GetProperty("reverse").GetBoolean();
                if (hA && OriginEnd(id, "a") && !ow && !(hB && OriginEnd(id, "b"))) f = !f;
                return f;
            }
            bool Free(int id) => !OneWayKind(edgeById[id].GetProperty("type").GetString()) && !OriginEnd(id, "a") && !OriginEnd(id, "b");
            var fixedE = new HashSet<int>();
            if (graph.TryGetProperty("road_links", out var rl0))
                foreach (var lk in rl0.EnumerateArray())
                {
                    int e1 = lk[0].GetInt32(), e2 = lk[2].GetInt32();
                    if (!edgeById.ContainsKey(e1) || !edgeById.ContainsKey(e2)) continue;
                    bool S1 = (lk[1].GetString() == "a") ^ (NaturalFlip(e1) ^ extraFlip.Contains(e1));
                    bool S2 = (lk[3].GetString() == "a") ^ (NaturalFlip(e2) ^ extraFlip.Contains(e2));
                    if (S1 != S2) { fixedE.Add(e1); fixedE.Add(e2); continue; }
                    if (Free(e2) && !fixedE.Contains(e2)) { if (!extraFlip.Add(e2)) extraFlip.Remove(e2); }
                    else if (Free(e1) && !fixedE.Contains(e1)) { if (!extraFlip.Add(e1)) extraFlip.Remove(e1); }
                    else { linkPlanFail++; continue; }
                    fixedE.Add(e1); fixedE.Add(e2);
                }
        }
        int roads = 0, segs = 0, skipped = 0, connected = 0, failed = 0, reversedAtOrigin = 0, originUnattached = 0;
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
            bool flipped = false;
            if (!hasA && !hasB && e.GetProperty("reverse").GetBoolean()) { pts.Reverse(); flipped = true; }
            var mid = pts.Where(p => (!hasA || Vector3.Distance(p, sa.center) > sa.radius) && (!hasB || Vector3.Distance(p, sb.center) > sb.radius)).ToList();
            var seq = new List<Vector3>();
            if (hasA) seq.Add(sa.nodePos);
            foreach (var p in mid) if (seq.Count == 0 || Vector3.Distance(seq[^1], p) > 3f) seq.Add(p);
            if (hasB) { if (seq.Count > 0 && Vector3.Distance(seq[^1], sb.nodePos) < 3f) seq.RemoveAt(seq.Count - 1); seq.Add(sb.nodePos); }
            if (seq.Count < 2) { skipped++; shortSkip[(hasA ? "A" : "-") + (hasB ? "B" : "-")] = shortSkip.GetValueOrDefault((hasA ? "A" : "-") + (hasB ? "B" : "-")) + 1; continue; }
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
            // TruckLib: prefabın 0 numaralı (origin) düğümünde yol prefabta BİTER, diğer düğümlerde prefabtan BAŞLAR.
            // Çift yönlü yol origin düğümünden başlıyorsa ters kurulur; tek yönlüde yön korunur ve uç sonradan bağlanır.
            static int NodeIdx(Prefab p, Vector3 pos) => p.Nodes.FindIndex(n => Vector3.DistanceSquared(n.Position, pos) < 0.01f);
            // yön yalnızca tek yönlü yol görünümlerinde (otoyol şeritleri, rampa) önemlidir
            bool oneway = kind.EndsWith("_oneway") || kind == "ramp_1lane";
            if (hasA && NodeIdx(sa.p, sa.nodePos) == 0 && !oneway && !(hasB && NodeIdx(sb.p, sb.nodePos) == 0))
            {
                seq.Reverse();
                (sa, sb) = (sb, sa);
                (hasA, hasB) = (hasB, hasA);
                reversedAtOrigin++;
                flipped = !flipped;
            }
            if (extraFlip.Contains(id))
            {
                seq.Reverse();
                (sa, sb) = (sb, sa);
                (hasA, hasB) = (hasB, hasA);
                flipped = !flipped;
            }
            string stage = "start";
            try
            {
                Road road;
                bool attachStartLater = false;
                if (hasA && NodeIdx(sa.p, sa.nodePos) != 0)
                {
                    stage = "A:" + sa.p.Model;
                    road = sa.p.AppendRoad((ushort)NodeIdx(sa.p, sa.nodePos), seq[1], token, ts, ts);
                    connected++;
                }
                else { road = Road.Add(map, seq[0], seq[1], token, ts, ts); attachStartLater = hasA; }
                var firstRoad = road;
                segs++;
                stage = "append";
                for (int i = 2; i < seq.Count; i++) { road = road.Append(seq[i]); segs++; }
                stage = hasB ? "B:" + sb.p.Model : "end";
                if (hasB) { sb.p.Attach(road); connected++; }
                if (attachStartLater)
                {
                    stage = "A-origin:" + sa.p.Model;
                    try { sa.p.Attach(firstRoad); connected++; }
                    catch (Exception ex2) { originUnattached++; if (originUnattached < 10) Console.WriteLine($"kenar {id} ({kind}) origin ucu bağlanamadı: {ex2.Message}"); }
                }
                roadEnds[(id, flipped ? "b" : "a")] = firstRoad.Node;
                roadEnds[(id, flipped ? "a" : "b")] = road.ForwardNode;
                roads++;
            }
            catch (Exception ex)
            {
                skipped++; failed++;
                if (failed < 40) Console.WriteLine($"kenar {id} ({kind}) atlandı [{stage}, seq={seq.Count}]: {ex.Message}");
            }
        }

        // 2b) farklı görünümlü yolların (r1↔r2) düz geçişleri: uç düğümlerini birleştir
        int linked = 0, linkFail = 0;
        if (graph.TryGetProperty("road_links", out var rl))
            foreach (var lk in rl.EnumerateArray())
            {
                var k1 = (lk[0].GetInt32(), lk[1].GetString());
                var k2 = (lk[2].GetInt32(), lk[3].GetString());
                if (!roadEnds.TryGetValue(k1, out var n1) || !roadEnds.TryGetValue(k2, out var n2)) { linkFail++; continue; }
                try { n1.Merge(n2); linked++; }
                catch
                {
                    try { n2.Merge(n1); linked++; }
                    catch (Exception ex) { linkFail++; if (linkFail < 6) Console.WriteLine($"yol bağlantısı {k1}-{k2}: {ex.Message}"); }
                }
            }
        Console.WriteLine($"r1↔r2 yol bağlantısı: {linked} (başarısız {linkFail}, yön planı çözülemeyen {linkPlanFail}, ters kurulan {extraFlip.Count})");
        File.WriteAllText(Path.Combine(Root, "data", "processed", "junction_rejects.json"),
            JsonSerializer.Serialize(rejectedNodes.Distinct().OrderBy(x => x)));
        Console.WriteLine($"reddedilen kavşak düğümleri yazıldı: {rejectedNodes.Count} (data/processed/junction_rejects.json)");

        // 3) binalar (map_export'tan, place=true olanlar)
        int buildings = AddBuildings(map, cfg, Path.Combine(Root, exportRel), new Vector3(off.X, 0, off.Y), noBuild);

        // 4) zemin: ground_s3.json sütun parçaları → Terrain öğeleri (yolların biraz altında)
        int ground = AddGround(map, cfg, Path.Combine(Root, "data", "processed", "ground_s3.json"), new Vector3(off.X, 0, off.Y));

        var outDir = cfg.GetProperty("output_map_dir").GetString();
        var name = cfg.GetProperty("output_map_name").GetString();
        if (name == "saklaz" || name == "europe") throw new InvalidOperationException("Korumalı ad.");
        map.Save(outDir, name, true);
        Console.WriteLine($"Prefab yerleşimi: yaw düzeltmeli {prefabFixed}, en kötü düğüm sapması {worstPrefabDev:F2} m; düzeltmeler: " + string.Join(", ", prefabYawFix.Where(kv => kv.Value != 0).Select(kv => $"{kv.Key}={kv.Value}°")));
        Console.WriteLine("kısa atlanan kenarlar (uç bağlantısına göre): " + string.Join(", ", shortSkip.Select(kv => $"{kv.Key}={kv.Value}")));
        Console.WriteLine("Prefab dağılımı: " + string.Join(", ", byToken.Select(kv => $"{kv.Key}={kv.Value}")));
        Console.WriteLine($"Kaydedildi: {name}.mbd  kavşak={placed} (reddedilen {rejected})  yol={roads} segment={segs} bağlantı={connected} atlanan={skipped} (hata {failed}, origin'de ters kurulan {reversedAtOrigin}, origin'e bağlanamayan {originUnattached}) bina={buildings} zemin={ground} depo={depots}");
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
            // çizim yükü (r_param_packet taşması): ayna/su yansıması kapalı, görüş mesafesi kısa
            if (b.TryGetProperty("view_distance", out var vd)) m.ViewDistance = (ushort)vd.GetInt32();
            m.MirrorReflection = false;
            m.WaterReflection = false;
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
        // ana caddeden uzak binalar: "<tür>_far" listesi (az parçalı mid modeller; çizim bütçesi)
        bool near = bl.TryGetProperty("near_main", out var nm) && nm.GetBoolean();
        if (!near && b.TryGetProperty(key + "_far", out _)) key += "_far";
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
