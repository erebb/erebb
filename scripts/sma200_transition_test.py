# -*- coding: utf-8 -*-
"""
SMA200 GEÇİŞ TESPİTİ — nedensel filtre denemesi
================================================
Tetikleyici bulgu (docs/EXIT_ANALYSIS.md, "TERS aylar"): sistemin SMA200
trend filtresi ayın gerçek yönüyle ters düştüğünde 16 ay boyunca −9.4R;
uyumlu olduğu 37 ayda +143.8R. Yani tüm zarar filtrenin yanıldığı aylardan.

AMA o tablo GERİYE DÖNÜKTÜR — "ayın gerçek yönü" ay bitince bilinir.
Bu script, aynı olguyu CANLIDA kurulabilecek biçimde yakalamayı dener:

  A) SMA200'e uzaklık        — geçiş bölgesinde (fiyat SMA'ya yakın) işlem yok
  B) kesişimden geçen gün    — taze/güvenilmez trendde işlem yok
  C) SMA200 eğimi            — yalnız eğim işlem yönündeyken işle
  D) A/B/C birleşimleri
  E) tersi                   — yalnız SMA200 yakınında işle (ortalamaya dönüş)
  F) nedensel "TERS" tespiti — filtre yönü vs N-günlük gerçekleşmiş momentum
  G) işlem yönü vs momentum

TÜM göstergeler shift(1) ile nedensel; motorun daily_trend'iyle aynı disiplin.
Kural: IS (<2025-01-11) ve OOS'ta BİRLİKTE iyileşmeyen aday elenir.

Kullanım: python3 scripts/sma200_transition_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

SPLIT = pd.Timestamp("2025-01-11")


def features(df_1h: pd.DataFrame) -> pd.DataFrame:
    from xauusd_fvg_engine_v10 import RegimeEngine
    c = RegimeEngine._daily(df_1h)["Close"]
    sma = c.rolling(200).mean()

    f = pd.DataFrame(index=c.index)
    f["dist"] = (c - sma) / c * 100                 # SMA200'e uzaklık %
    f["filt"] = np.sign(c - sma)                    # filtrenin gördüğü yön
    f["slope"] = (sma - sma.shift(20)) / sma * 100  # SMA200 eğimi (20g) %

    # kesişimden geçen gün sayısı
    sign = np.sign(c - sma)
    ages, last = [], None
    for i, flip in enumerate(sign != sign.shift(1)):
        if flip:
            last = i
        ages.append(np.nan if last is None else i - last)
    f["age"] = pd.Series(ages, index=c.index, dtype=float)

    for n in (10, 20, 40):                          # gerçekleşmiş momentum yönü
        f["mom%d" % n] = np.sign(c - c.shift(n))
    return f.shift(1)                               # NEDENSEL


def main() -> None:
    from gui import _load_data

    d = pd.read_csv(ROOT / "reports" / "ay_derin_islemler.csv")
    d = d[d["reason"] != "open"].copy()
    d["entry"] = pd.to_datetime(d["entry"])

    df_1h, _, _ = _load_data()
    f = features(df_1h)
    day = d["entry"].dt.normalize()
    for c in f.columns:
        d[c] = day.map(f[c])

    sgn = np.where(d["dir"] == "bull", 1, -1)
    d["adist"] = d["dist"].abs()
    d["salign"] = d["slope"] * sgn                  # eğim, işlem yönüne göre
    d["IS"] = d["entry"] < SPLIT
    b_is, b_oos = d[d.IS].r.sum(), d[~d.IS].r.sum()
    print("BASE N=%d IS=%+.1f OOS=%+.1f TOP=%+.1f\n"
          % (len(d), b_is, b_oos, b_is + b_oos))

    kabul = []

    def ev(mask, name):
        k = d[mask.fillna(True)]
        i, o = k[k.IS].r.sum(), k[~k.IS].r.sum()
        ok = i > b_is and o > b_oos
        if ok:
            kabul.append((name, i + o))
        print("%-36s N=%3d(-%3d) IS=%+6.1f(%+5.1f) OOS=%+6.1f(%+5.1f) "
              "TOP=%+6.1f(%+5.1f)%s"
              % (name, len(k), len(d) - len(k), i, i - b_is, o, o - b_oos,
                 i + o, i + o - b_is - b_oos, "  <<< KABUL" if ok else ""))

    print("--- A) SMA200 uzaklığı (geçiş bölgesini dışla) ---")
    for t in (0.5, 1.0, 1.5, 2.0, 3.0):
        ev(d.adist >= t, "|uzaklık| >= %.1f%%" % t)
    print("--- B) kesişimden geçen gün (taze trendi dışla) ---")
    for t in (5, 10, 20, 40, 60):
        ev(d.age >= t, "kesişim yaşı >= %d gün" % t)
    print("--- C) SMA200 eğimi işlem yönünde ---")
    for t in (0.0, 0.5, 1.0, 2.0):
        ev(d.salign >= t, "eğim uyumu >= %.1f%%" % t)
    print("--- D) birleşik ---")
    ev((d.adist >= 1.0) & (d.age >= 20), "uzaklık>=1% & yaş>=20g")
    ev((d.salign >= 0) & (d.age >= 20), "eğim uyumlu & yaş>=20g")
    ev((d.adist >= 1.0) & (d.salign >= 0), "uzaklık>=1% & eğim uyumlu")
    print("--- E) tersi: yalnız SMA200 yakınında işle ---")
    for t in (1.0, 2.0, 3.0):
        ev(d.adist <= t, "|uzaklık| <= %.1f%%" % t)
    print("--- F) nedensel TERS tespiti: filtre vs momentum ---")
    for n in (10, 20, 40):
        ev(d["filt"] == d["mom%d" % n], "filtre == %dg momentum (uyumlu al)" % n)
        ev(d["filt"] != d["mom%d" % n], "filtre != %dg momentum (ters al)" % n)
    print("--- G) işlem yönü vs momentum ---")
    for n in (20, 40):
        ev(pd.Series(sgn, index=d.index) == d["mom%d" % n],
           "işlem yönü == %dg momentum" % n)

    print("\n" + "=" * 78)
    if kabul:
        print("KABUL EDILEN ADAYLAR (gercek backtest ile dogrulanmali):")
        for n, v in sorted(kabul, key=lambda t: -t[1]):
            print("   %-36s TOP=%+.1f" % (n, v))
    else:
        print("KABUL EDILEN ADAY YOK — hicbir nedensel filtre IS+OOS'ta")
        print("birlikte iyilestirmedi. 'TERS ay' bulgusu geriye donuk bir")
        print("artefakt; canliya cevrilemiyor.")
    print("BITTI")


if __name__ == "__main__":
    main()
