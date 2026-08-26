# -*- coding: utf-8 -*-
"""
ORTUSME PENCERESI + KISA RR TESTI
==================================
Kullanicinin tezi: gunun ekstremumu Londra-NY ortusmesinde (13:30-15:30 UTC)
olusmayi seviyor; Londra zikzakli oldugu icin KISA RR (1:1 gibi) daha mantikli.

Olculen (scripts/dr_session_lab.py): ortusme penceresinde ekstremum yogunlugu
saat basina %8.85 — digerlerinin 2.1-2.4 kati. Tez dogrulandi.

BU TEST: mevcut sistemin girislerini pencereye kisitlayip RR tarar.
blackout_hours ile pencere disi saatler kapatilir (motor saat bazli calisir,
13:30 yerine 13:00 sinirina yuvarlanir - yaklasik ama tutarli).

Kural: IS (<2025-01-11) ve OOS'ta BIRLIKTE iyilesmeyen aday elenir.
Olcut riske-normalize.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from equity import event_equity, risk_for_dd

SPLIT = pd.Timestamp("2025-01-11")
STRATS = ["fvg", "harmonic", "threevol", "fib"]
TUM = list(range(24))


def kosu(saatler, rr):
    """saatler=None -> config'teki blackout; yoksa yalniz o saatlerde giris."""
    from config import get_config
    import gui
    from xauusd_fvg_engine_v10 import to_naive
    cfg = get_config()
    keep = {s: (cfg.get(s, "blackout_hours", default=[]), cfg.get(s, "rr", default="1:5fix"))
            for s in STRATS}
    try:
        for s in STRATS:
            if saatler is not None:
                cfg.set(s, "blackout_hours", [h for h in TUM if h not in saatler])
            if rr is not None:
                cfg.set(s, "rr", rr)
        rows = []
        for s in STRATS:
            r = gui._run_strategy(s, keep_trades=True)[0]
            for t in r.get("_trades", []):
                if t.exit_time is None or t.risk_dollar <= 0:
                    continue
                rows.append(dict(entry=pd.Timestamp(str(to_naive(t.signal.entry_time))[:19]),
                                 exit=pd.Timestamp(str(to_naive(t.exit_time))[:19]),
                                 r=t.pnl_dollar / t.risk_dollar))
    finally:
        for s in STRATS:
            cfg.set(s, "blackout_hours", keep[s][0])
            cfg.set(s, "rr", keep[s][1])
    return pd.DataFrame(rows).sort_values("exit").reset_index(drop=True)


def main():
    b = kosu(None, None)
    bi, bo = b[b.entry < SPLIT].r.sum(), b[b.entry >= SPLIT].r.sum()
    eb = event_equity(b, 0.01)
    nb = event_equity(b, risk_for_dd(b, eb["dd"]))["final"]
    print("BAZ (mevcut, tum saatler, 1:5)  N=%d IS=%+.1f OOS=%+.1f TOP=%+.1f "
          "bakiye=%s$ DD=%.1f%% esit-riskte=%s$\n"
          % (len(b), bi, bo, bi + bo, format(eb["final"], ",.0f").replace(",", "."),
             eb["dd"], format(nb, ",.0f").replace(",", ".")), flush=True)

    PENCERE = {"ortusme 13-16": [13, 14, 15],
               "genis 12-17": [12, 13, 14, 15, 16],
               "NY on 13-18": [13, 14, 15, 16, 17]}
    for pad, saatler in PENCERE.items():
        for rr in ("1:1", "1:1.5", "1:2fix", "1:3fix", "1:5fix"):
            try:
                d = kosu(saatler, rr)
            except Exception as ex:
                print("  %-14s %-7s HATA: %s" % (pad, rr, ex)); continue
            if len(d) < 15:
                print("  %-14s %-7s N=%3d  cok az" % (pad, rr, len(d))); continue
            i, o = d[d.entry < SPLIT].r.sum(), d[d.entry >= SPLIT].r.sum()
            e = event_equity(d, 0.01)
            n = event_equity(d, risk_for_dd(d, eb["dd"]))["final"]
            print("  %-14s %-7s N=%3d IS=%+6.1f OOS=%+6.1f TOP=%+6.1f "
                  "WR=%4.1f%% bakiye=%8s$ DD=%4.1f%% esit-riskte=%8s$ (%+.0f%%)%s"
                  % (pad, rr, len(d), i, o, i + o, 100 * (d.r > 0).mean(),
                     format(e["final"], ",.0f").replace(",", "."), e["dd"],
                     format(n, ",.0f").replace(",", "."), 100 * (n / nb - 1),
                     "  <<< KABUL" if (i > bi and o > bo and n > nb) else ""),
                  flush=True)
        print(flush=True)
    print("BITTI")


if __name__ == "__main__":
    main()
