"""Mod Yöneticisi simgesi (276x162 JPG): Kocaeli yol ağı + başlık. Çıktı: map/standalone/package/icon.jpg
Kullanım: python tools/packaging/make_icon.py
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
g = json.loads((ROOT / "data/processed/map_graph_s3.json").read_text(encoding="utf-8"))
W, H, DPI = 276, 162, 100
fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_facecolor("#0f1c2e")
fig.patch.set_facecolor("#0f1c2e")
style = {"hw": ("#f5a623", 1.1), "r2": ("#e8e8e8", 0.7), "r1": ("#8fa3bf", 0.35), "ramp": ("#f5a623", 0.5)}
for e in g["edges"]:
    t = e["type"]
    k = "hw" if t.startswith("hw") else "r2" if t == "r2_divided" else "ramp" if t == "ramp_1lane" else "r1"
    if k == "r1" and t != "r1_city":
        continue
    c, lw = style[k]
    ax.plot([p[0] for p in e["pts"]], [-p[1] for p in e["pts"]], color=c, lw=lw, solid_capstyle="round")
for c in g["cities"]:
    if "center" in c:
        ax.plot(c["center"][0], -c["center"][1], "o", color="#ff4d4d", ms=2.2)
xs = [p[0] for e in g["edges"] for p in e["pts"]]
zs = [-p[1] for e in g["edges"] for p in e["pts"]]
cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
span = max((max(xs) - min(xs)) / W, (max(zs) - min(zs)) / H) * 1.04
ax.set_xlim(cx - span * W / 2, cx + span * W / 2)
ax.set_ylim(cz - span * H / 2 - span * 12, cz + span * H / 2 - span * 12)
ax.axis("off")
ax.text(0.04, 0.9, "SAKLAZ", transform=ax.transAxes, color="white", fontsize=13, fontweight="bold", va="top")
ax.text(0.04, 0.72, "Türkiye Map · Kocaeli", transform=ax.transAxes, color="#f5a623", fontsize=7.5, va="top")
out = ROOT / "map/standalone/package/icon.jpg"
fig.savefig(out, dpi=DPI, facecolor=fig.get_facecolor(), pil_kwargs={"quality": 92})
print("simge:", out)
