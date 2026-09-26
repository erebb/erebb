# -*- coding: utf-8 -*-
"""
NY TUZAK (sahte kirilim) ANALIZI
=================================
Kullanicinin bes iddiasi 5 yillik XAUUSD 5M verisiyle olculur:

  1. Gunun en yuksek VEYA en dusuk noktasi 10 gunun ~7'sinde NY seansinda
  2. Piyasa once YANLIS yone kisa hamle yapip (tuzak) sonra gercek yone
     donuyor — NY gunlerinin ~%80'inde
  3. Tuzak genelde seansin ILK 1 SAATINDE (~%90)
  4. Tuzak kucuk (gunluk ortalama hareketin ~%10'u), asil hareket buyuk (~%59)
  5. Tokyo ve Londra ayni yonde ise (haftada ~2.5 gun), NY'de neredeyse her
     zaman (%99) tuzak goruluyor

TANIMLAR (kullanicinin XAU_Atlas penceresi, TR=UTC+3):
  Tokyo 00:00-06:00 UTC (2024-11-05 sonrasi 06:30)
  Londra 07:00-15:30 UTC
  NY 13:30-20:00 UTC

TUZAK TANIMI: NY seansinin NIHAI yonu belirlenir (acilis->kapanis).
Seans icinde, nihai yonun TERSINE gidilen en derin nokta = tuzak derinligi.
Tuzak "var" sayilmasi icin esik taranir (tek esik secmek sonucu istedigimiz
yere ceker).

Kullanim: python3 scripts/ny_trap_lab.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
DST = pd.Timestamp("2024-11-05")


def wilson(k, n):
    if n == 0: return (0.0, 0.0)
    z = 1.959963985; p = k / n; d = 1 + z * z / n
    m = (p + z * z / (2 * n)) / d
    s = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * max(0, m - s), 100 * min(1, m + s))


def main():
    from gui import _load_data
    _d1, df5, _ = _load_data()
    df5 = df5.copy(); df5.index = pd.to_datetime(df5.index)
    if getattr(df5.index, "tz", None) is not None:
        df5.index = df5.index.tz_localize(None)
    df5 = df5[df5.index.dayofweek < 5]
    gun = df5.index.normalize()

    rows = []
    for d, gg in df5.groupby(gun):
        sa = gg.index.hour + gg.index.minute / 60.0
        gh, gl = float(gg.High.max()), float(gg.Low.min())
        grng = gh - gl
        if grng <= 0 or len(gg) < 100: continue
        tok_bit = 6.5 if pd.Timestamp(d) >= DST else 6.0
        r = {"gun": d, "grng": grng}
        # gunun ekstremum zamanlari
        hi_t = float(sa[np.argmax(gg.High.values)])
        lo_t = float(sa[np.argmin(gg.Low.values)])
        r["hi_ny"] = 13.5 <= hi_t < 20.0
        r["lo_ny"] = 13.5 <= lo_t < 20.0
        ok = True
        for ad, (a, b) in (("Tokyo", (0.0, tok_bit)), ("Londra", (7.0, 15.5)),
                           ("NY", (13.5, 20.0))):
            s = gg[(sa >= a) & (sa < b)]
            if len(s) < 12: ok = False; break
            o, c = float(s.Open.iloc[0]), float(s.Close.iloc[-1])
            r[ad + "_yon"] = 1 if c > o else -1
            if ad == "NY":
                yon = r["NY_yon"]
                # nihai yonun TERSINE en derin sapma (tuzak) ve LEHTE en uc
                ters = (o - float(s.Low.min())) if yon == 1 else (float(s.High.max()) - o)
                leh = (float(s.High.max()) - o) if yon == 1 else (o - float(s.Low.min()))
                r["tuzak"] = max(0.0, ters); r["asil"] = max(0.0, leh)
                # tuzagin zamani: ters uc hangi barda?
                arr = s.Low.values if yon == 1 else s.High.values
                j = int(np.argmin(arr)) if yon == 1 else int(np.argmax(arr))
                r["tuzak_saat"] = float((s.index[j] - s.index[0]).total_seconds() / 3600)
        if ok: rows.append(r)
    d = pd.DataFrame(rows)
    n = len(d)
    print("Gün: %d  (%s → %s)\n" % (n, d.gun.iloc[0].date(), d.gun.iloc[-1].date()))

    def rp(ad, k, N, iddia=None):
        lo, hi = wilson(k, N)
        s = "  %-52s %4d/%4d = %%%.1f  [%%%.1f–%%%.1f]" % (ad, k, N, 100*k/N, lo, hi)
        if iddia is not None:
            s += "   iddia %%%.0f → %s" % (iddia, "UYUYOR" if lo <= iddia <= hi else "UYMUYOR")
        print(s)

    print("=" * 100)
    print("İDDİA 1 — günün ekstremumu NY seansında (13:30–20:00)")
    print("=" * 100)
    rp("en az biri (yüksek VEYA düşük) NY'de", int((d.hi_ny | d.lo_ny).sum()), n, 70)
    rp("günün yükseği NY'de", int(d.hi_ny.sum()), n)
    rp("günün düşüğü NY'de", int(d.lo_ny.sum()), n)
    rp("İKİSİ birden NY'de", int((d.hi_ny & d.lo_ny).sum()), n)
    print("  NOT: pencere günün %27.1'i → rastgele 'en az biri' beklentisi ~%47")
    print()

    print("=" * 100)
    print("İDDİA 2+4 — tuzak var mı, ne kadar derin? (eşik taranır)")
    print("=" * 100)
    print("  tuzak = NY nihai yönünün TERSİNE en derin sapma")
    for x in (0.02, 0.05, 0.10, 0.15, 0.20):
        rp("tuzak ≥ %.2f × günlük range" % x, int((d.tuzak >= x * d.grng).sum()), n,
           80 if abs(x - 0.10) < 1e-9 else None)
    print()
    print("  DERİNLİK (günlük range'in yüzdesi olarak):")
    print("    tuzak  medyan %%%.1f  ortalama %%%.1f   (iddia ~%%10)"
          % (100 * (d.tuzak / d.grng).median(), 100 * (d.tuzak / d.grng).mean()))
    print("    asıl   medyan %%%.1f  ortalama %%%.1f   (iddia ~%%59)"
          % (100 * (d.asil / d.grng).median(), 100 * (d.asil / d.grng).mean()))
    print("    oran (asıl/tuzak) medyan %.1fx"
          % (d.asil / d.tuzak.replace(0, np.nan)).median())
    print()

    print("=" * 100)
    print("İDDİA 3 — tuzak seansın ilk 1 saatinde mi?")
    print("=" * 100)
    m = d.tuzak >= 0.05 * d.grng
    sub = d[m]
    for saat in (1.0, 2.0, 3.0):
        rp("tuzak ilk %.0f saatte (tuzak≥%%5 olan %d günde)" % (saat, len(sub)),
           int((sub.tuzak_saat <= saat).sum()), len(sub),
           90 if abs(saat - 1.0) < 1e-9 else None)
    print("  tuzak zamanı medyan %.2f saat (seans başından)" % sub.tuzak_saat.median())
    print()

    print("=" * 100)
    print("İDDİA 5 — Tokyo=Londra günlerinde NY'de tuzak")
    print("=" * 100)
    ayni = d[d.Tokyo_yon == d.Londra_yon]
    farkli = d[d.Tokyo_yon != d.Londra_yon]
    print("  Tokyo=Londra: %d/%d gün (%%%.1f) → haftada %.1f gün"
          % (len(ayni), n, 100*len(ayni)/n, 5*len(ayni)/n))
    print("  iddia: haftada ~2.5 gün → %s"
          % ("UYUYOR" if 2.0 <= 5*len(ayni)/n <= 3.0 else "UYMUYOR"))
    for x in (0.02, 0.05, 0.10):
        a = int((ayni.tuzak >= x * ayni.grng).sum())
        b = int((farkli.tuzak >= x * farkli.grng).sum())
        la, ha = wilson(a, len(ayni)); lb, hb = wilson(b, len(farkli))
        print("  eşik %%%d:  Tokyo=Londra %%%.1f [%%%.1f–%%%.1f]  |  farklı %%%.1f "
              "[%%%.1f–%%%.1f]  → %s"
              % (100*x, 100*a/len(ayni), la, ha, 100*b/len(farkli), lb, hb,
                 "AYRIŞIYOR" if (ha < lb or hb < la) else "örtüşüyor (fark yok)"))
    print("BITTI")


if __name__ == "__main__":
    main()
