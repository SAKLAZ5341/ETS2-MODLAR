# SAKLAZ Türkiye Map

Euro Truck Simulator 2 için gerçek coğrafyaya dayalı Türkiye haritası.

- Hedef oyun: ETS 2 (Steam, güncel kararlı sürüm)
- Sürüm: 0.1.0 (geliştirme aşamasında, oynanabilir değil)
- İlk bölge: Gebze – Darıca – Çayırova

## Durum

| Aşama | Konu | Durum |
|---|---|---|
| A | Ortam analizi | Devam ediyor – ortam raporu bekleniyor |
| B | Coğrafi veri | Başlamadı |
| C | Harita altyapısı | Başlamadı |
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
