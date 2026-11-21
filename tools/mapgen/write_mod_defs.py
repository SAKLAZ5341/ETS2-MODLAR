"""map_graph_s3.json'daki şehir ve depolardan mod tanımlarını üretir ve editör moduna kopyalar.

Çıktı: map/mod_defs/def/{city.saklaz.sii, city/<şehir>.sui, company/<şirket>/editor/<şehir>.sii}
Kullanım: .venv\\Scripts\\python.exe -I tools\\mapgen\\write_mod_defs.py [--install]
Not: Oyun, şirket öğesinin şehrini konumuna göre CityArea'dan seçer; şehir alanları (sınır kutuları)
çakışabildiği için her depo için onu içeren tüm şehirlere company_def yazılır.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
G = json.loads((ROOT / "data" / "processed" / "map_graph_s3.json").read_text(encoding="utf-8"))
M = ROOT / "map" / "mod_defs" / "def"
INSTALL = Path(r"D:\SAKLAZ_DEV\Euro Truck Simulator 2\mod\user_map\def")
POP = {"gebze": 400000, "darica": 220000, "cayirova": 150000, "dilovasi": 50000}
PREFAB = {"generic": "at_0j004", "logistic": "at_0j009", "light_factory": "at_0j008"}

if M.exists():
    shutil.rmtree(M)
(M / "city").mkdir(parents=True)
inc = []
for c in G["cities"]:
    t = c["token"]
    inc.append(f'@include "city/{t}.sui"')
    (M / "city" / f"{t}.sui").write_text(
        f'city_data : city.{t}\n{{\n\tcity_name: "{c["name"]}"\n\tcountry: turkey\n\tpopulation: {POP.get(t, 100000)}\n}}\n',
        encoding="utf-8")
(M / "city.saklaz.sii").write_text("SiiNunit\n{\n" + "\n".join(inc) + "\n}\n", encoding="utf-8")

for d in G["depots"]:
    x, z = d["body"]
    cities = {c["token"] for c in G["cities"] if c["x0"] <= x <= c["x1"] and c["z0"] <= z <= c["z1"]} | {d["city"]}
    for t in sorted(cities):
        f = M / "company" / d["company"] / "editor" / f"{t}.sii"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f'SiiNunit\n{{\ncompany_def : .{t} {{\n city: {t}\n prefab: {PREFAB[d["kind"]]}\n}}\n}}\n',
                     encoding="utf-8")
    print(f'{d["company"]:10s} {d["kind"]:14s} -> {sorted(cities)}')

if "--install" in sys.argv:
    if INSTALL.exists():
        shutil.rmtree(INSTALL)
    shutil.copytree(M, INSTALL)
    print("kuruldu:", INSTALL)
