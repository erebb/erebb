# -*- coding: utf-8 -*-
"""
SEANS ANATOMISI — kullanicinin XAU_Atlas tanimlariyla
======================================================
TR = UTC+3.  Tokyo 03:00-09:00 TR (2024-11-05 sonrasi 09:30) -> 00:00-06:00 UTC
             Londra 10:00-18:30 TR -> 07:00-15:30 UTC
             New York 16:30-23:00 TR -> 13:30-20:00 UTC
             ORTUSME (Londra son + NY ilk) -> 13:30-15:30 UTC

Olculen iddialar:
  1. Medyan range %, gun range payi, ekstremum zaman imzasi (tablo dogrulamasi)
  2. Gunun ekstremumu ORTUSME penceresinde mi olusuyor?
  3. Londra zikzakli mi? (Kaufman verimlilik orani seans bazinda)
  4. NY uzatiyor mu? (NY ilk 1/3 vs son 2/3 hareket)

Hafta sonu ve <12 barli seanslar elenir.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))

DST = pd.Timestamp("2024-11-05")


def seans_pencere(day):
    tok_bit = 6.5 if pd.Timestamp(day) >= DST else 6.0
    return {"Tokyo": (0.0, tok_bit), "Londra": (7.0, 15.5), "NY": (13.5, 20.0)}


def main():
    from gui import _load_data
    _d1, df5, _ = _load_data()
    df5 = df5.copy(); df5.index = pd.to_datetime(df5.index)
    if getattr(df5.index, "tz", None) is not None:
        df5.index = df5.index.tz_localize(None)
    df5 = df5[df5.index.dayofweek < 5]
    saat = df5.index.hour + df5.index.minute / 60.0
    gun = df5.index.normalize()

    rows = []
    for d, gg in df5.groupby(gun):
        sa = gg.index.hour + gg.index.minute / 60.0
        gun_h, gun_l = float(gg.High.max()), float(gg.Low.min())
        gun_rng = gun_h - gun_l
        if gun_rng <= 0 or len(gg) < 100:
            continue
        r = {"gun": d, "gun_rng": gun_rng, "acilis": float(gg.Open.iloc[0])}
        # gunun ekstremumlarinin ZAMANI
        r["hi_t"] = float(sa[np.argmax(gg.High.values)])
        r["lo_t"] = float(sa[np.argmin(gg.Low.values)])
        ok = True
        for ad, (a, b) in seans_pencere(d).items():
            m = (sa >= a) & (sa < b)
            s = gg[m]
            if len(s) < 12:
                ok = False; break
            o, c = float(s.Open.iloc[0]), float(s.Close.iloc[-1])
            h, l = float(s.High.max()), float(s.Low.min())
            r[ad + "_rng"] = h - l
            r[ad + "_rngpct"] = 100 * (h - l) / o
            r[ad + "_pay"] = 100 * (h - l) / gun_rng
            r[ad + "_yon"] = 1 if c > o else -1
            r[ad + "_govde"] = abs(c - o) / (h - l) if h > l else 0.0
            # Kaufman verimlilik: net hareket / toplam yol
            yol = float(s.Close.diff().abs().sum())
            r[ad + "_er"] = abs(c - o) / yol if yol > 0 else 0.0
            # ekstremumun seans icindeki konumu (0=bas, 1=son)
            n = len(s)
            r[ad + "_hi_konum"] = float(np.argmax(s.High.values)) / max(n - 1, 1)
            r[ad + "_lo_konum"] = float(np.argmin(s.Low.values)) / max(n - 1, 1)
        if ok:
            rows.append(r)
    d = pd.DataFrame(rows)
    print("Gün: %d  (%s → %s)\n" % (len(d), d.gun.iloc[0].date(), d.gun.iloc[-1].date()))

    print("=" * 88)
    print("1) TABLO DOĞRULAMASI")
    print("=" * 88)
    print("%-8s %14s %14s %16s %16s" % ("Seans", "medyan rng%", "gün payı%",
                                        "gövde oranı", "verimlilik(ER)"))
    for ad, iddia_r, iddia_p in [("Tokyo", 0.49, 41), ("Londra", 0.97, 79),
                                 ("NY", 0.74, 58)]:
        print("%-8s %13.2f%% %13.1f%% %15.2f %15.2f   (iddia: rng%%%.2f pay%%%d)"
              % (ad, d[ad + "_rngpct"].median(), d[ad + "_pay"].median(),
                 d[ad + "_govde"].median(), d[ad + "_er"].median(),
                 iddia_r, iddia_p))
    print()
    print("EKSTREMUM ZAMAN İMZASI — seans içinde nerede oluşuyor (0=baş, 1=son):")
    for ad in ("Tokyo", "Londra", "NY"):
        hi = d[ad + "_hi_konum"]; lo = d[ad + "_lo_konum"]
        ekst = pd.concat([hi, lo])
        print("  %-8s medyan konum %.2f | ilk 1/3'te %%%.0f | son 1/3'te %%%.0f"
              % (ad, ekst.median(), 100 * (ekst < 1 / 3).mean(),
                 100 * (ekst > 2 / 3).mean()))
    print()

    print("=" * 88)
    print("2) GÜNÜN EKSTREMUMU ÖRTÜŞME PENCERESİNDE Mİ? (13:30–15:30 UTC)")
    print("=" * 88)
    for ad, t in (("Günün YÜKSEĞİ", d.hi_t), ("Günün DÜŞÜĞÜ", d.lo_t)):
        m = (t >= 13.5) & (t < 15.5)
        print("  %-14s örtüşmede %%%.1f   (pencere günün %%%.1f'i → "
              "rastgele beklenen %%%.1f)"
              % (ad, 100 * m.mean(), 100 * 2 / 24, 100 * 2 / 24))
    ikisi = (((d.hi_t >= 13.5) & (d.hi_t < 15.5))
             | ((d.lo_t >= 13.5) & (d.lo_t < 15.5)))
    print("  En az biri örtüşmede: %%%.1f" % (100 * ikisi.mean()))
    print()
    print("  Saat dilimi bazında günün ekstremum yoğunluğu (yüksek+düşük):")
    tt = pd.concat([d.hi_t, d.lo_t])
    kova = pd.cut(tt, [0, 6, 7, 13.5, 15.5, 20, 24],
                  labels=["00-06 Tokyo", "06-07 ara", "07-13:30 Londra",
                          "13:30-15:30 ÖRTÜŞME", "15:30-20 NY", "20-24 kapanış"])
    vc = kova.value_counts().sort_index()
    for k, v in vc.items():
        print("    %-22s %5d  (%%%.1f)" % (k, v, 100 * v / len(tt)))
    print()

    print("=" * 88)
    print("3) LONDRA ZİKZAKLI MI? (verimlilik oranı — 1'e yakın = temiz trend)")
    print("=" * 88)
    for ad in ("Tokyo", "Londra", "NY"):
        er = d[ad + "_er"]
        print("  %-8s medyan ER %.3f | 'temiz' (ER>0.30) gün oranı %%%.1f"
              % (ad, er.median(), 100 * (er > 0.30).mean()))
    print("  → kullanıcı 'temiz Londra ~%30' diyor")
    print()

    print("=" * 88)
    print("4) NY UZATIYOR MU? (Londra yönü NY'de sürüyor mu)")
    print("=" * 88)
    ayni = (d.Londra_yon == d.NY_yon)
    print("  Londra = NY yönü: %%%.1f" % (100 * ayni.mean()))
    tem = d[d.Londra_er > 0.30]
    print("  Londra TEMİZ günlerde (ER>0.30): %%%.1f  (n=%d)"
          % (100 * (tem.Londra_yon == tem.NY_yon).mean(), len(tem)))
    kir = d[d.Londra_er <= 0.30]
    print("  Londra ZİKZAK günlerde:          %%%.1f  (n=%d)"
          % (100 * (kir.Londra_yon == kir.NY_yon).mean(), len(kir)))
    print("BITTI")


if __name__ == "__main__":
    main()
