# Coğrafi Veri Kaynakları

| Veri | Kaynak | Lisans | İndirme (UTC) | Dosya |
|---|---|---|---|---|
| İlçe sınırları (Gebze, Darıca, Çayırova, Dilovası) | OpenStreetMap – Overpass API | ODbL 1.0 | 2026-11-21 | `data/raw/districts.json` |
| Yol ağı (motorway…service) | OpenStreetMap – Overpass API | ODbL 1.0 | 2026-11-21 | `data/raw/roads.json` |
| Kavşaklar, sinyaller, döner kavşaklar | OpenStreetMap – Overpass API | ODbL 1.0 | 2026-11-21 | `data/raw/junctions.json` |
| Arazi kullanımı / sanayi / depo | OpenStreetMap – Overpass API | ODbL 1.0 | 2026-11-21 | `data/raw/landuse.json` |
| Yerleşim düğümleri | OpenStreetMap – Overpass API | ODbL 1.0 | 2026-11-21 | `data/raw/places.json` |
| Demiryolu, istasyon, kıyı çizgisi | OpenStreetMap – Overpass API | ODbL 1.0 | 2026-11-21 | `data/raw/rail_coast.json` |
| Yükseklik (DEM) | Copernicus GLO-30 (aday, henüz indirilmedi) | Copernicus lisansı – atıf | – | – |

Her ham dosyanın yanında `*.meta.json` vardır: tam Overpass sorgusu, indirme zamanı ve OSM veri
zaman damgası (`osm_base_timestamp`). Ham veriler depoya girmez (`.gitignore`); `fetch_osm.py`
ile yeniden üretilir.

## Türetilmiş veriler

`data/roads/`, `data/cities/`, `data/processed/` altındaki dosyalar OSM'den türetilmiştir ve
**ODbL 1.0** kapsamındadır. Atıf zorunludur:

> © OpenStreetMap katkıda bulunanlar — https://www.openstreetmap.org/copyright

Harita modu yayımlanırsa mod açıklamasında ve `README`'de bu atıf yer almalıdır. ETS2 haritası
OSM'nin "Produced Work"ü sayılır; türetilmiş veritabanı (CSV/GeoJSON) paylaşılırsa ODbL ile paylaşılmalıdır.
