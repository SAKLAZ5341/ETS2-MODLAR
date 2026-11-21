# AŞAMA A – Ortam Analizi Raporu

Durum: **TAMAMLANMADI – kullanıcı bilgisayarından veri bekleniyor**
Tarih: 2026-11-20

## Neden tamamlanmadı (kanıt)

Bu geliştirme oturumu bulut tabanlı bir Linux çalışma alanında çalışıyor.
ETS 2 kurulu Windows bilgisayara erişimi yok (cihaz köprüsü bağlı değil).
SCS Map Editor yalnızca Windows sürümünde çalışır. Bu nedenle aşağıdaki
maddeler **tahmin edilmeden** boş bırakıldı; `tools/validation/env_check.ps1`
çıktısıyla doldurulacak.

## Başlangıç raporu

| # | Konu | Sonuç | Kaynak |
|---|---|---|---|
| 1 | ETS 2 kurulum durumu | Bekleniyor | env_check.ps1 §1 |
| 2 | ETS 2 sürümü | Bekleniyor | env_check.ps1 §2 (exe sürümü + game.log.txt) |
| 3 | Map Editor erişimi | Bekleniyor | env_check.ps1 §4 + elle `-edit` ile açılış testi |
| 4 | Blender durumu | Bekleniyor | env_check.ps1 §5 |
| 5 | SCS Blender Tools durumu | Bekleniyor | env_check.ps1 §5 (io_scs_tools) |
| 6 | Eksik araçlar | Bekleniyor | env_check.ps1 §7 |
| 7 | Disk alanı | Bekleniyor | env_check.ps1 §8 |
| 8 | Coğrafi veri araçları | Aşağıda | – |
| 9 | Teknik engeller | Aşağıda | – |
| 10 | Önerilen sonraki adım | Aşağıda | – |

## Resmi kaynaklardan doğrulanan bilgiler

- Map Editor oyunun içinde gelir ve yalnızca Windows sürümünde çalışır.
- Güncel sürümlerde editör ayrı bir araç olarak `-edit` başlatma parametresiyle
  açılır; günlüğü `editor.log.txt` dosyasına yazılır (SCS Modding Wiki).
  `-noworkshop` eklemek, Workshop modlarının editöre yüklenmesini önler.
- Bağımsız (standalone) harita, `europe.mbd` dışında ayrı bir modül olarak
  kaydedilir (ProMods geliştirici forumu – resmi dokümanla Aşama C'de doğrulanacak).
- Resmi SCS Blender Tools 2.4.1, Blender 3.2–3.6 için yapılmıştır. Blender 4.x/5.x
  için yalnızca resmi olmayan topluluk güncellemeleri var (SCS forumu). 0.1.0 için
  model üretimi gerekmiyorsa Blender beklemeye alınabilir.

## 8. Coğrafi veri hazırlığı için araçlar

| Araç | Amaç | Durum |
|---|---|---|
| Python 3.10+ | Veri işleme, koordinat dönüşümü, rapor | Bulut ortamında hazır; PC'de env_check ile kontrol |
| pyproj, shapely, geopandas, osmium | Projeksiyon, geometri, OSM okuma | Aşama B'de bulut ortamına kurulabilir (PC'ye otomatik kurulum yok) |
| QGIS | Görsel doğrulama, katman kontrolü | PC'de kontrol edilecek; kurulum kullanıcı kararı |
| Git | Sürüm kontrolü | PC'de kontrol edilecek |

## 9. Bilinen / olası teknik engeller

1. **GitHub erişimi:** `SAKLAZ5341/Saklaz-Harita-Modu` deposu bu oturumun GitHub
   yetkisinde görünmüyor. Ya depo henüz oluşturulmadı ya da Claude GitHub
   uygulamasına bu depo için izin verilmedi.
2. **PC erişimi yok:** Aşama A verileri ancak betik çıktısıyla toplanabilir.
3. **Blender Tools sürüm uyumu:** Blender 4.x/5.x kuruluysa resmi eklenti çalışmaz.
4. **OSM → oyun koordinatı:** SCS haritası metre tabanlı yerel koordinat kullanır;
   ETS 2 varsayılan haritası ölçeklidir. "Gerçekçi mesafe" hedefi için ölçek
   kararı (1:1 veya oyun ölçeği) Aşama B'de belgelenmeli.
5. **Yükseklik verisi:** Editör DEM içe aktarmaz; arazi elle veya yardımcı
   veriyle şekillendirilir. Python yalnızca referans yükseklik tablosu üretebilir.

## 10. Önerilen sonraki adım

1. GitHub deposunu Claude'a erişilebilir yapın (depo oluşturma veya izin).
2. PC'de `env_check.ps1` çalıştırıp `ENV_REPORT_*.md` dosyasını paylaşın.
3. Rapor geldikten sonra bu dosya doldurulup Aşama A kapatılacak.

---

# AŞAMA B – Uygulanabilir Görev Listesi (taslak)

Aşama A kapanmadan başlamaz. Her görev tek başına test edilebilir.

| # | Görev | Çıktı | Kabul ölçütü |
|---|---|---|---|
| B1 | Çalışma alanının sınır kutusunu (bbox) belirle: Gebze, Darıca, Çayırova, Dilovası bağlantısı, OSB'ler | `data/processed/aoi.geojson` | QGIS'te OSM altlığıyla üst üste doğru oturuyor |
| B2 | OSM verisini indir (Geofabrik Türkiye veya Overpass, yalnızca bbox) | `data/raw/` + GEO_DATA_SOURCES.md kaydı | Lisans (ODbL) ve tarih kayıtlı |
| B3 | Yol ağını çıkar: motorway/trunk/primary/secondary + bağlantı rampaları | `data/roads/roads_aoi.geojson` | D-100 ve O-4/TEM kesintisiz çizgi |
| B4 | D-100 ve TEM güzergâhlarını ayrı katman yap, ref etiketleriyle doğrula | `roads/d100.geojson`, `roads/tem.geojson` | `ref` etiketi kontrolü, uzunluk raporu |
| B5 | Önemli kavşakları işaretle (kavşak düğümleri, `motorway_junction`) | `roads/junctions.geojson` + tablo | Her kavşak için ad, tip, koordinat, OSM id |
| B6 | Sanayi alanlarını çıkar: Gebze OSB, Plastikçiler OSB, lojistik alanları | `data/cities/industrial.geojson` | OSM `landuse=industrial` + ad eşleşmesi |
| B7 | Yerleşim merkezleri (Gebze, Darıca, Çayırova) | `data/cities/places.geojson`, CITY_DATABASE.md | Koordinatlar OSM node id'li |
| B8 | Referans sistemi ve dönüşüm yöntemini belgele (WGS84 → UTM 35N/EPSG:32635 → oyun metresi, ölçek kararı) | TECHNICAL_ARCHITECTURE.md + `tools/geo/transform.py` | Bilinen iki nokta arası mesafe testi |
| B9 | Kaba yükseklik profili (D-100, TEM boyunca) | `data/terrain/profiles.csv` | Kaynak ve çözünürlük kayıtlı |
| B10 | Veri doğrulama raporu (topoloji, kopukluk, eksik etiket) | `tests/geo_validation_report.md` + `tools/validation/validate_geo.py` | Tüm testler sonuçlarıyla listelenmiş, başarısızlar açıkça yazılmış |

Not: Aşama B'de hiçbir SCS harita dosyası üretilmez. Bu veriler, editörde elle
yol çizerken referans olarak kullanılacak.
