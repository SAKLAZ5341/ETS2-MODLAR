"""OSM'de her yönü ayrı tek yönlü çizilmiş şehir caddelerini (bölünmüş yol) tek, çift yönlü orta hatta indirger.

Neden: 1/3 ölçekte iki şerit merkezi yalnızca 4-12 oyun m aralıklı; her biri çift yönlü yol olarak çizilince
iç içe geçmiş iki cadde görünüyordu ve aradaki kısa bağlantılar yüzünden yan sokaklar kavşaksız kalıyordu.

Yöntem (UTM, bölmeden önce):
  1. Aday: tek yönlü, bağlantı (_link) olmayan şehir yolları; oneway=-1 olanlar ters çevrilir. 10 m'de bir nokta.
  2. Her noktanın solunda (sağdan trafikte karşı yön solda), D içinde, ters yönlü aday parçası aranır.
  3. Yollar arası eşleşme grafiği 2 renge boyanır; bir renk "tutulan" (orta hatta kayar, çift yönlü olur),
     öbürü "atılan" (eşleşen kısmı silinir, eşleşmeyen kısımları tek yönlü kalır ve orta hatta bağlanır).
  4. Atılan noktaları kullanan diğer yollar (yan sokaklar) en yakın orta hat noktasına taşınır.
"""
from __future__ import annotations

import math
from collections import defaultdict, deque

from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

CAND_HW = {"primary", "secondary", "tertiary", "unclassified", "residential"}


def _densify(pts, step):
    out = [pts[0]]
    for p, q in zip(pts, pts[1:]):
        L = math.dist(p, q)
        n = int(L // step)
        for k in range(1, n + 1):
            t = k / (n + 1)
            out.append((round(p[0] + (q[0] - p[0]) * t, 2), round(p[1] + (q[1] - p[1]) * t, 2)))
        out.append(q)
    return out


def collapse(ways, roadmap, D=38.0, step=10.0, snap=14.0):
    """ways: [(wy, tags, hw, pts)] → yeni liste. roadmap: highway → (tür, öncelik)."""
    group = lambda hw: roadmap[hw][0]
    cand = []
    for idx, (wy, t, hw, pts) in enumerate(ways):
        ow = t.get("oneway")
        if hw in CAND_HW and ow in ("yes", "1", "-1") and len(pts) >= 2:
            p = list(pts[::-1]) if ow == "-1" else list(pts)
            cand.append(idx)
            ways[idx] = (wy, dict(t, oneway="yes"), hw, _densify(p, step))
    if not cand:
        return ways, {}
    segs, sinfo = [], []
    for i in cand:
        pts = ways[i][3]
        for k, (p, q) in enumerate(zip(pts, pts[1:])):
            if p != q:
                segs.append(LineString([p, q]))
                sinfo.append((i, k))
    tree = STRtree(segs)

    def tangent(pts, k):
        a, b = pts[max(k - 1, 0)], pts[min(k + 1, len(pts) - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        return dx / L, dy / L

    # 2) nokta eşleşmeleri: match[i][k] = (j, nokta)
    match = defaultdict(dict)
    wcount = defaultdict(int)
    for i in cand:
        wy, t, hw, pts = ways[i]
        for k, v in enumerate(pts):
            tx, ty = tangent(pts, k)
            P = Point(v)
            best = None
            for q in tree.query(P.buffer(D)):
                j, sk = sinfo[q]
                if j == i or group(ways[j][2]) != group(hw):
                    continue
                n1, n2 = t.get("name"), ways[j][1].get("name")
                if n1 and n2 and n1 != n2:
                    continue
                sp = ways[j][3]
                sx, sy = sp[sk + 1][0] - sp[sk][0], sp[sk + 1][1] - sp[sk][1]
                sl = math.hypot(sx, sy) or 1.0
                if (sx * tx + sy * ty) / sl > -0.8:  # ters yönlü değil
                    continue
                seg = segs[q]
                c = seg.interpolate(seg.project(P))
                ox, oy = c.x - v[0], c.y - v[1]
                d = math.hypot(ox, oy)
                if d < 2.0 or d > D:
                    continue
                if abs(ox * tx + oy * ty) / d > 0.5:  # karşı şerit yanda olmalı, önde/arkada değil
                    continue
                if (-ty) * ox + tx * oy < 0:  # sol = (-ty, tx) (UTM, y kuzey); sağdan trafikte karşı yön SOLDA
                    continue
                if best is None or d < best[0]:
                    best = (d, j, (c.x, c.y))
            if best:
                match[i][k] = (best[1], best[2])
                wcount[(i, best[1])] += 1

    # 3) eşleşme grafiği (iki yönde en az 3 nokta) → 2 renk
    adj = defaultdict(set)
    for (i, j), n in wcount.items():
        if n >= 3 and wcount.get((j, i), 0) >= 3:
            adj[i].add(j)
            adj[j].add(i)
    color = {}
    for s in adj:
        if s in color:
            continue
        comp, q = [s], deque([s])
        color[s] = 0
        bad = False
        while q:
            u = q.popleft()
            for v in adj[u]:
                if v not in color:
                    color[v] = 1 - color[u]
                    comp.append(v)
                    q.append(v)
                elif color[v] == color[u]:
                    bad = True
        L = [0.0, 0.0]
        for u in comp:
            p = ways[u][3]
            L[color[u]] += sum(math.dist(a, b) for a, b in zip(p, p[1:]))
        keepc = 0 if L[0] >= L[1] else 1
        for u in comp:
            color[u] = "keep" if color[u] == keepc else "drop"
        if bad:  # tek döngü: renk çelişkisi olan çiftlerde eşleşmeyi yok say
            pass

    def paired(i, k):
        m = match[i].get(k)
        if not m or i not in color:
            return None
        j = m[0]
        if j not in color or color[j] == color[i] or j not in adj[i]:
            return None
        return m

    remap = {}
    new_ways = []
    center_runs = []  # (liste indeksi) orta hat koşuları
    kept_idx = set()
    stats = defaultdict(int)
    # tutulan yollar: eşleşen noktalar orta noktaya kayar, koşulara bölünür
    for i in cand:
        if color.get(i) != "keep":
            continue
        wy, t, hw, pts = ways[i]
        flags, newp = [], []
        for k, v in enumerate(pts):
            m = paired(i, k)
            if m:
                nv = (round((v[0] + m[1][0]) / 2, 2), round((v[1] + m[1][1]) / 2, 2))
                remap[v] = nv
                newp.append(nv)
                flags.append(True)
            else:
                newp.append(v)
                flags.append(False)
        # 1-2 noktalık eşleşme adacıklarını yok say (kavşak ağzı)
        runs, s = [], 0
        for k in range(1, len(pts) + 1):
            if k == len(pts) or flags[k] != flags[s]:
                runs.append((s, k - 1, flags[s]))
                s = k
        for a0, a1, f in runs:
            if f and a1 - a0 < 2:
                for k in range(a0, a1 + 1):
                    newp[k] = pts[k]
                    remap.pop(pts[k], None)
                    flags[k] = False
        runs, s = [], 0
        for k in range(1, len(pts) + 1):
            if k == len(pts) or flags[k] != flags[s]:
                runs.append((s, k - 1, flags[s]))
                s = k
        for r, (a0, a1, f) in enumerate(runs):
            lo = a0 - 1 if a0 > 0 else a0  # komşu koşuyla ortak sınır noktası
            seg = newp[lo:a1 + 1]
            if len(seg) < 2:
                continue
            tt = dict(t, oneway="no") if f else t
            new_ways.append([dict(wy, id=wy["id"] * 100 + r), tt, hw, seg])
            if f:
                center_runs.append(len(new_ways) - 1)
                stats["orta hat m"] += LineString(seg).length
        kept_idx.add(i)
    # orta hat ağacı (nokta yakalama için)
    cpts = []
    for ci in center_runs:
        for v in new_ways[ci][3]:
            cpts.append((v, ci))
    ctree = STRtree([Point(v) for v, _ in cpts]) if cpts else None
    cseg = [LineString(new_ways[ci][3]) for ci in center_runs]
    csegtree = STRtree(cseg) if cseg else None
    inserts = defaultdict(list)  # ci -> [(t, nokta)]

    def snap_to_center(v):
        if ctree is None:
            return None
        P = Point(v)
        near = [cpts[q] for q in ctree.query(P.buffer(snap))]
        if near:
            return min(near, key=lambda x: math.dist(x[0], v))[0]
        q = [q for q in csegtree.query(P.buffer(D * 0.75))]
        if not q:
            return None
        q = min(q, key=lambda q: cseg[q].distance(P))
        if cseg[q].distance(P) > D * 0.75:
            return None
        ci = center_runs[q]
        tpos = cseg[q].project(P)
        c = cseg[q].interpolate(tpos)
        nv = (round(c.x, 2), round(c.y, 2))
        inserts[ci].append((tpos, nv))
        return nv

    # atılan yollar: eşleşen noktalar silinir; kalan koşular tek yönlü, uçları orta hatta bağlanır
    for i in cand:
        if color.get(i) != "drop":
            continue
        wy, t, hw, pts = ways[i]
        flags = [paired(i, k) is not None for k in range(len(pts))]
        for k in range(len(pts)):
            if flags[k]:
                nv = snap_to_center(pts[k])
                if nv is not None:
                    remap[pts[k]] = nv
                else:
                    flags[k] = False
        runs, s = [], 0
        for k in range(1, len(pts) + 1):
            if k == len(pts) or flags[k] != flags[s]:
                runs.append((s, k - 1, flags[s]))
                s = k
        for r, (a0, a1, f) in enumerate(runs):
            if f:
                stats["silinen nokta"] += a1 - a0 + 1
                continue
            seg = list(pts[a0:a1 + 1])
            if a0 > 0:
                seg = [remap[pts[a0 - 1]]] + seg  # önceki silinen bölgenin orta hat noktasından başla
            if a1 < len(pts) - 1:
                seg = seg + [remap[pts[a1 + 1]]]
            if len(seg) >= 2:
                new_ways.append([dict(wy, id=wy["id"] * 100 + 50 + r), t, hw, seg])
        kept_idx.add(i)
    # orta hatta eklenecek yakalama noktaları
    for ci, lst in inserts.items():
        seg = new_ways[ci][3]
        cum = [0.0]
        for p, q in zip(seg, seg[1:]):
            cum.append(cum[-1] + math.dist(p, q))
        out = list(seg)
        have = set(seg)
        for tpos, nv in sorted(lst, reverse=True):  # arkadan öne: önceki indeksler geçerli kalır
            if nv in have:
                continue
            k = max(q for q in range(len(cum) - 1) if cum[q] <= tpos) if tpos > 0 else 0
            out.insert(k + 1, nv)
            have.add(nv)
        new_ways[ci][3] = out
    # diğer yollar
    result = []
    for idx, w in enumerate(ways):
        if idx in kept_idx:
            continue
        wy, t, hw, pts = w
        if idx in cand:  # eşleşmeyen aday: yoğunlaştırılmış hali kalır
            pass
        result.append((wy, t, hw, [remap.get(p, p) for p in pts]))
    result += [tuple(w) for w in new_ways]
    out = []
    for wy, t, hw, pts in result:
        dd = [pts[0]]
        for p in pts[1:]:
            if p != dd[-1]:
                dd.append(p)
        if len(dd) >= 2 and LineString(dd).length >= 1.0:
            out.append((wy, t, hw, dd))
        else:
            stats["çöken yol"] += 1
    stats["çift"] = sum(len(v) for v in adj.values()) // 2
    return out, {k: round(v) for k, v in stats.items()}
