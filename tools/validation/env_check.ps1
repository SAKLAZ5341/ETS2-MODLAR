<#
.SYNOPSIS
  SAKLAZ Türkiye Map - AŞAMA A: Ortam analizi (SALT OKUNUR).

.DESCRIPTION
  Bu betik HİÇBİR ŞEY KURMAZ, SİLMEZ, DEĞİŞTİRMEZ ve registry'ye YAZMAZ.
  HİÇBİR harici program çalıştırmaz. Python/py/Git dahil tüm sürüm bilgileri
  dosyaların gömülü VersionInfo bilgisinden veya registry'den (salt okuma) alınır.
  Tek yazma işlemi: rapor dosyası ENV_REPORT_<tarih>.md (OutputDir klasörüne).

  PowerShell 5.1 (Windows 10/11 varsayılanı) ile uyumludur.

.PARAMETER EditorTest
  Kullanıcının elle yaptığı gerçek '-edit' açılış testinin sonucu.
  Yapilmadi (varsayılan) | Basarili | Basarisiz
  Betik bu testi KENDİSİ YAPAMAZ; yalnızca sizin bildirdiğiniz sonucu kaydeder.

.PARAMETER EditorTestNote
  Test hakkında kısa not (ör. "editör açıldı, boş harita yüklendi").

.PARAMETER ExtraSearchPath
  SCS Conversion Tools / Blender için ek olarak aranacak klasör(ler).

.PARAMETER OutputDir
  Raporun yazılacağı klasör. Varsayılan: geçerli klasör.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\tools\validation\env_check.ps1

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\tools\validation\env_check.ps1 -EditorTest Basarili -EditorTestNote "Editör açıldı"
#>
[CmdletBinding()]
param(
    [ValidateSet('Yapilmadi', 'Basarili', 'Basarisiz')]
    [string]$EditorTest = 'Yapilmadi',
    [string]$EditorTestNote = '',
    [string[]]$ExtraSearchPath = @(),
    [string]$OutputDir = (Get-Location).Path
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# Çıktı klasörünü işe başlamadan önce doğrula.
if (-not $OutputDir -or -not (Test-Path -LiteralPath $OutputDir -PathType Container)) {
    Write-Host "HATA: Çıktı klasörü bulunamadı: '$OutputDir'. Var olan bir klasör verin (-OutputDir)." -ForegroundColor Red
    exit 1
}

$script:Report = New-Object System.Collections.Generic.List[string]
$script:Errors = New-Object System.Collections.Generic.List[string]
$ETS2_APPID = '227300'
$now = Get-Date

function Add-Line([string]$Line) { $script:Report.Add($Line) }
function Add-Section([string]$Title) { Add-Line ''; Add-Line "## $Title"; Add-Line '' }

# Her bölüm ayrı çalışır; bir bölümdeki hata diğerlerini durdurmaz.
function Invoke-Step([string]$Name, [scriptblock]$Block) {
    try {
        & $Block
    } catch {
        $msg = ($_.Exception.Message -replace '\s*[\r\n]+\s*', ' ').Trim()
        $where = ''
        if ($_.InvocationInfo -and $_.InvocationInfo.ScriptLineNumber) {
            $where = " (satır $($_.InvocationInfo.ScriptLineNumber))"
        }
        $type = $_.Exception.GetType().Name
        Add-Line "- **HATA:** Bu bölüm tamamlanamadı: $msg"
        $script:Errors.Add("[$Name] $type$where : $msg")
    }
}

# Erişim reddi gibi beklenen tarama hatalarını kaydeder, ama durdurmaz.
function Get-ChildItemSafe {
    param([string]$Path, [string]$Filter = '*', [int]$Depth = 0, [switch]$Directory, [switch]$File, [string]$Context = '')
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return @() }
    $errs = $null
    $params = @{ LiteralPath = $Path; Filter = $Filter; ErrorAction = 'SilentlyContinue'; ErrorVariable = 'errs' }
    if ($Depth -gt 0) { $params['Recurse'] = $true; $params['Depth'] = $Depth }
    if ($Directory) { $params['Directory'] = $true }
    if ($File) { $params['File'] = $true }
    $items = @(Get-ChildItem @params)
    if ($errs) {
        $denied = @($errs | Where-Object { $_.Exception -is [System.UnauthorizedAccessException] }).Count
        $other = @($errs).Count - $denied
        if ($denied -gt 0) { $script:Errors.Add("[$Context] '$Path' taranırken $denied klasöre erişim reddedildi (sonuç eksik olabilir).") }
        if ($other -gt 0) { $script:Errors.Add("[$Context] '$Path' taranırken $other başka hata: $(($errs[0].Exception.Message -replace '\s*[\r\n]+\s*', ' '))") }
    }
    return $items
}

function Read-RegValue([string]$Key, [string]$Name) {
    # Yalnızca okuma.
    if (-not (Test-Path -LiteralPath $Key)) { return $null }
    $p = Get-ItemProperty -LiteralPath $Key -ErrorAction SilentlyContinue
    if ($p -and ($p.PSObject.Properties.Name -contains $Name)) { return $p.$Name }
    return $null
}

function Get-UninstallEntry([string]$NamePattern) {
    # Yalnızca okuma: Programlar ve Özellikler kayıtları.
    $roots = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
    )
    $out = @()
    foreach ($r in $roots) {
        if (-not (Test-Path -LiteralPath $r)) { continue }
        foreach ($k in @(Get-ChildItem -LiteralPath $r -ErrorAction SilentlyContinue)) {
            $p = Get-ItemProperty -LiteralPath $k.PSPath -ErrorAction SilentlyContinue
            if (-not $p) { continue }
            $names = $p.PSObject.Properties.Name
            if (-not ($names -contains 'DisplayName')) { continue }
            if ($p.DisplayName -notlike $NamePattern) { continue }
            $ver = ''; $loc = ''
            if ($names -contains 'DisplayVersion') { $ver = $p.DisplayVersion }
            if ($names -contains 'InstallLocation') { $loc = $p.InstallLocation }
            $out += New-Object psobject -Property @{ Name = $p.DisplayName; Version = $ver; Location = $loc }
        }
    }
    return $out
}

function Format-Size([double]$Bytes) { return ('{0:N1} GB' -f ($Bytes / 1GB)) }

# =====================================================================
Add-Line '# SAKLAZ Türkiye Map - Ortam Raporu (Aşama A)'
Add-Line ''
Add-Line '> **GİZLİLİK UYARISI – PAYLAŞMADAN ÖNCE OKUYUN**'
Add-Line '>'
Add-Line '> Bu rapor kişisel bilgi içerebilir: **bilgisayar adı**, **Windows kullanıcı adı**'
Add-Line '> (klasör yollarında), **Steam kullanıcı numarası**, **Steam başlatma seçenekleri**'
Add-Line '> ve **kurulu mod dosya adları**. Raporu GitHub''a yüklemeden veya başkasıyla'
Add-Line '> paylaşmadan önce baştan sona okuyun; istemediğiniz bilgileri silin ya da'
Add-Line '> `<gizlendi>` ile değiştirin. Proje `.gitignore` dosyası `ENV_REPORT_*.md`'
Add-Line '> dosyalarını depoya almaz; bilerek eklemediğiniz sürece yüklenmez.'
Add-Line ''
Add-Line "- Rapor tarihi: $($now.ToString('yyyy-MM-dd HH:mm'))"
Add-Line "- Bilgisayar adı: $env:COMPUTERNAME"
Add-Line "- PowerShell: $($PSVersionTable.PSVersion) ($($PSVersionTable.PSEdition))"
Add-Line "- Betik modu: salt okunur. Yazılan tek dosya bu rapordur."

Invoke-Step 'OS' {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    Add-Line "- İşletim sistemi: $($os.Caption) $($os.Version) ($($os.OSArchitecture))"
}

# ---------------------------------------------------------------- 1. Steam / ETS2
$script:SteamPath = $null
$script:Libraries = @()
$script:EtsDir = $null
$script:Manifest = $null

Add-Section '1. Steam ve ETS 2 kurulumu'
Invoke-Step 'Steam' {
    $sp = Read-RegValue 'HKCU:\Software\Valve\Steam' 'SteamPath'
    if (-not $sp) { $sp = Read-RegValue 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam' 'InstallPath' }
    if (-not $sp) { $sp = Read-RegValue 'HKLM:\SOFTWARE\Valve\Steam' 'InstallPath' }
    if ($sp) { $sp = $sp -replace '/', '\' }
    $script:SteamPath = $sp
    if (-not $sp) {
        Add-Line '- Steam yolu registry''de bulunamadı. (Steam kurulu değil ya da standart dışı kurulum.)'
        return
    }
    Add-Line "- Steam yolu: ``$sp``"
    $libs = @(Join-Path $sp 'steamapps')
    $vdf = Join-Path $sp 'steamapps\libraryfolders.vdf'
    if (Test-Path -LiteralPath $vdf) {
        foreach ($line in (Get-Content -LiteralPath $vdf)) {
            # Join-Path, PS 5.1'de var olmayan sürücüde (ör. çıkarılmış E:) hata fırlatır; .NET Combine fırlatmaz.
            if ($line -match '"path"\s+"(.+)"') { $libs += [System.IO.Path]::Combine(($Matches[1] -replace '\\\\', '\'), 'steamapps') }
        }
    } else {
        Add-Line '- libraryfolders.vdf bulunamadı; yalnızca ana Steam kütüphanesi kontrol edildi.'
    }
    $script:Libraries = @($libs | Select-Object -Unique)
    Add-Line "- Steam kütüphaneleri ($($script:Libraries.Count)):"
    foreach ($l in $script:Libraries) {
        $state = 'erişilemiyor'
        if (Test-Path -LiteralPath $l) { $state = 'var' }
        Add-Line "  - ``$l`` ($state)"
    }
}

Invoke-Step 'ETS2' {
    foreach ($lib in $script:Libraries) {
        $m = [System.IO.Path]::Combine($lib, "appmanifest_$ETS2_APPID.acf")
        if (Test-Path -LiteralPath $m) {
            $script:Manifest = $m
            $mi = Select-String -LiteralPath $m -Pattern '"installdir"\s+"(.+)"' | Select-Object -First 1
            if ($mi) { $script:EtsDir = Join-Path $lib ('common\' + $mi.Matches[0].Groups[1].Value) }
            break
        }
    }
    if (-not $script:Manifest) {
        Add-Line "- ETS 2 Steam kaydı BULUNAMADI (appmanifest_$ETS2_APPID.acf tarandığı kütüphanelerde yok)."
        Add-Line '  Steam dışı veya taşınmış bir kurulum bu betikle tespit edilemez.'
        return
    }
    if ($script:EtsDir -and (Test-Path -LiteralPath $script:EtsDir)) {
        Add-Line "- ETS 2 KURULU: ``$($script:EtsDir)``"
    } else {
        Add-Line "- Steam kaydı var ama oyun klasörü bulunamadı: ``$($script:EtsDir)`` (indirme yarıda kalmış olabilir)."
    }
    foreach ($key in 'buildid', 'BetaKey', 'StateFlags', 'LastUpdated') {
        $hit = Select-String -LiteralPath $script:Manifest -Pattern ('"' + $key + '"\s+"(.*)"') | Select-Object -First 1
        $val = 'tanımsız'
        if ($hit) { $val = $hit.Matches[0].Groups[1].Value }
        if ($key -eq 'BetaKey' -and $val -eq 'tanımsız') { $val = 'yok (public dal)' }
        if ($key -eq 'StateFlags' -and $val -eq '4') { $val = '4 (tam kurulu)' }
        if ($key -eq 'LastUpdated' -and $val -match '^\d+$') {
            $val = ([DateTime]'1970-01-01').AddSeconds([double]$val).ToLocalTime().ToString('yyyy-MM-dd HH:mm')
        }
        Add-Line "- appmanifest ${key}: $val"
    }
}

# ---------------------------------------------------------------- 2. Sürüm
$docs = [Environment]::GetFolderPath('MyDocuments')
if (-not $docs -and $env:USERPROFILE) { $docs = Join-Path $env:USERPROFILE 'Documents' }
if (-not $docs) {
    $docs = ''
    $script:Errors.Add('[Profil] Belgeler (Documents) klasörü belirlenemedi; profil kontrolleri yapılamadı.')
    $profileDir = '(bilinmiyor)'
} else {
    $profileDir = Join-Path $docs 'Euro Truck Simulator 2'
}

Add-Section '2. ETS 2 sürümü'
Invoke-Step 'Sürüm' {
    if (-not $script:EtsDir) { Add-Line '- Oyun klasörü bilinmediği için exe sürümü okunamadı.' }
    else {
        $exe = Join-Path $script:EtsDir 'bin\win_x64\eurotrucks2.exe'
        if (Test-Path -LiteralPath $exe) {
            $vi = (Get-Item -LiteralPath $exe).VersionInfo
            Add-Line "- eurotrucks2.exe dosya sürümü: $($vi.FileVersion) / ürün sürümü: $($vi.ProductVersion)"
        } else { Add-Line "- ``bin\win_x64\eurotrucks2.exe`` bulunamadı." }
    }
    $gameLog = Join-Path $profileDir 'game.log.txt'
    if (Test-Path -LiteralPath $gameLog) {
        $v = Select-String -LiteralPath $gameLog -Pattern 'ver\.\s*[0-9]' | Select-Object -First 1
        $d = (Get-Item -LiteralPath $gameLog).LastWriteTime.ToString('yyyy-MM-dd HH:mm')
        if ($v) { Add-Line "- game.log.txt ($d): ``$($v.Line.Trim())``" }
        else { Add-Line "- game.log.txt ($d) var ama sürüm satırı bulunamadı." }
    } else {
        Add-Line '- game.log.txt yok (oyun bu Windows kullanıcısıyla hiç açılmamış olabilir).'
    }
}

# ---------------------------------------------------------------- 3. DLC
Add-Section '3. DLC ve paketler (oyun klasöründeki .scs dosyaları)'
Invoke-Step 'DLC' {
    if (-not $script:EtsDir -or -not (Test-Path -LiteralPath $script:EtsDir)) { Add-Line '- Oyun klasörü bilinmiyor; DLC listesi çıkarılamadı.'; return }
    $scs = @(Get-ChildItemSafe -Path $script:EtsDir -Filter '*.scs' -File -Context 'DLC' | Sort-Object Name)
    $dlc = @($scs | Where-Object { $_.Name -like 'dlc_*' })
    $base = @($scs | Where-Object { $_.Name -notlike 'dlc_*' })
    Add-Line "- Temel paketler ($($base.Count)): $(($base | ForEach-Object { $_.Name }) -join ', ')"
    Add-Line "- DLC paketleri ($($dlc.Count)):"
    foreach ($x in $dlc) { Add-Line ("  - {0} ({1:N1} MB)" -f $x.Name, ($x.Length / 1MB)) }
    Add-Line '- Not: Steam''de satın alınmış ama devre dışı bırakılmış DLC''ler dosya olarak bulunmayabilir.'
}

# ---------------------------------------------------------------- 4. Map Editor
Add-Section '4. Map Editor erişimi'
Add-Line 'Aşağıdaki üç durum birbirinden BAĞIMSIZDIR ve ayrı değerlendirilir.'
Invoke-Step 'Profil' {
    $state = 'YOK'
    if (Test-Path -LiteralPath $profileDir) { $state = 'var' }
    Add-Line ''
    Add-Line "- Profil klasörü: ``$profileDir`` ($state)"
}

$script:EditorLog = Join-Path $profileDir 'editor.log.txt'
$script:EditorLogItem = $null

Add-Line ''
Add-Line '### 4a. editor.log.txt dosyası mevcut mu?'
Add-Line ''
Invoke-Step 'EditorLog' {
    if (Test-Path -LiteralPath $script:EditorLog) {
        $script:EditorLogItem = Get-Item -LiteralPath $script:EditorLog
        Add-Line ("- **EVET.** Boyut: {0:N0} bayt, son yazma: {1}" -f $script:EditorLogItem.Length, $script:EditorLogItem.LastWriteTime.ToString('yyyy-MM-dd HH:mm'))
        Add-Line '- Bu yalnızca dosyanın varlığını gösterir; tek başına editörün çalıştığını kanıtlamaz.'
    } else {
        Add-Line '- **HAYIR.** `editor.log.txt` profil klasöründe yok.'
    }
}

Add-Line ''
Add-Line '### 4b. Editör geçmişte açılmış mı? (dolaylı kanıtlar)'
Add-Line ''
Invoke-Step 'EditorHistory' {
    $evidence = 0
    if ($script:EditorLogItem -and $script:EditorLogItem.Length -gt 0) {
        $lines = @(Get-Content -LiteralPath $script:EditorLog -TotalCount 5000)
        Add-Line "- editor.log.txt boş değil ($($lines.Count) satır okundu)."
        $evidence++
        $errs = @($lines | Where-Object { $_ -match '<ERROR>' })
        Add-Line "- Logdaki ``<ERROR>`` satırı sayısı: $($errs.Count)"
        foreach ($e in ($errs | Select-Object -Last 5)) { Add-Line "  - ``$($e.Trim())``" }
    } else {
        Add-Line '- editor.log.txt yok veya boş: geçmiş açılışa dair log kanıtı yok.'
    }
    $mapDir = Join-Path $profileDir 'map'
    $mbd = @(Get-ChildItemSafe -Path $mapDir -Filter '*.mbd' -File -Context 'EditorHistory')
    if ($mbd.Count -gt 0) {
        $evidence++
        Add-Line "- Kullanıcı ``map`` klasöründe $($mbd.Count) kayıtlı harita modülü (.mbd): $(($mbd | ForEach-Object { $_.Name }) -join ', ')"
    } else {
        Add-Line '- Kullanıcı `map` klasöründe kayıtlı .mbd harita modülü yok.'
    }
    if ($evidence -gt 0) {
        Add-Line "- **Sonuç: Geçmişte açıldığına dair $evidence dolaylı kanıt var.** Bugün açıldığı anlamına gelmez."
    } else {
        Add-Line '- **Sonuç: Geçmişte açıldığına dair kanıt bulunamadı.** (Kesin değil; loglar silinmiş olabilir.)'
    }
}

Invoke-Step 'LaunchOptions' {
    Add-Line ''
    Add-Line '#### Ayar durumu (açılış kanıtı DEĞİLDİR)'
    Add-Line ''
    $cfg = Join-Path $profileDir 'config.cfg'
    if (Test-Path -LiteralPath $cfg) {
        foreach ($k in 'g_developer', 'g_console') {
            $l = Select-String -LiteralPath $cfg -Pattern ('uset ' + $k + ' ') | Select-Object -First 1
            $v = 'tanımsız'
            if ($l) { $v = $l.Line.Trim() }
            Add-Line "- config.cfg ${k}: ``$v``"
        }
    } else { Add-Line '- config.cfg bulunamadı.' }

    if (-not $script:SteamPath) { Add-Line '- Steam yolu bilinmediği için başlatma seçenekleri okunamadı.'; return }
    $ud = Join-Path $script:SteamPath 'userdata'
    $found = $false
    foreach ($u in @(Get-ChildItemSafe -Path $ud -Directory -Context 'LaunchOptions')) {
        $lc = Join-Path $u.FullName 'config\localconfig.vdf'
        if (-not (Test-Path -LiteralPath $lc)) { continue }
        $txt = [System.IO.File]::ReadAllText($lc)
        $i = $txt.IndexOf('"' + $ETS2_APPID + '"')
        if ($i -lt 0) { continue }
        $found = $true
        $chunk = $txt.Substring($i, [Math]::Min(4000, $txt.Length - $i))
        if ($chunk -match '"LaunchOptions"\s+"([^"]*)"') {
            $opt = $Matches[1]
            $hasEdit = $opt -match '(^|\s)-edit(\s|$)'
            $hasNoWs = $opt -match '(^|\s)-noworkshop(\s|$)'
            Add-Line "- Steam başlatma seçenekleri (Steam kullanıcı $($u.Name)): ``$opt``"
            Add-Line "  - ``-edit`` tanımlı: $(if ($hasEdit) { 'evet' } else { 'hayır' }); ``-noworkshop`` tanımlı: $(if ($hasNoWs) { 'evet' } else { 'hayır' })"
        } else {
            Add-Line "- Steam başlatma seçenekleri (Steam kullanıcı $($u.Name)): tanımsız"
        }
    }
    if (-not $found) { Add-Line '- localconfig.vdf içinde ETS 2 kaydı bulunamadı.' }
    Add-Line '- Not: Masaüstü kısayolundaki parametreler bu betik tarafından okunmaz.'
}

Add-Line ''
Add-Line '### 4c. Kullanıcının gerçek `-edit` açılış testi'
Add-Line ''
Invoke-Step 'EditorTest' {
    switch ($EditorTest) {
        'Yapilmadi' {
            Add-Line '- **YAPILMADI / DOĞRULANMADI.** Bu betik editörü açmaz ve açılabildiğini doğrulayamaz.'
            Add-Line '- Test için: Steam → ETS 2 → Özellikler → Başlatma seçenekleri: `-edit -noworkshop`,'
            Add-Line '  oyunu başlatın, editörün açıldığını görün, kapatın; sonra betiği şöyle yeniden çalıştırın:'
            Add-Line '  `env_check.ps1 -EditorTest Basarili -EditorTestNote "kısa not"` (veya `Basarisiz`).'
        }
        default {
            $label = 'BAŞARISIZ'
            if ($EditorTest -eq 'Basarili') { $label = 'BAŞARILI' }
            Add-Line "- **Kullanıcı beyanı: $label.** (Betik tarafından değil, kullanıcı tarafından bildirildi.)"
            if ($EditorTestNote) { Add-Line "- Not: $EditorTestNote" }
            if ($script:EditorLogItem) {
                $age = ($now - $script:EditorLogItem.LastWriteTime).TotalHours
                if ($age -le 24) { Add-Line ("- Destekleyici kanıt: editor.log.txt son {0:N1} saat içinde yazılmış." -f $age) }
                else { Add-Line ("- **Uyarı:** editor.log.txt en son {0:N0} saat önce yazılmış; beyan edilen testle tutarsız olabilir." -f $age) }
            } else {
                Add-Line '- **Uyarı:** editor.log.txt yok; beyan edilen test log ile desteklenmiyor.'
            }
        }
    }
}

# ---------------------------------------------------------------- 5. Blender
Add-Section '5. Blender'
$script:BlenderDirs = @()
Invoke-Step 'Blender' {
    $searched = @()
    $hits = @()   # psobject: Path, Version, Source

    # a) Program Files (64 ve 32 bit)
    foreach ($pf in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if (-not $pf) { continue }
        $root = Join-Path $pf 'Blender Foundation'
        $searched += $root
        foreach ($d in @(Get-ChildItemSafe -Path $root -Directory -Context 'Blender')) {
            $exe = Join-Path $d.FullName 'blender.exe'
            if (Test-Path -LiteralPath $exe) {
                $hits += New-Object psobject -Property @{ Path = $d.FullName; Version = (Get-Item -LiteralPath $exe).VersionInfo.ProductVersion; Source = 'Program Files' }
            }
        }
    }
    # b) Steam kütüphaneleri
    foreach ($lib in $script:Libraries) {
        $b = [System.IO.Path]::Combine($lib, 'common\Blender')
        $searched += $b
        $exe = [System.IO.Path]::Combine($b, 'blender.exe')
        if (Test-Path -LiteralPath $exe) {
            $hits += New-Object psobject -Property @{ Path = $b; Version = (Get-Item -LiteralPath $exe).VersionInfo.ProductVersion; Source = 'Steam' }
        }
    }
    # c) PATH
    $searched += 'PATH'
    foreach ($c in @(Get-Command -Name 'blender.exe' -All -CommandType Application -ErrorAction SilentlyContinue)) {
        $hits += New-Object psobject -Property @{ Path = (Split-Path -Parent $c.Source); Version = (Get-Item -LiteralPath $c.Source).VersionInfo.ProductVersion; Source = 'PATH' }
    }
    # d) Programlar ve Özellikler kayıtları (yalnızca okuma)
    $searched += 'Programlar ve Özellikler (registry, salt okuma)'
    foreach ($e in @(Get-UninstallEntry 'Blender*')) {
        $hits += New-Object psobject -Property @{ Path = $e.Location; Version = $e.Version; Source = "Kayıt: $($e.Name)" }
    }
    # e) Kullanıcı ek yolları
    foreach ($x in $ExtraSearchPath) {
        $searched += $x
        foreach ($f in @(Get-ChildItemSafe -Path $x -Filter 'blender.exe' -File -Depth 3 -Context 'Blender')) {
            $hits += New-Object psobject -Property @{ Path = $f.DirectoryName; Version = $f.VersionInfo.ProductVersion; Source = 'Ek yol' }
        }
    }

    if ($hits.Count -eq 0) {
        Add-Line '- Taranan konumlarda Blender **bulunamadı**. Bu, Blender''in kesin olarak kurulu olmadığı anlamına GELMEZ'
        Add-Line '  (taşınabilir/zip sürüm, farklı sürücü veya Microsoft Store kurulumu tespit edilemeyebilir).'
        Add-Line '  Başka bir yerdeyse: `-ExtraSearchPath "D:\Araclar"` ile yeniden çalıştırın.'
    } else {
        $seen = @{}
        foreach ($h in $hits) {
            $key = "$($h.Path)|$($h.Version)"
            if ($seen.ContainsKey($key)) { continue }
            $seen[$key] = $true
            if ($h.Path) { $script:BlenderDirs += $h.Path }
            $v = $h.Version
            if (-not $v) { $v = 'sürüm okunamadı' }
            Add-Line "- Blender $v - ``$($h.Path)`` (kaynak: $($h.Source))"
        }
    }
    Add-Line "- Taranan konumlar: $($searched -join '; ')"
}

# ---------------------------------------------------------------- 6. SCS Blender Tools
Add-Section '6. SCS Blender Tools (io_scs_tools)'
Invoke-Step 'BlenderTools' {
    $roots = @()
    $appdata = Join-Path $env:APPDATA 'Blender Foundation\Blender'
    foreach ($v in @(Get-ChildItemSafe -Path $appdata -Directory -Context 'BlenderTools')) {
        $roots += (Join-Path $v.FullName 'scripts\addons')
        $roots += (Join-Path $v.FullName 'extensions')   # Blender 4.2+ eklenti deposu
    }
    foreach ($bd in ($script:BlenderDirs | Select-Object -Unique)) {
        foreach ($v in @(Get-ChildItemSafe -Path $bd -Directory -Context 'BlenderTools')) {
            if ($v.Name -match '^\d+\.\d+$') { $roots += (Join-Path $v.FullName 'scripts\addons') }
        }
    }
    $found = 0
    foreach ($r in ($roots | Select-Object -Unique)) {
        foreach ($h in @(Get-ChildItemSafe -Path $r -Filter 'io_scs_tools' -Directory -Depth 2 -Context 'BlenderTools')) {
            $found++
            $init = Join-Path $h.FullName '__init__.py'
            $ver = 'okunamadı'
            $blv = ''
            if (Test-Path -LiteralPath $init) {
                $m = Select-String -LiteralPath $init -Pattern '"version"\s*:\s*\(([^)]*)\)' | Select-Object -First 1
                if ($m) { $ver = ($m.Matches[0].Groups[1].Value -replace '\s', '') -replace ',', '.' }
                $b = Select-String -LiteralPath $init -Pattern '"blender"\s*:\s*\(([^)]*)\)' | Select-Object -First 1
                if ($b) { $blv = ' / hedef Blender: ' + (($b.Matches[0].Groups[1].Value -replace '\s', '') -replace ',', '.') }
            }
            Add-Line "- Bulundu: ``$($h.FullName)`` (eklenti sürümü: $ver$blv)"
        }
    }
    if ($found -eq 0) {
        Add-Line '- io_scs_tools taranan eklenti klasörlerinde **bulunamadı** (kesin yokluk değildir).'
    }
    Add-Line '- Bilgi: Resmi SCS Blender Tools 2.4.1, Blender 3.2–3.6 için yapılmıştır; 4.x/5.x için yalnızca resmi olmayan topluluk sürümleri vardır.'
    Add-Line '- Eklentinin Blender içinde **etkin** olup olmadığı bu betikle anlaşılamaz.'
}

# ---------------------------------------------------------------- 7. Diğer araçlar
Add-Section '7. Diğer araçlar'
function Get-ToolVersion([string]$Label, [string]$Cmd, [string]$UninstallPattern) {
    # HİÇBİR harici program çalıştırılmaz. Get-Command yalnızca PATH'te dosyayı bulur;
    # sürüm, dosyanın gömülü VersionInfo bilgisinden okunur.
    $cmds = @(Get-Command -Name $Cmd -CommandType Application -All -ErrorAction SilentlyContinue)
    if ($cmds.Count -eq 0) {
        Add-Line "- ${Label}: PATH'te **bulunamadı** (başka konumda kurulu olabilir)."
    }
    $i = 0
    foreach ($c in $cmds) {
        $i++
        $tag = ''
        if ($i -eq 1) { $tag = ' [PATH''te ilk sırada - komut satırında kullanılacak olan]' }
        $note = ''
        if ($c.Source -like '*\WindowsApps\*') { $note = ' (Microsoft Store yönlendirme kısayolu olabilir)' }
        $ver = $null
        $reason = ''
        try {
            $vi = (Get-Item -LiteralPath $c.Source -ErrorAction Stop).VersionInfo
            if ($vi) {
                if ($vi.ProductVersion) { $ver = $vi.ProductVersion.Trim() }
                elseif ($vi.FileVersion) { $ver = $vi.FileVersion.Trim() }
            }
            if (-not $ver) { $reason = 'dosyada gömülü sürüm bilgisi yok' }
        } catch {
            $reason = 'dosya okunamadı: ' + (($_.Exception.Message -replace '\s*[\r\n]+\s*', ' ').Trim())
        }
        if ($ver) {
            Add-Line "- ${Label}: VAR - dosya sürümü $ver - ``$($c.Source)``$note$tag"
        } else {
            Add-Line "- ${Label}: VAR - **sürüm bilgisi alınamadı** ($reason) - ``$($c.Source)``$note$tag"
        }
    }
    if ($UninstallPattern) {
        $reg = @(Get-UninstallEntry $UninstallPattern)
        foreach ($e in $reg) {
            $v = $e.Version
            if (-not $v) { $v = 'sürüm kayıtlı değil' }
            Add-Line "  - Programlar kaydı: $($e.Name) - $v"
        }
    }
}
Invoke-Step 'Python' { Get-ToolVersion 'Python' 'python.exe' 'Python 3*'; Get-ToolVersion 'Python Launcher (py)' 'py.exe' '' }
Invoke-Step 'Git' { Get-ToolVersion 'Git' 'git.exe' 'Git*' }
Invoke-Step 'QGIS' {
    $q = @()
    foreach ($pf in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if ($pf) { $q += @(Get-ChildItemSafe -Path $pf -Filter 'QGIS*' -Directory -Context 'QGIS' | ForEach-Object { $_.FullName }) }
    }
    $q += @(Get-UninstallEntry 'QGIS*' | ForEach-Object { "$($_.Name) $($_.Version)" })
    if ($q.Count -gt 0) { Add-Line "- QGIS: $(($q | Select-Object -Unique) -join '; ')" }
    else { Add-Line '- QGIS: Program Files ve Programlar kayıtlarında **bulunamadı** (OSGeo4W gibi başka kurulumlar tespit edilemeyebilir).' }
}

Invoke-Step 'ConversionTools' {
    # Geniş C:\ taraması YOK. Yalnızca bilinen, sınırlı konumlar.
    $places = @(
        @{ P = (Join-Path $env:USERPROFILE 'Desktop'); D = 2 },
        @{ P = (Join-Path $env:USERPROFILE 'Downloads'); D = 2 },
        @{ P = $docs; D = 2 },
        @{ P = 'C:\SCS'; D = 2 },
        @{ P = 'C:\Tools'; D = 2 },
        @{ P = 'C:\Modding'; D = 2 }
    )
    foreach ($x in $ExtraSearchPath) { $places += @{ P = $x; D = 3 } }
    $hits = @()
    $searched = @()
    foreach ($pl in $places) {
        if (-not $pl.P -or -not (Test-Path -LiteralPath $pl.P)) { continue }
        $searched += "$($pl.P) (derinlik $($pl.D))"
        $hits += @(Get-ChildItemSafe -Path $pl.P -Filter '*conversion_tools*' -Directory -Depth $pl.D -Context 'ConversionTools' | ForEach-Object { $_.FullName })
        $hits += @(Get-ChildItemSafe -Path $pl.P -Filter 'converter_pix.exe' -File -Depth $pl.D -Context 'ConversionTools' | ForEach-Object { $_.FullName })
    }
    if ($hits.Count -gt 0) {
        Add-Line '- SCS Conversion Tools / ConverterPIX adayları:'
        foreach ($h in ($hits | Select-Object -Unique)) { Add-Line "  - ``$h``" }
    } else {
        Add-Line '- SCS Conversion Tools: sınırlı konumlarda **bulunamadı** (kesin yokluk değildir).'
        Add-Line '  Başka bir klasördeyse: `-ExtraSearchPath "D:\SCS"` ile yeniden çalıştırın.'
    }
    $s = '(hiçbiri mevcut değil)'
    if ($searched.Count -gt 0) { $s = $searched -join '; ' }
    Add-Line "- Taranan konumlar: $s"
}

Invoke-Step 'Donanım' {
    $gpu = @(Get-CimInstance -ClassName Win32_VideoController | ForEach-Object { $_.Name })
    Add-Line "- Ekran kartı: $($gpu -join ', ')"
    $cs = Get-CimInstance -ClassName Win32_ComputerSystem
    Add-Line "- RAM: $(Format-Size $cs.TotalPhysicalMemory)"
}

Invoke-Step 'Mods' {
    $modDir = Join-Path $profileDir 'mod'
    if (-not (Test-Path -LiteralPath $modDir)) { Add-Line '- Yerel mod klasörü yok.'; return }
    $mods = @(Get-ChildItemSafe -Path $modDir -File -Context 'Mods')
    Add-Line "- Yerel mod klasörü: $($mods.Count) dosya (adlar paylaşım öncesi kontrol edilmeli):"
    foreach ($m in $mods) { Add-Line "  - $($m.Name)" }
}

# ---------------------------------------------------------------- 8. Disk
Add-Section '8. Disk alanı'
Invoke-Step 'Disk' {
    $disks = @(Get-CimInstance -ClassName Win32_LogicalDisk -Filter 'DriveType=3')
    if ($disks.Count -eq 0) { Add-Line '- Yerel disk bilgisi alınamadı.'; return }
    foreach ($d in $disks) {
        Add-Line "- $($d.DeviceID) boş $(Format-Size $d.FreeSpace) / toplam $(Format-Size $d.Size)"
    }
    if ($script:EtsDir) {
        $drive = (Split-Path -Qualifier $script:EtsDir)
        Add-Line "- ETS 2'nin bulunduğu sürücü: $drive"
    }
}

# ---------------------------------------------------------------- Hatalar
Add-Section '9. Betik hataları ve eksik taramalar'
if ($script:Errors.Count -eq 0) {
    Add-Line '- Hata kaydedilmedi.'
} else {
    foreach ($e in $script:Errors) { Add-Line "- $e" }
}

# ---------------------------------------------------------------- Yazma
try {
    $out = Join-Path $OutputDir ('ENV_REPORT_{0}.md' -f $now.ToString('yyyyMMdd_HHmmss'))
    if (Test-Path -LiteralPath $out) { throw "Rapor dosyası zaten var, üzerine yazılmadı: $out" }
    $script:Report | Out-File -LiteralPath $out -Encoding utf8
    Write-Host "Rapor yazıldı: $out"
    Write-Host 'Paylaşmadan önce raporun başındaki gizlilik uyarısını okuyun.'
} catch {
    Write-Host "HATA: Rapor yazılamadı: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
