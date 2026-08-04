# -*- coding: utf-8 -*-
"""
BE KİLİT SEVİYESİ TARAMASI — tam breakeven'ın yumuşatılmış hâli
================================================================
Tam BE'nin bilinen maliyeti: hedefe gitmeden önce girişe geri çekilen
KAZANANLARI da keser. be_lock_r bu sertliği ayarlanabilir yapar:

    be_at_r  = tetik  (kâr kaç R'ye ulaşınca SL taşınsın)
    be_lock_r= kilit  (SL nereye konsun, R cinsinden)
        0.0  → klasik breakeven (SL = giriş)
       -0.5  → SL hâlâ 0.5R geride: zarar yarılanır, kazanana nefes payı kalır
       +0.5  → 0.5R kâr kilitle (en sert)

Tarama: (tetik, kilit) ızgarası, strateji strateji, IS/OOS ayrı.
Kural: IS ve OOS'ta BİRLİKTE iyileşmeyen aday elenir.
Kullanım: python3 scripts/be_lock_sweep.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

STRATS = ["fvg", "harmonic", "threevol", "fib"]
SPLIT = pd.Timestamp("2025-01-11")

# (tetik, kilit) ızgarası. (0,0) = mekanizma kapalı = referans.
# POZİTİF KİLİTLER TARANMIYOR: tam BE (kilit 0.0) scripts/be_sweep.py'de
# 32 backtestin HEPSİNDE zarar etti (fvg +62.0→+35.8R, harmonic +41.4→+7.3R).
# Kâr kilitleme tam BE'den daha SERT olduğu için mantıken kesin daha kötü.
# Geriye yalnız BE'den YUMUŞAK olan negatif kilitler kalıyor.
GRID = [(0.0, 0.0),
        (1.0, -0.5), (1.5, -0.5), (2.0, -0.5),
        (1.5, -0.75), (2.0, -0.75), (2.5, -0.75)]


def run(strat: str) -> pd.DataFrame:
    from gui import _run_strategy
    from xauusd_fvg_engine_v10 import to_naive
    r = _run_strategy(strat, keep_trades=True)[0]
    rows = []
    for t in r.get("_trades", []):
        if t.exit_time is None or t.risk_dollar <= 0:
            continue
        rows.append(dict(entry=to_naive(t.signal.entry_time),
                         r=t.pnl_dollar / t.risk_dollar,
                         reason=getattr(t, "exit_reason", "")))
    return pd.DataFrame(rows)


def summarize(d: pd.DataFrame) -> dict:
    if d.empty:
        return dict(n=0, r=0.0, is_r=0.0, oos_r=0.0, wr=0.0, pf=0.0)
    isk = d.entry < SPLIT
    g, b = d[d.r > 0].r.sum(), -d[d.r <= 0].r.sum()
    return dict(n=len(d), r=d.r.sum(), is_r=d[isk].r.sum(),
                oos_r=d[~isk].r.sum(), wr=100 * (d.r > 0).mean(),
                pf=(g / b if b else np.inf))


def main() -> None:
    from config import get_config
    cfg = get_config()
    # argv ile alt küme koşulabilir (uzun tarama yarıda kalırsa kalanı sürdür):
    #   python3 scripts/be_lock_sweep.py harmonic threevol fib
    global STRATS
    if len(sys.argv) > 1:
        STRATS = [s for s in sys.argv[1:] if s in STRATS]
    keep = {s: (cfg.get(s, "be_at_r", default=0), cfg.get(s, "be_lock_r", default=0))
            for s in STRATS}
    out: dict[str, dict] = {s: {} for s in STRATS}

    for s in STRATS:
        for trig, lock in GRID:
            cfg.set(s, "be_at_r", trig)
            cfg.set(s, "be_lock_r", lock)
            m = summarize(run(s))
            out[s][(trig, lock)] = m
            tag = "KAPALI     " if trig == 0 else "tetik%.1f kilit%+.2f" % (trig, lock)
            print("  %-9s %-20s N=%3d IS=%+6.1f OOS=%+6.1f TOP=%+6.1f "
                  "WR=%4.1f%% PF=%.2f"
                  % (s, tag, m["n"], m["is_r"], m["oos_r"], m["r"], m["wr"],
                     m["pf"]), flush=True)
        cfg.set(s, "be_at_r", keep[s][0])
        cfg.set(s, "be_lock_r", keep[s][1])
        print(flush=True)

    print("=" * 82)
    print("SONUC — IS ve OOS'ta BIRLIKTE iyilesen adaylar")
    print("=" * 82)
    tb = tn = 0.0
    for s in STRATS:
        base = out[s][(0.0, 0.0)]
        tb += base["r"]
        cand = [(k, m) for k, m in out[s].items() if k != (0.0, 0.0)
                and m["is_r"] > base["is_r"] and m["oos_r"] > base["oos_r"]]
        if not cand:
            tn += base["r"]
            print("  %-9s aday YOK — kapali kalsin (base %+.1fR)" % (s, base["r"]))
            continue
        k, m = max(cand, key=lambda t: t[1]["r"])
        tn += m["r"]
        print("  %-9s tetik %.1fR / kilit %+.2fR : %+.1f -> %+.1f (%+.1f)  "
              "IS %+.1f->%+.1f  OOS %+.1f->%+.1f"
              % (s, k[0], k[1], base["r"], m["r"], m["r"] - base["r"],
                 base["is_r"], m["is_r"], base["oos_r"], m["oos_r"]))
    print("-" * 82)
    print("  TOPLAM %+.1fR -> %+.1fR (%+.1fR)" % (tb, tn, tn - tb))
    print("BITTI")


if __name__ == "__main__":
    main()
