"""
Standart Test Matrisi — XAUUSD FVG Engine v10 + Fib Retest
===========================================================
BÖLÜM A: FVG v10 Stratejisi — 3 BİAS × 3 RR = 9 test
BÖLÜM B: Fib 0.618 Retest Stratejisi — 3 BİAS × 3 HEDEF = 9 test

Bias modları:
  • weekly  → weekly_bias.json
  • daily   → daily_bias.json (hindsight)
  • none    → bias yok

FVG v10 RR konfigürasyonları:
  • 1:1        → rr=1.0,  breakeven kapalı
  • 1:2 BE@1R  → rr=2.0,  1R kâra ulaşınca SL entry'ye taşınır
  • 1:2 fix    → rr=2.0,  breakeven kapalı

Fib Retest TP konfigürasyonları:
  • Likidte 2-5R → 2–5R aralığındaki ilk açık 1H FVG kenarı (yoksa 2R)
  • Sabit 2R     → rr=2.0 sabit
  • Sabit 3R     → rr=3.0 sabit

Kullanım: python3 run_test_matrix.py
"""

import io
import contextlib
from pathlib import Path

from xauusd_fvg_engine_v10 import (
    DataEngine, MarketBrain, RiskManager, BacktestEngine,
    PerformanceAnalytics, WeeklyBiasProvider, DailyBiasProvider,
    FibRetestBrain, FibBacktestEngine, LiquidityTargetFinder, SessionFilter,
)

INITIAL_CAPITAL = 10_000

# FVG v10 RR konfigürasyonları — (etiket, rr, breakeven_at_R)
RR_CONFIGS = [
    ('1:1',       1.0, None),
    ('1:2 BE@1R', 2.0, 1.0),
    ('1:2 fix',   2.0, None),
]

# Fib TP konfigürasyonları — (etiket, rr, use_liquidity_tp)
FIB_CONFIGS = [
    ('Lik.2-5R', 2.0, True),   # LiquidityTargetFinder (min 2R fallback)
    ('Sabit 2R', 2.0, False),
    ('Sabit 3R', 3.0, False),
]

BIAS_MODES = ['weekly', 'daily', 'none']


def make_bias(mode, df_1h):
    if mode == 'none':
        return None
    if mode == 'daily':
        if not Path('daily_bias.json').exists():
            DailyBiasProvider.build_from_1h(df_1h, 'daily_bias.json')
        return DailyBiasProvider('daily_bias.json')
    return WeeklyBiasProvider('weekly_bias.json')


def run_one(df_1h, df_5m, bt_start, bias_mode, rr, be):
    """FVG v10: tek konfigürasyon çalıştır."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bias_provider = make_bias(bias_mode, df_1h)
        brain    = MarketBrain(bias_provider=bias_provider)
        risk_mgr = RiskManager(rr=rr, sl_buffer=0.0005)
        engine   = BacktestEngine(brain, risk_mgr,
                                  initial_capital=INITIAL_CAPITAL,
                                  breakeven_at_R=be)
        trades   = engine.run(df_1h, df_5m, bt_start)
        analytics = PerformanceAnalytics(trades, INITIAL_CAPITAL)
        metrics   = analytics.compute()
    return trades, metrics


def run_one_fib(df_1h, df_5m, bt_start, bias_mode, rr, use_liq_tp):
    """Fib Retest: tek konfigürasyon çalıştır."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bias_provider = make_bias(bias_mode, df_1h)
        session       = SessionFilter()
        brain         = FibRetestBrain(bias_provider=bias_provider,
                                       session_filter=session)
        risk_mgr      = RiskManager(rr=rr, sl_buffer=0.0005)
        liq_finder    = LiquidityTargetFinder() if use_liq_tp else None
        engine        = FibBacktestEngine(brain, risk_mgr, liq_finder,
                                          initial_capital=INITIAL_CAPITAL,
                                          breakeven_at_R=None)
        trades        = engine.run(df_1h, df_5m, bt_start)
        analytics     = PerformanceAnalytics(trades, INITIAL_CAPITAL)
        metrics       = analytics.compute()
    return trades, metrics


def _print_row(row):
    pf_str = f"{row['pf']:.2f}" if row['pf'] != float('inf') else "inf"
    print(f"  {row['bias']:<8} {row['rr']:<11} {row['total']:>4} "
          f"{row['wins']:>4} {row['losses']:>5} {row['be']:>3} "
          f"{row['wr']:>6.1f} {row['pnl']:>+11.2f} {row['ret']:>+7.2f} "
          f"{pf_str:>6} {row['sharpe']:>7.2f} {row['maxdd']:>7.2f}")


def _header():
    return (f"\n  {'BİAS':<8} {'RR/TP':<11} {'İŞL':>4} {'WIN':>4} {'LOSS':>5} "
            f"{'BE':>3} {'WR%':>6} {'NetPnL$':>11} {'Ret%':>7} "
            f"{'PF':>6} {'Sharpe':>7} {'MaxDD%':>7}")


def main():
    df_1h, df_5m, bt_start = DataEngine.download(verbose=True)

    # ══════════════════════════════════════════════════════════════════════════
    # BÖLÜM A: FVG v10 — 3×3 = 9 test
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "═" * 78)
    print("  BÖLÜM A — FVG v10 STRATEJİSİ  │  3 BİAS × 3 RR  =  9 TEST")
    print("═" * 78)

    results_a = []
    for bias_mode in BIAS_MODES:
        print(f"\n  ── BİAS: {bias_mode.upper()} " + "─" * 55)
        print(_header())
        print("  " + "─" * 76)
        for rr_label, rr, be in RR_CONFIGS:
            trades, m = run_one(df_1h, df_5m, bt_start, bias_mode, rr, be)
            if m is None:
                print(f"  {bias_mode:<8} {rr_label:<11} "
                      f"{'— tamamlanan işlem yok —':>50}")
                continue
            row = dict(bias=bias_mode, rr=rr_label,
                       total=m['total'], wins=m['wins'], losses=m['losses'],
                       be=m['breakeven'], wr=m['win_rate'] * 100,
                       pnl=m['net_pnl'], ret=m['ret_pct'],
                       pf=m['profit_factor'], sharpe=m['sharpe'],
                       maxdd=m['max_dd'])
            results_a.append(row)
            _print_row(row)

    # ══════════════════════════════════════════════════════════════════════════
    # BÖLÜM B: Fib 0.618 Retest — 3×3 = 9 test
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "═" * 78)
    print("  BÖLÜM B — FİB 0.618 RETEST STRATEJİSİ  │  3 BİAS × 3 HEDEF  =  9 TEST")
    print("  (Seans: London 07-12 UTC / NY 12-21 UTC  |  Giriş: MSB→0.618 retest)")
    print("═" * 78)

    results_b = []
    for bias_mode in BIAS_MODES:
        print(f"\n  ── BİAS: {bias_mode.upper()} " + "─" * 55)
        print(_header())
        print("  " + "─" * 76)
        for tp_label, rr, use_liq in FIB_CONFIGS:
            trades, m = run_one_fib(df_1h, df_5m, bt_start, bias_mode, rr, use_liq)
            if m is None:
                print(f"  {bias_mode:<8} {tp_label:<11} "
                      f"{'— tamamlanan işlem yok —':>50}")
                continue
            row = dict(bias=bias_mode, rr=tp_label,
                       total=m['total'], wins=m['wins'], losses=m['losses'],
                       be=m['breakeven'], wr=m['win_rate'] * 100,
                       pnl=m['net_pnl'], ret=m['ret_pct'],
                       pf=m['profit_factor'], sharpe=m['sharpe'],
                       maxdd=m['max_dd'])
            results_b.append(row)
            _print_row(row)

    # ══════════════════════════════════════════════════════════════════════════
    # ÖZET — Her iki stratejinin en iyileri, Net PnL sıralı
    # ══════════════════════════════════════════════════════════════════════════
    all_results = (
        [dict(strateji='FVG-v10', **r) for r in results_a] +
        [dict(strateji='Fib0618', **r) for r in results_b]
    )

    print("\n" + "═" * 90)
    print("  GENEL ÖZET — Net PnL'e göre sıralı (her iki strateji)")
    print("═" * 90)
    print(f"\n  {'STRATEJİ':<9} {'BİAS':<8} {'RR/TP':<11} {'İŞL':>4} {'WIN':>4} "
          f"{'LOSS':>5} {'BE':>3} {'WR%':>6} {'NetPnL$':>11} {'Ret%':>7} "
          f"{'PF':>6} {'Sharpe':>7} {'MaxDD%':>7}")
    print("  " + "─" * 88)
    for row in sorted(all_results, key=lambda r: r['pnl'], reverse=True):
        pf_str = f"{row['pf']:.2f}" if row['pf'] != float('inf') else "inf"
        print(f"  {row['strateji']:<9} {row['bias']:<8} {row['rr']:<11} {row['total']:>4} "
              f"{row['wins']:>4} {row['losses']:>5} {row['be']:>3} "
              f"{row['wr']:>6.1f} {row['pnl']:>+11.2f} {row['ret']:>+7.2f} "
              f"{pf_str:>6} {row['sharpe']:>7.2f} {row['maxdd']:>7.2f}")
    print("═" * 90)


if __name__ == '__main__':
    main()
