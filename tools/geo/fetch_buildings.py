"""SAKLAZ Türkiye Map - çekirdek kent alanı için OSM binalarını indirir.

Kullanım:
    .venv\\Scripts\\python.exe -I tools\\geo\\fetch_buildings.py [--force]

Alan: config/aoi.json -> core_bbox (Gebze, Darıca, Çayırova kentsel çekirdeği).
Çıktı: data/raw/buildings.json (+ .meta.json). Veri © OpenStreetMap katkıda bulunanlar, ODbL 1.0.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_osm import RAW, overpass, save  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    cfg = json.loads((ROOT / "config" / "aoi.json").read_text(encoding="utf-8"))
    s, w, n, e = cfg["core_bbox_swne"]
    if (RAW / "buildings.json").exists() and not a.force:
        print("buildings.json önbellekte")
        return
    q = f"""[out:json][timeout:600][maxsize:1073741824][bbox:{s},{w},{n},{e}];
(way["building"];rel["building"];);
out tags geom;"""
    print("Binalar indiriliyor (büyük olabilir)...")
    save("buildings", overpass(q), q)


if __name__ == "__main__":
    main()
