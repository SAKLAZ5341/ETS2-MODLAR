# Teknik İnceleme Raporu – 2026-11-21

Hazırlayan: Claude Code (teknik sorumlu) · Kapsam: yalnızca inceleme (Aşama A kapanışı)
Bu incelemede **hiçbir oyun dosyası, mod, profil veya harita değiştirilmedi; dosya silinmedi; push yapılmadı.**
Yazılan tek dosya bu rapordur.

---

## 1. Özet (TL;DR)

| Konu | Sonuç | Kanıt |
|---|---|---|
| ETS 2 kurulumu | **KURULU** – `C:\Program Files (x86)\Steam\steamapps\common\Euro Truck Simulator 2` | `libraryfolders.vdf` (227300 ana kütüphanede), editor.log mount satırları |
| Sürüm | **1.62.3.3s** (rev. 7173c707daa0) | `editor.log.txt`: `init ver.1.62.3.3s`, `Loaded pack set version 1.62.3.3` |
| DLC | 104 DLC paketi yüklü (Balkans E/W, Greece, Iberia, Baltic, Nordic, Italia, France, Iceland, Tırsan vb.) | editor.log `dlc_*.scs mounted` |
| Map Editor | **ÇALIŞIYOR.** Şu an açık ve yanıt veriyor (PID 15740, pencere: `Map editor [2558x1300]`) | `Get-Process` + D:\SAKLAZ_DEV editor.log |
| Siyah ekran | **Arıza değil – editör haritasız açılmış.** (Ayrıntı §3) | editor.log: hiç `.mbd` yüklenmedi, `mode: none`, `map_files: 0` |
| D:\SAKLAZ_DEV | Temiz geliştirme profili, **0 mod**, doğru yapılandırılmış | editor.log: `Active 0 mods`, `Home directory: 'D:/SAKLAZ_DEV/...'` |
| env_check.ps1 | **Hata var:** ETS 2'yi yanlışlıkla "bulunamadı" raporladı (§6) | ENV_REPORT §1 `Cannot find drive 'E'` |
| Proje klasörü | Git deposu **değil** (sürüm kontrolü yok) | klasörde `.git` yok |

---

## 2. Proje dosyaları ve klasör yapısı

```
Saklaz-Turkiye-Map/            (74 KB, git deposu DEĞİL)
├─ README.md                   proje özeti, aşama tablosu (A: devam ediyor)
├─ .gitignore                  ham veri, ENV_REPORT_*.md, .scs sürümleri hariç
├─ ENV_REPORT_20261121_025310.md   env_check çıktısı (KİŞİSEL BİLGİ İÇERİR – paylaşmayın)
├─ docs/
│  ├─ PROJECT_BRIEF.md         ana talimat
│  ├─ STAGE_A_REPORT.md        Aşama A taslağı + Aşama B görev listesi (B1–B10)
│  ├─ GEO_DATA_SOURCES.md      boş şablon (OSM ODbL, Copernicus DEM adayları)
│  └─ CHANGELOG.md
├─ tools/validation/env_check.ps1  salt okunur ortam betiği
└─ data/raw, data/processed    boş (.gitkeep)
```

Brief'te istenen ama henüz olmayan: `PROJECT_PLAN.md`, `ROAD_NETWORK.md`, `CITY_DATABASE.md`,
`TESTING.md`, `TECHNICAL_ARCHITECTURE.md`, `data/roads|cities|terrain`, `map/`, `assets/`,
`tools/geo`, `tools/packaging`, `tests/`, `releases/`. Bu normal: Aşama B/C'de eklenecek.

`STAGE_A_REPORT.md` hâlâ "bulut ortamı, PC erişimi yok" diyor; bu rapordaki bulgularla güncellenmesi gerekiyor (onayınızla).

---

## 3. Map Editor siyah ekran sorunu – analiz

İki ayrı editör oturumu bulundu:

### Oturum A – Ana profil (02:57, `-edit europe -noworkshop`)
- Profil: `Documents\Euro Truck Simulator 2`
- **65 yerel mod aktif** (`Active 65 mods (local: 65, workshop: 0)`).
  `-noworkshop` yalnızca Workshop modlarını kapatır; `mod\` klasöründeki yerel modlar yine yüklenir.
- Aktif modlar arasında: **iki ayrı ProMods sürümü aynı anda (v2.81 + v2.84)**, Heart of Africa,
  OBMap, Grand Utopia, Sibir Map, Peru Death Road, Rota Factor, RTC – yani birbiriyle çakışan
  çok sayıda harita modu; ayrıca çoğu "Incompatible mod" (1.57/1.58 dönemi).
- `europe` haritası bu modlarla açılmaya çalışılmış. Log **1,3 MB sınırına ulaşıp kesilmiş**:
  ~7.400 `Unable to find`, ~2.000 `Invalid item!`, 426 `City ...`, 205 `Two trailer points` hatası.
- **Sonuç:** Bu oturumdaki siyah/donuk ekran büyük olasılıkla çakışan mod setiyle devasa
  `europe` haritasının yüklenmesi (çok uzun süren veya takılan yükleme). Log kesildiği için sonu görülemiyor.

### Oturum B – Temiz profil (03:16, `-homedir D:\SAKLAZ_DEV -noworkshop -edit`)
- 0 mod, tüm DLC'ler mount edildi, NVIDIA RTX 4060 Ti seçildi (dx11, SM5X), editör ~35 sn'de açıldı:
  `Opening content browser … Load finished in 69ms`.
- Hatalar yalnızca ilk açılışa özgü ve zararsız: `editor/storages/default.sii`, `editor/defaults.ini`
  (ilk açılışta henüz oluşmamış), `/def/background_map_legends.sii`, `/home/config.cfg`.
- `-edit` parametresine harita adı verilmemiş → **hiçbir harita yüklenmedi**. Editör ayarlarında
  `mode: none`, `map_files: 0`; `mod\user_map` boş.
- Süreç şu anda çalışıyor ve **yanıt veriyor** (`Responding: True`, başlık `Map editor`).
- **Sonuç:** Bu oturumdaki siyah görünüm **beklenen davranış**: harita açılmadan editör görüş alanı boş/siyahtır.
  Editörde *File → New map* (veya *Open map*) ile harita oluşturulduğunda/açıldığında görüntü gelir.
  (Bunu ben yapmadım – harita oluşturma Aşama C işidir ve onayınızı gerektirir.)

### Diğer olasılıklar (düşük olasılık, kayıt için)
- Çift GPU (RTX 4060 Ti + AMD iGPU) ve çift monitör: log doğru adaptörün (NVIDIA) seçildiğini gösteriyor.
- Dev profilde `r_fullscreen "1"`: editör yine de pencereli açılmış (resize olayları var); sorun değil.

### Önerilen doğrulama (kullanıcı yapar, değişiklik içermez)
1. Açık editörde ekran görüntüsü alın veya bana ekranı gözlemleme izni verin; menülerin görünüp görünmediğini kontrol edelim.
2. Map Editor'ü **daima** `-homedir D:\SAKLAZ_DEV -noworkshop -edit` ile açın; ana profilde editör açmayın.
3. Siyah ekran harita açıldıktan sonra da sürerse yeni `editor.log.txt` ile tekrar incelenir.

---

## 4. D:\SAKLAZ_DEV geliştirme profili

```
D:\SAKLAZ_DEV\Euro Truck Simulator 2\   (151 KB, 2026-11-21 03:16'da oluştu)
├─ config.cfg            varsayılanlar (g_developer 0, g_console 0)
├─ editor\editor_settings.sii, editor\contentbrowser\*
├─ editor.log.txt        Oturum B logu
├─ mod\user_map\         BOŞ (henüz harita yok)
├─ profiles\             boş (oyun profili yok – editör için gerekmez)
└─ cache, music, online, screenshot, net.log, *.sii
```

Değerlendirme: Ana profilden tamamen izole, modsuz, editör için **doğru kurulmuş**. Eksik/öneriler:
- Dev profilde `g_developer`/`g_console` 0. Editör için gerekmiyor; ancak oyun içi test (Aşama F) için
  bu profile ayrı bir oyun profili ve konsol gerekecek.
- Ana profildeki `config.cfg` zaten `g_developer 1`, `g_console 1`.

---

## 5. Eksik araçlar

| Araç | Durum | 0.1.0 için gerekli mi? |
|---|---|---|
| ETS 2 1.62.3.3 + Map Editor | Var, çalışıyor | Evet |
| Python 3.12.8 | Var: `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`. **Ama PATH'te önce Microsoft Store kısayolu geliyor**, `py` yok | Evet (Aşama B) |
| pyproj, shapely, geopandas, osmium, requests | **Yok** | Evet (Aşama B) – proje içi `.venv` önerilir |
| Git 2.56 + GitHub CLI 2.103 | Var | Evet – ama proje klasörü git deposu değil |
| QGIS | **Bulunamadı** | Önerilir (görsel doğrulama) |
| Blender | **Bulunamadı** | Hayır (0.1.0 yalnızca SCS assetleri kullanırsa) |
| SCS Blender Tools | **Bulunamadı** | Hayır (özel model aşamasında; resmi sürüm Blender 3.2–3.6 ister) |
| SCS Conversion Tools | **Bulunamadı** | Hayır (özel model/dönüştürme aşamasında) |

Hiçbir araç kurulmadı; kurulum kararı sizde.

---

## 6. env_check.ps1 hatası (düzeltilmedi, yalnızca tespit)

`libraryfolders.vdf` içinde artık var olmayan `E:\SteamLibrary` ve `F:\SteamLibrary` kayıtlı.
Betik satır 173'te `Join-Path "E:\SteamLibrary" 'steamapps'` çağırıyor; PowerShell 5.1'de `Join-Path`
var olmayan sürücüde `DriveNotFoundException` fırlatır. Bütün Steam bölümü iptal olur,
kütüphane listesi boş kalır ve ETS 2 (aslında C:'de kurulu) **"BULUNAMADI"** raporlanır;
bu yüzden sürüm (exe), DLC listesi ve disk sürücüsü bölümleri de boş çıktı.
Düzeltme önerisi: yolu `[System.IO.Path]::Combine()` veya string birleştirme ile kurmak, sonra `Test-Path` ile kontrol etmek.

---

## 7. Gebze – Darıca – Çayırova yol ağı ve geliştirme planı

> **Uyarı:** Aşağıdaki güzergâh ve yer bilgileri genel bilgiye dayalı **ön taslaktır, koordinat içermez
> ve doğrulanmamıştır.** Gerçek geometri Aşama B'de OpenStreetMap'ten çıkarılıp doğrulanacaktır
> (brief madde 7: gerçek olmayan koordinatları gerçekmiş gibi gösterme).

### 7.1 Çalışma alanı (AOI) – taslak
Batıda Tuzla/Çayırova sınırı, doğuda Dilovası, güneyde Darıca–Gebze sahili (İzmit Körfezi),
kuzeyde TEM ve Gebze OSB/Kuzey Marmara bağlantısı. Kesin bbox: Aşama B1.

### 7.2 Hiyerarşik yol ağı (doğrulanacak)

| Seviye | Yol | Rol | Öncelik |
|---|---|---|---|
| Otoyol | **O-4 / TEM (E80)** | İstanbul–Ankara ana ekseni, AOI'nin kuzeyi | 0.1.0 |
| Otoyol | **O-5 İstanbul–İzmir** | Gebze'den güneye, Dilovası üzerinden Osmangazi Köprüsü yönüne | 0.2+ (bağlantı kolu) |
| Otoyol | **O-7 Kuzey Marmara** | Kuzey bağlantısı | 0.3+ |
| Devlet yolu | **D-100 (E5)** | Çayırova–Gebze–Dilovası, kıyıya paralel ana arter | 0.1.0 |
| Ana bağlantı | Darıca ↔ D-100 bağlantıları | Darıca merkez erişimi | 0.1.0 |
| Ana bağlantı | Çayırova / Şekerpınar ↔ D-100 ↔ TEM | Lojistik koridoru | 0.1.0 |
| Ana bağlantı | Gebze merkez ↔ TEM ↔ Gebze OSB | Sanayi erişimi | 0.1.0 |
| Ana bağlantı | Gebze ↔ Dilovası (D-100 / TEM) | Doğu çıkışı | 0.1.0 (yalnızca giriş) |
| Şehir içi | Seçilmiş toplayıcı yollar | Depo/fabrika erişimi | 0.1.x |

Önemli kavşaklar (Aşama B5'te OSM `motorway_junction` ile ad/konum doğrulanacak):
TEM–Gebze bağlantısı, TEM–O-5 ayrımı, D-100–Darıca bağlantıları, D-100–Çayırova/Şekerpınar,
TEM–Çayırova/Şekerpınar, D-100/TEM–Dilovası.

Sanayi/lojistik hedefleri (OSM `landuse=industrial` + ad ile doğrulanacak):
Gebze OSB, Gebze Plastikçiler OSB, Şekerpınar/Çayırova lojistik alanları, Dilovası OSB bağlantısı.

### 7.3 Geliştirme planı (aşama sırasıyla)

| Aşama | İş | Çıktı | Onay kapısı |
|---|---|---|---|
| **B** Coğrafi veri | B1–B10 (STAGE_A_REPORT.md) – AOI, OSM indirme, yol/kavşak/sanayi katmanları, EPSG:32635 dönüşüm, yükseklik profili, doğrulama | `data/*`, `tools/geo/*`, doğrulama raporu | **Sizin onayınız** |
| **C** Altyapı | Ölçek kararı, yeni bağımsız harita modülü (`mod/user_map` altında `.mbd`), modül/def yapısının resmi dokümandan doğrulanması, başlangıç noktası | Boş ama açılıp kaydedilebilen harita | Onay |
| **D** İlk yollar | Önce D-100 Çayırova→Gebze (~en basit eksen), sonra TEM parçası, Darıca bağlantısı, Çayırova bağlantısı | Editörde bağlı yol ağı | Onay |
| **E** Yerleşim | Gebze merkez, bir depo/fabrika (Gebze OSB), tabelalar, arazi | İlk teslimat noktası | Onay |
| **F** Test/paket | Editör açılış/kaydetme, navigasyon, oyun içi yükleme, `.scs` | 0.1.0 test paketi | Onay |

Dikey dilim önerisi: 0.1.0'ı **yalnızca D-100 (Çayırova–Gebze) + bir TEM bağlantısı + bir depo** ile
sınırlamak; tüm AOI'yi tek seferde değil, oynanabilir küçük bir çekirdekle başlamak.

---

## 8. Teknik riskler

| # | Risk | Etki | Öneri |
|---|---|---|---|
| R1 | **Ana profil mod karmaşası** (65 mod, 2 ProMods sürümü, çakışan harita modları, 1.58 dönemi modlar) | Editör/oyun yükleme sorunları, yanlış teşhis | Editör işleri yalnızca D:\SAKLAZ_DEV'de. Ana profildeki modlara dokunulmadı. |
| R2 | Editörün yanlışlıkla ana profille açılması (Steam başlatma seçenekleri oyunla ortak) | Oturum A'daki tablo | Ayrı masaüstü kısayolu: `eurotrucks2.exe -homedir D:\SAKLAZ_DEV -noworkshop -edit` |
| R3 | **Oyun güncellemesi** (1.63) harita/editör formatını değiştirebilir | Kayıtlı sektörler bozulabilir | Her güncellemeden önce `D:\SAKLAZ_DEV` yedeği; gerekirse Steam beta dalında eski sürüm |
| R4 | **DLC bağımlılığı** – editörde 104 DLC yüklü; DLC assetleri kullanılırsa haritayı yalnızca o DLC sahipleri açabilir | Dağıtım sorunu | 0.1.0'da yalnızca base game assetleri; DLC kullanımı belgelenmeli |
| R5 | **Ölçek kararı** (ETS 2 ölçeği mi, gerçekçi mesafe mi) verilmedi | Tüm yol çizimi buna bağlı | Aşama C öncesi kesin karar + test (iki nokta mesafe testi) |
| R6 | Türkiye'ye özgü asset eksikliği (tabela, plaka, bina) | Görsel kalite | Önce SCS base/Balkan stili; özel asset için Blender + SCS Tools gerekecek |
| R7 | **Sürüm kontrolü yok** – proje klasörü git deposu değil; harita dosyaları da D:\SAKLAZ_DEV'de | Kayıp/geri alma imkânsızlığı | Onayınızla `git init` + harita klasörü için düzenli yedek planı |
| R8 | Python PATH'te Store kısayolu önce geliyor | Betikler yanlış yorumlayıcıyla çalışabilir | Tam yol veya proje `.venv` kullanımı |
| R9 | OSM ODbL lisansı | Atıf/paylaşım yükümlülüğü | GEO_DATA_SOURCES.md'de kaynak + atıf; README'ye atıf |
| R10 | Kişisel veri: ENV_REPORT dosyasında bilgisayar adı, Steam ID'ler, mod listesi | Gizlilik | `.gitignore` kapsamında; paylaşmadan önce temizleyin |
| R11 | env_check.ps1 Steam hatası (§6) | Yanlış "kurulu değil" raporu | Onayınızla düzeltilebilir |
| R12 | Map Editor DEM içe aktarmıyor | Arazi elle şekillenecek | Python ile referans yükseklik tablosu (B9) |

---

## 9. Bekleyen kararlar (sizin onayınız gerekli)

1. Aşama B'ye (OSM verisi indirme, Python paketleri için `.venv`) geçilsin mi?
2. `env_check.ps1` hatası düzeltilsin ve `STAGE_A_REPORT.md` bu bulgularla güncellensin mi?
3. Proje klasöründe `git init` yapılsın mı? (push yok)
4. Ölçek kararı: ETS 2 standart ölçeği mi, gerçekçi (daha büyük) ölçek mi?
5. Editör ekranını doğrulamam için ekran gözlemine izin verilsin mi (yalnızca ekran görüntüsü)?
