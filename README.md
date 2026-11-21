# SAKLAZ Türkiye Map

Euro Truck Simulator 2 için gerçek coğrafyaya dayalı Türkiye haritası.

- Hedef oyun: ETS 2 1.62.3.3 (Steam)
- Sürüm: 0.1.0 (geliştirme aşamasında, oynanabilir değil)
- İlk bölge: Gebze – Darıca – Çayırova

## Durum

| Aşama | Konu | Durum |
|---|---|---|
| A | Ortam analizi | Tamamlandı (docs/TECHNICAL_REVIEW_20261121.md) |
| B | Coğrafi veri | Tamamlandı – OSM verisi, yol ağı, prototip koridoru |
| C | Harita altyapısı | Bekliyor – editörde `saklaz` haritası elle oluşturulacak |
| D | İlk yollar | Başlamadı |
| E | İlk yerleşim | Başlamadı |
| F | Test ve paketleme | Başlamadı |

## Aşama A: ortam raporu nasıl alınır

Windows bilgisayarda, depo klasöründe PowerShell açıp çalıştırın:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\validation\env_check.ps1
```

Betik salt okunurdur: hiçbir şey kurmaz, silmez veya değiştirmez. Çalıştığı
klasöre `ENV_REPORT_<tarih>.md` dosyasını yazar. Bu dosyayı paylaşın.

## Klasörler

- `docs/` – plan, kaynaklar, test raporları
- `tools/validation/` – ortam ve veri doğrulama betikleri
- `data/raw`, `data/processed` – coğrafi veriler (Aşama B)

Harita (`map/`) ve asset klasörleri, SCS'nin gerçek mod yapısı resmi
dokümantasyondan doğrulandıktan sonra Aşama C'de eklenecek.

## Lisans

Coğrafi veri kaynakları ve lisansları `docs/GEO_DATA_SOURCES.md` dosyasında
tutulur. OpenStreetMap verisi ODbL lisanslıdır ve atıf gerektirir.

## Coğrafi veri araçları

```powershell
.\.venv\Scripts\python.exe -I tools\geo\fetch_osm.py          # OSM indir (data/raw)
.\.venv\Scripts\python.exe -I tools\geo\build_network.py      # yol ağı, kavşak, sanayi
.\.venv\Scripts\python.exe -I tools\geo\build_prototype.py --scale 19
.\.venv\Scripts\python.exe -I tools\geo\export_editor_tables.py --scale 19
.\.venv\Scripts\python.exe -I tests\run_tests.py
```

Editör adımları: `docs/EDITOR_GUIDE.md`. Son durum: `docs/OVERNIGHT_REPORT_20261121.md`.

Harita verisi © OpenStreetMap katkıda bulunanlar (ODbL 1.0).
