"""Çift bilgisayar yayını – OYUN bilgisayarı Voicemeeter Potato ayarları (VoicemeeterRemote API).

Ses akışı (kullanıcının önceki VBAN düzeniyle aynı: iki ayrı akış, OBS'te ayrı kaynak):
  Oyun/sistem sesi -> "Voicemeeter Input"     (Strip[5]) -> A1 (kulaklık) + B1
  Discord vb.      -> "Voicemeeter AUX Input" (Strip[6]) -> A1 + B1
  Mikrofon         -> Strip[0] (Arctis 7+ mikrofon)       -> B2
  A1 = Kulaklıklar (Arctis 7+)
  VBAN çıkış 1 "OYUN PC KULAKLIK" = B1 -> OBS bilgisayarı UDP 6980
  VBAN çıkış 2 "OYUN PC MIKROFON" = B2 -> OBS bilgisayarı UDP 6980
OBS bilgisayarında: VBAN gelen akış 1 "OYUN PC KULAKLIK", akış 2 "OYUN PC MIKROFON", kaynak IP = bu bilgisayar.

Kullanım: python tools/stream/voicemeeter_gaming_pc.py [--obs-ip 192.168.1.150]
Önceki ayarların yedeği: D:\\SAKLAZ_DEV\\backups\\voicemeeter_*.
"""
import argparse
import ctypes
import sys
import time

DLL = r"C:\Program Files (x86)\VB\Voicemeeter\VoicemeeterRemote64.dll"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--obs-ip", default="192.168.1.150")
    ap.add_argument("--headset", default="Kulaklıklar (Arctis 7+)")
    ap.add_argument("--mic", default="Mikrofon (Arctis 7+)")
    a = ap.parse_args()
    vm = ctypes.WinDLL(DLL)
    r = vm.VBVMR_Login()
    if r < 0:
        sys.exit(f"Voicemeeter'a bağlanılamadı ({r}); Voicemeeter açık mı?")
    t = ctypes.c_long()
    for _ in range(40):  # bağlantı sonrası ilk parametre güncellemesini bekle
        vm.VBVMR_IsParametersDirty()
        vm.VBVMR_GetVoicemeeterType(ctypes.byref(t))
        if t.value:
            break
        time.sleep(0.25)
    if t.value != 3:
        sys.exit(f"Voicemeeter Potato bekleniyordu (tür {t.value}).")
    script = "\n".join([
        f'Strip[0].device.wdm="{a.mic}"',
        'Strip[0].Label="Mikrofon"', "Strip[0].A1=0", "Strip[0].A2=0", "Strip[0].B1=0", "Strip[0].B2=1",
        "Strip[0].B3=0", "Strip[0].Mute=0",
        'Strip[5].Label="Oyun"', "Strip[5].A1=1", "Strip[5].B1=1", "Strip[5].B2=0", "Strip[5].Mute=0",
        'Strip[6].Label="Discord"', "Strip[6].A1=1", "Strip[6].B1=1", "Strip[6].B2=0", "Strip[6].Mute=0",
        f'Bus[0].device.wdm="{a.headset}"', "Bus[0].Mute=0",
        "Bus[5].Mute=0", "Bus[6].Mute=0",
        "vban.Enable=1",
        "vban.outstream[0].on=1", 'vban.outstream[0].name="OYUN PC KULAKLIK"',
        f'vban.outstream[0].ip="{a.obs_ip}"', "vban.outstream[0].port=6980", "vban.outstream[0].bus=5",
        "vban.outstream[0].sr=48000", "vban.outstream[0].channel=2", "vban.outstream[0].quality=0",
        "vban.outstream[1].on=1", 'vban.outstream[1].name="OYUN PC MIKROFON"',
        f'vban.outstream[1].ip="{a.obs_ip}"', "vban.outstream[1].port=6980", "vban.outstream[1].bus=6",
        "vban.outstream[1].sr=48000", "vban.outstream[1].channel=2", "vban.outstream[1].quality=0",
    ])
    r = vm.VBVMR_SetParametersW(ctypes.c_wchar_p(script))
    if r != 0:
        sys.exit(f"Ayar uygulanamadı (kod {r}).")
    # uygulanan değerlerin geri okunabilmesi için güncellemeyi bekle
    for _ in range(20):
        time.sleep(0.25)
        vm.VBVMR_IsParametersDirty()
    # "vban.outstream[i].bus" Remote API'den değişmiyor (Potato 3.1.2.2'de denendi): ayarları XML'e kaydet,
    # VBAN çıkış satırlarını düzelt, Command.Load ile geri yükle.
    import os
    import re
    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), "saklaz_vm_gaming.xml")
    vm.VBVMR_SetParametersW(ctypes.c_wchar_p(f'Command.Save="{tmp}"'))
    time.sleep(2)
    s = open(tmp, encoding="utf-8", errors="surrogateescape").read()
    for idx, bus, name in ((1, 5, "OYUN PC KULAKLI"), (2, 6, "OYUN PC MIKROFO")):
        new = (f"<VBANStreamOut index='{idx}' bus='{bus}' status='1' name='{name}' ip='{a.obs_ip}' "
               f"port='6980' SR='48000' ch='2' NQ='0' format='1' />")
        s, n = re.subn(r"<VBANStreamOut index='%d'[^>]*/>" % idx, new, s)
        if n != 1:
            sys.exit(f"VBAN akış {idx} ayar dosyasında bulunamadı")
    open(tmp, "w", encoding="utf-8", errors="surrogateescape").write(s)
    vm.VBVMR_SetParametersW(ctypes.c_wchar_p(f'Command.Load="{tmp}"'))
    time.sleep(3)
    for _ in range(10):
        time.sleep(0.2)
        vm.VBVMR_IsParametersDirty()
    print("VBAN çıkışları: 1 = B1 (oyun), 2 = B2 (mikrofon) →", a.obs_ip)
    time.sleep(1.0)
    vm.VBVMR_IsParametersDirty()

    def get_s(name):
        buf = ctypes.create_unicode_buffer(512)
        vm.VBVMR_GetParameterStringW(ctypes.c_char_p(name.encode()), buf)
        return buf.value

    def get_f(name):
        f = ctypes.c_float()
        vm.VBVMR_GetParameterFloat(ctypes.c_char_p(name.encode()), ctypes.byref(f))
        return f.value

    for n in ("Strip[0].device.name", "Bus[0].device.name", "vban.outstream[0].name", "vban.outstream[0].ip",
              "vban.outstream[1].name", "vban.outstream[1].ip"):
        print(f"{n} = {get_s(n)}")
    for n in ("vban.Enable", "vban.outstream[0].on", "vban.outstream[0].bus", "vban.outstream[1].on",
              "vban.outstream[1].bus", "Strip[0].B2", "Strip[0].A1", "Strip[5].A1", "Strip[5].B1", "Strip[6].B1"):
        print(f"{n} = {get_f(n)}")
    vm.VBVMR_Logout()


if __name__ == "__main__":
    main()
