"""Çekirdek büyütme (Gebze–Çayırova–Darıca): oyun koordinatında sürekli radyal çarpıtma.

1:3 ölçekte bu ilçelerin yoğun sokak ağına kavşak prefabları sığmıyor, ağ onlarca parçaya bölünüyordu (2026-11-23).
Merkez C'den R1 içindeki her şey K kat büyütülür (çekirdek ≈ 1:2), dışı radyal olarak (K-1)·R1 kadar dışa kaydırılır
(sürekli, monoton). Tüm projeksiyonlar (yollar, yerler, binalar, arazi, zemin) bu modülden geçer.
Kapatmak için: SAKLAZ_WARP=0.
"""
import math
import os

C = (-915.0, 150.0)   # Gebze (0,0), Çayırova (-1446,-1183), Darıca (-1298,1635) merkezlerinin ortası (1:3 oyun m)
R1 = 2300.0           # büyütülen yarıçap (1:3 oyun m)
K = 1.5               # büyütme: 1:3 → 1:2
ON = os.environ.get("SAKLAZ_WARP", "1") != "0"


def warp(x, z):
    if not ON:
        return x, z
    dx, dz = x - C[0], z - C[1]
    r = math.hypot(dx, dz)
    if r < 1e-9:
        return x, z
    r2 = r * K if r < R1 else r + (K - 1) * R1
    f = r2 / r
    return C[0] + dx * f, C[1] + dz * f


def unwarp(x, z):
    if not ON:
        return x, z
    dx, dz = x - C[0], z - C[1]
    r2 = math.hypot(dx, dz)
    if r2 < 1e-9:
        return x, z
    r = r2 / K if r2 < R1 * K else r2 - (K - 1) * R1
    f = r / r2
    return C[0] + dx * f, C[1] + dz * f


def proj(e, n, E0, N0, S):
    """UTM (e, n) → çarpıtılmış oyun koordinatı (+X doğu, +Z güney)."""
    return warp((e - E0) / S, -(n - N0) / S)
