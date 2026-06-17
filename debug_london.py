"""Debug London Reversal — check MSB timing relative to sweeps."""
import numpy as np
import pandas as pd
from xauusd_fvg_engine_v10 import (
    DataEngine, AsianRangeCalculator, SessionFilter,
    to_naive,
)

de = DataEngine
df_1h, df_5m, bt_start = DataEngine.download(verbose=False)

print(f"Backtest start: {bt_start}")
print(f"5M bars total: {len(df_5m)}")

# Compute Asian ranges
ASIAN_H, ASIAN_L = AsianRangeCalculator.compute(df_5m)

# Check ranges in backtest period
mask_bt = df_5m.index >= pd.Timestamp(bt_start, tz='UTC')
df_bt = df_5m[mask_bt]
ah_bt = ASIAN_H[mask_bt.values]
al_bt = ASIAN_L[mask_bt.values]

print(f"Backtest bars: {len(df_bt)}")
valid_range = ~(np.isnan(ah_bt) | np.isnan(al_bt))
print(f"Valid Asian range bars: {valid_range.sum()}")
valid_wide = valid_range & ((ah_bt - al_bt) >= 0.5)
print(f"Valid + range ≥0.5: {valid_wide.sum()}")

# Compute ATR
C = df_bt['Close'].values
H = df_bt['High'].values
L = df_bt['Low'].values
ATR = pd.Series(np.where(np.arange(len(H)) > 0,
    np.maximum(H[1:] if len(H) > 1 else H,
               np.where(np.arange(len(H)) > 0, C[:-1] if len(C) > 1 else C, C)) - L,
    H - L)).rolling(14).mean().values
# Simple ATR as TR rolling mean
TR = np.maximum(H - L, np.maximum(np.abs(H - np.roll(C, 1)), np.abs(L - np.roll(C, 1))))
ATR14 = pd.Series(TR).rolling(14).mean().values
atr_mean = np.nanmean(ATR14)
print(f"Mean ATR: {atr_mean:.2f}")

# SessionFilter for London
sess = SessionFilter()

# Check sweeps in early London
print("\n--- Sweep Analysis ---")
sweeps_bull = []
sweeps_bear = []
london_bars = 0
early_london_bars = 0

for i, (ts, row) in enumerate(df_bt.iterrows()):
    t = to_naive(ts)
    if not sess.is_london_session(t) or sess.is_holiday(t):
        continue
    london_bars += 1
    if not valid_wide[i]:
        continue

    ah = ah_bt[i]
    al = al_bt[i]
    atr_v = float(ATR14[i]) if not np.isnan(ATR14[i]) else atr_mean
    min_depth = max(0.30, atr_v * 0.05)

    h_bar = float(H[i])
    l_bar = float(L[i])
    c_bar = float(C[i])

    # Early London check
    h_frac = t.hour + t.minute / 60.0
    is_bst = sess.is_london_dst(t)
    early = (7.0 <= h_frac < 8.5) if is_bst else (8.0 <= h_frac < 9.5)
    if early:
        early_london_bars += 1

    if early:
        # Bull sweep
        if l_bar < al - min_depth and c_bar > al:
            sweeps_bull.append({'idx': i, 'time': ts, 'al': al, 'ah': ah,
                                'low': l_bar, 'close': c_bar, 'depth': al - l_bar})
        # Bear sweep
        if h_bar > ah + min_depth and c_bar < ah:
            sweeps_bear.append({'idx': i, 'time': ts, 'al': al, 'ah': ah,
                                'high': h_bar, 'close': c_bar, 'depth': h_bar - ah})

print(f"London bars: {london_bars}")
print(f"Early London bars: {early_london_bars}")
print(f"Bull sweeps: {len(sweeps_bull)}")
print(f"Bear sweeps: {len(sweeps_bear)}")

# Now load MSB events via the engine's internal computation
# Import MSB engine output
from xauusd_fvg_engine_v10 import BacktestEngine, MarketBrain, RiskManager

class DebugEngine(BacktestEngine):
    def run(self, df_1h, df_5m, backtest_start):
        # run but intercept MSB events
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = super().run(df_1h, df_5m, backtest_start)
        self._debug_out = buf.getvalue()
        return result

brain = MarketBrain()
risk = RiskManager(rr=2.0)
# We'll use BacktestEngine internals to get MSB events
# Actually, let's just use the MSB engine directly
from xauusd_fvg_engine_v10 import MSBEngine
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    msb_result = MSBEngine.detect(df_5m)

msb_bull, msb_bear = msb_result

# Find MSB events in London session
london_msb_bull = [e for e in msb_bull
                   if sess.is_london_session(to_naive(df_5m.index[e.confirm_idx]))
                   and not sess.is_holiday(to_naive(df_5m.index[e.confirm_idx]))
                   and df_5m.index[e.confirm_idx] >= pd.Timestamp(bt_start, tz='UTC')]
london_msb_bear = [e for e in msb_bear
                   if sess.is_london_session(to_naive(df_5m.index[e.confirm_idx]))
                   and not sess.is_holiday(to_naive(df_5m.index[e.confirm_idx]))
                   and df_5m.index[e.confirm_idx] >= pd.Timestamp(bt_start, tz='UTC')]

print(f"\nMSB events total: bull={len(msb_bull)}, bear={len(msb_bear)}")
print(f"London MSB (backtest): bull={len(london_msb_bull)}, bear={len(london_msb_bear)}")

# Map MSBs by confirm_idx (local backtest index)
bt_start_ts = pd.Timestamp(bt_start, tz='UTC')
bt_offset = sum(df_5m.index < bt_start_ts)
msb_bull_by_idx = {e.confirm_idx: e for e in msb_bull}
msb_bear_by_idx = {e.confirm_idx: e for e in msb_bear}

# Check: how many sweeps get an MSB within various windows?
print("\n--- Sweep → MSB matching (none bias) ---")
windows = [6, 12, 24, 36, 48]
for w in windows:
    matched_b = 0
    matched_bear = 0
    for s in sweeps_bull:
        global_i = s['idx'] + bt_offset
        for j in range(1, w+1):
            if (global_i + j) in msb_bull_by_idx:
                matched_b += 1
                break
    for s in sweeps_bear:
        global_i = s['idx'] + bt_offset
        for j in range(1, w+1):
            if (global_i + j) in msb_bear_by_idx:
                matched_bear += 1
                break
    print(f"  Window {w:>2} bars ({w*5:>3}min): bull {matched_b}/{len(sweeps_bull)}, "
          f"bear {matched_bear}/{len(sweeps_bear)}")

# Show some bull sweeps and nearby MSBs
print("\n--- First 10 bull sweeps detail ---")
for s in sweeps_bull[:10]:
    global_i = s['idx'] + bt_offset
    nearby = []
    for j in range(-2, 50):
        gi = global_i + j
        if gi in msb_bull_by_idx:
            nearby.append((j, df_5m.index[gi]))
    print(f"  {s['time']} al={s['al']:.2f} low={s['low']:.2f} depth={s['depth']:.2f}  MSB@bars: {nearby[:5]}")
