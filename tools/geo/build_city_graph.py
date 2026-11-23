"""SAKLAZ Türkiye Map - kavşaklı şehir ağı (map_graph_s<scale>.json) üretir.

Kullanım:
    .venv\\Scripts\\python.exe -I tools\\geo\\build_city_graph.py [--scale 3]

build_city_export.py'den farkı: yollar önce GERÇEK OSM kesişim noktalarından bölünür, sonra her parça
ayrı sadeleştirilir; böylece kavşak noktaları korunur. Çıktı:
  edges     : kavşaktan kavşağa yol parçaları (oyun koordinatı), uçlarında düğüm kimliği
  junctions : prefab adayları (yalnızca şehir yolları, 3-4 kol, kollar yeterince uzun, birbirinden uzak)
              her kol için kenar kimliği, hangi uç ve çıkış yönü (birim vektör)
Prefab seçimi/döndürme tools/mapgen (C#) tarafında, .ppd düğümlerine göre yapılır.
Veri © OpenStreetMap katkıda bulunanlar, ODbL 1.0.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, box
from shapely.ops import unary_union

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
CFG = json.loads((ROOT / "config" / "aoi.json").read_text(encoding="utf-8"))
T = Transformer.from_crs("EPSG:4326", "EPSG:32635", always_xy=True)
E0, N0 = 705139.33, 4519475.38  # Gebze OSM düğümü 26505108

ROADMAP = {
    "motorway": ("hw3_divided", 1), "trunk": ("hw3_divided", 2), "primary": ("r2_divided", 3),
    "motorway_link": ("ramp_1lane", 4), "trunk_link": ("ramp_1lane", 4), "primary_link": ("ramp_1lane", 4),
    "secondary": ("r1_city", 5), "secondary_link": ("r1_city", 5), "tertiary": ("r1_city", 6),
    "tertiary_link": ("r1_city", 6), "unclassified": ("r1_city_narrow", 7), "residential": ("r1_city_narrow", 8),
    "living_street": ("r1_city_narrow", 8), "road": ("r1_city_narrow", 8), "service": ("service", 9),
}
CITY = {"r1_city", "r1_city_narrow"}
MAIN_HW = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary",
           "secondary_link", "tertiary", "tertiary_link"}


def load_province():
    """Kocaeli il sınırı (12 ilçe birleşimi), UTM; yoksa None (yalnız çekirdek)."""
    f = RAW / "kocaeli" / "districts.json"
    if not f.exists():
        return None
    from shapely.ops import polygonize
    polys = []
    for el in json.loads(f.read_text(encoding="utf-8"))["elements"]:
        lines = [LineString([T.transform(q["lon"], q["lat"]) for q in m["geometry"]])
                 for m in el.get("members", []) if m.get("role") == "outer" and "geometry" in m]
        polys += list(polygonize(unary_union(lines)))
    return unary_union(polys).buffer(30).simplify(30)
R2 = {"r2_divided"}
# kavşak prefabı sınıfı; şehir içi rampalar (bağlantı yolları) r1 sayılır: aksi halde rampa kesişimleri prefabsız
# kalıp ağ kopuyordu (yeni profilde "No valid offers found for player's HQ city" → oyun kapanıyordu, 2026-11-22)
cls = lambda t: "r2" if t in R2 else ("r1" if t in CITY or t == "ramp_1lane" else None)
# izin verilen (r1 sayısı, r2 sayısı) desenleri -> prefab var
PATTERNS = {(3, 0), (2, 1), (1, 2), (0, 3), (4, 0), (0, 4), (2, 2)}


def prefab_angle_error(dirs, cl, lens=None):
    """Kavşak prefabına (T: karşılıklı iki kol + dik gövde; X: dört dik kol; prefabinfo ile doğrulandı) en iyi
    döndürmede kolların en büyük açı hatası (derece). C# aynı ölçütle (max_angle_error_deg) reddediyordu; reddedilen
    düğümler sonraki derlemede dışlanıyordu (junction_excluded.json). Artık Python'da önceden hesaplanır."""
    ang = [math.degrees(math.atan2(d[1], d[0])) for d in dirs]
    n = len(ang)
    shapes = []
    if n == 4:
        perms = [p for p in __import__("itertools").permutations(range(4)) if p[0] == 0]
        if (cl.count("r1"), cl.count("r2")) == (2, 2):  # r2 × r1: karşılıklı kollar aynı sınıf
            perms = [p for p in perms if cl[p[0]] == cl[p[2]] and cl[p[1]] == cl[p[3]]]
        shapes = [("x", [0, 90, 180, 270], perms)]
    else:
        perms = []
        for st in range(3):
            if (cl.count("r1"), cl.count("r2")) in ((2, 1), (1, 2)):
                if cl.count(cl[st]) != 1:
                    continue  # gövde azınlık sınıfı olmalı
            th = [i for i in range(3) if i != st]
            perms.append(tuple(th + [st]))
        shapes = [("t", [0, 180, 90], perms)]  # iki geçiş + gövde
        if cl.count("r1") == 3:  # Y (ger_r1_x_r1_y_narrow[_mirrored]): dal 60°, dal kolu 25,4 m → kol ≥ 34 m
            yp = [pm for pm in perms if lens is None or lens[pm[2]] >= 34]
            shapes += [("y", [0, 180, 60], yp), ("y", [0, 180, 120], yp)]
    best, bshape = 1e9, None
    for shape, slots, pms in shapes:
        for pm in pms:  # pm[k] = slot k'ya giden kol
            res = [(ang[pm[k]] - slots[k]) for k in range(n)]
            sx = sum(math.cos(math.radians(r)) for r in res)
            sz = sum(math.sin(math.radians(r)) for r in res)
            rot = math.degrees(math.atan2(sz, sx))
            err = max(abs((r - rot + 180) % 360 - 180) for r in res)
            if err < best - (8 if shape == "y" else 0):  # Y yalnız belirgin biçimde daha iyiyse
                best, bshape = min(err, best), shape
    return (best, bshape) if lens is not None else best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=CFG["game"]["city_scale_divisor"])
    ap.add_argument("--simplify-m", type=float, default=10.0)
    ap.add_argument("--min-seg", type=float, default=8.0)
    ap.add_argument("--exclude", nargs="*", default=["service", "living_street"])
    ap.add_argument("--prefab-radius", type=float, default=18.0, help="prefab merkez-düğüm mesafesi (oyun m)")
    ap.add_argument("--min-arm", type=float, default=24.0, help="kol başına en az kenar uzunluğu (oyun m)")
    ap.add_argument("--min-junction-gap", type=float, default=55.0)
    ap.add_argument("--min-hw-gap", type=float, default=50.0, help="otoyol çıkış/katılma prefabları arası en az (oyun m)")
    ap.add_argument("--hw-prefab-len", type=float, default=40.0, help="otoyol çıkış/katılma prefab uzunluğu (oyun m)")
    ap.add_argument("--drop-deadend-len", type=float, default=90.0, help="bu uzunluktan kısa çıkmaz ara sokakları at (oyun m; 0=kapalı)")
    ap.add_argument("--no-collapse", action="store_true", help="bölünmüş caddeleri tek hatta indirgeme")
    ap.add_argument("--core-only", action="store_true", help="yalnız Gebze/Darıca/Çayırova/Dilovası çekirdeği")
    ap.add_argument("--cluster-len", type=float, default=22.0, help="bu uzunluktan kısa kesişim-kesişim parçası daraltılır (oyun m)")
    ap.add_argument("--pick-len", type=float, default=0.0, help="prefabı engelleyen ana yol kolu bu uzunluktan kısaysa kaldırılır")
    ap.add_argument("--ramp-reach", type=float, default=260.0, help="rampa-şehir bağlantısı en uzun (oyun m; 0=kapalı)")
    ap.add_argument("--ramp-min-comp", type=float, default=15000.0, help="rampa yalnız bu uzunluktan büyük şehir ağına")
    ap.add_argument("--max-angle", type=float, default=65.0, help="kavşak prefabı kol açı hatası üst sınırı (derece; C# mapping 70)")
    ap.add_argument("--connect-iters", type=int, default=12, help="bağlanamayan kesişimlerde sokak kaldırma turu")
    ap.add_argument("--tertiary-radius", type=float, default=3000.0, help="il geneli tertiary: merkeze en çok (gerçek m)")
    ap.add_argument("--no-villages", dest="villages", action="store_false", help="merkezden uzak köy yollarını alma")
    ap.add_argument("--street-radius", type=float, default=800.0, help="il geneli sokaklar: merkeze en çok (gerçek m)")
    a = ap.parse_args()
    S = a.scale
    s, w, n, e = CFG["core_bbox_swne"]
    core = box(*T.transform(w, s), *T.transform(e, n))

    # 1) yolları yükle (UTM), kullanım sayısı
    #    Çekirdek (core_bbox): tüm şehir yolları. İl geneli (data/raw/kocaeli): ana yollar (motorway..tertiary)
    #    ve ilçe merkezlerindeki sokaklar; il sınırı (12 ilçe) ∪ çekirdek kutusuna kırpılır.
    prov = None if a.core_only else load_province()
    region_prov = core if prov is None else unary_union([prov, core])
    ways, seen_ids = [], set()

    def add_way(wy, reg, rural=False):
        t = wy.get("tags", {})
        hw = t.get("highway")
        if hw not in ROADMAP or hw in a.exclude or wy["id"] in seen_ids:
            return
        if hw == "service" and t.get("service") not in (None, "", "alley"):
            return
        pts = [T.transform(p["lon"], p["lat"]) for p in wy["geometry"]]
        if not LineString(pts).intersects(core if reg == "core" else region_prov):
            return
        seen_ids.add(wy["id"])
        ways.append((dict(wy, _reg=reg, _rural=rural), t, hw, [(round(x, 2), round(y, 2)) for x, y in pts]))

    for wy in json.loads((RAW / "roads.json").read_text(encoding="utf-8"))["elements"]:
        hw = wy.get("tags", {}).get("highway")
        add_way(wy, "prov" if prov is not None and hw in MAIN_HW else "core")
    if prov is not None:
        n0 = len(ways)
        # Editör "Parameter packet batch system overflow" sınırı tüm harita için geçerli (27 bin segment çöktü,
        # ~14 bin sorunsuz): il genelinde köy yolları (tertiary) yalnız ilçe merkezlerinin yakınında.
        from shapely.geometry import Point as _P
        cen = json.loads((RAW / "kocaeli" / "centers.json").read_text(encoding="utf-8"))
        cpts = [_P(*T.transform(lo, la)) for la, lo in cen.values()]
        skipped = 0
        for f in ("roads.json", "streets.json"):
            for wy in json.loads((RAW / "kocaeli" / f).read_text(encoding="utf-8"))["elements"]:
                hw = wy.get("tags", {}).get("highway", "")
                if f == "streets.json" and wy["id"] not in seen_ids:
                    ln = LineString([T.transform(q["lon"], q["lat"]) for q in wy["geometry"]])
                    if min(ln.distance(c) for c in cpts) > a.street_radius:
                        skipped += 1
                        continue
                rural = False
                if hw.startswith("tertiary") and wy["id"] not in seen_ids:
                    ln = LineString([T.transform(q["lon"], q["lat"]) for q in wy["geometry"]])
                    if min(ln.distance(c) for c in cpts) > a.tertiary_radius:
                        if not a.villages:
                            skipped += 1
                            continue
                        rural = True  # köy yolu: merkezden uzak, seyrek düğümle (editör bütçesi)
                add_way(wy, "prov", rural)
        print(f"il geneli: merkezlerden uzak köy yolu atlandı: {skipped}")
        print(f"il geneli yol: +{len(ways) - n0} (çekirdek {n0})")
    if not a.no_collapse:  # bölünmüş şehir caddeleri → tek çift yönlü orta hat (collapse_dual.py)
        import collapse_dual
        ways, cst = collapse_dual.collapse(ways, ROADMAP)
        print(f"bölünmüş cadde indirgeme: {cst}")
    use = Counter()
    for _, _, _, pts in ways:
        for i, p in enumerate(pts):
            use[p] += 2 if i in (0, len(pts) - 1) else 1  # uçlar her zaman bölme noktası

    # 2) kesişimlerden böl, çekirdek alana kırp, sadeleştir
    g = lambda x, y: (round((x - E0) / S, 3), round(-(y - N0) / S, 3))
    edges, node_id, nodes = [], {}, []
    from shapely.prepared import prep
    region_prep = prep(region_prov)

    def nid(p):
        if p not in node_id:
            node_id[p] = len(nodes)
            nodes.append(p)
        return node_id[p]

    for wy, t, hw, pts in ways:
        cut = [0] + [i for i in range(1, len(pts) - 1) if use[pts[i]] >= 2] + [len(pts) - 1]
        kind, prio = ROADMAP[hw]
        for i0, i1 in zip(cut, cut[1:]):
            seg = pts[i0:i1 + 1]
            if len(seg) < 2:
                continue
            ln = LineString(seg)
            reg = core if wy.get("_reg") == "core" else region_prov
            parts = [seg]
            if not (reg is core and core.contains(ln)) and not (reg is not core and region_prep.contains(ln)):
                if not ln.intersects(reg):
                    continue
                inter = ln.intersection(reg)
                geoms = [inter] if inter.geom_type == "LineString" else                     [x for x in getattr(inter, "geoms", []) if x.geom_type == "LineString"]
                parts = [[(round(x, 2), round(y, 2)) for x, y in gg.coords] for gg in geoms if gg.length >= 6]
            for seg in parts:
                outer = not core.contains(LineString(seg).interpolate(0.5, normalized=True))
                # il geneli: kırsal yollar daha seyrek düğümle (ETS2 yolu düğümler arasında eğri çizer); bütçe
                if wy.get("_rural"):
                    tol, mseg = a.simplify_m * 15, a.min_seg * 25
                elif not outer and hw in ("residential", "unclassified", "road"):
                    tol, mseg = a.simplify_m * 1.4, a.min_seg * 1.6  # ara sokak: bütçe
                elif not outer:
                    tol, mseg = a.simplify_m, a.min_seg
                elif hw.startswith(("tertiary", "secondary")):
                    tol, mseg = a.simplify_m * 8, a.min_seg * 7
                elif hw in ("residential", "unclassified"):
                    tol, mseg = a.simplify_m * 4, a.min_seg * 3
                else:
                    tol, mseg = a.simplify_m * 5, a.min_seg * 5
                simp = list(LineString(seg).simplify(tol).coords)
                gpts = [g(x, y) for x, y in simp]
                out = [gpts[0]]
                for c in gpts[1:-1]:
                    if math.dist(out[-1], c) >= mseg and math.dist(c, gpts[-1]) >= mseg:
                        out.append(c)
                out.append(gpts[-1])
                L = sum(math.dist(p, q) for p, q in zip(out, out[1:]))
                if L < 2.0:
                    continue
                if kind == "hw3_divided" and t.get("oneway") in ("yes", "1"):
                    kind = "hw3_oneway"  # OSM'de her yön ayrı çizili: tek yönlü otoyol şeridi
                edges.append({"id": len(edges), "osm": wy["id"], "hw": hw, "type": kind, "prio": prio,
                              "name": t.get("name"), "oneway": t.get("oneway") in ("yes", "1", "-1"),
                              "reverse": t.get("oneway") == "-1", "a": nid(seg[0]), "b": nid(seg[-1]),
                              "len": round(L, 1), "pts": out, "outer": outer,
                              "rural": bool(wy.get("_rural"))})

    # 2b) Çok kısa kenarları (< 4 oyun m) daralt: iki ucu tek düğüm olur. C# 3 m'den kısa yolu kuramıyor
    #     ve atlıyordu → ağda boşluk (çoğu bölünmüş cadde indirgemesinin yakalama artığı).
    par = {}

    def root(n):
        while par.get(n, n) != n:
            n = par[n]
        return n

    short = 0
    for ed in edges:
        if ed["len"] < 4.0:
            ra, rb = root(ed["a"]), root(ed["b"])
            if ra != rb:
                par[rb] = ra
            short += 1
    if short:
        pos = {}
        for ed in edges:
            for end, p in (("a", ed["pts"][0]), ("b", ed["pts"][-1])):
                pos.setdefault(ed[end], p)
        keep = []
        for ed in edges:
            if ed["len"] < 4.0:
                continue
            ed["a"], ed["b"] = root(ed["a"]), root(ed["b"])
            ed["pts"][0], ed["pts"][-1] = pos[ed["a"]], pos[ed["b"]]
            if ed["a"] == ed["b"] and ed["len"] < 30:
                continue
            ed["id"] = len(keep)
            keep.append(ed)
        print(f"çok kısa kenar daraltıldı: {short} (kenar {len(edges)} -> {len(keep)})")
        edges = keep

    # 2c) Kesişim kümeleme: iki kesişimi (derece ≥ 3) birbirine bağlayan kısa parça (< cluster_len) daraltılır;
    #     iki yakın T tek X olur ve kavşak prefabı (kol 18 m) sığar. Aksi halde ikisi de prefabsız kalıyor,
    #     ana yollar kopuyordu (yeni profilde HQ şehirleri ve GPS, 2026-11-22). Tur başına her düğüm bir kez.
    for _ in range(6):
        deg = Counter()
        for ed in edges:
            deg[ed["a"]] += 1
            deg[ed["b"]] += 1
        pos = {}
        for ed in edges:
            pos.setdefault(ed["a"], tuple(ed["pts"][0]))
            pos.setdefault(ed["b"], tuple(ed["pts"][-1]))
        merged_into, touched = {}, set()
        for ed in sorted(edges, key=lambda e: e["len"]):
            if ed["len"] >= a.cluster_len or ed["a"] == ed["b"]:
                continue
            if deg[ed["a"]] < 3 or deg[ed["b"]] < 3 or ed["a"] in touched or ed["b"] in touched:
                continue
            if ed["type"] not in CITY and ed["type"] not in R2 and ed["type"] != "service":
                continue  # otoyol şeritleri ve rampalar korunur (tek yönlü şehir yolu kısa parçaları daraltılır:
                #           "kısa kol" kesişimlerinin ~%70'i 18 m'den kısa tek yönlü parçaydı, 2026-11-23)
            if deg[ed["a"]] + deg[ed["b"]] - 2 > 4:
                continue  # 5+ kollu düğüm prefab alamaz
            pa, pb = pos[ed["a"]], pos[ed["b"]]
            pos[ed["a"]] = (round((pa[0] + pb[0]) / 2, 3), round((pa[1] + pb[1]) / 2, 3))
            merged_into[ed["b"]] = ed["a"]
            touched |= {ed["a"], ed["b"]}
        if not merged_into:
            break
        keep = []
        for ed in edges:
            na, nb = merged_into.get(ed["a"], ed["a"]), merged_into.get(ed["b"], ed["b"])
            if na == nb:
                continue  # daraltılan parça
            ed["a"], ed["b"] = na, nb
            ed["pts"][0], ed["pts"][-1] = list(pos[na]), list(pos[nb])
            ed["len"] = round(sum(math.dist(p, q) for p, q in zip(ed["pts"], ed["pts"][1:])), 1)
            ed["id"] = len(keep)
            keep.append(ed)
        print(f"kesişim kümeleme: {len(merged_into)} kısa parça daraltıldı")
        edges = keep

    # C# üreticinin prefab açısı tutmadığı için reddettiği kavşak düğümleri (junction_rejects.json) birikimli
    # olarak dışlanır; bu düğümler 4c'de düz geçiş olarak bağlanır.
    excl_path = ROOT / "data" / "processed" / "junction_excluded.json"
    rej_path = ROOT / "data" / "processed" / "junction_rejects.json"
    excluded = set(json.loads(excl_path.read_text())) if excl_path.exists() else set()
    if rej_path.exists():
        excluded |= set(json.loads(rej_path.read_text()))
        excl_path.write_text(json.dumps(sorted(excluded)))
        rej_path.unlink()
    # Bağlantı döngüsü: ETS2'de kesişim ancak kavşak prefabıyla bağlanır. Prefab alamayan kesişimlerde en düşük
    # öncelikli ara sokak kolu (servis > konut > adsız) kaldırılır; ana yollara dokunulmaz. Kalan her kesişim ya
    # prefablı ya da düz geçiş olur → yol ağı bağlı (yeni profilde "No valid offers ... HQ city" çökmesi, 2026-11-22).
    removed_total, main_rm = 0, [0]
    for _it in range(a.connect_iters + 1):
        # kısa çıkmaz ara sokakları önce buda (kesişimi gereksiz yere "kısa kol" yapıyorlar)
        while True:
            deg = Counter()
            for ed in edges:
                deg[ed["a"]] += 1
                deg[ed["b"]] += 1
            drop = {ed["id"] for ed in edges if ed["prio"] >= 7 and ed["len"] < a.drop_deadend_len
                    and (deg[ed["a"]] == 1) != (deg[ed["b"]] == 1)}
            if not drop:
                break
            edges = [ed for ed in edges if ed["id"] not in drop]
            for i, ed in enumerate(edges):
                ed["id"] = i
            removed_total += len(drop)
        # 3) düğüm dereceleri ve kavşak adayları
        inc = defaultdict(list)
        for ed in edges:
            inc[ed["a"]].append((ed, "a"))
            inc[ed["b"]].append((ed, "b"))

        def arm_dir(ed, end):
            pts = ed["pts"] if end == "a" else ed["pts"][::-1]
            o = pts[0]
            acc = 0.0
            tgt = pts[-1]
            for p, q in zip(pts, pts[1:]):  # ~15 m ilerideki nokta
                acc += math.dist(p, q)
                if acc >= 15:
                    tgt = q
                    break
            dx, dz = tgt[0] - o[0], tgt[1] - o[1]
            L = math.hypot(dx, dz) or 1
            return [round(dx / L, 4), round(dz / L, 4)]

        # Kol zinciri: kavşak düğümünden çıkan kenar, 2 dereceli ve aynı görünüm grubundaki (r1/r2) düğümlerden
        # geçerek devam eder; bu düğümler 4c'de tek yola birleştirildiği için kolun gerçek uzunluğu zincirdir.
        # (Önceden ilk OSM parçasının uzunluğu ölçülüyordu: ~13 bin aday "kısa kol" diye eleniyordu.)
        def arm_chain(ed, end, k):
            L, chain, cur, cend = 0.0, [ed["id"]], ed, end
            pts = list(ed["pts"] if end == "a" else ed["pts"][::-1])
            while True:
                L += cur["len"]
                far = cur["b"] if cend == "a" else cur["a"]
                nxt = inc.get(far, [])
                if len(nxt) != 2 or far == k or L >= 200:
                    STOP[0] = "uç" if len(nxt) == 1 else ("kesişim" if len(nxt) > 2 else "uzun/halka")
                    return L, chain, pts
                (e2, en2) = nxt[0] if nxt[0][0]["id"] != cur["id"] else nxt[1]
                if e2["id"] == cur["id"] or e2["id"] in chain or cls(e2["type"]) != cls(cur["type"]) \
                        or cls(e2["type"]) is None or e2["oneway"] != cur["oneway"]:
                    STOP[0] = "tür değişimi " + cur["type"] + ">" + e2["type"] + ("" if e2["oneway"] == cur["oneway"] else " (tek yön)")
                    return L, chain, pts
                chain.append(e2["id"])
                pts += (e2["pts"] if en2 == "a" else e2["pts"][::-1])[1:]
                cur, cend = e2, en2

        def chain_dir(pts):
            o, acc, tgt = pts[0], 0.0, pts[-1]
            for p, q in zip(pts, pts[1:]):
                acc += math.dist(p, q)
                if acc >= 15:
                    tgt = q
                    break
            dx, dz = tgt[0] - o[0], tgt[1] - o[1]
            L = math.hypot(dx, dz) or 1
            return [round(dx / L, 4), round(dz / L, 4)]

        cand = []
        STOP, SHORT, SHORT2, PICK = ["?"], Counter(), Counter(), {}
        JWHY = Counter()
        blocked = set()
        for k, lst in inc.items():
            if len(lst) < 3:
                continue
            blocked.add(k)  # seçilirse aşağıda çıkarılır
            # prefab alamayan kesişimde kaldırılacak ana yol kolu önerisi (en önemsiz, en kısa): prefabsız düğümde o kol
            # zaten kopuk kalıyordu; kaldırınca kalan kollar prefabla bağlanır (2026-11-23)
            low = sorted((ed for ed, _ in lst if ed["type"] in CITY or ed["type"] in R2 or ed["type"] == "service"),
                         key=lambda e: (-e["prio"], e["len"]))
            if len(lst) > 4:
                JWHY["5+ kol"] += 1
                if low:
                    PICK[k] = low[0]["id"]
                continue
            if k in excluded:
                JWHY["reddedilmiş"] += 1
                if low and len(lst) == 4:
                    PICK[k] = low[0]["id"]
                continue
            cl = [cls(ed["type"]) for ed, _ in lst]
            if len(lst) == 3 and all(ed["type"] == "ramp_1lane" and ed["oneway"] for ed, _ in lst):
                JWHY["rampa çatalı (3c)"] += 1
                continue  # tek yönlü rampa ayrılma/birleşmesi: Y prefabı (3c)
            if None in cl or (cl.count("r1"), cl.count("r2")) not in PATTERNS:
                JWHY["desen " + "+".join(sorted(LOOK_GROUP.get(ed["type"], ed["type"]) for ed, _ in lst))] += 1
                continue
            if any(ed["a"] == ed["b"] for ed, _ in lst):
                JWHY["halka"] += 1
                continue
            chains, stops = [], []
            for ed, end in lst:
                STOP[0] = "?"
                chains.append(arm_chain(ed, end, k))
                stops.append(STOP[0])
            if min(c[0] for c in chains) < a.min_arm:
                JWHY["kısa kol"] += 1
                i_ = min(range(len(chains)), key=lambda i: chains[i][0])
                e_ = lst[i_][0]
                if e_["type"] in CITY or e_["type"] in R2 or e_["type"] == "service":
                    PICK[k] = e_["id"]
                SHORT[stops[i_] + (" ana" if all(ed["prio"] < 7 for ed, _ in lst) else "")] += 1
                if stops[i_] == "kesişim":
                    e_ = lst[i_][0]
                    SHORT2[(int(chains[i_][0] // 6) * 6, e_["oneway"], len(chains[i_][1]))] += 1
                continue
            ids = [x for c in chains for x in c[1]]
            if len(ids) != len(set(ids)):  # iki kol aynı zincir (halka)
                JWHY["kol halkası"] += 1
                continue
            dirs = [chain_dir(c[2]) for c in chains]
            perr, pshape = prefab_angle_error(dirs, cl, [c_[0] for c_ in chains])
            if perr > a.max_angle:
                JWHY["açı tutmuyor"] += 1
                if low and len(lst) == 4:
                    PICK[k] = low[0]["id"]
                continue
            close = [(i, j) for i in range(len(dirs)) for j in range(i) if dirs[i][0] * dirs[j][0] + dirs[i][1] * dirs[j][1] > 0.9]
            if close:
                JWHY["dar açı"] += 1
                i, j = close[0]
                pk = [lst[x][0] for x in (i, j) if lst[x][0]["type"] in CITY or lst[x][0]["type"] in R2]
                if pk:
                    PICK[k] = max(pk, key=lambda e: (e["prio"], -e["len"]))["id"]
                continue  # iki kol neredeyse üst üste (prefab açısı tutmaz)
            c = edges[lst[0][0]["id"]]["pts"][0] if lst[0][1] == "a" else lst[0][0]["pts"][-1]
            cand.append((min(c_[0] for c_ in chains), k, c, lst, chains, dirs, pshape))
        cand.sort(key=lambda x: -x[0])  # en uzun kollu (en rahat) kavşaklar önce
        chosen, grid = [], defaultdict(list)
        G = a.min_junction_gap
        used_edges = Counter()
        for _, k, c, lst, chains, dirs, pshape in cand:
            key = (int(c[0] // G), int(c[1] // G))
            if any(math.dist(c, q) < G for dx in (-1, 0, 1) for dz in (-1, 0, 1) for q in grid[(key[0] + dx, key[1] + dz)]):
                JWHY["başka kavşağa yakın"] += 1
                continue
            # aynı zincirin iki ucunda prefab: zincir 2*yarıçap + pay kadar uzun olmalı
            rad = 23.25 if any(cls(ed["type"]) == "r2" for ed, _ in lst) else a.prefab_radius
            if any(used_edges[ch[1][0]] or any(used_edges[x] for x in ch[1]) for ch in chains
                   if ch[0] < 2 * rad + 8):
                continue
            grid[key].append(c)
            for ch in chains:
                for x in ch[1]:
                    used_edges[x] += 1
            blocked.discard(k)
            chosen.append({"id": len(chosen), "node": k, "x": c[0], "z": c[1], "shape": pshape, "arms":
                           [{"edge": ed["id"], "end": end, "cls": cls(ed["type"]), "dir": d}
                            for (ed, end), d in zip(lst, dirs)]})

        if _it == a.connect_iters:
            break
        rm = set()
        for k in blocked:
            minor = [ed for ed, _ in inc[k] if ed["prio"] >= 7 and ed["id"] not in rm]
            if minor:
                rm.add(max(minor, key=lambda e: (e["prio"], -e["len"]))["id"])
            elif k in PICK and _it >= 2 and edges[PICK[k]]["len"] < a.pick_len:
                rm.add(PICK[k])
                main_rm[0] += 1
        print(f"  bağlantı turu {_it + 1}: kavşak {len(chosen)}, prefabsız kesişim {len(blocked)}, kaldırılan sokak {len(rm)}")
        if not rm:
            break
        edges = [ed for ed in edges if ed["id"] not in rm]
        for i, ed in enumerate(edges):
            ed["id"] = i
        removed_total += len(rm)
    print(f"bağlantı için kaldırılan ara sokak parçası: {removed_total} (ana yol kolu {main_rm[0]})")
    print(f"kavşak: {len(chosen)} prefab; prefabsız kesişim nedenleri: {dict(JWHY.most_common(14))}")
    print(f"  kısa kol: neden {dict(SHORT.most_common(12))}")
    print(f"  kısa kol kesişim (uzunluk, tek yön, parça): {sorted(SHORT2.items())}")

    # 3b) Otoyol ayrılma/katılma noktaları (tek yönlü şerit + tek yönlü rampa, sağdan trafik)
    hwj, hgrid = [], defaultdict(list)
    HG = a.min_hw_gap
    why = Counter()
    for k, lst in inc.items():
        if len(lst) != 3 or k in {j["node"] for j in chosen}:
            continue
        hwl = [(ed, end) for ed, end in lst if ed["type"] == "hw3_oneway" and not ed["reverse"]]
        rl = [(ed, end) for ed, end in lst if ed["type"] == "ramp_1lane" and ed["oneway"] and not ed["reverse"]]
        if len(hwl) != 2 or len(rl) != 1 or any(ed["a"] == ed["b"] for ed, _ in lst):
            continue
        hin = [x for x in hwl if x[1] == "b"]
        hout = [x for x in hwl if x[1] == "a"]
        if len(hin) != 1 or len(hout) != 1:
            why["yön (giren/çıkan şerit yok)"] += 1
            continue
        (ein, _), (eout, _), (er, rend) = hin[0], hout[0], rl[0]
        kind = "exit" if rend == "a" else "merge"
        di, do, dr = arm_dir(ein, "b"), arm_dir(eout, "a"), arm_dir(er, rend)
        tx, tz = do[0] - di[0], do[1] - di[1]
        tl = math.hypot(tx, tz)
        if tl < 1e-6:
            continue
        tx, tz = tx / tl, tz / tl
        # rampanın ~30 m ilerideki noktasının şeride göre yanal sapması (sağ = (-tz, tx); +Z güney)
        # (köşe noktası yerine rampa boyunca ara değerlenmiş noktalar: yonca rampası ilk köşede sola dönmüş
        #  görünüp "solda" sayılıyordu, 2026-11-23)
        rp = er["pts"] if rend == "a" else er["pts"][::-1]

        def at_len(L_):
            acc = 0.0
            for p_, q_ in zip(rp, rp[1:]):
                d_ = math.dist(p_, q_)
                if acc + d_ >= L_:
                    t_ = (L_ - acc) / (d_ or 1)
                    return (p_[0] + (q_[0] - p_[0]) * t_, p_[1] + (q_[1] - p_[1]) * t_)
                acc += d_
            return rp[-1]
        lat = 0.0
        for L_ in (8, 14, 20, 30, 45, 60):
            q_ = at_len(L_)
            lat = (q_[0] - rp[0][0]) * (-tz) + (q_[1] - rp[0][1]) * tx
            if abs(lat) > 0.6:
                break
        if lat <= 0.3:  # rampa sağda değil
            why["rampa solda" if lat < -0.3 else "rampa düz"] += 1
            continue
        # prefab (40 m) çıkışta gelen şeridin, katılmada giden şeridin üstüne oturur
        long_e, short_e = (ein, eout) if kind == "exit" else (eout, ein)
        # kenar uzunluğu yerine 2 dereceli düğümlerden geçen şerit zinciri (4c'de tek yola birleşiyor): OSM köprü/
        # tünel bölmeleri yüzünden 137 çıkış "kısa kenar" diye eleniyordu (2026-11-23)
        def hw_chain(ed, end):
            L, cur, cend, seen_ = 0.0, ed, end, {ed["id"]}
            while L < 200:
                L += cur["len"]
                far = cur["a"] if cend == "b" else cur["b"]
                nx = [(e2, en2) for e2, en2 in inc.get(far, []) if e2["id"] != cur["id"]]
                if len(inc.get(far, [])) != 2 or len(nx) != 1 or nx[0][0]["type"] != cur["type"] or nx[0][0]["id"] in seen_:
                    break
                cur, cend = nx[0][0], ("b" if nx[0][1] == "b" else "a")
                seen_.add(cur["id"])
            return L
        if hw_chain(long_e, "b" if long_e is ein else "a") < a.hw_prefab_len + 4 or short_e["len"] < 8 or er["len"] < 20:
            why[f"kısa kenar ({'uzun' if long_e['len'] < a.hw_prefab_len + 10 else 'kısa/rampa'})"] += 1
            continue
        c = ein["pts"][-1]
        key = (int(c[0] // 100), int(c[1] // 100))
        # prefab izdüşümü şerit boyunca: çıkış [-40, 0], katılma [0, +40] (çapa = ayrılma/katılma noktası). Aynı şeritteki
        # prefablar yalnız izdüşümleri çakışırsa çatışır (yonca kavşağında çıkış ardından katılma 20-40 m arayla
        # meşru; eski 50 m çember kuralı bunları eliyordu, 2026-11-23)
        PL = a.hw_prefab_len
        lo, hi = (-PL, 0.0) if kind == "exit" else (0.0, PL)
        clash = False
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for (q, qt, qlo, qhi) in hgrid[(key[0] + dx, key[1] + dz)]:
                    dd = math.dist(c, q)
                    if dd > 2 * PL + 10:
                        continue
                    same = tx * qt[0] + tz * qt[1] > 0.7 and abs((c[0] - q[0]) * qt[1] - (c[1] - q[1]) * qt[0]) < 6
                    if same:
                        sx = (c[0] - q[0]) * qt[0] + (c[1] - q[1]) * qt[1]
                        if max(sx + lo, qlo) < min(sx + hi, qhi) + 4:
                            clash = True
                    elif dd < 12:
                        clash = True
        if clash:
            why["başka prefaba yakın"] += 1
            continue
        hgrid[key].append((c, (tx, tz), lo, hi))
        hwj.append({"id": len(hwj), "node": k, "x": c[0], "z": c[1], "kind": kind,
                    "travel": [round(tx, 4), round(tz, 4)],
                    "arms": [{"edge": ein["id"], "end": "b", "role": "in"},
                             {"edge": eout["id"], "end": "a", "role": "out"},
                             {"edge": er["id"], "end": rend, "role": "ramp"}]})
    print(f"otoyol ayrılma/katılma: {sum(1 for h in hwj if h['kind'] == 'exit')} çıkış, "
          f"{sum(1 for h in hwj if h['kind'] == 'merge')} katılma; elenen: {dict(why)}")

    # 3c) Rampa çatalları: tek yönlü tek şeritli rampanın ikiye ayrılması / iki rampanın birleşmesi. Simetrik Y prefabı
    #     (exit_road_joint_short[_mirrored]_tmpl, 17 m, kollar ±30°; ppdnav ile doğrulandı). Önceden şehir kavşağı
    #     sayılıyor, rampa otoyol prefabına bağlıysa atılıyordu: otoyolun iki yönü ve ilçeler ayrı ağlarda kalıyordu
    #     ("ramp orta + ramp uç" kopuklukları, 2026-11-23).
    forks, fwhy = [], Counter()
    used_nodes = {j["node"] for j in chosen} | {h["node"] for h in hwj}
    for k, lst in inc.items():
        if len(lst) != 3 or k in used_nodes:
            continue
        if not all(ed["type"] == "ramp_1lane" and ed["oneway"] and not ed["reverse"] for ed, _ in lst):
            continue
        if any(ed["a"] == ed["b"] for ed, _ in lst):
            continue
        ins = [(ed, end) for ed, end in lst if end == "b"]
        outs = [(ed, end) for ed, end in lst if end == "a"]
        if (len(ins), len(outs)) not in ((1, 2), (2, 1)):
            fwhy["yön"] += 1
            continue
        kind = "split" if len(ins) == 1 else "join"
        if any(ed["len"] < 15 for ed, _ in lst):
            fwhy["kısa kol"] += 1
            continue
        if kind == "split":
            d0 = arm_dir(ins[0][0], "b")
            tx, tz = -d0[0], -d0[1]
            br = [(ed, end, arm_dir(ed, end)) for ed, end in outs]
            ang = [math.degrees(math.acos(max(-1, min(1, d[0] * tx + d[1] * tz)))) for _, _, d in br]
        else:
            tx, tz = arm_dir(outs[0][0], "a")
            br = [(ed, end, arm_dir(ed, end)) for ed, end in ins]
            ang = [math.degrees(math.acos(max(-1, min(1, -(d[0] * tx + d[1] * tz))))) for _, _, d in br]
        if max(ang) > 75:
            fwhy["açı"] += 1
            continue
        # sağ = (-tz, tx); ayrılmada dal yönü, birleşmede geliş yönünün tersi (akış yönü) yanal sapması
        sgn = 1 if kind == "split" else -1
        lat = [sgn * (d[0] * (-tz) + d[1] * tx) for _, _, d in br]
        left, right = (br[0], br[1]) if lat[0] < lat[1] else (br[1], br[0])
        c = lst[0][0]["pts"][0] if lst[0][1] == "a" else lst[0][0]["pts"][-1]
        trunk = ins[0] if kind == "split" else outs[0]
        forks.append({"id": len(forks), "node": k, "x": c[0], "z": c[1], "kind": kind,
                      "travel": [round(tx, 4), round(tz, 4)],
                      "arms": [{"edge": trunk[0]["id"], "end": trunk[1], "role": "trunk"},
                               {"edge": left[0]["id"], "end": left[1], "role": "left"},
                               {"edge": right[0]["id"], "end": right[1], "role": "right"}]})
    print(f"rampa çatalı: {sum(1 for f_ in forks if f_['kind'] == 'split')} ayrılma, "
          f"{sum(1 for f_ in forks if f_['kind'] == 'join')} birleşme; elenen: {dict(fwhy)}")

    # 4) Prefab konmayan kesişimlerde parçaları aynı OSM yolu boyunca yeniden birleştir
    #    (editör öğe sayısı sınırı: ~17 bin öğe üstünde render taşması).
    jnodes = {j["node"] for j in chosen} | {h["node"] for h in hwj} | {f_["node"] for f_ in forks}
    remap, merged = {}, []
    cur = None
    for ed in edges:  # aynı yolun parçaları ardışık üretildi
        if cur and cur["osm"] == ed["osm"] and cur["b"] == ed["a"] and ed["a"] not in jnodes and cur["type"] == ed["type"]:
            cur["pts"].extend(ed["pts"][1:])
            cur["b"] = ed["b"]
            cur["len"] = round(cur["len"] + ed["len"], 1)
            remap[(ed["id"], "b")] = cur
            remap[(ed["id"], "a")] = cur
            cur["_parts"].append(ed["id"])
        else:
            cur = dict(ed, pts=list(ed["pts"]), _parts=[ed["id"]])
            merged.append(cur)
            remap[(ed["id"], "a")] = cur
            remap[(ed["id"], "b")] = cur
    for i, m in enumerate(merged):
        m["id"] = i
    for j in chosen + hwj + forks:
        for arm in j["arms"]:
            m = remap[(arm["edge"], arm["end"])]
            arm["edge"] = m["id"]
            # birleşik kenarın hangi ucu bu kavşakta
            arm["end"] = "a" if m["a"] == j["node"] else "b"
    for m in merged:
        m.pop("_parts", None)
        if len(m["pts"]) > 2:  # birleşik kenarı yeniden sadeleştir (uçlar korunur)
            ls = LineString(m["pts"]).simplify(a.simplify_m / S)
            ps = [tuple(round(v, 3) for v in c) for c in ls.coords]
            o = [ps[0]]
            for c in ps[1:-1]:
                if math.dist(o[-1], c) >= a.min_seg and math.dist(c, ps[-1]) >= a.min_seg:
                    o.append(c)
            o.append(ps[-1])
            m["pts"] = [list(c) for c in o]
    edges = merged

    # 4b) Kısa çıkmaz sokakları at (editör öğe/segment sınırı). Kavşak kolu olan kenarlar korunur.
    if a.drop_deadend_len > 0:
        deg = Counter()
        for ed in edges:
            deg[ed["a"]] += 1
            deg[ed["b"]] += 1
        armed = {arm["edge"] for j in chosen + hwj + forks for arm in j["arms"]}
        keep = [ed for ed in edges if not (ed["type"] in ("r1_city_narrow", "service") and ed["id"] not in armed
                                            and (deg[ed["a"]] == 1 or deg[ed["b"]] == 1) and ed["len"] < a.drop_deadend_len)]
        idmap = {ed["id"]: i for i, ed in enumerate(keep)}
        for j in chosen + hwj + forks:
            for arm in j["arms"]:
                arm["edge"] = idmap[arm["edge"]]
        for i, ed in enumerate(keep):
            ed["id"] = i
        print(f"kısa çıkmaz sokak atıldı: {len(edges) - len(keep)}")
        edges = keep

    # 4c) Prefabsız düğümlerde yol sürekliliği: ETS2'de aynı noktada biten iki yol öğesi BAĞLI DEĞİLDİR
    #     (GPS, yapay zekâ trafiği ve iş rotaları kopar). Her prefabsız düğümde en düz/uyumlu kol çiftleri
    #     tek kenarda birleştirilir; 3-4 kollu kesişimde ana yol kesintisiz geçer, kalan kol orada biter.
    jnodes = {j["node"] for j in chosen} | {h["node"] for h in hwj} | {f_["node"] for f_ in forks}
    edges, road_links = link_through(edges, chosen + hwj + forks, jnodes, arm_dir)
    # il geneli kenarlar: birleştirme sonrası ara düğümler (eski kesişimler) yeniden sadeleştirilir (segment bütçesi)
    before = sum(len(e["pts"]) - 1 for e in edges)
    for e in edges:
        if e.get("outer") and len(e["pts"]) > 2:
            tol = 12.0 if e["hw"].startswith(("tertiary", "secondary", "primary", "trunk", "motorway")) else 6.0
            mseg = 40.0 if tol > 10 else 20.0
            if e.get("rural"):
                tol, mseg = 22.0, 150.0
            ps = [tuple(c) for c in LineString(e["pts"]).simplify(tol).coords]
            o = [ps[0]]
            for c in ps[1:-1]:
                if math.dist(o[-1], c) >= mseg and math.dist(c, ps[-1]) >= mseg:
                    o.append(c)
            o.append(ps[-1])
            e["pts"] = [list(c) for c in o]
    print(f"il geneli yeniden sadeleştirme: segment {before} -> {sum(len(e['pts']) - 1 for e in edges)}")

    # 5) Şirket depoları: sanayi alanlarında, düz ve uzun bir şehir yolu parçasının yanına iki düğümlü depo
    #    prefabı. Parça ikiye bölünür; depo düğümleri iki yeni kenar ucuna gelir.
    # Şehir kavşağına bağlanan rampalar: prefab kolu 1+1 şerit, rampa 1 şerit tek yön → "[traffic] Unable to determine
    # output road lane". Otoyol prefabına bağlı olmayan rampa iki yönlü şehir yoluna çevrilir; bağlıysa kavşak atılır.
    hw_edges = {arm["edge"] for h in hwj for arm in h["arms"]}
    E_ = {e["id"]: e for e in edges}
    keep_j, conv, dropj = [], 0, 0
    for j in chosen:
        ramps = [arm["edge"] for arm in j["arms"] if E_[arm["edge"]]["type"] == "ramp_1lane"]
        # otoyol prefabına da bağlı (tek yönlü kalması gereken) rampa: kavşak tutulur, rampa tek yönlü kalır. Prefabın
        # karşı yön şeridi boşta kalır (log: "[traffic] Unable to determine output road lane") ama rampa yönündeki
        # akış ve GPS çalışır; kavşak atılınca kavşak rampası şehre hiç bağlanmıyordu (ilçeler kopuk, 2026-11-23).
        keep_ow = [r for r in ramps if r in hw_edges]
        if keep_ow:
            dropj += 1
        for r in ramps:
            if r in keep_ow:
                continue
            e = E_[r]
            e.update(type="r1_city", oneway=False, reverse=False)
            conv += 1
        keep_j.append(j)
    for i, j in enumerate(keep_j):
        j["id"] = i
    chosen = keep_j
    print(f"şehir kavşağındaki rampa: {conv} iki yönlü yola çevrildi, {dropj} kavşakta otoyol rampası tek yönlü kaldı")
    edges, chosen = force_tees(edges, chosen, hwj + forks, road_links, a)
    edges = force_hw_tees(edges, chosen, hwj, forks, road_links, a)
    road_links[:] = heal_links(edges, chosen + hwj + forks, road_links)
    if add_connectors(edges, chosen + hwj + forks, road_links):
        edges, chosen = force_tees(edges, chosen, hwj + forks, road_links, a)
        edges = force_hw_tees(edges, chosen, hwj, forks, road_links, a)
    meta = {"scale_divisor": S, "origin_osm_node": 26505108, "axes": "+X doğu, +Z güney, Y=0",
            "prefab_radius": a.prefab_radius, "attribution": "(c) OpenStreetMap contributors, ODbL 1.0"}
    dst = ROOT / "data" / "processed" / f"map_graph_s{S:g}.json"
    # 1) otoyol prefab ↔ yol şerit sayısı eşleme (hi/lo prefab + hw2/3/4_oneway); çelişkili otoyol kavşaklarını atar
    dst.write_text(json.dumps({"meta": meta, "edges": edges, "junctions": chosen, "hw_junctions": hwj, "ramp_forks": forks,
                               "road_links": road_links}, ensure_ascii=False), encoding="utf-8")
    import assign_hw_lanes
    assign_hw_lanes.main(str(dst))
    gl = json.loads(dst.read_text(encoding="utf-8"))
    edges, hwj = gl["edges"], gl["hw_junctions"]
    # 2) Oyunun yol ağı: yalnız prefab düğümleri, birleşik yollar ve uç bağlantıları bağlıdır. Depo ve garajlar
    #    SON ağın en büyük bağlı bileşenine konur → her HQ şehrinden diğer şehirlerin depolarına rota (ilk iş) bulunur.
    #    (Aksi halde yeni profilde "No valid offers found for player's HQ city" → oyun kapanıyordu, 2026-11-22.)
    road_links = heal_links(edges, chosen + hwj + forks, road_links)
    # ilçe ağlarının rampa erişimi dönüş bağlantılarından önce (boşta rampa uçlarını önce şehirler alsın)
    sys.path.insert(0, str(ROOT / "tools" / "validation"))
    from directed import largest_scc
    _scc0 = largest_scc({"edges": edges, "junctions": chosen, "hw_junctions": hwj, "ramp_forks": forks,
                         "road_links": road_links})
    if a.ramp_reach > 0 and ramp_city_links(edges, chosen, hwj, forks, road_links, reach_m=a.ramp_reach,
                                             min_comp=a.ramp_min_comp):
        edges, chosen = force_tees(edges, chosen, hwj + forks, road_links, a)
        road_links = heal_links(edges, chosen + hwj + forks, road_links)
    if ramp_access(edges, chosen, hwj, forks, road_links, _scc0, lane_based=True):
        edges, chosen = force_tees(edges, chosen, hwj + forks, road_links, a)
        road_links = heal_links(edges, chosen + hwj + forks, road_links)
    # Dönüş bağlantıları (uturn) boşta rampa uçlarını tüketir; SCC'ye giremeyen ilçelerin (Darıca) erişimi için o
    # ilçelerin alanındaki uçlar önce ilçe erişimine ayrılır. Hangi ilçeler: kopya üzerinde deneme turu.
    import copy
    areas = city_grid(edges, S)

    def _city_at(p):
        for b in areas:
            if b["x0"] <= p[0] <= b["x1"] and b["z0"] <= p[1] <= b["z1"]:
                return b["token"]
    _e, _l = copy.deepcopy(edges), copy.deepcopy(road_links)
    uturn_links(_e, chosen + hwj + forks, _l)
    _s = largest_scc({"edges": _e, "junctions": chosen, "hw_junctions": hwj, "ramp_forks": forks, "road_links": _l})
    have = Counter(_city_at(e["pts"][len(e["pts"]) // 2]) for e in _e if e["id"] in _s and e["type"] in CITY)
    lacking = [t for t in CITY_TOKENS.values() if have[t] < 20]
    print(f"SCC'de yolu az ilçe (deneme): {lacking}")
    skip = [{"x0": b["x0"] - 800, "x1": b["x1"] + 800, "z0": b["z0"] - 800, "z1": b["z1"] + 800}
            for b in areas if b["token"] in lacking]
    uturn_links(edges, chosen + hwj + forks, road_links, skip_boxes=skip)
    if lacking:
        _scc = largest_scc({"edges": edges, "junctions": chosen, "hw_junctions": hwj, "ramp_forks": forks,
                            "road_links": road_links})
        if ramp_access(edges, chosen, hwj, forks, road_links, _scc, min_group=2000.0):
            edges, chosen = force_tees(edges, chosen, hwj + forks, road_links, a)
            road_links = heal_links(edges, chosen + hwj + forks, road_links)
    # Oyun rotayı yönlü arar: depo/garaj yalnız her noktasından her noktasına gidilip dönülebilen en büyük güçlü
    # bağlı ağa konur (yalnız yönsüz bağlı ağda tek yönlü rampa tuzakları vardı, 2026-11-23).
    sys.path.insert(0, str(ROOT / "tools" / "validation"))
    from directed import largest_scc
    fix_city_ramp_arms(edges, chosen, hwj + forks, road_links)
    filter_links(edges, road_links, use_rejects=False)
    main_edges = largest_scc({"edges": edges, "junctions": chosen, "hw_junctions": hwj, "ramp_forks": forks,
                              "road_links": road_links})
    for _ in range(3):  # güçlü bağlı ağın dışında kalan büyük ilçe ağlarını iki yönlü bağlantı yoluyla bağla
        n1 = add_connectors(edges, chosen + hwj + forks, road_links, min_comp=4000.0, targets=main_edges)
        n2 = lane_access(edges, chosen, hwj, forks, road_links, a, main_edges, None)
        n3 = ramp_access(edges, chosen, hwj, forks, road_links, main_edges)
        if not n1 and not n2 and not n3:
            break
        edges, chosen = force_tees(edges, chosen, hwj + forks, road_links, a)
        if n2:  # yeni otoyol prefabları: şerit sayıları yeniden eşlenir (hi/lo)
            dst.write_text(json.dumps({"meta": meta, "edges": edges, "junctions": chosen, "hw_junctions": hwj,
                                       "ramp_forks": forks, "road_links": road_links}, ensure_ascii=False), encoding="utf-8")
            assign_hw_lanes.main(str(dst))
            gl = json.loads(dst.read_text(encoding="utf-8"))
            edges, hwj = gl["edges"], gl["hw_junctions"]
        road_links = heal_links(edges, chosen + hwj + forks, road_links)
        uturn_links(edges, chosen + hwj + forks, road_links)
        fix_city_ramp_arms(edges, chosen, hwj + forks, road_links)
        filter_links(edges, road_links, use_rejects=False)
        main_edges = largest_scc({"edges": edges, "junctions": chosen, "hw_junctions": hwj, "ramp_forks": forks,
                                  "road_links": road_links})
    # Yerleşim için oyundaki gerçek ağ: önceki C# derlemesinin birleştiremediği bağlantılar düşülür (onarımlar ret
    # listesinden bağımsız → her derlemede aynı ağ; C# aynı bağlantıları yine reddeder, yerleşim bunu bilir)
    _real = filter_links(edges, [list(l) for l in road_links], use_rejects=True)
    main_edges = largest_scc({"edges": edges, "junctions": chosen, "hw_junctions": hwj, "ramp_forks": forks,
                              "road_links": _real})
    print(f"ana bağlı ağ: {len(main_edges)}/{len(edges)} kenar, "
          f"%{100 * sum(e['len'] for e in edges if e['id'] in main_edges) / sum(e['len'] for e in edges):.1f} uzunluk")
    depots = place_depots(edges, chosen, S, a, links=road_links, allowed=main_edges)
    cities = assign_cities(depots, edges, S)
    garages = place_garages(edges, chosen, depots, S, links=road_links, allowed=main_edges, cities=cities)
    signs = place_signs(edges, chosen + hwj + forks + depots + garages, cities, S, main_edges)
    out = {"meta": meta, "edges": edges, "junctions": chosen, "hw_junctions": hwj, "ramp_forks": forks, "signs": signs,
           "depots": depots, "garages": garages,
           "cities": cities, "road_links": road_links, "city_areas": city_grid(edges, S)}
    dst.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    deg =Counter(len(v) for v in inc.values())
    summary = {"scale": S, "edges": len(edges), "segments": sum(len(e["pts"]) - 1 for e in edges),
               "graph_nodes": len(inc), "degree_hist": dict(sorted(deg.items())),
               "junction_candidates_city": len(cand), "junctions_chosen": len(chosen),
               "junctions_T": sum(1 for j in chosen if len(j["arms"]) == 3),
               "junctions_X": sum(1 for j in chosen if len(j["arms"]) == 4),
               "depots": len(depots), "depot_companies": Counter(d["company"] for d in depots)}
    (ROOT / "data" / "processed" / f"map_graph_s{S:g}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


CITY_TOKENS = {"Gebze": "gebze", "Darıca": "darica", "Çayırova": "cayirova", "Dilovası": "dilovasi",
               "İzmit": "izmit", "Körfez": "korfez", "Derince": "derince", "Gölcük": "golcuk",
               "Karamürsel": "karamursel", "Kandıra": "kandira", "Kartepe": "kartepe", "Başiskele": "basiskele"}

LOOK_GROUP = {"r1_city": "r1", "r1_city_narrow": "r1", "service": "r1", "r2_divided": "r2",
              "ramp_1lane": "ramp", "hw3_oneway": "hw3", "hw3_divided": "hw3d"}
ONEWAY_LOOK = {"ramp", "hw3"}


def link_through(edges, junctions, jnodes, arm_dir):
    """Prefabsız düğümlerde kol çiftlerini (düz geçiş) zincirleyip kenarları birleştirir; kavşak kollarını yeniden eşler."""
    inc = defaultdict(list)
    for ed in edges:
        inc[ed["a"]].append((ed["id"], "a"))
        inc[ed["b"]].append((ed["id"], "b"))
    E = {ed["id"]: ed for ed in edges}
    partner = {}
    stats = Counter()
    xlinks = []  # farklı görünümlü çift yönlü yollar (r1↔r2): birleştirilmez, C# düğümleri birleştirir

    def ok_pair(x, y, cross=False):
        ex, ey = E[x[0]], E[y[0]]
        if x[0] == y[0]:
            return False
        gx, gy = LOOK_GROUP.get(ex["type"]), LOOK_GROUP.get(ey["type"])
        if gx is None or gy is None:
            return False
        if cross:  # farklı görünüm (r1↔r2, rampa↔şehir yolu/otoyol şeridi): C# uç düğümleri birleştirir
            if gx == gy or not {gx, gy} <= {"r1", "r2", "ramp", "hw3"}:
                return False
        elif gx != gy:
            return False
        ow = [g in ONEWAY_LOOK for g in (gx, gy)]
        if any(ow) and (ex["reverse"] and ow[0] or ey["reverse"] and ow[1]):
            return False
        if all(ow):  # iki tek yönlü: biri gelen (b), öbürü giden (a)
            if {x[1], y[1]} != {"a", "b"}:
                return False
        if cross and "hw3" in (gx, gy) and not all(ow):
            return False  # otoyol şeridi yalnızca rampayla
        return True

    for n, ends in inc.items():
        if n in jnodes or len(ends) < 2:
            continue
        dirs = {e: arm_dir(E[e[0]], e[1]) for e in ends}
        pairs = []
        for i in range(len(ends)):
            for j in range(i + 1, len(ends)):
                x, y = ends[i], ends[j]
                cross = ok_pair(x, y, cross=True)
                if not (cross or ok_pair(x, y)):
                    continue
                dot = dirs[x][0] * dirs[y][0] + dirs[x][1] * dirs[y][1]  # -1 = tam düz geçiş
                pr = min(E[x[0]]["prio"], E[y[0]]["prio"])
                pairs.append((dot + 0.15 * pr + (0.2 if cross else 0), dot, x, y, cross))
        pairs.sort(key=lambda t: t[0])
        used = set()
        for _, dot, x, y, cross in pairs:
            if x in used or y in used:
                continue
            if len(ends) > 2 and dot > -0.5:  # kesişimde yalnızca belirgin düz geçişler (≥120°)
                continue
            used |= {x, y}
            if cross:
                xlinks.append((x, y))
                stats["görünüm-arası"] += 1
                continue
            partner[x], partner[y] = y, x
            stats[len(ends)] += 1
        # ikinci şans: kesişimde düz çift dışında kalan iki kol, ≥60° dönüşle birbirine bağlanır (GPS/iş rotası
        # sürekliliği; aksi halde ikisi de orada çıkmaz biterdi)
        rest = [e for e in ends if e not in used]
        if len(ends) > 2 and len(rest) >= 2:
            for _, dot, x, y, cross in pairs:
                if x in used or y in used or dot > 0.5:
                    continue
                used |= {x, y}
                if cross:
                    xlinks.append((x, y))
                else:
                    partner[x], partner[y] = y, x
                stats["dönüşlü"] += 1

    # zincirler: serbest ucu olan kenardan başlayıp ortaklara yürü
    seen, out, endmap = set(), [], {}
    loop_links = []

    def walk(start_id, start_end):
        """start_end ucundan başlayarak zinciri döndürür: [(edge_id, ters_mi)], kenarların yürüme yönünde"""
        chain, eid, entry = [], start_id, start_end
        while True:
            seen.add(eid)
            rev = entry == "b"  # kenara b ucundan girildiyse ters yürünür
            chain.append((eid, rev))
            exit_end = "a" if rev else "b"
            nxt = partner.get((eid, exit_end))
            if nxt is None or nxt[0] in seen:
                return chain
            eid, entry = nxt

    starts = [(ed["id"], "a") for ed in edges if (ed["id"], "a") not in partner] +              [(ed["id"], "b") for ed in edges if (ed["id"], "b") not in partner]
    for eid, end in starts + [(ed["id"], "a") for ed in edges]:  # sonuncular: kapalı halkalar
        if eid in seen:
            continue
        chain = walk(eid, end)
        first = E[chain[0][0]]
        # tek yönlü görünümde zincir yürüme yönü trafik yönü olmalı: ters yürüdüyse tüm zinciri çevir
        if LOOK_GROUP.get(first["type"]) in ONEWAY_LOOK and chain[0][1]:
            chain = [(e, not r) for e, r in reversed(chain)]
        pts, L = [], 0.0
        for e, r in chain:
            ps = E[e]["pts"][::-1] if r else E[e]["pts"]
            pts.extend(ps if not pts else ps[1:])
            L += E[e]["len"]
        head = max((E[e] for e, _ in chain), key=lambda x: x["len"])
        e0, r0 = chain[0]
        e1, r1 = chain[-1]
        na = E[e0]["b"] if r0 else E[e0]["a"]
        nb = E[e1]["a"] if r1 else E[e1]["b"]
        new = dict(head, id=len(out), pts=[list(p) for p in pts], len=round(L, 1), a=na, b=nb,
                   prio=min(E[e]["prio"] for e, _ in chain),
                   type=min((E[e]["type"] for e, _ in chain), key=lambda t: {"r1_city": 0}.get(t, 1)),
                   reverse=head["reverse"] if len(chain) == 1 else False)
        if False and na == nb and len(new["pts"]) >= 3:  # kapalı: editörde "inconsistent linkage" verdi
            # kapalı halka: ETS2 bir yolu kendisine bağlayamaz → ikiye böl, iki ucu C#'ta birleştir
            m = len(new["pts"]) // 2
            mid_node = 10_000_000 + len(out)
            A = dict(new, pts=new["pts"][:m + 1], b=mid_node)
            B = dict(new, id=len(out) + 1, pts=new["pts"][m:], a=mid_node)
            for h in (A, B):
                h["len"] = round(sum(math.dist(p_, q_) for p_, q_ in zip(h["pts"], h["pts"][1:])), 1)
            out += [A, B]
            endmap[(e0, "b" if r0 else "a")] = (A["id"], "a")
            endmap[(e1, "a" if r1 else "b")] = (B["id"], "b")
            loop_links.append([A["id"], "b", B["id"], "a"])
            if na not in jnodes:  # halkanın başlangıç düğümü de prefabsızsa orada da birleştir
                loop_links.append([A["id"], "a", B["id"], "b"])
            stats["halka"] += 1
            continue
        out.append(new)
        endmap[(e0, "b" if r0 else "a")] = (new["id"], "a")
        endmap[(e1, "a" if r1 else "b")] = (new["id"], "b")
    for j in junctions:
        for arm in j["arms"]:
            arm["edge"], arm["end"] = endmap[(arm["edge"], arm["end"])]
    links = [[*endmap[x], *endmap[y]] for x, y in xlinks] + loop_links
    # eşlenmiş ama zincir yürüyüşünde birleşmemiş çiftler (zincir kendine dönünce durur): uçları C#'ta birleştir
    done = set()
    for x, y in ([] if True else partner.items()):  # kapalı: editörde "inconsistent linkage" verdi
        if (y, x) in done or x not in endmap or y not in endmap:
            continue
        done.add((x, y))
        ex_, ey_ = endmap[x], endmap[y]
        if ex_[0] != ey_[0]:
            links.append([*ex_, *ey_])
            stats["birleşmeyen çift"] += 1
    print(f"düz geçiş birleştirme: {sum(stats.values())} bağlantı (kol sayısına göre {dict(stats)}); "
          f"kenar {len(edges)} -> {len(out)}")
    return out, links


def load_city_polys(S):
    """İlçe poligonları (OSM admin_level 6), oyun koordinatında: {token: (ad, poligon)}."""
    from shapely.ops import polygonize, unary_union
    g = lambda x, y: ((x - E0) / S, -(y - N0) / S)
    polys = {}
    src = RAW / "kocaeli" / "districts.json"
    if not src.exists():
        src = RAW / "districts.json"
    for el in json.loads(src.read_text(encoding="utf-8"))["elements"]:
        tok = CITY_TOKENS.get(el.get("tags", {}).get("name"))
        if not tok:
            continue
        lines = [LineString([g(*T.transform(q["lon"], q["lat"])) for q in m["geometry"]])
                 for m in el.get("members", []) if m.get("role") == "outer" and "geometry" in m]
        polys[tok] = (el["tags"]["name"], unary_union(list(polygonize(unary_union(lines)))))
    return polys


_GRID = {}


def city_grid(edges, S, cell=250.0):
    """Oyunun şehir alanları (CityArea) için ÜST ÜSTE BİNMEYEN dikdörtgenler: yol ağı kutusu cell×cell ızgaraya
    bölünür, her hücre merkezinin düştüğü ilçeye verilir, aynı satırdaki ardışık aynı ilçe hücreleri birleştirilir.
    Neden: ilçe sınır kutuları çakışınca oyun depoyu başka şehre sayıyor ve aynı şehirde aynı depo prefabı
    iki şirkete düşünce "Invalid company item assignment" veriyordu (2026-11-22)."""
    key = (round(S, 3), cell)
    if key in _GRID:
        return _GRID[key]
    from shapely.geometry import Point
    polys = load_city_polys(S)
    xs = [p[0] for e in edges for p in e["pts"]]
    zs = [p[1] for e in edges for p in e["pts"]]
    x0, z0 = math.floor(min(xs) / cell) * cell, math.floor(min(zs) / cell) * cell
    nx, nz = int(math.ceil((max(xs) - x0) / cell)), int(math.ceil((max(zs) - z0) / cell))
    rects = []
    for j in range(nz):
        run = None
        for i in range(nx + 1):
            tok = None
            if i < nx:
                c = Point(x0 + (i + 0.5) * cell, z0 + (j + 0.5) * cell)
                tok = next((t for t, (_, poly) in polys.items() if poly.contains(c)), None)
                if tok is None:  # ilçe dışı (ör. İstanbul sınırı, deniz kıyısı): en yakın ilçe → boşluk kalmaz
                    tok = min(polys, key=lambda t: polys[t][1].distance(c))
            if run and tok == run[0]:
                run[2] = i
                continue
            if run and run[0]:
                rects.append({"token": run[0], "x0": x0 + run[1] * cell, "x1": x0 + (run[2] + 1) * cell,
                              "z0": z0 + j * cell, "z1": z0 + (j + 1) * cell})
            run = [tok, i, i]
    _GRID[key] = rects
    return rects


def grid_city(rects, pt, default="gebze"):
    """Oyunun göreceği şehir: noktayı içeren ızgara dikdörtgeni (yoksa en yakını)."""
    x, z = pt
    best, bd = default, float("inf")
    for r in rects:
        dx = max(r["x0"] - x, 0, x - r["x1"])
        dz = max(r["z0"] - z, 0, z - r["z1"])
        d = math.hypot(dx, dz)
        if d < bd:
            best, bd = r["token"], d
    return best


def city_of(polys, pt):
    from shapely.geometry import Point
    P = Point(pt)
    return next((t for t, (_, poly) in polys.items() if poly.contains(P)), "gebze")


def assign_cities(depots, edges, S):
    """İlçe sınırlarından (OSM admin_level 6) şehir alanları; her depoya bulunduğu ilçenin şehri atanır.
    Şehir alanı = ilçe poligonunun yol ağı kutusuyla kesişiminin sınır kutusu (oyun koordinatı)."""
    from shapely.geometry import Point, box as sbox
    from shapely.ops import polygonize, unary_union
    xs = [p[0] for e in edges for p in e["pts"]]
    zs = [p[1] for e in edges for p in e["pts"]]
    net = sbox(min(xs), min(zs), max(xs), max(zs))
    polys = load_city_polys(S)
    cities = []
    for tok, (name, poly) in polys.items():
        part = poly.intersection(net)
        if part.is_empty:
            continue
        x0, z0, x1, z1 = part.bounds
        rp = part.representative_point()
        cities.append({"token": tok, "name": name, "x0": round(x0, 1), "z0": round(z0, 1),
                       "x1": round(x1, 1), "z1": round(z1, 1), "cx": round(rp.x, 1), "cz": round(rp.y, 1)})
    # şehir adı etiketi ilçe merkezinde (places town/city): dünya haritasında doğru yerde görünsün
    cf = RAW / "kocaeli" / "centers.json"
    if cf.exists():
        cen = json.loads(cf.read_text(encoding="utf-8"))
        for c in cities:
            if c["name"] in cen:
                la, lo = cen[c["name"]]
                x, y = T.transform(lo, la)
                c["center"] = [round((x - E0) / S, 1), round(-(y - N0) / S, 1)]
    rects = city_grid(edges, S)
    for d in depots:
        d["city"] = grid_city(rects, d["body"])
    # Şirket seçimi: her şirketin TEK bir depo türü var (ana oyunda o prefabı kullanan şirketler,
    # data/processed/game_defs/company_prefabs.tsv), tanımı tüm şehirlere yazılır. Bir şehirde aynı tür/şirket
    # iki kez olmaz (place_depots (tür, şehir) benzersiz). Mümkünse haritada az kullanılan şirket seçilir.
    count, in_city = Counter(), set()
    for d in depots:
        pool = [c for c in COMPANY_POOLS[d["kind"]] if (c, d["city"]) not in in_city]
        d["company"] = min(pool, key=lambda c: (count[c], COMPANY_POOLS[d["kind"]].index(c)))
        count[d["company"]] += 1
        in_city.add((d["company"], d["city"]))
    return cities


# Depo prefabları (ana oyun, Avusturya seti): düğüm0 → düğüm1 aralığı (oyun m).
DEPOT_TYPES = [
    {"kind": "logistic", "span": 80.0},
    {"kind": "generic", "span": 100.0},
    {"kind": "light_factory", "span": 90.65},
]
COMPANY_POOLS = {"generic": ["stokes", "transinet"],
                 "logistic": ["tradeaux", "posped"],  # lkwlog, eurogoodies önizlemede "Invalid company item assignment" verdi
                 "light_factory": ["trameri", "kathode"]}


def place_depots(edges, chosen, S, a, per_city=3, min_gap=250.0, links=(), allowed=None):
    """Her şehre en çok bir tane her depo türünden yerleştirir; edges listesini yerinde böler.
    Önce sanayi poligonları içindeki uzun düz parçalar; en az iki depo alamayan şehirlerde sonra sanayi
    dışı (ör. Darıca'da sanayi alanı neredeyse yok) iki yönlü şehir yolları, giderek daralan boşlukla."""
    from shapely.geometry import Point, Polygon
    from shapely.strtree import STRtree

    g = lambda x, y: ((x - E0) / S, -(y - N0) / S)
    inds, lu_seen = [], set()
    lu = json.loads((RAW / "landuse.json").read_text(encoding="utf-8"))["elements"]
    if (RAW / "kocaeli" / "landuse.json").exists():
        lu += json.loads((RAW / "kocaeli" / "landuse.json").read_text(encoding="utf-8"))["elements"]
    for el in lu:
        if el["id"] in lu_seen:
            continue
        lu_seen.add(el["id"])
        t = el.get("tags", {})
        if el["type"] == "way" and "geometry" in el and (t.get("landuse") == "industrial" or t.get("industrial")):
            pts = [g(*T.transform(p["lon"], p["lat"])) for p in el["geometry"]]
            if len(pts) >= 4 and pts[0] == pts[-1]:
                p = Polygon(pts)
                if p.is_valid and p.area > 2000:
                    inds.append(p)
    itree = STRtree(inds)
    jpts = [(j["x"], j["z"]) for j in chosen]
    out, used = [], []
    # Oyun bir şehirde aynı depo prefabını iki şirkete eşleyemiyor ("Invalid company item assignment ...
    # Economy reset - company mismatch", 2026-11-22 önizlemede doğrulandı) → (tür, şehir) benzersiz olmalı.
    rects = city_grid(edges, S)
    kind_city = set()
    why = Counter()
    next_node = max(max(e["a"], e["b"]) for e in edges) + 1
    need = min(t["span"] for t in DEPOT_TYPES) + 24

    for industrial, clear in ((True, 45.0), (True, 36.0), (False, 40.0), (False, 32.0)):
        have = Counter(c for _, c in kind_city)
        if not industrial and all(have[c] >= 2 for c in CITY_TOKENS.values()):
            break
        lines = [LineString(e["pts"]) for e in edges]  # her geçişte yeniden: önceki bölmeler dahil
        ltree = STRtree(lines)
        k = len(out)
        for ed in sorted(edges, key=lambda e: -e["len"]):
            if ed["type"] not in ("r1_city", "r1_city_narrow") or ed["oneway"]:
                continue
            if allowed is not None and ed["id"] not in allowed:
                continue
            pts = ed["pts"]
            for i in range(len(pts) - 1):
                P, Q = pts[i], pts[i + 1]
                L = math.dist(P, Q)
                if L < need:
                    continue
                mid = ((P[0] + Q[0]) / 2, (P[1] + Q[1]) / 2)
                mp = Point(mid)
                in_ind = any(inds[q].contains(mp) for q in itree.query(mp))
                if industrial != in_ind:
                    continue
                if any(math.dist(mid, u) < min_gap for u in used):
                    why["başka depoya yakın"] += 1
                    continue
                ux, uz = (Q[0] - P[0]) / L, (Q[1] - P[1]) / L
                side = None
                for sgn in (1, -1):  # yolun sağı/solu: depo gövdesi ~55 m içeride
                    nx, nz = -uz * sgn, ux * sgn
                    body = Point(mid[0] + nx * 60, mid[1] + nz * 60)
                    near = [q for q in ltree.query(body.buffer(clear)) if edges[q] is not ed
                            and lines[q].distance(body) < clear]
                    if not near:
                        side = (nx, nz)
                        break
                if side is None:
                    why["gövde yeri dolu"] += 1
                    continue
                bcity = grid_city(rects, (mid[0] + side[0] * 55, mid[1] + side[1] * 55))
                have = Counter(c for _, c in kind_city)
                if have[bcity] >= per_city or (not industrial and have[bcity] >= 2):
                    why["şehir dolu"] += 1
                    continue
                cands = [DEPOT_TYPES[(k + q) % len(DEPOT_TYPES)] for q in range(len(DEPOT_TYPES))]
                typ = next((t for t in cands if L >= t["span"] + 24 and (t["kind"], bcity) not in kind_city
                            and not any(math.dist(mid, j) < t["span"] / 2 + 26 for j in jpts)), None)
                if typ is None:
                    why["tür sığmıyor/kavşağa yakın"] += 1
                    continue
                h = typ["span"] / 2
                n0 = (round(mid[0] - ux * h, 3), round(mid[1] - uz * h, 3))
                n1 = (round(mid[0] + ux * h, 3), round(mid[1] + uz * h, 3))
                # Depo bütünüyle tek şehir alanında olmalı: oyun öğeyi sınırdaki komşu şehre sayabiliyor
                # (Darıca deposu Gebze'ye sayılıp "Invalid company item assignment" verdi, 2026-11-22).
                probe = [n0, n1, mid] + [(mid[0] + side[0] * dd + ux * ee, mid[1] + side[1] * dd + uz * ee)
                                         for dd in (30, 60, 90) for ee in (-h - 10, 0, h + 10)]
                if any(grid_city(rects, q) != bcity for q in probe):
                    why["şehir alanı sınırında"] += 1
                    continue
                kind_city.add((typ["kind"], bcity))
                # kenarı böl: A = baş..n0, B = n1..son
                ida, idb = next_node, next_node + 1
                next_node += 2
                B = dict(ed, id=len(edges), a=idb, pts=[list(n1)] + [list(p) for p in pts[i + 1:]])
                ed["pts"] = [list(p) for p in pts[:i + 1]] + [list(n0)]
                ed["b"] = ida
                for e2 in (ed, B):
                    e2["len"] = round(sum(math.dist(p, q) for p, q in zip(e2["pts"], e2["pts"][1:])), 1)
                # B, eski kenarın b ucundaki kavşak kolunu / bağlantıyı / depo kolunu devralır
                for j in chosen:
                    for arm in j["arms"]:
                        if arm["edge"] == ed["id"] and arm["end"] == "b":
                            arm["edge"] = B["id"]
                for lk in links:  # [e1, uç1, e2, uç2]
                    for q in (0, 2):
                        if lk[q] == ed["id"] and lk[q + 1] == "b":
                            lk[q] = B["id"]
                for d in out:
                    for arm in (d["arm0"], d["arm1"]):
                        if arm["edge"] == ed["id"] and arm["end"] == "b":
                            arm["edge"] = B["id"]
                edges.append(B)
                used.append(mid)
                out.append({"id": len(out), "company": None, "kind": typ["kind"],
                            "n0": list(n0), "n1": list(n1), "industrial": industrial,
                            "body": [round(mid[0] + side[0] * 55, 2), round(mid[1] + side[1] * 55, 2)],
                            "arm0": {"edge": ed["id"], "end": "b"}, "arm1": {"edge": B["id"], "end": "a"}})
                k += 1
                break
    have = Counter(c for _, c in kind_city)
    print(f"depolar: {len(out)} (şehre göre {dict(have)}); elenen: {dict(why)}")
    return out


def comp_finder(edges, junctions, links):
    par = {}

    def f(x):
        par.setdefault(x, x)
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for j in junctions:
        for arm in j["arms"]:
            ra, rb = f(("e", arm["edge"])), f(("j", id(j)))
            if ra != rb:
                par[ra] = rb
    for l in links:
        ra, rb = f(("e", l[0])), f(("e", l[2]))
        if ra != rb:
            par[ra] = rb
    return lambda eid: f(("e", eid))


def ramp_city_links(edges, chosen, hwj, forks, links, reach_m=260.0, clear=40.0, min_comp=5000.0):
    """Kavşak rampaları şehre bağlansın: boşta BİTEN çıkış rampası ve boşta BAŞLAYAN katılma rampası en yakın iki yönlü
    şehir yoluna kısa bağlantı yolu (Bezier, uçta rampa yönünde) + T kavşak (force_tees) ile bağlanır. Yoksa otoyoldan
    çıkıp dönülemiyor, otoyol halkası bile güçlü bağlı ağın dışında kalıyordu (2026-11-23)."""
    from shapely.geometry import Point
    from shapely.strtree import STRtree
    allj = chosen + hwj + forks
    used = {(x["edge"], x["end"]) for j in allj for x in j["arms"]}
    used |= {(l[0], l[1]) for l in links} | {(l[2], l[3]) for l in links}
    centers = [(j["x"], j["z"]) for j in allj]
    cgrid = defaultdict(list)
    for c in centers:
        cgrid[(int(c[0] // 100), int(c[1] // 100))].append(c)

    def clear_of(p):
        gx, gz = int(p[0] // 100), int(p[1] // 100)
        return all(math.dist(p, q) >= clear for dx in (-1, 0, 1) for dz in (-1, 0, 1) for q in cgrid[(gx + dx, gz + dz)])
    # yalnız büyük şehir ağı parçalarına (≥ 5 km): küçük kopuk sokak parçasına bağlanan rampa tuzak olur
    comp = comp_finder(edges, allj, links)
    clen = Counter()
    for e in edges:
        clen[comp(e["id"])] += e["len"]
    tw = [e for e in edges if (e["type"] in CITY or e["type"] in R2) and clen[comp(e["id"])] >= min_comp]
    lines = [LineString(e["pts"]) for e in tw]
    tree = STRtree(lines)
    allines = [LineString(e["pts"]) for e in edges]
    atree = STRtree(allines)
    ends = []
    for e in edges:
        if e["type"] != "ramp_1lane" or e.get("reverse"):
            continue
        for end in ("a", "b"):
            if (e["id"], end) not in used:
                ends.append((e, end))
    made = 0
    for r, rend in ends:
        Q = tuple(r["pts"][0] if rend == "a" else r["pts"][-1])
        rt = end_tangent(r, rend)
        best = None
        for i in tree.query(Point(Q).buffer(reach_m)):
            ln, e = lines[i], tw[i]
            if e["id"] == r["id"]:
                continue
            na = (23.5 if e["type"] in R2 else 18.5) + (22.0 if (e["id"], "a") in used else 4.0)
            nb = (23.5 if e["type"] in R2 else 18.5) + (22.0 if (e["id"], "b") in used else 4.0)
            if ln.length < na + nb:
                continue
            s_ = min(max(ln.project(Point(Q)), na), ln.length - nb)
            Pp = ln.interpolate(s_)
            P = (Pp.x, Pp.y)
            d = math.dist(P, Q)
            if d < 25 or d > reach_m or (best and d >= best[0]) or not clear_of(P):
                continue
            ux, uz = (Q[0] - P[0]) / d, (Q[1] - P[1]) / d
            P2 = ln.interpolate(min(ln.length, s_ + 2))
            P1 = ln.interpolate(max(0, s_ - 2))
            tl = math.dist((P1.x, P1.y), (P2.x, P2.y)) or 1
            if abs(ux * (P2.x - P1.x) / tl + uz * (P2.y - P1.y) / tl) > 0.85:
                continue  # T için yola yaklaşık dik
            a_ = (P[0] + ux * 1.5, P[1] + uz * 1.5)
            tQ = rt if rend == "a" else (-rt[0], -rt[1])
            npts = bezier_pts(a_, (ux, uz), Q, tQ)
            if not smooth_enough(npts, (ux, uz), tQ, 40.0):
                continue
            pl = LineString(npts)
            if any(edges[q]["id"] not in (e["id"], r["id"]) and allines[q].intersects(pl)
                   and allines[q].distance(Point(Q)) > 1 for q in atree.query(pl)):
                continue
            best = (d, P, npts, e["id"])
        if not best:
            continue
        d, P, npts, eid = best
        npts = thin_curve(npts)
        n0 = max(max(x["a"], x["b"]) for x in edges) + 1
        edges.append({"id": len(edges), "osm": 0, "hw": "tertiary", "type": "r1_city", "prio": 6, "oneway": False,
                      "reverse": False, "a": n0, "b": n0 + 1, "pts": npts,
                      "len": round(sum(math.dist(p_, q_) for p_, q_ in zip(npts, npts[1:])), 1), "connector": True})
        links.append([len(edges) - 1, "b", r["id"], rend])
        used |= {(r["id"], rend), (len(edges) - 1, "b")}
        centers.append(P)
        cgrid[(int(P[0] // 100), int(P[1] // 100))].append(P)
        made += 1
    print(f"rampa-şehir bağlantısı: {made} / {len(ends)} boşta rampa ucu")
    return made


def ramp_access(edges, chosen, hwj, forks, links, targets, min_group=4000.0, reach_m=450.0, lane_based=False):
    """Güçlü bağlı ağın dışında kalan büyük şehir ağı için yönlü eksik tamamlama: gruptan ağa çıkış yoksa boşta
    BAŞLAYAN ve ağa ulaşan bir katılma rampasına, ağdan gruba giriş yoksa boşta BİTEN ve ağdan gelinen bir çıkış
    rampasına kısa bağlantı yolu (gruptaki yolda T, rampa ucunda uç bağlantısı). Başka yolu kesmez (Darıca, 2026-11-23)."""
    from shapely.geometry import Point
    from shapely.strtree import STRtree
    sys.path.insert(0, str(ROOT / "tools" / "validation"))
    from directed import build, reach
    allj = chosen + hwj + forks
    g = {"edges": edges, "junctions": chosen, "hw_junctions": hwj, "ramp_forks": forks, "road_links": links}
    adj = build(g)
    radj = defaultdict(set)
    for u, vs in adj.items():
        for v in vs:
            radj[v].add(u)
    Sn = {(i, x) for i in targets for x in "ab"}
    ref = next(iter(Sn))
    if lane_based:  # ilk tur: herhangi bir otoyol şeridine ulaşan / şeritten gelinen (dönüşler sonra kurulur)
        src = [(e["id"], x) for e in edges if e["type"].startswith("hw") and e["type"].endswith("_oneway") for x in "ab"]

        def multi(gr):
            seen, q = set(src), list(src)
            while q:
                u = q.pop()
                for v in gr[u]:
                    if v not in seen:
                        seen.add(v); q.append(v)
            return seen
        toS, fromS = multi(radj), multi(adj)
    else:
        toS = reach(radj, ref)    # buradan S'ye gidilebilen düğümler
        fromS = reach(adj, ref)   # S'den gidilebilen düğümler
    nt = {e["id"] for e in edges if e["id"] not in targets}
    sub_j = [{"arms": [x for x in j["arms"] if x["edge"] in nt]} for j in allj]
    comp = comp_finder(edges, sub_j, [l for l in links if l[0] in nt and l[2] in nt])
    glen = Counter()
    for e in edges:
        if e["id"] in nt:
            glen[comp(e["id"])] += e["len"]
    used = {(x["edge"], x["end"]) for j in allj for x in j["arms"]}
    used |= {(l[0], l[1]) for l in links} | {(l[2], l[3]) for l in links}
    centers = [(j["x"], j["z"]) for j in allj]
    bad = [e for e in edges if len(e["pts"]) < 2]
    if bad:
        print("HATA tek noktalı kenar:", [(e["id"], e["type"], e.get("connector"), e.get("uturn"), e["pts"]) for e in bad[:5]])
    allines = [LineString(e["pts"]) for e in edges]
    atree = STRtree(allines)
    pt = lambda e, end: tuple(e["pts"][0] if end == "a" else e["pts"][-1])
    dead_in = [(e, "a") for e in edges if e["type"] == "ramp_1lane" and not e.get("reverse")
               and (e["id"], "a") not in used and (e["id"], "a") in toS]
    dead_out = [(e, "b") for e in edges if e["type"] == "ramp_1lane" and not e.get("reverse")
                and (e["id"], "b") not in used and (e["id"], "b") in fromS]
    made = 0
    for g_, L in glen.most_common():
        if L < min_group:
            break
        gnodes = [(e["id"], x) for e in edges if e["id"] in nt and comp(e["id"]) == g_ for x in "ab"]
        has_out = any(n in toS for n in gnodes)
        has_in = any(n in fromS for n in gnodes)
        tw = [e for e in edges if e["id"] in nt and comp(e["id"]) == g_ and (e["type"] in CITY or e["type"] in R2)]
        if not tw:
            continue
        lines = [LineString(e["pts"]) for e in tw]
        tree = STRtree(lines)
        for need_dir, pool in (("out", dead_in), ("in", dead_out)):
            if (need_dir == "out" and has_out) or (need_dir == "in" and has_in):
                continue
            best = None
            for r, rend in pool:
                Q = pt(r, rend)
                for i in tree.query(Point(Q).buffer(reach_m)):
                    ln = lines[i]
                    e = tw[i]
                    s_ = ln.project(Point(Q))
                    na = (23.5 if e["type"] in R2 else 18.5) + (22.0 if (e["id"], "a") in used else 4.0)
                    nb = (23.5 if e["type"] in R2 else 18.5) + (22.0 if (e["id"], "b") in used else 4.0)
                    s_ = min(max(s_, na), ln.length - nb)
                    if s_ < na:
                        continue
                    P = ln.interpolate(s_)
                    P = (P.x, P.y)
                    d = math.dist(P, Q)
                    if d < 25 or d > reach_m or (best and d >= best[0]):
                        continue
                    if any(math.dist(P, q) < 45 for q in centers):
                        continue
                    seg = LineString([P, Q])
                    if any(edges[q]["id"] not in (e["id"], r["id"]) and allines[q].intersects(seg)
                           and allines[q].distance(Point(P)) > 1 and allines[q].distance(Point(Q)) > 1
                           for q in atree.query(seg)):
                        continue
                    best = (d, P, Q, r["id"], rend, e["id"])
            if not best:
                print(f"  rampa erişimi ({need_dir}) bulunamadı: grup {L / 1000:.1f} km")
                continue
            d, P, Q, rid, rend, eid = best
            ux, uz = (Q[0] - P[0]) / d, (Q[1] - P[1]) / d
            a_ = (P[0] + ux * 1.5, P[1] + uz * 1.5)
            n0 = max(max(x["a"], x["b"]) for x in edges) + 1
            Rr = next(x for x in edges if x["id"] == rid)
            rt = end_tangent(Rr, rend)
            # P→Q yönünde Q'daki teğet: rampaya giriş (a) → rampa yönü; rampadan çıkış (b) → rampa yönünün tersi
            tQ = rt if rend == "a" else (-rt[0], -rt[1])
            npts = thin_curve(bezier_pts(a_, (ux, uz), Q, tQ))
            edges.append({"id": len(edges), "osm": 0, "hw": "tertiary", "type": "r1_city", "prio": 6, "oneway": False,
                          "reverse": False, "a": n0, "b": n0 + 1, "pts": npts,
                          "len": round(sum(math.dist(p_, q_) for p_, q_ in zip(npts, npts[1:])), 1), "connector": True})
            links.append([len(edges) - 1, "b", rid, rend])
            used |= {(rid, rend), (len(edges) - 1, "b")}
            centers.append(P)
            dead_in = [x for x in dead_in if x[0]["id"] != rid]
            dead_out = [x for x in dead_out if x[0]["id"] != rid]
            made += 1
            print(f"  rampa erişimi ({need_dir}): grup {L / 1000:.1f} km, {d:.0f} m, {[round(v) for v in P]}")
    return made


def lane_access(edges, chosen, hwj, forks, links, a, targets, cities, min_group=4000.0):
    """Güçlü bağlı ağın dışında kalan büyük şehir ağı (Darıca: D-100 şeritlerine 20-40 m paralel yan yol) için yan yol
    üzerine X kavşak + aynı şeritte çıkış (s-25) ve katılma (s+25) rampaları: ilçeye hem girilir hem çıkılır."""
    from shapely.geometry import Point
    from shapely.strtree import STRtree
    PL = a.hw_prefab_len
    allj = chosen + hwj + forks
    nt = {e["id"] for e in edges if e["id"] not in targets}
    sub_j = [{"arms": [x for x in j["arms"] if x["edge"] in nt]} for j in allj]
    comp = comp_finder(edges, sub_j, [l for l in links if l[0] in nt and l[2] in nt])
    glen = Counter()
    for e in edges:
        if e["id"] in nt:
            glen[comp(e["id"])] += e["len"]
    used = {(x["edge"], x["end"]) for j in allj for x in j["arms"]}
    centers = [(j["x"], j["z"]) for j in allj]
    lanes = [e for e in edges if e["id"] in targets and e["type"].startswith("hw") and e["type"].endswith("_oneway")
             and not e.get("reverse") and e["len"] > 2 * PL + 70]
    if not lanes:
        return 0
    llines = [LineString(e["pts"]) for e in lanes]
    ltree = STRtree(llines)
    allines = [LineString(e["pts"]) for e in edges]
    atree = STRtree(allines)
    made, touched = 0, set()
    for g_, L in glen.most_common():
        if L < min_group:
            break
        best = None
        LD = Counter()
        for e in edges:
            if e["id"] not in nt or comp(e["id"]) != g_ or e["id"] in touched:
                continue
            LD["tip " + e["type"]] += 1
            if not (e["type"] in CITY or e["type"] in R2) or e["type"] in R2:
                continue
            ln = LineString(e["pts"])
            need_a = 18.5 + (22.0 if (e["id"], "a") in used else 4.0)
            need_b = 18.5 + (22.0 if (e["id"], "b") in used else 4.0)
            d0 = need_a
            while d0 <= ln.length - need_b:
                J = ln.interpolate(d0)
                Jp = (J.x, J.y)
                d0 += 10.0
                if any(math.dist(Jp, q) < 45 for q in centers):
                    LD["J prefab yakın"] += 1
                    continue
                for i in ltree.query(J.buffer(70)):
                    if lanes[i]["id"] in touched:
                        continue  # bu çağrıda bölündü (geometri eski)
                    hl = llines[i]
                    dl = hl.distance(J)
                    if dl < 18 or dl > 70:
                        LD["şerit uzaklığı"] += 1
                        continue
                    LD["aday"] += 1
                    s_ = hl.project(J)
                    se_, sm_ = s_ - 30.0, s_ + 30.0
                    if se_ < PL + 6 or hl.length - sm_ < PL + 6:
                        LD["şerit kısa"] += 1
                        continue
                    ce = (hl.interpolate(se_).x, hl.interpolate(se_).y)
                    cm = (hl.interpolate(sm_).x, hl.interpolate(sm_).y)
                    if any(math.dist(z, q) < PL + 15 for q in centers for z in (ce, cm)):
                        LD["şeritte prefab yakın"] += 1
                        continue
                    A1, A2 = hl.interpolate(s_ - 5), hl.interpolate(s_ + 5)
                    tl = math.dist((A1.x, A1.y), (A2.x, A2.y)) or 1
                    tx, tz = (A2.x - A1.x) / tl, (A2.y - A1.y) / tl
                    if (Jp[0] - A1.x) * (-tz) + (Jp[1] - A1.y) * tx < 10:
                        LD["solda"] += 1
                        continue  # yan yol şeridin sağında olmalı
                    bad = False
                    for seg in (LineString([ce, Jp]), LineString([Jp, cm])):
                        for q in atree.query(seg):
                            if edges[q]["id"] in (e["id"], lanes[i]["id"]):
                                continue
                            if allines[q].intersects(seg) and allines[q].distance(Point(Jp)) > 1 and \
                                    allines[q].distance(Point(ce)) > 1 and allines[q].distance(Point(cm)) > 1:
                                bad = True
                    if bad:
                        LD["kesişiyor"] += 1
                        continue
                    score = dl
                    if best is None or score < best[0]:
                        best = (score, e["id"], d0 - 10.0, Jp, i, se_, sm_, ce, cm, (tx, tz))
        if not best:
            print(f"  şerit erişimi bulunamadı: grup {L / 1000:.1f} km {dict(LD) if L > 25000 else ''}")
            continue
        _, eid, dJ, Jp, i, se_, sm_, ce, cm, (tx, tz) = best
        E = {x["id"]: x for x in edges}
        e = E[eid]
        h = lanes[i]

        def split_edge(hh, cut):
            hp = hh["pts"]
            sc = LineString(hp).project(Point(cut))
            acc_, kk = 0.0, 0
            while kk < len(hp) - 1 and acc_ + math.dist(hp[kk], hp[kk + 1]) < sc:
                acc_ += math.dist(hp[kk], hp[kk + 1])
                kk += 1
            Ap = [list(q) for q in hp[:kk + 1]] + [list(cut)]
            Bp = [list(cut)] + [list(q) for q in hp[kk + 1:]]
            if len(Ap) > 2 and math.dist(Ap[-2], cut) < 0.5:
                Ap.pop(-2)
            if len(Bp) > 2 and math.dist(Bp[1], cut) < 0.5:
                Bp.pop(1)
            nn = max(max(x["a"], x["b"]) for x in edges) + 1
            Bn = dict(hh, id=len(edges), a=nn, pts=Bp)
            Bn["b"] = hh["b"]
            hh["pts"], hh["b"] = Ap, nn
            for e2 in (hh, Bn):
                e2["len"] = round(sum(math.dist(p_, q_) for p_, q_ in zip(e2["pts"], e2["pts"][1:])), 1)
            for j in allj:
                for x in j["arms"]:
                    if x["edge"] == hh["id"] and x["end"] == "b":
                        x["edge"] = Bn["id"]
            for lk in links:
                for q_ in (0, 2):
                    if lk[q_] == hh["id"] and lk[q_ + 1] == "b":
                        lk[q_] = Bn["id"]
            edges.append(Bn)
            if "_id_targets" in hh:
                pass
            return Bn, nn
        Bm, n_m = split_edge(h, cm)
        Mm, n_e = split_edge(h, ce)
        targets |= {Bm["id"], Mm["id"]}
        touched |= {h["id"], Bm["id"], Mm["id"], e["id"]}
        Be, nJ = split_edge(e, Jp)
        Rx = {"id": len(edges), "osm": 0, "hw": "motorway_link", "type": "ramp_1lane", "prio": 4, "oneway": True,
              "reverse": False, "a": n_e, "b": nJ, "pts": [list(ce), list(Jp)], "len": round(math.dist(ce, Jp), 1)}
        edges.append(Rx)
        Rm = {"id": len(edges), "osm": 0, "hw": "motorway_link", "type": "ramp_1lane", "prio": 4, "oneway": True,
              "reverse": False, "a": nJ, "b": n_m, "pts": [list(Jp), list(cm)], "len": round(math.dist(Jp, cm), 1)}
        edges.append(Rm)

        def dfrom(pp):
            o_, tg = pp[0], pp[-1]
            acc2 = 0.0
            for p_, q_ in zip(pp, pp[1:]):
                acc2 += math.dist(p_, q_)
                if acc2 >= 15:
                    tg = q_
                    break
            dx_, dz_ = tg[0] - o_[0], tg[1] - o_[1]
            LL = math.hypot(dx_, dz_) or 1
            return [round(dx_ / LL, 4), round(dz_ / LL, 4)]
        dirs_ = [dfrom(e["pts"][::-1]), dfrom(Be["pts"]), dfrom([list(Jp), list(ce)]), dfrom([list(Jp), list(cm)])]
        chosen.append({"id": len(chosen), "node": nJ, "x": Jp[0], "z": Jp[1], "shape": "x", "forced": True,
                       "arms": [{"edge": e["id"], "end": "b", "cls": "r1", "dir": dirs_[0]},
                                {"edge": Be["id"], "end": "a", "cls": "r1", "dir": dirs_[1]},
                                {"edge": Rx["id"], "end": "b", "cls": "r1", "dir": dirs_[2]},
                                {"edge": Rm["id"], "end": "a", "cls": "r1", "dir": dirs_[3]}]})
        hwj.append({"id": len(hwj), "node": n_e, "x": ce[0], "z": ce[1], "kind": "exit",
                    "travel": [round(tx, 4), round(tz, 4)], "forced": True,
                    "arms": [{"edge": h["id"], "end": "b", "role": "in"}, {"edge": Mm["id"], "end": "a", "role": "out"},
                             {"edge": Rx["id"], "end": "a", "role": "ramp"}]})
        hwj.append({"id": len(hwj), "node": n_m, "x": cm[0], "z": cm[1], "kind": "merge",
                    "travel": [round(tx, 4), round(tz, 4)], "forced": True,
                    "arms": [{"edge": Mm["id"], "end": "b", "role": "in"}, {"edge": Bm["id"], "end": "a", "role": "out"},
                             {"edge": Rm["id"], "end": "b", "role": "ramp"}]})
        centers += [ce, cm, Jp]
        allj = chosen + hwj + forks
        made += 1
        print(f"  şerit erişimi (yarım elmas, yan yolda X): grup {L / 1000:.1f} km, {[round(v) for v in Jp]}")
    return made


def add_connectors(edges, junctions, links, min_comp=8000.0, max_len=600.0, clear=45.0, targets=None):
    """Ana ağdan kopuk büyük şehir ağları (Darıca: ana ağa yalnız prefab sığmayan sıkışık otoyol kavşaklarında
    değiyordu) için kısa bağlantı yolu: iki ağın birbirine en yakın, prefablardan uzak ve başka yolu kesmeyen noktaları
    arasına iki yönlü şehir yolu konur; uçları 1,5 m açıkta bırakılır, force_tees T kavşakla bağlar (2026-11-23)."""
    from shapely.geometry import Point
    from shapely.strtree import STRtree
    comp = comp_finder(edges, junctions, links)
    clen = Counter()
    for e in edges:
        clen[comp(e["id"])] += e["len"]
    main = clen.most_common(1)[0][0]
    # targets verilirse (güçlü bağlı ağın kenarları): hedef = o ağ, kaynak = dışında kalan büyük bileşen parçaları
    in_main = (lambda e: e["id"] in targets) if targets is not None else (lambda e: comp(e["id"]) == main)
    if targets is not None:
        # kaynak grupları yalnız güçlü bağlı ağ DIŞINDAKİ kenarlar üzerinden (aksi halde Darıca ana yönsüz bileşenin
        # bir parçası sayılıp bağlantı başka yere konuyordu)
        nt = {e["id"] for e in edges if e["id"] not in targets}
        sub_j = [{"arms": [a_ for a_ in j["arms"] if a_["edge"] in nt]} for j in junctions]
        comp = comp_finder(edges, sub_j, [l for l in links if l[0] in nt and l[2] in nt])
        clen = Counter()
        for e in edges:
            if e["id"] not in targets:
                clen[comp(e["id"])] += e["len"]
        main = None
    TW = [e for e in edges if e["type"] in CITY or e["type"] in R2]
    centers = [(j["x"], j["z"]) for j in junctions]
    cgrid = defaultdict(list)
    for c in centers:
        cgrid[(int(c[0] // 100), int(c[1] // 100))].append(c)

    def clear_of(p):
        gx, gz = int(p[0] // 100), int(p[1] // 100)
        return all(math.dist(p, q) >= clear for dx in (-1, 0, 1) for dz in (-1, 0, 1) for q in cgrid[(gx + dx, gz + dz)])

    def samples(e):
        ln = LineString(e["pts"])
        out = []
        d = 48.0
        while d <= ln.length - 48.0:
            q = ln.interpolate(d)
            q2 = ln.interpolate(d + 2.0)
            L = math.dist((q.x, q.y), (q2.x, q2.y)) or 1
            out.append(((q.x, q.y), ((q2.x - q.x) / L, (q2.y - q.y) / L)))
            d += 12.0
        return out
    mpts = [(p_, t_, e["id"]) for e in TW if in_main(e) for p_, t_ in samples(e)]
    if not mpts:
        return 0
    mtree = STRtree([Point(p_) for p_, _, _ in mpts])
    allines = [LineString(e["pts"]) for e in edges]
    atree = STRtree(allines)
    hwl = [LineString(e["pts"]) for e in edges if e["type"].startswith("hw") or e["type"] == "ramp_1lane"]
    htree = STRtree(hwl)

    def off_hw(p):
        P = Point(p)
        return all(hwl[q].distance(P) >= 10.0 for q in htree.query(P.buffer(10.0)))
    added = 0
    for c, L in clen.most_common():
        if c == main or L < min_comp:
            continue
        best = None
        DBG = Counter()
        for e in TW:
            if comp(e["id"]) != c or in_main(e):
                continue
            for p1, t1 in samples(e):
                DBG["tw örnek"] += 1
                if not clear_of(p1) or not off_hw(p1):
                    DBG["tw p1 yakın"] += 1
                    continue
                for k in mtree.query(Point(p1).buffer(max_len)):
                    p2, t2, eid2 = mpts[k]
                    d = math.dist(p1, p2)
                    if d < 48 or d > max_len or (best and d >= best[0]):
                        continue
                    ux, uz = (p2[0] - p1[0]) / d, (p2[1] - p1[1]) / d
                    if abs(ux * t1[0] + uz * t1[1]) > 0.85 or abs(ux * t2[0] + uz * t2[1]) > 0.85:
                        DBG["tw dik değil"] += 1
                        continue  # T için bağlantı yola yaklaşık dik olmalı
                    if not clear_of(p2) or not off_hw(p2):
                        DBG["tw p2 yakın"] += 1
                        continue
                    seg = LineString([p1, p2])
                    if any(allines[q].distance(Point(p1)) > 0.5 and allines[q].distance(Point(p2)) > 0.5
                           and allines[q].intersects(seg) for q in atree.query(seg)):
                        DBG["tw kesişiyor"] += 1
                        continue
                    best = (d, p1, p2, ux, uz)
        if not best:
            # ikinci seçenek: otoyol/bölünmüş yol şeridine (sağ yandan) çıkış/katılma ile (force_hw_tees bağlar)
            lanes = [e for e in edges if e["type"] == "hw3_oneway" and not e.get("reverse") and e["len"] > 120
                     and (targets is None or e["id"] in targets)]
            for e in TW:
                if comp(e["id"]) != c or in_main(e):
                    continue
                for p1, t1 in samples(e):
                    DBG["örnek"] += 1
                    if not clear_of(p1) or not off_hw(p1):
                        DBG["p1 prefab/otoyol yakın"] += 1
                        continue
                    for h in lanes:
                        ln = LineString(h["pts"])
                        if ln.distance(Point(p1)) > max_len:
                            continue
                        s_ = ln.project(Point(p1))
                        if s_ < 50 or ln.length - s_ < 50:
                            continue
                        Q = ln.interpolate(s_)
                        p2 = (Q.x, Q.y)
                        d = math.dist(p1, p2)
                        if d < 48 or (best and d >= best[0]):
                            continue
                        if any(math.dist(p2, q) < 52 for q in centers):
                            DBG["p2 prefab yakın"] += 1
                            continue
                        A1, A2 = ln.interpolate(max(0, s_ - 5)), ln.interpolate(min(ln.length, s_ + 5))
                        tl = math.dist((A1.x, A1.y), (A2.x, A2.y)) or 1
                        tx, tz = (A2.x - A1.x) / tl, (A2.y - A1.y) / tl
                        ux, uz = (p2[0] - p1[0]) / d, (p2[1] - p1[1]) / d
                        if (-ux) * (-tz) + (-uz) * tx < 0.5:
                            DBG["sol taraf"] += 1
                            continue  # bağlantı şeridin sağından gelmeli
                        if abs(ux * t1[0] + uz * t1[1]) > 0.75:
                            DBG["dik değil"] += 1
                            continue
                        seg = LineString([p1, (p2[0] - ux * 2, p2[1] - uz * 2)])
                        if any(allines[q].distance(Point(p1)) > 0.5 and allines[q].intersects(seg)
                               for q in atree.query(seg)):
                            DBG["kesişiyor"] += 1
                            continue
                        best = (d, p1, p2, ux, uz)
        if not best:
            print(f"  bağlantı yolu bulunamadı: bileşen {L / 1000:.1f} km {dict(DBG)}")
            continue
        d, p1, p2, ux, uz = best
        a_ = (p1[0] + ux * 1.5, p1[1] + uz * 1.5)
        b_ = (p2[0] - ux * 1.5, p2[1] - uz * 1.5)
        n0 = max(max(e["a"], e["b"]) for e in edges) + 1
        pts = [list(a_)]
        nseg = max(1, int((d - 3) // 60))
        for i in range(1, nseg):
            t = i / nseg
            pts.append([a_[0] + (b_[0] - a_[0]) * t, a_[1] + (b_[1] - a_[1]) * t])
        pts.append(list(b_))
        edges.append({"id": len(edges), "osm": 0, "hw": "tertiary", "type": "r1_city", "prio": 6, "oneway": False,
                      "reverse": False, "a": n0, "b": n0 + 1, "pts": pts, "len": round(d - 3.0, 1), "connector": True})
        mpts += [(q_, t_, len(edges) - 1) for q_, t_ in []]
        centers += [p1, p2]
        cgrid[(int(p1[0] // 100), int(p1[1] // 100))].append(p1)
        cgrid[(int(p2[0] // 100), int(p2[1] // 100))].append(p2)
        added += 1
        print(f"  bağlantı yolu: bileşen {L / 1000:.1f} km → ana ağ, {d:.0f} m, {[round(v) for v in p1]}")
    return added


def force_tees(edges, chosen, others, links, a, gap=42.0, need=28.0, reach=60.0):
    """T kopukluğu onarımı: iki yönlü bir yolun boşta kalan ucu başka bir iki yönlü yolun ORTASINA değiyorsa (önceki
    turlarda kısa kol / yakın kavşak yüzünden prefab alamamış kesişim; 4c'de geçen yol tek parçaya birleşti) geçen yol
    o noktada bölünür ve T (iki uç değiyorsa X) kavşak prefabı konur. Darıca ve Karamürsel'in şehir içi ağı bu
    kopukluklarla ana ağdan ayrıydı (2026-11-23). Koşul: her kol ≥ need m, başka prefaba ≥ gap m, açı uyuyor."""
    from shapely.geometry import Point
    from shapely.strtree import STRtree
    # şehir yolu görünümleri oyunda her zaman çift yönlü yol öğesi (tek yönlü OSM yolları da; yalnız rampa/otoyol şeridi
    # tek yönlü görünümde) → tek yönlü şehir yolları da T kavşağa bağlanabilir
    TWT = lambda e: e["type"] in CITY or e["type"] in R2 or e["type"] == "service"
    centers = [(j["x"], j["z"]) for j in chosen + others]
    next_node = max(max(e["a"], e["b"]) for e in edges) + 1
    made, extended = 0, [0]

    def arm_need(e_, far_used):
        # prefab düğümü merkezden 18 m (r1) / 23,25 m (r2); kalan yol ≥ 4 m, karşı uç prefablıysa onun kolu da
        return (23.5 if e_["type"] in R2 else 18.5) + (22.0 if far_used else 4.0)
    for _pass in range(4):
        E = {e["id"]: e for e in edges}
        used = {(arm["edge"], arm["end"]) for j in chosen + others for arm in j["arms"]}
        used |= {(l[0], l[1]) for l in links} | {(l[2], l[3]) for l in links}
        tw = [e for e in edges if TWT(e)]
        lines = [LineString(e["pts"]) for e in tw]
        tree = STRtree(lines)
        cgrid = defaultdict(list)
        for c in centers:
            cgrid[(int(c[0] // 50), int(c[1] // 50))].append(c)

        def near_c(p):
            gx, gz = int(p[0] // 50), int(p[1] // 50)
            return any(math.dist(p, q) < gap for dx in (-1, 0, 1) for dz in (-1, 0, 1) for q in cgrid[(gx + dx, gz + dz)])
        hits = defaultdict(list)  # (geçen kenar) -> [(s, sap kenar, uç)]
        comp = comp_finder(edges, chosen + others, links)
        allines = [LineString(e["pts"]) for e in edges]
        edges_idx = [e["id"] for e in edges]
        atree = STRtree(allines)
        endcount = Counter()
        for e in edges:
            endcount[tuple(round(v, 1) for v in e["pts"][0])] += 1
            endcount[tuple(round(v, 1) for v in e["pts"][-1])] += 1
        hw_armed = {arm["edge"] for j in others if "kind" in j for arm in j["arms"]}  # otoyol prefabı ve rampa çatalı kolları
        for e in tw + [e for e in edges if e["type"] == "ramp_1lane"]:
            for end in ("a", "b"):
                oth = "b" if end == "a" else "a"
                if (e["id"], end) in used or e["len"] < arm_need(e, (e["id"], oth) in used):
                    continue
                p = e["pts"][0] if end == "a" else e["pts"][-1]
                P = Point(p)
                dead = endcount[tuple(round(v, 1) for v in p)] == 1 and e["type"] != "ramp_1lane"
                best = None
                for i in tree.query(P.buffer(reach if dead else 3.0)):
                    h = tw[i]
                    d_ = lines[i].distance(P)
                    if h["id"] == e["id"] or d_ > (reach if dead else 3.0):
                        continue
                    if d_ > 3.0:
                        # uzatma yalnız ayrı bileşenleri birleştirmek için ve başka yolu kesmeden
                        if comp(h["id"]) == comp(e["id"]):
                            continue
                        Q = lines[i].interpolate(lines[i].project(P))
                        seg = LineString([p, (Q.x, Q.y)])
                        if any(edges_idx[k_] not in (e["id"], h["id"]) and allines[k_].distance(Q) > 0.5
                               and allines[k_].crosses(seg) for k_ in atree.query(seg)):
                            continue
                    s_ = lines[i].project(P)
                    if s_ < arm_need(h, (h["id"], "a") in used) or                             lines[i].length - s_ < arm_need(h, (h["id"], "b") in used):
                        continue
                    if best is None or d_ < best[0]:
                        best = (d_, h["id"], s_)
                if best:
                    hits[best[1]].append((best[2], e["id"], end))
        done_edges, new_edges, splits = set(), [], 0
        for hid, lst in hits.items():
            lst.sort()
            s_, sid, send = lst[0]
            stems = [(sid, send)] + [(x[1], x[2]) for x in lst[1:] if abs(x[0] - s_) < 3.0 and x[1] != sid][:1]
            if hid in done_edges or any(x[0] in done_edges for x in stems):
                continue
            h = E[hid]
            ln = LineString(h["pts"])
            X = ln.interpolate(s_)
            c = (round(X.x, 3), round(X.y, 3))
            if near_c(c):
                continue
            # bölme noktası, iki yön ve sap yönleri
            pts = h["pts"]
            acc, k = 0.0, 0
            while k < len(pts) - 1 and acc + math.dist(pts[k], pts[k + 1]) < s_:
                acc += math.dist(pts[k], pts[k + 1])
                k += 1
            A_pts = [list(q) for q in pts[:k + 1]] + [list(c)]
            B_pts = [list(c)] + [list(q) for q in pts[k + 1:]]
            if math.dist(A_pts[-2], c) < 0.5:
                A_pts.pop(-2)
            if math.dist(B_pts[1], c) < 0.5:
                B_pts.pop(1)
            if len(A_pts) < 2 or len(B_pts) < 2:
                continue

            def dir_from(ps):
                o, acc_, tgt = ps[0], 0.0, ps[-1]
                for p_, q_ in zip(ps, ps[1:]):
                    acc_ += math.dist(p_, q_)
                    if acc_ >= 15:
                        tgt = q_
                        break
                dx, dz = tgt[0] - o[0], tgt[1] - o[1]
                L = math.hypot(dx, dz) or 1
                return [round(dx / L, 4), round(dz / L, 4)]
            arms = [(None, "A", dir_from(A_pts[::-1]), h), (None, "B", dir_from(B_pts), h)]
            def stem_pts(se, send_):
                ps = se["pts"] if send_ == "a" else se["pts"][::-1]
                if math.dist(ps[0], c) > 3.0:  # uzatılan çıkmaz uç
                    return [list(c)] + [list(q) for q in ps]
                return [list(c)] + [list(q) for q in ps[1:]]
            for sid_, send_ in stems:
                se = E[sid_]
                arms.append((sid_, send_, dir_from(stem_pts(se, send_)), se))
            cl = [cls(x[3]["type"]) if x[3]["type"] != "service" else "r1" for x in arms]
            if (cl.count("r1"), cl.count("r2")) not in PATTERNS:
                continue
            if len(arms) == 4 and (cl[0] != cl[1] or cl[2] != cl[3]):
                continue
            dirs = [x[2] for x in arms]
            if any(dirs[i][0] * dirs[j][0] + dirs[i][1] * dirs[j][1] > 0.9 for i in range(len(dirs)) for j in range(i)):
                continue
            lens = [s_, h["len"] - s_] + [E[x[0]]["len"] for x in stems]
            err, shape = prefab_angle_error(dirs, cl, lens)
            if err > a.max_angle:
                continue
            # bölme
            nid = next_node
            next_node += 1
            B = dict(h, id=len(edges) + len(new_edges), a=nid, pts=B_pts)
            old_b = h["b"]
            h["pts"], h["b"] = A_pts, nid
            B["b"] = old_b
            for e2 in (h, B):
                e2["len"] = round(sum(math.dist(p_, q_) for p_, q_ in zip(e2["pts"], e2["pts"][1:])), 1)
            for j in chosen + others:
                for arm in j["arms"]:
                    if arm["edge"] == hid and arm["end"] == "b":
                        arm["edge"] = B["id"]
            for lk in links:
                for q_ in (0, 2):
                    if lk[q_] == hid and lk[q_ + 1] == "b":
                        lk[q_] = B["id"]
            new_edges.append(B)
            for sid_, send_ in stems:
                se = E[sid_]
                if se["type"] == "ramp_1lane" and sid_ not in hw_armed:
                    se.update(type="r1_city", oneway=False, reverse=False)  # şehir kavşağına bağlanan rampa
                sp_ = stem_pts(se, send_)
                se["pts"] = sp_ if send_ == "a" else sp_[::-1]
                se[send_] = nid
                se["len"] = round(sum(math.dist(p_, q_) for p_, q_ in zip(se["pts"], se["pts"][1:])), 1)
                if len(se["pts"]) > 2 and math.dist(se["pts"][0 if send_ == "a" else -1], se["pts"][1 if send_ == "a" else -2]) > 3:
                    extended[0] += 1
            jarms = [{"edge": hid, "end": "b", "cls": cl[0], "dir": dirs[0]},
                     {"edge": B["id"], "end": "a", "cls": cl[1], "dir": dirs[1]}]
            for (sid_, send_), cc, dd in zip(stems, cl[2:], dirs[2:]):
                jarms.append({"edge": sid_, "end": send_, "cls": cc, "dir": dd})
            chosen.append({"id": len(chosen), "node": nid, "x": c[0], "z": c[1], "shape": shape, "arms": jarms,
                           "forced": True})
            centers.append(c)
            cgrid[(int(c[0] // 50), int(c[1] // 50))].append(c)
            done_edges.add(hid)
            done_edges |= {x[0] for x in stems}
            splits += 1
        edges += new_edges
        made += splits
        if not splits:
            break
    print(f"T kopukluğu onarımı: {made} kavşak (yol bölünerek; {extended[0]} çıkmaz uç uzatıldı)")
    return edges, chosen


def force_hw_tees(edges, chosen, hwj, forks, links, a, reach=60.0):
    """Şehir yolunun tek yönlü otoyol/bölünmüş yol şeridine T olarak değdiği yerler (Darıca D-100, Karamürsel D-130):
    şerit bölünür, çıkış ya da katılma prefabı konur; şehir yolunun ilk ~20 m'si tek yönlü rampa olur, kalanı uç
    bağlantısıyla devam eder. Çıkış/katılma seçimi sapın şeride göre açısından (ileri bakan = çıkış)."""
    from shapely.geometry import Point
    from shapely.strtree import STRtree
    PL = a.hw_prefab_len
    allj = chosen + hwj + forks
    used = {(arm["edge"], arm["end"]) for j in allj for arm in j["arms"]}
    used |= {(l[0], l[1]) for l in links} | {(l[2], l[3]) for l in links}
    comp = comp_finder(edges, allj, links)
    E = {e["id"]: e for e in edges}
    lanes = [e for e in edges if e["type"] == "hw3_oneway" and not e.get("reverse")]
    llines = [LineString(e["pts"]) for e in lanes]
    ltree = STRtree(llines)
    allines = [LineString(e["pts"]) for e in edges]
    atree = STRtree(allines)
    centers = [(j["x"], j["z"]) for j in allj]
    endcount = Counter()
    for e in edges:
        endcount[tuple(round(v, 1) for v in e["pts"][0])] += 1
        endcount[tuple(round(v, 1) for v in e["pts"][-1])] += 1
    next_node = max(max(e["a"], e["b"]) for e in edges) + 1
    done, made, kinds = set(), 0, Counter()
    for e in [e for e in edges if e["type"] in CITY or e["type"] in R2]:
        for end in ("a", "b"):
            if (e["id"], end) in used or e["id"] in done or e["len"] < 30:
                continue
            p = e["pts"][0] if end == "a" else e["pts"][-1]
            P = Point(p)
            dead = endcount[tuple(round(v, 1) for v in p)] == 1
            best = None
            for i in ltree.query(P.buffer(reach if dead else 3.0)):
                h = lanes[i]
                d_ = llines[i].distance(P)
                if h["id"] in done or d_ > (reach if dead else 3.0) or comp(h["id"]) == comp(e["id"]):
                    continue
                s_ = llines[i].project(P)
                Q = llines[i].interpolate(s_)
                if d_ > 3.0:
                    seg = LineString([p, (Q.x, Q.y)])
                    if any(E_id not in (e["id"], h["id"]) and allines[k_].crosses(seg)
                           for k_ in atree.query(seg) for E_id in [edges[k_]["id"]]):
                        continue
                if best is None or d_ < best[0]:
                    best = (d_, i, s_, (Q.x, Q.y))
            if not best:
                continue
            _, i, s_, c = best
            h = lanes[i]
            L = llines[i].length
            if any(math.dist(c, q) < PL + 20 for q in centers):
                continue
            # akış yönü ve sapın tarafı
            A1 = llines[i].interpolate(max(0, s_ - 5))
            A2 = llines[i].interpolate(min(L, s_ + 5))
            tl = math.dist((A1.x, A1.y), (A2.x, A2.y)) or 1
            tx, tz = (A2.x - A1.x) / tl, (A2.y - A1.y) / tl
            ps = e["pts"] if end == "a" else e["pts"][::-1]
            far = ps[min(len(ps) - 1, 1)]
            if math.dist(ps[0], c) > 3.0:
                far = ps[0]
            sd = (far[0] - c[0], far[1] - c[1])
            sl = math.hypot(*sd) or 1
            sd = (sd[0] / sl, sd[1] / sl)
            if sd[0] * (-tz) + sd[1] * tx <= 0.2:
                continue  # sap şeridin solunda: sağdan trafik prefabı yok
            fwd = sd[0] * tx + sd[1] * tz
            # Yarım elmas: aynı şeritte çıkış (s-25) + katılma (s+25), iki rampa şehir yolunda 30 m içeride T
            # kavşakta birleşir → ilçeye hem girilir hem çıkılır (tek çıkış/katılma yönlü tuzak yaratıyordu: depo/garaj
            # karşılıklı erişilemiyor, HQ'da iş çıkmayabiliyordu, 2026-11-23).
            ps_st = [list(c)] + ([list(q) for q in ps] if math.dist(ps[0], c) > 3.0 else [list(q) for q in ps[1:]])
            st_len = sum(math.dist(p_, q_) for p_, q_ in zip(ps_st, ps_st[1:]))
            far_used = (e["id"], "b" if end == "a" else "a") in used
            se_, sm_ = s_ - 25.0, s_ + 25.0
            if (se_ >= PL + 6 and L - sm_ >= PL + 6 and st_len >= 30.0 + (40.5 if far_used else 22.5)
                    and all(math.dist(q, z) >= PL + 20 for q in centers
                            for z in [(llines[i].interpolate(se_).x, llines[i].interpolate(se_).y),
                                      (llines[i].interpolate(sm_).x, llines[i].interpolate(sm_).y)])):
                LS = LineString(ps_st)
                Jp = LS.interpolate(30.0)
                J = (Jp.x, Jp.y)
                if all(math.dist(J, q) >= 42 for q in centers):
                    ce = (llines[i].interpolate(se_).x, llines[i].interpolate(se_).y)
                    cm = (llines[i].interpolate(sm_).x, llines[i].interpolate(sm_).y)

                    def split_lane(hh, cut):
                        hp = hh["pts"]
                        lnh = LineString(hp)
                        sc = lnh.project(Point(cut))
                        acc_, kk = 0.0, 0
                        while kk < len(hp) - 1 and acc_ + math.dist(hp[kk], hp[kk + 1]) < sc:
                            acc_ += math.dist(hp[kk], hp[kk + 1])
                            kk += 1
                        Ap = [list(q) for q in hp[:kk + 1]] + [list(cut)]
                        Bp = [list(cut)] + [list(q) for q in hp[kk + 1:]]
                        if len(Ap) > 2 and math.dist(Ap[-2], cut) < 0.5:
                            Ap.pop(-2)
                        if len(Bp) > 2 and math.dist(Bp[1], cut) < 0.5:
                            Bp.pop(1)
                        nn = max(max(x["a"], x["b"]) for x in edges) + 1
                        Bn = dict(hh, id=len(edges), a=nn, pts=Bp)
                        Bn["b"] = hh["b"]
                        hh["pts"], hh["b"] = Ap, nn
                        for e2 in (hh, Bn):
                            e2["len"] = round(sum(math.dist(p_, q_) for p_, q_ in zip(e2["pts"], e2["pts"][1:])), 1)
                        for j in allj:
                            for arm in j["arms"]:
                                if arm["edge"] == hh["id"] and arm["end"] == "b":
                                    arm["edge"] = Bn["id"]
                        for lk in links:
                            for q_ in (0, 2):
                                if lk[q_] == hh["id"] and lk[q_ + 1] == "b":
                                    lk[q_] = Bn["id"]
                        edges.append(Bn)
                        return Bn, nn
                    Bm, n_m = split_lane(h, cm)      # h = [başlangıç..cm], Bm = [cm..son]
                    Mm, n_e = split_lane(h, ce)      # h = [başlangıç..ce], Mm = [ce..cm]
                    nJ = max(max(x["a"], x["b"]) for x in edges) + 1
                    k_ = 0
                    acc_ = 0.0
                    while k_ < len(ps_st) - 1 and acc_ + math.dist(ps_st[k_], ps_st[k_ + 1]) < 30.0:
                        acc_ += math.dist(ps_st[k_], ps_st[k_ + 1])
                        k_ += 1
                    rest = [list(J)] + ps_st[k_ + 1:]
                    Rx = dict(e, id=len(edges), type="ramp_1lane", oneway=True, reverse=False, prio=4, osm=0,
                              a=n_e, b=nJ, pts=[list(ce), list(J)])
                    Rx["len"] = round(math.dist(ce, J), 1)
                    edges.append(Rx)
                    Rm = dict(e, id=len(edges), type="ramp_1lane", oneway=True, reverse=False, prio=4, osm=0,
                              a=nJ, b=n_m, pts=[list(J), list(cm)])
                    Rm["len"] = round(math.dist(J, cm), 1)
                    edges.append(Rm)
                    e["pts"] = rest if end == "a" else rest[::-1]
                    e[end] = nJ
                    e["len"] = round(sum(math.dist(p_, q_) for p_, q_ in zip(e["pts"], e["pts"][1:])), 1)

                    def dfrom(pp):
                        o_, tg = pp[0], pp[-1]
                        acc2 = 0.0
                        for p_, q_ in zip(pp, pp[1:]):
                            acc2 += math.dist(p_, q_)
                            if acc2 >= 15:
                                tg = q_
                                break
                        dx_, dz_ = tg[0] - o_[0], tg[1] - o_[1]
                        LL = math.hypot(dx_, dz_) or 1
                        return [round(dx_ / LL, 4), round(dz_ / LL, 4)]
                    dirs_ = [dfrom([list(J), list(ce)]), dfrom([list(J), list(cm)]), dfrom(rest)]
                    err_, shp = prefab_angle_error(dirs_, ["r1", "r1", "r1"], [Rx["len"], Rm["len"], e["len"]])
                    chosen.append({"id": len(chosen), "node": nJ, "x": J[0], "z": J[1], "shape": shp if err_ <= a.max_angle else "t",
                                   "forced": True,
                                   "arms": [{"edge": Rx["id"], "end": "b", "cls": "r1", "dir": dirs_[0]},
                                            {"edge": Rm["id"], "end": "a", "cls": "r1", "dir": dirs_[1]},
                                            {"edge": e["id"], "end": end, "cls": cls(e["type"]), "dir": dirs_[2]}]})
                    hwj.append({"id": len(hwj), "node": n_e, "x": ce[0], "z": ce[1], "kind": "exit",
                                "travel": [round(tx, 4), round(tz, 4)], "forced": True,
                                "arms": [{"edge": h["id"], "end": "b", "role": "in"},
                                         {"edge": Mm["id"], "end": "a", "role": "out"},
                                         {"edge": Rx["id"], "end": "a", "role": "ramp"}]})
                    hwj.append({"id": len(hwj), "node": n_m, "x": cm[0], "z": cm[1], "kind": "merge",
                                "travel": [round(tx, 4), round(tz, 4)], "forced": True,
                                "arms": [{"edge": Mm["id"], "end": "b", "role": "in"},
                                         {"edge": Bm["id"], "end": "a", "role": "out"},
                                         {"edge": Rm["id"], "end": "b", "role": "ramp"}]})
                    centers += [ce, cm, J]
                    done |= {h["id"], Bm["id"], Mm["id"], e["id"]}
                    used.add((e["id"], end))
                    made += 1
                    kinds["yarım elmas"] += 1
                    continue
            kind = "exit" if fwd > 0.05 or (abs(fwd) <= 0.05 and made % 2 == 0) else "merge"
            if kind == "exit" and (s_ < PL + 6 or L - s_ < 12):
                kind = "merge"
            if kind == "merge" and (L - s_ < PL + 6 or s_ < 12):
                continue
            # şeridi böl
            pts = h["pts"]
            acc, k = 0.0, 0
            while k < len(pts) - 1 and acc + math.dist(pts[k], pts[k + 1]) < s_:
                acc += math.dist(pts[k], pts[k + 1])
                k += 1
            A_pts = [list(q) for q in pts[:k + 1]] + [list(c)]
            B_pts = [list(c)] + [list(q) for q in pts[k + 1:]]
            if math.dist(A_pts[-2], c) < 0.5:
                A_pts.pop(-2)
            if math.dist(B_pts[1], c) < 0.5:
                B_pts.pop(1)
            if len(A_pts) < 2 or len(B_pts) < 2:
                continue
            nid, mid_n = next_node, next_node + 1
            next_node += 2
            B = dict(h, id=len(edges), a=nid, pts=B_pts)
            B["b"] = h["b"]
            h["pts"], h["b"] = A_pts, nid
            for e2 in (h, B):
                e2["len"] = round(sum(math.dist(p_, q_) for p_, q_ in zip(e2["pts"], e2["pts"][1:])), 1)
            for j in allj:
                for arm in j["arms"]:
                    if arm["edge"] == h["id"] and arm["end"] == "b":
                        arm["edge"] = B["id"]
            for lk in links:
                for q_ in (0, 2):
                    if lk[q_] == h["id"] and lk[q_ + 1] == "b":
                        lk[q_] = B["id"]
            edges.append(B)
            # sap: c'den başlayan nokta dizisi; ilk 20 m rampa
            sp = [list(c)] + ([list(q) for q in ps] if math.dist(ps[0], c) > 3.0 else [list(q) for q in ps[1:]])
            acc, k = 0.0, 0
            while k < len(sp) - 1 and acc + math.dist(sp[k], sp[k + 1]) < 20.0:
                acc += math.dist(sp[k], sp[k + 1])
                k += 1
            t_ = (20.0 - acc) / (math.dist(sp[k], sp[k + 1]) or 1)
            m = [sp[k][0] + (sp[k + 1][0] - sp[k][0]) * t_, sp[k][1] + (sp[k + 1][1] - sp[k][1]) * t_]
            ramp_pts = sp[:k + 1] + [m]
            rest_pts = [m] + sp[k + 1:]
            if kind == "merge":
                ramp_pts = ramp_pts[::-1]
            R = dict(e, id=len(edges), type="ramp_1lane", oneway=True, reverse=False, prio=4,
                     a=(nid if kind == "exit" else mid_n), b=(mid_n if kind == "exit" else nid), pts=ramp_pts)
            R["len"] = round(sum(math.dist(p_, q_) for p_, q_ in zip(R["pts"], R["pts"][1:])), 1)
            edges.append(R)
            # kalan şehir yolu: c tarafındaki ucu m'ye taşınır
            e["pts"] = rest_pts if end == "a" else rest_pts[::-1]
            e[end] = mid_n
            e["len"] = round(sum(math.dist(p_, q_) for p_, q_ in zip(e["pts"], e["pts"][1:])), 1)
            links.append([R["id"], "b" if kind == "exit" else "a", e["id"], end])
            hwj.append({"id": len(hwj), "node": nid, "x": c[0], "z": c[1], "kind": kind,
                        "travel": [round(tx, 4), round(tz, 4)], "forced": True,
                        "arms": [{"edge": h["id"], "end": "b", "role": "in"},
                                 {"edge": B["id"], "end": "a", "role": "out"},
                                 {"edge": R["id"], "end": "a" if kind == "exit" else "b", "role": "ramp"}]})
            centers.append(c)
            done |= {h["id"], B["id"], e["id"]}
            used.add((e["id"], end))
            made += 1
            kinds[kind] += 1
    print(f"şehir yolu-otoyol şeridi T onarımı: {made} ({dict(kinds)})")
    return edges


LINK_REJ = ROOT / "data" / "processed" / "link_rejects.json"


def filter_links(edges, links, use_rejects=True):
    """C#'ın uç birleştirme güvenlik kuralının aynısı (Program.cs 2b): uçlar ≤ 6,5 m, yollar ≥ 3 m kalır, ≥105° dönüş
    yok; ayrıca önceki C# derlemesinde başarısız olan birleşim noktaları (link_rejects.json, birikimli). Doğrulama ve
    depo/garaj yerleşimi oyundaki gerçek bağlantılarla yapılsın diye."""
    rej = set()
    if use_rejects and LINK_REJ.exists():
        rej = {(int(round(x * 10)), int(round(z * 10))) for x, z in json.loads(LINK_REJ.read_text())}
    E = {e["id"]: e for e in edges}

    def info(e, end):
        ps = e["pts"] if end == "b" else e["pts"][::-1]  # ps[-1] = uç
        tip = ps[-1]
        other = None
        for q in reversed(ps[:-1]):
            if math.dist(q, tip) > 3.0:
                other = q
                break
        return tip, other
    keep, drop = [], Counter()
    for l in links:
        e1, e2 = E.get(l[0]), E.get(l[2])
        if e1 is None or e2 is None:
            drop["kenar yok"] += 1
            continue
        p1, o1 = info(e1, l[1])
        p2, o2 = info(e2, l[3])
        key = lambda q: (int(round(q[0] * 10)), int(round(q[1] * 10)))  # C# 0,1 m'ye yuvarlıyor
        if key(p1) in rej or key(p2) in rej:
            drop["C# reddi"] += 1
            continue
        if o1 is None or o2 is None or math.dist(p1, p2) > 6.5 or math.dist(o1, p2) < 3 or math.dist(o2, p1) < 3:
            drop["kısa/uzak"] += 1
            continue
        # birleşimden iki yola doğru (yönden bağımsız): düz devam ≈ -1, saç tokası > 0.25 (C#: dot(-v1, v2) < -0.25)
        v1 = (o1[0] - p1[0], o1[1] - p1[1])
        v2 = (o2[0] - p2[0], o2[1] - p2[1])
        n1, n2 = math.hypot(*v1) or 1, math.hypot(*v2) or 1
        if (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2) > 0.25:
            drop["saç tokası " + e1["type"][:4] + ("(u)" if e1.get("uturn") else "(c)" if e1.get("connector") else "") + "/" + e2["type"][:4] + ("(u)" if e2.get("uturn") else "(c)" if e2.get("connector") else "")] += 1
            continue
        keep.append(l)
    links[:] = keep
    print(f"uç bağlantısı süzgeci: {len(keep)} kaldı, atılan {dict(drop)}")
    return links


def bezier_pts(P, t0, Q, t1, step=5.0):
    """P'den t0 teğetiyle çıkıp Q'ya t1 teğetiyle varan kübik eğri noktaları (uçlarda yön sürekliliği)."""
    d = math.dist(P, Q)
    k = max(6.0, d / 2.5)
    B1 = (P[0] + t0[0] * k, P[1] + t0[1] * k)
    B2 = (Q[0] - t1[0] * k, Q[1] - t1[1] * k)
    n = max(2, int((d + 2 * k) // step))
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append([u ** 3 * P[0] + 3 * u * u * t * B1[0] + 3 * u * t * t * B2[0] + t ** 3 * Q[0],
                    u ** 3 * P[1] + 3 * u * u * t * B1[1] + 3 * u * t * t * B2[1] + t ** 3 * Q[1]])
    out[0], out[-1] = list(P), list(Q)
    return out


def thin_curve(pts, end_keep=10.0, mid_step=15.0):
    """Çıktı için eğriyi seyrelt: uçlarda 5 m'lik noktalar (birleşim yönü), ortada ~15 m (editör segment bütçesi)."""
    L = [0.0]
    for p_, q_ in zip(pts, pts[1:]):
        L.append(L[-1] + math.dist(p_, q_))
    tot, out, last = L[-1], [pts[0]], 0.0
    for p_, l_ in zip(pts[1:-1], L[1:-1]):
        if l_ <= end_keep or tot - l_ <= end_keep or l_ - last >= mid_step:
            out.append(p_)
            last = l_
    out.append(pts[-1])
    return out


def smooth_enough(pts, t0, t1, max_deg=35.0):
    """5 m örneklenmiş eğride ardışık parçalar ve uç teğetleri arasında en çok max_deg dönüş."""
    c = math.cos(math.radians(max_deg))
    dirs = [t0]
    for p_, q_ in zip(pts, pts[1:]):
        L = math.dist(p_, q_)
        if L < 1e-6:
            continue
        dirs.append(((q_[0] - p_[0]) / L, (q_[1] - p_[1]) / L))
    dirs.append(t1)
    return all(u[0] * v[0] + u[1] * v[1] >= c for u, v in zip(dirs, dirs[1:]))


def end_tangent(e, end):
    """Kenarın ucundaki, kenarın geometri yönündeki (a→b) birim teğet."""
    ps = e["pts"]
    a_, b_ = (ps[0], ps[1]) if end == "a" else (ps[-2], ps[-1])
    L = math.dist(a_, b_) or 1
    return ((b_[0] - a_[0]) / L, (b_[1] - a_[1]) / L)


def uturn_links(edges, junctions, links, reach=120.0, skip_boxes=()):
    """Boşta BİTEN tek yönlü yolu (çıkış rampası, harita sınırında biten şerit) yakındaki boşta BAŞLAYAN tek yönlü
    yola (katılma rampası, karşı şerit) kısa bir tek yönlü bağlantı rampasıyla bağlar: kavşakta çıkıp geri katılmak
    ve sınırda dönmek mümkün olur. Önceden 366 çıkış rampası çıkmazdı; otoyolda dönüş yoktu, depolar yönlü ağda
    birbirine ulaşamıyordu (2026-11-23)."""
    from shapely.geometry import Point
    from shapely.strtree import STRtree
    OWT = lambda t: t == "ramp_1lane" or (t.startswith("hw") and t.endswith("_oneway"))
    used = {(a["edge"], a["end"]) for j in junctions for a in j["arms"]}
    used |= {(l[0], l[1]) for l in links} | {(l[2], l[3]) for l in links}
    outs, ins = [], []
    inbox = lambda p: any(b["x0"] <= p[0] <= b["x1"] and b["z0"] <= p[1] <= b["z1"] for b in skip_boxes)
    for e in edges:
        if not OWT(e["type"]):
            continue
        if skip_boxes and (inbox(e["pts"][0]) or inbox(e["pts"][-1])):
            continue
        s_, t_ = ("b", "a") if e.get("reverse") else ("a", "b")
        if (e["id"], t_) not in used:
            outs.append((e, t_))
        if (e["id"], s_) not in used:
            ins.append((e, s_))
    pt = lambda e, end: tuple(e["pts"][0] if end == "a" else e["pts"][-1])
    itree = STRtree([Point(pt(e, end)) for e, end in ins])
    allines = [LineString(e["pts"]) for e in edges]
    atree = STRtree(allines)
    cand = []
    for e, end in outs:
        P = pt(e, end)
        for k in itree.query(Point(P).buffer(reach)):
            f, fend = ins[k]
            if f["id"] == e["id"]:
                continue
            Q = pt(f, fend)
            d = math.dist(P, Q)
            if d > reach:
                continue
            seg = LineString([P, Q])
            cross = sum(1 for q in atree.query(seg) if allines[q].distance(Point(P)) > 1 and allines[q].distance(Point(Q)) > 1
                        and allines[q].intersects(seg))
            if cross and d > 40:
                continue
            ta = end_tangent(e, end)
            tb = end_tangent(f, fend)
            if e.get("reverse"):
                ta = (-ta[0], -ta[1])
            if f.get("reverse"):
                tb = (-tb[0], -tb[1])
            if d >= 3.0:
                npts = bezier_pts(P, ta, Q, tb)
                if not smooth_enough(npts, ta, tb):
                    continue  # tır için fazla keskin (C#'ta saç tokası birleşimi)
            cand.append((d + 50 * cross, e["id"], end, f["id"], fend, P, Q))
    cand.sort()
    taken, made = set(), 0
    nn = max(max(x["a"], x["b"]) for x in edges) + 1
    for d, eid, end, fid, fend, P, Q in cand:
        if (eid, end) in taken or (fid, fend) in taken:
            continue
        taken |= {(eid, end), (fid, fend)}
        if math.dist(P, Q) < 3.0:
            links.append([eid, end, fid, fend])
        else:
            Eo = next(x for x in edges if x["id"] == eid)
            Ei = next(x for x in edges if x["id"] == fid)
            t0 = end_tangent(Eo, end)   # boşta biten: trafik bu yönde gelir
            if Eo.get("reverse"):
                t0 = (-t0[0], -t0[1])
            t1 = end_tangent(Ei, fend)  # boşta başlayan: trafik bu yönde gider
            if Ei.get("reverse"):
                t1 = (-t1[0], -t1[1])
            npts = thin_curve(bezier_pts(P, t0, Q, t1))
            L = sum(math.dist(p_, q_) for p_, q_ in zip(npts, npts[1:]))
            edges.append({"id": len(edges), "osm": 0, "hw": "motorway_link", "type": "ramp_1lane", "prio": 4,
                          "oneway": True, "reverse": False, "a": nn, "b": nn + 1, "pts": npts, "len": round(L, 1),
                          "uturn": True})
            nn += 2
            links.append([eid, end, len(edges) - 1, "a"])
            links.append([len(edges) - 1, "b", fid, fend])
        made += 1
    print(f"dönüş bağlantısı: {made} (boşta biten {len(outs)}, boşta başlayan {len(ins)} tek yönlü uç)")


def fix_city_ramp_arms(edges, chosen, others, links, cut_at=22.0):
    """Şehir kavşağı prefabının kolu tek yönlü rampa olamaz: oyun "[traffic] Unable to determine output road lane ...
    Failed to register Prefab item" verip kavşağı trafikten çıkarıyordu (önizleme logu, 2026-11-23). Rampanın kavşak
    tarafındaki ilk cut_at m'si iki yönlü şehir yoluna çevrilir; kalan rampa bu parçaya yol-yol bağlantısıyla eklenir."""
    made, conv, left = 0, 0, 0
    drop_j = set()
    for _pass in range(3):
        E = {e["id"]: e for e in edges}
        prefab_ends = {(a_["edge"], a_["end"]) for j in chosen + others for a_ in j["arms"]}
        changed = False
        for j in chosen:
            for arm in j["arms"]:
                e = E[arm["edge"]]
                if e["type"] != "ramp_1lane":
                    continue
                far = "b" if arm["end"] == "a" else "a"
                if e["len"] < cut_at + 5:
                    if (e["id"], far) not in prefab_ends:
                        e.update(type="r1_city", oneway=False, reverse=False)
                        conv += 1
                        changed = True
                    else:
                        left += 1  # kavşak tutulur (kaldırınca otoyol-şehir bağlantısı kopuyordu)
                    continue
                ps = e["pts"] if arm["end"] == "a" else e["pts"][::-1]  # kavşaktan uzağa
                acc, k = 0.0, 0
                while k < len(ps) - 1 and acc + math.dist(ps[k], ps[k + 1]) < cut_at:
                    acc += math.dist(ps[k], ps[k + 1])
                    k += 1
                t = (cut_at - acc) / (math.dist(ps[k], ps[k + 1]) or 1)
                m = [ps[k][0] + (ps[k + 1][0] - ps[k][0]) * t, ps[k][1] + (ps[k + 1][1] - ps[k][1]) * t]
                near = [list(q) for q in ps[:k + 1]] + [m]
                rest = [m] + [list(q) for q in ps[k + 1:]]
                if len(rest) > 2 and math.dist(rest[1], m) < 0.5:
                    rest.pop(1)
                nn = max(max(x["a"], x["b"]) for x in edges) + 1
                R = dict(e, id=len(edges))
                if arm["end"] == "a":       # e = [kavşak .. m] (geometri a→b korunur), R = [m .. eski b]
                    e["pts"], R["pts"] = near, rest
                    R["a"], R["b"] = nn, e["b"]
                    e["b"] = nn
                    moved, lk_new = "b", [R["id"], "a", e["id"], "b"]
                else:                       # kavşak b'de: e = [m .. b], R = [eski a .. m]
                    e["pts"], R["pts"] = near[::-1], rest[::-1]
                    R["a"], R["b"] = e["a"], nn
                    e["a"] = nn
                    moved, lk_new = "a", [R["id"], "b", e["id"], "a"]
                for x in (e, R):
                    x["len"] = round(sum(math.dist(p_, q_) for p_, q_ in zip(x["pts"], x["pts"][1:])), 1)
                for jj in chosen + others:
                    for a_ in jj["arms"]:
                        if a_["edge"] == e["id"] and a_["end"] == moved:
                            a_["edge"] = R["id"]
                for lk in links:
                    for q_ in (0, 2):
                        if lk[q_] == e["id"] and lk[q_ + 1] == moved:
                            lk[q_] = R["id"]
                e.update(type="r1_city", oneway=False, reverse=False)
                edges.append(R)
                links.append(lk_new)
                E[R["id"]] = R
                made += 1
                changed = True
        if not changed:
            break
    # bölünemeyecek kadar kısa, öbür ucu otoyol prefabında olan rampa: kavşak kaldırılır (hatalı kavşak yerine kopukluk;
    # bağlantı denetimi sonra yapılır)
    if drop_j:
        keep = [j for j in chosen if id(j) not in drop_j]
        chosen[:] = keep
        for i, j in enumerate(chosen):
            j["id"] = i
    print(f"şehir kavşağı rampa kolu: {made} bölündü, {conv} iki yönlüye çevrildi, {left} kısa kaldı")


def heal_links(edges, junctions, links):
    """Prefabı sonradan atılan düğümlerde (şerit eşlemede bırakılan otoyol kavşağı, otoyol rampalı şehir kavşağı)
    kollar boşta kalıyordu: otoyol o noktada kopuyor, ilçeler ayrı ağlara bölünüyordu (2026-11-23). Aynı düğümde
    boşta kalan uyumlu yol uçları en düz çift olarak C#'ta birleştirilir (road_links). Yalnız bağlantılarla oluşan
    halka kurulmaz (editör "inconsistent linkage")."""
    used = {(a["edge"], a["end"]) for j in junctions for a in j["arms"]}
    used |= {(l[0], l[1]) for l in links} | {(l[2], l[3]) for l in links}
    par = {}

    def f(x):
        par.setdefault(x, x)
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    for l in links:
        par[f(l[0])] = f(l[2])
    E = {e["id"]: e for e in edges}
    # boşta uçlar konuma göre (3 m) kümelenir: kesişim kümelemesi/sadeleştirme sonrası aynı kavşaktaki uçlar farklı
    # düğüm kimliğinde 1-3 m arayla kalabiliyor (D-130 Gölcük-Karamürsel otoyol şeridi böyle kopuktu, 2026-11-23)
    fe = [(e["id"], end, e["pts"][0] if end == "a" else e["pts"][-1]) for e in edges for end in ("a", "b")
          if (e["id"], end) not in used]
    cell = defaultdict(list)
    for i, (_, _, p) in enumerate(fe):
        cell[(int(p[0] // 6), int(p[1] // 6))].append(i)
    cp = list(range(len(fe)))

    def cf(x):
        while cp[x] != x:
            cp[x] = cp[cp[x]]
            x = cp[x]
        return x
    for i, (_, _, p) in enumerate(fe):
        gx, gz = int(p[0] // 6), int(p[1] // 6)
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for j in cell[(gx + dx, gz + dz)]:
                    if j != i and math.dist(p, fe[j][2]) < 6.0:
                        cp[cf(i)] = cf(j)
    free = defaultdict(list)
    for i, (eid, end, _) in enumerate(fe):
        free[cf(i)].append((eid, end))

    def grp(t):
        return "ow" if t.startswith("hw") and "oneway" in t or t == "ramp_1lane" else                ("tw" if t in CITY or t in R2 or t == "service" else None)

    def d(e, end):
        ps = e["pts"] if end == "a" else e["pts"][::-1]
        q = ps[min(len(ps) - 1, 1)]
        L = math.dist(ps[0], q) or 1
        return ((q[0] - ps[0][0]) / L, (q[1] - ps[0][1]) / L)

    new = []
    for n, ends in free.items():
        if len(ends) < 2:
            continue
        pairs = []
        for i in range(len(ends)):
            for j in range(i + 1, len(ends)):
                x, y = ends[i], ends[j]
                ex, ey = E[x[0]], E[y[0]]
                if x[0] == y[0]:
                    continue
                gx, gy = grp(ex["type"]), grp(ey["type"])
                if gx is None or gy is None:
                    continue
                if gx == "ow" and gy == "ow":
                    if {x[1], y[1]} != {"a", "b"} or ex.get("reverse") or ey.get("reverse"):
                        continue
                elif gx != gy and "hw" in (ex["type"][:2], ey["type"][:2]):
                    continue  # otoyol şeridi yalnız otoyol şeridi/rampayla
                dx, dy = d(ex, x[1]), d(ey, y[1])
                pairs.append((dx[0] * dy[0] + dx[1] * dy[1], x, y))
        pairs.sort(key=lambda t: t[0])
        done = set()
        for dot, x, y in pairs:
            if x in done or y in done or (len(ends) > 2 and dot > -0.3) or dot > 0.25:
                continue  # dot > 0.25: ~105°'den keskin dönüş (saç tokası) → C#'ta bozuk eğri, yığın taşması
            if f(x[0]) == f(y[0]):
                continue
            par[f(x[0])] = f(y[0])
            done |= {x, y}
            new.append([x[0], x[1], y[0], y[1]])
    print(f"boşta kalan uç onarımı: {len(new)} bağlantı")
    return list(links) + new


def main_component(edges, junctions, links):
    """Oyunda bağlı olan en büyük yol ağının kenar kimlikleri (prefab kolları + uç bağlantıları ile birleşim)."""
    par = {}

    def f(x):
        par.setdefault(x, x)
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    for j in junctions:
        k = ("j", j["id"], j.get("kind", "c"))
        for arm in j["arms"]:
            par[f(("e", arm["edge"]))] = f(k)
    for l in links:
        ra, rb = f(("e", l[0])), f(("e", l[2]))
        if ra != rb:
            par[ra] = rb
    size = Counter()
    for e in edges:
        size[f(("e", e["id"]))] += e["len"]
    best = size.most_common(1)[0][0]
    return {e["id"] for e in edges if f(("e", e["id"])) == best}


def place_garages(edges, chosen, depots, S, links=(), along=26.7, need=78.0, clear=42.0, allowed=None, cities=()):
    """Her şehre bir oyuncu garajı (garage_medium_01): yeni profilde merkez (HQ) şehri seçimi ve tırın başlangıç
    yeri garajlardan gelir; garajsız haritada şehir listesi boş kalır ve tır harita dışında (boşlukta) başlar.
    Prefabın iki düğümü yol boyunca 26,7 m aralıklı (yanal 22,7 m kayma C# tarafında); gövde yolun iki yanına
    yayılır → her iki yanda boşluk aranır. Kenar depo gibi ikiye bölünür."""
    from shapely.geometry import Point
    from shapely.strtree import STRtree
    rects = city_grid(edges, S)
    jpts = [(j["x"], j["z"]) for j in chosen]
    dpts = [tuple(d["body"]) for d in depots]
    lines = [LineString(e["pts"]) for e in edges]
    ltree = STRtree(lines)
    next_node = max(max(e["a"], e["b"]) for e in edges) + 1
    out, done = [], set()
    # ilçe merkezine en yakın uygun yol önce (garaj = oyuncunun başladığı yer; kırsalda başlamasın)
    centers = [tuple(c["center"]) for c in cities if c.get("center")]

    def center_dist(e):
        return min((min(math.dist(p_, c_) for p_ in e["pts"][::max(1, len(e["pts"]) // 8)] + [e["pts"][-1]])
                    for c_ in centers), default=0.0)
    # HQ şehrinde depo yoksa yeni profilde ilk iş üretilemez ("No valid offers found for player's HQ city" → oyun
    # kapanır): garaj yalnız depolu şehirlere. Önce rahat ölçüt (78 m düz parça), sonra sıkışık merkezler için 58 m.
    with_depot = {d["city"] for d in depots}
    order = sorted(edges, key=lambda e: (center_dist(e), -e["len"]))
    for need_, clear_, ed in [(need, clear, e) for e in order] + [(58.0, 30.0, e) for e in order]:
        if ed["type"] not in ("r1_city", "r1_city_narrow") or ed["oneway"]:
            continue
        if allowed is not None and ed["id"] not in allowed:
            continue
        pts = ed["pts"]
        for i in range(len(pts) - 1):
            P, Q = pts[i], pts[i + 1]
            L = math.dist(P, Q)
            if L < need_:
                continue
            mid = ((P[0] + Q[0]) / 2, (P[1] + Q[1]) / 2)
            city = grid_city(rects, mid)
            if city in done or city not in with_depot:
                continue
            if any(math.dist(mid, j) < 70 for j in jpts) or any(math.dist(mid, d) < 160 for d in dpts):
                continue
            ux, uz = (Q[0] - P[0]) / L, (Q[1] - P[1]) / L
            ok = True
            for sgn in (1, -1):
                for k in (-20, 0, 20):
                    body = Point(mid[0] + ux * k - uz * 40 * sgn, mid[1] + uz * k + ux * 40 * sgn)
                    if any(q_ != ed["id"] and lines[q_].distance(body) < clear_ for q_ in ltree.query(body.buffer(clear_))):
                        ok = False
            probe = [(mid[0] + ux * k - uz * 60 * sg, mid[1] + uz * k + ux * 60 * sg) for k in (-40, 0, 40) for sg in (1, -1)]
            if not ok or any(grid_city(rects, q_) != city for q_ in probe + [mid]):
                continue
            h = along / 2
            n0 = (round(mid[0] - ux * h, 3), round(mid[1] - uz * h, 3))
            n1 = (round(mid[0] + ux * h, 3), round(mid[1] + uz * h, 3))
            ida, idb = next_node, next_node + 1
            next_node += 2
            B = dict(ed, id=len(edges), a=idb, pts=[list(n1)] + [list(p_) for p_ in pts[i + 1:]])
            ed["pts"] = [list(p_) for p_ in pts[:i + 1]] + [list(n0)]
            ed["b"] = ida
            for e2 in (ed, B):
                e2["len"] = round(sum(math.dist(p_, q_) for p_, q_ in zip(e2["pts"], e2["pts"][1:])), 1)
            for j in chosen:
                for arm in j["arms"]:
                    if arm["edge"] == ed["id"] and arm["end"] == "b":
                        arm["edge"] = B["id"]
            for lk in links:
                for q_ in (0, 2):
                    if lk[q_] == ed["id"] and lk[q_ + 1] == "b":
                        lk[q_] = B["id"]
            for d in depots + out:
                for arm in (d["arm0"], d["arm1"]):
                    if arm["edge"] == ed["id"] and arm["end"] == "b":
                        arm["edge"] = B["id"]
            edges.append(B)
            lines.append(LineString(B["pts"]))
            done.add(city)
            out.append({"id": len(out), "city": city, "n0": list(n0), "n1": list(n1), "mid": [round(mid[0], 2), round(mid[1], 2)],
                        "arm0": {"edge": ed["id"], "end": "b"}, "arm1": {"edge": B["id"], "end": "a"}})
            break
    missing = sorted(set(CITY_TOKENS.values()) - done)
    print(f"garaj: {len(out)} şehir; garajsız: {missing}")
    return out


# Türkiye tabela şablonları (Road to the Black Sea, def/sign/templates.mod_tr.sii); metin kimlikleri oyunun kendi
# Edirne tabelalarından okundu (mapgen signscan). Öznitelik 0 = metin.
SIGN_CITY = {"model": "dlc_blke_400", "template": "sign_templ.tr_1", "area": "ml2",
             "name": 105644032, "pop": 1730019327, "alt": 1241776128}
SIGN_PLACE = {"model": "dlc_blke_439", "template": "sign_templ.tr_150", "area": "ml2", "name": 996016128}
CITY_NAMES = {"gebze": "Gebze", "darica": "Darıca", "cayirova": "Çayırova", "dilovasi": "Dilovası", "izmit": "İzmit",
              "korfez": "Körfez", "derince": "Derince", "golcuk": "Gölcük", "karamursel": "Karamürsel",
              "kandira": "Kandıra", "kartepe": "Kartepe", "basiskele": "Başiskele"}
# yaklaşık nüfus ve merkez rakımı (m) – tabela metni
CITY_SIGN = {"gebze": (400000, 120), "darica": (220000, 40), "cayirova": (150000, 90), "dilovasi": (50000, 30),
             "izmit": (370000, 10), "korfez": (180000, 20), "derince": (150000, 20), "golcuk": (175000, 5),
             "karamursel": (60000, 5), "kandira": (55000, 60), "kartepe": (135000, 150), "basiskele": (120000, 30)}


def tr_upper(t):
    return t.replace("i", "İ").replace("ı", "I").upper()


def place_signs(edges, items, cities, S, main_edges, max_place=650):
    """Şehir giriş tabelaları (ad, nüfus, rakım) ve mahalle/köy ad tabelaları. Tabela yolun trafik yönüne göre sağına
    konur, ön yüzü (+Z) gelen sürücüye bakar (oyun verisinden ölçüldü). Çıktı: graph["signs"]."""
    from shapely.geometry import Point
    from shapely.strtree import STRtree
    jp = []
    for it in items:
        if "x" in it:
            jp.append((it["x"], it["z"]))
        elif "mid" in it:
            jp.append(tuple(it["mid"]))
        elif "n0" in it:
            jp.append(tuple(it["n0"]))
    jgrid = defaultdict(list)
    for p in jp:
        jgrid[(int(p[0] // 50), int(p[1] // 50))].append(p)

    def near_j(p, r):
        gx, gz = int(p[0] // 50), int(p[1] // 50)
        return any(math.dist(p, q) < r for dx in (-1, 0, 1) for dz in (-1, 0, 1) for q in jgrid[(gx + dx, gz + dz)])
    TW = [e for e in edges if not e["oneway"] and (e["type"] in CITY or e["type"] in R2)]
    out, sgrid = [], defaultdict(list)

    def add(p, d, kind, texts, model, tmpl, gap):
        off = 11.0 if kind == "r2" else 7.0
        rx, rz = -d[1], d[0]
        q = (p[0] + rx * off, p[1] + rz * off)
        gx, gz = int(q[0] // 100), int(q[1] // 100)
        if any(math.dist(q, w) < gap for dx in (-1, 0, 1) for dz in (-1, 0, 1) for w in sgrid[(gx + dx, gz + dz)]):
            return False
        sgrid[(gx, gz)].append(q)
        out.append({"x": round(q[0], 2), "z": round(q[1], 2), "dir": [round(d[0], 4), round(d[1], 4)],
                    "model": model, "template": tmpl, "texts": texts})
        return True

    # 1) şehir girişleri: merkezden R uzaklıkta yolun çemberi kestiği noktada, merkeze doğru giden trafiğe
    n_city = 0
    for c in cities:
        if not c.get("center") or c["token"] not in CITY_SIGN:
            continue
        pop, alt = CITY_SIGN[c["token"]]
        R = 1100.0 if pop >= 250000 else (850.0 if pop >= 120000 else 600.0)
        cx, cz = c["center"]
        cand = []
        for e in TW:
            ps = e["pts"]
            for P, Q in zip(ps, ps[1:]):
                dp, dq = math.dist(P, (cx, cz)), math.dist(Q, (cx, cz))
                if (dp - R) * (dq - R) > 0 or abs(dp - dq) < 1e-6:
                    continue
                t = (R - dp) / (dq - dp)
                X = (P[0] + (Q[0] - P[0]) * t, P[1] + (Q[1] - P[1]) * t)
                inner, outer = (Q, P) if dq < dp else (P, Q)
                L = math.dist(inner, outer) or 1
                d = ((inner[0] - outer[0]) / L, (inner[1] - outer[1]) / L)
                if near_j(X, 30):
                    continue
                ang = math.atan2(X[1] - cz, X[0] - cx)
                cand.append((e["prio"] + (0 if e["id"] in main_edges else 3), ang, X, d, "r2" if e["type"] in R2 else "r1"))
        cand.sort(key=lambda x: x[0])
        used = []
        for pr, ang, X, d, kind in cand:
            if len(used) >= 4:
                break
            if any(abs((ang - u + math.pi) % (2 * math.pi) - math.pi) < math.radians(70) for u in used):
                continue
            texts = [[SIGN_CITY["name"], SIGN_CITY["area"], tr_upper(CITY_NAMES[c["token"]])],
                     [SIGN_CITY["pop"], SIGN_CITY["area"], f"{pop:,}".replace(",", ".")],
                     [SIGN_CITY["alt"], SIGN_CITY["area"], str(alt)]]
            if add(X, d, kind, texts, SIGN_CITY["model"], SIGN_CITY["template"], 40):
                used.append(ang)
                n_city += 1
    # 2) mahalle / köy adları (OSM place=suburb/neighbourhood/quarter/village): en yakın iki yönlü yolun kenarına
    lines = [LineString(e["pts"]) for e in TW]
    tree = STRtree(lines)
    g = lambda x, y: ((x - E0) / S, -(y - N0) / S)
    seen, places = set(), []
    for f in (RAW / "places.json", RAW / "kocaeli" / "places.json"):
        if not f.exists():
            continue
        for el in json.loads(f.read_text(encoding="utf-8"))["elements"]:
            t = el.get("tags", {})
            if t.get("place") not in ("suburb", "neighbourhood", "quarter", "village") or not t.get("name"):
                continue
            if el["id"] in seen or "lat" not in el:
                continue
            seen.add(el["id"])
            places.append((g(*T.transform(el["lon"], el["lat"])), t["name"], t["place"]))
    # bilinen yerler (AVM, hastane, belediye, meydan): ad tabelası
    import landmarks as lmmod
    for kind, name, ux_, uy_, lid in lmmod.load(lambda lo, la: T.transform(lo, la)):
        places.append((g(ux_, uy_), name, "landmark"))
    rects = city_grid(edges, S)
    n_place = 0
    for P, name, kind in sorted(places, key=lambda x: {"landmark": 0, "village": 2}.get(x[2], 1)):
        if n_place >= max_place:
            break
        if not any(r["x0"] <= P[0] <= r["x1"] and r["z0"] <= P[1] <= r["z1"] for r in rects):
            continue  # il dışı (ör. İstanbul köyleri)
        i = tree.nearest(Point(P))
        ln = lines[i]
        if ln.distance(Point(P)) > 150:
            continue
        s_ = ln.project(Point(P))
        X = ln.interpolate(s_)
        X2 = ln.interpolate(min(ln.length, s_ + 3.0))
        X1 = ln.interpolate(max(0.0, s_ - 3.0))
        L = X1.distance(X2) or 1
        d = ((X2.x - X1.x) / L, (X2.y - X1.y) / L)
        # yer adının bulunduğu taraf yolun sağı olsun (tabela mahalleye bakan yanda)
        if (P[0] - X.x) * (-d[1]) + (P[1] - X.y) * d[0] < 0:
            d = (-d[0], -d[1])
        if near_j((X.x, X.y), 28):
            continue
        nm = name
        for a_, b_ in (("Alışveriş Merkezi", "AVM"), ("Devlet Hastanesi", "Devlet Hast."), ("Hastanesi", "Hast."),
                       ("Belediyesi", "Bld."), ("Eğitim ve Araştırma", "EAH"), ("Meydanı", "Myd.")):
            if len(nm) > 22:
                nm = nm.replace(a_, b_)
        if len(nm) > 22:
            nm = nm[:22].rsplit(" ", 1)[0]
        if add((X.x, X.y), d, "r2" if TW[i]["type"] in R2 else "r1",
               [[SIGN_PLACE["name"], SIGN_PLACE["area"], tr_upper(nm)]], SIGN_PLACE["model"], SIGN_PLACE["template"], 60):
            n_place += 1
    print(f"tabela: {n_city} şehir girişi, {n_place} mahalle/köy adı")
    return out


if __name__ == "__main__":
    main()
