# Tam Şehir Haritası – Durum ve Plan (2026-11-21)

İstek: yalnızca yollar değil; Gebze, Darıca ve Çayırova'nın binaları ve ara sokaklarıyla tam haritası.

## 1. Kavşak denemelerinden çıkan ölçek sonucu

Editörde kavşak prefabları denendi (`cross/hw3-2_x_city2-1`, `ger hw3 r2 fork`, `ger hw3 exit joint`).
Prefablar gerçek boyutlu: bölünmüş yol üzerindeki bir yonca kavşak yaklaşık **290 m**. Kavşaklar arasındaki
mesafe ölçeğe göre şöyle:

| Kavşak arası | Gerçek | 1:19 | 1:10 | 1:5 | 1:3 |
|---|---|---|---|---|---|
| Çayırova K-63 → Darıca bağlantısı | 5.238 m | 276 | 524 | 1.048 | 1.746 |
| Darıca bağlantısı → Gebze merkez | 1.692 m | **89** | 169 | 338 | 564 |
| Gebze merkez → Gebze Kavşağı (TEM) | 3.467 m | 182 | 347 | 693 | 1.156 |

1:19'da kavşaklar üst üste biniyor; binalara ve ara sokaklara da yer kalmıyor. ETS2'nin kendi şehirleri
yaklaşık 1:3 ölçekte. **Karar: tam şehir haritası 1:3 ölçekte üretilecek** (`config/aoi.json` → `city_scale_divisor`).
Elle çizilen 1:19 `saklaz` haritası koridor denemesi olarak kalıyor.

## 2. Hacim ve yöntem

Çekirdek alan (S 40.745, W 29.330, N 40.875, E 29.500), 1:3 ölçekte (`data/processed/map_export_s3_summary.json`):

- 12.242 yol zinciri, 49.349 düğüm, ~744 km oyun yolu, ~4,6 × 4,6 km alan
- 2.235 adet 3+ kollu kesişim (prefab gerekir)
- Binalar: OSM'den indiriliyor (`tools/geo/fetch_buildings.py`)

Fareyle çizim bu hacimde mümkün değil (36 düğümlük D-100 ≈ 15 dk). Yöntem: **TruckLib** (sk-zk, GPL-2.0)
ile programatik üretim. TruckLib 0.5.3, harita sürümü 907'yi (ETS2 1.59–1.62) destekliyor.

## 3. Hazır olanlar

| Dosya | Durum |
|---|---|
| `tools/geo/build_city_export.py` | Çalıştı: 1:3 yol/kavşak/bina dışa aktarımı |
| `tools/geo/fetch_buildings.py` | Bina indirme (Overpass yoğun, yeniden deniyor) |
| `tools/mapgen/Program.cs`, `.csproj`, `mapping.json` | TruckLib üretici: **yazıldı, henüz derlenmedi** |
| `tools/mapgen/run.ps1` | .NET 10'u yalnızca `D:\SAKLAZ_DEV\tools\dotnet` altına kurar, tipleri listeler, `saklaz_city` haritasını üretir |

## 4. Engel

.NET 10 SDK kurulumu (yerel klasöre bile) bu oturumun otomatik izin denetimi tarafından engellendi.
İzin kuralı eklemem de engellendi. Kullanıcının yapabileceği iki yol var:

1. Bir PowerShell penceresinde `tools\mapgen\run.ps1` dosyasını kendisi çalıştırmak (kurulum + üretim tek komut), **veya**
2. Claude Code izin modunu değiştirmek ya da `.claude/settings.local.json` dosyasına
   `D:\SAKLAZ_DEV\tools\...` komutları için izin kuralı eklemek; sonra Claude kurulumu ve üretimi yapar.

## 5. Üretimden sonraki adımlar (Claude yapacak)

1. `list` çıktısından gerçek road_look / bina modeli adlarını seçip `mapping.json`'u doldurmak.
2. Küçük deneme (ör. 200 yol) → editörde aç → *Map > Recompute map* → kaydet → yeniden aç.
3. Tüm yollar + binalar.
4. Kavşaklar: ana kesişimlere prefab (TruckLib `Prefab.Add` + `Attach`; kütüphane prefabların "bozulabileceğini" belirtiyor, bu yüzden aşamalı ilerlenecek).
5. Şirket/depo ve başlangıç noktası → oyun içi test.

## 6. Güncelleme – 2026-11-21 12:30

- .NET 10.0.404 kullanıcı tarafından `run.ps1` ile `D:\SAKLAZ_DEV\tools\dotnet` altına kuruldu; üretici derlendi.
- Gerçek tipler def.scs/.pmd'den doğrulandı: yollar `ger14` / `ger11` / `ger5` / `ger1`; binalar `0700b` (var1, var2), `3q001` (variant1), `3z001` (variant1–4, 6 renk).
- 37 bin parçalık ilk tam harita editörde "Parameter packet batch system overflow" ile çöktü. Sadeleştirme (6 m), en kısa parça 8 m, servis yolu ve living_street dışlama, ara sokakta arazi 0 ile 9.411 yol / 16.671 parça / 704 bina → **çökmeden açıldı**, *Recompute map* + kayıt yapıldı.
- SnowyMoon (ReShade + OptiScaler + DLSS5) kullanıcı tarafından `tools/maintenance/remove_snowymoon.ps1` ile yedeğe taşındı. Sonrasında editör 3 zararsız hata ile, 9 sn'de açıldı; OptiScaler katmanı yok.
- Sıradaki: kavşak prefabları (2.235 nokta), daha yoğun bina yerleşimi (Buildings öğesi), şirket/başlangıç noktası, oyun içi test.

## 7. Kavşaklar – 2026-11-21 12:45

- `tools/geo/build_city_graph.py`: ağ gerçek OSM kesişimlerinden bölündü, prefab sığan kesişimler seçildi
  (şehir yolları, 3-4 kol, kol ≥ 24 oyun m, kavşaklar arası ≥ 55 m) → 385 aday; sonra prefab olmayan
  kesişimlerde parçalar yeniden birleştirildi (editör ~17 bin öğe üstünde render taşmasıyla çöküyor).
- `tools/mapgen buildgraph`: her kavşakta .ppd düğümlerine göre 0–359° tarama + kol/düğüm eşlemesi
  (en büyük açı hatası ≤ 40°). Prefablar: T `mod_ger_67` (ger_r1_x_r1_t_narrow_tmpl), X `mod_ger_63`
  (ger_r1_x_r1_narrow_tmpl), look `ger_1`, variant `clean`. Yollar `AppendRoad` / `Attach` ile bağlandı.
- Sonuç: **313 kavşak prefabı** (72 aday açı uyuşmazlığından reddedildi), 10.032 yol, 15.641 parça,
  613 yol-prefab bağlantısı, 704 bina. Editörde çökmeden açıldı, *Recompute map* + kayıt yapıldı.
- Bilinen: yüklemede "Terrain point count doesn't match" uyarıları (prefab arazisi, TruckLib'in prefab
  desteği "deneysel"); yeniden hesaplama sonrası editör kaydıyla yazıldı. Ana yollar (D-100, TEM, birincil)
  ile ara sokak kesişimleri ve sık aralıklı kesişimler henüz prefabsız.

## 8. Ana cadde (r2) kavşakları ve oyun içi test – 2026-11-21 13:40

- Kavşak seçimi sınıf kurallı: her kol r1 (şehir) ya da r2 (ana cadde, `r2_divided`) sınıfında; izinli
  desenler T için (3,0) (2,1) (1,2) (0,3), dörtlü için (4,0) (0,4). r2 kolu olan kavşakta yarıçap 23,25 m.
- Prefablar (`mapping.json` → `junctions.prefabs`, `.ppd` düğüm sırasıyla kol sınıfı):
  `mod_ger_67` r1 T, `mod_ger_63` r1 X, `mod_ger_75` r2×r1 T, `mod_ger_72` r1×r2 T, `mod_ger_88` r2 T,
  `mod_ger_53` r2 X. `r2_divided` yol tipi `ger7` (ger road 2 city narrow) yapıldı.
- Sonuç: 436 aday → **348 kavşak** (mod_ger_67=276, mod_ger_75=40, mod_ger_63=32), 88 reddedildi.
- Arazi: şehir yollarına arazi (terrain_size > 0) verilince editör "Parameter packet batch system overflow"
  ile çöküyor. Şimdilik `terrain_size = { hw3_divided: 10, r2_divided: 6, default: 0 }`.
- Editörde açıldı, *Recompute map* + kayıt yapıldı; yedek `D:\SAKLAZ_DEV\backups\saklaz_city_r2junc_*`.
- **Oyun içi önizleme** (`eurotrucks2.exe -preview /map/saklaz_city.mbd -previewconfig /preview_config/default.cfg`):
  harita 12 sn'de yüklendi, tır (0,0,0)'a yerleşti, oyun çökmedi. Görüntü: `docs/img/ingame_preview_r2junc.jpg`.
- **Uyarı:** 13:06'da editör ve oyun önizlemesi aynı anda açıkken bilgisayar aniden kapandı (Kernel-Power 41,
  hata kodu yok → donma/güç kesintisi). Önizlemeyi **editör kapalıyken tek başına** çalıştırmak sorunsuz oldu.
- Eksikler: (0,0,0) yol üstünde değil, tır toprak tümseğe doğuyor → başlangıç noktası/şirket gerekli;
  merkezde üst üste binen paralel yollar var; D-100/TEM kavşakları ve sık kesişimler hâlâ prefabsız.

## 9. Başlangıç noktası – 2026-11-21 13:50

- Önizleme tırı her zaman (0,0,0)'a, -Z yönüne bakarak koyuyor. `buildgraph` artık haritayı kaydırıyor:
  Z eksenine paralel (±4°), ≥ 50 m düz, kavşaklardan ≥ 60 m ve başka yoldan ≥ 25 m uzak, orijine en yakın
  `r1_city`/`r2_divided` parçasının ortası (0,0)'a geliyor (`mapping.json` → `spawn` ile ayarlanabilir).
  Seçilen: kenar 7052 (r1_city), eski konum (964,2; -1522,4).
- Oyunda tır yol üstünde doğdu ve sürüldü (119 km/s). Görüntü: `docs/img/ingame_spawn_on_road.jpg`.
- Eksik: arazi yok; yol dışı boşluk ve tır yoldan çıkınca düşüyor.
