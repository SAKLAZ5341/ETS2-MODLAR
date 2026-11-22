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


def load_elements(name):
    """Çekirdek (data/raw) + il geneli (data/raw/kocaeli) öğeleri, kimliğe göre tekil."""
    out, seen = [], set()
    for f in (RAW / f"{name}.json", RAW / "kocaeli" / f"{name}.json"):
        if f.exists():
            for el in json.loads(f.read_text(encoding="utf-8"))["elements"]:
                if (el["type"], el["id"]) not in seen:
                    seen.add((el["type"], el["id"]))
                    out.append(el)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=3.0)
    ap.add_argument("--cell", type=float, default=96.0, help="çekirdek hücre kenarı (oyun m)")
    ap.add_argument("--outer-cell", type=float, default=512.0, help="il geneli hücre kenarı (oyun m)")
    ap.add_argument("--outer-reach", type=float, default=900.0, help="il geneli: yola en çok bu kadar uzak hücre (oyun m)")
    ap.add_argument("--margin", type=float, default=300.0, help="yol ağının dışına taşma (oyun m)")
    ap.add_argument("--smooth", type=int, default=2, help="çoğunluk filtresi tekrar sayısı")
    ap.add_argument("--core-from", default="data/processed/ground_core_s3.json",
                    help="çekirdek zemini bu dosyadan aynen al (bbox = çekirdek kutusu); yoksa yeniden üret. "
                         "Yeniden üretilen geniş çekirdek zemini editörü 'Index outside array boundaries: 12 >= 12' ile çökertti")
    a = ap.parse_args()
    s = int(a.scale)

    graph = json.loads((OUT / f"map_graph_s{s}.json").read_text(encoding="utf-8"))
    lines = [LineString(e["pts"]) for e in graph["edges"] if len(e["pts"]) >= 2]
    xs = [p[0] for e in graph["edges"] for p in e["pts"]]
    zs = [p[1] for e in graph["edges"] for p in e["pts"]]
    X0, X1 = min(xs) - a.margin, max(xs) + a.margin
    Z0, Z1 = min(zs) - a.margin, max(zs) + a.margin
    cxs = [p[0] for e in graph["edges"] if not e.get("outer") for p in e["pts"]]
    czs = [p[1] for e in graph["edges"] if not e.get("outer") for p in e["pts"]]
    core = (min(cxs) - a.margin, min(czs) - a.margin, max(cxs) + a.margin, max(czs) + a.margin)
    core_runs = None
    cf = ROOT / a.core_from if a.core_from else None
    if cf is not None and cf.exists():
        cg = json.loads(cf.read_text(encoding="utf-8"))
        core, core_runs = tuple(cg["meta"]["bbox"]), cg["runs"]
        print("çekirdek zemini:", cf.name, len(core_runs), "parça")
    road_tree = STRtree(lines)
    area = box(X0, Z0, X1, Z1)

    # 1) sınıf poligonları
    polys: list[tuple[Polygon, str]] = []
    for el in load_elements("nature"):
        tags = el.get("tags", {})
        cls = next((c for (k, v), c in NATURE.items() if tags.get(k) == v), None)
        if tags.get("landuse") in ("residential", "industrial"):
            cls = "urban"
        if cls:
            polys += [(p, cls) for p in geom_polys(el, a.scale) if p.intersects(area)]
    for el in load_elements("landuse"):
        if el.get("tags", {}).get("landuse") or el.get("tags", {}).get("industrial"):
            polys += [(p, "urban") for p in geom_polys(el, a.scale) if p.intersects(area)]
    print("sınıf poligonları:", Counter(c for _, c in polys))
    ptree = STRtree([p for p, _ in polys])

    # 2) deniz: kıyı çizgileri alanı böler; deniz noktası içeren parçalar deniz
    clines = [LineString([proj(g["lon"], g["lat"], a.scale) for g in el["geometry"]])
              for el in load_elements("rail_coast") if el.get("tags", {}).get("natural") == "coastline" and "geometry" in el]
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
    from shapely.prepared import prep
    sea_p = prep(sea) if sea is not None else None

    def classify(x0, z0, nx, nz, C, outer, sea_runs=False, sea_only=False):
        grid = []
        for i in range(nx):
            col = []
            for j in range(nz):
                cx, cz = x0 + (i + 0.5) * C, z0 + (j + 0.5) * C
                pt = Point(cx, cz)
                if outer and core[0] <= cx <= core[2] and core[1] <= cz <= core[3]:
                    col.append(("skip", 0.0))
                    continue
                if sea_p is not None and sea_p.contains(pt):
                    col.append(("sea", 0.0) if not sea_runs else ("seawater", 0.0))
                    continue
                if sea_only:
                    col.append(("skip", 0.0))
                    continue
                q = road_tree.query(pt.buffer(a.outer_reach if outer else C * 1.5))
                near = min(lines[k].distance(pt) for k in q) if len(q) else 1e9
                if outer and near > a.outer_reach:
                    col.append(("skip", 0.0))
                    continue
                best = "grass"
                for k in ptree.query(pt):
                    p, c = polys[k]
                    if PRIO[c] > PRIO[best] and p.contains(pt):
                        best = c
                col.append((best, near))
            grid.append(col)
        # çoğunluk filtresi: tek başına kalan hücreleri komşularına uydur (daha doğal sınırlar, daha az parça)
        for _ in range(a.smooth):
            g2 = [list(col) for col in grid]
            for i in range(nx):
                for j in range(nz):
                    c, near = grid[i][j]
                    if c in ("sea", "skip", "seawater"):
                        continue
                    nb = Counter(grid[i + di][j + dj][0] for di in (-1, 0, 1) for dj in (-1, 0, 1)
                                 if 0 <= i + di < nx and 0 <= j + dj < nz and grid[i + di][j + dj][0] not in ("sea", "skip", "seawater"))
                    top, n = nb.most_common(1)[0]
                    if top != c and n >= 5 and c != "water":
                        g2[i][j] = (top, near)
            grid = g2
        print("hücre:", nx, "x", nz, "C", C, Counter(c for col in grid for c, _ in col))

        def key(c, near):
            if c in ("sea", "skip"):
                return None
            if c == "seawater":
                return ("water", False, "sea")
            if outer:  # il geneli: yalnız orman ağaçlı (çizim bütçesi)
                return (c, c == "forest" and near > 40)
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
                    r = {"x": round(x0 + (i + 0.5) * C, 2), "z0": round(z0 + j * C, 2),
                         "z1": round(z0 + (j2 + 1) * C, 2), "cls": k[0], "trees": k[1], "w": C / 2}
                    if len(k) > 2:  # deniz: su malzemesi, kıyıdan alçakta (boşluk/gökyüzü görünmesin)
                        r["y"] = -2.5
                        r["sea"] = True
                    if outer:
                        r["dens"] = 0.35
                    runs.append(r)
                j = j2 + 1
        return runs

    C = a.cell
    runs = core_runs if core_runs is not None else         classify(core[0], core[1], int((core[2] - core[0]) // C) + 1, int((core[3] - core[1]) // C) + 1, C, False)
    nc = len(runs)
    CO = a.outer_cell
    runs += classify(X0, Z0, int((X1 - X0) // CO) + 1, int((Z1 - Z0) // CO) + 1, CO, True, sea_runs=True)
    # çekirdek kutusundaki deniz (çekirdek zemini dosyadan geldiği için denizi yok): yalnız deniz hücreleri
    CS = 384.0
    runs += classify(core[0], core[1], int((core[2] - core[0]) // CS) + 1, int((core[3] - core[1]) // CS) + 1, CS, False,
                     sea_runs=True, sea_only=True)
    meta = {"scale_divisor": a.scale, "cell": C, "outer_cell": CO, "bbox": [X0, Z0, X1, Z1], "core": core,
            "attribution": "(c) OpenStreetMap contributors, ODbL 1.0"}
    (OUT / f"ground_s{s}.json").write_text(json.dumps({"meta": meta, "runs": runs}, ensure_ascii=False), encoding="utf-8")
    print("parça: çekirdek", nc, "il geneli", len(runs) - nc,
          "uzunluk toplamı (km)", round(sum(r["z1"] - r["z0"] for r in runs) / 1000, 1))


if __name__ == "__main__":
    main()
