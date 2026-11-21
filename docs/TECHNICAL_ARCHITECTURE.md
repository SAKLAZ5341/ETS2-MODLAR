# Teknik Mimari

## 1. Veri akışı

```
OpenStreetMap (Overpass API)
   │  tools/geo/fetch_osm.py        → data/raw/*.json (+ .meta.json: zaman, sorgu, lisans)   [depoya girmez]
   ▼
build_network.py                    → data/roads/*.geojson, data/cities/*.geojson
   │                                  data/processed/editor_roads_main.csv, junctions.csv,
   │                                  industrial_sites.csv, places.csv, network_report.json
   ▼
build_prototype.py                  → data/processed/prototype/editor_nodes.csv,
   │                                  prototype.geojson, prototype_summary.json,
   │                                  docs/img/prototype_corridor.png
   ▼
ETS2 Map Editor (elle)              → D:\SAKLAZ_DEV\Euro Truck Simulator 2\mod\user_map\map\saklaz.mbd + sektörler
```

Tüm betikler proje içindeki `.venv` ile çalışır; sistem geneline paket kurulmaz:

```powershell
.\.venv\Scripts\python.exe -I tools\geo\fetch_osm.py
.\.venv\Scripts\python.exe -I tools\geo\build_network.py
.\.venv\Scripts\python.exe -I tools\geo\build_prototype.py
```

## 2. Koordinat sistemi

| Adım | Sistem | Not |
|---|---|---|
| Kaynak | WGS84, EPSG:4326 | OSM ham verisi |
| Metrik | UTM 35N, EPSG:32635 | Gebze ~29.43°D, 35N diliminin (24–30°D) doğu kenarına yakın; bölge küçük olduğu için ölçek bozulması ihmal edilebilir (<%0,1) |
| Oyun | ETS2 dünya metresi | `x = (E − E0) / s`, `z = −(N − N0) / s`, `y` = 0 (yükseklik yok) |

- **Köken (E0, N0):** OSM'deki `Gebze` (place=town/city) düğümü. Gerçek düğüm; düğüm id'si `network_report.json`'da.
- **Eksenler:** ETS2'de +X doğu, +Z güney, +Y yukarıdır. Bu yüzden kuzey (N) işaret değiştirir.
- **Ölçek `s`:** varsayılan **19** (ETS2 standart haritasının kırsal ölçeğine yakın). Şehir içi
  için SCS 1:3 civarı kullanır. **Ölçek kararı kullanıcıya aittir**; `--scale` parametresiyle
  tüm çıktılar yeniden üretilebilir. Ölçek değişirse editörde çizilen yollar da yeniden çizilmelidir.

## 3. Yol sınıflandırması

| OSM `highway` | Katman | Prototipte | Önerilen ETS2 yol tipi |
|---|---|---|---|
| motorway | otoyol | evet | bölünmüş otoyol 2x2/2x3 |
| trunk | ana_yol | evet | bölünmüş yol (D-100 burada) |
| primary | birincil | evet | 2x2 veya 1+1 |
| secondary | ikincil | evet | 1+1 |
| tertiary | ucuncul | evet | 1+1 dar |
| *_link | rampa | evet | tek yön rampa |
| unclassified / residential / service | yerel / servis | hayır (yalnızca bağlantı arama) | — |

`ref` etiketleri boşluk/tire temizlenerek normalize edilir (`D 100` → `D100`, `O-4` → `O4`).

## 4. Doğrulama

- Ana ağ, ortak OSM düğüm koordinatları üzerinden graf olarak kurulur (networkx);
  bağlı bileşen sayısı ve en büyük bileşen oranı raporlanır.
- D-100 ve O-4 için `ref` alt grafiği kurulup parça sayısı raporlanır (bölünmüş yolda 2 parça normal).
- Prototip bağlantıları (Darıca→D-100, D-100→TEM vb.) **gerçek en kısa yol** olarak hesaplanır;
  bağlantı bulunamazsa "ağ kopuk" diye raporlanır, uydurulmaz.

## 5. SCS dosya formatları hakkında

ETS2 harita sektörleri (`.base`, `.aux`, `.data`, `.snd`, `.desc`, `.layer`) belgelenmemiş ikili
dosyalardır. Proje talimatı gereği bu dosyalar **tahminle üretilmez**. Harita yalnızca SCS Map Editor
ile oluşturulur ve kaydedilir; Python araçları editöre referans veri (koordinat listesi, görsel) hazırlar.

## 6. Yükseklik

Map Editor DEM içe aktarmaz. 0.1.0'da tüm noktalar `y = 0`. Yükseklik profili (Copernicus GLO-30
veya SRTM) sonraki adımdır; editörde elle uygulanacaktır.
