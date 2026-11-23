"""Yönlü erişilebilirlik: oyunun rota bulucusu tek yönlü yolları (otoyol şeridi, rampa) ve otoyol prefablarındaki akış
yönünü dikkate alır. Her depo ve garajdan diğer bütün depolara gidilebiliyor mu ve geri dönülebiliyor mu?
(Yalnız çıkış ya da yalnız katılma ile bağlanan bir ilçe HQ seçilirse "No valid offers" ile oyun kapanabilir.)

Düğüm = (kenar, uç). Kenar içinde: iki yönlü yol a<->b, tek yönlü görünüm a->b (reverse ise b->a).
Kullanım: python tools/validation/directed.py [graph.json]
"""
import json
import sys
from collections import defaultdict, deque

OW = lambda t: t == "ramp_1lane" or (t.startswith("hw") and t.endswith("_oneway"))


def build(g):
    adj = defaultdict(set)

    def add(x, y):
        adj[x].add(y)
    skip = g.get("skip_edges", set())
    for e in g["edges"]:
        i = e["id"]
        if i in skip:
            continue  # C#'ın kuramadığı (prefab içinde kalan) kısa kenar
        if OW(e["type"]):
            if e.get("reverse"):
                add((i, "b"), (i, "a"))
            else:
                add((i, "a"), (i, "b"))
        else:
            add((i, "a"), (i, "b"))
            add((i, "b"), (i, "a"))
    # uç noktası (kenarın bittiği yer) -> prefaba "giriş"; prefabtan çıkan kol -> kenarın başladığı uç
    for j in g["junctions"]:
        ends = [(a["edge"], a["end"]) for a in j["arms"]]
        for x in ends:
            for y in ends:
                if x != y:
                    add(x, y)
    for h in g["hw_junctions"]:
        r = {a["role"]: (a["edge"], a["end"]) for a in h["arms"]}
        add(r["in"], r["out"])
        if h["kind"] == "exit":
            add(r["in"], r["ramp"])
        else:
            add(r["ramp"], r["out"])
    for f in g.get("ramp_forks", []):
        r = {a["role"]: (a["edge"], a["end"]) for a in f["arms"]}
        if f["kind"] == "split":
            add(r["trunk"], r["left"]); add(r["trunk"], r["right"])
        else:
            add(r["left"], r["trunk"]); add(r["right"], r["trunk"])
    for d in g.get("depots", []) + g.get("garages", []):
        x, y = (d["arm0"]["edge"], d["arm0"]["end"]), (d["arm1"]["edge"], d["arm1"]["end"])
        add(x, y); add(y, x)
    for l in g.get("road_links", []):
        add((l[0], l[1]), (l[2], l[3])); add((l[2], l[3]), (l[0], l[1]))
    # C# ile aynı: kurulamayan kısa yolun iki ucundaki bağlantı ortakları doğrudan birleşir (kısa yol köprüsü)
    partner = defaultdict(list)
    for l in g.get("road_links", []):
        partner[(l[0], l[1])].append((l[2], l[3]))
        partner[(l[2], l[3])].append((l[0], l[1]))
    for sid in skip:
        pa, pb = partner.get((sid, "a"), []), partner.get((sid, "b"), [])
        if len(pa) == 1 and len(pb) == 1 and pa[0][0] not in skip and pb[0][0] not in skip:
            add(pa[0], pb[0]); add(pb[0], pa[0])
    return adj


def reach(adj, src):
    seen, q = {src}, deque([src])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in seen:
                seen.add(v); q.append(v)
    return seen


def skipped_edges(g, path="data/processed/edge_skips.json"):
    """Önceki C# derlemesinin kuramadığı kenarlar (ilk noktası 0,1 m eşleşen)."""
    import os
    if not os.path.exists(path):
        return set()
    k = lambda p: (int(round(p[0] * 10)), int(round(p[1] * 10)))
    keys = {(k(v[0:2]), k(v[2:4])) for v in json.load(open(path)) if len(v) == 4}  # ilk + son nokta (tek uç çakışıyordu)
    return {e["id"] for e in g["edges"] if (k(e["pts"][0]), k(e["pts"][-1])) in keys}


def main(path):
    g = json.load(open(path, encoding="utf-8"))
    g["skip_edges"] = skipped_edges(g)
    # C#'ın birleştiremediği uç bağlantıları (link_rejects.json) oyunda yok: denetimden düşülür
    import os
    lr = "data/processed/link_rejects.json"
    if os.path.exists(lr):
        rej = {(int(round(x * 10)), int(round(z * 10))) for x, z in json.load(open(lr))}
        E = {e["id"]: e for e in g["edges"]}
        key = lambda l, i: (lambda p: (int(round(p[0] * 10)), int(round(p[1] * 10))))(
            E[l[i]]["pts"][0] if l[i + 1] == "a" else E[l[i]]["pts"][-1])
        g["road_links"] = [l for l in g["road_links"] if key(l, 0) not in rej and key(l, 2) not in rej]
    adj = build(g)
    radj = defaultdict(set)
    for u, vs in adj.items():
        for v in vs:
            radj[v].add(u)
    pts = [(f"depo {d['city']}/{d['company']}", (d["arm0"]["edge"], d["arm0"]["end"])) for d in g["depots"]]
    pts += [(f"garaj {d['city']}", (d["arm0"]["edge"], d["arm0"]["end"])) for d in g.get("garages", [])]
    ref = pts[0][1]
    fwd, back = reach(adj, ref), reach(radj, ref)
    bad = 0
    for name, n in pts:
        ok_to, ok_from = n in fwd, n in back
        if not (ok_to and ok_from):
            bad += 1
            print(f"  {name}: {'gidilir' if ok_to else 'GİDİLEMEZ'}, {'dönülür' if ok_from else 'DÖNÜLEMEZ'}")
    print(f"yönlü denetim: {len(pts) - bad}/{len(pts)} depo/garaj karşılıklı erişilebilir")
    return bad


if __name__ == "__main__":
    sys.exit(1 if main(sys.argv[1] if len(sys.argv) > 1 else "data/processed/map_graph_s3.json") else 0)


def largest_scc(g):
    """En büyük güçlü bağlı bileşenin (her uçtan her uca gidilip dönülebilen) kenar kimlikleri (iki ucu da içinde)."""
    if "skip_edges" not in g:
        g = dict(g, skip_edges=skipped_edges(g))
    adj = build(g)
    nodes = set(adj)
    for vs in list(adj.values()):
        nodes |= vs
    radj = defaultdict(set)
    for u, vs in adj.items():
        for v in vs:
            radj[v].add(u)
    order, seen = [], set()
    for s in nodes:  # 1. geçiş: bitiş sırası (yinelemesiz)
        if s in seen:
            continue
        seen.add(s)
        st = [(s, iter(adj[s]))]
        while st:
            u, it = st[-1]
            nxt = next(it, None)
            if nxt is None:
                st.pop(); order.append(u)
            elif nxt not in seen:
                seen.add(nxt); st.append((nxt, iter(adj[nxt])))
    comp, best = {}, None
    for s in reversed(order):  # 2. geçiş: ters grafikte
        if s in comp:
            continue
        cid, members, q = s, [s], [s]
        comp[s] = cid
        while q:
            u = q.pop()
            for v in radj[u]:
                if v not in comp:
                    comp[v] = cid; members.append(v); q.append(v)
        if best is None or len(members) > len(best):
            best = members
    S = set(best)
    return {e["id"] for e in g["edges"] if (e["id"], "a") in S and (e["id"], "b") in S}
