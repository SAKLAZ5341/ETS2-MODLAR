"""SAKLAZ Türkiye Map - tam şehir haritası için üretici girdisi (map_export.json) hazırlar.

Kullanım:
    .venv\\Scripts\\python.exe -I tools\\geo\\build_city_export.py [--scale 3]

Kapsam: config/aoi.json -> core_bbox_swne (Gebze, Darıca, Çayırova kentsel çekirdeği).
İçerik:
  roads     : tüm yol sınıfları (otoyol ... ara sokak, seçilmiş servis yolları), oyun koordinatında,
              sadeleştirilmiş, en kısa parça >= 2 oyun m; her yol için ETS2 yol tipi önerisi
  junctions : 3+ kollu kesişimler (prefab gerektiren noktalar) ve kol sayısı
  buildings : OSM bina poligonlarından merkez, yön (en uzun kenar açısı), boyut (oyun m),
              kat sayısı/tipi -> üretici bunu ETS2 bina modeli/Buildings öğesine eşler
Köken (0,0) = Gebze OSM düğümü; +X doğu, +Z güney. Veri © OpenStreetMap katkıda bulunanlar, ODbL 1.0.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, Polygon, box

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
CFG = json.loads((ROOT / "config" / "aoi.json").read_text(encoding="utf-8"))
T = Transformer.from_crs("EPSG:4326", "EPSG:32635", always_xy=True)

# OSM sınıfı -> (ETS2 yol önerisi, öncelik)
ROADMAP = {
    "motorway": ("hw3_divided", 1), "trunk": ("hw3_divided", 2), "primary": ("r2_divided", 3),
    "motorway_link": ("ramp_1lane", 4), "trunk_link": ("ramp_1lane", 4), "primary_link": ("ramp_1lane", 4),
    "secondary": ("r1_city", 5), "secondary_link": ("r1_city", 5), "tertiary": ("r1_city", 6),
    "tertiary_link": ("r1_city", 6), "unclassified": ("r1_city_narrow", 7), "residential": ("r1_city_narrow", 8),
    "living_street": ("r1_city_narrow", 8), "road": ("r1_city_narrow", 8), "service": ("service", 9),
}
SERVICE_KEEP = {None, "", "alley", "driveway_industrial"}  # park yeri koridorlarını alma


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=CFG["game"]["city_scale_divisor"])
    ap.add_argument("--simplify-m", type=float, default=1.5, help="Douglas-Peucker toleransı (gerçek m)")
    ap.add_argument("--min-seg", type=float, default=2.0, help="en kısa yol parçası (oyun m)")
    ap.add_argument("--exclude", nargs="*", default=[], help="dışlanacak OSM highway sınıfları")
    ap.add_argument("--road-clearance", type=float, default=8.0, help="bina merkezi - yol arası en az oyun m")
    ap.add_argument("--min-building-gap", type=float, default=15.0, help="bina merkezleri arası en az oyun m")
    ap.add_argument("--max-buildings", type=int, default=3500, help="en büyükten başlayarak en fazla bu kadar bina (editör öğe sınırı)")
    ap.add_argument("--road-clearance-default", type=float, default=8.0)
    ap.add_argument("--max-detailed", type=int, default=600, help="detaylı (ana cadde) model sayısı üst sınırı; çizim bütçesi")
    a = ap.parse_args()
    S = a.scale
    s, w, n, e = CFG["core_bbox_swne"]
    core = box(*T.transform(w, s), *T.transform(e, n))
    E0, N0 = 705139.33, 4519475.38  # Gebze OSM düğümü 26505108 (build_network ile aynı)
    g = lambda x, y: (round((x - E0) / S, 3), round(-(y - N0) / S, 3))

    roads, cnt, deg = [], Counter(), defaultdict(int)
    for wy in json.loads((RAW / "roads.json").read_text(encoding="utf-8"))["elements"]:
        t = wy.get("tags", {})
        hw = t.get("highway")
        if hw not in ROADMAP:
            continue
        if hw in a.exclude or (hw == "service" and t.get("service") not in SERVICE_KEEP):
            continue
        pts = [T.transform(p["lon"], p["lat"]) for p in wy["geometry"]]
        ln = LineString(pts)
        if not ln.intersects(core):
            continue
        ln = ln.intersection(core)
        parts = list(ln.geoms) if hasattr(ln, "geoms") else [ln]
        for part in parts:
            if part.length < 6 or part.geom_type != "LineString":
                continue
            simp = part.simplify(a.simplify_m)
            cs = [g(x, y) for x, y in simp.coords]
            out = [cs[0]]
            for c in cs[1:]:
                if math.dist(out[-1], c) >= a.min_seg:  # ETS2 en kısa yol parçası ~1,25 m
                    out.append(c)
            if len(out) < 2:
                continue
            kind, prio = ROADMAP[hw]
            roads.append({"osm": wy["id"], "hw": hw, "type": kind, "prio": prio, "name": t.get("name"),
                          "ref": t.get("ref"), "oneway": t.get("oneway") in ("yes", "1", "-1"),
                          "reverse": t.get("oneway") == "-1", "lanes": t.get("lanes"),
                          "bridge": t.get("bridge") == "yes", "tunnel": t.get("tunnel") == "yes", "pts": out})
            cnt[hw] += 1
            for c in (out[0], out[-1]):
                deg[(round(c[0], 1), round(c[1], 1))] += 1
    junctions = [{"x": k[0], "z": k[1], "arms": v} for k, v in deg.items() if v >= 3]

    buildings, bcnt = [], Counter()
    bpath = RAW / "buildings.json"
    if bpath.exists():
        for el in json.loads(bpath.read_text(encoding="utf-8"))["elements"]:
            geom = el.get("geometry") or next((m.get("geometry") for m in el.get("members", []) if m.get("role") == "outer"), None)
            if not geom or len(geom) < 4:
                continue
            try:
                poly = Polygon([T.transform(p["lon"], p["lat"]) for p in geom]).buffer(0)
            except ValueError:
                continue
            if poly.is_empty or poly.area < 20 or not core.contains(poly.representative_point()):
                continue
            mrr = poly.minimum_rotated_rectangle
            xs = list(mrr.exterior.coords)
            e1, e2 = (xs[0], xs[1]), (xs[1], xs[2])
            l1, l2 = math.dist(*e1), math.dist(*e2)
            long_e = e1 if l1 >= l2 else e2
            ang = math.degrees(math.atan2(long_e[1][1] - long_e[0][1], long_e[1][0] - long_e[0][0]))
            c = poly.centroid
            t = el.get("tags", {})
            kind = t.get("building", "yes")
            bcnt[kind] += 1
            buildings.append({"osm": el["id"], "kind": kind, "levels": t.get("building:levels"),
                              "x": g(c.x, c.y)[0], "z": g(c.x, c.y)[1], "heading_deg": round(-ang, 1),
                              "len": round(max(l1, l2) / S, 2), "wid": round(min(l1, l2) / S, 2),
                              "area_real_m2": round(poly.area)})

    # Gerçek boyutlu modeller 1:S sıkıştırılmış şehre sığmaz: yola yakın ve birbirine yakın binaları ele.
    placed = []
    if buildings:
        from shapely.strtree import STRtree
        rlines = [LineString(r["pts"]) for r in roads if r["prio"] <= 8]
        tree = STRtree(rlines)
        mlines = [LineString(r["pts"]) for r in roads if r["prio"] <= 6]  # ana caddeler (tertiary ve üstü)
        mtree = STRtree(mlines)
        cell = defaultdict(list)
        CELL = a.min_building_gap
        for b in sorted(buildings, key=lambda b: -b["area_real_m2"]):
            p = (b["x"], b["z"])
            from shapely.geometry import Point as _P
            pt = _P(p)
            near = tree.query(pt.buffer(a.road_clearance))
            if any(rlines[i].distance(pt) < a.road_clearance for i in near):
                continue
            k = (int(p[0] // CELL), int(p[1] // CELL))
            if any(math.dist(p, q) < CELL for dx in (-1, 0, 1) for dz in (-1, 0, 1) for q in cell[(k[0] + dx, k[1] + dz)]):
                continue
            cell[k].append(p)
            # ana caddeye 35 oyun m'den yakın binalar detaylı modelle, diğerleri düşük detaylı (mid) modelle
            b["near_main"] = any(mlines[i].distance(pt) < 35 for i in mtree.query(pt.buffer(35)))
            placed.append(b)
            if a.max_buildings and len(placed) >= a.max_buildings:
                break
    for b in buildings:
        b["place"] = False
    nd = 0
    for b in placed:  # alan sırasıyla: en büyük ana cadde binaları detaylı kalır
        b["place"] = True
        if b.get("near_main"):
            nd += 1
            if nd > a.max_detailed:
                b["near_main"] = False

    out = {"meta": {"scale_divisor": S, "origin_osm_node": 26505108, "axes": "+X doğu, +Z güney, Y=0",
                    "core_bbox_swne": CFG["core_bbox_swne"],
                    "attribution": "(c) OpenStreetMap contributors, ODbL 1.0"},
           "roads": roads, "junctions": junctions, "buildings": buildings}
    dst = ROOT / "data" / "processed" / f"map_export_s{S:g}.json"
    dst.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    L = sum(sum(math.dist(p, q) for p, q in zip(r["pts"], r["pts"][1:])) for r in roads)
    xs = [p[0] for r in roads for p in r["pts"]]
    zs = [p[1] for r in roads for p in r["pts"]]
    summary = {"scale": S, "roads": len(roads), "road_nodes": sum(len(r["pts"]) for r in roads),
               "road_km_game": round(L / 1000, 1), "by_class": dict(cnt), "junctions_3plus": len(junctions),
               "buildings": len(buildings), "buildings_placed": sum(1 for b in buildings if b.get("place")),
               "buildings_by_kind_top": bcnt.most_common(10),
               "extent_game_m": [round(min(xs)), round(max(xs)), round(min(zs)), round(max(zs))],
               "file_mb": round(dst.stat().st_size / 1e6, 1)}
    (ROOT / "data" / "processed" / f"map_export_s{S:g}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
