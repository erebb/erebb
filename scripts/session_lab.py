# -*- coding: utf-8 -*-
"""
SEANS HİZALAMA ANALİZİ — Tokyo / Londra / New York
====================================================
Kullanıcının ileri sürdüğü dört iddia 5 yıllık XAUUSD 5M verisiyle ölçülür:

  1. NY açılışı %30 ihtimalle Tokyo ve Londra ile aynı hizada
  2. Tokyo doğrudan belirleyici değil, teyit edicidir
  3. Londra–NY hizalanması %62
  4. NY seansı gün yönünde ilerlemeden önce %40 ihtimalle ters yöne
     manipülasyon yapar

Seans tanımları (UTC) — forex konvansiyonu:
  Tokyo   00:00–08:00
  Londra  07:00–16:00
  New York 12:00–21:00

Seans yönü = sign(seans_kapanış − seans_açılış).
Hafta sonu ve seansta <12 bar olan günler elenir (veri boşluğu).

Manipülasyon ölçümü: NY seansı içinde, seansın NİHAİ yönünün TERSİNE
önce en az X×ATR'lik hareket yapıldı mı? (X eşiği taranır — tek bir
eşik seçmek sonucu istediğimiz yere çeker.)

Kullanım: python3 scripts/session_lab.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

SEANS = {"Tokyo": (0, 8), "Londra": (7, 16), "NY": (12, 21)}


def wilson(k: int, n: int) -> tuple:
    """%95 Wilson güven aralığı — oranın belirsizliğini gösterir."""
    if n == 0:
        return (0.0, 0.0)
    z = 1.959963985
    p = k / n
    d = 1 + z * z / n
    m = (p + z * z / (2 * n)) / d
    s = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * max(0.0, m - s), 100 * min(1.0, m + s))


def main() -> None:
    from gui import _load_data
    _df1h, df5, _ = _load_data()
    df5 = df5.copy()
    df5.index = pd.to_datetime(df5.index)
    if getattr(df5.index, "tz", None) is not None:
        df5.index = df5.index.tz_localize(None)
    df5 = df5[df5.index.dayofweek < 5]          # hafta sonu yok

    gun = df5.index.normalize()
    saat = df5.index.hour

    # günlük ATR (aralık) — manipülasyon eşiği için ölçek
    g = df5.groupby(gun).agg(H=("High", "max"), L=("Low", "min"))
    atr = (g.H - g.L).rolling(14).mean().shift(1)   # NEDENSEL

    kayit = []
    for d, gg in df5.groupby(gun):
        row = {"gun": d, "atr": float(atr.get(d, np.nan))}
        ok = True
        for ad, (a, b) in SEANS.items():
            m = (gg.index.hour >= a) & (gg.index.hour < b)
            s = gg[m]
            if len(s) < 12:
                ok = False
                break
            row[ad + "_o"] = float(s.Open.iloc[0])
            row[ad + "_c"] = float(s.Close.iloc[-1])
            row[ad + "_h"] = float(s.High.max())
            row[ad + "_l"] = float(s.Low.min())
            row[ad] = 1 if row[ad + "_c"] > row[ad + "_o"] else -1
        if ok:
            kayit.append(row)
    d = pd.DataFrame(kayit).dropna(subset=["atr"])
    print("Gün sayısı: %d  (%s → %s)\n"
          % (len(d), d.gun.iloc[0].date(), d.gun.iloc[-1].date()))

    def rapor(ad: str, k: int, n: int, iddia: float | None = None):
        lo, hi = wilson(k, n)
        s = "%-46s %4d/%4d = %%%.1f   [%%%.1f–%%%.1f]" % (ad, k, n, 100 * k / n,
                                                          lo, hi)
        if iddia is not None:
            icinde = lo <= iddia <= hi
            s += "   iddia %%%.0f → %s" % (iddia,
                                           "UYUYOR" if icinde else "UYMUYOR")
        print(s)

    print("=" * 96)
    print("İDDİA 1 — NY, Tokyo ve Londra ile aynı hizada (üçü de aynı yön)")
    print("=" * 96)
    ucu = ((d.Tokyo == d.Londra) & (d.Londra == d.NY)).sum()
    rapor("üç seans da aynı yön", int(ucu), len(d), 30.0)
    print("   NOT: rastgele olsaydı beklenen %25 (2 bağımsız eşleşme).")
    print()

    print("=" * 96)
    print("İDDİA 3 — Londra ve NY hizalanması")
    print("=" * 96)
    ln = int((d.Londra == d.NY).sum())
    rapor("Londra = NY", ln, len(d), 62.0)
    rapor("Tokyo = Londra", int((d.Tokyo == d.Londra).sum()), len(d))
    rapor("Tokyo = NY", int((d.Tokyo == d.NY).sum()), len(d))
    print()

    print("=" * 96)
    print("İDDİA 2 — Tokyo teyit edici mi? (Tokyo, Londra–NY uyumunu artırıyor mu?)")
    print("=" * 96)
    a = d[d.Tokyo == d.Londra]
    b = d[d.Tokyo != d.Londra]
    ka, kb = int((a.Londra == a.NY).sum()), int((b.Londra == b.NY).sum())
    rapor("Tokyo Londra ile UYUMLU iken  Londra=NY", ka, len(a))
    rapor("Tokyo Londra ile TERS iken    Londra=NY", kb, len(b))
    la, ha = wilson(ka, len(a))
    lb, hb = wilson(kb, len(b))
    print("   → aralıklar %s (örtüşüyorsa Tokyo'nun teyit değeri "
          "istatistiksel olarak GÖSTERİLEMİYOR)"
          % ("ÖRTÜŞÜYOR" if not (ha < lb or hb < la) else "AYRIŞIYOR"))
    print()

    print("=" * 96)
    print("İDDİA 4 — NY, yönüne gitmeden önce ters yöne manipülasyon yapıyor mu?")
    print("=" * 96)
    print("NY seansı içinde, seansın NİHAİ yönünün TERSİNE en az X×ATR hareket:")
    up = d.NY == 1
    ters = np.where(up, d.NY_o - d.NY_l, d.NY_h - d.NY_o)   # ters yöndeki uç
    for x in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30):
        k = int((ters >= x * d.atr).sum())
        rapor("  ters hareket ≥ %.2f×ATR" % x, k, len(d),
              40.0 if abs(x - 0.15) < 1e-9 else None)
    print()
    print("   Karşılaştırma — LEHTE yöndeki uç aynı ölçekte:")
    leh = np.where(up, d.NY_h - d.NY_o, d.NY_o - d.NY_l)
    for x in (0.10, 0.15, 0.20):
        k = int((leh >= x * d.atr).sum())
        rapor("  lehte hareket ≥ %.2f×ATR" % x, k, len(d))
    print("   → ters ve lehte oranlar benzerse 'manipülasyon' değil, "
          "sıradan seans oynaklığıdır.")
    print("BITTI")


if __name__ == "__main__":
    main()
