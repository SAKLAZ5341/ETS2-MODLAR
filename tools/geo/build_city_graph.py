"""SAKLAZ TÃ¼rkiye Map - kavÅŸaklÄ± ÅŸehir aÄŸÄ± (map_graph_s<scale>.json) Ã¼retir.

KullanÄ±m:
    .venv\\Scripts\\python.exe -I tools\\geo\\build_city_graph.py [--scale 3]

build_city_export.py'den farkÄ±: yollar Ã¶nce GERÃ‡EK OSM kesiÅŸim noktalarÄ±ndan bÃ¶lÃ¼nÃ¼r, sonra her parÃ§a
ayrÄ± sadeleÅŸtirilir; bÃ¶ylece kavÅŸak noktalarÄ± korunur. Ã‡Ä±ktÄ±:
  edges     : kavÅŸaktan kavÅŸaÄŸa yol parÃ§alarÄ± (oyun koordinatÄ±), uÃ§larÄ±nda dÃ¼ÄŸÃ¼m kimliÄŸi
  junctions : prefab adaylarÄ± (yalnÄ±zca ÅŸehir yollarÄ±, 3-4 kol, kollar yeterince uzun, birbirinden uzak)
              her kol iÃ§in kenar kimliÄŸi, hangi uÃ§ ve Ã§Ä±kÄ±ÅŸ yÃ¶nÃ¼ (birim vektÃ¶r)
Prefab seÃ§imi/dÃ¶ndÃ¼rme tools/mapgen (C#) tarafÄ±nda, .ppd dÃ¼ÄŸÃ¼mlerine gÃ¶re yapÄ±lÄ±r.
Veri Â© OpenStreetMap katkÄ±da bulunanlar, ODbL 1.0.
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
E0, N0 = 705139.33, 4519475.38  # Gebze OSM dÃ¼ÄŸÃ¼mÃ¼ 26505108

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
# izin verilen (r1 sayÄ±sÄ±, r2 sayÄ±sÄ±) desenleri -> prefab var
PATTERNS = {(3, 0), (2, 1), (1, 2), (0, 3), (4, 0), (0, 4)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=CFG["game"]["city_scale_divisor"])
    ap.add_argument("--simplify-m", type=float, default=10.0)
    ap.add_argument("--min-seg", type=float, default=8.0)
    ap.add_argument("--exclude", nargs="*", default=["service", "living_street"])
    ap.add_argument("--prefab-radius", type=float, default=18.0, help="prefab merkez-dÃ¼ÄŸÃ¼m mesafesi (oyun m)")
    ap.add_argument("--min-arm", type=float, default=24.0, help="kol baÅŸÄ±na en az kenar uzunluÄŸu (oyun m)")
    ap.add_argument("--min-junction-gap", type=float, default=55.0)
    ap.add_argument("--drop-deadend-len", type=float, default=60.0, help="bu uzunluktan kÄ±sa Ã§Ä±kmaz ara sokaklarÄ± at (oyun m; 0=kapalÄ±)")
    a = ap.parse_args()
    S = a.scale
    s, w, n, e = CFG["core_bbox_swne"]
    core = box(*T.transform(w, s), *T.transform(e, n))

    # 1) yollarÄ± yÃ¼kle (UTM), kullanÄ±m sayÄ±sÄ±
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
            use[p] += 2 if i in (0, len(pts) - 1) else 1  # uÃ§lar her zaman bÃ¶lme noktasÄ±

    # 2) kesiÅŸimlerden bÃ¶l, Ã§ekirdek alana kÄ±rp, sadeleÅŸtir
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

    # 3) dÃ¼ÄŸÃ¼m dereceleri ve kavÅŸak adaylarÄ±
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
    cand.sort(key=lambda x: -x[0])  # en uzun kollu (en rahat) kavÅŸaklar Ã¶nce
    chosen, grid = [], defaultdict(list)
    G = a.min_junction_gap
    used_edges = Counter()
    for _, k, c, lst in cand:
        key = (int(c[0] // G), int(c[1] // G))
        if any(math.dist(c, q) < G for dx in (-1, 0, 1) for dz in (-1, 0, 1) for q in grid[(key[0] + dx, key[1] + dz)]):
            continue
        # aynÄ± kenarÄ±n iki ucunda prefab: kenar 2*yarÄ±Ã§ap + pay kadar uzun olmalÄ±
        rad = 23.25 if any(cls(ed["type"]) == "r2" for ed, _ in lst) else a.prefab_radius
        if any(used_edges[ed["id"]] and ed["len"] < 2 * rad + 8 for ed, _ in lst):
            continue
        grid[key].append(c)
        for ed, _ in lst:
            used_edges[ed["id"]] += 1
        chosen.append({"id": len(chosen), "node": k, "x": c[0], "z": c[1], "arms":
                       [{"edge": ed["id"], "end": end, "cls": cls(ed["type"]), "dir": arm_dir(ed, end)} for ed, end in lst]})

    # 4) Prefab konmayan kesiÅŸimlerde parÃ§alarÄ± aynÄ± OSM yolu boyunca yeniden birleÅŸtir
    #    (editÃ¶r Ã¶ÄŸe sayÄ±sÄ± sÄ±nÄ±rÄ±: ~17 bin Ã¶ÄŸe Ã¼stÃ¼nde render taÅŸmasÄ±).
    jnodes = {j["node"] for j in chosen}
    remap, merged = {}, []
    cur = None
    for ed in edges:  # aynÄ± yolun parÃ§alarÄ± ardÄ±ÅŸÄ±k Ã¼retildi
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
            # birleÅŸik kenarÄ±n hangi ucu bu kavÅŸakta
            arm["end"] = "a" if m["a"] == j["node"] else "b"
    for m in merged:
        m.pop("_parts", None)
        if len(m["pts"]) > 2:  # birleÅŸik kenarÄ± yeniden sadeleÅŸtir (uÃ§lar korunur)
            ls = LineString(m["pts"]).simplify(a.simplify_m / S)
            ps = [tuple(round(v, 3) for v in c) for c in ls.coords]
            o = [ps[0]]
            for c in ps[1:-1]:
                if math.dist(o[-1], c) >= a.min_seg and math.dist(c, ps[-1]) >= a.min_seg:
                    o.append(c)
            o.append(ps[-1])
            m["pts"] = [list(c) for c in o]
    edges = merged

    # 4b) KÄ±sa Ã§Ä±kmaz sokaklarÄ± at (editÃ¶r Ã¶ÄŸe/segment sÄ±nÄ±rÄ±). KavÅŸak kolu olan kenarlar korunur.
    if a.drop_deadend_len > 0:
        deg = Counter()
        for ed in edges:
            deg[ed["a"]] += 1
            deg[ed["b"]] += 1
        armed = {arm["edge"] for j in chosen for arm in j["arms"]}
        keep = [ed for ed in edges if not (ed["type"] in ("r1_city_narrow", "service") and ed["id"] not in armed
                                            and (deg[ed["a"]] == 1 or deg[ed["b"]] == 1) and ed["len"] < a.drop_deadend_len)]
        idmap = {ed["id"]: i for i, ed in enumerate(keep)}
        for j in chosen:
            for arm in j["arms"]:
                arm["edge"] = idmap[arm["edge"]]
        for i, ed in enumerate(keep):
            ed["id"] = i
        print(f"kÄ±sa Ã§Ä±kmaz sokak atÄ±ldÄ±: {len(edges) - len(keep)}")
        edges = keep

    # 5) Åirket depolarÄ±: sanayi alanlarÄ±nda, dÃ¼z ve uzun bir ÅŸehir yolu parÃ§asÄ±nÄ±n yanÄ±na iki dÃ¼ÄŸÃ¼mlÃ¼ depo
    #    prefabÄ±. ParÃ§a ikiye bÃ¶lÃ¼nÃ¼r; depo dÃ¼ÄŸÃ¼mleri iki yeni kenar ucuna gelir.
    depots = place_depots(edges, chosen, S, a)

    out = {"meta": {"scale_divisor": S, "origin_osm_node": 26505108, "axes": "+X doÄŸu, +Z gÃ¼ney, Y=0",
                    "prefab_radius": a.prefab_radius, "attribution": "(c) OpenStreetMap contributors, ODbL 1.0"},
           "edges": edges, "junctions": chosen, "depots": depots}
    dst = ROOT / "data" / "processed" / f"map_graph_s{S:g}.json"
    dst.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    deg = Counter(len(v) for v in inc.values())
    summary = {"scale": S, "edges": len(edges), "segments": sum(len(e["pts"]) - 1 for e in edges),
               "graph_nodes": len(inc), "degree_hist": dict(sorted(deg.items())),
               "junction_candidates_city": len(cand), "junctions_chosen": len(chosen),
               "junctions_T": sum(1 for j in chosen if len(j["arms"]) == 3),
               "junctions_X": sum(1 for j in chosen if len(j["arms"]) == 4),
               "depots": len(depots), "depot_companies": Counter(d["company"] for d in depots)}
    (ROOT / "data" / "processed" / f"map_graph_s{S:g}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


# Depo prefablarÄ± (ana oyun, Avusturya seti): dÃ¼ÄŸÃ¼m0 â†’ dÃ¼ÄŸÃ¼m1 aralÄ±ÄŸÄ± (oyun m). Åirketler sÄ±rayla daÄŸÄ±tÄ±lÄ±r.
DEPOT_TYPES = [
    {"company": "stokes", "kind": "generic", "span": 100.0},
    {"company": "lkwlog", "kind": "logistic", "span": 80.0},
    {"company": "trameri", "kind": "light_factory", "span": 90.65},
    {"company": "transinet", "kind": "generic", "span": 100.0},
    {"company": "tradeaux", "kind": "logistic", "span": 80.0},
    {"company": "posped", "kind": "logistic", "span": 80.0},
]


def place_depots(edges, chosen, S, a, max_depots=len(DEPOT_TYPES), min_gap=300.0, clear=45.0):
    """Sanayi poligonu iÃ§indeki uzun dÃ¼z parÃ§alara depo yerleÅŸtirir; edges listesini yerinde bÃ¶ler."""
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
    next_node = max(max(e["a"], e["b"]) for e in edges) + 1
    k = 0
    for ed in sorted(edges, key=lambda e: -e["len"]):
        if len(out) >= max_depots:
            break
        if ed["type"] not in ("r1_city", "r1_city_narrow") or ed["oneway"]:
            continue
        typ = DEPOT_TYPES[k % len(DEPOT_TYPES)]
        need = typ["span"] + 24
        pts = ed["pts"]
        for i in range(len(pts) - 1):
            P, Q = pts[i], pts[i + 1]
            L = math.dist(P, Q)
            if L < need:
                continue
            mid = ((P[0] + Q[0]) / 2, (P[1] + Q[1]) / 2)
            if any(math.dist(mid, u) < min_gap for u in used) or any(math.dist(mid, j) < typ["span"] / 2 + 26 for j in jpts):
                continue
            mp = Point(mid)
            if not any(inds[q].contains(mp) for q in itree.query(mp)):
                continue
            ux, uz = (Q[0] - P[0]) / L, (Q[1] - P[1]) / L
            side = None
            for sgn in (1, -1):  # yolun saÄŸÄ±/solu: depo gÃ¶vdesi ~55 m iÃ§eride
                nx, nz = -uz * sgn, ux * sgn
                body = Point(mid[0] + nx * 60, mid[1] + nz * 60)
                near = [q for q in ltree.query(body.buffer(clear)) if q != ed["id"] and lines[q].distance(body) < clear]
                if not near:
                    side = (nx, nz)
                    break
            if side is None:
                continue
            h = typ["span"] / 2
            n0 = (round(mid[0] - ux * h, 3), round(mid[1] - uz * h, 3))
            n1 = (round(mid[0] + ux * h, 3), round(mid[1] + uz * h, 3))
            # kenarÄ± bÃ¶l: A = baÅŸ..n0, B = n1..son
            ida, idb = next_node, next_node + 1
            next_node += 2
            B = dict(ed, id=len(edges), a=idb, pts=[list(n1)] + [list(p) for p in pts[i + 1:]])
            ed["pts"] = [list(p) for p in pts[:i + 1]] + [list(n0)]
            ed["b"] = ida
            for e2 in (ed, B):
                e2["len"] = round(sum(math.dist(p, q) for p, q in zip(e2["pts"], e2["pts"][1:])), 1)
            # B, eski kenarÄ±n b ucundaki kavÅŸak kolunu devralÄ±r
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
