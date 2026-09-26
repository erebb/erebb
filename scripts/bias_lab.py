# -*- coding: utf-8 -*-
"""
BIAS LABORATUVARI — yön filtresi varyantları
=============================================
TEST AMAÇLIDIR. Config bellekte değiştirilir ve her koşudan sonra geri alınır;
config/default.json diske YAZILMAZ.

Sistemde dört bias modu var (xauusd_fvg_engine_v10.py):
  none     — bias yok (mevcut ayar, tüm stratejilerde)
  daily    — daily_bias.json'dan GÜNLÜK yön; dosya yoksa 1H'den türetilir
  weekly   — weekly_bias.json'dan HAFTALIK yön (elle doldurulur)
  private  — GARCH-benzeri otomatik rejim tespiti (EWMA varyans + EMA 21/55),
             saf numpy, lookahead yok

Bias, sinyalin yönüyle uyuşmuyorsa girişi eler — yani günlük SMA200 trend
kapısının ÜSTÜNE ikinci bir yön filtresi koyar. Sistem zaten trend kapısı
kullandığı için bu ek katmanın kazanç getirip getirmediği ölçülmeli.

Kural: IS (<2025-01-11) ve OOS'ta BİRLİKTE iyileşmeyen aday elenir.
Ölçüm olay tabanlı bileşik (scripts/equity.py).

NOT: 'daily' modu daily_bias.json dosyasını üretebilir (türetilmiş veri).
'weekly' dosyası elle doldurulmadıysa bias hep None döner → 'none' ile
aynı sonucu verir; bu beklenen davranıştır ve raporda görünür.

Kullanım: python3 scripts/bias_lab.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

STRATS = ["fvg", "harmonic", "threevol", "fib"]
MODES = ["none", "daily", "weekly", "private"]
SPLIT = pd.Timestamp("2025-01-11")
BASE_TOP = 134.4


def run_one(strat: str, mode: str) -> pd.DataFrame:
    from config import get_config
    cfg = get_config()
    keep = cfg.get(strat, "bias", default="none")
    cfg.set(strat, "bias", mode)
    try:
        import gui
        r = gui._run_strategy(strat, keep_trades=True)[0]
        rows = []
        for t in r.get("_trades", []):
            if t.exit_time is None or t.risk_dollar <= 0:
                continue
            e = pd.Timestamp(str(t.signal.entry_time)[:19])
            x = pd.Timestamp(str(t.exit_time)[:19])
            rows.append(dict(entry=e, exit=x, r=t.pnl_dollar / t.risk_dollar,
                             reason=getattr(t, "exit_reason", "")))
    finally:
        cfg.set(strat, "bias", keep)
    return pd.DataFrame(rows)


def stat(d: pd.DataFrame) -> dict:
    if d.empty:
        return dict(n=0, r=0.0, is_r=0.0, oos_r=0.0, wr=0.0)
    isk = d.entry < SPLIT
    return dict(n=len(d), r=d.r.sum(), is_r=d[isk].r.sum(),
                oos_r=d[~isk].r.sum(), wr=100 * (d.r > 0).mean())


def main() -> None:
    from equity import event_equity

    res: dict = {}
    for s in STRATS:
        for m in MODES:
            d = run_one(s, m)
            res[(s, m)] = (stat(d), d)
            k = res[(s, m)][0]
            print("  %-9s bias=%-8s N=%3d IS=%+6.1f OOS=%+6.1f TOP=%+6.1f "
                  "WR=%4.1f%%" % (s, m, k["n"], k["is_r"], k["oos_r"],
                                  k["r"], k["wr"]), flush=True)
        print(flush=True)

    print("=" * 78)
    print("STRATEJI BASINA EN IYI BIAS (IS+OOS birlikte iyilesme sarti)")
    print("=" * 78)
    best = {}
    tot_base = tot_new = 0.0
    for s in STRATS:
        b = res[(s, "none")][0]
        tot_base += b["r"]
        cand = [(m, res[(s, m)][0]) for m in MODES if m != "none"
                and res[(s, m)][0]["is_r"] > b["is_r"]
                and res[(s, m)][0]["oos_r"] > b["oos_r"]]
        if not cand:
            best[s] = "none"
            tot_new += b["r"]
            print("  %-9s none kalsin — hicbir bias IS+OOS'ta iyilestirmedi "
                  "(base %+.1fR)" % (s, b["r"]))
            continue
        m, k = max(cand, key=lambda t: t[1]["r"])
        best[s] = m
        tot_new += k["r"]
        print("  %-9s %-8s %+.1f -> %+.1f (%+.1f)  IS %+.1f->%+.1f  "
              "OOS %+.1f->%+.1f" % (s, m, b["r"], k["r"], k["r"] - b["r"],
                                    b["is_r"], k["is_r"], b["oos_r"],
                                    k["oos_r"]))
    print("-" * 78)
    print("  TOPLAM %+.1fR -> %+.1fR (%+.1fR)" % (tot_base, tot_new,
                                                  tot_new - tot_base))

    # portföy: en iyi bias kombinasyonu, olay tabanlı bileşik
    print()
    for label, pick in (("mevcut (hepsi none)", {s: "none" for s in STRATS}),
                        ("en iyi bias kombinasyonu", best)):
        d = pd.concat([res[(s, pick[s])][1] for s in STRATS])
        d = d.sort_values("exit").reset_index(drop=True)
        e = event_equity(d, 0.01)
        isk = d.entry < SPLIT
        print("  %-26s N=%3d IS=%+6.1f OOS=%+6.1f TOP=%+6.1f bakiye=%s$ "
              "DD=%.1f%%" % (label, len(d), d[isk].r.sum(), d[~isk].r.sum(),
                             d.r.sum(),
                             format(e["final"], ",.0f").replace(",", "."),
                             e["dd"]))
    print("BITTI")


if __name__ == "__main__":
    main()
