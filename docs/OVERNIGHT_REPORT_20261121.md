# Gece Çalışması Raporu – 2026-11-21

Hazırlayan: Claude Code · Çalışma: 03:30–04:00 · Kapsam: kullanıcının verdiği gece görevi

## 1. Kısa özet

| Hedef | Durum |
|---|---|
| Git deposu, yedek | ✅ Tamam – 4 commit, push yok. Başlangıç yedeği: `D:\SAKLAZ_DEV\backups\project_before_git_20261121.tar` |
| Proje içi Python sanal ortamı | ✅ `.venv` (Python 3.12.8) – `requirements.txt` |
| Gerçek OSM verisi | ✅ 6 veri seti, OSM zaman damgası 2026-11-21T00:33Z, ODbL kayıtlı |
| Koordinat dönüşümü | ✅ WGS84 → UTM 35N → ETS2 oyun metresi (1:19 ve 1:10 iki sürüm) |
| Yol sınıflandırma ve bağlantı doğrulama | ✅ 23.567 yol, 14 testten 12'si geçti |
| Editöre hazır dosyalar | ✅ Düğüm tabloları, CSV, GeoJSON, görsel, kılavuz, paketleme betiği |
| **Map Editor'de harita modülü** | ✅ **Tamam (11:29)** – ekran erişimi verildikten sonra `saklaz.mbd` oluşturuldu (bkz. §8) |
| Haritayı kaydet, yeniden aç, test et | ✅ Kaydedildi; editör kapatılıp `-edit saklaz` ile yeniden açıldı: "Map loaded" |
| D-100 Çayırova–Gebze editörde | ✅ Gerçek koordinatlarla çizildi (36 düğüm, sapma ≈0,3 m) |
| Oyun içi sürüş testi | ❌ Yapılmadı – başlangıç noktası/şirket yok; bağımsız harita yükleme yöntemi doğrulanmadı |

**Dürüst durum:** Gerçek coğrafi veri ve editöre aktarılmaya hazır prototip verisi tamam. ETS2 içinde
**henüz bir harita modülü yok**. Editörü yalnızca ekran üzerinden (tıklama/klavye) kullanabiliyorum ve
bu oturumda ekran erişimi verilmedi. SCS sektör dosyaları belgelenmemiş ikili dosyalardır; proje
talimatı gereği tahminle üretilmedi.

## 2. Yapılanlar

### 2.1 Altyapı
- `git init` (dal `main`); mevcut tüm dosyalar ilk commit'te korundu. `.gitignore`: ham veri, venv, ENV raporları, büyük türetilmiş dosya.
- `.venv`: requests, shapely, pyproj, networkx, matplotlib (yalnızca proje içine).
- `env_check.ps1` hatası düzeltildi: Steam'de kayıtlı ama artık olmayan E:/F: kütüphaneleri betiği çökertiyor ve ETS2'yi "bulunamadı" gösteriyordu. Test: ETS2 1.62.3.3, 107 DLC bulundu, **0 hata**.

### 2.2 Coğrafi veri (`tools/geo/fetch_osm.py`)
- İlçe sınırları OSM'den alındı (Gebze, Darıca, Çayırova, Dilovası); bbox bu sınırlardan hesaplandı:
  S 40.742, W 29.323, N 41.054, E 29.763.
- İndirilenler: yollar (23.567 way), kavşaklar (142 `motorway_junction`), arazi kullanımı/sanayi, yerleşimler, demiryolu/kıyı.
- Her dosyada sorgu, zaman, lisans kaydı (`data/raw/*.meta.json`). Kaynaklar: `docs/GEO_DATA_SOURCES.md`.

### 2.3 Yol ağı (`tools/geo/build_network.py`) → `docs/ROAD_NETWORK.md`
- D-100 (trunk) 90 km, O-4/TEM 106 km, O-7 121 km, O-5 11 km (iki yön toplam, bbox içi).
- Ana ağ (motorway…tertiary + rampalar): en büyük bağlı bileşen **%99,32**.
- 1:19 ölçekte ana ağ ≈ **97,8 km oyun yolu**.
- 1.234 sanayi/lojistik/liman alanı (511'i adlı): TOSB, İAYOSB, Kimyacılar OSB, Gebze V Kimya OSB, DP World Yarımca, Evyapport, Borusan Lojistik… → `docs/CITY_DATABASE.md`.

### 2.4 Prototip koridoru (`tools/geo/build_prototype.py`) → `docs/EDITOR_NODES_s19.md`
Köken (0,0) = Gebze OSM düğümü 26505108. +X doğu, +Z güney.

| Segment | Gerçek | 1:19 oyun | Güzergâh (OSM) |
|---|---|---|---|
| P1 D-100 doğu yönü (Çayırova batı sınırı → Gebze) | 6.355 m | 334 m | D-100 |
| P1 D-100 batı yönü | 6.241 m | 329 m | D-100 |
| P2 D-100 → TEM | 3.985 m | 210 m | D-100 → Gebze 1 Kavşağı → Gebze Kavşağı |
| P3 Darıca → D-100 | 5.031 m | 265 m | Tuzla Cd. → Aliarıcan Cd. → İstasyon Cd. → Eskihisar Feribot Yolu |
| P4 Gebze merkez → D-100 | 1.114 m | 59 m | Zübeyde Hanım Cd. → Hükümet Cd. → Adliye Cd. |
| P5 Çayırova → TEM | 5.986 m | 315 m | Adnan Kahveci Cd. → Muammer Aksoy Cd. → Şekerpınar Kavşağı |

177 editör düğümü (1:19), en fazla 20 oyun metre aralıkla, gerçek geometriden sapma ≤ 2,9 m.
Görsel: `docs/img/prototype_corridor_s19.png` (1:10 sürümü de var).

### 2.5 Editör ve paketleme hazırlığı
- `docs/EDITOR_GUIDE.md`: editörü doğru profille açma, `saklaz` haritasını oluşturma/kaydetme, çizim sırası.
- `tools/validation/check_editor_output.py`: kaydedilen haritayı ve editor.log'u **salt okunur** denetler.
- `map/standalone/package/` (manifest.sii, description.txt) + `tools/packaging/build_scs.py`: harita
  kaydedildikten sonra `releases/` altına test .scs paketi üretir (oyun klasörüne kopyalamaz).

## 3. Test sonuçları (`tests/geo_validation_report.md`)

12/14 geçti. Kalanlar:
- **T08 KALDI – D-100 OSM'de 5 parça.** Yol fiziksel olarak kesintisiz; Gebze'de way **1383071546**
  (trunk, 40.7930 / 29.4300) üzerinde `ref=D 100` etiketi eksik. Prototip bu durumdan etkilenmedi
  (iki yön de kesintisiz bulundu). İsterseniz OSM'de düzeltilebilir (sizin kararınız).
- **T14 KALDI – Editörde `saklaz.mbd` yok.** Elle adım gerekiyor.

## 4. Yapılamayanlar ve nedenleri

| İş | Neden | Gereken manuel adım |
|---|---|---|
| Map Editor'de boş harita modülü | Ekran erişimi (computer use) isteği reddedildi; editör yalnızca arayüzden kullanılabiliyor | `docs/EDITOR_GUIDE.md` §1 (≈5 dk) **veya** yeni oturumda ekran erişimini onaylayın, ben yapayım |
| D-100/TEM/Darıca yollarını editörde çizmek | Aynı neden | `docs/EDITOR_NODES_s19.md` tablolarıyla çizim |
| Kaydet → yeniden aç → oyun içi test | Harita yok | Harita oluşunca `check_editor_output.py`, sonra `build_scs.py` |
| Yükseklik verisi | Kapsam/öncelik dışında bırakıldı | Copernicus GLO-30 indirme (sonraki adım) |

## 5. Açık kararlar ve riskler

1. **Ölçek:** 1:19 ile tüm Çayırova–Gebze D-100'ü ~330 m, Gebze–Darıca ~330 m oyun mesafesi olur; bu
   ETS2 standart haritasıyla tutarlı ama küçük. 1:10 sürümü de hazır (~635 m). Editörde çizime
   başlamadan **ölçeği seçin**; sonradan değiştirmek yeniden çizim demektir.
2. **Bağımsız haritanın oyunda yüklenmesi:** Oyun oynanışta varsayılan haritayı yükler. Bağımsız
   haritanın pakette hangi ad/yapı ile yükleneceği (europe.mbd yerine geçme ya da başka yöntem)
   **resmî dokümantasyon ve gerçek oyun testiyle doğrulanmadı**. Editörde `saklaz` adıyla çalışmak güvenli; yükleme yöntemi Aşama F'de test edilmeli.
3. **Gebze OSB ve Gebze Plastikçiler OSB** OSM'de adlı poligon değil; sınırlar elle eşlenmeli.
4. Bağlantı rotaları (P2–P5) yönsüz grafta hesaplandı; tek-yön kuralları yalnızca D-100'e uygulandı.
5. Ana oyun profilinde 65 mod (2 ProMods sürümü, çakışan harita modları). Editörü **yalnızca** `-homedir D:\SAKLAZ_DEV` ile açın.

## 6. Değişen / oluşturulan dosyalar

- Proje: `.gitignore`, `requirements.txt`, `config/aoi.json`, `tools/geo/*.py`, `tools/validation/check_editor_output.py`,
  `tools/validation/env_check.ps1` (düzeltme), `tools/packaging/build_scs.py`, `map/standalone/package/*`,
  `tests/*`, `data/**` (türetilmiş, ODbL), `docs/*` (yeni: TECHNICAL_ARCHITECTURE, ROAD_NETWORK, CITY_DATABASE,
  EDITOR_GUIDE, EDITOR_NODES_s19/s10, PC_GAMING_SETTINGS, bu rapor).
- D:\SAKLAZ_DEV: yalnızca `backups\project_before_git_20261121.tar` eklendi. Profil/harita dosyalarına dokunulmadı.
- ETS2 kurulum dizini, ana profil, modlar, Steam: **dokunulmadı**.

## 7. Sonraki adımlar

1. Ölçeği seçin (1:19 / 1:10 / başka).
2. Editörde `saklaz` haritasını oluşturup kaydedin (veya bana ekran erişimi verin).
3. `check_editor_output.py` → sonuç bana iletilsin; P1 D-100 çizimi.
4. P4 Gebze, P3 Darıca, P2/P5 TEM bağlantıları; kavşak prefabları (`ROAD_NETWORK.md` kavşak tablosu).
5. Bir depo/fabrika (TOSB veya Gebze OSB bölgesi) + başlangıç noktası → Aşama F oyun içi test.


## 8. Ek – Map Editor oturumu (2026-11-21 11:20–11:40, ekran erişimiyle)

| Adım | Sonuç | Kanıt |
|---|---|---|
| Siyah ekran | Arıza değil: harita boşken görüş alanı siyah. İlk öğe eklenince arazi ve yol görüntülendi | `docs/img/editor_d100_s19.jpg` |
| Boş harita kaydı | Editör reddetti: `Saving empty map is not allowed!` → tek deneme yolu eklenip kaydedildi, sonra silindi | editor.log |
| Kayıt yeri | `D:\SAKLAZ_DEV\Euro Truck Simulator 2\mod\user_map\map\saklaz.mbd` + `saklaz\sec*.{base,aux,data,desc,layer}` | `check_editor_output.py` |
| Yeniden açma | Editör kapatıldı, `-homedir D:\SAKLAZ_DEV -noworkshop -edit saklaz` ile açıldı: `Map '/map/saklaz.mbd' ... Map loaded` | editor.log |
| D-100 | `ger hw 3 lanes 2m offset tmpl` (base oyun, DLC yok), 36 düğüm: Çayırova batı sınırı (−285,0; −57,4) → Gebze Kavşağı yakını (143,4; −5,0). İmleç okumasıyla hedeften sapma ≈0,3 m | ekran + durum çubuğu |
| Paket | `releases/saklaz_turkiye_map_0.1.0-dev_*.scs` (23 dosya, zip doğrulandı). Oyuna **kurulmadı** | `build_scs.py` |
| Testler | 13/14 geçti (kalan: OSM'de D-100 `ref` etiket boşluğu) | `tests/geo_validation_report.md` |

Yedekler: `D:\SAKLAZ_DEV\backups\user_map_saklaz_*.tar` (her kayıttan sonra).

### Öğrenilen editör davranışları
- Menüler: *File → New / Open / Save / Save As (Ctrl+Shift+S)*; kayıt penceresinin dizini `/map/`. "Source" kutusu DLC filtresidir, boş bırakılmalı.
- Araçlar: *New Item (E)*, *Move Item (M)*, *Delete Item (D)*. New Item modunda her tıklama yola düğüm ekler; ~10 oyun metreden yakın tıklamalar yok sayılır; Esc bitirir.
- Kamera yukarıdan bakıyor; durum çubuğundaki imleç koordinatı yalnızca arazi veya yol üzerindeyken güncelleniyor.
- Bir yol düğümüne yalnızca iki yol bağlanabiliyor. **Gebze, Darıca ve TEM bağlantıları için kavşak prefabı gerekiyor**; bu yüzden P2–P5 henüz çizilmedi.
- Editör exe ile parametreli başlatılınca Steam "bu parametrelerle başlatılsın mı" onayı gösteriyor (Steam penceresinde).
- Oyun klasöründe **OptiScaler** (üçüncü taraf ölçekleyici, ekranda "Insert for menu" yazısı) yüklü. Önceki siyah ekran/çökme şikâyetlerinde etkisi olabilir; oyun dosyası olduğu için dokunulmadı.

### Sonraki adımlar (güncel)
1. Kavşak prefabları: Gebze Kavşağı (D-100↔TEM), Darıca ve Gebze merkez bağlantıları.
2. Bir şirket/depo prefabı ve oyuncu başlangıç noktası.
3. Bağımsız haritanın oyunda nasıl yükleneceğini doğrulamak (paket yapısı/harita adı), sonra oyun içi sürüş testi.
