"""SAKLAZ Türkiye Map - OpenStreetMap verisini Overpass API ile indirir.

Kullanım:
    .venv\\Scripts\\python.exe tools\\geo\\fetch_osm.py [--force]

Adımlar:
  1. Kocaeli içindeki ilçe sınırlarını (config/aoi.json -> districts) indirir.
  2. Sınırların birleşik kutusuna tampon ekleyerek çalışma alanını (bbox) hesaplar.
  3. Bu bbox içindeki yol, kavşak, sanayi, yerleşim, demiryolu ve kıyı verisini indirir.

Çıktılar data/raw/ altına yazılır (depoya girmez). Her dosyanın yanında
.meta.json vardır: indirme zamanı, Overpass veri zaman damgası, sorgu.

Veri © OpenStreetMap katkıda bulunanlar, ODbL 1.0.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import sys as _sys
_sys.stdout.reconfigure(encoding="utf-8")

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
CONFIG = ROOT / "config" / "aoi.json"

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
HEADERS = {"User-Agent": "SAKLAZ-Turkiye-Map-dev/0.1 (ETS2 map research)"}


def overpass(query: str) -> dict:
    last = None
    for attempt in range(3):
        for url in ENDPOINTS:
            try:
                r = requests.post(url, data={"data": query}, headers=HEADERS, timeout=300)
                if r.status_code == 200:
                    return r.json()
                last = f"{url} HTTP {r.status_code}: {r.text[:200]}"
            except requests.RequestException as e:  # ağ hatası -> sonraki uç nokta
                last = f"{url} {type(e).__name__}: {e}"
            print("  uyarı:", last, file=sys.stderr)
        time.sleep(15 * (attempt + 1))
    raise RuntimeError(f"Overpass başarısız: {last}")


def save(name: str, data: dict, query: str) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    meta = {
        "source": "OpenStreetMap via Overpass API",
        "license": "ODbL 1.0 - (c) OpenStreetMap contributors",
        "downloaded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "osm_base_timestamp": data.get("osm3s", {}).get("timestamp_osm_base"),
        "element_count": len(data.get("elements", [])),
        "query": query,
    }
    (RAW / f"{name}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {name}: {meta['element_count']} öğe, OSM zamanı {meta['osm_base_timestamp']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="var olan indirmeleri yenile")
    args = ap.parse_args()
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))

    # 1) İlçe sınırları
    if args.force or not (RAW / "districts.json").exists():
        names = "|".join(cfg["districts"])
        q = f"""[out:json][timeout:180];
area["name"="{cfg['province']}"]["admin_level"="4"]->.p;
rel(area.p)["boundary"="administrative"]["admin_level"="6"]["name"~"^({names})$"];
out geom;"""
        print("İlçe sınırları indiriliyor...")
        save("districts", overpass(q), q)
    districts = json.loads((RAW / "districts.json").read_text(encoding="utf-8"))

    lats, lons = [], []
    for el in districts["elements"]:
        b = el.get("bounds")
        if b:
            lats += [b["minlat"], b["maxlat"]]
            lons += [b["minlon"], b["maxlon"]]
    if not lats:
        raise SystemExit("HATA: İlçe sınırları bulunamadı; config/aoi.json adlarını kontrol edin.")
    buf = cfg.get("bbox_buffer_deg", 0.01)
    bbox = (min(lats) - buf, min(lons) - buf, max(lats) + buf, max(lons) + buf)
    found = sorted(el.get("tags", {}).get("name", "?") for el in districts["elements"])
    print("Bulunan ilçeler:", ", ".join(found))
    print("Çalışma alanı bbox (S,W,N,E):", ", ".join(f"{v:.5f}" for v in bbox))
    (RAW / "bbox.json").write_text(json.dumps({"bbox_swne": bbox, "districts": found}, indent=2), encoding="utf-8")

    bb = ",".join(f"{v:.6f}" for v in bbox)
    queries = {
        "roads": f"""[out:json][timeout:300][bbox:{bb}];
way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link|unclassified|residential|service|living_street|road)$"];
out tags geom;""",
        "junctions": f"""[out:json][timeout:180][bbox:{bb}];
(node["highway"="motorway_junction"];node["highway"="traffic_signals"];node["junction"];way["junction"="roundabout"];);
out tags geom;""",
        "landuse": f"""[out:json][timeout:300][bbox:{bb}];
(way["landuse"~"^(industrial|commercial|retail|residential|port)$"];
 rel["landuse"~"^(industrial|commercial|retail|residential|port)$"];
 way["industrial"];rel["industrial"];
 way["building"="warehouse"];);
out tags geom;""",
        "places": f"""[out:json][timeout:120][bbox:{bb}];
(node["place"~"^(city|town|suburb|quarter|neighbourhood|village|hamlet)$"];);
out tags geom;""",
        "rail_coast": f"""[out:json][timeout:180][bbox:{bb}];
(way["railway"~"^(rail|light_rail|subway)$"];way["natural"="coastline"];node["railway"="station"];);
out tags geom;""",
    }
    for name, q in queries.items():
        if not args.force and (RAW / f"{name}.json").exists():
            print(f"  {name}: önbellekte, atlandı")
            continue
        print(f"{name} indiriliyor...")
        save(name, overpass(q), q)
        time.sleep(5)  # Overpass adil kullanım
    print("Tamam.")


if __name__ == "__main__":
    main()
