# Windows varsayılan ses aygıtlarını ayarlar (IPolicyConfig, Windows'un ses ayarları penceresinin kullandığı arayüz).
# Kullanım: powershell -File tools\stream\set_default_audio.ps1 -Playback "Voicemeeter Input" -Comms "Voicemeeter AUX Input"
param(
    [string]$Playback = "Voicemeeter Input",
    [string]$Comms = "Voicemeeter AUX Input"
)
$code = @'
using System;
using System.Runtime.InteropServices;
[Guid("f8679f50-850a-41cf-9c72-430f290290c8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IPolicyConfig {
    int GetMixFormat(); int GetDeviceFormat(); int ResetDeviceFormat(); int SetDeviceFormat();
    int GetProcessingPeriod(); int SetProcessingPeriod(); int GetShareMode(); int SetShareMode();
    int GetPropertyValue(); int SetPropertyValue();
    [PreserveSig] int SetDefaultEndpoint([MarshalAs(UnmanagedType.LPWStr)] string id, int role);
    int SetEndpointVisibility();
}
[ComImport, Guid("870af99c-171d-4f9e-af0d-e63df40c2bc9")] class PolicyConfigClient {}
public static class AudioDefault {
    public static int Set(string id, int role) {
        var pc = (IPolicyConfig)new PolicyConfigClient();
        return pc.SetDefaultEndpoint(id, role);
    }
}
'@
Add-Type -TypeDefinition $code
$base = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render'
function Find-Render([string]$name) {
    foreach ($k in Get-ChildItem $base) {
        if ((Get-ItemProperty $k.PSPath).DeviceState -ne 1) { continue }
        $n = (Get-ItemProperty "$($k.PSPath)\Properties").'{a45c254e-df1c-4efd-8020-67d146a850e0},2'
        if ($n -eq $name) { return "{0.0.0.00000000}.$($k.PSChildName)" }
    }
    throw "Aygıt bulunamadı: $name"
}
$p = Find-Render $Playback
$c = Find-Render $Comms
# rol: 0 = konsol (varsayılan), 1 = multimedya, 2 = iletişim
foreach ($r in 0, 1) { "oynatma rol $r -> $([AudioDefault]::Set($p, $r))" }
"iletişim -> $([AudioDefault]::Set($c, 2))"
