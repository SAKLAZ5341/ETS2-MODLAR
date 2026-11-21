# remove_snowymoon.ps1 ile taşınan dosyaları oyun klasörüne GERİ koyar.
#   powershell -ExecutionPolicy Bypass -File .\tools\maintenance\restore_snowymoon.ps1 -BackupDir "D:\SAKLAZ_DEV\backups\snowymoon_kaldirildi_...\bin_win_x64"
param([Parameter(Mandatory)][string]$BackupDir)
$ErrorActionPreference = 'Stop'
if (Get-Process eurotrucks2 -ErrorAction SilentlyContinue) { throw "ETS2 açık. Önce kapatın." }
$bin = "C:\Program Files (x86)\Steam\steamapps\common\Euro Truck Simulator 2\bin\win_x64"
Get-ChildItem -LiteralPath $BackupDir | ForEach-Object {
  $t = Join-Path $bin $_.Name
  if (Test-Path -LiteralPath $t) { Write-Host "Atlandı (zaten var): $($_.Name)"; return }
  Move-Item -LiteralPath $_.FullName -Destination $bin; Write-Host "Geri kondu: $($_.Name)"
}
