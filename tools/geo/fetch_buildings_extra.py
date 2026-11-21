"""Ek bina şeridini indirip data/raw/buildings.json ile birleştirir (OSM id'ye göre tekilleştirir).

Kullanım: .venv\Scripts\python.exe -I tools\geo\fetch_buildings_extra.py S W N E
Veri © OpenStreetMap katkıda bulunanlar, ODbL 1.0.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_osm import overpass  # noqa: E402

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
s, w, n, e = (float(v) for v in sys.argv[1:5])
q = f"""[out:json][timeout:300][bbox:{s},{w},{n},{e}];
(way["building"];rel["building"];);
out tags geom;"""
extra = overpass(q)
base = json.loads((RAW / "buildings.json").read_text(encoding="utf-8"))
seen = {(el["type"], el["id"]) for el in base["elements"]}
add = [el for el in extra["elements"] if (el["type"], el["id"]) not in seen]
base["elements"] += add
(RAW / "buildings.json").write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
meta = RAW / "buildings.meta.json"
m = json.loads(meta.read_text(encoding="utf-8"))
m.setdefault("extra_queries", []).append(q)
m["element_count"] = len(base["elements"])
meta.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"eklenen bina: {len(add)}, toplam: {len(base['elements'])}")
