"""SAKLAZ Türkiye Map - test paketini (.scs, zip biçimi) oluşturur.

Kullanım:
    .venv\\Scripts\\python.exe -I tools\\packaging\\build_scs.py [--home "D:\\SAKLAZ_DEV"] [--map saklaz] [--dry-run]

- map/standalone/package/ içindeki manifest.sii + description.txt (+ varsa icon.jpg) alınır.
- Editörün D:\\SAKLAZ_DEV altında kaydettiği <map>.mbd ve <map>/ sektör klasörü pakete /map/ altına eklenir.
- Çıktı: releases/saklaz_turkiye_map_<sürüm>_<tarih>.scs  (releases/*.scs depoya girmez)

Hiçbir oyun veya profil dosyası DEĞİŞTİRİLMEZ; yalnızca okunur. Paketi oyuna kurmak (mod klasörüne
kopyalamak) kullanıcının elle yapacağı ayrı bir adımdır.
Not: Oyunun bağımsız haritayı hangi .mbd adıyla yükleyeceği (europe.mbd yerine geçme vs.) Aşama F'de
gerçek oyun testiyle doğrulanmalıdır; bkz. docs/OVERNIGHT_REPORT_20261121.md.
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "map" / "standalone" / "package"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default=r"D:\SAKLAZ_DEV")
    ap.add_argument("--map", default="saklaz")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    manifest = (PKG / "manifest.sii").read_text(encoding="utf-8")
    ver = re.search(r'package_version:\s*"([^"]+)"', manifest).group(1)
    prof = Path(a.home) / "Euro Truck Simulator 2"
    mbd = next(iter(sorted(prof.rglob(f"{a.map}.mbd"))), None) if prof.exists() else None
    if mbd is None:
        print(f"HATA: '{a.map}.mbd' {prof} altında bulunamadı. Önce haritayı editörde kaydedin (docs/EDITOR_GUIDE.md).")
        raise SystemExit(2)
    sec = mbd.with_suffix("")
    files = [(PKG / n, n) for n in ("manifest.sii", "description.txt", "icon.jpg") if (PKG / n).exists()]
    files.append((mbd, f"map/{mbd.name}"))
    if sec.is_dir():
        files += [(p, f"map/{sec.name}/{p.relative_to(sec).as_posix()}") for p in sorted(sec.rglob("*")) if p.is_file()]
    out = ROOT / "releases" / f"saklaz_turkiye_map_{ver}_{datetime.now():%Y%m%d_%H%M}.scs"
    print(f"{len(files)} dosya -> {out}")
    for src, arc in files[:20]:
        print(f"  {arc}  ({src.stat().st_size} bayt)")
    if a.dry_run:
        return
    out.parent.mkdir(exist_ok=True)
    if out.exists():
        raise SystemExit(f"HATA: {out} zaten var; üzerine yazılmadı.")
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for src, arc in files:
            z.write(src, arc)
    print("Paket oluşturuldu.")


if __name__ == "__main__":
    main()
