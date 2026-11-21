"""SAKLAZ Türkiye Map - coğrafi veri ve prototip doğrulama testleri.

Kullanım:
    .venv\\Scripts\\python.exe -I tests\\run_tests.py

Her test GEÇTİ/KALDI olarak yazdırılır; sonuçlar tests/geo_validation_report.md dosyasına yazılır.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path

from pyproj import Geod, Transformer

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"
results: list[tuple[str, bool, str]] = []


def test(name):
    def deco(fn):
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001 - test hatası rapora yazılır
            ok, detail = False, f"istisna: {type(e).__name__}: {e}"
        results.append((name, ok, detail))
        return fn
    return deco


@test("T01 Ham OSM dosyaları ve meta kayıtları mevcut")
def _():
    names = ["districts", "roads", "junctions", "landuse", "places", "rail_coast"]
    miss = [n for n in names if not (ROOT / "data/raw" / f"{n}.json").exists()
            or not (ROOT / "data/raw" / f"{n}.meta.json").exists()]
    return not miss, "eksik: " + ", ".join(miss) if miss else "6/6 dosya + meta"


@test("T02 Projeksiyon mesafe testi: UTM mesafesi jeodezik mesafeye %0,2 içinde")
def _():
    a = (29.431767, 40.8006696)   # Gebze OSM düğümü 26505108
    b = (29.3840563, 40.7574799)  # Darıca OSM düğümü 251382196
    geo = Geod(ellps="WGS84").inv(a[0], a[1], b[0], b[1])[2]
    t = Transformer.from_crs("EPSG:4326", "EPSG:32635", always_xy=True)
    utm = math.dist(t.transform(*a), t.transform(*b))
    err = abs(utm - geo) / geo
    return err < 0.002, f"jeodezik {geo:.1f} m, UTM {utm:.1f} m, hata %{err*100:.3f}"


@test("T03 Oyun koordinatı ölçek testi (1:19): Gebze–Darıca oyun mesafesi = gerçek/19")
def _():
    s = json.loads((P / "prototype_s19/prototype_summary.json").read_text(encoding="utf-8"))
    g, d = s["anchors"]["Gebze"]["game"], s["anchors"]["Darıca"]["game"]
    game = math.dist(g, d)
    real = Geod(ellps="WGS84").inv(29.431767, 40.8006696, 29.3840563, 40.7574799)[2]
    err = abs(game * 19 - real) / real
    return err < 0.003 and abs(g[0]) < 1e-6 and abs(g[1]) < 1e-6, f"oyun {game:.2f} m × 19 = {game*19:.1f} m, gerçek {real:.1f} m"


@test("T04 Eksen yönü: Darıca (güneyde) +Z, Çayırova (kuzeyde) −Z")
def _():
    s = json.loads((P / "prototype_s19/prototype_summary.json").read_text(encoding="utf-8"))
    dz, cz = s["anchors"]["Darıca"]["game"][1], s["anchors"]["Çayırova"]["game"][1]
    return dz > 0 and cz < 0, f"Darıca z={dz}, Çayırova z={cz}"


@test("T05 Ana yol ağı bağlılığı: en büyük bileşen ≥ %98")
def _():
    r = json.loads((P / "network_report.json").read_text(encoding="utf-8"))
    sh = r["main_network"]["largest_component_share"]
    return sh >= 0.98, f"en büyük bileşen %{sh*100:.2f}, bileşen sayısı {r['main_network']['components']}"


@test("T06 D-100, O-4 (TEM), O-7, O-5 OSM ref etiketiyle mevcut")
def _():
    r = json.loads((P / "network_report.json").read_text(encoding="utf-8"))["refs"]
    miss = [k for k in ("D100", "O4", "O7", "O5") if r.get(k, {}).get("ways", 0) == 0]
    det = ", ".join(f"{k}: {r[k]['ways']} way / {r[k].get('length_km_real_all_carriageways')} km" for k in ("D100", "O4", "O7", "O5"))
    return not miss, det


@test("T07 O-4 (TEM) bbox içinde kesintisiz (2 parça = iki yön)")
def _():
    r = json.loads((P / "network_report.json").read_text(encoding="utf-8"))["refs"]["O4"]
    return r["connected_pieces"] <= 2, f"parça: {r['connected_pieces']}"


@test("T08 D-100 bbox içinde parça sayısı (bilgi: >2 ise kopukluk/bbox kesişi)")
def _():
    r = json.loads((P / "network_report.json").read_text(encoding="utf-8"))["refs"]["D100"]
    return r["connected_pieces"] <= 2, f"parça: {r['connected_pieces']} (bkz. rapor – bilinen sorun)"


@test("T09 Prototip D-100 iki yön de OSM tek-yön kurallarıyla kesintisiz")
def _():
    s = json.loads((P / "prototype_s19/prototype_summary.json").read_text(encoding="utf-8"))
    segs = s["P1_D100_segments"]
    return all(x["ok"] for x in segs) and len(segs) == 2, "; ".join(
        f"{x['id']}: {'tamam' if x['ok'] else x.get('reason')} {x.get('length_m_real', '')} m" for x in segs)


@test("T10 Prototip bağlantıları (TEM, Darıca, Gebze, Çayırova) gerçek yolla bulundu")
def _():
    s = json.loads((P / "prototype_s19/prototype_summary.json").read_text(encoding="utf-8"))
    bad = [r["id"] for r in s["routes"] if not r["ok"]]
    return not bad, "; ".join(f"{r['id']}: {r.get('length_m_real')} m" for r in s["routes"])


@test("T11 Editör düğümleri arası boşluk ≤ düğüm aralığı (20 oyun m) + tolerans")
def _():
    rows = list(csv.DictReader(open(P / "prototype_s19/editor_nodes.csv", encoding="utf-8-sig")))
    worst = 0.0
    for a, b in zip(rows, rows[1:]):
        if a["segment"] == b["segment"]:
            worst = max(worst, math.dist((float(a["game_x"]), float(a["game_z"])), (float(b["game_x"]), float(b["game_z"]))))
    return worst <= 20.5, f"en büyük aralık {worst:.2f} oyun m, düğüm {len(rows)}"


@test("T12 Editör düğümleri gerçek OSM geometrisinden sapma ≤ 5 m (gerçek)")
def _():
    from shapely.geometry import LineString, Point
    t = Transformer.from_crs("EPSG:4326", "EPSG:32635", always_xy=True)
    roads = json.loads((ROOT / "data/roads/roads_main.geojson").read_text(encoding="utf-8"))["features"]
    from shapely.strtree import STRtree
    lines = [LineString([t.transform(*c) for c in f["geometry"]["coordinates"]]) for f in roads]
    tree = STRtree(lines)
    rows = list(csv.DictReader(open(P / "prototype_s19/editor_nodes.csv", encoding="utf-8-sig")))
    worst = 0.0
    for r in rows:
        if not r["segment"].startswith("P1"):
            continue
        p = Point(t.transform(float(r["lon"]), float(r["lat"])))
        worst = max(worst, lines[tree.nearest(p)].distance(p))
    return worst <= 5.0, f"P1 düğümlerinde en büyük sapma {worst:.2f} m"


@test("T13 ODbL atıfı türetilmiş dosyalarda mevcut")
def _():
    files = list((ROOT / "data/roads").glob("*.geojson")) + list((ROOT / "data/processed").glob("prototype_s*/prototype.geojson"))
    miss = [f.name for f in files if "OpenStreetMap" not in f.read_text(encoding="utf-8")[:400]]
    return not miss, f"{len(files) - len(miss)}/{len(files)} dosyada atıf"


@test("T14 Map Editor: D:\\SAKLAZ_DEV'de kayıtlı saklaz.mbd var mı")
def _():
    prof = Path(r"D:\SAKLAZ_DEV\Euro Truck Simulator 2")
    m = list(prof.rglob("saklaz.mbd")) if prof.exists() else []
    return bool(m), (str(m[0]) if m else "YOK – editörde harita henüz oluşturulmadı (elle adım, bkz. EDITOR_GUIDE.md)")


def main() -> None:
    lines = [f"# Coğrafi veri doğrulama raporu – {datetime.now():%Y-%m-%d %H:%M}", "",
             "| Test | Sonuç | Ayrıntı |", "|---|---|---|"]
    for name, ok, det in results:
        print(f"[{'GEÇTİ' if ok else 'KALDI'}] {name} – {det}")
        lines.append(f"| {name} | {'GEÇTİ' if ok else '**KALDI**'} | {det} |")
    passed = sum(ok for _, ok, _ in results)
    lines += ["", f"Toplam: {passed}/{len(results)} geçti."]
    (ROOT / "tests" / "geo_validation_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n{passed}/{len(results)} geçti")


if __name__ == "__main__":
    main()
