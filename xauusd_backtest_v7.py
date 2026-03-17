"""
XAUUSD - 1:2 RR Day Trade Backtest  (v8.0)
============================================
v8.0 DEĞİŞİKLİKLERİ

1. LOOKAHEAD BIAS DÜZELTMESİ:
   FVG [i-2, i-1, i] üçlüsünden oluşur; yalnızca i. mum
   kapandıktan SONRA görünür. Önceki versiyonlarda
   'index = T[i-1]' ile karşılaştırma yapıldığından aynı
   mumda oluşan FVG sinyal için kullanılabiliyordu (lookahead).
   v8: her FVG'ye 'detect_time = T[i]' eklendi;
   tüm aktiflik kontrolleri detect_time üzerinden yapılır.

2. SWING HIGH/LOW STOP LOSS:
   Önceki versiyonlarda SL = son 10 mumun min/max'ı.
   v8: SL = son onaylanmış swing low (bull) / swing high (bear).
   (strength=2: her iki yanda 2 komşudan düşük/yüksek olmalı)

3. EMA ONAY ADIMI (Step 3c):
   Şemadaki üçüncü onay seçeneği eklendi:
   Bull → fiyat kapanışı EMA100 VE EMA200 üstünde mi?
   Bear → fiyat kapanışı EMA100 VE EMA200 altında mı?
   Sinyal kaynağı: 'EMA_Onay'

4. RİSK %0.5 (önce %1):
   RISK = 0.005  ($10,000 başlangıç → işlem başı $50 risk)

Strateji akışı:
  ADIM 0: EMA100 > EMA200 (trend kapısı/yön)
  ADIM 1: Taze 1H FVG'de fiyat var mı? (detect_time kontrolü)
  ADIM 2: Son 1 saatte 5M MSC var mı?
  ADIM 3: Onay — aşağıdakilerden biri:
    3a: RSI diverjansı (son 10 mum)
    3b: Taze 5dk FVG (son 60dk, detect_time kontrolü)
    3c: Fiyat > EMA100 VE EMA200 (bull) / < EMA100 VE EMA200 (bear)
  GİRİŞ : Sonraki mumun açılışından
  SL    : Son swing low/high × (0.9995 / 1.0005)
  TP    : Entry ± Risk × 2.0  (1:2 RR)
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


# ─────────────────────────────────────────────────────────
# YARDIMCI
# ─────────────────────────────────────────────────────────

def normalize_index(df):
    if df is None or df.empty:
        return df
    if hasattr(df.index, 'tz') and df.index.tz is not None:
        df.index = df.index.tz_convert('UTC').tz_localize(None)
    return df

def to_naive(dt):
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt

def flatten_columns(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    return df


# ─────────────────────────────────────────────────────────
# BÖLÜM 1: VERİ İNDİRME
# ─────────────────────────────────────────────────────────

def download_data():
    ticker   = "GC=F"
    end_date = datetime.now()
    start_5m = end_date - timedelta(days=57)
    start_1h = end_date - timedelta(days=90)

    print("=" * 60)
    print("  XAUUSD  |  1:2 RR  |  Day Trade  |  Backtest  v8.0")
    print("=" * 60)
    print(f"\nVeri indiriliyor...")
    print(f"  1H : {start_1h.date()} -> {end_date.date()}")
    print(f"  5dk: {start_5m.date()} -> {end_date.date()}")

    def dl(interval, start):
        df = yf.download(ticker, start=start, end=end_date,
                         interval=interval, progress=False, auto_adjust=True)
        df = flatten_columns(df)
        df = normalize_index(df)
        df.dropna(subset=['Close'], inplace=True)
        return df

    df_1h = dl("1h", start_1h)
    df_5m = dl("5m", start_5m)

    backtest_start = end_date - timedelta(days=30)
    warmup = len(df_5m[df_5m.index < backtest_start])
    bt_cnt = len(df_5m[df_5m.index >= backtest_start])
    print(f"\n  1H : {len(df_1h)} mum")
    print(f"  5dk: {len(df_5m)} mum  (isinma:{warmup} | backtest:{bt_cnt})")
    print(f"  Backtest: {backtest_start.date()} -> {end_date.date()}\n")
    return df_1h, df_5m, backtest_start


# ─────────────────────────────────────────────────────────
# BÖLÜM 2: GÖSTERGELER
# ─────────────────────────────────────────────────────────

def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def calc_rsi(series, period=14):
    d  = series.diff()
    ag = d.clip(lower=0).ewm(com=period-1, min_periods=period).mean()
    al = (-d.clip(upper=0)).ewm(com=period-1, min_periods=period).mean()
    return 100 - 100 / (1 + ag / (al + 1e-10))

def detect_fvg_raw(df, direction='bull', min_gap=0.50):
    """
    Ham FVG listesi üret (mitigasyon kontrolü YOK).
    Her FVG: {index, detect_time, top, bottom, mid, mitigated: False}
    direction='bull': destek FVG (fiyat üstünden geri döner)
    direction='bear': direnç FVG (fiyat altından geri döner)

    NOT: FVG [i-2, i-1, i] üçlüsünden oluşur.
      index       = T[i-1]  (orta mum zamanı)
      detect_time = T[i]    (3. mum kapandıktan SONRA FVG görünür olur)
    Lookahead'i önlemek için her zaman detect_time kullanılmalıdır.
    """
    H = df['High'].values.astype(float)
    L = df['Low'].values.astype(float)
    T = df.index
    out = []
    for i in range(2, len(df)):
        if direction == 'bull':
            gap = L[i] - H[i-2]
            if gap >= min_gap:
                out.append({
                    'index'      : T[i-1],
                    'detect_time': T[i],    # FVG yalnızca bu mum kapandıktan sonra kullanılabilir
                    'top'        : L[i],
                    'bottom'     : H[i-2],
                    'mid'        : (L[i] + H[i-2]) / 2,
                    'direction'  : 'bull',
                    'mitigated'  : False,
                    'created_i'  : i - 1,
                })
        else:
            gap = L[i-2] - H[i]
            if gap >= min_gap:
                out.append({
                    'index'      : T[i-1],
                    'detect_time': T[i],
                    'top'        : L[i-2],
                    'bottom'     : H[i],
                    'mid'        : (L[i-2] + H[i]) / 2,
                    'direction'  : 'bear',
                    'mitigated'  : False,
                    'created_i'  : i - 1,
                })
    return out


def build_fvg_mitigation_map(df_1h, fvg_list):
    """
    Her FVG için hangi 1H mum indeksinde mitige edildiğini hesaplar.

    Bull FVG mitigasyon kuralı:
      FVG oluştuktan sonra ilk CLOSE <= fvg['top']
      (fiyat FVG bölgesinin içine veya altına kapandı)
      → mitigated, kullanılmaz.

    Bear FVG mitigasyon kuralı:
      FVG oluştuktan sonra ilk CLOSE >= fvg['bottom']
      (fiyat FVG bölgesinin içine veya üstüne kapandı)
      → mitigated, kullanılmaz.

    Döndürür: {fvg_index → mitigated_at_time (veya None)}
    """
    C_1h = df_1h['Close'].values.astype(float)
    T_1h = df_1h.index
    n    = len(df_1h)

    mit_map = {}  # fvg['index'] → datetime or None

    for fvg in fvg_list:
        fvg_time = to_naive(fvg['index'])

        # FVG oluşum zamanından SONRAKİ 1H mumlarını tara
        start_i = None
        for j in range(n):
            if to_naive(T_1h[j]) > fvg_time:
                start_i = j
                break

        if start_i is None:
            mit_map[id(fvg)] = None
            continue

        mitigated_at = None
        for j in range(start_i, n):
            close_j = C_1h[j]
            if fvg['direction'] == 'bull':
                # Fiyat FVG'nin içine veya altına kapandı mı?
                if close_j <= fvg['top']:
                    mitigated_at = to_naive(T_1h[j])
                    break
            else:
                # Fiyat FVG'nin içine veya üstüne kapandı mı?
                if close_j >= fvg['bottom']:
                    mitigated_at = to_naive(T_1h[j])
                    break

        mit_map[id(fvg)] = mitigated_at

    return mit_map


def get_active_fvgs(fvg_list, mit_map, current_time, max_age_hours=48):
    """
    Belirli bir zamanda AKTIF (mitige edilmemiş, taze) FVG'leri döndür.

    Aktif FVG kriterleri:
      1. detect_time < current_time  (3. mum kapandı → FVG görünür; LOOKAHEAD YOK)
      2. detect_time > current_time - max_age_hours  (çok eski değil)
      3. mit_map'e göre bu zamana kadar mitige edilmemiş
    """
    t      = to_naive(current_time)
    cutoff = t - timedelta(hours=max_age_hours)
    active = []

    for fvg in fvg_list:
        det_t = to_naive(fvg['detect_time'])
        if det_t >= t:
            continue           # 3. mum henüz kapanmadı → görünmez (lookahead engeli)
        if det_t < cutoff:
            continue           # çok eski

        # Mitigasyon kontrolü
        mit_time = mit_map.get(id(fvg))
        if mit_time is not None and mit_time <= t:
            continue           # bu zamana kadar mitige edilmiş → kullanılmaz

        active.append(fvg)

    return active   # en eski → en yeni sıralı (detect_fvg_raw çıktısı gibi)


def price_in_active_fvg(price, active_fvgs, buf_ratio=0.05):
    """
    Aktif FVG listesindeki herhangi bir FVG'nin bölgesinde
    fiyat var mı?
    buf_ratio=0.05: FVG aralığının ±%5'i buffer.
    """
    for fvg in reversed(active_fvgs):  # en yeni önce
        span = fvg['top'] - fvg['bottom']
        buf  = span * buf_ratio
        if (fvg['bottom'] - buf) <= price <= (fvg['top'] + buf):
            return True
    return False


def detect_msc(df, lookback=10):
    """BOS/CHoCH: son N mumun swing kırılması."""
    df = df.copy()
    df['msc_bull'] = False
    df['msc_bear'] = False
    H = df['High'].values.astype(float)
    L = df['Low'].values.astype(float)
    C = df['Close'].values.astype(float)
    for i in range(lookback, len(df)):
        wh = np.max(H[i-lookback:i])
        wl = np.min(L[i-lookback:i])
        if C[i] > wh and C[i-1] <= wh:
            df.iloc[i, df.columns.get_loc('msc_bull')] = True
        if C[i] < wl and C[i-1] >= wl:
            df.iloc[i, df.columns.get_loc('msc_bear')] = True
    return df


def build_fvg5_mitigation_map(df_5m, fvg5_list):
    """
    5dk FVG mitigasyon haritası.
    Aynı kural: sonraki 5dk mum close FVG içine girerse mitigated.
    """
    C_5m = df_5m['Close'].values.astype(float)
    T_5m = df_5m.index
    n    = len(df_5m)
    mit_map = {}

    for fvg in fvg5_list:
        fvg_time = to_naive(fvg['index'])
        start_i  = None
        for j in range(n):
            if to_naive(T_5m[j]) > fvg_time:
                start_i = j
                break
        if start_i is None:
            mit_map[id(fvg)] = None
            continue

        mitigated_at = None
        for j in range(start_i, n):
            c = C_5m[j]
            if fvg['direction'] == 'bull' and c <= fvg['top']:
                mitigated_at = to_naive(T_5m[j]); break
            elif fvg['direction'] == 'bear' and c >= fvg['bottom']:
                mitigated_at = to_naive(T_5m[j]); break

        mit_map[id(fvg)] = mitigated_at

    return mit_map


def has_active_fvg5_recent(fvg5_list, mit5_map, current_time,
                            window_secs=3600):
    """
    Son 60 dakikada MİTİGE EDİLMEMİŞ 5dk FVG var mı?

    LOOKAHEAD DÜZELTMESİ:
      detect_time < current_time kontrolü kullanılır.
      FVG yalnızca 3. mumu kapandıktan SONRA görünür.
    """
    t      = to_naive(current_time)
    cutoff = t - timedelta(seconds=window_secs)

    for fvg in reversed(fvg5_list):
        det_t = to_naive(fvg['detect_time'])
        if det_t >= t:
            continue           # 3. mum henüz kapanmadı → lookahead engeli
        if det_t < cutoff:
            break              # reversed → daha eskisi de pencere dışı

        # Mitigasyon kontrolü
        mit_time = mit5_map.get(id(fvg))
        if mit_time is not None and mit_time <= t:
            continue           # mitige edilmiş

        return True   # taze 5dk FVG bulundu

    return False


def find_last_swing_low(L, idx, lookback=30, strength=2):
    """
    idx'ten önce onaylanmış en son swing low'u döndürür.

    Swing low tanımı: L[j], her iki yanda 'strength' kadar komşusundan küçük.
    Sağ taraf onayı için j + strength <= idx şartı (lookahead yok).
    Bulunamazsa fallback: son lookback mumun minimum'u.
    """
    end   = idx - strength          # sağ tarafın tam onaylandığı son pozisyon
    start = max(strength, idx - lookback)
    for j in range(end, start - 1, -1):
        if j - strength < 0:
            continue
        left_ok  = all(L[j] < L[j - k] for k in range(1, strength + 1))
        right_ok = all(L[j] < L[j + k] for k in range(1, strength + 1))
        if left_ok and right_ok:
            return float(L[j])
    # Fallback
    return float(np.min(L[max(0, idx - lookback):idx + 1]))


def find_last_swing_high(H, idx, lookback=30, strength=2):
    """
    idx'ten önce onaylanmış en son swing high'ı döndürür.

    Swing high tanımı: H[j], her iki yanda 'strength' kadar komşusundan büyük.
    Sağ taraf onayı için j + strength <= idx şartı (lookahead yok).
    Bulunamazsa fallback: son lookback mumun maksimum'u.
    """
    end   = idx - strength
    start = max(strength, idx - lookback)
    for j in range(end, start - 1, -1):
        if j - strength < 0:
            continue
        left_ok  = all(H[j] > H[j - k] for k in range(1, strength + 1))
        right_ok = all(H[j] > H[j + k] for k in range(1, strength + 1))
        if left_ok and right_ok:
            return float(H[j])
    # Fallback
    return float(np.max(H[max(0, idx - lookback):idx + 1]))


def rsi_divergence(prices, rsi_vals):
    """RSI Uyumsuzluğu (son 10 mum = 50dk)."""
    if len(prices) < 4 or np.any(np.isnan(rsi_vals)):
        return None
    p = prices.astype(float)
    r = rsi_vals.astype(float)
    half = max(2, len(p) // 2)
    il   = int(np.argmin(p[:half]))
    ih   = int(np.argmax(p[:half]))
    if p[-1] < p[il] and r[-1] > r[il]:
        return 'bull'
    if p[-1] > p[ih] and r[-1] < r[ih]:
        return 'bear'
    return None


# ─────────────────────────────────────────────────────────
# BÖLÜM 3: ANA BACKTEST
# ─────────────────────────────────────────────────────────

def run_backtest(df_1h, df_5m, backtest_start,
                 initial_capital=10_000, risk_per_trade=0.01):

    print("Gostergeler hesaplaniyor...")

    df5 = df_5m.copy()
    df5['ema100'] = calc_ema(df5['Close'], 100)
    df5['ema200'] = calc_ema(df5['Close'], 200)
    df5['rsi']    = calc_rsi(df5['Close'], 14)
    df5           = detect_msc(df5, lookback=10)

    df1 = df_1h.copy()

    # ── 1H FVG listesi + mitigasyon haritası ─────────────
    fvg1_bull_raw = detect_fvg_raw(df1, 'bull', min_gap=2.0)
    fvg1_bear_raw = detect_fvg_raw(df1, 'bear', min_gap=2.0)

    print(f"  1H ham FVG -> Bull: {len(fvg1_bull_raw)} | "
          f"Bear: {len(fvg1_bear_raw)}")

    print("  1H FVG mitigasyon hesaplaniyor...", end=' ')
    mit1_bull = build_fvg_mitigation_map(df1, fvg1_bull_raw)
    mit1_bear = build_fvg_mitigation_map(df1, fvg1_bear_raw)

    # Kaç tanesi mitige edildi?
    mit_b = sum(1 for v in mit1_bull.values() if v is not None)
    mit_r = sum(1 for v in mit1_bear.values() if v is not None)
    print(f"tamamlandi. Mitige: bull={mit_b}, bear={mit_r}")

    # ── 5dk FVG listesi + mitigasyon haritası ────────────
    fvg5_bull_raw = detect_fvg_raw(df5, 'bull', min_gap=0.50)
    fvg5_bear_raw = detect_fvg_raw(df5, 'bear', min_gap=0.50)

    print(f"  5dk ham FVG -> Bull: {len(fvg5_bull_raw)} | "
          f"Bear: {len(fvg5_bear_raw)}")
    print("  5dk FVG mitigasyon hesaplaniyor...", end=' ')
    mit5_bull = build_fvg5_mitigation_map(df5, fvg5_bull_raw)
    mit5_bear = build_fvg5_mitigation_map(df5, fvg5_bear_raw)
    mit5_b = sum(1 for v in mit5_bull.values() if v is not None)
    mit5_r = sum(1 for v in mit5_bear.values() if v is not None)
    print(f"tamamlandi. Mitige: bull={mit5_b}, bear={mit5_r}")

    bs         = to_naive(backtest_start)
    bt_mask    = df5.index >= bs
    bt_indices = np.where(bt_mask)[0]
    print(f"\nSinyaller taranıyor... ({len(bt_indices)} mum, "
          f"{bs.date()} sonrasi)\n")

    dbg = {
        'seans_disinda': 0,
        'trend_gate'   : 0,
        'fvg1_yok'     : 0,
        'msc_yok'      : 0,
        'onay_yok'     : 0,
        'risk_filtre'  : 0,
        'uretildi'     : 0,
    }

    trades      = []
    in_trade    = False
    trade_entry = None
    equity      = float(initial_capital)

    C  = df5['Close'].values.astype(float)
    O  = df5['Open'].values.astype(float)
    H  = df5['High'].values.astype(float)
    L  = df5['Low'].values.astype(float)
    E1 = df5['ema100'].values.astype(float)
    E2 = df5['ema200'].values.astype(float)
    RS = df5['rsi'].values.astype(float)
    MB = df5['msc_bull'].values
    MR = df5['msc_bear'].values
    TM = df5.index

    for idx in bt_indices:
        if idx + 1 >= len(df5):
            break

        # ── Açık işlem: HIGH/LOW ile TP/SL kontrolü ────
        if in_trade:
            d  = trade_entry['direction']
            tp = trade_entry['tp']
            sl = trade_entry['sl']

            hit_tp = (H[idx] >= tp) if d == 'bull' else (L[idx] <= tp)
            hit_sl = (L[idx] <= sl) if d == 'bull' else (H[idx] >= sl)

            if hit_sl and hit_tp:
                hit_tp = False   # aynı mumda ikisi → SL önce

            if hit_tp or hit_sl:
                mult   = trade_entry['rr'] if hit_tp else -1.0
                dollar = mult * trade_entry['risk_dollar']
                equity += dollar
                trade_entry.update({
                    'exit_price': tp if hit_tp else sl,
                    'exit_time' : TM[idx],
                    'result'    : 'WIN' if hit_tp else 'LOSS',
                    'pnl_dollar': round(dollar, 2),
                    'equity'    : round(equity, 2),
                })
                trades.append(trade_entry.copy())
                in_trade = False
            continue

        # ── Yeni sinyal ────────────────────────────────
        cur_time  = TM[idx]
        cur_close = C[idx]
        hour      = cur_time.hour

        if not (7 <= hour <= 17):
            dbg['seans_disinda'] += 1
            continue

        t  = to_naive(cur_time)
        e1 = E1[idx]
        e2 = E2[idx]

        # ── ADIM 0: TREND GATE ─────────────────────────
        bull_trend = e1 > e2
        bear_trend = e1 < e2
        if not bull_trend and not bear_trend:
            dbg['trend_gate'] += 1
            continue

        candidate_dirs = []
        if bull_trend: candidate_dirs.append('bull')
        if bear_trend: candidate_dirs.append('bear')

        # ── ADIM 1: TAZE 1H FVG İÇİNDE Mİ? ────────────
        # [v7 KRİTİK DEĞİŞİKLİK]
        # Her yön için:
        #   a) O ana kadar mitige edilmemiş 1H FVG'leri al
        #   b) Fiyat bu FVG'lerden birinin içinde mi?
        valid_dirs = []
        for d in candidate_dirs:
            fvg1_raw = fvg1_bull_raw if d == 'bull' else fvg1_bear_raw
            mit1     = mit1_bull     if d == 'bull' else mit1_bear

            active_fvgs = get_active_fvgs(
                fvg1_raw, mit1, t, max_age_hours=48
            )

            if price_in_active_fvg(cur_close, active_fvgs, buf_ratio=0.05):
                valid_dirs.append(d)

        if not valid_dirs:
            dbg['fvg1_yok'] += 1
            continue

        # ── ADIM 2: SON 1 SAATTE MSC VAR MI? ──────────
        ws = max(0, idx - 12)
        confirmed_dirs = []
        for d in valid_dirs:
            arr = MB if d == 'bull' else MR
            if np.any(arr[ws:idx+1]):
                confirmed_dirs.append(d)

        if not confirmed_dirs:
            dbg['msc_yok'] += 1
            continue

        # ── ADIM 3: ONAY ───────────────────────────────
        found = False
        for direction in confirmed_dirs:

            signal_source = None

            # 3a: RSI Diverjans (son 10 mum = 50dk)
            sl_ = max(0, idx - 10)
            div = rsi_divergence(C[sl_:idx+1], RS[sl_:idx+1])
            if direction == 'bull' and div == 'bull':
                signal_source = 'RSI_Divergence'
            elif direction == 'bear' and div == 'bear':
                signal_source = 'RSI_Divergence'

            # 3b: Son 60dk'da MİTİGE EDİLMEMİŞ 5dk FVG
            # [v7 KRİTİK DEĞİŞİKLİK] + [v8: detect_time lookahead fix]
            if signal_source is None:
                fvg5_raw = fvg5_bull_raw if direction == 'bull' else fvg5_bear_raw
                mit5     = mit5_bull     if direction == 'bull' else mit5_bear
                if has_active_fvg5_recent(fvg5_raw, mit5, t, window_secs=3600):
                    signal_source = 'FVG_5m'

            # 3c: Fiyat hem EMA100 hem EMA200 üstünde mi? (bull)
            #      Fiyat hem EMA100 hem EMA200 altında mı?  (bear)
            # [v8: şema Step 4c]
            if signal_source is None:
                if direction == 'bull' and cur_close > e1 and cur_close > e2:
                    signal_source = 'EMA_Onay'
                elif direction == 'bear' and cur_close < e1 and cur_close < e2:
                    signal_source = 'EMA_Onay'

            if signal_source is None:
                continue

            # ── ADIM 4: GİRİŞ / SL / TP ───────────────
            entry = O[idx + 1]

            if direction == 'bull':
                # Son onaylanmış swing low (son 30 mum, strength=2)
                sl_  = find_last_swing_low(L, idx, lookback=30, strength=2) * 0.9995
                risk = abs(entry - sl_)
                if risk < 0.50 or risk > 150:
                    dbg['risk_filtre'] += 1; continue
                tp_ = entry + risk * 2.0
            else:
                # Son onaylanmış swing high (son 30 mum, strength=2)
                sl_  = find_last_swing_high(H, idx, lookback=30, strength=2) * 1.0005
                risk = abs(sl_ - entry)
                if risk < 0.50 or risk > 150:
                    dbg['risk_filtre'] += 1; continue
                tp_ = entry - risk * 2.0

            risk_pct = risk / entry * 100
            if risk_pct > 2.0:
                dbg['risk_filtre'] += 1; continue

            if direction == 'bull' and tp_ <= entry:
                dbg['risk_filtre'] += 1; continue
            if direction == 'bear' and tp_ >= entry:
                dbg['risk_filtre'] += 1; continue

            risk_dollar = equity * risk_per_trade
            dbg['uretildi'] += 1

            trade_entry = {
                'entry_time'   : cur_time,
                'exit_time'    : None,
                'direction'    : direction,
                'signal_source': signal_source,
                'entry_price'  : round(entry, 2),
                'sl'           : round(sl_, 2),
                'tp'           : round(tp_, 2),
                'risk'         : round(risk, 2),
                'risk_pct'     : round(risk_pct, 4),
                'risk_dollar'  : round(risk_dollar, 2),
                'rr'           : 2.0,
                'exit_price'   : None,
                'result'       : None,
                'pnl_dollar'   : 0.0,
                'equity'       : round(equity, 2),
            }
            in_trade = True
            found    = True
            break

        if not found:
            dbg['onay_yok'] += 1

    # Kapanmamış işlem
    if in_trade and trade_entry:
        trade_entry.update({
            'exit_price': float(C[-1]),
            'exit_time' : TM[-1],
            'result'    : 'OPEN',
        })
        trades.append(trade_entry.copy())

    df_t   = pd.DataFrame(trades)
    total  = len(df_t)
    wins   = len(df_t[df_t['result']=='WIN'])  if total else 0
    losses = len(df_t[df_t['result']=='LOSS']) if total else 0
    opentr = len(df_t[df_t['result']=='OPEN']) if total else 0

    print(f"  FİLTRE ANALİZİ:")
    print(f"    Seans dışı           : {dbg['seans_disinda']:>6}")
    print(f"    Trend gate (EMA)     : {dbg['trend_gate']:>6}")
    print(f"    Taze 1H FVG yok      : {dbg['fvg1_yok']:>6}")
    print(f"    MSC yok (1 saat)     : {dbg['msc_yok']:>6}")
    print(f"    Onay yok (RSI+FVG)   : {dbg['onay_yok']:>6}")
    print(f"    Risk filtresi        : {dbg['risk_filtre']:>6}")
    print(f"\n  SONUÇ: {total} işlem "
          f"({wins} WIN | {losses} LOSS | {opentr} AÇIK)")
    return df_t


# ─────────────────────────────────────────────────────────
# BÖLÜM 4: PERFORMANS ANALİZİ
# ─────────────────────────────────────────────────────────

def analyze_performance(trades_df, initial_capital=10_000):
    if trades_df.empty:
        print("Hiç işlem bulunamadı!"); return None

    done = trades_df[trades_df['result'].isin(['WIN','LOSS'])].copy()
    if done.empty:
        print("Tamamlanmış işlem yok."); return None

    total  = len(done)
    wins   = int((done['result']=='WIN').sum())
    losses = int((done['result']=='LOSS').sum())
    wr     = wins / total * 100

    done['cum_pnl']      = done['pnl_dollar'].cumsum()
    done['equity_curve'] = initial_capital + done['cum_pnl']
    peak   = done['equity_curve'].cummax()
    dd     = (peak - done['equity_curve']) / peak * 100
    max_dd = float(dd.max())

    net = float(done['pnl_dollar'].sum())
    ret = net / initial_capital * 100
    aw  = float(done.loc[done['result']=='WIN',  'pnl_dollar'].mean())
    al_ = float(done.loc[done['result']=='LOSS', 'pnl_dollar'].mean())
    tw  = float(done.loc[done['result']=='WIN',  'pnl_dollar'].sum())
    tl  = float(abs(done.loc[done['result']=='LOSS','pnl_dollar'].sum()))
    pf  = round(tw/tl, 2) if tl > 0 else float('inf')

    done['entry_time'] = pd.to_datetime(done['entry_time'])
    daily  = done.set_index('entry_time').resample('D')['pnl_dollar'].sum()
    sharpe = float((daily.mean()/daily.std()*np.sqrt(252)) if daily.std()>0 else 0)

    seq = done['result'].values
    max_c = cur_c = 0
    for r in seq:
        cur_c = cur_c+1 if r=='LOSS' else 0
        max_c = max(max_c, cur_c)

    sig_d = done['signal_source'].value_counts()
    dir_d = done.groupby('direction').agg(
        islem=('result','count'),
        win  =('result', lambda x: (x=='WIN').sum()),
        pnl  =('pnl_dollar','sum')
    )

    SEP = "=" * 60
    print(f"\n{SEP}")
    print("  XAUUSD | 1:2 RR | Day Trade | 1 Aylık Backtest v8.0")
    print(f"  Dönem  : {done['entry_time'].min().date()}  ->  "
          f"{done['entry_time'].max().date()}")
    print(SEP)
    print(f"\n  GENEL")
    print(f"    Toplam İşlem          : {total}")
    print(f"    Kazanç                : {wins:3d}  (%{wr:.1f})")
    print(f"    Kayıp                 : {losses:3d}  (%{100-wr:.1f})")
    print(f"\n  KARLILIK  ($10,000 başlangıç | %0.5 risk/işlem)")
    print(f"    Net PnL               : ${net:>+9,.2f}")
    print(f"    Toplam Getiri         : %{ret:>+7.2f}")
    print(f"    Son Sermaye           : ${initial_capital+net:>9,.2f}")
    print(f"\n  RİSK")
    print(f"    Maks Drawdown         : %{max_dd:.2f}")
    print(f"    Profit Factor         : {pf}")
    print(f"    Sharpe Ratio          : {sharpe:.2f}")
    print(f"    Ort Kazanç/İşlem      : ${aw:>+8.2f}")
    print(f"    Ort Kayıp/İşlem       : ${al_:>+8.2f}")
    print(f"    Maks Ardışık Kayıp    : {max_c}")
    print(f"\n  SİNYAL KAYNAKLARI")
    for src, cnt in sig_d.items():
        w_s   = int(((done['signal_source']==src)&(done['result']=='WIN')).sum())
        pnl_s = float(done.loc[done['signal_source']==src,'pnl_dollar'].sum())
        print(f"    {src:<22}: {cnt:3d} işlem | %{w_s/cnt*100:.0f} WR | ${pnl_s:>+8.2f}")
    print(f"\n  YÖN ANALİZİ")
    for d, row in dir_d.iterrows():
        lbl = "LONG (Bull) " if d=='bull' else "SHORT (Bear)"
        print(f"    {lbl}: {int(row['islem']):3d} işlem | "
              f"%{row['win']/row['islem']*100:.0f} WR | ${row['pnl']:>+8.2f}")
    print(f"\n  HAFTALIK PERFORMANS")
    done['week'] = done['entry_time'].dt.to_period('W')
    weekly = done.groupby('week').agg(
        islem=('result','count'),
        kar  =('pnl_dollar','sum'),
        wr_p =('result', lambda x: (x=='WIN').mean()*100)
    )
    for week, row in weekly.iterrows():
        bar  = "█" * min(int(abs(row['kar'])/10), 35)
        sign = "+" if row['kar']>=0 else ""
        print(f"    {week}: {int(row['islem']):2d} işlem | "
              f"${sign}{row['kar']:>+7.0f} | %{row['wr_p']:4.0f} WR | {bar}")
    print(f"\n{SEP}")
    return done


# ─────────────────────────────────────────────────────────
# BÖLÜM 5: GRAFİKLER
# ─────────────────────────────────────────────────────────

def plot_results(done, initial_capital=10_000,
                 out='xauusd_backtest_raporu.png'):
    try:
        import matplotlib; matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
        from matplotlib.ticker import FuncFormatter

        BG='#0d0d1a'; PN='#12122a'; G='#00e5a0'
        R='#ff3f5b'; GD='#ffd700'; TX='#d0d0e0'; GR='#1e1e3a'

        def sty(ax):
            ax.set_facecolor(PN)
            ax.tick_params(colors=TX, labelsize=8)
            ax.xaxis.label.set_color(TX); ax.yaxis.label.set_color(TX)
            ax.title.set_color(TX)
            for s in ax.spines.values(): s.set_edgecolor(GR)
            ax.grid(True, color=GR, lw=0.4, alpha=0.5)

        fig = plt.figure(figsize=(20, 14), facecolor=BG)
        dr  = (f"{done['entry_time'].min().date()} -> "
               f"{done['entry_time'].max().date()}")
        fig.suptitle(
            f'XAUUSD  |  1:2 RR  |  Day Trade  |  Backtest v8.0  |  {dr}',
            color=GD, fontsize=13, fontweight='bold', y=0.97)
        gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.48, wspace=0.32)

        eq = initial_capital + done['pnl_dollar'].cumsum()
        pk = eq.cummax()
        x  = np.arange(len(eq))

        ax1 = fig.add_subplot(gs[0, :])
        ax1.fill_between(x, initial_capital, eq.values,
                         where=eq.values>=initial_capital, color=G, alpha=0.2)
        ax1.fill_between(x, initial_capital, eq.values,
                         where=eq.values<initial_capital,  color=R, alpha=0.3)
        ax1.plot(x, eq.values, color=G, lw=2.0, label='Equity')
        ax1.plot(x, pk.values, color=GD, lw=0.9, ls='--', alpha=0.6, label='Peak')
        ax1.fill_between(x, eq.values, pk.values,
                         color=R, alpha=0.12, label='Drawdown')
        ax1.axhline(initial_capital, color='white', lw=0.6, ls=':')
        wm = done['result'].values=='WIN'
        lm = done['result'].values=='LOSS'
        ax1.scatter(x[wm], eq.values[wm], color=G, s=40, zorder=5, alpha=0.85)
        ax1.scatter(x[lm], eq.values[lm], color=R, s=40, zorder=5,
                    alpha=0.85, marker='v')
        ax1.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f'${v:,.0f}'))
        ax1.set_title('Equity Curve  |  Yeşil=WIN  Kırmızı=LOSS', fontweight='bold')
        ax1.set_xlabel('İşlem #'); ax1.set_ylabel('Sermaye ($)')
        ax1.legend(facecolor=PN, labelcolor=TX, fontsize=8, loc='upper left')
        sty(ax1)

        ax2 = fig.add_subplot(gs[1, :2])
        dc  = done.copy()
        dc['week'] = dc['entry_time'].dt.to_period('W')
        wp  = dc.groupby('week')['pnl_dollar'].sum()
        cw  = [G if v>=0 else R for v in wp.values]
        bs2 = ax2.bar(range(len(wp)), wp.values, color=cw, alpha=0.85, width=0.6)
        ax2.axhline(0, color='white', lw=0.5)
        for b, v in zip(bs2, wp.values):
            ax2.text(b.get_x()+b.get_width()/2, v+(3 if v>=0 else -15),
                     f'${v:+,.0f}', ha='center', va='bottom', fontsize=8, color=TX)
        ax2.set_xticks(range(len(wp)))
        ax2.set_xticklabels([str(w) for w in wp.index], rotation=20, fontsize=8)
        ax2.set_title('Haftalık Net Kar / Zarar ($)', fontweight='bold')
        ax2.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f'${v:,.0f}'))
        sty(ax2)

        ax3 = fig.add_subplot(gs[1, 2])
        wn = int((done['result']=='WIN').sum())
        ln = int((done['result']=='LOSS').sum())
        _, _, ats = ax3.pie(
            [wn, ln], labels=[f'WIN\n{wn}', f'LOSS\n{ln}'],
            colors=[G, R], autopct='%1.1f%%', startangle=90,
            wedgeprops={'edgecolor':BG,'linewidth':2.5},
            textprops={'color':TX,'fontsize':10})
        for at in ats: at.set_color('white'); at.set_fontsize(10)
        ax3.set_title('Win / Loss Oranı', fontweight='bold')
        sty(ax3)

        ax4 = fig.add_subplot(gs[2, 0])
        sig = done['signal_source'].value_counts()
        cs  = ['#7bed9f','#70a1ff','#ffa502'][:len(sig)]
        b4  = ax4.bar(sig.index, sig.values, color=cs, alpha=0.85)
        for b, v in zip(b4, sig.values):
            ax4.text(b.get_x()+b.get_width()/2, v+0.2,
                     str(v), ha='center', fontsize=9, color=TX)
        ax4.set_title('Sinyal Kaynakları', fontweight='bold')
        ax4.set_ylabel('İşlem Sayısı')
        plt.setp(ax4.get_xticklabels(), rotation=10, fontsize=8)
        sty(ax4)

        ax5 = fig.add_subplot(gs[2, 1])
        pos = done.loc[done['pnl_dollar']>0,'pnl_dollar'].values
        neg = done.loc[done['pnl_dollar']<0,'pnl_dollar'].values
        if len(pos): ax5.hist(pos, bins=12, color=G, alpha=0.75, label='Kazanç')
        if len(neg): ax5.hist(neg, bins=12, color=R, alpha=0.75, label='Kayıp')
        ax5.axvline(0, color='white', lw=0.6)
        ax5.set_title('PnL Dağılımı ($)', fontweight='bold')
        ax5.set_xlabel('PnL ($)')
        ax5.legend(facecolor=PN, labelcolor=TX, fontsize=8)
        sty(ax5)

        ax6 = fig.add_subplot(gs[2, 2])
        dg  = done.groupby('direction')['pnl_dollar'].sum()
        dwr = done.groupby('direction').apply(
            lambda x: (x['result']=='WIN').mean()*100)
        dlbl=[]; dv=[]; dc6=[]
        for d in dg.index:
            dlbl.append(f"{'LONG' if d=='bull' else 'SHORT'}\n%{dwr[d]:.0f} WR")
            dv.append(float(dg[d]))
            dc6.append(G if d=='bull' else R)
        b6 = ax6.bar(dlbl, dv, color=dc6, alpha=0.85, width=0.5)
        for b, v in zip(b6, dv):
            ax6.text(b.get_x()+b.get_width()/2, v+(5 if v>=0 else -25),
                     f'${v:+,.0f}', ha='center', fontsize=9, color=TX)
        ax6.axhline(0, color='white', lw=0.5)
        ax6.set_title('Long vs Short PnL', fontweight='bold')
        ax6.set_ylabel('PnL ($)')
        ax6.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f'${v:,.0f}'))
        sty(ax6)

        plt.savefig(out, dpi=150, bbox_inches='tight', facecolor=BG)
        plt.close()
        print(f"\nGrafik kaydedildi -> {out}")
    except Exception as e:
        print(f"Grafik oluşturulamadı: {e}")


# ─────────────────────────────────────────────────────────
# BÖLÜM 6: CSV
# ─────────────────────────────────────────────────────────

def save_csv(df, filename='xauusd_islem_logu.csv'):
    if df.empty: return
    cols = ['entry_time','exit_time','direction','signal_source',
            'entry_price','sl','tp','exit_price',
            'risk','risk_pct','risk_dollar','result','pnl_dollar','equity']
    df[[c for c in cols if c in df.columns]].to_csv(
        filename, index=False, float_format='%.4f')
    print(f"Log kaydedildi -> {filename}")


# ─────────────────────────────────────────────────────────
# ANA
# ─────────────────────────────────────────────────────────

if __name__ == '__main__':
    CAPITAL = 10_000
    RISK    = 0.005   # %0.5 risk/işlem

    df_1h, df_5m, bt_start = download_data()
    if df_5m.empty or df_1h.empty:
        print("Veri indirilemedi."); exit(1)

    trades = run_backtest(df_1h, df_5m, bt_start,
                          initial_capital=CAPITAL, risk_per_trade=RISK)
    if trades.empty:
        print("Sinyal üretilemedi."); exit(0)

    done = analyze_performance(trades, initial_capital=CAPITAL)
    if done is not None and not done.empty:
        plot_results(done, initial_capital=CAPITAL)
        save_csv(trades)

    print("\nBacktest tamamlandı!")
