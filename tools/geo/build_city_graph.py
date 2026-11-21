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
    ap.add_argument("--simplify-m", type=float, default=6.0)
    ap.add_argument("--min-seg", type=float, default=8.0)
    ap.add_argument("--exclude", nargs="*", default=["service", "living_street"])
    ap.add_argument("--prefab-radius", type=float, default=18.0, help="prefab merkez-düğüm mesafesi (oyun m)")
    ap.add_argument("--min-arm", type=float, default=24.0, help="kol başına en az kenar uzunluğu (oyun m)")
    ap.add_argument("--min-junction-gap", type=float, default=55.0)
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

    # 4) Prefab konmayan kesişimlerde parçaları aynı OSM yolu boyunca yeniden birleştir
    #    (editör öğe sayısı sınırı: ~17 bin öğe üstünde render taşması).
    jnodes = {j["node"] for j in chosen}
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
    for j in chosen:
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

    out = {"meta": {"scale_divisor": S, "origin_osm_node": 26505108, "axes": "+X doğu, +Z güney, Y=0",
                    "prefab_radius": a.prefab_radius, "attribution": "(c) OpenStreetMap contributors, ODbL 1.0"},
           "edges": edges, "junctions": chosen}
    dst = ROOT / "data" / "processed" / f"map_graph_s{S:g}.json"
    dst.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    deg = Counter(len(v) for v in inc.values())
    summary = {"scale": S, "edges": len(edges), "segments": sum(len(e["pts"]) - 1 for e in edges),
               "graph_nodes": len(inc), "degree_hist": dict(sorted(deg.items())),
               "junction_candidates_city": len(cand), "junctions_chosen": len(chosen),
               "junctions_T": sum(1 for j in chosen if len(j["arms"]) == 3),
               "junctions_X": sum(1 for j in chosen if len(j["arms"]) == 4)}
    (ROOT / "data" / "processed" / f"map_graph_s{S:g}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
