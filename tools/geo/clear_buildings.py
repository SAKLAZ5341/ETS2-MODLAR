"""Bina yerleşimini seçer: OSM bina izleri + OSM'de bina olmayan yerleşim alanlarına sokak boyu dolgu.

Kurallar:
1. Binalar güncel yollara (map_graph_s3.json), kavşaklara ve depolara taşmaz.
2. Gerçek boyutlu oyun modelleri 1:3 ölçekli şehre konduğu için çakışma, OSM izine göre değil SEÇİLEN MODELİN
   boyutuna göre denetlenir (model kare ayak izi, %85).
3. Öncelik: ana caddeye bakan OSM binaları, sonra büyükten küçüğe OSM binaları, sonra dolgu (konut/ticari/sanayi
   alanında, OSM binası olmayan sokak kenarları).
4. Bütçe: editörde yeniden hesaplama yer tutucu modelle yapılır (tools/mapgen buildgraph + SAKLAZ_PLACEHOLDER,
   sonra swapmodels); editör sınırı yer tutucu SAYISINA bağlıdır → --max-count.
Çıktı: data/processed/map_export_s3_clear.json (mapgen buildgraph'ın 3. argümanı).
Kullanım: python tools/geo/clear_buildings.py [--max-count 8000] [--no-fill] [--mid]
"""
import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union
from shapely.prepared import prep
from shapely.strtree import STRtree

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
HALF = {"hw3_divided": 12, "hw2_oneway": 5, "hw3_oneway": 7, "hw4_oneway": 9, "r2_divided": 8,
        "ramp_1lane": 4, "r1_city": 5, "r1_city_narrow": 5, "service": 4}
T = Transformer.from_crs("EPSG:4326", "EPSG:32635", always_xy=True)
E0, N0 = 705139.33, 4519475.38
sys.path.insert(0, str(Path(__file__).resolve().parent))
import warp as WARP  # noqa: E402  çekirdek büyütme


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


def polys_of(el, g):
    out = []
    if el["type"] == "way" and "geometry" in el and len(el["geometry"]) >= 4:
        pts = [g(*T.transform(p["lon"], p["lat"])) for p in el["geometry"]]
        if pts[0] == pts[-1]:
            p = Polygon(pts).buffer(0)
            if not p.is_empty:
                out.append(p)
    elif el["type"] == "relation":
        lines = [LineString([g(*T.transform(q["lon"], q["lat"])) for q in m["geometry"]])
                 for m in el.get("members", []) if m.get("role") in ("outer", "") and "geometry" in m]
        if lines:
            out += [p for p in polygonize(unary_union(lines)) if p.area > 0]
    return out


def osm_buildings(path, S, have_ids):
    if not path.exists():
        return []
    g = lambda x, y: WARP.proj(x, y, E0, N0, S)
    out = []
    for el in json.loads(path.read_text(encoding="utf-8"))["elements"]:
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
    ap.add_argument("--max-count", type=int, default=8000, help="toplam bina (editör yer tutucu sınırı)")
    ap.add_argument("--no-fill", action="store_true", help="OSM dışı dolgu binası üretme")
    ap.add_argument("--mid", action="store_true", help="ana cadde dışında az parçalı mid model (eski davranış)")
    ap.add_argument("--fill-step", type=float, default=14.0, help="dolgu: sokak boyunca aralık (oyun m)")
    ap.add_argument("--center-fill", type=float, default=700.0,
                    help="ilçe merkezine bu uzaklıktaki (oyun m) sokaklarda arazi etiketi olmasa da dolgu")
    a = ap.parse_args()
    cfg = json.loads((ROOT / "tools/mapgen/mapping.json").read_text(encoding="utf-8"))["buildings"]
    dims = {r["token"]: (float(r["dx"]), float(r["dz"])) for r in
            csv.DictReader(open(ROOT / "data/processed/game_defs/building_model_costs.csv", encoding="utf-8"))}
    dims.setdefault("250", (40.0, 50.0))  # meydan döşemesi (pavement_plaza1, modelinfo)

    def model_of(b):
        if b.get("models"):
            return b["models"][b.get("alt", 0) % len(b["models"])].split("|")[0]
        if b.get("alt_model"):
            return b["alt_model"].split("|")[0]
        key = model_key(b)
        if not b.get("near_main") and key + "_far" in cfg:
            key += "_far"
        arr = cfg[key]
        return arr[(abs(b["osm"]) // 7) % len(arr)].split("|")[0]

    def footprint(b):
        dx, dz = dims.get(model_of(b), (14.0, 14.0))
        r = max(dx, dz) / 2 * 0.85
        return Point(b["x"], b["z"]).buffer(r, cap_style=3)

    g = json.loads((ROOT / "data/processed/map_graph_s3.json").read_text(encoding="utf-8"))
    ex = json.loads((ROOT / "data/processed/map_export_s3.json").read_text(encoding="utf-8"))
    S = g["meta"]["scale_divisor"]
    gfun = lambda x, y: WARP.proj(x, y, E0, N0, S)
    roads = [LineString(e["pts"]).buffer(HALF.get(e["type"], 5) + 0.5) for e in g["edges"]]
    for j in g["junctions"] + g["hw_junctions"]:
        roads.append(Point(j["x"], j["z"]).buffer(22))
    for d in g.get("depots", []):
        roads.append(LineString([d["n0"], d["n1"]]).buffer(20).union(Point(*d["body"]).buffer(65)))
    rtree = STRtree(roads)
    mains = [LineString(e["pts"]) for e in g["edges"] if e["type"] in ("r2_divided", "r1_city")]
    mtree = STRtree(mains)

    # aday binalar
    for b in ex["buildings"]:  # map_export_s3.json çarpıtmasız 1:3 koordinatta → çekirdek büyütme
        b["x"], b["z"] = (round(v, 3) for v in WARP.warp(b["x"], b["z"]))
    core_b = [b for b in ex["buildings"] if b.get("place", True) or True]
    for b in core_b:
        b["place"] = True
    have = {b["osm"] for b in ex["buildings"]}
    prov = osm_buildings(RAW / "kocaeli" / "buildings.json", S, have)
    osm = core_b + prov
    for b in osm:
        fp0 = Point(b["x"], b["z"]).buffer(8)
        b["near_main"] = any(mains[q].distance(fp0) < 22 for q in mtree.query(fp0.buffer(22)))
    if not a.mid:
        for b in osm:
            b["near_main"] = True  # yer tutucu yöntemiyle parça bütçesi yok: hepsi ayrıntılı (Türk/Balkan) model
    osm.sort(key=lambda b: (not b["near_main"], -b["area_real_m2"]))

    # Bilinen yerler (fetch_kocaeli landmarks): AVM, hastane, belediye, meydan → kendi modeliyle, en önce
    LM = {"mall": cfg.get("lm_mall"), "hospital": cfg.get("lm_hospital"), "townhall": cfg.get("lm_townhall"),
          "square": cfg.get("lm_square")}
    lms = []
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import landmarks as lmmod
    all_lines = [LineString(e["pts"]) for e in g["edges"] if e["type"] in ("r1_city", "r1_city_narrow", "r2_divided")]
    ltree = STRtree(all_lines)
    for kind, name, ux_, uy_, lid in lmmod.load(lambda lo, la: T.transform(lo, la)):
        if not LM.get(kind):
            continue
        x, z = gfun(ux_, uy_)
        P = Point(x, z)
        i = ltree.nearest(P)
        ln = all_lines[i]
        if ln.distance(P) > 120:
            continue  # yol ağının dışında (il dışı)
        Q = ln.interpolate(ln.project(P))
        dx, dz = x - Q.x, z - Q.y
        L = math.hypot(dx, dz) or 1
        nx, nz = dx / L, dz / L  # yoldan binaya doğru
        ang = math.degrees(math.atan2(-nx, -nz))  # ön yüz yola
        for k in range(len(LM[kind])):
            for push in (0, 15, 30, 45):
                lms.append({"osm": -(10 ** 12) - lid * 10 - k * 4 - push // 15, "kind": kind, "models": LM[kind], "alt": k,
                            "x": round(x + nx * push, 3), "z": round(z + nz * push, 3), "heading_deg": round(ang, 1),
                            "len": 30, "wid": 30, "area_real_m2": 1e9, "near_main": True, "place": True,
                            "landmark": lid, "name": name})
    print(f"bilinen yer adayı: {len({b['landmark'] for b in lms})}")

    # dolgu adayları: yerleşim alanındaki sokak kenarları
    fill = []
    if not a.no_fill:
        areas = []
        for f in (RAW / "landuse.json", RAW / "kocaeli" / "nature.json", RAW / "kocaeli" / "landuse.json"):
            if not f.exists():
                continue
            for el in json.loads(f.read_text(encoding="utf-8"))["elements"]:
                lu = el.get("tags", {}).get("landuse")
                if lu in ("residential", "commercial", "retail", "industrial"):
                    areas += [(p, lu) for p in polys_of(el, gfun) if p.area > 400]
        atree = STRtree([p for p, _ in areas])
        aprep = [prep(p) for p, _ in areas]
        fid = -1
        centers = [tuple(c["center"]) for c in g.get("cities", []) if c.get("center")]
        for e in g["edges"]:
            if e["type"] not in ("r1_city", "r1_city_narrow", "r2_divided"):
                continue
            ln = LineString(e["pts"])
            L = ln.length
            k = a.fill_step / 2
            while k < L - a.fill_step / 2:
                p = ln.interpolate(k)
                q = ln.interpolate(min(k + 1, L))
                dx, dz = q.x - p.x, q.y - p.y
                n = math.hypot(dx, dz) or 1
                ux, uz = dx / n, dz / n
                for sgn in (1, -1):
                    off = HALF.get(e["type"], 5) + 10.5
                    cx, cz = p.x - uz * off * sgn, p.y + ux * off * sgn
                    pt = Point(cx, cz)
                    hit = [i for i in atree.query(pt) if aprep[i].contains(pt)]
                    if not hit:
                        if not any(math.dist((cx, cz), c_) < a.center_fill for c_ in centers):
                            continue
                        lu = "residential"  # merkez çevresi: etiketsiz yerleşim
                    else:
                        lu = areas[hit[0]][1]
                    kind = {"industrial": "industrial", "commercial": "commercial", "retail": "commercial"}.get(lu)
                    h = int(abs(cx * 7.31 + cz * 3.17)) % 10
                    if kind is None:
                        kind = "apartments" if h < 6 else "house"
                    ang = math.degrees(math.atan2(uz, ux))
                    fill.append({"osm": fid, "kind": kind, "levels": None, "x": round(cx, 3), "z": round(cz, 3),
                                 "heading_deg": round(ang + (180 if sgn < 0 else 0), 1), "len": 12, "wid": 10,
                                 "area_real_m2": 300, "near_main": True, "place": True, "fill": True})
                    fid -= 1
                k += a.fill_step
        if a.mid:
            for b in fill:
                b["near_main"] = False

    # yerleştirme: yollara taşmayan, birbirine çakışmayan; ızgara ile hızlı çakışma denetimi
    cell = 40.0
    grid = defaultdict(list)
    kept, off_road, overlap = [], 0, 0
    # küçük model yedeği: seçilen model sığmazsa en küçük iki ev modeli denenir (1:3 şehirde gerçek boyutlu modeller
    # yola taştığı için OSM binalarının çoğu eleniyordu)
    smalls = sorted(cfg.get("small_house", []), key=lambda m: (lambda d: d[0] * d[1])(dims.get(m.split("|")[0], (99, 99))))[:2]
    done_lm = set()

    def fits(b):
        fp = footprint(b)
        if any(roads[q].intersects(fp) for q in rtree.query(fp)):
            return None, "road"
        x0, z0, x1, z1 = fp.bounds
        cells = [(i, j) for i in range(int(x0 // cell), int(x1 // cell) + 1) for j in range(int(z0 // cell), int(z1 // cell) + 1)]
        if any(o.intersects(fp) for c in cells for o in grid[c]):
            return None, "overlap"
        return (fp, cells), None
    for b in lms + osm + fill:
        if len(kept) >= a.max_count:
            break
        if b.get("landmark") is not None and b["landmark"] in done_lm:
            continue
        ok, why = fits(b)
        if ok is None and b.get("landmark") is None and b.get("kind") not in ("industrial", "mosque"):
            for m in smalls:
                b["alt_model"] = m
                ok, why2 = fits(b)
                if ok is not None:
                    break
            if ok is None:
                b.pop("alt_model", None)
        if ok is None:
            if why == "road":
                off_road += 1
            else:
                overlap += 1
            continue
        fp, cells = ok
        for c in cells:
            grid[c].append(fp)
        kept.append(b)
        if b.get("landmark") is not None:
            done_lm.add(b["landmark"])
    print(f"bilinen yer yerleşti: {len(done_lm)} / {len({b['landmark'] for b in lms})}")
    ids = {b["osm"] for b in kept}
    for b in ex["buildings"]:
        b["place"] = b["osm"] in ids
    for b in kept:  # seçilen yedek/simge modeli export'a yazılır
        if b.get("models"):
            b["model"] = b["models"][b.get("alt", 0) % len(b["models"])]
        elif b.get("alt_model"):
            b["model"] = b["alt_model"]
    ex["buildings"] += [b for b in prov + fill + lms if b["osm"] in ids]
    (ROOT / "data/processed/map_export_s3_clear.json").write_text(json.dumps(ex, ensure_ascii=False), encoding="utf-8")
    print(f"bina: {len(kept)} (OSM {sum(1 for b in kept if not b.get('fill'))}, dolgu {sum(1 for b in kept if b.get('fill'))}); "
          f"aday OSM {len(osm)}, dolgu {len(fill)}; yola taşan {off_road}, çakışan {overlap}")


if __name__ == "__main__":
    main()
