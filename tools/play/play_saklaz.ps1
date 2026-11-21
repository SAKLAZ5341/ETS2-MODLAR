# SAKLAZ Gebze–Darıca–Dilovası haritasını ETS2 önizleme modunda başlatır.
# Editör açıksa önce kapatır (editör + oyun aynı anda açıkken bilgisayar kilitlenmişti).
$ErrorActionPreference = 'Stop'
$game = 'C:\Program Files (x86)\Steam\steamapps\common\Euro Truck Simulator 2\bin\win_x64'
$homeDir = 'D:\SAKLAZ_DEV'

if (Get-Process eurotrucks2 -ErrorAction SilentlyContinue) {
    Write-Host 'ETS2 zaten açık; kapatılıyor...'
    Stop-Process -Name eurotrucks2 -Force
    Start-Sleep 3
}
# Steam'in başlatma-seçenekleri penceresini atlamak için (geliştirici yöntemi; silinerek geri alınır)
$appid = Join-Path $game 'steam_appid.txt'
if (-not (Test-Path $appid)) { Set-Content -Path $appid -Value '227300' -NoNewline -Encoding ascii }

Start-Process -FilePath (Join-Path $game 'eurotrucks2.exe') -WorkingDirectory $game -ArgumentList @(
    '-nosingle', '-preview', '/map/saklaz_city.mbd',
    '-previewconfig', '/preview_config/default.cfg',
    '-homedir', "`"$homeDir`"", '-noworkshop', '-mm_pool_size', '2048')
Write-Host 'Harita yükleniyor. Açılınca ESC ile menüyü kapatıp sürmeye başlayabilirsin.'
