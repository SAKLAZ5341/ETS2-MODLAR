"""SAKLAZ Türkiye Map - 0.1.0 prototip koridorunu ve editör düğüm listelerini üretir.

Kullanım:
    .venv\\Scripts\\python.exe tools\\geo\\build_prototype.py [--scale 19] [--node-spacing 40]

Prototip kapsamı (öncelik sırasıyla):
  P1  D-100: Çayırova - Gebze (iki yön)
  P2  D-100 <-> TEM (O-4) bağlantısı (OSM ana ağında gerçek en kısa yol)
  P3  Darıca merkez <-> D-100 bağlantısı (gerçek en kısa yol)
  P4  Gebze merkez <-> D-100 bağlantısı

Tüm noktalar gerçek OSM geometrisidir; yalnızca sadeleştirme ve yeniden örnekleme yapılır.
Çıktı: data/processed/prototype/*.csv, *.geojson, prototype_summary.json, docs/img/*.png

Veri © OpenStreetMap katkıda bulunanlar, ODbL 1.0.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
import sys as _sys
_sys.stdout.reconfigure(encoding="utf-8")

import networkx as nx
from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import linemerge, unary_union

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "prototype"
IMG = ROOT / "docs" / "img"
CONFIG = json.loads((ROOT / "config" / "aoi.json").read_text(encoding="utf-8"))
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32635", always_xy=True)
TO_WGS = Transformer.from_crs("EPSG:32635", "EPSG:4326", always_xy=True)

MAIN = {"motorway", "trunk", "primary", "secondary", "tertiary", "motorway_link", "trunk_link",
        "primary_link", "secondary_link", "tertiary_link"}
CONNECT = MAIN | {"unclassified", "residential"}
STYLE = {  # çizim rengi, kalınlık
    "motorway": ("#c0392b", 2.4), "trunk": ("#e67e22", 2.0), "primary": ("#f1c40f", 1.6),
    "secondary": ("#27ae60", 1.2), "tertiary": ("#7f8c8d", 0.8),
}


def norm_ref(ref):
    return [re.sub(r"[\s\-\.]", "", r).upper() for r in (ref or "").split(";") if r.strip()]


def load(name):
    return json.loads((RAW / f"{name}.json").read_text(encoding="utf-8"))["elements"]


def place(places, name):
    order = {"city": 0, "town": 1, "suburb": 2, "quarter": 3, "village": 4, "neighbourhood": 5}
    c = [p for p in places if p.get("tags", {}).get("name") == name]
    c.sort(key=lambda p: order.get(p["tags"].get("place"), 9))
    if not c:
        raise SystemExit(f"HATA: '{name}' yerleşim düğümü OSM'de bulunamadı")
    return c[0]


def resample(coords, spacing):
    """Gerçek geometri üzerinde eşit aralıklı noktalar (uçlar korunur)."""
    line = LineString(coords)
    n = max(1, int(math.ceil(line.length / spacing)))
    return [line.interpolate(i / n, normalized=True).coords[0] for i in range(n + 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=CONFIG["game"]["scale_divisor"])
    ap.add_argument("--node-spacing", type=float, default=40.0,
                    help="editör düğüm aralığı, OYUN metresi (varsayılan 40)")
    ap.add_argument("--corridor-buffer-m", type=float, default=1500.0)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    IMG.mkdir(parents=True, exist_ok=True)
    S = args.scale

    places = [e for e in load("places") if e["type"] == "node"]
    gebze, cayirova, darica = place(places, "Gebze"), place(places, "Çayırova"), place(places, "Darıca")
    E0, N0 = TO_UTM.transform(gebze["lon"], gebze["lat"])
    g = lambda e, n: (round((e - E0) / S, 2), round(-(n - N0) / S, 2))
    P = {k: Point(TO_UTM.transform(v["lon"], v["lat"])) for k, v in
         (("Gebze", gebze), ("Çayırova", cayirova), ("Darıca", darica))}

    # ---- graf (UTM metre ağırlıklı)
    ways = [w for w in load("roads") if w["type"] == "way" and w.get("tags", {}).get("highway") in CONNECT]
    G = nx.Graph()
    wayinfo = {}
    for w in ways:
        t = w["tags"]
        pts = [TO_UTM.transform(p["lon"], p["lat"]) for p in w["geometry"]]
        wayinfo[w["id"]] = (t, pts)
        oneway = t.get("oneway") in ("yes", "1", "true") or t.get("highway") in ("motorway", "motorway_link")
        penalty = 1.0 if t["highway"] in MAIN else 1.8   # ana yolları tercih et
        for a, b in zip(pts, pts[1:]):
            ka, kb = (round(a[0], 2), round(a[1], 2)), (round(b[0], 2), round(b[1], 2))
            d = math.dist(a, b)
            G.add_edge(ka, kb, w=d * penalty, d=d, way=w["id"], hw=t["highway"], oneway=oneway)

    def nearest(pt, pred=lambda n: True):
        best, bd = None, 1e18
        for n in G.nodes:
            if pred(n):
                d = (n[0] - pt.x) ** 2 + (n[1] - pt.y) ** 2
                if d < bd:
                    best, bd = n, d
        return best, math.sqrt(bd)

    def ref_nodes(tag):
        s = set()
        for wid, (t, pts) in wayinfo.items():
            if tag in norm_ref(t.get("ref")):
                s.update((round(p[0], 2), round(p[1], 2)) for p in pts)
        return s

    d100_nodes, o4_nodes = ref_nodes("D100"), ref_nodes("O4")

    # ---- P1: D-100 koridoru (Çayırova -> Gebze), yönlere göre
    corridor = LineString([P["Çayırova"].coords[0], P["Gebze"].coords[0]]).buffer(args.corridor_buffer_m)
    d100_lines = []
    for wid, (t, pts) in wayinfo.items():
        if "D100" in norm_ref(t.get("ref")) and t["highway"] in MAIN:
            ln = LineString(pts)
            if ln.intersects(corridor):
                clip = ln.intersection(corridor)
                if not clip.is_empty:
                    d100_lines.append((wid, t, clip))
    merged = linemerge(unary_union([c for _, _, c in d100_lines]))
    parts = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
    parts = sorted([p for p in parts if p.length > 300], key=lambda p: -p.length)

    rows, segs = [], []
    axis = LineString([P["Çayırova"].coords[0], P["Gebze"].coords[0]])
    for i, part in enumerate(parts[:4]):
        coords = list(part.coords)
        # yön: başlangıç Çayırova tarafındaysa doğuya (Gebze) gidiş
        if axis.project(Point(coords[0])) > axis.project(Point(coords[-1])):
            coords = coords[::-1]
            direction = "rev"
        else:
            direction = "fwd"
        segs.append({"id": f"P1_D100_{i}", "length_m_real": round(part.length, 1),
                     "length_m_game": round(part.length / S, 1), "osm_order": direction})
        for j, (e, n) in enumerate(resample(coords, args.node_spacing * S)):
            lon, lat = TO_WGS.transform(e, n)
            x, z = g(e, n)
            rows.append({"segment": f"P1_D100_{i}", "seq": j, "lat": round(lat, 7), "lon": round(lon, 7),
                         "game_x": x, "game_z": z})

    # ---- bağlantı yolları: gerçek en kısa yollar
    def route(name, src_pt, targets, desc):
        s, sd = nearest(src_pt)
        best = None
        try:
            lengths, paths = nx.single_source_dijkstra(G, s, weight="w")
        except nx.NetworkXError:
            return {"id": name, "ok": False, "reason": "kaynak düğüm grafikte yok"}
        for tnode in targets:
            if tnode in lengths and (best is None or lengths[tnode] < lengths[best]):
                best = tnode
        if best is None:
            return {"id": name, "ok": False, "reason": "hedefe bağlı yol yok (ağ kopuk)"}
        path = paths[best]
        real = sum(G[a][b]["d"] for a, b in zip(path, path[1:]))
        hws = {}
        for a, b in zip(path, path[1:]):
            hws[G[a][b]["hw"]] = hws.get(G[a][b]["hw"], 0) + G[a][b]["d"]
        wids = []
        for a, b in zip(path, path[1:]):
            if not wids or wids[-1] != G[a][b]["way"]:
                wids.append(G[a][b]["way"])
        for j, (e, n) in enumerate(resample(path, args.node_spacing * S) if len(path) > 1 else path):
            lon, lat = TO_WGS.transform(e, n)
            x, z = g(e, n)
            rows.append({"segment": name, "seq": j, "lat": round(lat, 7), "lon": round(lon, 7),
                         "game_x": x, "game_z": z})
        names = []
        for wid in wids:
            t = wayinfo[wid][0]
            lab = t.get("name") or t.get("ref") or t["highway"]
            if not names or names[-1] != lab:
                names.append(lab)
        return {"id": name, "ok": True, "desc": desc, "start_snap_m": round(sd, 1),
                "length_m_real": round(real, 1), "length_m_game": round(real / S, 1),
                "by_class_m": {k: round(v) for k, v in hws.items()}, "osm_ways": wids, "road_names": names}

    gebze_d100 = nearest(P["Gebze"], lambda n: n in d100_nodes)[0]
    routes = [
        route("P2_D100_TEM", Point(gebze_d100), o4_nodes, "Gebze D-100 -> en yakın TEM (O-4) bağlantısı"),
        route("P3_Darica_D100", P["Darıca"], d100_nodes, "Darıca merkez -> D-100"),
        route("P4_Gebze_D100", P["Gebze"], d100_nodes, "Gebze merkez -> D-100"),
        route("P5_Cayirova_TEM", P["Çayırova"], o4_nodes, "Çayırova merkez -> TEM (O-4)"),
    ]

    with open(OUT / "editor_nodes.csv", "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.DictWriter(fh, fieldnames=["segment", "seq", "lat", "lon", "game_x", "game_z"])
        wr.writeheader()
        wr.writerows(rows)
    feats = []
    for seg in sorted({r["segment"] for r in rows}):
        cs = [[r["lon"], r["lat"]] for r in rows if r["segment"] == seg]
        feats.append({"type": "Feature", "properties": {"segment": seg},
                      "geometry": {"type": "LineString", "coordinates": cs}})
    (OUT / "prototype.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "attribution": "(c) OpenStreetMap contributors, ODbL 1.0",
         "features": feats}, ensure_ascii=False), encoding="utf-8")

    anchors = {k: {"osm_node": v["id"], "lat": v["lat"], "lon": v["lon"],
                   "game": g(*TO_UTM.transform(v["lon"], v["lat"]))}
               for k, v in (("Gebze", gebze), ("Çayırova", cayirova), ("Darıca", darica))}
    summary = {"scale_divisor": S, "node_spacing_game_m": args.node_spacing,
               "origin": anchors["Gebze"], "anchors": anchors,
               "P1_D100_segments": segs, "routes": routes,
               "editor_node_count": len(rows)}
    (OUT / "prototype_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:5000])

    # ---- görseller
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def draw(ax, bounds=None, label_routes=True):
        for wid, (t, pts) in wayinfo.items():
            hw = t["highway"].replace("_link", "")
            if hw not in STYLE:
                continue
            col, lw = STYLE[hw]
            xs = [(p[0] - E0) / S for p in pts]
            zs = [-(p[1] - N0) / S for p in pts]
            ax.plot(xs, zs, color=col, lw=lw * (0.6 if "_link" in t["highway"] else 1), zorder=2)
        segcolors = {"P1": "#2c3e50", "P2": "#8e44ad", "P3": "#16a085", "P4": "#2980b9", "P5": "#d35400"}
        for seg in sorted({r["segment"] for r in rows}):
            xs = [r["game_x"] for r in rows if r["segment"] == seg]
            zs = [r["game_z"] for r in rows if r["segment"] == seg]
            ax.plot(xs, zs, color=segcolors[seg[:2]], lw=4, alpha=0.55, zorder=3,
                    label=seg if label_routes else None)
        for k, a in anchors.items():
            ax.plot(*a["game"], "ko", ms=6, zorder=5)
            ax.annotate(k, a["game"], xytext=(5, 5), textcoords="offset points", fontsize=10, weight="bold")
        ax.set_aspect("equal")
        ax.invert_yaxis()  # +Z güney -> aşağı
        ax.set_xlabel("oyun X (m, +doğu)")
        ax.set_ylabel("oyun Z (m, +güney)")
        ax.grid(True, lw=0.3)
        if bounds:
            ax.set_xlim(bounds[0], bounds[1])
            ax.set_ylim(bounds[3], bounds[2])

    xs = [r["game_x"] for r in rows]
    zs = [r["game_z"] for r in rows]
    pad = 150
    fig, ax = plt.subplots(figsize=(14, 10), dpi=130)
    draw(ax, (min(xs) - pad, max(xs) + pad, min(zs) - pad, max(zs) + pad))
    ax.legend(loc="lower left", fontsize=8)
    ax.set_title(f"SAKLAZ 0.1.0 prototip koridoru - ölçek 1:{S:g} - © OpenStreetMap katkıda bulunanlar (ODbL)")
    fig.tight_layout()
    fig.savefig(IMG / "prototype_corridor.png")
    plt.close(fig)
    print("Görsel:", IMG / "prototype_corridor.png")


if __name__ == "__main__":
    main()
