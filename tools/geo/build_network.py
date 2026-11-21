"""SAKLAZ Türkiye Map - OSM ham verisinden ETS2 editör referans ağı üretir.

Kullanım:
    .venv\\Scripts\\python.exe tools\\geo\\build_network.py [--scale 19]

Girdi : data/raw/*.json  (fetch_osm.py çıktısı)
Çıktı : data/roads/*.geojson, data/cities/*.geojson, data/processed/*.csv|json

Koordinat sistemi:
  WGS84 (EPSG:4326) -> UTM 35N (EPSG:32635, metre) -> oyun koordinatı
  oyun_x = (E - E0) / scale       (+X = doğu)
  oyun_z = -(N - N0) / scale      (+Z = güney, ETS2 kuralı)
  E0/N0 = Gebze place düğümünün UTM koordinatı (gerçek OSM düğümü).
Yükseklik (Y) bu aşamada yoktur (0). Bkz. docs/TECHNICAL_ARCHITECTURE.md.

Veri © OpenStreetMap katkıda bulunanlar, ODbL 1.0.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
import sys as _sys
_sys.stdout.reconfigure(encoding="utf-8")

import networkx as nx
from pyproj import Transformer
from shapely.geometry import LineString, Polygon, mapping
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT_ROADS = ROOT / "data" / "roads"
OUT_CITIES = ROOT / "data" / "cities"
OUT_PROC = ROOT / "data" / "processed"
CONFIG = json.loads((ROOT / "config" / "aoi.json").read_text(encoding="utf-8"))

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32635", always_xy=True)

# OSM sınıfı -> (ETS2 katmanı, öncelik, prototipte mi, önerilen ETS2 yol tipi)
CLASSES = {
    "motorway":       ("otoyol", 1, True, "otoyol 2x3 / 2x2 (bölünmüş)"),
    "trunk":          ("ana_yol", 2, True, "bölünmüş yol 2x2/2x3"),
    "primary":        ("birincil", 3, True, "2x2 bölünmüş veya 1+1"),
    "secondary":      ("ikincil", 4, True, "1+1 şehir/kırsal"),
    "tertiary":       ("ucuncul", 5, True, "1+1 dar"),
    "motorway_link":  ("rampa", 6, True, "tek yön rampa 1 şerit"),
    "trunk_link":     ("rampa", 6, True, "tek yön rampa 1 şerit"),
    "primary_link":   ("rampa", 6, True, "bağlantı kolu"),
    "secondary_link": ("rampa", 6, True, "bağlantı kolu"),
    "tertiary_link":  ("rampa", 6, True, "bağlantı kolu"),
    "unclassified":   ("yerel", 7, False, "1+1 yerel"),
    "residential":    ("yerel", 8, False, "şehir içi"),
    "living_street":  ("yerel", 8, False, "şehir içi"),
    "road":           ("yerel", 8, False, "bilinmeyen"),
    "service":        ("servis", 9, False, "tesis/depo içi"),
}
MAIN = {k for k, v in CLASSES.items() if v[2]}


def norm_ref(ref: str | None) -> list[str]:
    """'D 100;E 80' -> ['D100', 'E80']"""
    if not ref:
        return []
    return [re.sub(r"[\s\-\.]", "", r).upper() for r in ref.split(";") if r.strip()]


def load(name: str) -> list[dict]:
    p = RAW / f"{name}.json"
    if not p.exists():
        raise SystemExit(f"HATA: {p} yok. Önce fetch_osm.py çalıştırın.")
    return json.loads(p.read_text(encoding="utf-8"))["elements"]


def key(pt: dict) -> tuple[int, int]:
    return (round(pt["lat"] * 1e7), round(pt["lon"] * 1e7))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=CONFIG["game"]["scale_divisor"])
    ap.add_argument("--simplify-m", type=float, default=4.0, help="Douglas-Peucker toleransı (gerçek metre)")
    args = ap.parse_args()
    for d in (OUT_ROADS, OUT_CITIES, OUT_PROC):
        d.mkdir(parents=True, exist_ok=True)

    # ---------------- Yerleşimler ve köken
    places = [e for e in load("places") if e["type"] == "node"]
    origin = None
    for p in places:
        t = p.get("tags", {})
        if t.get("name") == "Gebze" and t.get("place") in ("city", "town"):
            origin = p
            break
    if origin is None:
        raise SystemExit("HATA: Gebze place=city/town düğümü bulunamadı.")
    E0, N0 = TO_UTM.transform(origin["lon"], origin["lat"])
    S = args.scale

    def game(lon: float, lat: float) -> tuple[float, float]:
        e, n = TO_UTM.transform(lon, lat)
        return round((e - E0) / S, 2), round(-(n - N0) / S, 2)

    # ---------------- Yollar
    ways = [w for w in load("roads") if w["type"] == "way" and "geometry" in w]
    G = nx.MultiGraph()          # ana ağ (prototip sınıfları)
    G_all = nx.MultiGraph()
    features, editor_rows = [], []
    stats = Counter()
    length_by_class = Counter()
    ref_ways = defaultdict(list)

    for w in ways:
        t = w.get("tags", {})
        hw = t.get("highway")
        if hw not in CLASSES:
            continue
        layer, prio, in_proto, ets_type = CLASSES[hw]
        geom = w["geometry"]
        if len(geom) < 2:
            continue
        utm = [TO_UTM.transform(p["lon"], p["lat"]) for p in geom]
        line = LineString(utm)
        L = line.length
        stats[hw] += 1
        length_by_class[hw] += L
        refs = norm_ref(t.get("ref"))
        for r in refs:
            ref_ways[r].append(w["id"])
        a, b = key(geom[0]), key(geom[-1])
        # tüm ara düğümleri de bağla (OSM kavşakları ara düğümlerde olabilir)
        keys = [key(p) for p in geom]
        for g in ([G_all, G] if in_proto else [G_all]):
            for k1, k2 in zip(keys, keys[1:]):
                g.add_edge(k1, k2, way=w["id"])
        props = {
            "osm_id": w["id"], "highway": hw, "layer": layer, "priority": prio,
            "prototype": in_proto, "ets2_road_type": ets_type,
            "ref": t.get("ref"), "ref_norm": refs, "name": t.get("name"),
            "oneway": t.get("oneway"), "lanes": t.get("lanes"), "maxspeed": t.get("maxspeed"),
            "bridge": t.get("bridge"), "tunnel": t.get("tunnel"), "length_m": round(L, 1),
        }
        features.append({"type": "Feature", "properties": props,
                         "geometry": {"type": "LineString", "coordinates": [[p["lon"], p["lat"]] for p in geom]}})
        if in_proto:
            simp = line.simplify(args.simplify_m, preserve_topology=False)
            inv = Transformer.from_crs("EPSG:32635", "EPSG:4326", always_xy=True)
            for i, (e, n) in enumerate(simp.coords):
                lon, lat = inv.transform(e, n)
                editor_rows.append({
                    "osm_way": w["id"], "seq": i, "highway": hw, "layer": layer,
                    "ref": t.get("ref") or "", "name": t.get("name") or "",
                    "oneway": t.get("oneway") or "", "lanes": t.get("lanes") or "",
                    "lat": round(lat, 7), "lon": round(lon, 7),
                    "utm_e": round(e, 2), "utm_n": round(n, 2),
                    "game_x": round((e - E0) / S, 2), "game_z": round(-(n - N0) / S, 2),
                })

    fc = lambda feats: {"type": "FeatureCollection",
                        "attribution": "(c) OpenStreetMap contributors, ODbL 1.0", "features": feats}
    (OUT_ROADS / "roads_all.geojson").write_text(json.dumps(fc(features), ensure_ascii=False), encoding="utf-8")
    proto = [f for f in features if f["properties"]["prototype"]]
    (OUT_ROADS / "roads_main.geojson").write_text(json.dumps(fc(proto), ensure_ascii=False), encoding="utf-8")
    for tag, fname in (("D100", "d100.geojson"), ("O4", "tem_o4.geojson"), ("O7", "o7.geojson"), ("O5", "o5.geojson")):
        sel = [f for f in features if tag in f["properties"]["ref_norm"]]
        (OUT_ROADS / fname).write_text(json.dumps(fc(sel), ensure_ascii=False), encoding="utf-8")

    with open(OUT_PROC / "editor_roads_main.csv", "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(editor_rows[0].keys()))
        wr.writeheader()
        wr.writerows(editor_rows)

    # ---------------- Bağlantı doğrulama
    comps = sorted(nx.connected_components(G), key=len, reverse=True)
    main_nodes = sum(len(c) for c in comps)
    report = {
        "scale_divisor": S,
        "origin": {"name": "Gebze", "osm_node": origin["id"], "lat": origin["lat"], "lon": origin["lon"],
                   "utm_e": round(E0, 2), "utm_n": round(N0, 2)},
        "way_counts": dict(stats),
        "length_km_real": {k: round(v / 1000, 2) for k, v in length_by_class.items()},
        "length_km_game_main": round(sum(v for k, v in length_by_class.items() if k in MAIN) / 1000 / S, 2),
        "main_network": {
            "nodes": main_nodes, "components": len(comps),
            "largest_component_share": round(len(comps[0]) / main_nodes, 4) if comps else 0,
            "small_components_lt20_nodes": sum(1 for c in comps if len(c) < 20),
        },
        "refs": {},
    }
    for tag in ("D100", "O4", "O7", "O5", "D130", "E80", "E5"):
        ids = set(ref_ways.get(tag, []))
        if not ids:
            report["refs"][tag] = {"ways": 0}
            continue
        sub = nx.MultiGraph()
        L = 0.0
        for f in features:
            if f["properties"]["osm_id"] in ids:
                cs = f["geometry"]["coordinates"]
                ks = [(round(c[1] * 1e7), round(c[0] * 1e7)) for c in cs]
                for k1, k2 in zip(ks, ks[1:]):
                    sub.add_edge(k1, k2)
                L += f["properties"]["length_m"]
        cc = nx.number_connected_components(sub)
        report["refs"][tag] = {"ways": len(ids), "length_km_real_all_carriageways": round(L / 1000, 2),
                               "connected_pieces": cc,
                               "note": "Bölünmüş yolda iki yön ayrı çizildiği için 2 parça normaldir; >2 kopukluk veya bbox kesişi olabilir."}

    # ---------------- Kavşaklar
    jel = load("junctions")
    junctions = []
    for e in jel:
        if e["type"] != "node":
            continue
        t = e.get("tags", {})
        if t.get("highway") == "motorway_junction":
            gx, gz = game(e["lon"], e["lat"])
            junctions.append({"osm_node": e["id"], "type": "motorway_junction", "name": t.get("name") or "",
                              "ref": t.get("ref") or "", "lat": e["lat"], "lon": e["lon"], "game_x": gx, "game_z": gz})
    # ana ağda derece >= 3 olan düğümler: kavşak/prefab adayları
    deg_nodes = [n for n in G.nodes if len(set(G.neighbors(n))) >= 3]
    for n in deg_nodes:
        lat, lon = n[0] / 1e7, n[1] / 1e7
        gx, gz = game(lon, lat)
        junctions.append({"osm_node": "", "type": "intersection_deg3plus", "name": "", "ref": "",
                          "lat": lat, "lon": lon, "game_x": gx, "game_z": gz})
    rabout = sum(1 for e in jel if e["type"] == "way" and e.get("tags", {}).get("junction") == "roundabout")
    with open(OUT_PROC / "junctions.csv", "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(junctions[0].keys()))
        wr.writeheader()
        wr.writerows(junctions)
    report["junctions"] = {
        "motorway_junction": sum(1 for j in junctions if j["type"] == "motorway_junction"),
        "intersections_deg3plus_main": len(deg_nodes),
        "roundabout_ways": rabout,
    }

    # ---------------- Sanayi / lojistik alanları
    land = load("landuse")
    ind_feats, ind_rows = [], []
    for e in land:
        t = e.get("tags", {})
        lu = t.get("landuse") or ("industrial" if "industrial" in t else None) or ("warehouse" if t.get("building") == "warehouse" else None)
        if lu not in ("industrial", "port", "warehouse", "commercial"):
            continue
        polys = []
        if e["type"] == "way" and len(e.get("geometry", [])) >= 4:
            polys.append(Polygon([TO_UTM.transform(p["lon"], p["lat"]) for p in e["geometry"]]))
        elif e["type"] == "relation":
            for m in e.get("members", []):
                if m.get("role") == "outer" and len(m.get("geometry", [])) >= 4:
                    try:
                        polys.append(Polygon([TO_UTM.transform(p["lon"], p["lat"]) for p in m["geometry"]]))
                    except ValueError:
                        pass
        polys = [p.buffer(0) for p in polys if p.is_valid or p.buffer(0).is_valid]
        if not polys:
            continue
        poly = unary_union(polys)
        area = poly.area
        if area < 2000 and not t.get("name"):
            continue
        c = poly.representative_point()
        inv = Transformer.from_crs("EPSG:32635", "EPSG:4326", always_xy=True)
        lon, lat = inv.transform(c.x, c.y)
        gx, gz = round((c.x - E0) / S, 2), round(-(c.y - N0) / S, 2)
        row = {"osm_type": e["type"], "osm_id": e["id"], "kind": lu, "industrial": t.get("industrial") or "",
               "name": t.get("name") or "", "operator": t.get("operator") or "",
               "area_ha": round(area / 10000, 2), "lat": round(lat, 7), "lon": round(lon, 7),
               "game_x": gx, "game_z": gz}
        ind_rows.append(row)
        from shapely.ops import transform as stransform
        geom_wgs = stransform(lambda x, y, z=None: inv.transform(x, y), poly)
        ind_feats.append({"type": "Feature", "properties": row, "geometry": mapping(geom_wgs)})
    ind_rows.sort(key=lambda r: (-bool(r["name"]), -r["area_ha"]))
    (OUT_CITIES / "industrial.geojson").write_text(json.dumps(fc(ind_feats), ensure_ascii=False), encoding="utf-8")
    with open(OUT_PROC / "industrial_sites.csv", "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(ind_rows[0].keys()))
        wr.writeheader()
        wr.writerows(ind_rows)
    report["industrial"] = {"sites": len(ind_rows), "named": sum(1 for r in ind_rows if r["name"]),
                            "osb_like": [r["name"] for r in ind_rows if re.search(r"OSB|Organize|Sanayi|Lojistik|Liman", r["name"], re.I)][:60]}

    # ---------------- Yerleşimler
    pl_rows, pl_feats = [], []
    for p in places:
        t = p.get("tags", {})
        gx, gz = game(p["lon"], p["lat"])
        row = {"osm_node": p["id"], "name": t.get("name") or "", "place": t.get("place"),
               "population": t.get("population") or "", "lat": p["lat"], "lon": p["lon"], "game_x": gx, "game_z": gz}
        pl_rows.append(row)
        pl_feats.append({"type": "Feature", "properties": row, "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]}})
    order = {"city": 0, "town": 1, "suburb": 2, "quarter": 3, "village": 4, "neighbourhood": 5, "hamlet": 6}
    pl_rows.sort(key=lambda r: (order.get(r["place"], 9), r["name"]))
    (OUT_CITIES / "places.geojson").write_text(json.dumps(fc(pl_feats), ensure_ascii=False), encoding="utf-8")
    with open(OUT_PROC / "places.csv", "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(pl_rows[0].keys()))
        wr.writeheader()
        wr.writerows(pl_rows)
    report["places"] = [r["name"] + f" ({r['place']})" for r in pl_rows if r["place"] in ("city", "town", "suburb")]

    # ---------------- Kapsam (oyun birimiyle)
    xs = [r["game_x"] for r in editor_rows]
    zs = [r["game_z"] for r in editor_rows]
    report["game_extent_main"] = {"x_min": min(xs), "x_max": max(xs), "z_min": min(zs), "z_max": max(zs),
                                  "width_m": round(max(xs) - min(xs), 1), "height_m": round(max(zs) - min(zs), 1)}
    (OUT_PROC / "network_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2)[:6000])


if __name__ == "__main__":
    main()
