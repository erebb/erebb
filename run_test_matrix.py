"""
Standart Test Matrisi — XAUUSD FVG Engine v10
=============================================
BÖLÜM A: FVG v10 Stratejisi           — 3 BİAS × 3 RR = 9 test
BÖLÜM C: Three_vol Doğrudan           — 3 BİAS × 3 RR = 9 test
BÖLÜM G: Harmonik PRZ Only            — 3 BİAS × 3 RR = 9 test

Kullanım: python3 run_test_matrix.py
"""

import io
import contextlib
from pathlib import Path

from xauusd_fvg_engine_v10 import (
    DataEngine, MarketBrain, RiskManager, BacktestEngine,
    PerformanceAnalytics, WeeklyBiasProvider, DailyBiasProvider,
    ThreeVolBrain,
)

INITIAL_CAPITAL = 10_000

# RR konfigürasyonları — (etiket, rr, breakeven_at_R)
RR_CONFIGS = [
    ('1:1',       1.0, None),
    ('1:2 BE@1R', 2.0, 1.0),
    ('1:2 fix',   2.0, None),
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


def run_one(df_1h, df_5m, bt_start, bias_mode, rr, be, poi_mode='all'):
    """FVG v10 / PRZ: tek konfigürasyon çalıştır."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bias_provider = make_bias(bias_mode, df_1h)
        brain    = MarketBrain(bias_provider=bias_provider, poi_mode=poi_mode)
        risk_mgr = RiskManager(rr=rr, sl_buffer=0.0005)
        engine   = BacktestEngine(brain, risk_mgr,
                                  initial_capital=INITIAL_CAPITAL,
                                  breakeven_at_R=be)
        trades   = engine.run(df_1h, df_5m, bt_start)
        analytics = PerformanceAnalytics(trades, INITIAL_CAPITAL)
        metrics   = analytics.compute()
    return trades, metrics


def run_one_threevol(df_1h, df_5m, bt_start, bias_mode, rr, be):
    """Three_vol doğrudan: tek konfigürasyon."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bias_provider = make_bias(bias_mode, df_1h)
        brain    = ThreeVolBrain(bias_provider=bias_provider)
        risk_mgr = RiskManager(rr=rr, sl_buffer=0.0005)
        engine   = BacktestEngine(brain, risk_mgr,
                                  initial_capital=INITIAL_CAPITAL,
                                  breakeven_at_R=be)
        trades   = engine.run(df_1h, df_5m, bt_start)
        analytics = PerformanceAnalytics(trades, INITIAL_CAPITAL)
        metrics   = analytics.compute()
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
                print(f"  {bias_mode:<8} {rr_label:<11} {'— tamamlanan işlem yok —':>50}")
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
    # BÖLÜM C: Three_vol Doğrudan — 3×3 = 9 test
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "═" * 78)
    print("  BÖLÜM C — THREE_VOL DOĞRUDAN  │  3 BİAS × 3 RR  =  9 TEST")
    print("  (Giriş: three_vol onay barında, FVG/POI dokunuşu yok)")
    print("═" * 78)

    results_c = []
    for bias_mode in BIAS_MODES:
        print(f"\n  ── BİAS: {bias_mode.upper()} " + "─" * 55)
        print(_header())
        print("  " + "─" * 76)
        for rr_label, rr, be in RR_CONFIGS:
            trades, m = run_one_threevol(df_1h, df_5m, bt_start, bias_mode, rr, be)
            if m is None:
                print(f"  {bias_mode:<8} {rr_label:<11} {'— tamamlanan işlem yok —':>50}")
                continue
            row = dict(bias=bias_mode, rr=rr_label,
                       total=m['total'], wins=m['wins'], losses=m['losses'],
                       be=m['breakeven'], wr=m['win_rate'] * 100,
                       pnl=m['net_pnl'], ret=m['ret_pct'],
                       pf=m['profit_factor'], sharpe=m['sharpe'],
                       maxdd=m['max_dd'])
            results_c.append(row)
            _print_row(row)

    # ══════════════════════════════════════════════════════════════════════════
    # BÖLÜM G: Harmonik PRZ Only — 3×3 = 9 test
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "═" * 78)
    print("  BÖLÜM G — HARMONİK PRZ ONLY  │  3 BİAS × 3 RR  =  9 TEST")
    print("  (Giriş: 5M harmonik PRZ dokunuşu + 5M MSB, FVG filtresi yok)")
    print("═" * 78)

    results_g = []
    for bias_mode in BIAS_MODES:
        print(f"\n  ── BİAS: {bias_mode.upper()} " + "─" * 55)
        print(_header())
        print("  " + "─" * 76)
        for rr_label, rr, be in RR_CONFIGS:
            trades, m = run_one(df_1h, df_5m, bt_start, bias_mode, rr, be, poi_mode='prz')
            if m is None:
                print(f"  {bias_mode:<8} {rr_label:<11} {'— tamamlanan işlem yok —':>50}")
                continue
            row = dict(bias=bias_mode, rr=rr_label,
                       total=m['total'], wins=m['wins'], losses=m['losses'],
                       be=m['breakeven'], wr=m['win_rate'] * 100,
                       pnl=m['net_pnl'], ret=m['ret_pct'],
                       pf=m['profit_factor'], sharpe=m['sharpe'],
                       maxdd=m['max_dd'])
            results_g.append(row)
            _print_row(row)

    # ══════════════════════════════════════════════════════════════════════════
    # ÖZET — Net PnL'e göre sıralı
    # ══════════════════════════════════════════════════════════════════════════
    all_results = (
        [dict(strateji='FVG-v10',  **r) for r in results_a] +
        [dict(strateji='3VOL-Dir', **r) for r in results_c] +
        [dict(strateji='PRZ-Only', **r) for r in results_g]
    )

    print("\n" + "═" * 90)
    print("  GENEL ÖZET — Net PnL'e göre sıralı")
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
