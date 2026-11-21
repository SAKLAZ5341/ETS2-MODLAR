"""SAKLAZ Türkiye Map - Map Editor çıktısını SALT OKUNUR kontrol eder.

Kullanım:
    .venv\\Scripts\\python.exe -I tools\\validation\\check_editor_output.py [--home "D:\\SAKLAZ_DEV"] [--map saklaz]

Kontroller:
  1. Geliştirme profili var mı?
  2. Kayıtlı harita modülü (.mbd) ve sektör dosyaları var mı (beklenen ve olası konumlar)?
  3. editor.log.txt: sürüm, komut satırı, aktif mod sayısı, açılan/kaydedilen harita izleri, hata özeti.
Hiçbir dosya yazılmaz veya değiştirilmez; sonuç ekrana yazdırılır.
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
import sys as _sys
_sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default=r"D:\SAKLAZ_DEV")
    ap.add_argument("--map", default="saklaz")
    a = ap.parse_args()
    prof = Path(a.home) / "Euro Truck Simulator 2"
    ok = True
    print(f"# Editör çıktısı kontrolü - {datetime.now():%Y-%m-%d %H:%M}")
    print(f"Profil: {prof} -> {'VAR' if prof.is_dir() else 'YOK'}")
    if not prof.is_dir():
        raise SystemExit(1)

    mbds = sorted(prof.rglob("*.mbd"))
    print(f"\n## Harita modülleri (.mbd): {len(mbds)}")
    for m in mbds:
        sec_dir = m.with_suffix("")
        secs = list(sec_dir.glob("*")) if sec_dir.is_dir() else []
        kinds = Counter(p.suffix for p in secs)
        print(f"- {m.relative_to(prof)}  ({m.stat().st_size} bayt, {datetime.fromtimestamp(m.stat().st_mtime):%Y-%m-%d %H:%M})"
              f"  sektör klasörü: {'var' if sec_dir.is_dir() else 'yok'}  dosyalar: {dict(kinds)}")
    target = [m for m in mbds if m.stem.lower() == a.map.lower()]
    if not target:
        ok = False
        print(f"- '{a.map}.mbd' BULUNAMADI (harita henüz kaydedilmemiş).")

    log = prof / "editor.log.txt"
    print(f"\n## editor.log.txt: {'var' if log.exists() else 'yok'}")
    if log.exists():
        txt = log.read_text(encoding="utf-8", errors="replace").splitlines()
        print(f"- satır: {len(txt)}, son yazma: {datetime.fromtimestamp(log.stat().st_mtime):%Y-%m-%d %H:%M}")
        for pat in (r"init ver\.", r"Command line", r"Active \d+ mods", r"\[map\]|map .*(load|save)|Saving|Saved map|Loading map|\.mbd"):
            hits = [l for l in txt if re.search(pat, l, re.I)]
            for h in hits[:6]:
                print(f"  {h.strip()[:200]}")
        errs = Counter(re.sub(r"'[^']*'|\([^)]*\)|\d+", "#", l.split("<ERROR>", 1)[1]).strip()[:90]
                       for l in txt if "<ERROR>" in l)
        print(f"- <ERROR> satırı: {sum(errs.values())}")
        for e, c in errs.most_common(10):
            print(f"  {c:5d} x {e}")
        if any("truncated" in l for l in txt[-3:]):
            print("- UYARI: log boyut sınırında kesilmiş.")
    print(f"\nSONUÇ: {'harita kaydı bulundu' if ok else 'harita kaydı YOK'}")


if __name__ == "__main__":
    main()
