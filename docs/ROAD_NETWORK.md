# Yol Ağı – Gebze / Darıca / Çayırova (0.1.0)

Kaynak: OpenStreetMap, Overpass, OSM zaman damgası `2026-11-21T00:33:01Z`. ODbL 1.0, © OpenStreetMap katkıda bulunanlar.
Çalışma alanı: Gebze, Darıca, Çayırova, Dilovası ilçe sınırlarının kutusu + 0,01° tampon.

## Sınıflara göre uzunluk (gerçek km, tüm şeritler/yönler ayrı sayılır)

| OSM sınıfı | way | km |
|---|---|---|
| residential | 10291 | 1776.07 |
| service | 6838 | 1100.64 |
| tertiary | 1391 | 665.67 |
| unclassified | 1344 | 483.86 |
| secondary | 714 | 268.91 |
| motorway | 240 | 258.96 |
| primary | 874 | 233.59 |
| trunk | 318 | 191.31 |
| motorway_link | 296 | 132.44 |
| trunk_link | 387 | 79.13 |
| living_street | 486 | 65.18 |
| primary_link | 226 | 18.22 |
| tertiary_link | 86 | 6.82 |
| secondary_link | 71 | 3.14 |
| road | 5 | 0.95 |

Prototip sınıfları (motorway…tertiary + rampalar) toplamı 1:19 ölçekte **97.8 km oyun yolu** eder.

## Ana güzergâhlar

| Ref | way | km (iki yön toplam) | Bağlı parça | Not |
|---|---|---|---|---|
| D100 | 144 | 90.07 | 5 | Fiziksel olarak kesintisiz. 5 parçanın nedeni: Gebze'de way 1383071546'da `ref` etiketi eksik (40.7930, 29.4300); Eskihisar Feribot Yolu'nun 4 düğümlük parçası ve Tuzla sınırında rampa parçaları da D100 ref'i taşıyor. |
| O4 | 106 | 106.42 | 2 | TEM – iki yön kesintisiz |
| O7 | 97 | 121.13 | 2 | Kuzey Marmara Otoyolu |
| O5 | 12 | 11.01 | 2 | İstanbul–İzmir Otoyolu (Gebze başlangıcı) |

## Prototip çevresindeki adlı otoyol kavşakları (OSM `motorway_junction`)

| Kavşak | Ref | Düğüm sayısı | Oyun X (ort.) | Oyun Z (ort.) | Enlem | Boylam |
|---|---|---|---|---|---|---|
| Çayırova 1 | K-63 | 7 | -297.7 | -73.9 | 40.8174785 | 29.3650216 |
| Çayırova | K-62 | 2 | -298.5 | -83.7 | 40.8175713 | 29.3656826 |
| Şekerpınar 1 | K-61 | 9 | -222.8 | -359.4 | 40.8651663 | 29.3860302 |
| Şekerpınar | K-6 | 3 | -175.0 | -396.3 | 40.8666141 | 29.3988139 |
| Gebze OSB | K-6-1 | 1 | -127.6 | -335.9 | 40.8587121 | 29.4051184 |
| Gebze | K-7 | 2 | 197.8 | -39.1 | 40.8075669 | 29.4712735 |
| Gebze 1 | K-71 | 2 | 184.1 | -14.9 | 40.8034595 | 29.4786246 |
| Muallimköy | K-7-1 | 7 | 351.8 | 18.6 | 40.7900776 | 29.5142227 |
| Bilişim Vadisi | K-1 | 2 | 381.9 | 101.4 | 40.7808908 | 29.5173989 |
| D-100 Gebze | K-203 | 8 | 396.1 | -65.8 | 40.8140238 | 29.5226257 |
| Dilovası | K-8 | 2 | 433.4 | 121.5 | 40.776686 | 29.5297653 |
| Mermerciler OSB | K-201 | 3 | 492.3 | -428.9 | 40.8675532 | 29.5421202 |
| Demirciler OSB | K-202 | 3 | 470.5 | -185.4 | 40.8288232 | 29.5416033 |

Diğer: ana ağda 3+ kollu 3215 kesişim (prefab adayı), 230 döner kavşak parçası. Tam liste: `data/processed/junctions.csv`.

## 0.1.0 prototip koridoru (ölçek 1:19)

| Segment | Açıklama | Gerçek m | Oyun m | OSM yolları |
|---|---|---|---|---|
| P1_D100_dogu | D-100 doğu yönü: Çayırova batı sınırı -> Gebze | 6354.7 | 334.5 | D-100 (trunk) |
| P1_D100_bati | D-100 batı yönü: Gebze -> Çayırova batı sınırı | 6240.9 | 328.5 | D-100 (trunk) |
| P2_D100_TEM | Gebze D-100 -> en yakın TEM (O-4) bağlantısı | 3985.3 | 209.8 | Kocaeli - İstanbul Yolu → D100 → Kocaeli - İstanbul Yolu → Gebze 1 Kavşağı → Gebze Kavşağı |
| P3_Darica_D100 | Darıca merkez -> D-100 | 5031.3 | 264.8 | residential → Tuzla Caddesi → Aliarıcan Caddesi → İstasyon Caddesi → primary → Eskihisar Feribot Yolu |
| P4_Gebze_D100 | Gebze merkez -> D-100 | 1114.1 | 58.6 | Zübeyde Hanım Caddesi → residential → Hükümet Caddesi → residential → Adliye Caddesi → primary → trunk_link |
| P5_Cayirova_TEM | Çayırova merkez -> TEM (O-4) | 5985.6 | 315.0 | residential → Adnan Kahveci Caddesi → primary → Muammer Aksoy Caddesi → Şekerpınar-Çayırova Bağlantısı → Şekerpınar Kavşağı |

Bağlantılar ana ağ üzerinde gerçek en kısa yol olarak hesaplanmıştır (yönsüz; tek-yön kuralları yalnızca P1 için uygulanır). Görsel: `docs/img/prototype_corridor_s19.png`. Düğümler: `docs/EDITOR_NODES_s19.md`.
