# Map Editor – Prototip Oluşturma Kılavuzu (elle yapılacak adımlar)

> 2026-11-21'de bu adımlar uygulandı: `saklaz` haritası oluşturuldu ve D-100 çizildi.
> Menü adları ETS2 1.62.3.3 editöründe doğrulandı. Boş harita kaydedilemez; önce en az bir öğe ekleyin.
> Haritanın gerçek yeri: `mod\user_map\map\saklaz.mbd` (`editor\saklaz.mbd` yalnızca editörün durum dosyasıdır).

## 0. Editörü doğru profille açın

Her zaman bu ayrı profili kullanın (ana profildeki 65 mod editöre yüklenmesin):

```powershell
& "C:\Program Files (x86)\Steam\steamapps\common\Euro Truck Simulator 2\bin\win_x64\eurotrucks2.exe" -homedir "D:\SAKLAZ_DEV" -noworkshop -edit
```

`-edit` sonrasına harita adı yazılmazsa editör **boş ve siyah** açılır; bu normaldir.

## 1. Boş SAKLAZ harita modülünü oluşturun (Öncelik 1)

1. Editör menüsünden yeni harita oluşturun (*File → New map* veya eşdeğeri).
2. Haritayı **`saklaz`** adıyla kaydedin (*File → Save map as*). `europe` adını **kullanmayın**:
   bu, oyunun ana haritasının adıdır.
3. Editörü kapatıp yeniden açın, *File → Open map → saklaz* ile açılıp açılmadığını kontrol edin.
4. Kayıt yerini doğrulayın: dosyaların `D:\SAKLAZ_DEV\Euro Truck Simulator 2\` altında
   (beklenen: `mod\user_map\map\saklaz.mbd` ve `mod\user_map\map\saklaz\` sektör klasörü) oluştuğunu görün.
5. Sonucu kaydedin:
   ```powershell
   .\.venv\Scripts\python.exe -I tools\validation\check_editor_output.py
   ```
   Bu betik salt okunurdur; kayıtlı haritayı ve editor.log hatalarını raporlar.

## 2. Koordinat referansı

- Tüm noktalar: `data/processed/prototype/editor_nodes.csv` (`game_x`, `game_z` sütunları, oyun metresi).
- Köken (0, 0) = Gebze OSM yerleşim düğümü. +X doğu, +Z güney. Ölçek: `prototype_summary.json` → `scale_divisor`.
- Genel görünüm: `docs/img/prototype_corridor.png`.
- Editörde imleç koordinatı durum çubuğunda görünür; düğümleri CSV'deki değerlere yakın yerleştirin.
  Editörün konsolunda/arama kutusunda koordinata gitme özelliği varsa onu kullanın (sürümle doğrulanacak).

## 3. Çizim sırası

| Sıra | Segment (CSV `segment`) | Ne | Önerilen yol tipi |
|---|---|---|---|
| 1 | `P1_D100_0`, `P1_D100_1` | D-100 Çayırova→Gebze, iki yön | bölünmüş ana yol |
| 2 | `P4_Gebze_D100` | Gebze merkez bağlantısı | 1+1 şehir yolu |
| 3 | `P3_Darica_D100` | Darıca bağlantısı | 1+1 |
| 4 | `P2_D100_TEM`, `P5_Cayirova_TEM` | TEM (O-4) bağlantıları | rampa + bağlantı yolu |

Kavşaklarda yol ucu yerine prefab (kavşak) kullanın; aday konumlar `data/processed/junctions.csv`.

## 4. Her oturum sonunda

1. Haritayı kaydedin.
2. `check_editor_output.py` çalıştırın.
3. Proje klasöründe `git add -A; git commit` (harita dosyaları D:\SAKLAZ_DEV'de; onları
   `D:\SAKLAZ_DEV\backups\` altına tarihli kopya olarak yedekleyin).
