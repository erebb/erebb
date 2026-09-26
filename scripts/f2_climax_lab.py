# -*- coding: utf-8 -*-
"""
F2 KLIMAKS+RET FILTRESI + TERS-MARTINGALE BOYUTLANDIRMA
========================================================
Disaridan gelen bir bot tanimindan (MARK 1.8) iki mekanizma test edilir:

  F2  "klimaks + ret" filtresi — o botta mahkemeyi gecmis ama HENUZ
      dogrulanmamis, golge log ile beklemede olan aday.
  RM  ters-martingale (piramit) boyutlandirma — taban risk %1, seri
      kazanclarda %8 tavana kadar buyuyor, gerceklesmis bakiyeye gore.

F2 TANIMI (bu kodda):
  Klimaks : H1 barinin araligi >= K x ATR14(H1)  (tukenme/asiri hareket)
  Ret     : ayni barda kapanis, hareketin TERSINE geri cekilmis —
            bogaci ret icin kapanis araligin ust %40'inda VE alt fitil
            >= araligin yarisi (dipler reddedildi); ayici ret simetrik.
  Filtre  : giris anindan onceki N H1 barinda, ISLEM YONUNDE bir
            klimaks+ret varsa girise izin ver.

NEDENSELLIK: yalniz giristen ONCE KAPANMIS H1 barlari okunur.
HACIM KULLANILMAZ: 5M verinin %32.6'si sifir hacimli (bkz. vwap_lab),
klimaks tanimi ARALIK tabanli tutuldu.

Kural: IS (<2025-01-11) ve OOS'ta BIRLIKTE iyilesmeyen aday elenir.
RM icin olcut riske-normalize: ayni maks. dususte daha cok para mi?
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from equity import event_equity, risk_for_dd

SPLIT = pd.Timestamp("2025-01-11")
LEDGER = ROOT / "reports" / "conc_ledger_N1.csv"


def h1_klimaks(df1h: pd.DataFrame, K: float):
    """(bogaci_ret, ayici_ret) bool serileri — bar KAPANDIKTAN sonra gecerli."""
    h, l, c, o = df1h.High, df1h.Low, df1h.Close, df1h.Open
    rng = (h - l).replace(0, np.nan)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()],
                   axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    klimaks = rng >= K * atr
    poz = (c - l) / rng                      # kapanisin aralik icindeki yeri
    alt_fitil = (pd.concat([o, c], axis=1).min(axis=1) - l) / rng
    ust_fitil = (h - pd.concat([o, c], axis=1).max(axis=1)) / rng
    boga = klimaks & (poz >= 0.60) & (alt_fitil >= 0.50)
    ayi = klimaks & (poz <= 0.40) & (ust_fitil >= 0.50)
    return boga.shift(1).fillna(False), ayi.shift(1).fillna(False)


def main():
    from gui import _load_data
    d = pd.read_csv(LEDGER, parse_dates=["entry", "exit"])
    df1h, _df5, _ = _load_data()
    df1h = df1h.copy(); df1h.index = pd.to_datetime(df1h.index)
    if getattr(df1h.index, "tz", None) is not None:
        df1h.index = df1h.index.tz_localize(None)
    idx = df1h.index
    d["IS"] = d.entry < SPLIT
    bi, bo = d[d.IS].r.sum(), d[~d.IS].r.sum()
    eb = event_equity(d.sort_values("exit").reset_index(drop=True), 0.01)
    print("BAZ  N=%d IS=%+.1f OOS=%+.1f TOP=%+.1f bakiye=%s$ DD=%.1f%%\n"
          % (len(d), bi, bo, bi + bo,
             format(eb["final"], ",.0f").replace(",", "."), eb["dd"]))

    print("=" * 78)
    print("F2 — KLIMAKS + RET FILTRESI")
    print("=" * 78)
    for K in (1.5, 2.0, 2.5):
        boga, ayi = h1_klimaks(df1h, K)
        for N in (3, 6, 12):
            izin = []
            for t, yon in zip(d.entry, d["dir"]):
                j = idx.searchsorted(np.datetime64(t), side="right")
                a = max(0, j - N)
                s = boga if yon == "bull" else ayi
                izin.append(bool(s.iloc[a:j].any()) if j > a else False)
            m = np.array(izin)
            k = d[m]
            if len(k) < 20:
                print("  K=%.1f  N=%2d bar  ->  N=%3d islem, cok az" % (K, N, len(k)))
                continue
            i, o = k[k.IS].r.sum(), k[~k.IS].r.sum()
            e = event_equity(k.sort_values("exit").reset_index(drop=True), 0.01)
            print("  K=%.1f  N=%2d bar  N=%3d(-%3d) IS=%+6.1f(%+5.1f) "
                  "OOS=%+6.1f(%+5.1f) TOP=%+6.1f(%+5.1f) bakiye=%8s$%s"
                  % (K, N, len(k), len(d) - len(k), i, i - bi, o, o - bo,
                     i + o, i + o - bi - bo,
                     format(e["final"], ",.0f").replace(",", "."),
                     "  <<< KABUL" if (i > bi and o > bo) else ""))
    print()
    print("=" * 78)
    print("RM — TERS-MARTINGALE (piramit) BOYUTLANDIRMA")
    print("=" * 78)
    print("taban %1, her ARDISIK kazancta x carpan, %8 tavan, kayipta tabana don")
    dd_hedef = eb["dd"]
    x = d.sort_values("exit").reset_index(drop=True)
    def rm(carpan, tavan=0.08, taban=0.01):
        bal = 10000.0; f = taban; c = []
        for r in x.r:
            bal += f * bal * r
            c.append(bal)
            f = min(tavan, f * carpan) if r > 0 else taban
        s = pd.Series(c)
        return bal, abs((s / s.cummax() - 1).min()) * 100
    def rm_norm(carpan, hedef):
        lo, hi = 0.001, 0.05
        for _ in range(40):
            m = (lo + hi) / 2
            if rm(carpan, taban=m, tavan=8 * m)[1] > hedef: hi = m
            else: lo = m
        return rm(carpan, taban=lo, tavan=8 * lo), lo
    print("  %-22s %11s %8s %14s" % ("carpan", "bakiye", "DD", "esit-riskte"))
    for carpan in (1.0, 1.25, 1.5, 2.0):
        b, dd = rm(carpan)
        (bn, ddn), f0 = rm_norm(carpan, dd_hedef)
        ad = "yok (sabit %1)" if carpan == 1.0 else "x%.2f" % carpan
        print("  %-22s %10s$ %7.1f%% %13s$  (taban %%%.2f)"
              % (ad, format(b, ",.0f").replace(",", "."), dd,
                 format(bn, ",.0f").replace(",", "."), f0 * 100))
    print("BITTI")


if __name__ == "__main__":
    main()
