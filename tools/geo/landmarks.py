"""Bilinen yerler (AVM, hastane, belediye, meydan): data/raw/kocaeli/landmarks.json'dan süzülmüş liste.

Küçük/tekrar kayıtlar atılır: muhtarlık, aile sağlığı merkezi, poliklinik, sağlık ocağı, "Girişi" kayıtları; aynı
türden 150 m (gerçek) içindeki ikinci kayıt. Veri © OpenStreetMap katkıda bulunanlar, ODbL 1.0.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP = ("muhtarl", "aile sağlığı", "poliklinik", "sağlık ocağı", "girişi", "acil", "ek bina", "zabıta", "müdürlüğü",
        "semt", "laboratuvar", "diş", "eczane")


def load(transform):
    """[(kind, name, x_utm, y_utm)] — kind: mall/hospital/townhall/square"""
    f = ROOT / "data" / "raw" / "kocaeli" / "landmarks.json"
    if not f.exists():
        return []
    out = []
    for el in json.loads(f.read_text(encoding="utf-8"))["elements"]:
        t = el.get("tags", {})
        c = el.get("center") or ({"lat": el["lat"], "lon": el["lon"]} if "lat" in el else None)
        nm = t.get("name")
        if not c or not nm or any(k in nm.lower() for k in SKIP):
            continue
        kind = ("mall" if t.get("shop") == "mall" else "hospital" if t.get("amenity") == "hospital" else
                "townhall" if t.get("amenity") == "townhall" else
                "square" if t.get("place") == "square" or t.get("highway") == "pedestrian" else None)
        if not kind or (kind == "square" and "kavşa" in nm.lower()):
            continue
        if kind == "townhall" and not any(k in nm.lower() for k in ("belediye", "kaymakam", "valilik")):
            continue
        x, y = transform(c["lon"], c["lat"])
        if any(k == kind and math.hypot(x - x2, y - y2) < 150 for k, _, x2, y2, _ in out):
            continue
        out.append((kind, nm, x, y, el["id"]))
    return out
