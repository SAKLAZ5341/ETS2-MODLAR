"""SAKLAZ Türkiye Map - zemin (arazi + bitki örtüsü) ızgarası üretir: data/processed/ground_s<scale>.json

Kullanım:
    .venv\\Scripts\\python.exe -I tools\\geo\\build_ground.py [--scale 3] [--cell 64]

Alan, oyun koordinatında kare hücrelere bölünür. Her hücreye OSM verisinden bir sınıf atanır:
  sea (deniz; boş bırakılır), water, forest, scrub, park, farm, urban, grass.
Yola yakın hücrelerde ağaç yoktur (ağaçlar yolları delmesin). Sonra her sütunda aynı sınıftaki ardışık
hücreler tek parçaya ("run") birleştirilir; tools/mapgen her parçayı bir Terrain öğesi olarak koyar.
Veri © OpenStreetMap katkıda bulunanlar, ODbL 1.0.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
T = Transformer.from_crs("EPSG:4326", "EPSG:32635", always_xy=True)
E0, N0 = 705139.33, 4519475.38  # Gebze OSM düğümü 26505108 (build_city_graph.py ile aynı)

NATURE = {
    ("landuse", "forest"): "forest", ("natural", "wood"): "forest",
    ("natural", "scrub"): "scrub", ("natural", "heath"): "scrub", ("landuse", "orchard"): "scrub",
    ("landuse", "vineyard"): "farm", ("landuse", "farmland"): "farm", ("landuse", "greenfield"): "farm",
    ("landuse", "meadow"): "park", ("landuse", "grass"): "park", ("natural", "grassland"): "park",
    ("landuse", "recreation_ground"): "park", ("landuse", "village_green"): "park", ("landuse", "cemetery"): "park",
    ("landuse", "allotments"): "park", ("leisure", "park"): "park", ("leisure", "garden"): "park",
    ("leisure", "golf_course"): "park", ("leisure", "nature_reserve"): "forest", ("leisure", "pitch"): "urban",
    ("natural", "water"): "water", ("natural", "wetland"): "park", ("natural", "beach"): "sand", ("natural", "sand"): "sand",
    ("landuse", "quarry"): "bare", ("natural", "bare_rock"): "bare", ("landuse", "construction"): "bare",
    ("landuse", "brownfield"): "bare",
}
# öncelik: aynı hücrede birden çok sınıf varsa büyük olan kazanır
PRIO = {"water": 9, "forest": 7, "scrub": 6, "park": 5, "sand": 5, "bare": 4, "farm": 3, "urban": 2, "grass": 1}


def proj(lon, lat, scale):
    e, n = T.transform(lon, lat)
    return ((e - E0) / scale, -(n - N0) / scale)  # +X doğu, +Z güney


def geom_polys(el, scale):
    """Overpass öğesinden kapalı poligonlar."""
    out = []
    if el["type"] == "way" and "geometry" in el:
        pts = [proj(g["lon"], g["lat"], scale) for g in el["geometry"]]
        if len(pts) >= 4 and pts[0] == pts[-1]:
            p = Polygon(pts)
            if p.is_valid and p.area > 0:
                out.append(p)
    elif el["type"] == "relation":
        lines = []
        for m in el.get("members", []):
            if m.get("role") in ("outer", "") and "geometry" in m:
                lines.append(LineString([proj(g["lon"], g["lat"], scale) for g in m["geometry"]]))
        out += [p for p in polygonize(unary_union(lines)) if p.area > 0] if lines else []
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=3.0)
    ap.add_argument("--cell", type=float, default=96.0, help="hücre kenarı (oyun m)")
    ap.add_argument("--margin", type=float, default=300.0, help="yol ağının dışına taşma (oyun m)")
    a = ap.parse_args()
    s = int(a.scale)

    graph = json.loads((OUT / f"map_graph_s{s}.json").read_text(encoding="utf-8"))
    lines = [LineString(e["pts"]) for e in graph["edges"] if len(e["pts"]) >= 2]
    xs = [p[0] for e in graph["edges"] for p in e["pts"]]
    zs = [p[1] for e in graph["edges"] for p in e["pts"]]
    x0, x1 = min(xs) - a.margin, max(xs) + a.margin
    z0, z1 = min(zs) - a.margin, max(zs) + a.margin
    road_tree = STRtree(lines)
    area = box(x0, z0, x1, z1)

    # 1) sınıf poligonları
    polys: list[tuple[Polygon, str]] = []
    nature = json.loads((RAW / "nature.json").read_text(encoding="utf-8"))
    for el in nature["elements"]:
        tags = el.get("tags", {})
        cls = next((c for (k, v), c in NATURE.items() if tags.get(k) == v), None)
        if cls:
            polys += [(p, cls) for p in geom_polys(el, a.scale) if p.intersects(area)]
    landuse = json.loads((RAW / "landuse.json").read_text(encoding="utf-8"))
    for el in landuse["elements"]:
        if el.get("tags", {}).get("landuse") or el.get("tags", {}).get("industrial"):
            polys += [(p, "urban") for p in geom_polys(el, a.scale) if p.intersects(area)]
    print("sınıf poligonları:", Counter(c for _, c in polys))
    ptree = STRtree([p for p, _ in polys])

    # 2) deniz: kıyı çizgileri alanı böler; deniz noktası içeren parçalar deniz
    coast = json.loads((RAW / "rail_coast.json").read_text(encoding="utf-8"))
    clines = [LineString([proj(g["lon"], g["lat"], a.scale) for g in el["geometry"]])
              for el in coast["elements"] if el.get("tags", {}).get("natural") == "coastline" and "geometry" in el]
    sea = None
    if clines:
        clipped = [l.intersection(area) for l in clines]
        clipped = [g for g in clipped if not g.is_empty]
        pieces = list(polygonize(unary_union(clipped + [area.exterior])))
        # deniz parçası: içinden en fazla 4 yol (iskele vb.) geçen ve en az 0,5 km² olan parçalar (yollar karadadır)
        sea_parts = [p for p in pieces if p.area > 5e5 and sum(1 for k in road_tree.query(p) if lines[k].intersects(p)) < 5]
        print("kıyı parçaları:", len(pieces), "deniz:", len(sea_parts))
        sea = unary_union(sea_parts) if sea_parts else None
    print("deniz alanı (km² oyun):", round(sea.area / 1e6, 2) if sea is not None else 0)

    # 3) hücre sınıflandırması
    C = a.cell
    nx, nz = int((x1 - x0) // C) + 1, int((z1 - z0) // C) + 1
    grid = []
    for i in range(nx):
        col = []
        for j in range(nz):
            cx, cz = x0 + (i + 0.5) * C, z0 + (j + 0.5) * C
            pt = Point(cx, cz)
            if sea is not None and sea.contains(pt):
                col.append(("sea", 0.0))
                continue
            best = "grass"
            for k in ptree.query(pt):
                p, c = polys[k]
                if PRIO[c] > PRIO[best] and p.contains(pt):
                    best = c
            near = min(lines[k].distance(pt) for k in road_tree.query(pt.buffer(C * 1.5))) if len(road_tree.query(pt.buffer(C * 1.5))) else 1e9
            col.append((best, near))
        grid.append(col)
    print("hücre:", nx, "x", nz, Counter(c for col in grid for c, _ in col))

    # 4) sütun parçaları: (sınıf, ağaçlı mı) aynı olan ardışık hücreler
    def key(c, near):
        if c == "sea":
            return None
        trees = c in ("forest", "scrub", "park", "grass") and near > C * 0.75 + 12
        return (c, trees)

    runs = []
    for i, col in enumerate(grid):
        j = 0
        while j < nz:
            k = key(*col[j])
            j2 = j
            while j2 + 1 < nz and key(*col[j2 + 1]) == k:
                j2 += 1
            if k is not None:
                runs.append({"x": round(x0 + (i + 0.5) * C, 2), "z0": round(z0 + j * C, 2),
                             "z1": round(z0 + (j2 + 1) * C, 2), "cls": k[0], "trees": k[1]})
            j = j2 + 1
    meta = {"scale_divisor": a.scale, "cell": C, "bbox": [x0, z0, x1, z1],
            "attribution": "(c) OpenStreetMap contributors, ODbL 1.0"}
    (OUT / f"ground_s{s}.json").write_text(json.dumps({"meta": meta, "runs": runs}, ensure_ascii=False), encoding="utf-8")
    print("parça:", len(runs), Counter((r["cls"], r["trees"]) for r in runs).most_common(12))


if __name__ == "__main__":
    main()
