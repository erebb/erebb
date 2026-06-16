"""
Standart Test Matrisi — XAUUSD FVG Engine v10
=============================================
BÖLÜM T: TBE taraması              — 3 STR × 3 BİAS × 4 TBE = 36 test
BÖLÜM A: FVG v10 (optimal TBE)    — 3 BİAS × 3 RR = 9 test
BÖLÜM C: Three_vol (optimal TBE)  — 3 BİAS × 3 RR = 9 test
BÖLÜM G: PRZ Only (optimal TBE)   — 3 BİAS × 3 RR = 9 test

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

RR_CONFIGS = [
    ('1:1',       1.0, None),
    ('1:2 BE@1R', 2.0, 1.0),
    ('1:2 fix',   2.0, None),
]

BIAS_MODES = ['weekly', 'daily', 'none']

TBE_OPTIONS = [
    ('Yok',    None),
    ('TBE-2h', 24),
    ('TBE-4h', 48),
    ('TBE-8h', 96),
]


def make_bias(mode, df_1h):
    if mode == 'none':
        return None
    if mode == 'daily':
        if not Path('daily_bias.json').exists():
            DailyBiasProvider.build_from_1h(df_1h, 'daily_bias.json')
        return DailyBiasProvider('daily_bias.json')
    return WeeklyBiasProvider('weekly_bias.json')


def run_one(df_1h, df_5m, bt_start, bias_mode, rr, be,
            poi_mode='all', tbe=None):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bias_provider = make_bias(bias_mode, df_1h)
        brain    = MarketBrain(bias_provider=bias_provider, poi_mode=poi_mode)
        risk_mgr = RiskManager(rr=rr, sl_buffer=0.0005)
        engine   = BacktestEngine(brain, risk_mgr,
                                  initial_capital=INITIAL_CAPITAL,
                                  breakeven_at_R=be,
                                  time_exit_bars=tbe)
        trades   = engine.run(df_1h, df_5m, bt_start)
        analytics = PerformanceAnalytics(trades, INITIAL_CAPITAL)
        metrics   = analytics.compute()
    return trades, metrics


def run_one_threevol(df_1h, df_5m, bt_start, bias_mode, rr, be, tbe=None):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bias_provider = make_bias(bias_mode, df_1h)
        brain    = ThreeVolBrain(bias_provider=bias_provider)
        risk_mgr = RiskManager(rr=rr, sl_buffer=0.0005)
        engine   = BacktestEngine(brain, risk_mgr,
                                  initial_capital=INITIAL_CAPITAL,
                                  breakeven_at_R=be,
                                  time_exit_bars=tbe)
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


def _tbe_scan(df_1h, df_5m, bt_start):
    """
    3 strateji × 3 bias × 4 TBE seçeneği × 1:2 fix = 36 test.
    Skor = sharpe × (1 - maxdd/100).
    Her strateji için bias ortalaması en yüksek TBE'yi seçer.
    """
    print("\n" + "═" * 90)
    print("  BÖLÜM T — TBE TARAMASI  │  3 STR × 3 BİAS × 4 TBE  =  36 TEST  │  1:2 fix")
    print("  Skor = Sharpe × (1 - MaxDD/100)  |  optimal TBE → A/C/G bölümlerine uygulanır")
    print("═" * 90)

    # (str_key, bias, tbe_label) → metrics
    scan: dict = {}

    str_runners = [
        ('fvg',      'FVG-v10',
         lambda bias, tbe: run_one(df_1h, df_5m, bt_start, bias, 2.0, None, 'all', tbe)),
        ('threevol', '3VOL-Dir',
         lambda bias, tbe: run_one_threevol(df_1h, df_5m, bt_start, bias, 2.0, None, tbe)),
        ('prz',      'PRZ-Only',
         lambda bias, tbe: run_one(df_1h, df_5m, bt_start, bias, 2.0, None, 'prz', tbe)),
    ]

    for bias in BIAS_MODES:
        print(f"\n  ── BİAS: {bias.upper()} " + "─" * 60)
        print(f"  {'Strateji':<10} {'TBE':>6} {'İŞL':>4} {'WR%':>6} "
              f"{'PnL$':>10} {'Sharpe':>7} {'MaxDD%':>7} {'Skor':>7}")
        print("  " + "─" * 65)
        for str_key, str_name, runner in str_runners:
            for tbe_label, tbe_bars in TBE_OPTIONS:
                _, m = runner(bias, tbe_bars)
                if m is None:
                    continue
                score = m['sharpe'] * (1.0 - m['max_dd'] / 100.0)
                scan[(str_key, bias, tbe_label)] = {**m, 'score': score}
                marker = ' ←' if tbe_label == 'Yok' else ''
                print(f"  {str_name:<10} {tbe_label:>6} {m['total']:>4} "
                      f"{m['win_rate']*100:>6.1f} {m['net_pnl']:>+10.2f} "
                      f"{m['sharpe']:>7.2f} {m['max_dd']:>7.2f} "
                      f"{score:>7.3f}{marker}")

    # ── Optimal TBE seçimi ───────────────────────────────────────────────────
    print("\n  ── Optimal TBE seçimi (bias ortalaması üzerinden) " + "─" * 38)

    optimal: dict = {}
    for str_key, str_name, _ in str_runners:
        best_tbe_label, best_avg = None, -1e9
        for tbe_label, _ in TBE_OPTIONS:
            scores = [
                scan[(str_key, bias, tbe_label)]['score']
                for bias in BIAS_MODES
                if (str_key, bias, tbe_label) in scan
            ]
            if not scores:
                continue
            avg = sum(scores) / len(scores)
            if avg > best_avg:
                best_avg = avg
                best_tbe_label = tbe_label

        best_bars = dict(TBE_OPTIONS)[best_tbe_label]
        optimal[str_key] = best_bars

        # Baseline ile karşılaştır
        base_scores = [
            scan[(str_key, bias, 'Yok')]['score']
            for bias in BIAS_MODES
            if (str_key, bias, 'Yok') in scan
        ]
        base_avg = sum(base_scores) / len(base_scores) if base_scores else 0
        delta = best_avg - base_avg
        bars_str = f"{best_bars}bar" if best_bars else "—"
        print(f"  {str_name:<10} → {best_tbe_label:<8} ({bars_str:<6})  "
              f"Ort.Skor: {best_avg:.3f}  (baseline: {base_avg:.3f}  Δ{delta:+.3f})")

    print("═" * 90)
    return optimal


def main():
    df_1h, df_5m, bt_start = DataEngine.download(verbose=True)

    # ── TBE taraması (BÖLÜM T) ————————————————————————————————————————————
    OPTIMAL_TBE = _tbe_scan(df_1h, df_5m, bt_start)

    # TBE etiketleri (başlıklar için)
    def _tbe_label(bars):
        if bars is None:
            return 'TBE:Yok'
        return f"TBE:{bars//12}h"

    # ══════════════════════════════════════════════════════════════════════════
    # BÖLÜM A: FVG v10
    # ══════════════════════════════════════════════════════════════════════════
    tbe_a = OPTIMAL_TBE['fvg']
    print("\n" + "═" * 78)
    print(f"  BÖLÜM A — FVG v10 STRATEJİSİ  │  {_tbe_label(tbe_a)}  │  3 BİAS × 3 RR  =  9 TEST")
    print("═" * 78)

    results_a = []
    for bias_mode in BIAS_MODES:
        print(f"\n  ── BİAS: {bias_mode.upper()} " + "─" * 55)
        print(_header())
        print("  " + "─" * 76)
        for rr_label, rr, be in RR_CONFIGS:
            trades, m = run_one(df_1h, df_5m, bt_start, bias_mode, rr, be, tbe=tbe_a)
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
    # BÖLÜM C: Three_vol
    # ══════════════════════════════════════════════════════════════════════════
    tbe_c = OPTIMAL_TBE['threevol']
    print("\n" + "═" * 78)
    print(f"  BÖLÜM C — THREE_VOL DOĞRUDAN  │  {_tbe_label(tbe_c)}  │  3 BİAS × 3 RR  =  9 TEST")
    print("  (Giriş: three_vol onay barında, FVG/POI dokunuşu yok)")
    print("═" * 78)

    results_c = []
    for bias_mode in BIAS_MODES:
        print(f"\n  ── BİAS: {bias_mode.upper()} " + "─" * 55)
        print(_header())
        print("  " + "─" * 76)
        for rr_label, rr, be in RR_CONFIGS:
            trades, m = run_one_threevol(df_1h, df_5m, bt_start, bias_mode, rr, be, tbe=tbe_c)
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
    # BÖLÜM G: Harmonik PRZ Only
    # ══════════════════════════════════════════════════════════════════════════
    tbe_g = OPTIMAL_TBE['prz']
    print("\n" + "═" * 78)
    print(f"  BÖLÜM G — HARMONİK PRZ ONLY  │  {_tbe_label(tbe_g)}  │  3 BİAS × 3 RR  =  9 TEST")
    print("  (Giriş: 5M harmonik PRZ dokunuşu + 5M MSB, FVG filtresi yok)")
    print("═" * 78)

    results_g = []
    for bias_mode in BIAS_MODES:
        print(f"\n  ── BİAS: {bias_mode.upper()} " + "─" * 55)
        print(_header())
        print("  " + "─" * 76)
        for rr_label, rr, be in RR_CONFIGS:
            trades, m = run_one(df_1h, df_5m, bt_start, bias_mode, rr, be,
                                poi_mode='prz', tbe=tbe_g)
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
    print(f"  GENEL ÖZET — Net PnL'e göre sıralı  "
          f"│  FVG:{_tbe_label(tbe_a)}  3VOL:{_tbe_label(tbe_c)}  PRZ:{_tbe_label(tbe_g)}")
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
