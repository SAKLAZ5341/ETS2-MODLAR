"""SAKLAZ Türkiye Map - tüm Kocaeli için OSM verisi (il geneli katman).

Kullanım:
    .venv\\Scripts\\python.exe tools\\geo\\fetch_kocaeli.py [--force]

Çekirdek (Gebze/Darıca/Çayırova/Dilovası) verisi data/raw/ altında kalır; burada il geneli için daha seyrek
katmanlar indirilir (data/raw/kocaeli/):
  districts  : 12 ilçenin sınırı (admin_level 6)
  roads      : motorway..tertiary (+ bağlantılar)
  streets    : ilçe merkezlerinde (places.json town/city, 1,6 km yarıçap) unclassified/residential
  landuse    : sanayi/liman alanları (depo yeri)
  places     : şehir/kasaba/köy noktaları
  nature     : orman/tarım/su (zemin)
  rail_coast : kıyı çizgisi, demiryolu
  buildings  : ilçe merkezlerinde (1,2 km) binalar
Veri © OpenStreetMap katkıda bulunanlar, ODbL 1.0.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_osm  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "kocaeli"
CENTERS = ["İzmit", "Körfez", "Derince", "Gölcük", "Karamürsel", "Kandıra", "Kartepe", "Başiskele",
           "Gebze", "Darıca", "Çayırova", "Dilovası", "Hereke", "Yarımca", "Değirmendere", "Tavşancıl"]


def save(name, data, q):
    fetch_osm.RAW = OUT
    fetch_osm.save(name, data, q)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", nargs="*", default=None, help="yalnız bu katmanları yeniden indir")
    ap.add_argument("--building-radius", type=int, default=2200, help="il geneli bina yarıçapı (m)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    def need(n):
        if a.only is not None:
            return n in a.only
        return a.force or not (OUT / f"{n}.json").exists()

    if need("districts"):
        q = """[out:json][timeout:180];
area["name"="Kocaeli"]["admin_level"="4"]->.p;
rel(area.p)["boundary"="administrative"]["admin_level"="6"];
out geom;"""
        print("ilçe sınırları...")
        save("districts", fetch_osm.overpass(q), q)
    d = json.loads((OUT / "districts.json").read_text(encoding="utf-8"))
    lats, lons = [], []
    for el in d["elements"]:
        b = el.get("bounds")
        if b:
            lats += [b["minlat"], b["maxlat"]]
            lons += [b["minlon"], b["maxlon"]]
    bbox = (min(lats) - 0.01, min(lons) - 0.01, max(lats) + 0.01, max(lons) + 0.01)
    print("ilçeler:", ", ".join(sorted(el["tags"].get("name", "?") for el in d["elements"])))
    print("bbox:", bbox)
    (OUT / "bbox.json").write_text(json.dumps({"bbox_swne": bbox}, indent=2), encoding="utf-8")
    bb = ",".join(f"{v:.6f}" for v in bbox)
    qs = {
        "roads": f"""[out:json][timeout:600][bbox:{bb}];
way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link)$"];
out tags geom;""",
        "places": f"""[out:json][timeout:120][bbox:{bb}];
node["place"~"^(city|town|suburb|village)$"];
out tags geom;""",
        "landuse": f"""[out:json][timeout:300][bbox:{bb}];
(way["landuse"~"^(industrial|port)$"];rel["landuse"~"^(industrial|port)$"];);
out tags geom;""",
        "nature": f"""[out:json][timeout:600][bbox:{bb}];
(way["landuse"~"^(forest|farmland|meadow|orchard|residential|industrial)$"];
 rel["landuse"~"^(forest|farmland|meadow|residential)$"];
 way["natural"~"^(wood|scrub|water)$"];rel["natural"~"^(wood|water)$"];);
out tags geom;""",
        "rail_coast": f"""[out:json][timeout:180][bbox:{bb}];
(way["natural"="coastline"];way["railway"="rail"];);
out tags geom;""",
        # bilinen yerler: AVM, hastane, belediye, meydan, stadyum (simge modeli + ad tabelası)
        "landmarks": f"""[out:json][timeout:300][bbox:{bb}];
(nwr["shop"="mall"];nwr["amenity"="hospital"];nwr["amenity"="townhall"]["townhall:type"!="village"];
 nwr["place"="square"];nwr["highway"="pedestrian"]["area"="yes"]["name"~"Meydan"];nwr["leisure"="stadium"];);
out tags center;""",
    }
    for n, q in qs.items():
        if need(n):
            print(n, "...")
            save(n, fetch_osm.overpass(q), q)
            time.sleep(5)
    # ilçe merkezleri: sokaklar ve binalar (merkez çevresi)
    pl = json.loads((OUT / "places.json").read_text(encoding="utf-8"))["elements"]
    cen = {}
    for p in pl:
        nm = p.get("tags", {}).get("name")
        if nm in CENTERS and (nm not in cen or p["tags"].get("place") in ("city", "town")):
            cen[nm] = (p["lat"], p["lon"])
    print("merkezler:", sorted(cen))
    (OUT / "centers.json").write_text(json.dumps(cen, ensure_ascii=False, indent=1), encoding="utf-8")
    if need("streets"):
        parts = "".join(f'way(around:1600,{la},{lo})["highway"~"^(unclassified|residential|living_street)$"];'
                        for nm, (la, lo) in cen.items() if nm not in ("Gebze", "Darıca", "Çayırova", "Dilovası"))
        q = f"[out:json][timeout:600];({parts});out tags geom;"
        print("streets ...")
        save("streets", fetch_osm.overpass(q), q)
        time.sleep(5)
    if need("buildings"):
        parts = "".join(f'way(around:{a.building_radius},{la},{lo})["building"];'
                        for nm, (la, lo) in cen.items() if nm not in ("Gebze", "Darıca", "Çayırova", "Dilovası"))
        q = f"[out:json][timeout:600][maxsize:1073741824];({parts});out tags geom;"
        print("buildings ...")
        save("buildings", fetch_osm.overpass(q), q)
    print("Tamam.")


if __name__ == "__main__":
    main()
