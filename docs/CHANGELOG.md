# Değişiklik Günlüğü

## [Yayınlanmadı] – 0.1.0 geliştirme

### Düzeltildi (env_check.ps1 inceleme sonrası)
- C:\ üzerindeki geniş recursive tarama kaldırıldı; Conversion Tools yalnızca sınırlı konumlarda aranıyor (`-ExtraSearchPath` ile genişletilebilir).
- Map Editor kontrolü üç bağımsız duruma ayrıldı: 4a log dosyası mevcut, 4b geçmiş açılış kanıtları, 4c kullanıcının bildirdiği `-edit` testi (`-EditorTest`).
- Blender: Program Files (x64/x86), Steam kütüphaneleri, PATH ve Programlar kayıtlarında aranıyor; bulunamaması kesin yokluk sayılmıyor.
- Raporun başına gizlilik uyarısı eklendi.
- Her bölüm ayrı hata yakalamalı; hatalar bölüm, tür ve satır numarasıyla raporlanıyor.
- Microsoft Store yönlendirme kısayolları çalıştırılmıyor; rapor dosyası var olanın üzerine yazılmıyor.
- Dosya UTF-8 BOM ile kaydedildi (PowerShell 5.1 Türkçe karakterleri doğru okusun diye).

### Eklendi
- Proje iskeleti, README, proje talimatı (`docs/PROJECT_BRIEF.md`).
- Aşama A için salt okunur ortam analizi betiği (`tools/validation/env_check.ps1`).
- Aşama A raporu ve Aşama B görev listesi (`docs/STAGE_A_REPORT.md`).
