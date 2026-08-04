# -*- coding: utf-8 -*-
"""
BE (breakeven) EŞİK TARAMASI — zarar eden ayları düzeltme denemesi
==================================================================
Gerekçe (reports/AY_DERIN_ANALIZ.html):
  • Kaybeden işlemlerin %62'si stop olmadan ÖNCE +0.5R'ye, %45'i +1.0R'ye gitti.
  • Kazananların MAE'si ortalama 0.42R, kaybedenlerin MFE'si 1.13R.
  → Lehe hareket edip geri dönen işlemleri BE'de kesmek zararı kısabilir.
  DİKKAT: MFE tabanlı kaba simülasyon +61R vaat ediyor ama hedefe gitmeden
  önce geri çekilen KAZANANLARI göremiyor. Gerçek backtest şart — bu script o.

IS = ilk %70 (< 2025-01-11), OOS = son %30. Kural: OOS'ta çürüyen eleme.
Kullanım: python3 scripts/be_sweep.py
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


def trades_for(strat: str) -> pd.DataFrame:
    from gui import _run_strategy
    from xauusd_fvg_engine_v10 import to_naive
    r = _run_strategy(strat, keep_trades=True)[0]
    rows = []
    for t in r.get("_trades", []):
        if t.exit_time is None or t.risk_dollar <= 0:
            continue
        rows.append(dict(entry=to_naive(t.signal.entry_time),
                         exit=to_naive(t.exit_time),
                         r=t.pnl_dollar / t.risk_dollar,
                         reason=getattr(t, "exit_reason", "")))
    return pd.DataFrame(rows)


def summarize(d: pd.DataFrame) -> dict:
    if d.empty:
        return dict(n=0, r=0.0, is_r=0.0, oos_r=0.0, wr=0.0, pf=0.0, be=0)
    isk = d.entry < SPLIT
    g = d[d.r > 0].r.sum()
    b = -d[d.r <= 0].r.sum()
    return dict(n=len(d), r=d.r.sum(), is_r=d[isk].r.sum(), oos_r=d[~isk].r.sum(),
                wr=100 * (d.r > 0).mean(), pf=(g / b if b else np.inf),
                be=int((d.reason == "be").sum()))


def main() -> None:
    from config import get_config
    cfg = get_config()

    # taranacak BE eşikleri; 0 = kapalı (mevcut sistem)
    LEVELS = [0.0, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0]

    orig = {s: cfg.get(s, "be_at_r", default=0) for s in STRATS}
    out: dict[str, dict[float, dict]] = {s: {} for s in STRATS}

    for s in STRATS:
        for lv in LEVELS:
            cfg.set(s, "be_at_r", lv)
            m = summarize(trades_for(s))
            out[s][lv] = m
            print("  %-9s BE@%.1f  N=%3d  IS=%+6.1f OOS=%+6.1f TOP=%+6.1f "
                  "WR=%4.1f%% PF=%.2f be=%d"
                  % (s, lv, m["n"], m["is_r"], m["oos_r"], m["r"], m["wr"],
                     m["pf"], m["be"]), flush=True)
        cfg.set(s, "be_at_r", orig[s])
        print(flush=True)

    print("=" * 78)
    print("SONUC — strateji basina en iyi BE esigi (OOS'ta da iyilesme sarti)")
    print("=" * 78)
    total_base = total_best = 0.0
    for s in STRATS:
        base = out[s][0.0]
        cand = [(lv, m) for lv, m in out[s].items() if lv > 0
                and m["r"] > base["r"] and m["oos_r"] > base["oos_r"]
                and m["is_r"] > base["is_r"]]
        total_base += base["r"]
        if not cand:
            total_best += base["r"]
            print("  %-9s KAPALI kalsin (BE hicbir esikte IS+OOS birlikte "
                  "iyilestirmedi)  base=%+.1fR" % (s, base["r"]))
            continue
        lv, m = max(cand, key=lambda t: t[1]["r"])
        total_best += m["r"]
        print("  %-9s BE@%.1f  %+.1fR -> %+.1fR (%+.1f)  IS %+.1f->%+.1f  "
              "OOS %+.1f->%+.1f" % (s, lv, base["r"], m["r"], m["r"] - base["r"],
                                    base["is_r"], m["is_r"], base["oos_r"],
                                    m["oos_r"]))
    print("-" * 78)
    print("  TOPLAM  %+.1fR -> %+.1fR  (%+.1fR)" % (total_base, total_best,
                                                    total_best - total_base))
    print("BITTI")


if __name__ == "__main__":
    main()
