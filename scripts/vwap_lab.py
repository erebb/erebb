# -*- coding: utf-8 -*-
"""
VWAP LABORATUVARI — dört çapa (saatlik / günlük / haftalık / aylık)
====================================================================
TEST AMAÇLIDIR. Motor ve config'e dokunulmaz; defter üzerinde tarama yapar.

VWAP = Σ(tipik_fiyat × hacim) / Σ(hacim), çapa noktasında sıfırlanır.
Tipik fiyat = (H+L+C)/3. Sapma z = (fiyat − VWAP) / σ_VWAP.
z_al = z × yön  → long'da VWAP üstü +, short'ta VWAP altı + (yön-göreli).

NEDENSELLİK: VWAP, σ ve fiyat hepsi shift(1) — giriş barının kendisi
kullanılmaz. Bar kapanmadan o barın VWAP'ı bilinemez.

HACİM UYARISI: 5M veride barların %32.6'sı SIFIR hacimli (hafta sonu ve
seans kapanışlarındaki doldurulmuş barlar). Bu barlar VWAP birikimine
katılmaz (0 × fiyat = 0, paydaya da 0 eklenir). İlk sürümde sıfırlar 1.0
yapılmıştı; bu VWAP'ı kısmen basit ortalamaya çeviriyor ve ayırt gücünü
YAPAY olarak 0.145'ten 0.308'e şişiriyordu.

Kural: IS (<2025-01-11) ve OOS'ta BİRLİKTE iyileşmeyen aday elenir.
Tarama TÜM işlemler üzerinde yapılır (örneklem yok).

Kullanım: python3 scripts/vwap_lab.py
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
LEDGER = ROOT / "reports" / "conc_ledger_N1.csv"


def anchors(idx: pd.DatetimeIndex) -> dict:
    """Çapa anahtarları — her birinde VWAP sıfırlanır."""
    iso = idx.isocalendar()
    return {
        "saatlik": idx.floor("h"),
        "günlük": idx.normalize(),
        "haftalık": pd.Index(iso.year.astype(str) + "-W"
                             + iso.week.astype(int).astype(str).str.zfill(2)),
        "aylık": idx.to_period("M").astype(str),
    }


def vwap_z(df5: pd.DataFrame, key) -> tuple:
    """(z serisi, VWAP serisi) — ikisi de shift(1) ile nedensel."""
    tp = (df5.High + df5.Low + df5.Close) / 3.0
    vol = df5.Volume.astype(float)          # sıfır hacim birikime katılmaz
    g = pd.Series(key, index=df5.index)
    pv = (tp * vol).groupby(g).cumsum()
    cv = vol.groupby(g).cumsum().replace(0, np.nan)
    vw = pv / cv
    var = ((tp - vw) ** 2 * vol).groupby(g).cumsum() / cv
    sd = np.sqrt(var)
    z = (df5.Close - vw) / sd.replace(0, np.nan)
    return z.shift(1), vw.shift(1)


def main() -> None:
    from gui import _load_data

    d = pd.read_csv(LEDGER, parse_dates=["entry", "exit"])
    _df1h, df5, _ = _load_data()
    df5 = df5.copy()
    df5.index = pd.to_datetime(df5.index)
    if getattr(df5.index, "tz", None) is not None:
        df5.index = df5.index.tz_localize(None)

    nz = int((df5.Volume == 0).sum())
    print("5M veri: %d bar | sıfır hacimli: %d (%%%.1f) — VWAP birikimine "
          "KATILMAZ" % (len(df5), nz, 100 * nz / len(df5)))
    print("Defter: %d işlem — tarama TÜMÜ üzerinde\n" % len(d))

    idx = df5.index
    sgn = np.where(d["dir"] == "bull", 1, -1)
    d["IS"] = d.entry < SPLIT
    bi, bo = d[d.IS].r.sum(), d[~d.IS].r.sum()
    print("BAZ  N=%d  IS=%+.1f  OOS=%+.1f  TOP=%+.1f\n" % (len(d), bi, bo, bi + bo))

    def at(s, t):
        i = idx.searchsorted(np.datetime64(t), side="right") - 1
        return float(s.iloc[i]) if 0 <= i < len(s) else np.nan

    A = anchors(idx)
    ozet = []
    for ad, key in A.items():
        z, _vw = vwap_z(df5, key)
        zz = np.array([at(z, t) for t in d.entry])
        za = zz * sgn
        ok = ~np.isnan(za)
        W = za[ok & (d.r.values > 0)]
        L = za[ok & (d.r.values <= 0)]
        sp = np.sqrt((W.var() + L.var()) / 2)
        dcoh = (W.mean() - L.mean()) / sp if sp else np.nan
        print("=== %s çapa ===" % ad.upper())
        print("  geçerli %d/%d | kazanan z_al %.3f | kaybeden z_al %.3f | "
              "Cohen d %+.3f" % (ok.sum(), len(d), W.mean(), L.mean(), dcoh))
        print("  VWAP ile uyumlu (z_al>0): %d/%d (%%%.0f)"
              % ((za[ok] > 0).sum(), ok.sum(), 100 * (za[ok] > 0).mean()))
        best = None
        for etiket, m in ([("z_al >= %.1f" % t, ok & (za >= t))
                           for t in (0.0, 0.5, 1.0, 1.5)]
                          + [("z_al <= %.1f" % t, ok & (za <= t))
                             for t in (0.0, -0.5)]
                          + [("|z| <= %.1f" % t, ok & (np.abs(zz) <= t))
                             for t in (1.0, 2.0, 3.0)]
                          + [("|z| >= %.1f" % t, ok & (np.abs(zz) >= t))
                             for t in (0.5, 1.0)]):
            k = d[m]
            if len(k) < 20:
                print("    %-14s N=%3d  çok az" % (etiket, len(k)))
                continue
            i, o = k[k.IS].r.sum(), k[~k.IS].r.sum()
            gecti = i > bi and o > bo
            if best is None or (i + o) > best[1]:
                best = (etiket, i + o)
            print("    %-14s N=%3d IS=%+6.1f(%+5.1f) OOS=%+6.1f(%+5.1f) "
                  "TOP=%+6.1f(%+5.1f)%s"
                  % (etiket, len(k), i, i - bi, o, o - bo, i + o,
                     i + o - bi - bo, "  <<< KABUL" if gecti else ""))
        ozet.append((ad, dcoh, best))
        print()

    print("=" * 74)
    print("ÖZET — çapa başına ayırt gücü ve en iyi filtre")
    print("=" * 74)
    for ad, dc, b in ozet:
        print("  %-9s Cohen d %+.3f   en iyi: %-14s TOP=%+.1f (baz %+.1f)"
              % (ad, dc, b[0] if b else "-", b[1] if b else 0, bi + bo))
    print("BITTI")


if __name__ == "__main__":
    main()
