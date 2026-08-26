# -*- coding: utf-8 -*-
"""
equity.py — portföy özkaynak eğrisi (OLAY TABANLI)
===================================================
Neden ayrı bir modül: raporlar önce bileşiği ÇIKIŞ SIRASINA göre
hesaplıyordu —

    for r in trades.sort_values('exit').r:  bal *= (1 + f*r)

Bu, eş-zamanlı pozisyon varken YANLIŞTIR: bir işlem açıldığında, ondan
sonra kapanacak işlemlerin kârı henüz hesapta yoktur; sıralı yöntem o kârı
peşinen sayıp pozisyonu olduğundan büyük boyutlandırır. Hata eş-zamanlılıkla
büyür (2026-08 ölçümü: ortalama 1.33 pozisyonlu mevcut sistemde %3.9,
limitsiz senaryoda **49 kat**).

Doğrusu: pozisyon GİRİŞ anındaki gerçekleşmiş bakiyeye göre boyutlanır,
kâr/zarar ancak ÇIKIŞ'ta bakiyeye geçer — motorun kendi davranışı da budur.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def event_equity(d: pd.DataFrame, f: float = 0.01,
                 capital: float = 10_000.0) -> dict:
    """Olay tabanlı portföy simülasyonu.

    d: en az `entry`, `exit` (datetime) ve `r` (R cinsinden sonuç) sütunları.
    f: işlem başına risk oranı (0.01 = %1).

    Döner: {'final', 'dd', 'pnl' (işlem sırasına göre dolar PnL dizisi),
            'curve' (DataFrame: t, bal)}
    """
    d = d.reset_index(drop=True)
    ev = []
    for i, r in enumerate(d.itertuples()):
        ev.append((r.entry, 0, i))      # 0 = giriş (boyutlandır)
        ev.append((getattr(r, "exit"), 1, i))   # 1 = çıkış (bakiyeye geç)
    ev.sort(key=lambda t: (t[0], t[1]))

    bal = float(capital)
    risk: dict = {}
    pnl = [0.0] * len(d)
    ts, bs = [], []
    for t, kind, i in ev:
        if kind == 0:
            risk[i] = f * bal           # giriş anındaki bakiyeye göre
        else:
            p = risk.pop(i, 0.0) * float(d["r"].iloc[i])
            bal += p
            pnl[i] = p
            ts.append(t)
            bs.append(bal)
    curve = pd.DataFrame({"t": ts, "bal": bs})
    dd = (abs((curve.bal / curve.bal.cummax() - 1).min()) * 100
          if len(curve) else 0.0)
    return dict(final=bal, dd=float(dd), pnl=pnl, curve=curve)


def risk_for_dd(d: pd.DataFrame, target_dd: float,
                capital: float = 10_000.0) -> float:
    """Maks. düşüşü `target_dd`'ye eşitleyen risk oranını bul (ikili arama).
    Farklı senaryolar ancak AYNI düşüşe getirilerek adil kıyaslanır."""
    lo, hi = 0.0005, 0.08
    for _ in range(45):
        mid = (lo + hi) / 2
        if event_equity(d, mid, capital)["dd"] > target_dd:
            hi = mid
        else:
            lo = mid
    return lo


def required_leverage(d: pd.DataFrame, f: float = 0.01) -> tuple:
    """(ortalama, tepe) gereken kaldıraç — açık pozisyonların toplam
    notional'ı / bakiye. Stop mesafesi dar olan işlem büyük notional
    gerektirir; eş-zamanlılıkta bu toplanır ve finanse edilemez hâle gelir.
    `px` ve `sl` sütunları gerekir; stop mesafesi 0/NaN olan satırlar atlanır.
    """
    if not {"px", "sl"}.issubset(d.columns):
        return (float("nan"), float("nan"))
    x = d.copy()
    x["stopd"] = (x.px - x.sl).abs()
    x = x[(x.stopd > 0) & x.stopd.notna()].reset_index(drop=True)
    if x.empty:
        return (float("nan"), float("nan"))
    x["nx"] = f * x.px / x.stopd            # bakiyenin kaç katı notional
    ev = []
    for i, r in enumerate(x.itertuples()):
        ev.append((r.entry, 1, i))
        ev.append((getattr(r, "exit"), -1, i))
    ev.sort(key=lambda t: (t[0], -t[1]))
    cur = mx = 0.0
    vals = []
    for _t, s, i in ev:
        cur += s * float(x.nx.iloc[i])
        mx = max(mx, cur)
        vals.append(cur)
    return float(np.mean(vals)), float(mx)
