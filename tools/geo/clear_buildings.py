"""Bina yerleşimini güncel yol ağına ve editörün çizim bütçesine göre seçer.

1. Güncel yollara (map_graph_s3.json) ve kavşaklara taşan binalar çıkarılır (yollar bölünmüş cadde indirgemesi ile
   kaydı; önizlemede kamyon binaya çarptı, 2026-11-22).
2. İl geneli: data/raw/kocaeli/buildings.json (ilçe merkezleri) varsa çekirdek binalarına eklenir.
3. Bütçe: editör "Parameter packet batch system overflow" sınırı yol segmentleri + model parçalarıyla dolar
   (ölçüm: 13,2 bin segment + 21,6 bin parça açıldı, 18,8 bin + 21,6 bin çöktü, 18,8 bin + 0 açıldı).
   Ayrıntılı (yakın) model yalnız ana caddeye bakan en büyük --close binada; gerisi az parçalı "mid" model.
   Toplam parça --budget'ı aşmaz; öncelik: ana cadde, sonra büyük alan.
Çıktı: data/processed/map_export_s3_clear.json (mapgen buildgraph'ın 3. argümanı).
Kullanım: python tools/geo/clear_buildings.py [--budget 11000] [--close 150]
"""
import argparse
import csv
import json
import math
import sys
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, Polygon
from shapely.strtree import STRtree

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
HALF = {"hw3_divided": 12, "hw2_oneway": 5, "hw3_oneway": 7, "hw4_oneway": 9, "r2_divided": 8,
        "ramp_1lane": 4, "r1_city": 5, "r1_city_narrow": 5, "service": 4}
T = Transformer.from_crs("EPSG:4326", "EPSG:32635", always_xy=True)
E0, N0 = 705139.33, 4519475.38


def model_key(b):
    kind = b["kind"] or "yes"
    if kind in ("industrial", "warehouse", "factory", "manufacture"):
        return "industrial"
    if kind in ("commercial", "retail", "office", "supermarket"):
        return "commercial"
    if kind in ("apartments", "residential"):
        return "apartment"
    if kind in ("house", "detached", "semidetached_house", "bungalow", "terrace"):
        return "small_house"
    if kind in ("mosque", "religious"):
        return "mosque"
    return "apartment" if b["area_real_m2"] > 250 else "small_house"


def province_buildings(S, have_ids):
    f = ROOT / "data/raw/kocaeli/buildings.json"
    if not f.exists():
        return []
    g = lambda x, y: ((x - E0) / S, -(y - N0) / S)
    out = []
    for el in json.loads(f.read_text(encoding="utf-8"))["elements"]:
        if el["id"] in have_ids or "geometry" not in el or len(el["geometry"]) < 4:
            continue
        try:
            poly = Polygon([T.transform(p["lon"], p["lat"]) for p in el["geometry"]]).buffer(0)
        except ValueError:
            continue
        if poly.is_empty or poly.area < 60:
            continue
        xs = list(poly.minimum_rotated_rectangle.exterior.coords)
        e1, e2 = (xs[0], xs[1]), (xs[1], xs[2])
        l1, l2 = math.dist(*e1), math.dist(*e2)
        le = e1 if l1 >= l2 else e2
        ang = math.degrees(math.atan2(le[1][1] - le[0][1], le[1][0] - le[0][0]))
        c = poly.centroid
        x, z = g(c.x, c.y)
        t = el.get("tags", {})
        out.append({"osm": el["id"], "kind": t.get("building", "yes"), "levels": t.get("building:levels"),
                    "x": round(x, 3), "z": round(z, 3), "heading_deg": round(-ang, 1),
                    "len": round(max(l1, l2) / S, 2), "wid": round(min(l1, l2) / S, 2),
                    "area_real_m2": round(poly.area), "near_main": False, "place": True, "province": True})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=11000, help="toplam model parçası")
    ap.add_argument("--close", type=int, default=150, help="ayrıntılı (yakın) model alan bina sayısı")
    a = ap.parse_args()
    cfg = json.loads((ROOT / "tools/mapgen/mapping.json").read_text(encoding="utf-8"))["buildings"]
    pieces = {r["token"]: int(r["pieces"]) for r in
              csv.DictReader(open(ROOT / "data/processed/game_defs/building_model_costs.csv", encoding="utf-8"))}

    def cost(b):
        key = model_key(b)
        if not b.get("near_main") and key + "_far" in cfg:
            key += "_far"
        arr = cfg[key]
        return pieces.get(arr[(abs(b["osm"]) // 7) % len(arr)].split("|")[0], 10)

    g = json.loads((ROOT / "data/processed/map_graph_s3.json").read_text(encoding="utf-8"))
    ex = json.loads((ROOT / "data/processed/map_export_s3.json").read_text(encoding="utf-8"))
    S = g["meta"]["scale_divisor"]
    roads = [LineString(e["pts"]).buffer(HALF.get(e["type"], 5) + 0.5) for e in g["edges"]]
    for j in g["junctions"] + g["hw_junctions"]:
        roads.append(LineString([(j["x"], j["z"]), (j["x"] + 0.1, j["z"])]).buffer(20))
    for d in g.get("depots", []):  # depo alanı
        roads.append(LineString([d["n0"], d["n1"]]).buffer(20).union(
            LineString([d["body"], d["body"]]).buffer(60)))
    tree = STRtree(roads)
    mains = [LineString(e["pts"]) for e in g["edges"] if e["type"] in ("r2_divided", "r1_city")]
    mtree = STRtree(mains)

    blds = [b for b in ex["buildings"] if b.get("place", True)]
    prov = province_buildings(S, {b["osm"] for b in ex["buildings"]})
    cand, foot = [], []
    off = 0
    for b in blds + prov:
        x, z, h = b["x"], b["z"], math.radians(b["heading_deg"])
        L, W = b.get("len", 10) / 2 * 0.85, b.get("wid", 10) / 2 * 0.85
        c, s = math.cos(h), math.sin(h)
        poly = Polygon([(x + dx * c - dz * s, z + dx * s + dz * c) for dx, dz in ((-L, -W), (L, -W), (L, W), (-L, W))])
        if any(roads[q].intersects(poly) for q in tree.query(poly)):
            off += 1
            continue
        if b.get("province"):
            b["near_main"] = any(mains[q].distance(poly) < 12 for q in mtree.query(poly.buffer(12)))
        cand.append(b)
        foot.append(poly)
    # il geneli binalar birbirine yakınsa (gerçek boyutlu model 1:3 şehre sığmaz) büyük olan kalır
    order = sorted(range(len(cand)), key=lambda i: (not cand[i].get("near_main"), -cand[i]["area_real_m2"]))
    kept, ktree_polys = [], []
    from shapely.strtree import STRtree as _T
    taken = []
    close_left, total = a.close, 0
    for i in order:
        b, poly = cand[i], foot[i]
        if b.get("province") and any(p.distance(poly) < 4 for p in taken[-400:] if p.distance(poly) < 30):
            continue
        if b.get("near_main"):
            if close_left > 0:
                close_left -= 1
            else:
                b["near_main"] = False  # bütçe: az parçalı mid model
        k = cost(b)
        if total + k > a.budget:
            continue
        total += k
        b["place"] = True
        kept.append(b)
        if b.get("province"):
            taken.append(poly)
    keep_ids = {b["osm"] for b in kept}
    for b in ex["buildings"]:
        b["place"] = b["osm"] in keep_ids and b.get("place", True)
    ex["buildings"] += [b for b in prov if b["osm"] in keep_ids]
    (ROOT / "data/processed/map_export_s3_clear.json").write_text(json.dumps(ex, ensure_ascii=False), encoding="utf-8")
    print(f"yola taşan bina çıkarıldı: {off}; seçilen {len(kept)} (il geneli {sum(1 for b in kept if b.get('province'))}, "
          f"ayrıntılı {a.close - close_left}), parça {total}/{a.budget}")


if __name__ == "__main__":
    main()
