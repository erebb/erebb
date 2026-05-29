"""
Standart Test Matrisi — XAUUSD FVG Engine v10
==============================================
3 BİAS MODU × 3 RR KONFİGÜRASYONU = 9 test.

Bias modları:
  • weekly  → weekly_bias.json (haftalık bias)
  • daily   → daily_bias.json   (günlük bias — hindsight içerir)
  • none    → bias yok (her iki yön serbest)

RR konfigürasyonları:
  • 1:1        → rr=1.0,  breakeven kapalı
  • 1:2 BE@1R  → rr=2.0,  1R kâra ulaşınca SL entry'ye taşınır
  • 1:2 fix    → rr=2.0,  breakeven kapalı (sabit 1:2)

Her test için: işlem sayısı, WIN/LOSS/BE, WR (BE hariç), net PnL,
getiri %, profit factor, Sharpe, MaxDD.

Kullanım: python3 run_test_matrix.py
"""

import io
import contextlib
from pathlib import Path

from xauusd_fvg_engine_v10 import (
    DataEngine, MarketBrain, RiskManager, BacktestEngine,
    PerformanceAnalytics, WeeklyBiasProvider, DailyBiasProvider,
)

INITIAL_CAPITAL = 10_000

# (etiket, rr, breakeven_at_R)
RR_CONFIGS = [
    ('1:1',       1.0, None),
    ('1:2 BE@1R', 2.0, 1.0),
    ('1:2 fix',   2.0, None),
]

# (etiket, mod)
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
    """Tek bir konfigürasyon çalıştır; metrik dict döndür (sessiz)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bias_provider = make_bias(bias_mode, df_1h)
        brain    = MarketBrain(bias_provider=bias_provider)
        risk_mgr = RiskManager(rr=rr, sl_buffer=0.0005)
        engine   = BacktestEngine(brain, risk_mgr,
                                  initial_capital=INITIAL_CAPITAL,
                                  breakeven_at_R=be)
        trades = engine.run(df_1h, df_5m, bt_start)
        analytics = PerformanceAnalytics(trades, INITIAL_CAPITAL)
        metrics   = analytics.compute()
    return trades, metrics


def main():
    # Veri bir kez indir
    df_1h, df_5m, bt_start = DataEngine.download(verbose=True)

    print("\n" + "═" * 78)
    print("  STANDART TEST MATRİSİ  │  3 BİAS × 3 RR  =  9 TEST")
    print("═" * 78)

    header = (f"\n  {'BİAS':<8} {'RR':<11} {'İŞL':>4} {'WIN':>4} {'LOSS':>5} "
              f"{'BE':>3} {'WR%':>6} {'NetPnL$':>11} {'Ret%':>7} "
              f"{'PF':>6} {'Sharpe':>7} {'MaxDD%':>7}")

    results = []
    for bias_mode in BIAS_MODES:
        print(f"\n  ── BİAS: {bias_mode.upper()} " + "─" * 55)
        print(header)
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
            results.append(row)
            pf_str = f"{row['pf']:.2f}" if row['pf'] != float('inf') else "inf"
            print(f"  {row['bias']:<8} {row['rr']:<11} {row['total']:>4} "
                  f"{row['wins']:>4} {row['losses']:>5} {row['be']:>3} "
                  f"{row['wr']:>6.1f} {row['pnl']:>+11.2f} {row['ret']:>+7.2f} "
                  f"{pf_str:>6} {row['sharpe']:>7.2f} {row['maxdd']:>7.2f}")

    # Özet: en iyi konfigürasyonlar
    print("\n" + "═" * 78)
    print("  ÖZET — Net PnL'e göre sıralı")
    print("═" * 78)
    print(header)
    print("  " + "─" * 76)
    for row in sorted(results, key=lambda r: r['pnl'], reverse=True):
        pf_str = f"{row['pf']:.2f}" if row['pf'] != float('inf') else "inf"
        print(f"  {row['bias']:<8} {row['rr']:<11} {row['total']:>4} "
              f"{row['wins']:>4} {row['losses']:>5} {row['be']:>3} "
              f"{row['wr']:>6.1f} {row['pnl']:>+11.2f} {row['ret']:>+7.2f} "
              f"{pf_str:>6} {row['sharpe']:>7.2f} {row['maxdd']:>7.2f}")
    print("═" * 78)


if __name__ == '__main__':
    main()
