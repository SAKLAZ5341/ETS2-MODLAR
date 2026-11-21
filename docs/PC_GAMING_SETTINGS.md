# Oyun Ayarları Önerisi – Warzone (FPS) + ETS2 (Simülasyon)

> Bu dosya SAKLAZ harita projesinin parçası değildir; kullanıcının ayrı isteğidir.
> Tarama **salt okunur** yapıldı (2026-11-21). Sistem ve NVIDIA ayarlarını **Claude değiştirmedi**;
> aşağıdaki adımları siz uygulayın. Her değişiklik geri alınabilir.

## 1. Tarama sonucu

| Bileşen | Bulunan | Değerlendirme |
|---|---|---|
| GPU | RTX 4060 Ti 8 GB, sürücü **621.14** (27.10.2026), PCIe 4.0 x8 | Kart zaten x8 tasarımlı, normal. Sürücü güncel sayılır |
| iGPU | AMD Radeon (Ryzen 7900X), 2. monitöre bağlı | Oyunlar NVIDIA'da çalışıyor (ETS2 logu doğruladı) |
| CPU | Ryzen 9 7900X (12C/24T) | Çok iyi |
| RAM | 2×16 GB G.Skill DDR5, **6400 MT/s'te çalışıyor** | EXPO açık, ideal |
| Monitör 1 | ASUS VG27AQ1A, 2560×1440 **170 Hz** (NVIDIA) | Ana oyun ekranı |
| Monitör 2 | GB-2411FF, 1920×1080 100 Hz (AMD iGPU) | — |
| Güç planı | **Nihai Performans** | Zaten en iyisi |
| Oyun Modu | Açık | Doğru |
| Game DVR / arka plan kaydı | Kapalı | Doğru (FPS için iyi) |
| HAGS (donanım hızlandırmalı GPU zamanlama) | Açık | Doğru (DLSS Frame Generation için gerekli) |
| Pencereli oyun iyileştirmeleri / VRR | Açık | Doğru |
| VBS | Çalışıyor, Bellek Bütünlüğü (HVCI) kapalı | Güvenlik ayarı – değiştirmeyin |
| SSD | 2× NVMe (ADATA 500 GB, MSI 1 TB) | İyi |
| Başlangıç uygulamaları | 22 adet (Docker Desktop, Overwolf, Adobe Sync, OneDrive, Edge, Logitech x2…) | **İyileştirilebilir** |

Sonuç: Temel Windows ayarların zaten oyuna uygun. Kazanç asıl **NVIDIA profilleri**, **oyun içi ayarlar**
ve **arka plan uygulamaları**ndan gelecek.

## 2. NVIDIA (NVIDIA App / Denetim Masası)

**Genel (Global) ayarlar**

| Ayar | Değer |
|---|---|
| Güç yönetimi modu | Maksimum performansı tercih et (yalnızca oyun profillerinde; global'de "Normal" bırakılabilir) |
| Düşük Gecikme Modu | Kapalı (Reflex destekleyen oyunlarda Reflex kullanılır) |
| G-SYNC | Açık – tam ekran ve pencereli mod (VG27AQ1A G-SYNC uyumlu) |
| Dikey senkronizasyon | **Açık** (G-SYNC ile birlikte; oyun içinde V-Sync KAPALI) |
| Maks. kare hızı | **164 FPS** (170 Hz − ~6; G-SYNC aralığında kalır, tearing olmaz) |
| Doku filtreleme – kalite | Yüksek performans |
| Shader önbellek boyutu | 10 GB veya Sınırsız |

**Call of Duty / Warzone profili (rekabetçi FPS)**

- Oyun içinde: **NVIDIA Reflex: Açık + Boost**, V-Sync kapalı, DLSS **Kalite** veya **Dengeli**,
  Frame Generation **kapalı** (gecikme ekler), Ekran modu: Tam ekran (Exclusive).
- Doku çözünürlüğü: Normal/Yüksek (8 GB VRAM sınırı – "VRAM kullanımı %90" altında tutun).
- Gölgeler, yansımalar, hacimsel ışık: Düşük/Normal; Sekonder ve Ambient Occlusion: Kapalı.
- Hareket bulanıklığı, film grenı, alan derinliği: Kapalı. Görüş alanı (FOV): 100–110.
- Hedef: 1440p'de 140+ FPS, Reflex ile düşük sistem gecikmesi.

**Euro Truck Simulator 2 profili (simülasyon)**

- ETS2 tek çekirdeğe yük bindirir; FPS'i genelde CPU sınırlar. Öneri:
  - Ölçekleme (Scaling): %100 (1440p'de 200–300 aşırı ağırdır; keskinlik için en fazla %150).
  - Anti-aliasing: oyun içi MSAA yerine ölçekleme kullanılır; NVIDIA'da **DLDSR yok** (DX11).
  - Yansıma, ayna kalitesi ve ayna mesafesi: Orta – en çok FPS götüren ayarlardır.
  - Trafik yoğunluğu (`g_traffic`): varsayılan.
  - V-Sync: oyun içinde kapalı, NVIDIA V-Sync + G-SYNC + 164 FPS sınırı.
- Ana profilde **1.58 dönemi uyumsuz ve çakışan modlar** var (iki ProMods sürümü aynı anda, birden
  fazla harita modu). Takılma ve çökmelerin en büyük olası sebebi bunlar; mod yöneticisinde yalnızca
  ihtiyaç duyduğunuz, 1.62 uyumlu modları etkin bırakın.

## 3. Windows

1. **Başlangıç uygulamaları** (Görev Yöneticisi → Başlangıç uygulamaları): oyun öncesi gerekmeyenleri
   devre dışı bırakın: Docker Desktop (en ağırı – WSL sanal makinesi açar), Adobe Acrobat Synchronizer,
   Microsoft Edge otomatik başlatma, Logitech/Logi Download Assistant, Overwolf (kullanmıyorsanız),
   OneDrive (oyun sırasında senkron yapmasın diye en azından duraklatın).
2. **İkinci monitör (iGPU):** Warzone'da takılma olursa ikinci ekranda video/Discord yayını açık
   tutmamayı deneyin; çok monitörlü farklı yenileme hızları bazen kare süresini dalgalandırır.
3. **Fare:** Ayarlar → Bluetooth ve cihazlar → Fare → İşaretçi hassasiyetini artır (ivme) **kapalı**.
4. **Yenileme hızı:** Ayarlar → Ekran → Gelişmiş ekran → VG27AQ1A için **170 Hz** seçili olduğundan emin olun
   (tarama 170 Hz gösteriyor ✔).
5. **Değiştirmeyin:** VBS/çekirdek yalıtımı gibi güvenlik ayarları, sayfa dosyası, kayıt defteri "tweak" paketleri.

## 4. BIOS (isteğe bağlı, kendi sorumluluğunuzda)

- EXPO zaten açık (6400 MT/s) ✔.
- Resizable BAR: NVIDIA ve Ryzen 7000 destekler; BIOS'ta "Re-Size BAR Support" açık olmalı.
  NVIDIA App → Sistem bilgisi'nden "Yeniden boyutlandırılabilir BAR: Evet" kontrol edin.
