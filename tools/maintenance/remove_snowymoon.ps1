# SnowyMoon grafik paketini ETS2 oyun klasöründen KALDIRIR (silmez, yedeğe taşır).
#
#   powershell -ExecutionPolicy Bypass -File .\tools\maintenance\remove_snowymoon.ps1
#
# Taşınan dosyalar 23.10.2026'da SnowyMoon kurulumuyla eklenenlerdir (ReShade, OptiScaler,
# DLSS5 eklentileri, snowymoon klasörü). Oyunun kendi dosyalarına dokunulmaz.
# Geri almak için: .\tools\maintenance\restore_snowymoon.ps1 -BackupDir "<yedek klasörü>"

$ErrorActionPreference = 'Stop'
if (Get-Process eurotrucks2 -ErrorAction SilentlyContinue) { throw "ETS2 / editör açık. Önce kapatın." }

$bin = "C:\Program Files (x86)\Steam\steamapps\common\Euro Truck Simulator 2\bin\win_x64"
$dst = "D:\SAKLAZ_DEV\backups\snowymoon_kaldirildi_$(Get-Date -Format yyyyMMdd_HHmmss)\bin_win_x64"
New-Item -ItemType Directory -Force $dst | Out-Null

$items = @(
  'snowymoon', 'snowymoon.io_env.dat', 'snowymoon.io_lighting_v1_0_0.cfg', 'snowymoon_logs.txt',
  'winmm.dll', 'ReShade.ini', 'ReShade2.ini', 'reshade-shaders', 'ReShade.log',
  'renodx-dlss5.addon64', 'dlss5-bridge.addon64', 'dlss5-bridge.cfg',
  'dxgi.dll', 'OptiScaler.ini', 'OptiScaler.log', 'optiscaler', 'dinput8.dll',
  'nvngx_dlss.dll', 'nvngx_dlssnr.dll', 'nvngx_dlssnr.dll.original', 'nvngx.dll_dlssnr.dll'
)
$moved = @()
foreach ($i in $items) {
  $s = Join-Path $bin $i
  if (Test-Path -LiteralPath $s) { Move-Item -LiteralPath $s -Destination $dst; $moved += $i }
}
Write-Host "Taşınan ($($moved.Count)): $($moved -join ', ')"
Write-Host "Yedek: $dst"
Write-Host "Oyunun bütünlüğü için isteğe bağlı: Steam > ETS2 > Özellikler > Yüklü Dosyalar > 'Oyun dosyalarının bütünlüğünü doğrula'."
