"""Prototip düğümlerini Map Editor'de elle yerleştirmek için Markdown tablosuna dönüştürür.

Kullanım:
    .venv\\Scripts\\python.exe -I tools\\geo\\export_editor_tables.py [--scale 19]

Girdi : data/processed/prototype_s<scale>/editor_nodes.csv
Çıktı : docs/EDITOR_NODES_s<scale>.md
Veri © OpenStreetMap katkıda bulunanlar, ODbL 1.0.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="19")
    a = ap.parse_args()
    d = ROOT / "data" / "processed" / f"prototype_s{a.scale}"
    rows = list(csv.DictReader(open(d / "editor_nodes.csv", encoding="utf-8-sig")))
    summ = json.loads((d / "prototype_summary.json").read_text(encoding="utf-8"))
    info = {s["id"]: s for s in summ["P1_D100_segments"]}
    info.update({r["id"]: r for r in summ["routes"]})
    out = [f"# Editör düğüm tabloları – ölçek 1:{a.scale}", "",
           "Otomatik üretildi (`tools/geo/export_editor_tables.py`). Köken (0,0) = Gebze OSM düğümü "
           f"{summ['origin']['osm_node']}. +X doğu, +Z güney, Y = 0. Birim: oyun metresi.", "",
           "Veri © OpenStreetMap katkıda bulunanlar (ODbL 1.0).", ""]
    for seg in dict.fromkeys(r["segment"] for r in rows):
        pts = [r for r in rows if r["segment"] == seg]
        meta = info.get(seg, {})
        out += [f"## {seg}", "", meta.get("desc", ""), "",
                f"Gerçek uzunluk: {meta.get('length_m_real', '?')} m · oyun: {meta.get('length_m_game', '?')} m · düğüm: {len(pts)}", ""]
        if meta.get("road_names"):
            out += ["Geçtiği yollar (OSM): " + " → ".join(meta["road_names"]), ""]
        out += ["| # | X | Z | önceki düğüme (oyun m) | enlem | boylam |", "|---|---|---|---|---|---|"]
        prev = None
        for r in pts:
            x, z = float(r["game_x"]), float(r["game_z"])
            dd = "" if prev is None else f"{math.dist(prev, (x, z)):.1f}"
            out.append(f"| {r['seq']} | {x:.2f} | {z:.2f} | {dd} | {r['lat']} | {r['lon']} |")
            prev = (x, z)
        out.append("")
    p = ROOT / "docs" / f"EDITOR_NODES_s{a.scale}.md"
    p.write_text("\n".join(out), encoding="utf-8")
    print("Yazıldı:", p, len(rows), "düğüm")


if __name__ == "__main__":
    main()
