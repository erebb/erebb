"""
Standart Test Matrisi — XAUUSD FVG Engine v10 + Kârlı Stratejiler
==================================================================
BÖLÜM A: FVG v10 Stratejisi           — 3 BİAS × 3 RR = 9 test
BÖLÜM B: Fib 0.618 Retest             — 3 BİAS × 2 TP = 6 test
BÖLÜM C: Three_vol Doğrudan           — 3 BİAS × 3 RR = 9 test
BÖLÜM F: Breaker Block (BB) POI Only  — 1 BİAS × 3 RR = 3 test  (sadece daily)
BÖLÜM G: Harmonik PRZ Only            — 3 BİAS × 3 RR = 9 test
BÖLÜM I: FVG v10 + Açık Likidite TP   — 3 BİAS × 2 TP = 6 test
BÖLÜM J: FVG v10 + EQL TP             — 3 BİAS × 2 EQL = 6 test

Kaldırılanlar (sürekli zarar): 3VOL-Ret, OB-Only, HS-Only, BB weekly/none,
                                Sabit 3R TP, EQL 3-4R BE2

Kullanım: python3 run_test_matrix.py
"""

import io
import contextlib
from pathlib import Path

from xauusd_fvg_engine_v10 import (
    DataEngine, MarketBrain, RiskManager, BacktestEngine,
    PerformanceAnalytics, WeeklyBiasProvider, DailyBiasProvider,
    FibRetestBrain, FibBacktestEngine, LiquidityTargetFinder, SessionFilter,
    ThreeVolBrain,
    EqualLiquidityFinder, LiquidityTPConfig,
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
]

# EqualLiquidityFinder konfigürasyonları — (etiket, LiquidityTPConfig, breakeven_at_R)
EQL_CONFIGS = [
    ('EQL 2-4R BE2', LiquidityTPConfig(min_r=2.0, max_r=4.0), 2.0),  # BE@2R
    ('EQL 2-3R',     LiquidityTPConfig(min_r=2.0, max_r=3.0), None),
]

# BÖLÜM J strateji tanımları — SADECE 1H FVG girişi için
# (etiket, brain_type, poi_mode, enable_bb, use_session)
EQL_STRATEGIES = [
    ('FVG-v10', 'fvg', 'all', False, False),
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


def run_one(df_1h, df_5m, bt_start, bias_mode, rr, be, poi_mode='all', enable_bb=False):
    """FVG v10 / POI-only: tek konfigürasyon çalıştır."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bias_provider = make_bias(bias_mode, df_1h)
        brain    = MarketBrain(bias_provider=bias_provider, poi_mode=poi_mode)
        risk_mgr = RiskManager(rr=rr, sl_buffer=0.0005)
        engine   = BacktestEngine(brain, risk_mgr,
                                  initial_capital=INITIAL_CAPITAL,
                                  breakeven_at_R=be,
                                  enable_bb=enable_bb)
        trades   = engine.run(df_1h, df_5m, bt_start)
        analytics = PerformanceAnalytics(trades, INITIAL_CAPITAL)
        metrics   = analytics.compute()
    return trades, metrics


def run_one_fvg_liq(df_1h, df_5m, bt_start, bias_mode, rr, use_liq_tp):
    """FVG v10 girişi + açık likidite TP (LiquidityTargetFinder)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bias_provider = make_bias(bias_mode, df_1h)
        brain      = MarketBrain(bias_provider=bias_provider)
        risk_mgr   = RiskManager(rr=rr, sl_buffer=0.0005)
        liq_finder = LiquidityTargetFinder() if use_liq_tp else None
        engine     = FibBacktestEngine(brain, risk_mgr, liq_finder,
                                       initial_capital=INITIAL_CAPITAL,
                                       breakeven_at_R=None)
        trades     = engine.run(df_1h, df_5m, bt_start)
        analytics  = PerformanceAnalytics(trades, INITIAL_CAPITAL)
        metrics    = analytics.compute()
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


def run_one_eql(df_1h, df_5m, bt_start, bias_mode, brain_type, poi_mode,
                enable_bb, use_session, eql_cfg: LiquidityTPConfig,
                be_r=None):
    """Herhangi bir strateji + EqualLiquidityFinder TP."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bias_provider = make_bias(bias_mode, df_1h)
        session       = SessionFilter() if use_session else None

        if brain_type == 'fib':
            brain = FibRetestBrain(bias_provider=bias_provider,
                                   session_filter=session)
        elif brain_type == 'threevol':
            brain = ThreeVolBrain(bias_provider=bias_provider)
        else:
            brain = MarketBrain(bias_provider=bias_provider, poi_mode=poi_mode)

        risk_mgr   = RiskManager(rr=2.0, sl_buffer=0.0005)
        eql_finder = EqualLiquidityFinder(eql_cfg)
        engine     = FibBacktestEngine(brain, risk_mgr, eql_finder,
                                       initial_capital=INITIAL_CAPITAL,
                                       breakeven_at_R=be_r,
                                       enable_bb=enable_bb)
        trades     = engine.run(df_1h, df_5m, bt_start)
        analytics  = PerformanceAnalytics(trades, INITIAL_CAPITAL)
        metrics    = analytics.compute()
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
    print("  BÖLÜM B — FİB 0.618 RETEST STRATEJİSİ  │  3 BİAS × 2 HEDEF  =  6 TEST")
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
    # BÖLÜM F: Breaker Block (BB) POI Only — sadece daily bias (weekly/none zarar)
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "═" * 78)
    print("  BÖLÜM F — BREAKER BLOCK POI ONLY  │  DAILY BİAS × 3 RR  =  3 TEST")
    print("  (Giriş: 1H BB reclaim + 5M MSB  |  weekly/none zarar verdiğinden kaldırıldı)")
    print("═" * 78)

    results_f = []
    print(f"\n  ── BİAS: DAILY " + "─" * 55)
    print(_header())
    print("  " + "─" * 76)
    for rr_label, rr, be in RR_CONFIGS:
        trades, m = run_one(df_1h, df_5m, bt_start, 'daily', rr, be,
                            poi_mode='bb', enable_bb=True)
        if m is None:
            print(f"  {'daily':<8} {rr_label:<11} {'— tamamlanan işlem yok —':>50}")
            continue
        row = dict(bias='daily', rr=rr_label,
                   total=m['total'], wins=m['wins'], losses=m['losses'],
                   be=m['breakeven'], wr=m['win_rate'] * 100,
                   pnl=m['net_pnl'], ret=m['ret_pct'],
                   pf=m['profit_factor'], sharpe=m['sharpe'],
                   maxdd=m['max_dd'])
        results_f.append(row)
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
    # BÖLÜM I: FVG v10 + Açık Likidite TP — 3×3 = 9 test
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "═" * 78)
    print("  BÖLÜM I — FVG v10 + AÇIK LİKİDİTE TP  │  3 BİAS × 2 TP  =  6 TEST")
    print("  (FVG dokunuşu + 5M MSB girişi, TP = 2–5R aralığındaki ilk açık 1H FVG)")
    print("═" * 78)

    results_i = []
    for bias_mode in BIAS_MODES:
        print(f"\n  ── BİAS: {bias_mode.upper()} " + "─" * 55)
        print(_header())
        print("  " + "─" * 76)
        for tp_label, rr, use_liq in FIB_CONFIGS:
            trades, m = run_one_fvg_liq(df_1h, df_5m, bt_start, bias_mode, rr, use_liq)
            if m is None:
                print(f"  {bias_mode:<8} {tp_label:<11} {'— tamamlanan işlem yok —':>50}")
                continue
            row = dict(bias=bias_mode, rr=tp_label,
                       total=m['total'], wins=m['wins'], losses=m['losses'],
                       be=m['breakeven'], wr=m['win_rate'] * 100,
                       pnl=m['net_pnl'], ret=m['ret_pct'],
                       pf=m['profit_factor'], sharpe=m['sharpe'],
                       maxdd=m['max_dd'])
            results_i.append(row)
            _print_row(row)

    # ══════════════════════════════════════════════════════════════════════════
    # BÖLÜM J: 1H FVG × EqualLiquidityFinder TP × 3 BİAS = 9 TEST
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "═" * 78)
    print("  BÖLÜM J — EŞİT TEPE/DİP LİKİDİTE TP  │  1H FVG × 3 BİAS × 2 EQL = 6 TEST")
    print("  (Önce eşit seviyeler, yoksa 1H FVG kenarı, yoksa 2R/3R fallback)")
    print("═" * 78)

    results_j = []
    for strat_label, brain_type, poi_mode, enable_bb, use_session in EQL_STRATEGIES:
        print(f"\n  ── STRATEJİ: {strat_label} " + "─" * 50)
        print(_header())
        print("  " + "─" * 76)
        for bias_mode in BIAS_MODES:
            for eql_label, eql_cfg, be_r in EQL_CONFIGS:
                trades, m = run_one_eql(df_1h, df_5m, bt_start, bias_mode,
                                        brain_type, poi_mode, enable_bb,
                                        use_session, eql_cfg, be_r)
                if m is None:
                    print(f"  {bias_mode:<8} {eql_label:<11} {'— tamamlanan işlem yok —':>50}")
                    continue
                row = dict(bias=bias_mode, rr=eql_label,
                           total=m['total'], wins=m['wins'], losses=m['losses'],
                           be=m['breakeven'], wr=m['win_rate'] * 100,
                           pnl=m['net_pnl'], ret=m['ret_pct'],
                           pf=m['profit_factor'], sharpe=m['sharpe'],
                           maxdd=m['max_dd'])
                results_j.append(dict(strateji=f'EQL:{strat_label}', **row))
                _print_row(row)

    # ══════════════════════════════════════════════════════════════════════════
    # KAPSAMLI ÖZET — Teknik × Bias × TP tablosu, Net PnL sıralı
    # ══════════════════════════════════════════════════════════════════════════
    all_results = (
        [dict(strateji='FVG-v10',  **r) for r in results_a] +
        [dict(strateji='Fib0618',  **r) for r in results_b] +
        [dict(strateji='3VOL-Dir', **r) for r in results_c] +
        [dict(strateji='BB-Only',  **r) for r in results_f] +
        [dict(strateji='PRZ-Only', **r) for r in results_g] +
        [dict(strateji='FVG-Liq',  **r) for r in results_i] +
        results_j
    )

    print("\n" + "═" * 90)
    print("  GENEL ÖZET — Net PnL'e göre sıralı (tüm stratejiler)")
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
