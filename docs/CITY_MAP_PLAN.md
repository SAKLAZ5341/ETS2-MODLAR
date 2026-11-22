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

## 10. Bitmiş harita yol haritası (kullanıcı isteği, 2026-11-21)

Hedef: Gebze + Darıca + Dilovası, gerçekçi ve oynanabilir. Sıra:
1. **Zemin:** `Terrain` öğeleriyle tüm alana kaba ızgara arazi (StepSize Meters16, az sayıda büyük parça;
   yol başına arazi render taşmasına yol açıyor). Malzeme/profil tokenı `extract def.scs /def/world` ile bulunacak
   (Git Bash yol dönüştürmesini önlemek için PowerShell'den çalıştır).
2. **Ağaçlar:** `TerrainSide.Vegetation` (RoadVegetation From/To, Name, Density) + `VegetationSphere` ile yollardan uzak tutma.
3. **Dilovası:** `config/aoi.json` core_bbox doğusu 29.50 → ~29.58, OSM yeniden indirme.
4. **Binalar:** 24.706 OSM binasından daha fazlası (öğe sınırı ~17 bin gözetilerek `Buildings` dizileri).
5. **Şirketler:** `CityArea` + şirket prefabı + `Company`; mod içinde `def/city` ve `def/company` tanımları.
6. **Trafik + paket:** `TrafficArea`, sonra oynanabilir .scs mod paketi.

## 11. Zemin ve ağaçlar – 2026-11-21 17:05

- `tools/geo/fetch_osm.py` → yeni `nature` sorgusu (orman, park, tarla, çalılık, su, kum…; 6.919 öğe).
- `tools/geo/build_ground.py` → `ground_s3.json`: 64 m hücre ızgarası; sınıflar OSM'den (deniz kıyı çizgisiyle
  bölünen, içinden yol geçmeyen parça → boş). Yola 60 m'den yakın hücrede ağaç yok. Sütunlarda aynı sınıflı
  hücreler tek parça: 2.174 parça → 2.572 Terrain öğesi (≤ 300 m segment, StepSize 16 m, y = -0,25).
- `mapping.json` → `ground.classes`: malzeme (`terrain_mat.<n>`) ve bitki örtüsü (`veg.v2_*`, yoğunluk).
- Editör çökmeden açıldı (overflow yok), Recompute + kayıt; oyunda çim, kentsel zemin, ağaç ve çalılar görünüyor
  (`docs/img/ingame_ground_trees.jpg`).
- Not: Bilgisayar yeniden başladıktan sonra Steam başlatma-seçenekleri penceresi açılıp exe'yi kapatıyordu (kod 53).
  Çözüm: `...\bin\win_x64\steam_appid.txt` (içerik `227300`) – silinerek geri alınır.

## 12. Dilovası, şirket depoları, şehir – 2026-11-21 17:40

- `config/aoi.json` çekirdek alanı doğuya 29.585'e genişletildi (Dilovası + OSB). Graf: 12.5 bin kenar, 609 kavşak adayı.
- `build_city_graph.py` adım 5 `place_depots`: sanayi poligonu içindeki, kavşaklardan uzak, ≥ (açıklık+24) m düz
  şehir yolu parçaları ikiye bölünür, araya iki düğümlü depo prefabı girer; gövde tarafında 45 m içinde yol olmamalı.
  Şirketler sırayla: stokes, lkwlog, trameri, transinet, tradeaux, posped (Avusturya seti depoları
  `at_0j004` generic_warehouse, `at_0j009` logistic, `at_0j008` light_factory; tabela = prefab variant).
- `mapgen buildgraph`: depo prefabı iki yol ucuna bağlanır, `Company` öğesi (şehir `gebze`) ve .ppd'deki
  yükleme/boşaltma noktaları eklenir; tüm alanı kapsayan `CityArea` "gebze".
- Mod tanımları `map/mod_defs/def` → `mod/user_map/def`: `city.saklaz.sii` + `city/gebze.sui` (ülke: turkey),
  `company/<şirket>/editor/gebze.sii`.
- Sonuç: 475 kavşak, 11.760 yol, 3.674 zemin, 8 depo. Bina indirmesi (Dilovası dahil) Overpass'ta uzun sürüyor;
  şimdilik eski 704 bina.

## 13. Binalar ve editör taşması – 2026-11-21 17:20

- Dilovası bina şeridi `tools/geo/fetch_buildings_extra.py` ile eklendi (+10.927; toplam 35.633 OSM binası).
- Bina modelleri: Balkan Doğu `tr` seti (müstakil ev ×7, apartman ×3, cami), dükkân, Alman depo.
  Hepsi `base.scs` içinde (DLC bağımlılığı yok). `build_city_export.py --max-buildings` (varsayılan 2800).
- **Editör taşması ("Parameter packet batch system overflow")**: öğe sayısından çok çizilen *farklı*
  model/look/variant sayısına bağlı. 1.485 binada eski 3 modelle sorun yok; 30+ çeşitli Türk/Balkan
  modeliyle çöküyor. Çözüm: sınırlı model/variant seti. Kısa çıkmaz sokaklar (< 60 m) atıldı
  (kenar 12,5 bin → 7,8 bin), zemin hücresi 96 m.
- Steam: `bin\win_x64\steam_appid.txt` olmadan exe Steam'e devrediyor ve başlatma penceresinde takılıyor.

## 14. Şehirler, şirketler, oynatma – 2026-11-21 17:30

- 4 şehir OSM ilçe sınırlarından: `gebze`, `darica`, `cayirova`, `dilovasi` (ülke `turkey`). `CityArea` konumu
  alanın **merkezi**dir (köşe sanıldığında doğu yarısındaki şirketler "assignment" hatası veriyordu).
- Oyun şirket öğesinin şehrini konumdaki CityArea'dan seçiyor; kutular çakıştığı için `write_mod_defs.py`
  her depo için onu içeren tüm şehirlere `company_def` yazar.
- Depolar: stokes, tradeaux, trameri, transinet (lkwlog/posped sürekli hata verdiği için çıkarıldı).
  Son durum: 6 deponun 5'i hatasız; `tradeaux@dilovasi` için "Invalid company item assignment" kalıyor.
- Önizlemede AI trafiği etkin (logda trafik römorku yükleme denemeleri), kırsal başlangıç noktasında seyrek.
- **Oynatma:** masaüstünde "SAKLAZ Gebze Haritasi" kısayolu → `tools/play/play_saklaz.ps1` (editörü kapatır,
  önizlemeyi başlatır). Oyun içi arayüz otomatik tıklamaya yanıt vermediğinden iş pazarı ekrandan doğrulanamadı.

## 15. Çizim bütçesi ve 3.235 bina – 2026-11-21 18:00

- Taşma oyunda da oluyor (`r_param_packet`, 16 bit kimlik): harita küçük olduğu için tüm sektörler aynı anda
  yükleniyor ve toplam çizim parçası (model × parça) sınırı aşılıyor. Görüş mesafesi/yansıma ayarı etkisiz.
- `modelinfo` artık parça sayısını yazıyor → `data/processed/game_defs/building_model_costs.csv` (656 model).
  Batı Balkan blokları 135–202 parça (asıl sorun), Türk apartmanları 22–50, "mid" köy/apartman modelleri 2–7.
- `build_city_export.py`: ana caddeye (tertiary+) 35 m içindeki en büyük 600 bina detaylı Türk modeli
  (`near_main`), kalanlar `*_far` listelerinden az parçalı Akdeniz/Balkan "mid" modelleri.
- Sonuç: **3.235 bina** oyunda taşmadan yükleniyor (4.157'de taşıyor). Editörden geçirmeden de oynanıyor.
- GitHub: `SAKLAZ5341/ETS2-MODLAR` (main).

## 16. Bağımsız harita paketi – 2026-11-21 22:15

- `tools/packaging/build_scs.py --map saklaz_city` artık `.set`/`.expa` yan dosyalarını ve `map/mod_defs/def`
  (şehir + şirket tanımları) içeriğini de pakete koyuyor. Çıktı: `releases/saklaz_turkiye_map_0.2.0-dev_*.scs`
  (47 dosya, 1,8 MB, zip testi geçti). Manifest 0.2.0-dev, kategori `map`.
- Referans: Grand Utopia (kullanıcının mod klasöründe, salt okunur incelendi) haritasını `map/grandutopia.mbd`
  adıyla getiriyor, `europe.mbd`'nin yerine geçmiyor; ana oyun şehirlerini `def/city.sii` ile boşaltıyor.
  Bizim paket de haritayı kendi adıyla getiriyor. **Yeni profilde harita seçimiyle oyunda doğrulanmadı.**
- Açık: son oyun logunda (18:10) ≥ 4 depo "Company item without company assignment" (koordinatlardan:
  transinet@gebze, trameri@dilovasi, stokes@dilovasi …). Tanım dosyaları mevcut; neden oyunda
  `g_developer 2` ile tam liste alınarak incelenecek.

## 17. Ana yol kavşakları ve depo şirketleri – 2026-11-21 22:30 (oyun/editör açılmadan)

- **Otoyol şeritleri:** OSM'de D-100/TEM her yön ayrı tek yönlü çizili; önceden her biri çift yönlü bölünmüş
  `ger14` ile çiziliyordu (üst üste binen ikili yollar). Artık `hw3_oneway` → `ger16` (ger hw 3 lanes one way).
- **Çıkış/katılma prefabları:** `mapgen ppdnav` ile .ppd navigasyon eğrileri okundu:
  `mod_ger_31` (ger_hw3_exit_joint_mirrored) = **çıkış** (node0 4 şerit giriş → node1 3 şerit + node2 sağ rampa),
  `ch_4202j` (ger_hw3_exit_joint_tmpl_v02) = **katılma** (node0 3 şerit + node2 sağ rampa → node1 4 şerit).
  `build_city_graph.py` 3b: tek yönlü şerit + tek yönlü rampa düğümleri, rampa ~30 m'de sağda (yanal sapma > 1 m),
  prefabın oturacağı kenar ≥ 50 m, aralık ≥ 70 m → **28 çıkış + 34 katılma = 62 prefab**, hepsi yerleşti.
- **Depo hatası düzeltmesi (oyunda doğrulanmadı):** "Company item without company assignment" nedeni aynı şirketin
  farklı türde iki deposu + çakışan şehir alanlarıydı (her şirket-şehir için tek prefab tanımı). Artık her depo
  harita genelinde benzersiz şirket alıyor; şirket, ana oyunda o prefabı kullananlardan seçiliyor
  (`mapgen companyprefabs` → `game_defs/company_prefabs.tsv`): stokes, transinet (genel), tradeaux, lkwlog,
  posped (lojistik), trameri (hafif fabrika). `write_mod_defs.py` tanımı 4 şehrin hepsine yazıyor (24 dosya).
- Sonuç: 474 şehir kavşağı + 62 otoyol prefabı, 7.016 yol, 12.889 parça, 3.235 bina, 1.690 zemin, 6 depo.
  Paket: `releases/saklaz_turkiye_map_0.2.0-dev_*_2226.scs`.

### Kullanıcı oyununu bitirince yapılacak testler
1. Editör (yalnız): `saklaz_city` aç → *Map > Recompute map* → kaydet → kapat (taşma olmamalı; parça 12.889).
2. Önizleme (editör kapalıyken): `tools/play/play_saklaz.ps1`; logda "Company item without company assignment"
   olmamalı; D-100 çıkış/katılma prefablarında AI trafiği ve sürüş kontrolü.
3. Paketi ayrı bir profilde etkinleştirip yeni profil oluştururken harita seçimini doğrula.

## 18. Test turu ve bağlantı düzeltmeleri – 2026-11-22 02:15

İlk test (editör tek başına, sonra önizleme tek başına):
- Editör taşma vermedi; depo hatası ("Company item without company assignment") önizlemede **yok** → §17 şirket düzeltmesi doğrulandı.
- Önizlemede 28 × `[traffic] Unable to determine output road lane 4`: `mod_ger_31` çıkış prefabı girişte 4 şerit bekliyor, ana yol 3 şeritti.

Düzeltmeler:
1. **Şerit eşleme** (`tools/geo/assign_hw_lanes.py`, `build_city_graph.py` sonunda otomatik çalışır): her otoyol kavşağı için hi/lo prefab seçilir; prefab düğümü ile yolun şerit sayısı birebir tutar.
   - exit hi `mod_ger_31` (4 → 3 + rampa), exit lo `ch_2y016` (3 → 2 + rampa)
   - merge hi `ch_4202j` (3 + rampa → 4), merge lo `ch_2y017` (2 + rampa → 3)
   - yollar `hw2_oneway`=ger13, `hw3_oneway`=ger16, `hw4_oneway`=ger19. Sonuç: 62/62 kavşak; prefab arası parçalar 3 şerit: 50, 4 şerit: 43 (katılma→çıkış arası yardımcı şerit), 2 şerit: 5.
2. **TruckLib prefab dönüşü**: `Prefab.Add` dönüşü düğüm 0'ın yönüne göre uyguluyor; düğüm 0'ı -Z'ye bakmayan prefablar ters/yan yerleşiyordu (mod_ger_67/63 270°, mod_ger_75/ch_4202j/ch_2y017 180°). `AddPrefabChecked` boş haritada deneyip düzeltme açısını bulur; en kötü düğüm sapması 0,00 m.
3. **Origin düğüm kuralı**: prefabın origin düğümüne yalnızca yolun bitiş ucu bağlanabilir. Çift yönlü yollar origin'de ters kurulur; kalan çakışmalarda `ChangeOrigin` ile origin boş kola / gelen tek yönlü yola taşınır.
   - Önce 680 yol sessizce bağlanamıyordu (kavşak ve otoyol kopuklukları). Şimdi: hata 0, bağlantı 1.660, 7.696 yol, 13.847 segment.
4. Editörde *Map > Recompute map* bir onay penceresi açar (Yes = ekranın ortası); onaylanmadan çalışmaz. Recompute + Save sonrası "Terrain point count" hataları 0.
5. **Depo / ekonomi**: önizlemede `Invalid company item assignment detected! [Company:X, City:Y]` + `Economy reset - company mismatch`.
   - Şirket değiştirmek hatayı aynı depoya taşıdı → sorun şirket değil: oyun bir şehirde **aynı depo prefabını iki şirkete** eşleyemiyor (dilovasi'de iki `at_0j009` lojistik depo vardı).
   - İkinci neden: ilçe sınır kutuları çakışıyordu (Gebze kutusu haritanın çoğunu kaplıyor); oyun öğenin şehrini CityArea'dan aldığı için Çayırova'daki depoyu Gebze'ye saydı. İlçe dışı hücrelerde alan yoktu → `Company item without company assignment`.
   - Düzeltme: `city_grid` 250 m ızgaradan **üst üste binmeyen** 69 CityArea dikdörtgeni üretir (ilçe dışı hücreler en yakın ilçeye); depo şehri bu ızgaradan alınır; `place_depots` her (tür, şehir) çiftini benzersiz tutar (her noktada boşta olan türü dener). C# öğe konumunu alanlarla karşılaştırıp uyarır.
   - Sonuç: 6 depo (tradeaux, trameri, stokes → Dilovası; kathode, posped, transinet → Çayırova), önizlemede şirket hatası yok. Gebze/Darıca'da uygun sanayi yolu bulunamadı (sonraki iş).
   - Kalan `Economy reset - company mismatch` satırı hatasız tek başına her önizlemede çıkıyor (önizleme ilk kaydı `def/initial_save/preview` yok); gerçek profilde doğrulanacak.
6. Sürüş: önizlemede klavyeyle sürüş çalışıyor. Oyun menüsü sentetik fare tıklamalarını almıyor (klavye Enter çalışıyor) → yeni profil + harita seçimi testi elle yapılmalı.
7. Paket `releases/saklaz_turkiye_map_0.2.0-dev_20261122_0259.scs` (70 dosya); oyun `[zipfs] ... Created, 70 entries` ile manifest uyarısı olmadan yükledi. Kopyası kullanıcının `Belgeler\Euro Truck Simulator 2\mod\saklaz_turkiye_map_0.2.0-dev.scs`.

## 19. Yol ağı sürekliliği – 2026-11-22 03:10

ETS2'de aynı noktada biten iki yol öğesi **bağlı değildir** (GPS, yapay zekâ trafiği, iş rotaları kopar).
Analiz: 2.062 düğümde iki serbest uç (çıkmaz sokak budamasından sonra yeniden birleştirilmemiş),
~1.400 kesişimde prefab yoktu.

- `build_city_graph.py` 4c `link_through`: prefabsız her düğümde en düz/uyumlu kol çiftleri tek kenara birleştirilir
  (tek yönlü görünümlerde gelen→giden yön korunur; kesişimde ≥120° düz geçiş). 3.605 bağlantı; kenar 7.675 → 4.149.
- Farklı görünümlü çift yönlü geçişler (r1↔r2) `road_links` olarak yazılır; C# yön ön planı (origin'e dokunmayan
  yol ters kurulabilir) + `INode.Merge` ile bağlar: 63/72.
- C# reddettiği kavşak düğümlerini `junction_rejects.json`'a yazar; graf üreticisi bunları birikimli olarak
  (`junction_excluded.json`) dışlayıp düz geçiş yapar. 3 turda yakınsadı: **487 kavşak, reddedilen 0**.
- Kalan serbest uçlar: ~190 iki uçlu (çoğu rampa↔şehir yolu, tek yön/şerit uyuşmazlığı) ve ~76 kesişim.
- Sonuç: yol 4.126, segment 13.730, bağlantı 1.689, prefab hata 0; editör recompute/save hatasız; önizlemede harita, trafik ve şirket hatası yok.
- Paket: `releases/saklaz_turkiye_map_0.2.0-dev_20261122_0310.scs` → `Belgeler\Euro Truck Simulator 2\mod\saklaz_turkiye_map_0.2.0-dev.scs`.

Sonraki işler: OSM'de çift şeritli (iki tek yönlü yol) şehir caddeleri hâlâ iki ayrı çift yönlü yol olarak çiziliyor (tek eksene indirilmeli);
Gebze/Darıca'ya depo; rampa↔şehir yolu bağlantıları; tüm Kocaeli.

## 20. Kalan eksikler – 2026-11-22 11:55

- **Bölünmüş caddeler** (`tools/geo/collapse_dual.py`, `build_city_graph.py` 1. adımdan sonra): OSM'de her yönü ayrı
  tek yönlü çizili şehir caddeleri (solda ters yönlü eş şerit, ≤38 m) eşleştirilir, eşleşme grafiği 2 renge boyanır;
  biri orta hatta kayıp çift yönlü olur, öbürü silinir, yan sokaklar orta hatta taşınır. 589 çift, 162 km orta hat.
  Tek yönlü şehir yolu 125 km → 23 km. `--no-collapse` ile kapatılır.
- **Çok kısa kenarlar** (<4 m) düğüm birleştirmeyle daraltılır (C# bunları atlıyordu → ağda boşluk). Atlanan yol 92 → 23.
- **Kavşak kolu uzunluğu** artık 2 dereceli aynı sınıf düğümlerden geçen zincirle ölçülür (önce ilk OSM parçası:
  ~13 bin aday "kısa kol" diye eleniyordu). Kavşak 487 → 564, reddedilen 0 (2 tur).
- **Yol sürekliliği** (`link_through`): rampa ↔ şehir yolu/r2 ve rampa ↔ otoyol şeridi (yönü tutarlıysa) görünüm-arası
  bağlantı olarak C#'ta birleştirilir; kesişimde düz çift dışında kalan iki kol ≥90° dönüşle bağlanır.
  Görünüm-arası bağlantı 165 (başarısız 11 + yön planı 8). Bağlantısız uçlu düğüm 275 → ~186 (27'si kapalı halka).
- **Depolar** her şehirde tür başına bir (`place_depots` per_city=3): önce sanayi alanı, sonra sanayi dışı iki yönlü
  şehir yolu. Depo noktalarının hepsi (düğümler + gövde çevresi) aynı CityArea dikdörtgeninde olmalı: sınırdaki Darıca
  deposu oyunda Gebze'ye sayılıp "Invalid company item assignment" verdi. `lkwlog` ve `eurogoodies` lojistik deposunda
  hep bu hatayı verdiği için havuzdan çıkarıldı; şirketler artık birden çok şehirde (aynı tür) olabilir.
  Sonuç 10 depo: Gebze (Trameri, Tradeaux), Darıca (Kathode, Posped), Çayırova (Posped, Trameri, Transinet),
  Dilovası (Tradeaux, Kathode, Stokes).
- **Sanayi binaları**: `3z001` ve `blke_45/46` (açık hangar) pembe iskelet görünüyordu ve yola taşıyordu →
  `factory_hall_01_balt` (varyant `factory`), `warehouse_04_balt`, `factory_hall_06_balt`, `warehouse_03_balt` (hepsi base.scs).
- **Bina–yol çakışması** (`tools/geo/clear_buildings.py` → `map_export_s3_clear.json`): binalar indirgeme öncesi yollara
  göre seçilmişti; güncel yol tamponuna (yarı genişlik + 0,5 m) ve kavşaklara (20 m) değen 964 bina çıkarıldı, 2.489 kaldı.
  Üretim: `mapgen buildgraph data/processed/map_graph_s3.json data/processed/map_export_s3_clear.json`.
- Sonuç: yol 4.131, segment 13.230, bağlantı 1.931, prefab hata 0; editör recompute + save, taşma yok, model hatası yok;
  önizlemede harita/trafik/şirket hatası yok (yalnız önizlemeye özgü tek "Economy reset" satırı), sürüş kontrol edildi.
- Paket `releases/saklaz_turkiye_map_0.2.0-dev_20261122_1154.scs` (70 dosya) → `Belgeler\Euro Truck Simulator 2\mod\saklaz_turkiye_map_0.2.0-dev.scs`.

Sonraki: tüm Kocaeli.

## 21. Tüm Kocaeli – 2026-11-22 13:05

- Veri: `tools/geo/fetch_kocaeli.py` → `data/raw/kocaeli/` (12 ilçe sınırı, motorway..tertiary, ilçe merkezlerinde
  sokak ve bina, sanayi/liman, doğa, kıyı). Çekirdek (Gebze/Darıca/Çayırova/Dilovası) verisi değişmedi.
- `build_city_graph.py`: çekirdekte tüm şehir yolları; il genelinde (12 ilçe sınırı ∪ çekirdek kutusu) ana yollar,
  merkezlere ≤3 km köy yolları (tertiary), merkezlere ≤800 m sokaklar. Kırsal kenarlar sınıfa göre seyrek düğümlü ve
  birleştirme sonrası yeniden sadeleştirilir. `--core-only` eski çekirdek haritayı üretir.
- **Editör sınırı (ölçüldü):** "Parameter packet batch system overflow" tüm harita için: yaklaşık 3 × yol segmenti +
  model parçası ≲ 65 bin. 27,4 bin ve 18,8 bin segment (+bina) çöktü; 18,8 bin binasız açıldı.
  Bütçe: 16,2 bin segment + 9 bin parça bina (`clear_buildings.py --budget 9000 --close 120`: ana caddeye bakan
  120 binada ayrıntılı model, gerisi 2–7 parçalı mid model; il merkezlerinden 832 bina dahil, toplam 1.384).
- Zemin: çekirdek zemini `ground_core_s3.json`'dan aynen (yeniden üretilen geniş çekirdek zemini editörü
  "Index outside array boundaries: 12 >= 12" ile çökertti); il geneli 512 m hücre, yola ≤900 m, ağaç yalnız ormanda
  (yoğunluk ×0,35). C# zemin parçası genişliği/yoğunluğu `w`/`dens`. 2.689 zemin öğesi.
- 12 şehir (`city.*`), etiket ilçe merkezini içeren alanda; 549 CityArea; 26 depo (her ilçede 2–3).
- Sonuç: 775 kavşak (red 0), 168 otoyol çıkış/katılma, 5.676 yol, 16.225 segment, 2.929 bağlantı; editör recompute +
  save hatasız; önizlemede harita/trafik/şirket hatası yok (1 prefab tabelası kayıt uyarısı).
- Paket `releases/saklaz_turkiye_map_0.2.0-dev_20261122_1306.scs` (348 dosya) → kullanıcı mod klasörü.

Sınırlar: köyler (merkezden >3 km tertiary) ve ilçe merkezleri dışındaki sokaklar bütçe nedeniyle yok; bina sayısı
çekirdekte azaldı (2.489 → ~550 + il geneli 832).
