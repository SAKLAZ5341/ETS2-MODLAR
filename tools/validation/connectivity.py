"""Yol ağının oyunda görülecek bağlantı bileşenlerini hesaplar; depo ve garajların aynı ağda olup olmadığını denetler.

ETS2'de iki yol ancak (a) aynı prefabın düğümlerine bağlıysa, (b) tek yol öğesi olarak birleştirilmişse
(link_through) ya da (c) uçları C#'ta birleştirilmişse (road_links) bağlıdır. Aynı noktada biten yollar BAĞLI DEĞİLDİR.
Yeni profilde "No valid offers found for player's HQ city" → ilk iş üretilemez, oyun kapanır: HQ şehrinin
depoları diğer şehirlerin depolarına yol ağıyla ulaşabilmeli.

Kullanım: python tools/validation/connectivity.py [data/processed/map_graph_s3.json]
"""
import json
import sys
from collections import Counter, defaultdict


def components(g):
    E = {e["id"]: e for e in g["edges"]}
    par = {}

    def f(x):
        par.setdefault(x, x)
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    def u(a, b):
        ra, rb = f(a), f(b)
        if ra != rb:
            par[ra] = rb

    for e in g["edges"]:  # bir yol öğesinin iki ucu bağlı
        u(("e", e["id"]), ("e", e["id"]))
    for j in g["junctions"] + g["hw_junctions"] + g.get("ramp_forks", []):
        for arm in j["arms"]:
            u(("j", j["id"], j.get("kind", "c")), ("e", arm["edge"]))
    for k, d in enumerate(g.get("depots", [])):
        u(("d", k), ("e", d["arm0"]["edge"]))
        u(("d", k), ("e", d["arm1"]["edge"]))
    for k, d in enumerate(g.get("garages", [])):
        u(("g", k), ("e", d["arm0"]["edge"]))
        u(("g", k), ("e", d["arm1"]["edge"]))
    for l in g.get("road_links", []):
        u(("e", l[0]), ("e", l[2]))
    return f, E


def main(path):
    g = json.load(open(path, encoding="utf-8"))
    f, E = components(g)
    comp_len = Counter()
    for e in g["edges"]:
        comp_len[f(("e", e["id"]))] += e["len"]
    main_c = comp_len.most_common(1)[0][0]
    total = sum(comp_len.values())
    print(f"bileşen: {len(comp_len)}; en büyük %{100 * comp_len[main_c] / total:.1f} ({comp_len[main_c] / 1000:.0f} oyun-km)")
    bad = 0
    for kind, lst in (("depo", g.get("depots", [])), ("garaj", g.get("garages", []))):
        for k, d in enumerate(lst):
            c = f(("d" if kind == "depo" else "g", k))
            ok = c == main_c
            if not ok:
                bad += 1
            print(f"  {kind} {k:2d} {d.get('city'):10s} {d.get('company', ''):10s} {'ANA AĞ' if ok else 'KOPUK (bileşen %.1f km)' % (comp_len[c] / 1000)}")
    return bad


if __name__ == "__main__":
    sys.exit(1 if main(sys.argv[1] if len(sys.argv) > 1 else "data/processed/map_graph_s3.json") else 0)
