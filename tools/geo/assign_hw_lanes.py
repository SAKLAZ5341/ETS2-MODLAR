"""Otoyol çıkış/katılma prefablarının şerit sayılarını eşleştirir.

ETS2'de prefab düğümündeki şerit sayısı ile bağlanan yolun şerit sayısı aynı olmalıdır;
yoksa oyun "Unable to determine output road lane" verir ve trafik o prefabı kullanamaz.

Her kavşak iki prefabtan biriyle yapılır:
  exit  hi = mod_ger_31  (giriş 4 → devam 3 + rampa)   lo = ch_2y016 (giriş 3 → devam 2 + rampa)
  merge hi = ch_4202j    (giriş 3 + rampa → çıkış 4)   lo = ch_2y017 (giriş 2 + rampa → çıkış 3)
Port şeridi = taban + (hi ? 1 : 0); taban: exit in 3, exit out 2, merge in 2, merge out 3.
İki prefab arasındaki kenarın iki ucu aynı şerit sayısını ister → eşitlik/zorlama kısıtları.
Prefaba bağlı olmayan yol uçları serbesttir. Çelişkide kavşak bırakılır (rampa serbest kalır).
Kenar tipi: hw2_oneway / hw3_oneway / hw4_oneway.

Kullanım: python tools/geo/assign_hw_lanes.py [data/processed/map_graph_s3.json]
"""
import json
import sys
from collections import defaultdict, deque

BASE = {("exit", "in"): 3, ("exit", "out"): 2, ("merge", "in"): 2, ("merge", "out"): 3}
HW = {"hw2_oneway", "hw3_oneway", "hw4_oneway"}


def main(path):
    g = json.load(open(path, encoding="utf-8"))
    edges = {e["id"]: e for e in g["edges"]}
    hw = g["hw_junctions"]
    for e in g["edges"]:
        if e["type"] in HW:
            e["type"] = "hw3_oneway"

    # kenar -> [(kavşak indeksi, rol)]
    ports = defaultdict(list)
    for i, h in enumerate(hw):
        for a in h["arms"]:
            if a["role"] in ("in", "out"):
                ports[a["edge"]].append((i, a["role"]))

    alive = [True] * len(hw)
    while True:
        # kısıt grafiği: (j, k, d) → h_j - h_k = d
        adj = defaultdict(list)
        forced = {}
        bad = None
        for eid, lst in ports.items():
            lst = [p for p in lst if alive[p[0]]]
            if len(lst) != 2:
                continue
            (j, rj), (k, rk) = lst
            bj, bk = BASE[(hw[j]["kind"], rj)], BASE[(hw[k]["kind"], rk)]
            d = bk - bj  # bj + hj = bk + hk
            if j == k:
                bad = j
                break
            if d == 0:
                adj[j].append((k, 0)); adj[k].append((j, 0))
            elif d == 1:  # hj=1, hk=0
                for n, v in ((j, 1), (k, 0)):
                    if forced.get(n, v) != v:
                        bad = n
                    forced[n] = v
            elif d == -1:
                for n, v in ((j, 0), (k, 1)):
                    if forced.get(n, v) != v:
                        bad = n
                    forced[n] = v
            else:
                bad = j
            if bad is not None:
                break
        if bad is not None:
            alive[bad] = False
            continue
        # bileşenler (yalnızca eşitlik) → tek değer
        val = {}
        conflict = None
        for s in range(len(hw)):
            if not alive[s] or s in val:
                continue
            comp, q = [s], deque([s])
            seen = {s}
            while q:
                u = q.popleft()
                for v, _ in adj[u]:
                    if v not in seen:
                        seen.add(v); comp.append(v); q.append(v)
            fv = {forced[n] for n in comp if n in forced}
            if len(fv) > 1:
                conflict = next(n for n in comp if n in forced and forced[n] == 0)
                break
            if fv:
                h = fv.pop()
            else:
                # serbest: ana hat 3 şeritten dar olmasın (2 şerit ağır ceza, 4 şerit hafif)
                def cost(hv):
                    c = 0
                    for n in comp:
                        for a in hw[n]["arms"]:
                            if a["role"] in ("in", "out"):
                                lanes = BASE[(hw[n]["kind"], a["role"])] + hv
                                c += {2: 3, 3: 0, 4: 1}[lanes]
                    return c
                h = 0 if cost(0) <= cost(1) else 1
            for n in comp:
                val[n] = h
        if conflict is not None:
            alive[conflict] = False
            continue
        break

    out, dropped = [], 0
    lanes_of = {}
    for i, h in enumerate(hw):
        if not alive[i]:
            dropped += 1
            continue
        hv = val[i]
        h["variant"] = f"{h['kind']}_{'hi' if hv else 'lo'}"
        for a in h["arms"]:
            if a["role"] in ("in", "out"):
                lanes_of.setdefault(a["edge"], set()).add(BASE[(h["kind"], a["role"])] + hv)
        out.append(h)
    stats = defaultdict(int)
    for eid, ls in lanes_of.items():
        assert len(ls) == 1, (eid, ls)
        n = ls.pop()
        assert n in (2, 3, 4), (eid, n)
        edges[eid]["type"] = f"hw{n}_oneway"
        stats[n] += 1
    g["hw_junctions"] = out
    json.dump(g, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    kinds = defaultdict(int)
    for h in out:
        kinds[h["variant"]] += 1
    print(f"otoyol şerit eşleme: {len(out)} kavşak ({dict(kinds)}), bırakılan {dropped}; "
          f"prefab kenarı şerit sayısı: {dict(stats)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/processed/map_graph_s3.json")
