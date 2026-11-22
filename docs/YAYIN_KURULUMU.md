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
1. Voicemeeter (Banana yeterli) kur, yeniden başlat.
2. VBAN > gelen akış 1: ad `OYUN PC KULAKLI`, IP `192.168.1.186`, port 6980 → bir girişe (ör. giriş 1).
   Gelen akış 2: ad `OYUN PC MIKROFO`, IP `192.168.1.186` → başka bir giriş.
3. Bu girişleri OBS'in dinleyeceği bus'lara gönder (ör. oyun → B1, mikrofon → B2) ve OBS'te
   "Ses Girişi Yakalama": `Voicemeeter Out B1` (Oyun), `Voicemeeter Out B2` (Mikrofon) ayrı kaynak olarak.
4. Güvenlik duvarı: Voicemeeter'a özel ağda UDP 6980 izni.
5. Görüntü: yakalama kartı veya NDI ile oyun bilgisayarından.
