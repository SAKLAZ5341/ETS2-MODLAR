"""Güncel yol ağına (map_graph_s3.json) taşan binaları yerleştirmeden çıkarır.

Neden: binalar (map_export_s3.json, place=true) yol ağı bölünmüş cadde indirgemesinden önce seçiliyordu;
orta hatta kayan yollar bazı binaların içinden geçiyordu (önizlemede kamyon binaya çarptı, 2026-11-22).
Çıktı: data/processed/map_export_s3_clear.json (mapgen buildgraph'ın 3. argümanı).
Kullanım: python tools/geo/clear_buildings.py
"""
import json
import math
from pathlib import Path

from shapely.geometry import LineString, Polygon
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[2]
HALF = {"hw3_divided": 12, "hw2_oneway": 5, "hw3_oneway": 7, "hw4_oneway": 9, "r2_divided": 8,
        "ramp_1lane": 4, "r1_city": 5, "r1_city_narrow": 5, "service": 4}


def main():
    g = json.loads((ROOT / "data/processed/map_graph_s3.json").read_text(encoding="utf-8"))
    ex = json.loads((ROOT / "data/processed/map_export_s3.json").read_text(encoding="utf-8"))
    roads = [LineString(e["pts"]).buffer(HALF.get(e["type"], 5) + 0.5) for e in g["edges"]]
    for j in g["junctions"] + g["hw_junctions"]:
        roads.append(LineString([(j["x"], j["z"]), (j["x"] + 0.1, j["z"])]).buffer(20))
    tree = STRtree(roads)
    off = 0
    for b in ex["buildings"]:
        if not b.get("place", True):
            continue
        x, z, h = b["x"], b["z"], math.radians(b["heading_deg"])
        L, W = b.get("len", 10) / 2, b.get("wid", 10) / 2
        # ayak izi: OSM dikdörtgeni (uzun kenar başlık yönünde), %85 (köşe/çıkıntı payı)
        L, W = L * 0.85, W * 0.85
        c, s = math.cos(h), math.sin(h)
        poly = Polygon([(x + dx * c - dz * s, z + dx * s + dz * c) for dx, dz in ((-L, -W), (L, -W), (L, W), (-L, W))])
        if any(roads[q].intersects(poly) for q in tree.query(poly)):
            b["place"] = False
            off += 1
    (ROOT / "data/processed/map_export_s3_clear.json").write_text(json.dumps(ex, ensure_ascii=False), encoding="utf-8")
    n = sum(1 for b in ex["buildings"] if b.get("place", True))
    print(f"yola taşan bina çıkarıldı: {off}; kalan {n}")


if __name__ == "__main__":
    main()
