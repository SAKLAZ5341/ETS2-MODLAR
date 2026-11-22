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
cls = lambda t: "r2" if t in R2 else ("r1" if t in CITY else None)
# izin verilen (r1 sayısı, r2 sayısı) desenleri -> prefab var
PATTERNS = {(3, 0), (2, 1), (1, 2), (0, 3), (4, 0), (0, 4)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=CFG["game"]["city_scale_divisor"])
    ap.add_argument("--simplify-m", type=float, default=10.0)
    ap.add_argument("--min-seg", type=float, default=8.0)
    ap.add_argument("--exclude", nargs="*", default=["service", "living_street"])
    ap.add_argument("--prefab-radius", type=float, default=18.0, help="prefab merkez-düğüm mesafesi (oyun m)")
    ap.add_argument("--min-arm", type=float, default=24.0, help="kol başına en az kenar uzunluğu (oyun m)")
    ap.add_argument("--min-junction-gap", type=float, default=55.0)
    ap.add_argument("--min-hw-gap", type=float, default=70.0, help="otoyol çıkış/katılma prefabları arası en az (oyun m)")
    ap.add_argument("--hw-prefab-len", type=float, default=40.0, help="otoyol çıkış/katılma prefab uzunluğu (oyun m)")
    ap.add_argument("--drop-deadend-len", type=float, default=90.0, help="bu uzunluktan kısa çıkmaz ara sokakları at (oyun m; 0=kapalı)")
    ap.add_argument("--no-collapse", action="store_true", help="bölünmüş caddeleri tek hatta indirgeme")
    ap.add_argument("--core-only", action="store_true", help="yalnız Gebze/Darıca/Çayırova/Dilovası çekirdeği")
    ap.add_argument("--tertiary-radius", type=float, default=3000.0, help="il geneli tertiary: merkeze en çok (gerçek m)")
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

    def add_way(wy, reg):
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
        ways.append((dict(wy, _reg=reg), t, hw, [(round(x, 2), round(y, 2)) for x, y in pts]))

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
                if hw.startswith("tertiary") and wy["id"] not in seen_ids:
                    ln = LineString([T.transform(q["lon"], q["lat"]) for q in wy["geometry"]])
                    if min(ln.distance(c) for c in cpts) > a.tertiary_radius:
                        skipped += 1
                        continue
                add_way(wy, "prov")
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
                if not outer and hw in ("residential", "unclassified", "road"):
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
                              "len": round(L, 1), "pts": out, "outer": outer})

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

    # C# üreticinin prefab açısı tutmadığı için reddettiği kavşak düğümleri (junction_rejects.json) birikimli
    # olarak dışlanır; bu düğümler 4c'de düz geçiş olarak bağlanır.
    excl_path = ROOT / "data" / "processed" / "junction_excluded.json"
    rej_path = ROOT / "data" / "processed" / "junction_rejects.json"
    excluded = set(json.loads(excl_path.read_text())) if excl_path.exists() else set()
    if rej_path.exists():
        excluded |= set(json.loads(rej_path.read_text()))
        excl_path.write_text(json.dumps(sorted(excluded)))
        rej_path.unlink()
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
                return L, chain, pts
            (e2, en2) = nxt[0] if nxt[0][0]["id"] != cur["id"] else nxt[1]
            if e2["id"] == cur["id"] or e2["id"] in chain or cls(e2["type"]) != cls(cur["type"]) \
                    or cls(e2["type"]) is None or e2["oneway"] != cur["oneway"]:
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
    for k, lst in inc.items():
        if len(lst) not in (3, 4) or k in excluded:
            continue
        cl = [cls(ed["type"]) for ed, _ in lst]
        if None in cl or (cl.count("r1"), cl.count("r2")) not in PATTERNS:
            continue
        if any(ed["a"] == ed["b"] for ed, _ in lst):
            continue
        chains = [arm_chain(ed, end, k) for ed, end in lst]
        if min(c[0] for c in chains) < a.min_arm:
            continue
        ids = [x for c in chains for x in c[1]]
        if len(ids) != len(set(ids)):  # iki kol aynı zincir (halka)
            continue
        dirs = [chain_dir(c[2]) for c in chains]
        if any(dirs[i][0] * dirs[j][0] + dirs[i][1] * dirs[j][1] > 0.9 for i in range(len(dirs)) for j in range(i)):
            continue  # iki kol neredeyse üst üste (prefab açısı tutmaz)
        c = edges[lst[0][0]["id"]]["pts"][0] if lst[0][1] == "a" else lst[0][0]["pts"][-1]
        cand.append((min(c_[0] for c_ in chains), k, c, lst, chains, dirs))
    cand.sort(key=lambda x: -x[0])  # en uzun kollu (en rahat) kavşaklar önce
    chosen, grid = [], defaultdict(list)
    G = a.min_junction_gap
    used_edges = Counter()
    for _, k, c, lst, chains, dirs in cand:
        key = (int(c[0] // G), int(c[1] // G))
        if any(math.dist(c, q) < G for dx in (-1, 0, 1) for dz in (-1, 0, 1) for q in grid[(key[0] + dx, key[1] + dz)]):
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
        chosen.append({"id": len(chosen), "node": k, "x": c[0], "z": c[1], "arms":
                       [{"edge": ed["id"], "end": end, "cls": cls(ed["type"]), "dir": d}
                        for (ed, end), d in zip(lst, dirs)]})

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
        rp = er["pts"] if rend == "a" else er["pts"][::-1]
        acc, far = 0.0, rp[-1]
        for p_, q_ in zip(rp, rp[1:]):
            acc += math.dist(p_, q_)
            if acc >= 30:
                far = q_
                break
        lat = (far[0] - rp[0][0]) * (-tz) + (far[1] - rp[0][1]) * tx
        if lat <= 1.0:  # rampa sağda değil
            why["rampa solda/düz"] += 1
            continue
        # prefab (40 m) çıkışta gelen şeridin, katılmada giden şeridin üstüne oturur
        long_e, short_e = (ein, eout) if kind == "exit" else (eout, ein)
        if long_e["len"] < a.hw_prefab_len + 10 or short_e["len"] < 12 or er["len"] < 30:
            why[f"kısa kenar ({'uzun' if long_e['len'] < a.hw_prefab_len + 10 else 'kısa/rampa'})"] += 1
            continue
        c = ein["pts"][-1]
        key = (int(c[0] // HG), int(c[1] // HG))
        if any(math.dist(c, q) < HG for dx in (-1, 0, 1) for dz in (-1, 0, 1) for q in hgrid[(key[0] + dx, key[1] + dz)]):
            why["başka prefaba yakın"] += 1
            continue
        hgrid[key].append(c)
        hwj.append({"id": len(hwj), "node": k, "x": c[0], "z": c[1], "kind": kind,
                    "travel": [round(tx, 4), round(tz, 4)],
                    "arms": [{"edge": ein["id"], "end": "b", "role": "in"},
                             {"edge": eout["id"], "end": "a", "role": "out"},
                             {"edge": er["id"], "end": rend, "role": "ramp"}]})
    print(f"otoyol ayrılma/katılma: {sum(1 for h in hwj if h['kind'] == 'exit')} çıkış, "
          f"{sum(1 for h in hwj if h['kind'] == 'merge')} katılma; elenen: {dict(why)}")

    # 4) Prefab konmayan kesişimlerde parçaları aynı OSM yolu boyunca yeniden birleştir
    #    (editör öğe sayısı sınırı: ~17 bin öğe üstünde render taşması).
    jnodes = {j["node"] for j in chosen} | {h["node"] for h in hwj}
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
    for j in chosen + hwj:
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
        armed = {arm["edge"] for j in chosen + hwj for arm in j["arms"]}
        keep = [ed for ed in edges if not (ed["type"] in ("r1_city_narrow", "service") and ed["id"] not in armed
                                            and (deg[ed["a"]] == 1 or deg[ed["b"]] == 1) and ed["len"] < a.drop_deadend_len)]
        idmap = {ed["id"]: i for i, ed in enumerate(keep)}
        for j in chosen + hwj:
            for arm in j["arms"]:
                arm["edge"] = idmap[arm["edge"]]
        for i, ed in enumerate(keep):
            ed["id"] = i
        print(f"kısa çıkmaz sokak atıldı: {len(edges) - len(keep)}")
        edges = keep

    # 4c) Prefabsız düğümlerde yol sürekliliği: ETS2'de aynı noktada biten iki yol öğesi BAĞLI DEĞİLDİR
    #     (GPS, yapay zekâ trafiği ve iş rotaları kopar). Her prefabsız düğümde en düz/uyumlu kol çiftleri
    #     tek kenarda birleştirilir; 3-4 kollu kesişimde ana yol kesintisiz geçer, kalan kol orada biter.
    jnodes = {j["node"] for j in chosen} | {h["node"] for h in hwj}
    edges, road_links = link_through(edges, chosen + hwj, jnodes, arm_dir)
    # il geneli kenarlar: birleştirme sonrası ara düğümler (eski kesişimler) yeniden sadeleştirilir (segment bütçesi)
    before = sum(len(e["pts"]) - 1 for e in edges)
    for e in edges:
        if e.get("outer") and len(e["pts"]) > 2:
            tol = 12.0 if e["hw"].startswith(("tertiary", "secondary", "primary", "trunk", "motorway")) else 6.0
            mseg = 40.0 if tol > 10 else 20.0
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
    depots = place_depots(edges, chosen, S, a, links=road_links)
    cities = assign_cities(depots, edges, S)

    out = {"meta": {"scale_divisor": S, "origin_osm_node": 26505108, "axes": "+X doğu, +Z güney, Y=0",
                    "prefab_radius": a.prefab_radius, "attribution": "(c) OpenStreetMap contributors, ODbL 1.0"},
           "edges": edges, "junctions": chosen, "hw_junctions": hwj, "depots": depots, "cities": cities, "road_links": road_links,
           "city_areas": city_grid(edges, S)}
    dst = ROOT / "data" / "processed" / f"map_graph_s{S:g}.json"
    dst.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    # otoyol prefab ↔ yol şerit sayısı eşleme (hi/lo prefab + hw2/3/4_oneway)
    import assign_hw_lanes
    assign_hw_lanes.main(str(dst))
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
        # ikinci şans: kesişimde düz çift dışında kalan iki kol, ≥90° dönüşle birbirine bağlanır (GPS/iş rotası
        # sürekliliği; aksi halde ikisi de orada çıkmaz biterdi)
        rest = [e for e in ends if e not in used]
        if len(ends) > 2 and len(rest) >= 2:
            for _, dot, x, y, cross in pairs:
                if x in used or y in used or dot > 0.0:
                    continue
                used |= {x, y}
                if cross:
                    xlinks.append((x, y))
                else:
                    partner[x], partner[y] = y, x
                stats["dönüşlü"] += 1

    # zincirler: serbest ucu olan kenardan başlayıp ortaklara yürü
    seen, out, endmap = set(), [], {}

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
        out.append(new)
        endmap[(e0, "b" if r0 else "a")] = (new["id"], "a")
        endmap[(e1, "a" if r1 else "b")] = (new["id"], "b")
    for j in junctions:
        for arm in j["arms"]:
            arm["edge"], arm["end"] = endmap[(arm["edge"], arm["end"])]
    links = [[*endmap[x], *endmap[y]] for x, y in xlinks]
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


def place_depots(edges, chosen, S, a, per_city=3, min_gap=250.0, links=()):
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


if __name__ == "__main__":
    main()
