"""Quick London Reversal backtest only (BÖLÜM H + H-E)."""
from pathlib import Path
from xauusd_fvg_engine_v10 import (
    DataEngine, RiskManager, PerformanceAnalytics,
    WeeklyBiasProvider, DailyBiasProvider,
    LondonReversalBrain, LondonBacktestEngine,
    EMAEngine, MACDEngine, to_naive,
)

INITIAL_CAPITAL = 10_000
BIAS_MODES = ['weekly', 'daily', 'none']


def make_bias(mode, df_1h):
    if mode == 'none':
        return None
    if mode == 'daily':
        if not Path('daily_bias.json').exists():
            DailyBiasProvider.build_from_1h(df_1h, 'daily_bias.json')
        return DailyBiasProvider('daily_bias.json')
    return WeeklyBiasProvider('weekly_bias.json')


def run_london(df_1h, df_5m, bt_start, bias_mode, emf=False, tbe=None):
    bias_provider = make_bias(bias_mode, df_1h)
    brain = LondonReversalBrain(bias_provider=bias_provider)
    risk_mgr = RiskManager(rr=2.0, sl_buffer=0.0005)
    engine = LondonBacktestEngine(brain, risk_mgr,
                                  initial_capital=INITIAL_CAPITAL,
                                  breakeven_at_R=None,
                                  time_exit_bars=tbe,
                                  ema_macd_filter=emf)
    trades = engine.run(df_1h, df_5m, bt_start)
    analytics = PerformanceAnalytics(trades, INITIAL_CAPITAL)
    metrics = analytics.compute()
    stats = brain.stats
    return trades, metrics, stats


def main():
    print("Veri yükleniyor...")
    df_1h, df_5m, bt_start = DataEngine.download(verbose=True)
    print(f"5M barlar: {len(df_5m)}, 1H barlar: {len(df_1h)}")

    print("\n" + "=" * 85)
    print("  BÖLÜM H — LONDON REVERSAL (ICT Judas Swing)  |  TBE:Yok  |  3 BİAS")
    print("=" * 85)

    for bias_mode in BIAS_MODES:
        trades, m, stats = run_london(df_1h, df_5m, bt_start, bias_mode)
        print(f"\n  BİAS: {bias_mode.upper()}")
        print(f"  Brain stats: {stats}")
        if m is None:
            print("  → İşlem yok")
            continue
        print(f"  İşlem:{m['total']:>4}  Win:{m['wins']:>4}  Loss:{m['losses']:>4}  "
              f"WR:{m['win_rate']*100:>5.1f}%  NetPnL:{m['net_pnl']:>+10.2f}  "
              f"PF:{m['profit_factor']:.2f}  Sharpe:{m['sharpe']:.2f}  MaxDD:{m['max_dd']:.2f}%")

        # Show first 5 trades
        for tr in trades[:5]:
            print(f"    {to_naive(tr.signal.entry_time)}  {tr.signal.direction}  "
                  f"entry={tr.entry_price:.2f}  sl={tr.sl:.2f}  "
                  f"tp={tr.tp:.2f}  exit={tr.exit_price:.2f}  "
                  f"result={tr.result}  pnl={tr.pnl_dollar:.2f}")

    print("\n" + "=" * 85)
    print("  BÖLÜM H-E — LONDON REVERSAL × EMA-MACD FİLTRESİ")
    print("=" * 85)

    for bias in BIAS_MODES:
        _, m0, s0 = run_london(df_1h, df_5m, bt_start, bias, emf=False)
        _, m1, s1 = run_london(df_1h, df_5m, bt_start, bias, emf=True)
        t0 = m0['total'] if m0 else 0
        t1 = m1['total'] if m1 else 0
        wr0 = m0['win_rate'] * 100 if m0 else 0
        wr1 = m1['win_rate'] * 100 if m1 else 0
        p0 = m0['net_pnl'] if m0 else 0
        p1 = m1['net_pnl'] if m1 else 0
        print(f"\n  bias={bias:<7} filtresiz: İşl={t0:>4} WR={wr0:.1f}% PnL={p0:>+9.2f}")
        print(f"  bias={bias:<7} EMA-MACD:  İşl={t1:>4} WR={wr1:.1f}% PnL={p1:>+9.2f}")
        if m0 and m1:
            print(f"  Δ: İşl={t1-t0:>+3}  PnL={p1-p0:>+9.2f}")

    print("\n" + "=" * 85)


if __name__ == '__main__':
    main()
