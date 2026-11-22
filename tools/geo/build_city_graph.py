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
    ap.add_argument("--drop-deadend-len", type=float, default=60.0, help="bu uzunluktan kısa çıkmaz ara sokakları at (oyun m; 0=kapalı)")
    a = ap.parse_args()
    S = a.scale
    s, w, n, e = CFG["core_bbox_swne"]
    core = box(*T.transform(w, s), *T.transform(e, n))

    # 1) yolları yükle (UTM), kullanım sayısı
    ways = []
    for wy in json.loads((RAW / "roads.json").read_text(encoding="utf-8"))["elements"]:
        t = wy.get("tags", {})
        hw = t.get("highway")
        if hw not in ROADMAP or hw in a.exclude:
            continue
        if hw == "service" and t.get("service") not in (None, "", "alley"):
            continue
        pts = [T.transform(p["lon"], p["lat"]) for p in wy["geometry"]]
        if not LineString(pts).intersects(core):
            continue
        ways.append((wy, t, hw, [(round(x, 2), round(y, 2)) for x, y in pts]))
    use = Counter()
    for _, _, _, pts in ways:
        for i, p in enumerate(pts):
            use[p] += 2 if i in (0, len(pts) - 1) else 1  # uçlar her zaman bölme noktası

    # 2) kesişimlerden böl, çekirdek alana kırp, sadeleştir
    g = lambda x, y: (round((x - E0) / S, 3), round(-(y - N0) / S, 3))
    edges, node_id, nodes = [], {}, []

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
            if not core.contains(ln):
                if not ln.intersects(core):
                    continue
                inter = ln.intersection(core)
                if inter.geom_type != "LineString" or inter.length < 6:
                    continue
                ln = inter
                seg = [(round(x, 2), round(y, 2)) for x, y in ln.coords]
            simp = list(LineString(seg).simplify(a.simplify_m).coords)
            gpts = [g(x, y) for x, y in simp]
            out = [gpts[0]]
            for c in gpts[1:-1]:
                if math.dist(out[-1], c) >= a.min_seg and math.dist(c, gpts[-1]) >= a.min_seg:
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
                          "len": round(L, 1), "pts": out})

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

    cand = []
    for k, lst in inc.items():
        if len(lst) not in (3, 4):
            continue
        cl = [cls(ed["type"]) for ed, _ in lst]
        if None in cl or (cl.count("r1"), cl.count("r2")) not in PATTERNS:
            continue
        if any(ed["a"] == ed["b"] for ed, _ in lst):
            continue
        if min(ed["len"] for ed, _ in lst) < a.min_arm:
            continue
        c = edges[lst[0][0]["id"]]["pts"][0] if lst[0][1] == "a" else lst[0][0]["pts"][-1]
        cand.append((min(ed["len"] for ed, _ in lst), k, c, lst))
    cand.sort(key=lambda x: -x[0])  # en uzun kollu (en rahat) kavşaklar önce
    chosen, grid = [], defaultdict(list)
    G = a.min_junction_gap
    used_edges = Counter()
    for _, k, c, lst in cand:
        key = (int(c[0] // G), int(c[1] // G))
        if any(math.dist(c, q) < G for dx in (-1, 0, 1) for dz in (-1, 0, 1) for q in grid[(key[0] + dx, key[1] + dz)]):
            continue
        # aynı kenarın iki ucunda prefab: kenar 2*yarıçap + pay kadar uzun olmalı
        rad = 23.25 if any(cls(ed["type"]) == "r2" for ed, _ in lst) else a.prefab_radius
        if any(used_edges[ed["id"]] and ed["len"] < 2 * rad + 8 for ed, _ in lst):
            continue
        grid[key].append(c)
        for ed, _ in lst:
            used_edges[ed["id"]] += 1
        chosen.append({"id": len(chosen), "node": k, "x": c[0], "z": c[1], "arms":
                       [{"edge": ed["id"], "end": end, "cls": cls(ed["type"]), "dir": arm_dir(ed, end)} for ed, end in lst]})

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

    # 5) Şirket depoları: sanayi alanlarında, düz ve uzun bir şehir yolu parçasının yanına iki düğümlü depo
    #    prefabı. Parça ikiye bölünür; depo düğümleri iki yeni kenar ucuna gelir.
    depots = place_depots(edges, chosen, S, a)
    cities = assign_cities(depots, edges, S)

    out = {"meta": {"scale_divisor": S, "origin_osm_node": 26505108, "axes": "+X doğu, +Z güney, Y=0",
                    "prefab_radius": a.prefab_radius, "attribution": "(c) OpenStreetMap contributors, ODbL 1.0"},
           "edges": edges, "junctions": chosen, "hw_junctions": hwj, "depots": depots, "cities": cities,
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


CITY_TOKENS = {"Gebze": "gebze", "Darıca": "darica", "Çayırova": "cayirova", "Dilovası": "dilovasi"}


def load_city_polys(S):
    """İlçe poligonları (OSM admin_level 6), oyun koordinatında: {token: (ad, poligon)}."""
    from shapely.ops import polygonize, unary_union
    g = lambda x, y: ((x - E0) / S, -(y - N0) / S)
    polys = {}
    for el in json.loads((RAW / "districts.json").read_text(encoding="utf-8"))["elements"]:
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
    rects = city_grid(edges, S)
    for d in depots:
        d["city"] = grid_city(rects, d["body"])
    # Her depo harita genelinde BENZERSİZ bir şirket alır; şirket o depo türünün prefabını ana oyunda da
    # kullanıyor olmalı (def.scs /def/company/*/editor taraması: data/processed/game_defs/company_prefabs.tsv).
    # Neden: oyunda her (şirket, şehir) için tek company_def/prefab var; şehir alanları çakışınca aynı şirketin
    # farklı türde iki deposu "Company item without company assignment" hatası veriyordu.
    pools = {"generic": ["stokes", "transinet", "posped"],
             "logistic": ["tradeaux", "posped", "eurogoodies", "lkwlog"],
             "light_factory": ["trameri", "kathode"]}
    used = set()
    for d in depots:
        free = [c for c in pools.get(d["kind"], []) if c not in used]
        if free:
            d["company"] = free[0]
        used.add(d["company"])
    return cities


# Depo prefabları (ana oyun, Avusturya seti): düğüm0 → düğüm1 aralığı (oyun m). Şirketler sırayla dağıtılır.
DEPOT_TYPES = [
    {"company": "stokes", "kind": "generic", "span": 100.0},
    {"company": "lkwlog", "kind": "logistic", "span": 80.0},
    {"company": "trameri", "kind": "light_factory", "span": 90.65},
    {"company": "transinet", "kind": "generic", "span": 100.0},
    {"company": "tradeaux", "kind": "logistic", "span": 80.0},
    {"company": "posped", "kind": "logistic", "span": 80.0},
]


def place_depots(edges, chosen, S, a, max_depots=9, min_gap=300.0, clear=45.0):
    """Sanayi poligonu içindeki uzun düz parçalara depo yerleştirir; edges listesini yerinde böler."""
    from shapely.geometry import Point, Polygon
    from shapely.strtree import STRtree

    g = lambda x, y: ((x - E0) / S, -(y - N0) / S)
    inds = []
    for el in json.loads((RAW / "landuse.json").read_text(encoding="utf-8"))["elements"]:
        t = el.get("tags", {})
        if el["type"] == "way" and "geometry" in el and (t.get("landuse") == "industrial" or t.get("industrial")):
            pts = [g(*T.transform(p["lon"], p["lat"])) for p in el["geometry"]]
            if len(pts) >= 4 and pts[0] == pts[-1]:
                p = Polygon(pts)
                if p.is_valid and p.area > 2000:
                    inds.append(p)
    itree = STRtree(inds)
    lines = [LineString(e["pts"]) for e in edges]
    ltree = STRtree(lines)
    jpts = [(j["x"], j["z"]) for j in chosen]
    out, used = [], []
    # Oyun bir şehirde aynı depo prefabını iki şirkete eşleyemiyor ("Invalid company item assignment ...
    # Economy reset - company mismatch", 2026-11-22 önizlemede doğrulandı) → (tür, şehir) benzersiz olmalı.
    rects = city_grid(edges, S)
    kind_city = set()
    next_node = max(max(e["a"], e["b"]) for e in edges) + 1
    k = 0
    for ed in sorted(edges, key=lambda e: -e["len"]):
        if len(out) >= max_depots:
            break
        if ed["type"] not in ("r1_city", "r1_city_narrow") or ed["oneway"]:
            continue
        need = min(t["span"] for t in DEPOT_TYPES) + 24
        pts = ed["pts"]
        for i in range(len(pts) - 1):
            P, Q = pts[i], pts[i + 1]
            L = math.dist(P, Q)
            if L < need:
                continue
            mid = ((P[0] + Q[0]) / 2, (P[1] + Q[1]) / 2)
            if any(math.dist(mid, u) < min_gap for u in used) or any(math.dist(mid, j) < need / 2 + 14 for j in jpts):
                continue
            mp = Point(mid)
            if not any(inds[q].contains(mp) for q in itree.query(mp)):
                continue
            ux, uz = (Q[0] - P[0]) / L, (Q[1] - P[1]) / L
            side = None
            for sgn in (1, -1):  # yolun sağı/solu: depo gövdesi ~55 m içeride
                nx, nz = -uz * sgn, ux * sgn
                body = Point(mid[0] + nx * 60, mid[1] + nz * 60)
                near = [q for q in ltree.query(body.buffer(clear)) if q != ed["id"] and lines[q].distance(body) < clear]
                if not near:
                    side = (nx, nz)
                    break
            if side is None:
                continue
            bcity = grid_city(rects, (mid[0] + side[0] * 55, mid[1] + side[1] * 55))
            # bu noktaya sığan ve o şehirde henüz olmayan türü seç (sıra k ile döner → türler dengeli)
            cands = [DEPOT_TYPES[(k + q) % len(DEPOT_TYPES)] for q in range(len(DEPOT_TYPES))]
            typ = next((t for t in cands if L >= t["span"] + 24 and (t["kind"], bcity) not in kind_city
                        and not any(math.dist(mid, j) < t["span"] / 2 + 26 for j in jpts)), None)
            if typ is None:
                continue
            kind_city.add((typ["kind"], bcity))
            h = typ["span"] / 2
            n0 = (round(mid[0] - ux * h, 3), round(mid[1] - uz * h, 3))
            n1 = (round(mid[0] + ux * h, 3), round(mid[1] + uz * h, 3))
            # kenarı böl: A = baş..n0, B = n1..son
            ida, idb = next_node, next_node + 1
            next_node += 2
            B = dict(ed, id=len(edges), a=idb, pts=[list(n1)] + [list(p) for p in pts[i + 1:]])
            ed["pts"] = [list(p) for p in pts[:i + 1]] + [list(n0)]
            ed["b"] = ida
            for e2 in (ed, B):
                e2["len"] = round(sum(math.dist(p, q) for p, q in zip(e2["pts"], e2["pts"][1:])), 1)
            # B, eski kenarın b ucundaki kavşak kolunu devralır
            for j in chosen:
                for arm in j["arms"]:
                    if arm["edge"] == ed["id"] and arm["end"] == "b":
                        arm["edge"] = B["id"]
            edges.append(B)
            used.append(mid)
            out.append({"id": len(out), "company": typ["company"], "kind": typ["kind"],
                        "n0": list(n0), "n1": list(n1),
                        "body": [round(mid[0] + side[0] * 55, 2), round(mid[1] + side[1] * 55, 2)],
                        "arm0": {"edge": ed["id"], "end": "b"}, "arm1": {"edge": B["id"], "end": "a"}})
            k += 1
            break
    return out


if __name__ == "__main__":
    main()
