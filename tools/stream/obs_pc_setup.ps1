# Çift bilgisayar yayını – OBS (yayın) bilgisayarı Voicemeeter VBAN alım ayarı.
#
# Oyun bilgisayarı (192.168.1.186) iki VBAN akışı gönderir (UDP 6980, 48 kHz):
#   "OYUN PC KULAKLI" = oyun + sistem + Discord     "OYUN PC MIKROFO" = mikrofon
# Bu betik (OBS bilgisayarında, Voicemeeter Banana veya Potato açıkken):
#   - gelen akış 1 -> 1. sanal giriş ("Oyun PC"), gelen akış 2 -> 2. sanal giriş ("Mikrofon")
#   - Oyun PC -> B1 (+ A1 izleme isteğe bağlı), Mikrofon -> B2
#   - OBS'te ses kaynakları: "Voicemeeter Out B1" (oyun) ve "Voicemeeter Out B2" (mikrofon)
#   - Güvenlik duvarı: UDP 6980 gelen (yönetici ise)
# Kullanım (PowerShell):  powershell -ExecutionPolicy Bypass -File obs_pc_setup.ps1 [-GamePcIp 192.168.1.186] [-Monitor]
param(
    [string]$GamePcIp = "192.168.1.186",
    [switch]$Monitor
)
$ErrorActionPreference = 'Stop'
$dll = 'C:\Program Files (x86)\VB\Voicemeeter\VoicemeeterRemote64.dll'
if (-not (Test-Path $dll)) { throw "Voicemeeter kurulu değil: önce Voicemeeter'ı kurup bilgisayarı yeniden başlatın." }
if (-not (Get-Process | Where-Object { $_.ProcessName -match '^voicemeeter' })) {
    $exe = Get-ChildItem 'C:\Program Files (x86)\VB\Voicemeeter' -Filter 'voicemeeter*x64.exe' | Sort-Object Name -Descending | Select-Object -First 1
    Start-Process $exe.FullName; Start-Sleep 6
}
Add-Type -TypeDefinition @"
using System; using System.Runtime.InteropServices; using System.Text;
public static class VM {
  const string D = @"$dll";
  [DllImport(D)] public static extern int VBVMR_Login();
  [DllImport(D)] public static extern int VBVMR_Logout();
  [DllImport(D)] public static extern int VBVMR_IsParametersDirty();
  [DllImport(D)] public static extern int VBVMR_GetVoicemeeterType(out int t);
  [DllImport(D, CharSet = CharSet.Unicode)] public static extern int VBVMR_SetParametersW(string s);
  [DllImport(D)] public static extern int VBVMR_GetParameterFloat(string n, out float v);
}
"@
if ([VM]::VBVMR_Login() -lt 0) { throw "Voicemeeter'a bağlanılamadı." }
$t = 0
for ($i = 0; $i -lt 40 -and $t -eq 0; $i++) { [void][VM]::VBVMR_IsParametersDirty(); [void][VM]::VBVMR_GetVoicemeeterType([ref]$t); Start-Sleep -Milliseconds 250 }
# sanal girişler: Banana 3,4 / Potato 5,6 ; bus: Banana A1-A3=0-2, B1=3, B2=4 / Potato A1-A5=0-4, B1=5, B2=6
switch ($t) {
  2 { $v1 = 3; $v2 = 4; $b1 = 'B1'; $b2 = 'B2'; $kind = 'Banana' }
  3 { $v1 = 5; $v2 = 6; $b1 = 'B1'; $b2 = 'B2'; $kind = 'Potato' }
  default { throw "Voicemeeter Banana veya Potato gerekli (bulunan tür: $t)." }
}
$a1 = if ($Monitor) { 1 } else { 0 }
$script = @(
  "Strip[$v1].Label=`"Oyun PC`"", "Strip[$v1].A1=$a1", "Strip[$v1].$b1=1", "Strip[$v1].$b2=0", "Strip[$v1].Mute=0",
  "Strip[$v2].Label=`"Mikrofon`"", "Strip[$v2].A1=$a1", "Strip[$v2].$b1=0", "Strip[$v2].$b2=1", "Strip[$v2].Mute=0",
  "vban.Enable=1"
) -join "`n"
if ([VM]::VBVMR_SetParametersW($script) -ne 0) { throw "Voicemeeter ayarı uygulanamadı." }
for ($i = 0; $i -lt 10; $i++) { [void][VM]::VBVMR_IsParametersDirty(); Start-Sleep -Milliseconds 200 }
# VBAN gelen akışları: bazı alanlar Remote API'den değişmiyor -> ayar dosyası üzerinden (Command.Save/Load)
$tmp = Join-Path $env:TEMP 'saklaz_vm_obs.xml'
[void][VM]::VBVMR_SetParametersW("Command.Save=`"$tmp`"")
Start-Sleep 2
$x = [IO.File]::ReadAllText($tmp)
$streams = @(@{ i = 1; name = 'OYUN PC KULAKLI'; in = $v1 }, @{ i = 2; name = 'OYUN PC MIKROFO'; in = $v2 })
foreach ($s in $streams) {
  $new = "<VBANStreamIn index='$($s.i)' in='$($s.in)' status='1' name='$($s.name)' ip='$GamePcIp' port='6980' NQ='1' />"
  $rx = [regex]"<VBANStreamIn index='$($s.i)'[^>]*/>"
  if (-not $rx.IsMatch($x)) { throw "Ayar dosyasında VBAN gelen akış $($s.i) yok." }
  $x = $rx.Replace($x, $new, 1)
}
[IO.File]::WriteAllText($tmp, $x)
[void][VM]::VBVMR_SetParametersW("Command.Load=`"$tmp`"")
Start-Sleep 3
for ($i = 0; $i -lt 10; $i++) { [void][VM]::VBVMR_IsParametersDirty(); Start-Sleep -Milliseconds 200 }
$prof = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Voicemeeter\SAKLAZ_ObsPC.xml'
New-Item -ItemType Directory -Force (Split-Path $prof) | Out-Null
[void][VM]::VBVMR_SetParametersW("Command.Save=`"$prof`"")
Start-Sleep 2
[void][VM]::VBVMR_Logout()
Write-Host "Voicemeeter $kind ayarlandı: akış 1 -> sanal giriş 'Oyun PC' -> $b1, akış 2 -> 'Mikrofon' -> $b2 (kaynak $GamePcIp)."
Write-Host "Profil: $prof"

# Voicemeeter açılışta başlasın
$lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'Voicemeeter.lnk'
$exe = Get-ChildItem 'C:\Program Files (x86)\VB\Voicemeeter' -Filter 'voicemeeter*x64.exe' | Sort-Object Name -Descending | Select-Object -First 1
$sc = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk); $sc.TargetPath = $exe.FullName; $sc.WindowStyle = 7; $sc.Save()

# güvenlik duvarı (yönetici gerekir)
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($admin) {
  if (-not (Get-NetFirewallRule -DisplayName 'VBAN UDP 6980' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName 'VBAN UDP 6980' -Direction Inbound -Protocol UDP -LocalPort 6980 -Action Allow -Profile Private,Domain | Out-Null
  }
  Write-Host "Güvenlik duvarı: UDP 6980 gelen izni var."
} else {
  Write-Host "UYARI: yönetici değil; güvenlik duvarı kuralı eklenmedi. Voicemeeter ilk açılışta izin sorarsa 'Özel ağlar'ı onaylayın."
}
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.168.*' } | Select-Object -First 1).IPAddress
Write-Host "Bu bilgisayarın IP adresi: $ip   (oyun bilgisayarı akışları 192.168.1.150'ye gönderiyor; farklıysa oyun PC'de:"
Write-Host "  .venv\Scripts\python.exe tools\stream\voicemeeter_gaming_pc.py --obs-ip $ip )"
Write-Host "OBS: Ses Girişi Yakalama -> 'Voicemeeter Out $b1' (Oyun) ve 'Voicemeeter Out $b2' (Mikrofon) ekleyin."
