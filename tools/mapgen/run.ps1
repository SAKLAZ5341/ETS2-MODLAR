# SAKLAZ Türkiye Map - harita üreticiyi kurup çalıştırır (kullanıcı tarafından çalıştırılır).
#
#   powershell -ExecutionPolicy Bypass -File .\tools\mapgen\run.ps1
#
# 1) .NET 10 SDK'yı yalnızca D:\SAKLAZ_DEV\tools\dotnet altına kurar (sistem PATH'i değişmez).
# 2) Oyunun def dosyalarından yol/bina tiplerini listeler (salt okunur).
# 3) Haritayı D:\SAKLAZ_DEV\...\mod\user_map\map\saklaz_city.mbd olarak üretir.
# Ana profil, oyun klasörü ve modlar değiştirilmez.

$ErrorActionPreference = 'Stop'
$repo = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$tools = 'D:\SAKLAZ_DEV\tools'
$dotnet = Join-Path $tools 'dotnet\dotnet.exe'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_NOLOGO = '1'

if (-not (Test-Path $dotnet)) {
    New-Item -ItemType Directory -Force $tools | Out-Null
    $script = Join-Path $tools 'dotnet-install.ps1'
    if (-not (Test-Path $script)) { Invoke-WebRequest -UseBasicParsing 'https://dot.net/v1/dotnet-install.ps1' -OutFile $script }
    $sig = Get-AuthenticodeSignature $script
    if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notlike '*Microsoft Corporation*') { throw "dotnet-install.ps1 imzası doğrulanamadı" }
    & $script -Channel 10.0 -InstallDir (Join-Path $tools 'dotnet') -NoPath
}
& $dotnet --version

Push-Location $repo
try {
    & $dotnet run --project tools\mapgen -c Release -- list
    $export = 'data\processed\map_export_s3.json'
    if (-not (Test-Path $export)) { & .\.venv\Scripts\python.exe -I tools\geo\build_city_export.py --scale 3 }
    & $dotnet run --project tools\mapgen -c Release -- build $export
} finally { Pop-Location }
Write-Host "Bitti. Editörü D:\SAKLAZ_DEV profiliyle açıp 'saklaz_city' haritasını açın, Map > Recompute map, Save."
