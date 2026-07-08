"""Lookahead (gelecek görme) testi — KESME DEĞİŞMEZLİĞİ.

Prensip: strateji geleceğe bakmıyorsa, veriyi T anında kesmek T'den önceki
işlemleri DEĞİŞTİREMEZ. Her strateji tam veri ve %70'te kesilmiş veriyle
koşulur; kesme anından 3 gün öncesine kadar girilen işlemlerin
(giriş zamanı, yön, giriş fiyatı, SL, TP) birebir aynı olması assert edilir.
Fark çıkarsa → lookahead var → WR şişiyor demektir.
"""
import sys, io, contextlib
import pandas as pd
sys.path.insert(0, '/home/user/erebb')
import os; os.chdir('/home/user/erebb')
from xauusd_fvg_engine_v10 import (
    DataEngine, RiskManager, PerformanceAnalytics, to_naive,
    MarketBrain, ThreeVolBrain, LondonReversalBrain, QweBrain,
    BacktestEngine, LondonBacktestEngine, QweBacktestEngine,
    PrivateBiasProvider,
)

df_1h, df_5m, bt_start = DataEngine.download(verbose=False)
cut = df_5m.index[int(len(df_5m) * 0.70)]
margin = pd.Timedelta(days=3)
print(f"kesme noktası: {cut}  (marj: {margin})")

df_5m_cut = df_5m[df_5m.index <= cut]
df_1h_cut = df_1h[df_1h.index <= cut]


def run(name, brain_f, engine_cls):
    def one(d1, d5):
        brain = brain_f(d1)
        eng = engine_cls(brain, RiskManager(rr=2.0, sl_buffer=0.0005),
                         initial_capital=10000, breakeven_at_R=None,
                         time_exit_bars=None, ema_macd_filter=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            return eng.run(d1, d5, bt_start)
    full = one(df_1h, df_5m)
    part = one(df_1h_cut, df_5m_cut)
    key = lambda t: (to_naive(t.signal.entry_time), t.signal.direction,
                     round(t.entry_price, 2), round(t.sl, 2), round(t.tp, 2))
    lim = cut - margin
    f_keys = sorted(k for k in map(key, full) if k[0] <= lim)
    p_keys = sorted(k for k in map(key, part) if k[0] <= lim)
    only_full = set(f_keys) - set(p_keys)
    only_part = set(p_keys) - set(f_keys)
    status = 'TEMİZ' if not only_full and not only_part else 'LOOKAHEAD ŞÜPHESİ!'
    print(f"  {name:<10}: tam={len(f_keys):>3} kesik={len(p_keys):>3}  → {status}")
    for k in sorted(only_full)[:3]:
        print(f"      yalnız TAM veride : {k}")
    for k in sorted(only_part)[:3]:
        print(f"      yalnız KESİK'te   : {k}")
    return not only_full and not only_part


ok = True
ok &= run('fvg',      lambda d1: MarketBrain(bias_provider=None, poi_mode='all'), BacktestEngine)
ok &= run('threevol', lambda d1: ThreeVolBrain(bias_provider=None),               BacktestEngine)
ok &= run('london',   lambda d1: LondonReversalBrain(bias_provider=PrivateBiasProvider(d1)),
          LondonBacktestEngine)
ok &= run('qwe',      lambda d1: QweBrain(bias_provider=None),                    QweBacktestEngine)

print("\nSONUÇ:", "4 STRATEJİ DE KESME-DEĞİŞMEZ (lookahead yok)" if ok
      else "LOOKAHEAD BULUNDU — yukarıdaki farklara bak")
sys.exit(0 if ok else 1)
