# Çift bilgisayar yayın kurulumu (Voicemeeter VBAN)

## Oyun bilgisayarı (192.168.1.186) – yapıldı 2026-11-22

Voicemeeter Potato 3.1.2.2 (Başlangıç klasöründen otomatik açılır).

| Voicemeeter | Aygıt / kaynak | Gönderim |
|---|---|---|
| Giriş 1 "Mikrofon" | Mikrofon (Arctis 7+) | B2 (kendi kulaklığına gitmez) |
| Sanal giriş "Oyun" (Voicemeeter Input) | Windows varsayılan oynatma: ETS2, sistem | A1 + B1 |
| Sanal giriş "Discord" (Voicemeeter AUX Input) | Windows iletişim aygıtı | A1 + B1 |
| A1 | Kulaklıklar (Arctis 7+) | duyma |

VBAN çıkış (UDP 6980, 48 kHz, 2 kanal) → OBS bilgisayarı `192.168.1.150`:
- akış 1 **OYUN PC KULAKLI** = B1 (oyun + sistem + Discord)
- akış 2 **OYUN PC MIKROFO** = B2 (mikrofon)
(VBAN akış adı en çok 15 karakter.)

Tekrar uygulamak / OBS IP'si değişirse:
```
.venv\Scripts\python.exe tools\stream\voicemeeter_gaming_pc.py --obs-ip 192.168.1.X
powershell -File tools\stream\set_default_audio.ps1
```
Profil dosyası: `Belgeler\Voicemeeter\SAKLAZ_OyunPC.xml` (Voicemeeter > Menu > Load Settings).
Not: `vban.outstream[i].bus` Remote API'den değişmiyor; betik ayarı XML'e kaydedip düzeltir ve `Command.Load` ile yükler.

Discord'da: Çıkış aygıtı "Voicemeeter AUX Input", giriş aygıtı "Mikrofon (Arctis 7+)".
OBS bilgisayarı açıkken: `192.168.1.150` gerçekten o bilgisayar olmalı (o bilgisayarda `ipconfig`).

## OBS bilgisayarı (yapılacak)
1. Voicemeeter (Banana veya Potato) kur, bilgisayarı yeniden başlat.
2. Betiği indir: https://github.com/SAKLAZ5341/ETS2-MODLAR/blob/main/tools/stream/obs_pc_setup.ps1 (Raw → farklı kaydet)
   ya da depoyu klonla.
3. PowerShell'i **yönetici olarak** aç ve çalıştır:
   `powershell -ExecutionPolicy Bypass -File obs_pc_setup.ps1` (yayın bilgisayarında da duymak için `-Monitor`)
   - gelen akış 1 `OYUN PC KULAKLI` → sanal giriş "Oyun PC" → B1; akış 2 `OYUN PC MIKROFO` → "Mikrofon" → B2
   - kaynak IP `192.168.1.186`, UDP 6980 güvenlik duvarı izni, Voicemeeter açılışta başlar
   - betik bu bilgisayarın IP'sini yazar; `192.168.1.150` değilse oyun bilgisayarında
     `.venv\Scripts\python.exe tools\streamoicemeeter_gaming_pc.py --obs-ip <IP>`
4. OBS → Ses Girişi Yakalama: `Voicemeeter Out B1` (Oyun), `Voicemeeter Out B2` (Mikrofon) ayrı kaynaklar.
5. Görüntü: yakalama kartı veya NDI ile oyun bilgisayarından.
