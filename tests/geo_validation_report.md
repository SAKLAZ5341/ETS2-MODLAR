# Coğrafi veri doğrulama raporu – 2026-11-21 03:55

| Test | Sonuç | Ayrıntı |
|---|---|---|
| T01 Ham OSM dosyaları ve meta kayıtları mevcut | GEÇTİ | 6/6 dosya + meta |
| T02 Projeksiyon mesafe testi: UTM mesafesi jeodezik mesafeye %0,2 içinde | GEÇTİ | jeodezik 6262.9 m, UTM 6263.6 m, hata %0.011 |
| T03 Oyun koordinatı ölçek testi (1:19): Gebze–Darıca oyun mesafesi = gerçek/19 | GEÇTİ | oyun 329.66 m × 19 = 6263.6 m, gerçek 6262.9 m |
| T04 Eksen yönü: Darıca (güneyde) +Z, Çayırova (kuzeyde) −Z | GEÇTİ | Darıca z=258.18, Çayırova z=-186.82 |
| T05 Ana yol ağı bağlılığı: en büyük bileşen ≥ %98 | GEÇTİ | en büyük bileşen %99.32, bileşen sayısı 11 |
| T06 D-100, O-4 (TEM), O-7, O-5 OSM ref etiketiyle mevcut | GEÇTİ | D100: 144 way / 90.07 km, O4: 106 way / 106.42 km, O7: 97 way / 121.13 km, O5: 12 way / 11.01 km |
| T07 O-4 (TEM) bbox içinde kesintisiz (2 parça = iki yön) | GEÇTİ | parça: 2 |
| T08 D-100 bbox içinde parça sayısı (bilgi: >2 ise kopukluk/bbox kesişi) | **KALDI** | parça: 5 (bkz. rapor – bilinen sorun) |
| T09 Prototip D-100 iki yön de OSM tek-yön kurallarıyla kesintisiz | GEÇTİ | P1_D100_dogu: tamam 6354.7 m; P1_D100_bati: tamam 6240.9 m |
| T10 Prototip bağlantıları (TEM, Darıca, Gebze, Çayırova) gerçek yolla bulundu | GEÇTİ | P2_D100_TEM: 3985.3 m; P3_Darica_D100: 5031.3 m; P4_Gebze_D100: 1114.1 m; P5_Cayirova_TEM: 5985.6 m |
| T11 Editör düğümleri arası boşluk ≤ düğüm aralığı (20 oyun m) + tolerans | GEÇTİ | en büyük aralık 19.56 oyun m, düğüm 177 |
| T12 Editör düğümleri gerçek OSM geometrisinden sapma ≤ 5 m (gerçek) | GEÇTİ | P1 düğümlerinde en büyük sapma 2.88 m |
| T13 ODbL atıfı türetilmiş dosyalarda mevcut | GEÇTİ | 8/8 dosyada atıf |
| T14 Map Editor: D:\SAKLAZ_DEV'de kayıtlı saklaz.mbd var mı | **KALDI** | YOK – editörde harita henüz oluşturulmadı (elle adım, bkz. EDITOR_GUIDE.md) |

Toplam: 12/14 geçti.