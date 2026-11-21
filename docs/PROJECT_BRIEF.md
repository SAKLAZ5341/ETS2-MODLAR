SAKLAZ TÜRKİYE MAP – ANA GELİŞTİRME TALİMATI

1. PROJE KİMLİĞİ

Proje adı: SAKLAZ Türkiye Map
Hedef oyun: Euro Truck Simulator 2 (Steam – güncel kararlı sürüm)
İlk sürüm: 0.1.0
İlk bölge: Gebze – Darıca – Çayırova
Harita hedefi: Gerçek coğrafyaya dayalı, gerçekçi sürüş mesafelerine sahip Türkiye haritası.

Geliştirme modeli:

- Claude Code: Teknik geliştirme ve otomasyon.
- ChatGPT: Mimari denetim, kalite kontrolü ve teknik inceleme.
- Kullanıcı: SCS Map Editor ve gerçek oyun testleri.

2. TEMEL HEDEF

ETS 2 için kurulabilir, oynanabilir, sürdürülebilir ve genişletilebilir bir Türkiye haritası oluştur.

Harita şu özelliklere sahip olmalı:

- Gerçek coğrafi konumlar.
- Gerçek yol güzergâhları.
- Gerçekçi kavşaklar ve yol bağlantıları.
- Türkiye'ye özgü tabelalar.
- Gerçekçi sanayi bölgeleri.
- Fabrikalar, depolar ve lojistik tesisleri.
- Doğru arazi yükseklikleri ve yol eğimleri.
- Çalışan trafik ve navigasyon.
- Performanslı sektör yapısı.

3. GELİŞTİRME PRENSİPLERİ

1. Öncelikle mevcut bilgisayarı, ETS 2 kurulumunu ve geliştirme araçlarını analiz et.
2. ETS 2'nin kurulu sürümünü ve DLC durumunu tespit et.
3. SCS Map Editor ve SCS araçlarının uyumluluğunu kontrol et.
4. Bilgisayarda bulunmayan araçları kendiliğinden kurma.
5. Kullanıcının mevcut dosyalarını silme veya üzerine yazma.
6. Her geliştirmeyi küçük ve test edilebilir aşamalara ayır.
7. Gerçek olmayan koordinatları gerçekmiş gibi gösterme.
8. Coğrafi verilerin kaynağını ve lisansını kaydet.
9. Her aşamada test raporu oluştur.
10. Çalışmayan özellikleri tamamlandı olarak bildirme.

4. İLK GELİŞTİRME BÖLGESİ

Gebze – Darıca – Çayırova.

Öncelikli yerler:

- Gebze şehir merkezi
- Gebze Organize Sanayi Bölgesi
- Gebze Plastikçiler OSB
- Dilovası bağlantısı
- Çayırova
- Darıca
- D-100 bağlantısı
- TEM bağlantısı

Bu alanın gerçek coğrafi koordinatlarını ve yol geometrisini araştır.

OpenStreetMap ve uygun açık coğrafi veri kaynaklarından yararlan. Kaynak ve lisans bilgilerini GEO_DATA_SOURCES.md dosyasına kaydet.

5. TEKNİK ARAÇLAR

Ana araçlar:

- ETS 2 SCS Map Editor
- SCS Blender Tools
- Blender
- SCS Conversion Tools
- QGIS
- Python
- Git

Öncelikle resmi SCS dokümantasyonunu incele:
https://modding.scssoft.com/wiki/Tutorials/Map_Editor

https://modding.scssoft.com/wiki/Documentation/Tools/SCS_Blender_Tools

Harita sektörlerinin oluşturulmasında SCS Map Editor'ün gerçek çalışma biçimine bağlı kal.

Python araçlarını coğrafi veri hazırlama, koordinat dönüşümü, veri doğrulama ve raporlama için kullan.

SCS sektör dosyalarını tahmin ederek veya rastgele metin üreterek oluşturma.

6. PROJE DOSYA YAPISI

Aşağıdaki yapıyı oluştur:

SAKLAZ-Turkiye-Map/
docs/
PROJECT_PLAN.md
ROAD_NETWORK.md
CITY_DATABASE.md
GEO_DATA_SOURCES.md
TESTING.md
CHANGELOG.md
TECHNICAL_ARCHITECTURE.md

data/
raw/
processed/
roads/
cities/
terrain/

map/
standalone/
promods/

assets/
models/
buildings/
signs/
textures/

tools/
geo/
validation/
packaging/

tests/
releases/

Gerçek SCS harita dosyaları için gerekli dizin ve modül yapısını resmi dokümantasyondan doğrula. Bu dizin yapısını zorla kullanma; gerekirse SCS formatına uygun şekilde uyarla.

7. İLK SÜRÜMÜN GÖREVLERİ

0.1.0 – İlk teknik prototip

AŞAMA A – Ortam analizi

- ETS 2 kurulum yolunu bul.
- Oyun sürümünü tespit et.
- Gerekli DLC'leri listele.
- Map Editor erişimini doğrula.
- Blender ve SCS Tools durumunu incele.
- Mevcut disk alanını kontrol et.

AŞAMA B – Coğrafi veri

- Gebze ve Darıca koordinatlarını hazırla.
- Yol ağını çıkar.
- D-100 ve TEM güzergâhlarını belirle.
- Önemli kavşakları işaretle.
- Coğrafi referans sistemini ve oyun koordinat dönüşüm yöntemini belgele.
- Veri doğrulama raporu oluştur.

AŞAMA C – Harita altyapısı

- Yeni harita modülü oluşturma yöntemini belirle.
- Modül tanımlarını hazırla.
- Gerekli def ve map yapılarını belirle.
- İlk harita sektörünün oluşturulma sürecini belgele.
- Test başlangıç noktası planla.

AŞAMA D – İlk yollar

- Gebze başlangıç noktası.
- Darıca bağlantısı.
- Çayırova bağlantısı.
- D-100 bağlantısı.
- Yol ve prefab bağlantı kontrolleri.

AŞAMA E – İlk yerleşim

- Temel şehir yerleşimi.
- İlk fabrika/depo alanı.
- Yol tabelaları.
- Arazi düzenlemesi.
- Basit çevre modelleri.

AŞAMA F – Test ve paketleme

- Editörde açılış testi.
- Sektör kaydetme testi.
- Eksik asset kontrolü.
- Yol bağlantısı testi.
- Navigasyon testi.
- Oyun içi yükleme testi.
- Test modunu .scs olarak paketleme.

8. PROMODS UYUMLULUĞU

Standalone ve ProMods sürümlerini ayrı ele al.

Öncelik:

1. Standalone prototip.
2. Bağımsız haritanın kararlı hale getirilmesi.
3. ProMods uyumluluk analizi.
4. Gerekirse ayrı bağlantı ve uyumluluk paketi.

ProMods dosyalarını izinsiz kopyalama veya yeniden dağıtma.

ProMods uyumluluğu gerçek sürüm ve yükleme sırası testleriyle doğrulanmadan garanti edilmiş olarak açıklanamaz.

9. TEST VE KALİTE KONTROLÜ

Her aşama için:

- Yapılan işler
- Değiştirilen dosyalar
- Test edilen özellikler
- Başarısız testler
- Bilinen sorunlar
- Sonraki aşama

raporlanmalı.

Aşağıdaki durumlarda sürümü tamamlandı olarak işaretleme:

- Harita editörde açılmıyorsa.
- Sektörler kaydedilemiyorsa.
- Eksik modeller varsa.
- Yol bağlantıları hatalıysa.
- Oyun yükleme sırasında çöküyorsa.
- Oyun içi test yapılmamışsa.

10. GÜVENLİK VE DOSYA YÖNETİMİ

- Mevcut ETS 2 dosyalarını değiştirme.
- Orijinal oyun dosyalarına müdahale etme.
- Herhangi bir dosyayı silmeden önce kullanıcı onayı al.
- Gizli anahtar veya hesap bilgisi isteme.
- Git işlemlerinde mevcut değişiklikleri koru.
- Kullanıcının onayı olmadan GitHub'a push yapma.
- Mevcut dosyaların üzerine yazma.
- Her önemli aşamadan önce yedek oluştur.

11. İLK GÖREV

ŞİMDİ SADECE AŞAMA A İLE BAŞLA.

Önce bilgisayardaki geliştirme ortamını incele.

Henüz harita dosyası oluşturma veya oyuna müdahale etme.

Bana şu bilgileri içeren bir başlangıç raporu sun:

1. ETS 2 kurulum durumu.
2. ETS 2 sürümü.
3. Map Editor erişimi.
4. Blender durumu.
5. SCS Blender Tools durumu.
6. Gerekli araçların eksikleri.
7. Disk alanı.
8. Coğrafi veri hazırlığı için gerekli araçlar.
9. İlk prototip için teknik engeller.
10. Önerilen sonraki adım.

Ortam analizi tamamlandıktan sonra AŞAMA B için uygulanabilir görev listesi oluştur.

Herhangi bir teknik engel varsa tahmin yürütme; kanıtla ve raporla.

PROJENİN ANA HEDEFİ:
SAKLAZ Türkiye Map'i gerçekçi, kaliteli, oynanabilir ve uzun vadede büyütülebilir bir ETS 2 haritasına dönüştürmek.

İlk öncelik hız değil, doğru çalışan bir temel oluşturmaktır.