"""Quick London MSB density check."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import numpy as np
import pandas as pd
from xauusd_fvg_engine_v10 import DataEngine, MSB5MEngine, SessionFilter, to_naive

print("Loading data...")
df_1h, df_5m, bt_start = DataEngine.download(verbose=False)
print(f"BT start: {bt_start}, 5M bars: {len(df_5m)}")

msb_eng = MSB5MEngine(vol_mult=1.5, vol_window=20)
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    msb_events = msb_eng.detect(df_5m, df_5m['atr'])

msb_bull = [e for e in msb_events if e.direction == 'bull']
msb_bear = [e for e in msb_events if e.direction == 'bear']
print(f"MSB total: bull={len(msb_bull)}, bear={len(msb_bear)}")

sess = SessionFilter()

# Filter to backtest period and London
bt_ts = pd.Timestamp(bt_start)
bt_idx = 0
for i, ts in enumerate(df_5m.index):
    t = to_naive(ts)
    if t >= bt_ts:
        bt_idx = i
        break

print(f"BT start index: {bt_idx}, total bars after: {len(df_5m) - bt_idx}")

london_msb_bull = []
london_msb_bear = []
for e in msb_bull:
    if e.confirm_idx < bt_idx:
        continue
    t = to_naive(df_5m.index[e.confirm_idx])
    if sess.is_london_session(t) and not sess.is_holiday(t):
        london_msb_bull.append(e)

for e in msb_bear:
    if e.confirm_idx < bt_idx:
        continue
    t = to_naive(df_5m.index[e.confirm_idx])
    if sess.is_london_session(t) and not sess.is_holiday(t):
        london_msb_bear.append(e)

print(f"London MSBs in backtest: bull={len(london_msb_bull)}, bear={len(london_msb_bear)}")

# Count trading days in backtest
london_days = set()
for i in range(bt_idx, len(df_5m)):
    t = to_naive(df_5m.index[i])
    if sess.is_london_session(t) and not sess.is_holiday(t):
        london_days.add(t.date())

print(f"London trading days in backtest: {len(london_days)}")
print(f"Avg London MSBs per day: bull={len(london_msb_bull)/len(london_days):.2f}, "
      f"bear={len(london_msb_bear)/len(london_days):.2f}")

# Check distribution by hour in London
from collections import Counter
bull_hours = Counter(to_naive(df_5m.index[e.confirm_idx]).hour for e in london_msb_bull)
bear_hours = Counter(to_naive(df_5m.index[e.confirm_idx]).hour for e in london_msb_bear)
print(f"\nBull MSB by hour (UTC): {dict(sorted(bull_hours.items()))}")
print(f"Bear MSB by hour (UTC): {dict(sorted(bear_hours.items()))}")

# Check: first 3 bull London MSBs
print("\nFirst 5 London bull MSBs:")
for e in london_msb_bull[:5]:
    t = to_naive(df_5m.index[e.confirm_idx])
    print(f"  idx={e.confirm_idx} time={t} type={e.msb_type}")

print("\nFirst 5 London bear MSBs:")
for e in london_msb_bear[:5]:
    t = to_naive(df_5m.index[e.confirm_idx])
    print(f"  idx={e.confirm_idx} time={t} type={e.msb_type}")
