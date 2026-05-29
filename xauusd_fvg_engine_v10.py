"""
XAUUSD FVG Strategy - Engine v10.0
====================================
Wall Street Grade Backtest & Signal Engine

STRATEJİ AKIŞI (Şemaya Birebir):
──────────────────────────────────
ADIM 0: Haftalık Bias (weekly_bias.json) — bull veya bear?
  → Dosyada o hafta için giriş yoksa → işlem yapma.
  → Giriş varsa sadece o yönde işlem aç.

ADIM 1: Fiyat 1H FVG'ye temas etti mi?
  → Hayır: İşlem alma  → Evet : ADIM 2

ADIM 2: Temas sonrası beklenti yönünde 5dk MSC (BOS/CHoCH) geldi mi?
  → Hayır: İşlem alma  → Evet : ADIM 3

ADIM 3: Onay (aşağıdakilerden BİRİ yeterli):
  3a: RSI'da beklenti yönünde uyumsuzluk? (5dk, son 10 mum)
  3b: MSC sırasında 5dk FVG oluşumu mevcut? (son 60dk)
  3c: Fiyat mum kapanışları EMA100 VE EMA200 üstünde/altında? (5dk)
  Hiçbiri → İşlem alma

RİSK: 1:2 RR | %0.5 risk/işlem | ATR-adaptive Swing SL | London+NY seansı

v10 YENİLİKLERİ:
  1. WeeklyBiasProvider — weekly_bias.json okur; ISO hafta → bull/bear
  2. significant_swing_low / significant_swing_high — ATR anlamlılık filtresi
     + adaptive strength (2-5) + skor bazlı en iyi swing seçimi
"""

import os
import json
import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
import warnings
warnings.filterwarnings('ignore')


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 0: VERİ YAPILARI
# ═══════════════════════════════════════════════════════════════════════════

_fvg_counter = 0

def _next_fvg_id() -> int:
    global _fvg_counter
    _fvg_counter += 1
    return _fvg_counter


@dataclass
class FVG:
    """Fair Value Gap — tek bir boşluk kaydı."""
    fvg_id        : int
    timeframe     : str          # '1h' | '5m'
    direction     : str          # 'bull' | 'bear'
    index         : Any          # orta mum zamanı
    detect_time   : Any          # 3. mum kapandıktan sonra görünür (lookahead engeli)
    top           : float
    bottom        : float
    mid           : float
    gap_size      : float
    gap_atr_ratio : float        # gap / ATR(14) — kalite göstergesi
    momentum      : float        # orta mum body/range oranı
    quality_score : float        # 0–100 kompozit skor
    mitigated     : bool  = False
    mitigated_at  : Any   = None
    created_i     : int   = 0


@dataclass
class BreakerBlock:
    """1H MSB olayından türeyen breaker block (order block kırılımı)."""
    block_id      : int
    direction     : str   # 'bull' → kırılan swing-high, geri çekilmede LONG; 'bear' → kırılan swing-low, geri çekilmede SHORT
    break_time    : Any   # MSB mumunun zamanı (index open time)
    detect_time   : Any   # görünür olduğu an = MSB mumu kapandıktan sonra
    high          : float # MSB mumunun yüksek değeri
    low           : float # MSB mumunun düşük değeri
    swing_level   : float # kırılan swing seviyesi
    quality_score : float # 0–100


@dataclass
class MSCSignal:
    """Market Structure Change (BOS / CHoCH) kaydı."""
    time           : Any
    direction      : str          # 'bull' | 'bear'
    idx            : int
    swing_level    : float
    close_at_break : float
    momentum_score : float        # 0–1
    body_ratio     : float


@dataclass
class MSBEvent:
    """
    5M Market Structure Break olayı — şemanın 3. adımındaki tetikleyici.
    Üç tür: 'breaker', 'mitigation', 'three_vol'.
    Lookahead engeli: olay confirm_idx mumunun KAPANIŞINDA onaylanır.
    """
    msb_type    : str    # 'breaker' | 'mitigation' | 'three_vol'
    direction   : str    # 'bull' | 'bear'
    confirm_idx : int    # onay mumunun indeksi (kapanış)
    detect_time : Any    # TM[confirm_idx]
    stop_price  : float  # tür-bazlı stop (swing veya 2. mum wick)
    swing_level : float = 0.0
    quality     : float = 0.0


@dataclass
class HarmonicSignal:
    """
    Harmonik desen (pinescript portu) — herhangi bir zaman diliminde.
    PRZ (Potential Reversal Zone) bir fiyat aralığıdır; taze 1H FVG ile
    çakışırsa bias'sız işlem tetikler. Lookahead: detect_time = C-pivot
    onay barının kapanışı (pivot bar + strength + TF offset).
    """
    direction   : str    # 'bull' | 'bear'
    pattern     : str    # 'Gartley' | 'Bat' | ... | 'Cypher'
    timeframe   : str    # '5m' | '15m' | '1h' | '4h'
    prz_low     : float
    prz_high    : float
    detect_time : Any
    expiry_time : Any
    conf        : float = 0.0


@dataclass
class TradeSignal:
    """Tam onaylı trade sinyali."""
    entry_time        : Any
    direction         : str
    trigger_fvg       : Optional[FVG]           # 1H FVG tetikleyici (ya da None)
    confirmation_type : str       # 'EMA' | 'RSI' | 'EMA+RSI'
    confidence        : float     # 0–100
    msb_type          : str = ''  # 'breaker' | 'mitigation' | 'three_vol'
    confluence_count  : int = 1   # 1 → 0.5R, 2 → 1R
    stop_price        : float = 0.0
    risk_fraction     : float = 0.005
    msc_signal        : Optional[MSCSignal] = None
    trigger_bb        : Optional['BreakerBlock'] = None
    harmonic          : Optional['HarmonicSignal'] = None
    rsi_div_type      : Optional[str] = None
    fvg5_quality      : float = 0.0
    ema_distance_pct  : float = 0.0


@dataclass
class Trade:
    """Gerçekleşmiş işlem kaydı."""
    trade_id    : int
    signal      : TradeSignal
    entry_price : float
    sl          : float
    tp          : float
    risk        : float
    risk_pct    : float
    risk_dollar : float
    rr            : float = 2.0
    risk_fraction : float = 0.005
    exit_price  : Optional[float] = None
    exit_time   : Optional[Any]   = None
    result      : str   = 'OPEN'
    pnl_dollar  : float = 0.0
    equity_after: float = 0.0


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 1: YARDIMCI FONKSİYONLAR
# ═══════════════════════════════════════════════════════════════════════════

def to_naive(dt):
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt

def normalize_index(df):
    if df is None or df.empty:
        return df
    if hasattr(df.index, 'tz') and df.index.tz is not None:
        df.index = df.index.tz_convert('UTC').tz_localize(None)
    return df

def flatten_columns(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    return df


def resample_ohlcv(df: 'pd.DataFrame', rule: str) -> 'pd.DataFrame':
    """OHLC(V) yeniden örnekleme — harmonik için üst zaman dilimleri (15M, 4H)."""
    agg = {'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'}
    if 'Volume' in df.columns:
        agg['Volume'] = 'sum'
    out = df.resample(rule, label='left', closed='left').agg(agg).dropna()
    return out


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 1b: HAFTALIK BİAS SAĞLAYICI
# ═══════════════════════════════════════════════════════════════════════════

class WeeklyBiasProvider:
    """
    weekly_bias.json dosyasından haftalık bias okur.

    Kullanım:
      - Her Pazar/Pazartesi sabahı weekly_bias.json dosyasını aç
      - O haftanın ISO anahtarını (ör. "2025-W21") gir ve değeri "bull" / "bear" yap
      - Kaydet — kod çalıştırıldığında otomatik yüklenir

    Kurallar:
      - Giriş yoksa o hafta işlem YAPILMAZ
      - "none" yazılırsa da o hafta işlem yapılmaz
      - Sadece "bull" veya "bear" geçerli

    Örnek weekly_bias.json:
      {
        "_aciklama": "ISO hafta: YYYY-W##  Deger: bull | bear | none",
        "2025-W21": "bull",
        "2025-W22": "bear"
      }
    """

    def __init__(self, filepath: str = 'weekly_bias.json'):
        self.filepath = Path(filepath)
        self._data: Dict[str, str] = {}
        self._load()

    def _load(self):
        if self.filepath.exists():
            with open(self.filepath, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            self._data = {
                k: v.strip().lower()
                for k, v in raw.items()
                if not k.startswith('_') and isinstance(v, str)
            }
            valid = {k: v for k, v in self._data.items() if v in ('bull', 'bear')}
            print(f"  Haftalık bias yüklendi: {len(valid)} aktif hafta "
                  f"({self.filepath.name})")
            self._data = valid
        else:
            print(f"  UYARI: {self.filepath} bulunamadı — "
                  f"haftalık bias devre dışı (tüm haftalar atlanır)")

    def get(self, dt: Any) -> Optional[str]:
        """
        Verilen datetime için bias döndür.
        None → o hafta giriş yok → işlem yapma.
        """
        t   = to_naive(dt)
        iso = t.isocalendar()
        key = f"{iso[0]}-W{iso[1]:02d}"
        return self._data.get(key)  # None veya 'bull'/'bear'

    def summary(self) -> str:
        if not self._data:
            return "  Bias: boş / devre dışı"
        lines = [f"  Bias kayıtları: {len(self._data)} hafta"]
        for k, v in sorted(self._data.items()):
            lines.append(f"    {k}: {v.upper()}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 2: VERİ ENGİNİ
# ═══════════════════════════════════════════════════════════════════════════

class DataEngine:
    """Veri indirme, doğrulama ve hazırlama."""

    TICKER  = "GC=F"
    FILE_5M = "xauusd_5m.csv"
    FILE_1H = "xauusd_1h.csv"
    WARMUP_DAYS = 4   # backtest başlangıcı = 5M verinin ilk tarihi + WARMUP

    @staticmethod
    def _load_csv(filepath):
        df = pd.read_csv(filepath, index_col=0, parse_dates=True)
        df = flatten_columns(df)
        df = normalize_index(df)
        df.dropna(subset=['Close'], inplace=True)
        return df

    @staticmethod
    def download(verbose: bool = True):
        if verbose:
            print("═" * 65)
            print("  XAUUSD  │  FVG Strategy Engine  │  v10.0 │  Day Trade")
            print("═" * 65)

        use_csv = os.path.exists(DataEngine.FILE_5M) and os.path.exists(DataEngine.FILE_1H)

        if use_csv:
            if verbose:
                print(f"\n  Yerel CSV bulundu → dosyadan yükleniyor")
            df_1h = DataEngine._load_csv(DataEngine.FILE_1H)
            df_5m = DataEngine._load_csv(DataEngine.FILE_5M)
        else:
            end      = datetime.now()
            start_1h = end - timedelta(days=90)
            start_5m = end - timedelta(days=59)   # Yahoo 5M limiti: max 60 gün
            if verbose:
                print(f"\n  CSV yok → yfinance indiriliyor... ({DataEngine.TICKER})")

            def dl(interval, start):
                df = yf.download(DataEngine.TICKER, start=start, end=end,
                                 interval=interval, progress=False, auto_adjust=True)
                df = flatten_columns(df)
                df = normalize_index(df)
                df.dropna(subset=['Close'], inplace=True)
                return df

            df_1h = dl("1h", start_1h)
            df_5m = dl("5m", start_5m)

        for df, name in [(df_1h, "1H"), (df_5m, "5M")]:
            if df.empty:
                raise ValueError(f"{name}: Veri boş!")
            for col in ['Open', 'High', 'Low', 'Close']:
                if col not in df.columns:
                    raise ValueError(f"{name}: '{col}' sütunu eksik!")

        # Backtest başlangıcı: 5M verinin başından WARMUP_DAYS sonrası
        data_start = df_5m.index.min()
        data_end   = df_5m.index.max()
        bt_start   = to_naive(data_start) + timedelta(days=DataEngine.WARMUP_DAYS)

        if verbose:
            wm = len(df_5m[df_5m.index < bt_start])
            bt = len(df_5m[df_5m.index >= bt_start])
            src = "CSV" if use_csv else "yfinance"
            print(f"  Kaynak: {src}")
            print(f"  1H : {len(df_1h)} mum  ({to_naive(df_1h.index.min()).date()} → {to_naive(df_1h.index.max()).date()})")
            print(f"  5M : {len(df_5m)} mum  (ısınma:{wm}  backtest:{bt})")
            print(f"  Backtest dönemi: {bt_start.date()} → {to_naive(data_end).date()}\n")

        return df_1h, df_5m, bt_start


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 3: İNDİKATÖR ENGİNİ
# ═══════════════════════════════════════════════════════════════════════════

class IndicatorEngine:
    """ATR — değişmeyen temel gösterge. (RSI için bkz. RSIEngine)"""

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        h  = df['High']
        l  = df['Low']
        pc = df['Close'].shift(1)
        tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
        return tr.ewm(span=period, adjust=False).mean()


class RSIEngine:
    """
    Profesyonel RSI motoru: Wilder yumuşatması + pivot-tabanlı
    regular diverjans tespiti.

    Diverjans, gerçek fraktal pivotlar üzerinden hesaplanır (kaba
    yarı-pencere karşılaştırması değil):
      Regular BULL : fiyat daha düşük dip (LL) yaparken RSI daha yüksek dip (HL)
      Regular BEAR : fiyat daha yüksek tepe (HH) yaparken RSI daha düşük tepe (LH)
    """

    @staticmethod
    def wilder(series: pd.Series, period: int = 14) -> pd.Series:
        """Wilder RSI (EWM com=period-1 ile birebir Wilder yumuşatması)."""
        d  = series.diff()
        ag = d.clip(lower=0).ewm(com=period - 1, min_periods=period).mean()
        al = (-d.clip(upper=0)).ewm(com=period - 1, min_periods=period).mean()
        return 100 - 100 / (1 + ag / (al + 1e-10))

    @staticmethod
    def _pivots_low(a: np.ndarray, strength: int = 2) -> List[int]:
        """Fraktal dip indeksleri (lookahead-safe değil — kapalı pencere içinde çağrılır)."""
        idxs = []
        for j in range(strength, len(a) - strength):
            if (all(a[j] < a[j - k] for k in range(1, strength + 1)) and
                    all(a[j] <= a[j + k] for k in range(1, strength + 1))):
                idxs.append(j)
        return idxs

    @staticmethod
    def _pivots_high(a: np.ndarray, strength: int = 2) -> List[int]:
        idxs = []
        for j in range(strength, len(a) - strength):
            if (all(a[j] > a[j - k] for k in range(1, strength + 1)) and
                    all(a[j] >= a[j + k] for k in range(1, strength + 1))):
                idxs.append(j)
        return idxs

    @staticmethod
    def divergence(prices: np.ndarray, rsi_vals: np.ndarray,
                   strength: int = 2) -> Tuple[Optional[str], float]:
        """
        Son iki onaylı pivot üzerinden regular diverjans. (tip, güç 0-1).
        Pencere zaten geçmiş veridir; çağıran taraf lookahead'i yönetir.
        """
        p = np.asarray(prices, dtype=float)
        r = np.asarray(rsi_vals, dtype=float)
        if len(p) < 2 * strength + 3 or np.any(np.isnan(r)):
            return None, 0.0

        # BULL: fiyat dipleri
        lows = RSIEngine._pivots_low(p, strength)
        if len(lows) >= 2:
            i1, i2 = lows[-2], lows[-1]
            if p[i2] < p[i1] and r[i2] > r[i1]:
                price_drop = (p[i1] - p[i2]) / (abs(p[i1]) + 1e-10)
                rsi_lift   = (r[i2] - r[i1]) / 100.0
                strg = min(1.0, (price_drop * 30 + rsi_lift) )
                return 'bull', float(max(0.05, strg))

        # BEAR: fiyat tepeleri
        highs = RSIEngine._pivots_high(p, strength)
        if len(highs) >= 2:
            i1, i2 = highs[-2], highs[-1]
            if p[i2] > p[i1] and r[i2] < r[i1]:
                price_rise = (p[i2] - p[i1]) / (abs(p[i1]) + 1e-10)
                rsi_drop   = (r[i1] - r[i2]) / 100.0
                strg = min(1.0, (price_rise * 30 + rsi_drop))
                return 'bear', float(max(0.05, strg))

        return None, 0.0


class EMAEngine:
    """Çok-periyotlu EMA hesabı ve df'e ekleme."""

    @staticmethod
    def compute(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def add(df: pd.DataFrame, *periods: int, col: str = 'Close') -> pd.DataFrame:
        """Her periyot için df'e ema{period} kolonu ekler, df kopyası döner."""
        df = df.copy()
        for p in periods:
            df[f'ema{p}'] = df[col].ewm(span=p, adjust=False).mean()
        return df


class SwingEngine:
    """
    Lookahead-safe fraktal pivot tespiti.

    Bir pivot j'de ancak her iki tarafta `strength` bar görüldükten
    sonra onaylanır; yani j+strength'inci bardan itibaren görünür hale
    gelir. Bu, backtest sırasında ileriye dönük veri sızmasını engeller.

    `compute()` → her bar için o ana kadar görünür en son onaylı
    swing-high / swing-low fiyatlarını döndürür.

    `best_swing_low/high()` → RiskManager için geriye dönük en anlamlı
    pivot bulma (SL yerleştirme).
    """

    @staticmethod
    def compute(
        H: np.ndarray, L: np.ndarray, atr: np.ndarray,
        strength: int = 2,
        min_atr_mult: float = 0.3,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Returns
        -------
        last_sh : ndarray — her bar için o ana kadar onaylı en son swing-high fiyatı
        last_sl : ndarray — her bar için o ana kadar onaylı en son swing-low  fiyatı
        """
        n = len(H)
        last_sh = np.full(n, np.nan)
        last_sl = np.full(n, np.nan)
        cur_sh  = np.nan
        cur_sl  = np.nan

        for i in range(n):
            j = i - strength         # pivot adayı — sağı artık tam görünür
            if j >= strength:
                atr_j = max(float(atr[j]), 1e-6)

                # Swing high kontrolü
                is_sh = (all(H[j] > H[j - k] for k in range(1, strength + 1)) and
                         all(H[j] > H[j + k] for k in range(1, strength + 1)))
                if is_sh:
                    ld = float(H[j]) - float(np.max(H[j - strength:j]))
                    rd = float(H[j]) - float(np.max(H[j + 1:j + strength + 1]))
                    if (ld + rd) / 2 >= min_atr_mult * atr_j:
                        cur_sh = float(H[j])

                # Swing low kontrolü
                is_sl = (all(L[j] < L[j - k] for k in range(1, strength + 1)) and
                         all(L[j] < L[j + k] for k in range(1, strength + 1)))
                if is_sl:
                    ld = float(np.min(L[j - strength:j])) - float(L[j])
                    rd = float(np.min(L[j + 1:j + strength + 1])) - float(L[j])
                    if (ld + rd) / 2 >= min_atr_mult * atr_j:
                        cur_sl = float(L[j])

            # Fallback: görünür pivot yoksa son 20 barın ekstrem değeri
            last_sh[i] = cur_sh if not np.isnan(cur_sh) else float(np.max(H[max(0, i - 20):i + 1]))
            last_sl[i] = cur_sl if not np.isnan(cur_sl) else float(np.min(L[max(0, i - 20):i + 1]))

        return last_sh, last_sl

    @staticmethod
    def best_swing_low(
        L: np.ndarray, H: np.ndarray, atr: np.ndarray,
        idx: int,
        lookback: int = 50,
        min_strength: int = 2,
        max_strength: int = 5,
        min_atr_mult: float = 0.3,
    ) -> Tuple[float, float]:
        """Geriye dönük en anlamlı swing-low (SL yerleştirme). (price, score)"""
        window_end   = idx - min_strength
        window_start = max(max_strength, idx - lookback)
        candidates: List[Tuple[float, float]] = []
        for j in range(window_end, window_start - 1, -1):
            for s in range(max_strength, min_strength - 1, -1):
                if j - s < 0 or j + s > idx:
                    continue
                if not (all(L[j] < L[j - k] for k in range(1, s + 1)) and
                        all(L[j] < L[j + k] for k in range(1, s + 1))):
                    continue
                atr_val = max(float(atr[j]), 1e-6)
                ld = float(np.min(L[j - s:j]))        - float(L[j])
                rd = float(np.min(L[j + 1:j + s + 1])) - float(L[j])
                depth = (ld + rd) / 2.0
                if depth < min_atr_mult * atr_val:
                    continue
                candidates.append((float(L[j]), s + depth / atr_val))
                break
        if candidates:
            return max(candidates, key=lambda x: x[1])
        return float(np.min(L[max(0, idx - lookback):idx + 1])), 0.0

    @staticmethod
    def best_swing_high(
        H: np.ndarray, L: np.ndarray, atr: np.ndarray,
        idx: int,
        lookback: int = 50,
        min_strength: int = 2,
        max_strength: int = 5,
        min_atr_mult: float = 0.3,
    ) -> Tuple[float, float]:
        """Geriye dönük en anlamlı swing-high (SL yerleştirme). (price, score)"""
        window_end   = idx - min_strength
        window_start = max(max_strength, idx - lookback)
        candidates: List[Tuple[float, float]] = []
        for j in range(window_end, window_start - 1, -1):
            for s in range(max_strength, min_strength - 1, -1):
                if j - s < 0 or j + s > idx:
                    continue
                if not (all(H[j] > H[j - k] for k in range(1, s + 1)) and
                        all(H[j] > H[j + k] for k in range(1, s + 1))):
                    continue
                atr_val = max(float(atr[j]), 1e-6)
                ld = float(H[j]) - float(np.max(H[j - s:j]))
                rd = float(H[j]) - float(np.max(H[j + 1:j + s + 1]))
                depth = (ld + rd) / 2.0
                if depth < min_atr_mult * atr_val:
                    continue
                candidates.append((float(H[j]), s + depth / atr_val))
                break
        if candidates:
            return max(candidates, key=lambda x: x[1])
        return float(np.max(H[max(0, idx - lookback):idx + 1])), 0.0


class MSBEngine:
    """
    Market Structure Break (BOS / CHoCH) tespiti.

    SwingEngine'in onaylı pivot dizilerini kullanır:
      Bull BOS  → close, bir önceki barın son onaylı swing-high'ını yukarı kırar
      Bear BOS  → close, bir önceki barın son onaylı swing-low'unu  aşağı kırar

    Çıktı kolonları (BacktestEngine sözleşmesi değişmez):
      msc_bull, msc_bear, msc_bull_mom, msc_bear_mom
    """

    @staticmethod
    def compute(
        df: pd.DataFrame,
        atr_series: pd.Series,
        strength: int = 2,
        min_atr_mult: float = 0.3,
    ) -> pd.DataFrame:
        df   = df.copy()
        H    = df['High'].values.astype(float)
        L    = df['Low'].values.astype(float)
        C    = df['Close'].values.astype(float)
        atr  = atr_series.values.astype(float)
        n    = len(df)

        last_sh, last_sl = SwingEngine.compute(H, L, atr, strength, min_atr_mult)

        msc_bull     = np.zeros(n, dtype=bool)
        msc_bear     = np.zeros(n, dtype=bool)
        msc_bull_mom = np.zeros(n, dtype=float)
        msc_bear_mom = np.zeros(n, dtype=float)

        for i in range(1, n):
            atr_i = max(float(atr[i]), 1e-6)
            sh    = last_sh[i - 1]   # bir önceki barda görünür son swing-high
            sl    = last_sl[i - 1]   # bir önceki barda görünür son swing-low

            # Bull BOS: close önceki swing-high'ı ilk kez yukarı kırdı
            if C[i] > sh and C[i - 1] <= sh:
                msc_bull[i]     = True
                msc_bull_mom[i] = min(1.0, (C[i] - sh) / atr_i)

            # Bear BOS: close önceki swing-low'u ilk kez aşağı kırdı
            if C[i] < sl and C[i - 1] >= sl:
                msc_bear[i]     = True
                msc_bear_mom[i] = min(1.0, (sl - C[i]) / atr_i)

        df['msc_bull']     = msc_bull
        df['msc_bear']     = msc_bear
        df['msc_bull_mom'] = msc_bull_mom
        df['msc_bear_mom'] = msc_bear_mom
        return df


class MSB5MEngine:
    """
    5M MSB (Market Structure Break) tespiti — şemanın 3. adım tetikleyicisi.

    Üç tür olay üretir (hepsi mum KAPANIŞ onaylı, lookahead-güvenli):
      • breaker    : close önceki onaylı swing seviyesini kırar (BOS).
      • mitigation : kırılımdan önceki son zıt-renk order-block mumuna fiyat
                     wick ile geri girer ve yön lehine kapatır.
      • three_vol  : 3 ardışık büyük-hacimli yön-uyumlu mum (momentum patlaması).

    Her olay tür-bazlı bir stop fiyatı taşır:
      breaker/mitigation → MSB'yi yaptıran son swing low(long)/high(short)
      three_vol          → 2. mumun Low(long)/High(short), wick dahil
    """

    def __init__(self, strength: int = 2, vol_mult: float = 1.5,
                 vol_window: int = 20, body_mult: float = 1.3,
                 min_atr_mult: float = 0.3):
        self.strength     = strength
        self.vol_mult     = vol_mult
        self.vol_window   = vol_window
        self.body_mult    = body_mult
        self.min_atr_mult = min_atr_mult

    def detect(self, df: pd.DataFrame, atr_series: pd.Series) -> List[MSBEvent]:
        H   = df['High'].values.astype(float)
        L   = df['Low'].values.astype(float)
        C   = df['Close'].values.astype(float)
        O   = df['Open'].values.astype(float)
        T   = df.index
        atr = atr_series.values.astype(float)
        n   = len(df)

        # Hacim — gerçek Volume varsa kullan; yoksa gövde-boyutu yedeği
        if 'Volume' in df.columns:
            V = df['Volume'].values.astype(float)
        else:
            V = np.zeros(n)
        vol_ma  = pd.Series(V).rolling(self.vol_window, min_periods=1).mean().values
        body    = np.abs(C - O)
        body_ma = pd.Series(body).rolling(self.vol_window, min_periods=1).mean().values

        def is_large(j: int) -> bool:
            # Hacim geçerliyse 1.5× ortalama; değilse gövde 1.3× ortalama
            if V[j] > 0 and vol_ma[j] > 0:
                return V[j] > self.vol_mult * vol_ma[j]
            return body[j] > self.body_mult * (body_ma[j] + 1e-10)

        last_sh, last_sl = SwingEngine.compute(H, L, atr, self.strength, self.min_atr_mult)

        events: List[MSBEvent] = []

        for i in range(2, n):
            atr_i = max(float(atr[i]), 1e-6)
            sh    = last_sh[i - 1]
            sl    = last_sl[i - 1]

            # ── (a) BREAKER — close ile BOS ───────────────────────────────
            if not np.isnan(sh) and C[i] > sh and C[i - 1] <= sh:
                stop, _ = SwingEngine.best_swing_low(L, H, atr, i,
                                                     lookback=50, min_strength=2,
                                                     max_strength=5, min_atr_mult=0.3)
                events.append(MSBEvent(
                    msb_type='breaker', direction='bull', confirm_idx=i,
                    detect_time=T[i], stop_price=float(stop),
                    swing_level=float(sh), quality=min(1.0, (C[i] - sh) / atr_i)))
            if not np.isnan(sl) and C[i] < sl and C[i - 1] >= sl:
                stop, _ = SwingEngine.best_swing_high(H, L, atr, i,
                                                      lookback=50, min_strength=2,
                                                      max_strength=5, min_atr_mult=0.3)
                events.append(MSBEvent(
                    msb_type='breaker', direction='bear', confirm_idx=i,
                    detect_time=T[i], stop_price=float(stop),
                    swing_level=float(sl), quality=min(1.0, (sl - C[i]) / atr_i)))

            # ── (b) MITIGATION — order-block geri testi, close onaylı ─────
            # Bull: i'den geriye en yakın düşüş-kapanışlı OB mumu k; fiyat
            #       H[k]'ye wick ile geri girip C[i] > H[k] kapatırsa.
            k = self._last_ob(C, O, i, want_down=True)
            if k is not None and L[i] <= H[k] and C[i] > H[k] and C[i - 1] <= H[k]:
                stop, _ = SwingEngine.best_swing_low(L, H, atr, i,
                                                     lookback=50, min_strength=2,
                                                     max_strength=5, min_atr_mult=0.3)
                events.append(MSBEvent(
                    msb_type='mitigation', direction='bull', confirm_idx=i,
                    detect_time=T[i], stop_price=float(stop),
                    swing_level=float(H[k]), quality=min(1.0, (C[i] - H[k]) / atr_i)))
            k = self._last_ob(C, O, i, want_down=False)
            if k is not None and H[i] >= L[k] and C[i] < L[k] and C[i - 1] >= L[k]:
                stop, _ = SwingEngine.best_swing_high(H, L, atr, i,
                                                      lookback=50, min_strength=2,
                                                      max_strength=5, min_atr_mult=0.3)
                events.append(MSBEvent(
                    msb_type='mitigation', direction='bear', confirm_idx=i,
                    detect_time=T[i], stop_price=float(stop),
                    swing_level=float(L[k]), quality=min(1.0, (L[k] - C[i]) / atr_i)))

            # ── (c) THREE_VOL — Three White Soldiers / Three Black Crows ──
            # pinescript "Mercüment Çözer" mum-deseni mantığı (hacim YOK).
            # Mumlar: c3=i-2 (en eski), c2=i-1, c1=i (en yeni). Onay i kapanışında.
            b3, b2, b1 = body[i - 2], body[i - 1], body[i]
            r3 = H[i - 2] - L[i - 2]; r2 = H[i - 1] - L[i - 1]; r1 = H[i] - L[i]
            k_br_min = (r3 > 0 and r2 > 0 and r1 > 0 and
                        b3 / r3 >= 0.45 and b2 / r2 >= 0.45 and b1 / r1 >= 0.45)
            bmax = max(b3, b2, b1); bmin = min(b3, b2, b1)
            k_ratio  = bmin > 0 and bmax / bmin <= 2.0
            k_minbod = (b3 >= atr_i * 0.15 and b2 >= atr_i * 0.15 and b1 >= atr_i * 0.15)
            base_ok  = k_br_min and k_ratio and k_minbod
            if base_ok:
                opens_ok = (self._open_ok(O[i - 1], O[i - 2], C[i - 2], b3) and
                            self._open_ok(O[i],     O[i - 1], C[i - 1], b2))
                # 3WS (bull): üçü boğa, yükselen kapanış, küçük üst fitiller
                if (opens_ok and C[i-2] > O[i-2] and C[i-1] > O[i-1] and C[i] > O[i] and
                        C[i-1] > C[i-2] and C[i] > C[i-1] and
                        (H[i-2] - max(O[i-2], C[i-2])) <= b3 * 0.40 and
                        (H[i-1] - max(O[i-1], C[i-1])) <= b2 * 0.40 and
                        (H[i]   - max(O[i],   C[i]))   <= b1 * 0.40):
                    events.append(MSBEvent(
                        msb_type='three_vol', direction='bull', confirm_idx=i,
                        detect_time=T[i], stop_price=float(L[i - 1]),
                        swing_level=float(L[i - 1]), quality=min(1.0, body[i] / atr_i)))
                # 3BC (bear): üçü ayı, düşen kapanış, küçük alt fitiller
                elif (opens_ok and C[i-2] < O[i-2] and C[i-1] < O[i-1] and C[i] < O[i] and
                        C[i-1] < C[i-2] and C[i] < C[i-1] and
                        (min(O[i-2], C[i-2]) - L[i-2]) <= b3 * 0.40 and
                        (min(O[i-1], C[i-1]) - L[i-1]) <= b2 * 0.40 and
                        (min(O[i],   C[i])   - L[i])   <= b1 * 0.40):
                    events.append(MSBEvent(
                        msb_type='three_vol', direction='bear', confirm_idx=i,
                        detect_time=T[i], stop_price=float(H[i - 1]),
                        swing_level=float(H[i - 1]), quality=min(1.0, body[i] / atr_i)))

        events.sort(key=lambda e: e.confirm_idx)
        return events

    @staticmethod
    def _last_ob(C: np.ndarray, O: np.ndarray, i: int,
                 want_down: bool, lookback: int = 12) -> Optional[int]:
        """i'den hemen önceki son zıt-renk order-block mumunun indeksi."""
        for k in range(i - 1, max(0, i - lookback) - 1, -1):
            is_down = C[k] < O[k]
            if want_down and is_down:
                return k
            if (not want_down) and (C[k] > O[k]):
                return k
        return None

    @staticmethod
    def _open_ok(o_cur: float, o_prev: float, c_prev: float,
                 b_prev: float, ptol: float = 0.20) -> bool:
        """3WS/3BC: mum, önceki mumun gövdesi içinde/yakınında mı açılmış?"""
        lo = min(o_prev, c_prev) - b_prev * ptol
        hi = max(o_prev, c_prev) + b_prev * ptol
        return lo <= o_cur <= hi


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 3c: HARMONİK DESEN ENGİNİ (pinescript "Mercüment Çözer" portu)
# ═══════════════════════════════════════════════════════════════════════════

class HarmonicEngine:
    """
    ZigZag fraktal pivot → son 4 nokta XABC → Fibonacci oran kontrolü →
    8 desen (Gartley/Bat/AltBat/Butterfly/Crab/DeepCrab/Shark/Cypher) → PRZ.

    pinescript ile birebir: tüm desenler `struct_ok` (alternatif retracement)
    kapısı altında; bu nedenle Shark/Cypher kaynaktaki gibi pratikte nadir/hiç
    tetiklenmez (yapı tipiyle çelişir) — sadakat için yine de dahil edildi.

    Lookahead: pivot bar p, `swing` bar sonra (p+swing) onaylanır; desen
    C-pivotunun onay barının KAPANIŞINDA görünür olur (detect_time).
    """

    AGE_MAP = {'5m':  pd.Timedelta(hours=24), '15m': pd.Timedelta(days=2),
               '1h':  pd.Timedelta(days=5),  '4h':  pd.Timedelta(days=14)}
    TF_OFFSET = {'5m': pd.Timedelta(minutes=5),  '15m': pd.Timedelta(minutes=15),
                 '1h': pd.Timedelta(hours=1),    '4h':  pd.Timedelta(hours=4)}

    def __init__(self, swing: int = 5, min_conf: float = 40.0,
                 max_prz_pct: float = 4.0):
        self.swing       = swing
        self.min_conf    = min_conf
        self.max_prz_pct = max_prz_pct

    # ── Fibonacci yardımcıları (pinescript f_* portu) ────────────────────
    @staticmethod
    def _conf(v1, lo1, hi1, v2, lo2, hi2) -> float:
        m1 = (lo1 + hi1) / 2.0; m2 = (lo2 + hi2) / 2.0
        d1 = abs(v1 - m1) / max(m1, 1e-10)
        d2 = abs(v2 - m2) / max(m2, 1e-10)
        return max(0.0, min(100.0, 100.0 - (d1 * 40.0 + d2 * 40.0)))

    @staticmethod
    def _nearest_cd(ab_bc, c382, c500, c618, c786, c886) -> float:
        keys = [(0.382, c382), (0.500, c500), (0.618, c618),
                (0.786, c786), (0.886, c886)]
        return min(keys, key=lambda kv: abs(ab_bc - kv[0]))[1]

    def _prz(self, d1, d2, x_p, bullish, retrace):
        lo = min(d1, d2); hi = max(d1, d2)
        if retrace:
            if bullish:
                lo = max(lo, x_p); hi = max(hi, x_p)
            else:
                lo = min(lo, x_p); hi = min(hi, x_p)
        ctr = abs((lo + hi) / 2.0)
        gap = (hi - lo) / ctr * 100 if ctr > 1e-10 else 99.0
        return lo, hi, (gap <= self.max_prz_pct)

    def _check(self, x_p, a_p, b_p, c_p, bullish):
        """Bir XABC için ilk eşleşen deseni döndür: (pattern, conf, lo, hi) | None."""
        xa = abs(x_p - a_p); ab = abs(a_p - b_p); bc = abs(b_p - c_p)
        if bullish:
            struct_ok = b_p > x_p and b_p < a_p and c_p > b_p and c_p < a_p
        else:
            struct_ok = b_p < x_p and b_p > a_p and c_p < b_p and c_p > a_p
        if not (xa > 1e-10 and ab > 1e-10 and struct_ok):
            return None

        xa_ab  = ab / xa
        ab_bc  = bc / max(ab, 1e-10)
        xb_ext = abs(x_p - b_p) / xa
        xc_prj = abs(x_p - c_p) / xa
        f_in   = lambda v, lo, hi: lo <= v <= hi

        def proj_ad(ad_lo, ad_hi):
            mid = (ad_lo + ad_hi) / 2.0
            return (a_p - xa * mid) if bullish else (a_p + xa * mid)

        def proj_cd(cd_r):
            return (c_p - bc * cd_r) if bullish else (c_p + bc * cd_r)

        # (pattern, xa_ab[lo,hi], ad[lo,hi], cd5, retrace)
        STD = [
            ('Gartley',   0.550, 0.680, 0.750, 0.820, (1.618, 1.414, 1.272, 1.272, 1.272), True),
            ('Bat',       0.320, 0.560, 0.850, 0.920, (2.618, 2.000, 1.618, 1.618, 1.618), True),
            ('AltBat',    0.080, 0.420, 1.080, 1.180, (3.618, 2.618, 2.240, 2.000, 2.000), False),
            ('Butterfly', 0.720, 0.850, 1.200, 1.680, (2.618, 2.000, 2.240, 2.618, 2.618), False),
            ('Crab',      0.350, 0.650, 1.550, 1.700, (3.618, 2.618, 2.618, 2.618, 2.618), False),
            ('DeepCrab',  0.850, 0.930, 1.550, 1.700, (3.618, 2.618, 2.618, 2.618, 2.618), False),
        ]
        for name, xlo, xhi, adlo, adhi, cd5, retr in STD:
            if f_in(xa_ab, xlo, xhi) and f_in(ab_bc, 0.382, 0.886):
                cv = self._conf(xa_ab, xlo, xhi, ab_bc, 0.382, 0.886)
                if cv >= self.min_conf:
                    d1 = proj_ad(adlo, adhi)
                    d2 = proj_cd(self._nearest_cd(ab_bc, *cd5))
                    lo, hi, ok = self._prz(d1, d2, x_p, bullish, retr)
                    if ok:
                        return (name, cv, lo, hi)

        # SHARK
        shark_b = (b_p > a_p) if bullish else (b_p < a_p)
        if shark_b and f_in(xb_ext, 1.080, 1.680) and f_in(ab_bc, 1.500, 2.350):
            cv = self._conf(xb_ext, 1.080, 1.680, ab_bc, 1.500, 2.350)
            if cv >= self.min_conf:
                xc_len = abs(x_p - c_p)
                d1 = (c_p - xc_len * 0.886) if bullish else (c_p + xc_len * 0.886)
                d2 = proj_cd(self._nearest_cd(ab_bc, 2.240, 2.000, 1.618, 1.618, 1.618))
                lo, hi, ok = self._prz(d1, d2, x_p, bullish, False)
                if ok:
                    return ('Shark', cv, lo, hi)

        # CYPHER
        c_ex = (c_p > a_p) if bullish else (c_p < a_p)
        if c_ex and f_in(xa_ab, 0.350, 0.650) and f_in(xc_prj, 1.200, 1.500):
            cv = self._conf(xa_ab, 0.350, 0.650, xc_prj, 1.200, 1.500)
            if cv >= self.min_conf:
                xc_len = abs(x_p - c_p)
                d1 = (c_p - xc_len * 0.786) if bullish else (c_p + xc_len * 0.786)
                d2 = proj_cd(self._nearest_cd(ab_bc, 1.272, 1.000, 0.786, 0.786, 0.786))
                lo, hi, ok = self._prz(d1, d2, x_p, bullish, True)
                if ok:
                    return ('Cypher', cv, lo, hi)
        return None

    def detect(self, df: pd.DataFrame, timeframe: str) -> List[HarmonicSignal]:
        H = df['High'].values.astype(float)
        L = df['Low'].values.astype(float)
        T = df.index
        n = len(df)
        s = self.swing
        offset = self.TF_OFFSET.get(timeframe, pd.Timedelta(minutes=5))
        age    = self.AGE_MAP.get(timeframe, pd.Timedelta(days=2))

        # ZigZag onaylı pivotlar: paralel diziler (price, type ±1, confirm_bar)
        zp: List[float] = []; zt: List[int] = []; zc: List[int] = []
        seen = set()
        signals: List[HarmonicSignal] = []

        def scan(conf_bar: int):
            if len(zp) < 4:
                return
            x_p, a_p, b_p, c_p = zp[-4], zp[-3], zp[-2], zp[-1]
            tx, ta, tb, tc     = zt[-4], zt[-3], zt[-2], zt[-1]
            if tx == -1 and ta == 1 and tb == -1 and tc == 1:
                bullish = True
            elif tx == 1 and ta == -1 and tb == 1 and tc == -1:
                bullish = False
            else:
                return
            res = self._check(x_p, a_p, b_p, c_p, bullish)
            if res is None:
                return
            name, cv, lo, hi = res
            cb = min(conf_bar, n - 1)
            dt = to_naive(T[cb]) + offset
            key = (timeframe, name, 'bull' if bullish else 'bear',
                   round(lo, 2), round(hi, 2))
            if key in seen:
                return
            seen.add(key)
            signals.append(HarmonicSignal(
                direction='bull' if bullish else 'bear',
                pattern=name, timeframe=timeframe,
                prz_low=float(lo), prz_high=float(hi),
                detect_time=dt, expiry_time=dt + age, conf=float(cv)))

        for i in range(2 * s, n):
            p = i - s   # pivot adayı; sağı i'de tam görünür
            is_sh = all(H[p] > H[p - k] and H[p] > H[p + k] for k in range(1, s + 1))
            is_sl = all(L[p] < L[p - k] and L[p] < L[p + k] for k in range(1, s + 1))
            if is_sh:
                if zt and zt[-1] == 1:
                    if H[p] > zp[-1]:
                        zp[-1] = H[p]; zc[-1] = i
                        scan(i)
                else:
                    zp.append(H[p]); zt.append(1); zc.append(i)
                    scan(i)
            if is_sl:
                if zt and zt[-1] == -1:
                    if L[p] < zp[-1]:
                        zp[-1] = L[p]; zc[-1] = i
                        scan(i)
                else:
                    zp.append(L[p]); zt.append(-1); zc.append(i)
                    scan(i)
            # bellek: pivot listesini sınırlı tut
            if len(zp) > 50:
                del zp[0]; del zt[0]; del zc[0]

        return signals


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 3b: BREAKER BLOCK ENGİNİ
# ═══════════════════════════════════════════════════════════════════════════

_bb_id_counter = 0

def _next_bb_id() -> int:
    global _bb_id_counter
    _bb_id_counter += 1
    return _bb_id_counter


class BreakerEngine:
    """
    1H MSB (Market Structure Break) olaylarından breaker block tespiti.

    Kural:
      • Bull breaker: 1H close, önceki onaylı swing-high'ı YUKARI kırarsa
        → o mumun H/L aralığı = bullish breaker block
        → fiyat aşağı çekilip bloğa girerse: LONG entry (kırılım yönünde devam)
      • Bear breaker: 1H close, önceki onaylı swing-low'u AŞAĞI kırarsa
        → o mumun H/L aralığı = bearish breaker block
        → fiyat yukarı çekilip bloğa girerse: SHORT entry

    Tespit: MUM KAPANIS bazlı (wick değil).
    Tüketim: bloğun karşı kenarından (mum kapanışıyla) geçilirse geçersiz.
    """

    def __init__(self, max_age_hours: float = 72, buf_ratio: float = 0.05):
        self.max_age_hours = max_age_hours
        self.buf_ratio     = buf_ratio
        self._detect_offset = timedelta(hours=1)

    def detect(self, df: pd.DataFrame, direction: str,
               atr_series: pd.Series, strength: int = 2) -> List[BreakerBlock]:
        """
        df: 1H DataFrame. direction: 'bull' | 'bear'.
        SwingEngine kullanarak close-bazlı MSB tespiti yapar.
        """
        H   = df['High'].values.astype(float)
        L   = df['Low'].values.astype(float)
        C   = df['Close'].values.astype(float)
        O   = df['Open'].values.astype(float)
        T   = df.index
        atr = atr_series.values.astype(float)
        n   = len(df)

        last_sh, last_sl = SwingEngine.compute(H, L, atr, strength=strength)

        blocks: List[BreakerBlock] = []
        for i in range(1, n):
            atr_i = max(float(atr[i]), 1e-6)
            if direction == 'bull':
                sh = last_sh[i - 1]
                if np.isnan(sh):
                    continue
                # Bull BOS: close kırıyor, bir önceki bar kırmamış
                if C[i] > sh and C[i - 1] <= sh:
                    body   = abs(C[i] - O[i]) / (H[i] - L[i] + 1e-10)
                    brk    = (C[i] - sh) / atr_i
                    qual   = min(100.0, 40 * min(1.0, brk) + 40 * body + 20 * min(1.0, (H[i]-L[i])/atr_i))
                    blocks.append(BreakerBlock(
                        block_id      = _next_bb_id(),
                        direction     = 'bull',
                        break_time    = T[i],
                        detect_time   = T[i] + self._detect_offset,
                        high          = float(H[i]),
                        low           = float(L[i]),
                        swing_level   = float(sh),
                        quality_score = qual,
                    ))
            else:
                sl = last_sl[i - 1]
                if np.isnan(sl):
                    continue
                # Bear BOS: close kırıyor, bir önceki bar kırmamış
                if C[i] < sl and C[i - 1] >= sl:
                    body   = abs(C[i] - O[i]) / (H[i] - L[i] + 1e-10)
                    brk    = (sl - C[i]) / atr_i
                    qual   = min(100.0, 40 * min(1.0, brk) + 40 * body + 20 * min(1.0, (H[i]-L[i])/atr_i))
                    blocks.append(BreakerBlock(
                        block_id      = _next_bb_id(),
                        direction     = 'bear',
                        break_time    = T[i],
                        detect_time   = T[i] + self._detect_offset,
                        high          = float(H[i]),
                        low           = float(L[i]),
                        swing_level   = float(sl),
                        quality_score = qual,
                    ))
        return blocks

    def build_mitigation_map(self, df: pd.DataFrame,
                              bb_list: List[BreakerBlock]) -> Dict[int, Optional[Any]]:
        """
        Bloğun geçersiz olduğu anı ön-hesapla.
          Bull breaker: close < bb.low  → blok tutmadı, geçersiz
          Bear breaker: close > bb.high → blok tutmadı, geçersiz
        """
        C = df['Close'].values.astype(float)
        T = df.index
        n = len(df)
        mit_map: Dict[int, Optional[Any]] = {}
        for bb in bb_list:
            det     = to_naive(bb.detect_time)
            start_i = next((j for j in range(n) if to_naive(T[j]) >= det), None)
            mit_map[bb.block_id] = None
            if start_i is None:
                continue
            for j in range(start_i, n):
                c = C[j]
                # Close-bazlı geçersizleştirme
                invalid = (c < bb.low) if bb.direction == 'bull' else (c > bb.high)
                if invalid:
                    mit_map[bb.block_id] = to_naive(T[j]) + self._detect_offset
                    break
        return mit_map

    def get_active(self, bb_list: List[BreakerBlock],
                   mit_map: Dict[int, Optional[Any]],
                   current_time: Any) -> List[BreakerBlock]:
        t      = to_naive(current_time)
        cutoff = t - timedelta(hours=self.max_age_hours)
        active = []
        for bb in bb_list:
            det = to_naive(bb.detect_time)
            if det >= t:
                continue
            if det < cutoff:
                continue
            mit = mit_map.get(bb.block_id)
            if mit is not None and mit <= t:
                continue
            active.append(bb)
        return active

    def price_touching(self, price: float,
                       active: List[BreakerBlock]) -> Optional[BreakerBlock]:
        """Fiyat aktif bir breaker block içinde mi? En kalitelisini döndür."""
        best: Optional[BreakerBlock] = None
        best_q = -1.0
        for bb in reversed(active):
            span = bb.high - bb.low
            buf  = span * self.buf_ratio
            if (bb.low - buf) <= price <= (bb.high + buf):
                if bb.quality_score > best_q:
                    best, best_q = bb, bb.quality_score
        return best


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 4: FVG ENGİNİ
# ═══════════════════════════════════════════════════════════════════════════

class FVGEngine:
    """
    FVG tespiti, kalite skorlaması ve mitigasyon takibi.
    Lookahead engeli: her FVG yalnızca 3. mum kapandıktan sonra görünür.
    """

    def __init__(self, timeframe: str, min_gap: float = 0.50,
                 max_age_hours: float = 48, buf_ratio: float = 0.05):
        self.timeframe     = timeframe
        self.min_gap       = min_gap
        self.max_age_hours = max_age_hours
        self.buf_ratio     = buf_ratio
        # Bar kapanış offseti: yfinance index'i bar AÇILIŞ zamanıdır.
        # FVG yalnızca 3. mumun KAPANIŞINDAN sonra görünür olmalı.
        _tf_map = {'1h': pd.Timedelta(hours=1), '5m': pd.Timedelta(minutes=5),
                   '15m': pd.Timedelta(minutes=15), '1d': pd.Timedelta(days=1)}
        self._detect_offset = _tf_map.get(timeframe, pd.Timedelta(minutes=5))

    def detect(self, df: pd.DataFrame, direction: str,
               atr_series: pd.Series = None) -> List[FVG]:
        """Ham FVG listesi — kalite skoru dahil."""
        H   = df['High'].values.astype(float)
        L   = df['Low'].values.astype(float)
        O   = df['Open'].values.astype(float)
        C   = df['Close'].values.astype(float)
        T   = df.index
        atr = atr_series.values if atr_series is not None else np.ones(len(df)) * 10.0

        fvgs: List[FVG] = []
        for i in range(2, len(df)):
            if direction == 'bull':
                gap_size = L[i] - H[i - 2]
                if gap_size < self.min_gap:
                    continue
                top, bottom = L[i], H[i - 2]
            else:
                gap_size = L[i - 2] - H[i]
                if gap_size < self.min_gap:
                    continue
                top, bottom = L[i - 2], H[i]

            mid          = (top + bottom) / 2
            gap_atr      = gap_size / (atr[i] + 1e-10)
            mid_range    = H[i - 1] - L[i - 1]
            momentum     = abs(C[i - 1] - O[i - 1]) / (mid_range + 1e-10)
            quality      = min(100.0,
                               40 * min(1.0, gap_atr) +
                               40 * momentum +
                               20 * (1.0 if gap_atr > 0.5 else gap_atr * 2))

            fvgs.append(FVG(
                fvg_id        = _next_fvg_id(),
                timeframe     = self.timeframe,
                direction     = direction,
                index         = T[i - 1],
                detect_time   = T[i] + self._detect_offset,
                top           = top,
                bottom        = bottom,
                mid           = mid,
                gap_size      = gap_size,
                gap_atr_ratio = gap_atr,
                momentum      = momentum,
                quality_score = quality,
                created_i     = i - 1,
            ))
        return fvgs

    def build_mitigation_map(self, df: pd.DataFrame,
                              fvg_list: List[FVG]) -> Dict[int, Optional[Any]]:
        """Her FVG'nin ne zaman mitigasyon yaşadığını ön hesapla."""
        C = df['Close'].values.astype(float)
        T = df.index
        n = len(df)
        mit_map: Dict[int, Optional[Any]] = {}

        for fvg in fvg_list:
            fvg_time = to_naive(fvg.detect_time)
            start_i  = next((j for j in range(n)
                             if to_naive(T[j]) >= fvg_time), None)
            if start_i is None:
                mit_map[fvg.fvg_id] = None
                continue

            mit_map[fvg.fvg_id] = None
            for j in range(start_i, n):
                c = C[j]
                # KULLANIM KURALI: bir mum FVG'nin İÇİNE (proksimal kenardan)
                # kapanırsa FVG tüketilir → artık işlem alınmaz.
                #   Bull: proksimal=top  → close <= top   (gap'e girdi/aştı)
                #   Bear: proksimal=bottom → close >= bottom
                # Tüketim zamanı = mumun KAPANIŞ anı (lookahead engeli).
                consumed = (c <= fvg.top) if fvg.direction == 'bull' else (c >= fvg.bottom)
                if consumed:
                    mit_map[fvg.fvg_id] = to_naive(T[j]) + self._detect_offset
                    break

        return mit_map

    def get_active(self, fvg_list: List[FVG],
                   mit_map: Dict[int, Optional[Any]],
                   current_time: Any) -> List[FVG]:
        """Belirli zamanda aktif (taze, mitigasyon yok) FVG'leri döndür."""
        t      = to_naive(current_time)
        cutoff = t - timedelta(hours=self.max_age_hours)
        active = []
        for fvg in fvg_list:
            det = to_naive(fvg.detect_time)
            if det >= t:
                continue                              # lookahead engeli
            if det < cutoff:
                continue                              # çok eski
            mit = mit_map.get(fvg.fvg_id)
            if mit is not None and mit <= t:
                continue                              # mitigasyon yapıldı
            active.append(fvg)
        return active

    def price_touching(self, price: float,
                       active: List[FVG]) -> Optional[FVG]:
        """Fiyat aktif bir FVG bölgesinde mi? En kalitelisini döndür."""
        best: Optional[FVG] = None
        best_q = -1.0
        for fvg in reversed(active):
            span = fvg.top - fvg.bottom
            buf  = span * self.buf_ratio
            if (fvg.bottom - buf) <= price <= (fvg.top + buf):
                if fvg.quality_score > best_q:
                    best, best_q = fvg, fvg.quality_score
        return best

    def has_recent_active(self, fvg_list: List[FVG],
                          mit_map: Dict[int, Optional[Any]],
                          current_time: Any,
                          window_secs: int = 3600,
                          since_time: Optional[Any] = None) -> Tuple[bool, float]:
        """
        Şemaya göre: MSC SIRASINDA/SONRASINDA oluşmuş, henüz tüketilmemiş
        bir 5M FVG var mı? (bool, kalite)

        since_time verilirse o andan (MSC zamanı) bu yana oluşan FVG'ler
        sayılır; verilmezse son `window_secs` saniyeye bakılır.
        fvg_list zaten yön-bazlı (bull/bear) geldiği için yön uyumu sağlanır.
        """
        t      = to_naive(current_time)
        cutoff = (to_naive(since_time) if since_time is not None
                  else t - timedelta(seconds=window_secs))
        best_q = 0.0
        found  = False
        for fvg in reversed(fvg_list):
            det = to_naive(fvg.detect_time)
            if det >= t:
                continue
            if det < cutoff:
                break
            mit = mit_map.get(fvg.fvg_id)
            if mit is not None and mit <= t:
                continue
            found  = True
            best_q = max(best_q, fvg.quality_score)
        return found, best_q


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 5: MARKET BRAIN (Sinyal Zekâsı)
# ═══════════════════════════════════════════════════════════════════════════

class MarketBrain:
    """
    Şemayı birebir uygulayan sinyal değerlendirme katmanı.

    Adım 1: Fiyat 1H FVG'ye WICK ile dokundu mu? (stateful — dokunan FVG
            tetikleyene kadar 'pending' kayıtta tutulur, fiyat çıksa bile)
    Adım 2: Konfluens — EMA (fiyat EMA100&200 üstü/altı) ve/veya RSI uyumsuzluğu.
            En az biri gerekli. İkisi birden varsa risk 1R, biri varsa 0.5R.
    Adım 3: MSB tetikleyici (5M) — breaker | mitigation | three_vol.
            Tek başına MSB → işlem YOK.

    Stop: breaker/mitigation → MSB swing low/high; three_vol → 2. mum wick.
    Sabit 1:2 RR. Seans filtresi YOK.

    Haftalık bias: WeeklyBiasProvider üzerinden. Bias yoksa o hafta işlem yapılmaz.
    """

    RSI_WINDOW         = 30   # mum sayısı (5M → ~150 dk) — iki pivot sığsın
    TOUCH_MAX_AGE_BARS = 20   # dokunuştan sonra MSB için bekleme penceresi (20×5dk)

    def __init__(self, bias_provider: Optional['WeeklyBiasProvider'] = None):
        self.bias = bias_provider
        self.last_skip_reason: Optional[str] = None
        # Adım-bazlı teşhis: sinyalin hangi adımda öldüğünü sayar
        self.stats = dict(step1_fail=0, step2_fail=0, step3_fail=0)
        # KULLANIM KURALI: her 1H FVG yalnızca bir kez işlem açabilir
        self.used_fvg_ids: set = set()
        # STATEFUL: dokunmuş ama henüz MSB ile tetiklenmemiş 1H FVG'ler (yön bazlı)
        #   {fvg_id, fvg, touch_idx, touch_time}
        self.pending: Dict[str, List[dict]] = {'bull': [], 'bear': []}

    # ── RSI Diverjansı (RSIEngine'e delege) ──────────────────────────────
    def rsi_divergence(self, prices: np.ndarray,
                       rsi_vals: np.ndarray) -> Tuple[Optional[str], float]:
        """Pivot-tabanlı regular diverjans — bkz. RSIEngine.divergence."""
        return RSIEngine.divergence(prices, rsi_vals, strength=2)

    # ── EMA Onayı ───────────────────────────────────────────────────────
    def ema_confirm(self, close: float, e100: float, e200: float,
                    direction: str) -> Tuple[bool, float]:
        if direction == 'bull':
            ok   = close > e100 and close > e200
            dist = min((close - e100) / (e100 + 1e-10),
                       (close - e200) / (e200 + 1e-10)) * 100
        else:
            ok   = close < e100 and close < e200
            dist = min((e100 - close) / (e100 + 1e-10),
                       (e200 - close) / (e200 + 1e-10)) * 100
        return ok, float(dist)

    # ── Ana Değerlendirme ────────────────────────────────────────────────
    def evaluate(self,
                 idx: int,
                 C: np.ndarray, O: np.ndarray,
                 H: np.ndarray, L: np.ndarray,
                 E100: np.ndarray, E200: np.ndarray,
                 RSI: np.ndarray,
                 TM: pd.Index,
                 fvg1_bull: List[FVG], mit1_bull: Dict,
                 fvg1_bear: List[FVG], mit1_bear: Dict,
                 fvg1_eng: 'FVGEngine',
                 msb_events_bull: List[MSBEvent],
                 msb_events_bear: List[MSBEvent],
                 przfvg_bull: Optional[List[FVG]] = None,
                 przfvg_bear: Optional[List[FVG]] = None,
                 mit_prz: Optional[Dict] = None,
                 prz_eng: Optional['FVGEngine'] = None,
                 prz_harm: Optional[Dict] = None
                 ) -> Optional[TradeSignal]:

        # last_skip_reason her çağrıda sıfırlanır (stale değer bug fix)
        self.last_skip_reason = None
        przfvg_bull = przfvg_bull or []
        przfvg_bear = przfvg_bear or []
        mit_prz     = mit_prz or {}
        prz_harm    = prz_harm or {}

        cur_time  = TM[idx]
        cur_close = float(C[idx])

        # ── HAFTALIK BİAS ──────────────────────────────────────────────
        # Bias EMA/RSI konfluensini (ve PRZ-POI senaryosunu) kapılar.
        # Harmonik-örtüşme konfluensi (gerçek 1H FVG üzerinde) bias'tan BAĞIMSIZ.
        weekly_dir = self.bias.get(cur_time) if self.bias is not None else None

        t = to_naive(cur_time)
        best_signal: Optional[TradeSignal] = None
        best_key    = (-1, -1.0)
        stage = 0   # 0=dokunuş yok, 1=dokundu konfluens yok, 2=konfluens var MSB yok

        for direction in ('bull', 'bear'):
            fvg1_raw   = fvg1_bull if direction == 'bull' else fvg1_bear
            mit1       = mit1_bull if direction == 'bull' else mit1_bear
            przfvg_raw = przfvg_bull if direction == 'bull' else przfvg_bear
            msb_events = msb_events_bull if direction == 'bull' else msb_events_bear
            pend       = self.pending[direction]

            # ── ADIM 1: WICK dokunuşu — İKİ POI kaynağı ───────────────────
            #   kind='fvg' → gerçek 1H FVG; kind='prz' → harmonik PRZ bölgesi.
            sources = [('fvg', fvg1_raw, mit1, fvg1_eng)]
            if prz_eng is not None and przfvg_raw:
                sources.append(('prz', przfvg_raw, mit_prz, prz_eng))

            pend_ids = {p['fvg_id'] for p in pend}
            for kind, raw, mitm, eng in sources:
                active = eng.get_active(raw, mitm, t)
                active = [f for f in active if f.fvg_id not in self.used_fvg_ids]
                for fvg in active:
                    span = fvg.top - fvg.bottom
                    buf  = span * fvg1_eng.buf_ratio
                    if L[idx] <= (fvg.top + buf) and H[idx] >= (fvg.bottom - buf):
                        if fvg.fvg_id not in pend_ids:
                            pend.append({'fvg_id': fvg.fvg_id, 'fvg': fvg, 'kind': kind,
                                         'touch_idx': idx, 'touch_time': t})
                            pend_ids.add(fvg.fvg_id)

            # PRUNE: tüketilmiş / yaşlanmış / iptal pending'leri at
            mit_by_kind = {'fvg': mit1, 'prz': mit_prz}
            kept = []
            for p in pend:
                m = mit_by_kind.get(p['kind'], {}).get(p['fvg_id'])
                if p['fvg_id'] in self.used_fvg_ids:
                    continue                                   # işlem açıldı
                if m is not None and to_naive(m) <= t:
                    continue                                   # iptal / süre doldu
                if idx - p['touch_idx'] > self.TOUCH_MAX_AGE_BARS:
                    continue                                   # çok bekledi (20 mum)
                kept.append(p)
            pend[:] = kept
            self.pending[direction] = pend

            if not pend:
                continue
            stage = max(stage, 1)

            # ── ADIM 2: Konfluens ─────────────────────────────────────────
            bias_allows = (self.bias is None) or (weekly_dir == direction)

            ema_ok, ema_d = self.ema_confirm(
                cur_close, float(E100[idx]), float(E200[idx]), direction)
            sl_ = max(0, idx - self.RSI_WINDOW)
            div_type, div_str = self.rsi_divergence(C[sl_:idx + 1], RSI[sl_:idx + 1])
            rsi_ok = (div_type == direction)
            bias_main = bias_allows and (ema_ok or rsi_ok)

            # Hem gerçek 1H FVG hem harmonik PRZ POI'leri yalnız bias_main
            # (EMA/RSI + haftalık bias) ile işlem açar. (Senaryo-1 kaldırıldı.)
            if not bias_main:
                continue                                       # konfluens yok → bekle
            stage = max(stage, 2)

            trigger = max(pend, key=lambda p: p['fvg'].quality_score)

            # ── ADIM 3: MSB tetikleyici (dokunuştan sonra, kapanmış) ─────
            #   Harmonik/PRZ olsa da MSB ŞART; stop MSB'den (aynı mantık).
            tch = trigger['touch_idx']
            event: Optional[MSBEvent] = None
            for e in reversed(msb_events):
                if e.confirm_idx > idx:
                    continue
                if e.confirm_idx < tch:
                    break
                event = e
                break
            if event is None:
                continue                                       # MSB beklenmeye devam

            # ── Sinyal oluştur ───────────────────────────────────────────
            confluence_count = int(ema_ok) + int(rsi_ok)
            risk_fraction = 0.01 if confluence_count == 2 else 0.005

            src = []
            if ema_ok: src.append('EMA')
            if rsi_ok: src.append('RSI')
            if trigger['kind'] == 'prz': src.append('PRZ')           # senaryo-2
            conf_label = '+'.join(src)

            harmonic_ref = (prz_harm.get(trigger['fvg_id'])
                            if trigger['kind'] == 'prz' else None)

            confidence = min(100.0,
                             40 * (trigger['fvg'].quality_score / 100.0) +
                             30 * float(event.quality) +
                             30 * (confluence_count / 2.0))

            key = (confluence_count, trigger['fvg'].quality_score)
            if key > best_key:
                best_key = key
                best_signal = TradeSignal(
                    entry_time        = cur_time,
                    direction         = direction,
                    trigger_fvg       = trigger['fvg'],
                    confirmation_type = conf_label,
                    confidence        = confidence,
                    msb_type          = event.msb_type,
                    confluence_count  = max(confluence_count, 1),
                    stop_price        = event.stop_price,
                    risk_fraction     = risk_fraction,
                    harmonic          = harmonic_ref,
                    rsi_div_type      = div_type if (bias_allows and rsi_ok) else None,
                    ema_distance_pct  = ema_d if (bias_allows and ema_ok) else 0.0,
                )

        # Teşhis: hangi adımda öldü?
        if best_signal is None:
            if stage == 0:
                self.stats['step1_fail'] += 1
            elif stage == 1:
                self.stats['step2_fail'] += 1
            else:
                self.stats['step3_fail'] += 1
            if self.bias is not None and weekly_dir is None:
                self.last_skip_reason = 'no_bias'
            else:
                self.last_skip_reason = 'no_signal'

        return best_signal


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 6: RİSK YÖNETİCİSİ
# ═══════════════════════════════════════════════════════════════════════════

class RiskManager:
    """
    MSB-tabanlı SL (stop fiyatı dışarıdan gelir), 1:2 RR TP ve
    konfluens-bazlı kesirli pozisyon büyüklüğü (0.5R / 1R).
    """

    def __init__(self, rr: float = 2.0, sl_buffer: float = 0.0005):
        self.rr             = rr
        self.sl_buffer      = sl_buffer
        self.min_risk       = 0.50
        self.max_risk       = 150.0
        self.max_risk_pct   = 2.0

    def compute(self, direction: str, entry: float,
                stop_price: float, equity: float,
                risk_fraction: float) -> Optional[Dict]:

        if direction == 'bull':
            sl   = stop_price * (1.0 - self.sl_buffer)
            risk = abs(entry - sl)
            tp   = entry + risk * self.rr
        else:
            sl   = stop_price * (1.0 + self.sl_buffer)
            risk = abs(sl - entry)
            tp   = entry - risk * self.rr

        if not (self.min_risk <= risk <= self.max_risk):
            return None
        if risk / entry * 100 > self.max_risk_pct:
            return None
        if direction == 'bull' and (tp <= entry or sl >= entry):
            return None
        if direction == 'bear' and (tp >= entry or sl <= entry):
            return None

        return {
            'sl'           : round(sl,   2),
            'tp'           : round(tp,   2),
            'risk'         : round(risk, 2),
            'risk_pct'     : round(risk / entry * 100, 4),
            'risk_dollar'  : round(equity * risk_fraction, 2),
            'risk_fraction': risk_fraction,
        }


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 7: BACKTEST ENGİNİ
# ═══════════════════════════════════════════════════════════════════════════

class BacktestEngine:
    """
    Olay güdümlü (event-driven) backtester.
    5M mumları sırayla işler. Aynı anda tek açık pozisyon.
    """

    def __init__(self, brain: MarketBrain, risk_mgr: RiskManager,
                 initial_capital: float = 10_000,
                 breakeven_at_R: Optional[float] = None):
        self.brain   = brain
        self.risk    = risk_mgr
        self.capital = initial_capital
        # breakeven_at_R: fiyat bu kadar R kâra ulaşınca SL entry'ye taşınır
        # (None → kapalı). Örn 1.0 → 1R'de breakeven.
        self.breakeven_at_R = breakeven_at_R

    def run(self, df_1h: pd.DataFrame, df_5m: pd.DataFrame,
            backtest_start: datetime) -> List[Trade]:

        print("  Göstergeler hesaplanıyor...")

        # 5M göstergeler
        df5 = df_5m.copy()
        df5 = EMAEngine.add(df5, 100, 200)
        df5['rsi'] = RSIEngine.wilder(df5['Close'], 14)
        df5['atr'] = IndicatorEngine.atr(df5, 14)

        df1 = df_1h.copy()
        df1['atr'] = IndicatorEngine.atr(df1, 14)

        # 1H FVG motoru (yüksek-zaman dilimi POI) — wick dokunuş için dar buffer
        fvg1_eng = FVGEngine('1h', min_gap=2.0, max_age_hours=48, buf_ratio=0.02)

        print("  1H FVG...", end=' ')
        fvg1_bull = fvg1_eng.detect(df1, 'bull', df1['atr'])
        fvg1_bear = fvg1_eng.detect(df1, 'bear', df1['atr'])
        mit1_bull = fvg1_eng.build_mitigation_map(df1, fvg1_bull)
        mit1_bear = fvg1_eng.build_mitigation_map(df1, fvg1_bear)
        print(f"Bull:{len(fvg1_bull)}  Bear:{len(fvg1_bear)}")

        # 5M MSB motoru (breaker | mitigation | three_vol)
        print("  5M MSB...", end=' ')
        msb_eng    = MSB5MEngine(vol_mult=1.5, vol_window=20)
        msb_events = msb_eng.detect(df5, df5['atr'])
        msb_events_bull = [e for e in msb_events if e.direction == 'bull']
        msb_events_bear = [e for e in msb_events if e.direction == 'bear']
        _typ = lambda lst, t: sum(1 for e in lst if e.msb_type == t)
        print(f"Bull:{len(msb_events_bull)}  Bear:{len(msb_events_bear)}  "
              f"(breaker:{_typ(msb_events,'breaker')} "
              f"mitigation:{_typ(msb_events,'mitigation')} "
              f"three_vol:{_typ(msb_events,'three_vol')})")

        # Harmonik motor — 5M + 15M + 1H + 4H (resample 15M/4H)
        print("  Harmonik...", end=' ')
        harm_eng = HarmonicEngine(swing=5, min_conf=40.0, max_prz_pct=4.0)
        harmonics: List[HarmonicSignal] = []
        try:
            harmonics += harm_eng.detect(df5, '5m')
            harmonics += harm_eng.detect(resample_ohlcv(df5, '15min'), '15m')
            harmonics += harm_eng.detect(df1, '1h')
            harmonics += harm_eng.detect(resample_ohlcv(df1, '4h'), '4h')
        except Exception as e:
            print(f"(harmonik hata: {e})", end=' ')
        harm_bull = [s for s in harmonics if s.direction == 'bull']
        harm_bear = [s for s in harmonics if s.direction == 'bear']
        _htf = lambda tf: sum(1 for s in harmonics if s.timeframe == tf)
        print(f"Bull:{len(harm_bull)}  Bear:{len(harm_bear)}  "
              f"(5m:{_htf('5m')} 15m:{_htf('15m')} 1h:{_htf('1h')} 4h:{_htf('4h')})")

        # Harmonik PRZ'leri POI olarak da kullan (senaryo-2: 1H FVG gibi,
        # MSB+EMA+RSI+bias ile). Her PRZ → pseudo-FVG; süre dolumu = expiry.
        prz_eng    = FVGEngine('prz', max_age_hours=24 * 30, buf_ratio=0.02)
        przfvg_bull: List[FVG] = []; przfvg_bear: List[FVG] = []
        mit_prz: Dict[int, Any] = {}
        prz_harm: Dict[int, HarmonicSignal] = {}
        for hsig in harmonics:
            top = hsig.prz_high; bottom = hsig.prz_low
            pf = FVG(fvg_id=_next_fvg_id(), timeframe='prz', direction=hsig.direction,
                     index=hsig.detect_time, detect_time=hsig.detect_time,
                     top=top, bottom=bottom, mid=(top + bottom) / 2,
                     gap_size=top - bottom, gap_atr_ratio=0.0, momentum=0.0,
                     quality_score=hsig.conf, created_i=0)
            mit_prz[pf.fvg_id]  = to_naive(hsig.expiry_time)   # süre dolumu
            prz_harm[pf.fvg_id] = hsig
            (przfvg_bull if hsig.direction == 'bull' else przfvg_bear).append(pf)

        # Array'ler
        C    = df5['Close'].values.astype(float)
        O    = df5['Open'].values.astype(float)
        H    = df5['High'].values.astype(float)
        L    = df5['Low'].values.astype(float)
        ATR  = df5['atr'].values.astype(float)
        E100 = df5['ema100'].values.astype(float)
        E200 = df5['ema200'].values.astype(float)
        RSI  = df5['rsi'].values.astype(float)
        TM   = df5.index

        bs      = to_naive(backtest_start)
        bt_idx  = np.where(np.array([to_naive(t) >= bs for t in TM]))[0]

        print(f"\n  Sinyaller taranıyor... ({len(bt_idx)} mum | {bs.date()} sonrası)\n")

        dbg = dict(no_bias=0, no_signal=0, risk_fail=0, generated=0, harmonic=0)

        trades: List[Trade]       = []
        trade_id                  = 0
        in_trade                  = False
        active: Optional[Trade]   = None
        equity                    = float(self.capital)

        for idx in bt_idx:
            if idx + 1 >= len(df5):
                break

            # Açık işlem: TP / SL kontrolü
            if in_trade and active is not None:
                d  = active.signal.direction
                R  = active.risk                     # 1R (puan)
                entry = active.entry_price
                hit_tp = (H[idx] >= active.tp) if d == 'bull' else (L[idx] <= active.tp)
                hit_sl = (L[idx] <= active.sl) if d == 'bull' else (H[idx] >= active.sl)
                if hit_sl and hit_tp:
                    hit_tp = False  # aynı mumda her ikisi → SL önce

                if hit_tp or hit_sl:
                    exit_price = active.tp if hit_tp else active.sl
                    # PnL R-katsayısı: TP→+rr, orijinal SL→-1, breakeven SL→0
                    mult = ((exit_price - entry) if d == 'bull'
                            else (entry - exit_price)) / (R + 1e-10)
                    dollar = mult * active.risk_dollar
                    equity += dollar
                    active.exit_price    = exit_price
                    active.exit_time     = TM[idx]
                    active.result        = ('WIN' if mult > 0.01 else
                                            ('BE' if abs(mult) <= 0.01 else 'LOSS'))
                    active.pnl_dollar    = round(dollar, 2)
                    active.equity_after  = round(equity, 2)
                    trades.append(active)
                    in_trade = False
                    active   = None
                # Breakeven: bu barda çıkış olmadıysa ve 1R kâra ulaşıldıysa
                # SL'i entry'ye taşı (sonraki barlardan itibaren geçerli).
                elif self.breakeven_at_R is not None and active.sl != entry:
                    be_lvl = (entry + self.breakeven_at_R * R if d == 'bull'
                              else entry - self.breakeven_at_R * R)
                    reached = (H[idx] >= be_lvl) if d == 'bull' else (L[idx] <= be_lvl)
                    if reached:
                        active.sl = round(entry, 2)
                # Exit sonrası aynı barda yeni giriş değerlendirilebilir;
                # hâlâ açık işlem varsa bu barı atla.
                if in_trade:
                    continue

            # Sinyal değerlendirme
            signal = self.brain.evaluate(
                idx=idx,
                C=C, O=O, H=H, L=L,
                E100=E100, E200=E200, RSI=RSI,
                TM=TM,
                fvg1_bull=fvg1_bull, mit1_bull=mit1_bull,
                fvg1_bear=fvg1_bear, mit1_bear=mit1_bear,
                fvg1_eng=fvg1_eng,
                msb_events_bull=msb_events_bull,
                msb_events_bear=msb_events_bear,
                przfvg_bull=przfvg_bull, przfvg_bear=przfvg_bear,
                mit_prz=mit_prz, prz_eng=prz_eng, prz_harm=prz_harm,
            )

            if signal is None:
                reason = self.brain.last_skip_reason
                if reason == 'no_bias':
                    dbg['no_bias'] += 1
                else:
                    dbg['no_signal'] += 1
                continue

            # Risk hesapla (stop MSB'den, risk konfluens'ten)
            entry = float(O[idx + 1])
            r = self.risk.compute(signal.direction, entry,
                                  signal.stop_price, equity, signal.risk_fraction)
            if r is None:
                dbg['risk_fail'] += 1
                continue

            # İşlem oluştur
            trade_id += 1
            dbg['generated'] += 1
            if signal.harmonic is not None:
                dbg['harmonic'] += 1
            active = Trade(
                trade_id      = trade_id,
                signal        = signal,
                entry_price   = round(entry, 2),
                sl            = r['sl'],
                tp            = r['tp'],
                risk          = r['risk'],
                risk_pct      = r['risk_pct'],
                risk_dollar   = r['risk_dollar'],
                rr            = self.risk.rr,
                risk_fraction = r['risk_fraction'],
            )
            in_trade = True
            # Kullanım kuralı: tetikleyici 1H FVG'yi tüket + pending'den çıkar
            if signal.trigger_fvg is not None:
                fid = signal.trigger_fvg.fvg_id
                self.brain.used_fvg_ids.add(fid)
                for d in ('bull', 'bear'):
                    self.brain.pending[d] = [
                        p for p in self.brain.pending[d] if p['fvg_id'] != fid]

        # Dönem sonu açık işlem
        if in_trade and active is not None:
            active.exit_price    = float(C[-1])
            active.exit_time     = TM[-1]
            active.result        = 'OPEN'
            active.equity_after  = round(equity, 2)
            trades.append(active)

        st = self.brain.stats
        print(f"  FİLTRE ÖZETİ:")
        print(f"    Bias filtresi      : {dbg['no_bias']:>6}")
        print(f"    Sinyal yok         : {dbg['no_signal']:>6}")
        print(f"      ├─ Adım1: 1H FVG wick dokunuş yok: {st['step1_fail']:>6}")
        print(f"      ├─ Adım2: dokundu, konfluens yok : {st['step2_fail']:>6}")
        print(f"      └─ Adım3: konfluens var, MSB yok : {st['step3_fail']:>6}")
        print(f"    Risk filtresi      : {dbg['risk_fail']:>6}")
        print(f"    Üretilen sinyaller : {dbg['generated']:>6}")
        print(f"      └─ Harmonik PRZ POI (senaryo-2)  : {dbg['harmonic']:>6}")
        print(f"\n  TOPLAM İŞLEM: {len(trades)}")
        return trades


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 8: PERFORMANS ANALİTİK ENGİNİ
# ═══════════════════════════════════════════════════════════════════════════

class PerformanceAnalytics:
    """
    Wall Street metrikleri:
    Sharpe, Sortino, Calmar, Profit Factor, VaR(95), CVaR(95),
    Kelly Kriteri, Beklenen Değer, Ardışık kayıp serisi.
    """

    def __init__(self, trades: List[Trade], initial_capital: float = 10_000):
        self.trades  = trades
        self.capital = initial_capital
        self.done    = [t for t in trades if t.result in ('WIN', 'LOSS', 'BE')]

    def compute(self) -> Optional[Dict]:
        if not self.done:
            return None

        pnls = np.array([t.pnl_dollar for t in self.done])
        eq   = self.capital + np.cumsum(pnls)
        peak = np.maximum.accumulate(eq)
        dd   = (peak - eq) / (peak + 1e-10) * 100

        wins      = sum(1 for t in self.done if t.result == 'WIN')
        losses    = sum(1 for t in self.done if t.result == 'LOSS')
        be        = sum(1 for t in self.done if t.result == 'BE')
        total     = len(self.done)
        wr        = wins / (wins + losses) if (wins + losses) else 0.0   # BE hariç
        net_pnl   = float(pnls.sum())
        ret_pct   = net_pnl / self.capital * 100

        win_p  = pnls[pnls > 0]
        loss_p = pnls[pnls < 0]
        avg_w  = float(win_p.mean())  if len(win_p)  else 0.0
        avg_l  = float(loss_p.mean()) if len(loss_p) else 0.0
        pf     = float(win_p.sum() / abs(loss_p.sum())) if len(loss_p) else float('inf')

        # Günlük getiri
        entry_times = pd.to_datetime([to_naive(t.signal.entry_time) for t in self.done])
        daily = pd.Series(pnls, index=entry_times).resample('D').sum() / self.capital
        sharpe  = float(daily.mean() / (daily.std() + 1e-10) * np.sqrt(252))
        neg_d   = daily[daily < 0]
        sortino = float(daily.mean() / (neg_d.std() + 1e-10) * np.sqrt(252)) if len(neg_d) else float('inf')
        calmar  = float(ret_pct / (float(dd.max()) + 1e-10))

        var95  = float(np.percentile(pnls, 5))
        cvar95 = float(pnls[pnls <= var95].mean()) if any(pnls <= var95) else var95

        avg_rr = abs(avg_w / avg_l) if avg_l != 0 else 2.0
        kelly  = wr - (1 - wr) / (avg_rr + 1e-10)
        ev     = wr * avg_w + (1 - wr) * avg_l

        max_streak = cur_streak = 0
        for t in self.done:
            cur_streak = cur_streak + 1 if t.result == 'LOSS' else 0
            max_streak = max(max_streak, cur_streak)

        return {
            'total'         : total,
            'wins'          : wins,
            'losses'        : losses,
            'breakeven'     : be,
            'win_rate'      : wr,
            'net_pnl'       : net_pnl,
            'ret_pct'       : ret_pct,
            'final_equity'  : self.capital + net_pnl,
            'max_dd'        : float(dd.max()),
            'profit_factor' : pf,
            'sharpe'        : sharpe,
            'sortino'       : sortino,
            'calmar'        : calmar,
            'var_95'        : var95,
            'cvar_95'       : cvar95,
            'kelly'         : kelly,
            'kelly_half'    : max(0.0, kelly / 2),
            'avg_win'       : avg_w,
            'avg_loss'      : avg_l,
            'ev_per_trade'  : ev,
            'max_streak_l'  : max_streak,
            'equity_curve'  : eq,
            'drawdown'      : dd,
        }

    def print_report(self, m: Dict):
        SEP = "═" * 65
        entry_times = [to_naive(t.signal.entry_time) for t in self.done]
        print(f"\n{SEP}")
        print("  XAUUSD  │  FVG Strategy Engine  │  v10.0 │  Performans")
        if entry_times:
            print(f"  Dönem : {min(entry_times).date()}  →  {max(entry_times).date()}")
        print(SEP)

        print(f"\n  ── GENEL ──────────────────────────────────────────────────")
        print(f"  Toplam İşlem        : {m['total']}")
        print(f"  Kazanç              : {m['wins']:3d}  (%{m['win_rate']*100:.1f} WR, BE hariç)")
        print(f"  Kayıp               : {m['losses']:3d}  (%{(1-m['win_rate'])*100:.1f})")
        if m.get('breakeven', 0):
            print(f"  Breakeven           : {m['breakeven']:3d}")

        print(f"\n  ── KARLILIK ($10,000 başlangıç | %0.5 risk/işlem) ─────────")
        print(f"  Net PnL             : ${m['net_pnl']:>+10,.2f}")
        print(f"  Toplam Getiri       : %{m['ret_pct']:>+8.2f}")
        print(f"  Son Sermaye         : ${m['final_equity']:>10,.2f}")
        print(f"  Beklenen Değer/İşlem: ${m['ev_per_trade']:>+8.2f}")

        print(f"\n  ── RİSK METRİKLERİ ─────────────────────────────────────────")
        print(f"  Maks Drawdown       : %{m['max_dd']:.2f}")
        print(f"  Profit Factor       : {m['profit_factor']:.3f}")
        print(f"  Sharpe Ratio        : {m['sharpe']:.3f}")
        print(f"  Sortino Ratio       : {m['sortino']:.3f}")
        print(f"  Calmar Ratio        : {m['calmar']:.3f}")
        print(f"  VaR (95%)           : ${m['var_95']:>+8.2f}")
        print(f"  CVaR (95%)          : ${m['cvar_95']:>+8.2f}")
        print(f"  Kelly Kriteri       : %{m['kelly']*100:.2f}")
        print(f"  Yarım Kelly         : %{m['kelly_half']*100:.2f}")
        print(f"  Maks Ardışık Kayıp  : {m['max_streak_l']}")
        print(f"  Ort Kazanç/İşlem    : ${m['avg_win']:>+8.2f}")
        print(f"  Ort Kayıp/İşlem     : ${m['avg_loss']:>+8.2f}")

        # Sinyal kaynakları
        conf_d: Dict[str, Dict] = {}
        for t in self.done:
            ct = t.signal.confirmation_type
            conf_d.setdefault(ct, {'n': 0, 'w': 0, 'pnl': 0.0})
            conf_d[ct]['n']   += 1
            conf_d[ct]['w']   += 1 if t.result == 'WIN' else 0
            conf_d[ct]['pnl'] += t.pnl_dollar
        print(f"\n  ── SİNYAL KAYNAKLARI ───────────────────────────────────────")
        for src, d in conf_d.items():
            wr = d['w'] / d['n'] * 100 if d['n'] else 0
            print(f"  {src:<16} : {d['n']:3d} işlem | %{wr:.0f} WR | ${d['pnl']:>+8.2f}")

        # MSB türü dağılımı (breaker / mitigation / three_vol)
        msb_d: Dict[str, Dict] = {}
        for t in self.done:
            mt = t.signal.msb_type or '?'
            msb_d.setdefault(mt, {'n': 0, 'w': 0, 'pnl': 0.0})
            msb_d[mt]['n']   += 1
            msb_d[mt]['w']   += 1 if t.result == 'WIN' else 0
            msb_d[mt]['pnl'] += t.pnl_dollar
        print(f"\n  ── MSB TÜRÜ ─────────────────────────────────────────────────")
        for mt, d in msb_d.items():
            wr = d['w'] / d['n'] * 100 if d['n'] else 0
            print(f"  {mt:<16} : {d['n']:3d} işlem | %{wr:.0f} WR | ${d['pnl']:>+8.2f}")

        # Konfluens dağılımı (1 → 0.5R, 2 → 1R)
        cc_d: Dict[int, Dict] = {}
        for t in self.done:
            cc = t.signal.confluence_count
            cc_d.setdefault(cc, {'n': 0, 'w': 0, 'pnl': 0.0})
            cc_d[cc]['n']   += 1
            cc_d[cc]['w']   += 1 if t.result == 'WIN' else 0
            cc_d[cc]['pnl'] += t.pnl_dollar
        print(f"\n  ── KONFLUENS (risk) ─────────────────────────────────────────")
        for cc in sorted(cc_d):
            d   = cc_d[cc]
            lbl = "EMA+RSI (1R)" if cc == 2 else "Tek onay (0.5R)"
            wr  = d['w'] / d['n'] * 100 if d['n'] else 0
            print(f"  {lbl:<16} : {d['n']:3d} işlem | %{wr:.0f} WR | ${d['pnl']:>+8.2f}")

        # Yön analizi
        dir_d: Dict[str, Dict] = {}
        for t in self.done:
            dd_ = t.signal.direction
            dir_d.setdefault(dd_, {'n': 0, 'w': 0, 'pnl': 0.0})
            dir_d[dd_]['n']   += 1
            dir_d[dd_]['w']   += 1 if t.result == 'WIN' else 0
            dir_d[dd_]['pnl'] += t.pnl_dollar
        print(f"\n  ── YÖN ANALİZİ ─────────────────────────────────────────────")
        for d, data in dir_d.items():
            lbl = "LONG  (Bull)" if d == 'bull' else "SHORT (Bear)"
            wr  = data['w'] / data['n'] * 100 if data['n'] else 0
            print(f"  {lbl} : {data['n']:3d} işlem | %{wr:.0f} WR | ${data['pnl']:>+8.2f}")

        # Güven skoru dağılımı
        print(f"\n  ── GÜVEN SKORU DAĞILIMI ────────────────────────────────────")
        for lo, hi, lbl in [(0,40,'Düşük'), (40,60,'Orta'),
                             (60,80,'Yüksek'), (80,101,'Çok Yüksek')]:
            sub = [t for t in self.done if lo <= t.signal.confidence < hi]
            if sub:
                wr  = sum(1 for t in sub if t.result == 'WIN') / len(sub) * 100
                pnl = sum(t.pnl_dollar for t in sub)
                print(f"  {lbl:<12} ({lo:2d}–{hi:3d}) : "
                      f"{len(sub):3d} işlem | %{wr:.0f} WR | ${pnl:>+8.2f}")

        # Haftalık performans
        print(f"\n  ── HAFTALIK PERFORMANS ─────────────────────────────────────")
        entry_s = pd.Series(
            {to_naive(t.signal.entry_time): t.pnl_dollar for t in self.done})
        weekly = entry_s.resample('W').agg(['sum', 'count'])
        for week, row in weekly.iterrows():
            cnt  = int(row['count'])
            s    = float(row['sum'])
            bar  = "█" * min(int(abs(s) / 8), 35)
            sign = "+" if s >= 0 else ""
            wr_w = sum(1 for t in self.done
                       if to_naive(t.signal.entry_time).isocalendar()[:2] ==
                       to_naive(week).isocalendar()[:2] and t.result == 'WIN')
            wr_pct = wr_w / cnt * 100 if cnt else 0
            print(f"  {str(week.date())} : {cnt:2d} işlem | "
                  f"${sign}{s:>+7.0f} | %{wr_pct:.0f} WR | {bar}")

        print(f"\n{SEP}")


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 9: RAPOR ÜRETİCİSİ
# ═══════════════════════════════════════════════════════════════════════════

class ReportGenerator:
    """Profesyonel görsel rapor ve CSV çıkışı."""

    @staticmethod
    def generate(trades: List[Trade], metrics: Dict,
                 initial_capital: float = 10_000,
                 out: str = 'xauusd_fvg_v9_report.png'):
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import matplotlib.gridspec as gridspec
            from matplotlib.ticker import FuncFormatter

            BG = '#0a0a14'; PN = '#10102a'
            G  = '#00e5a0'; R  = '#ff3f5b'
            GD = '#ffd700'; TX = '#d0d0e0'
            GR = '#1a1a3a'; OR = '#ff9800'
            BL = '#4fc3f7'

            done = [t for t in trades if t.result in ('WIN', 'LOSS', 'BE')]
            if not done:
                print("  Grafik için tamamlanan işlem yok."); return

            pnls = np.array([t.pnl_dollar for t in done])
            eq   = initial_capital + np.cumsum(pnls)
            peak = np.maximum.accumulate(eq)
            dd   = (peak - eq) / (peak + 1e-10) * 100
            x    = np.arange(len(done))

            fig = plt.figure(figsize=(22, 17), facecolor=BG)
            dr  = (f"{to_naive(done[0].signal.entry_time).date()} → "
                   f"{to_naive(done[-1].signal.entry_time).date()}")
            fig.suptitle(
                f'XAUUSD  │  FVG Engine v10.0 │  {dr}  '
                f'│  WR:{metrics["win_rate"]*100:.1f}%  '
                f'PF:{metrics["profit_factor"]:.2f}  '
                f'Sharpe:{metrics["sharpe"]:.2f}  '
                f'MaxDD:%{metrics["max_dd"]:.2f}',
                color=GD, fontsize=11, fontweight='bold', y=0.99)

            gs = gridspec.GridSpec(4, 3, figure=fig, hspace=0.55, wspace=0.32)

            def sty(ax, title=''):
                ax.set_facecolor(PN)
                ax.tick_params(colors=TX, labelsize=8)
                for lbl in ax.get_xticklabels() + ax.get_yticklabels():
                    lbl.set_color(TX)
                ax.xaxis.label.set_color(TX)
                ax.yaxis.label.set_color(TX)
                if title:
                    ax.set_title(title, color=TX, fontweight='bold', fontsize=9)
                for sp in ax.spines.values():
                    sp.set_edgecolor(GR)
                ax.grid(True, color=GR, lw=0.4, alpha=0.5)

            # 1. Equity Curve
            ax1 = fig.add_subplot(gs[0, :])
            ax1.fill_between(x, initial_capital, eq,
                             where=eq >= initial_capital, color=G, alpha=0.15)
            ax1.fill_between(x, initial_capital, eq,
                             where=eq < initial_capital, color=R, alpha=0.25)
            ax1.plot(x, eq, color=G, lw=2.0, label='Equity', zorder=4)
            ax1.plot(x, peak, color=GD, lw=0.8, ls='--', alpha=0.5, label='Peak')
            ax1.fill_between(x, eq, peak, color=R, alpha=0.10, label='DD Zone')
            ax1.axhline(initial_capital, color='white', lw=0.5, ls=':')
            wm = np.array([t.result == 'WIN'  for t in done])
            lm = np.array([t.result == 'LOSS' for t in done])
            ax1.scatter(x[wm], eq[wm], color=G, s=35, zorder=6, alpha=0.9)
            ax1.scatter(x[lm], eq[lm], color=R, s=35, marker='v', zorder=6, alpha=0.9)
            ax1.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'${v:,.0f}'))
            ax1.set_xlabel('İşlem #')
            ax1.set_ylabel('Sermaye ($)')
            ax1.legend(facecolor=PN, labelcolor=TX, fontsize=8, loc='upper left')
            sty(ax1, 'Equity Curve  │  ▲ WIN  ▼ LOSS')

            # 2. Drawdown
            ax2 = fig.add_subplot(gs[1, :])
            ax2.fill_between(x, 0, -dd, color=R, alpha=0.40)
            ax2.plot(x, -dd, color=R, lw=1.2)
            ax2.axhline(0, color='white', lw=0.4)
            ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'%{abs(v):.1f}'))
            ax2.set_xlabel('İşlem #')
            ax2.set_ylabel('Drawdown %')
            sty(ax2, f'Drawdown  │  Maks: %{metrics["max_dd"]:.2f}')

            # 3. Haftalık PnL
            ax3 = fig.add_subplot(gs[2, :2])
            entry_s = pd.Series(
                {to_naive(t.signal.entry_time): t.pnl_dollar for t in done})
            weekly = entry_s.resample('W').sum()
            cw     = [G if v >= 0 else R for v in weekly.values]
            bars   = ax3.bar(range(len(weekly)), weekly.values,
                             color=cw, alpha=0.85, width=0.6)
            for b, v in zip(bars, weekly.values):
                ax3.text(b.get_x() + b.get_width() / 2,
                         v + (3 if v >= 0 else -18),
                         f'${v:+,.0f}', ha='center', fontsize=7, color=TX)
            ax3.axhline(0, color='white', lw=0.4)
            ax3.set_xticks(range(len(weekly)))
            ax3.set_xticklabels(
                [str(w.date()) for w in weekly.index], rotation=30, fontsize=7)
            ax3.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'${v:,.0f}'))
            sty(ax3, 'Haftalık Net PnL ($)')

            # 4. Win/Loss pasta
            ax4 = fig.add_subplot(gs[2, 2])
            wn = metrics['wins']
            ln = metrics['losses']
            ax4.pie([wn, ln],
                    labels=[f'WIN\n{wn}', f'LOSS\n{ln}'],
                    colors=[G, R], autopct='%1.1f%%', startangle=90,
                    wedgeprops={'edgecolor': BG, 'linewidth': 2.5},
                    textprops={'color': TX, 'fontsize': 10})
            sty(ax4, f'Win/Loss  │  %{metrics["win_rate"]*100:.1f} WR')

            # 5. Sinyal kaynakları
            ax5 = fig.add_subplot(gs[3, 0])
            conf_d: Dict[str, int] = {}
            for t in done:
                conf_d[t.signal.confirmation_type] = conf_d.get(
                    t.signal.confirmation_type, 0) + 1
            cs   = ['#7bed9f', '#70a1ff', '#ffa502']
            b5   = ax5.bar(conf_d.keys(), conf_d.values(),
                           color=cs[:len(conf_d)], alpha=0.85)
            for b, v in zip(b5, conf_d.values()):
                ax5.text(b.get_x() + b.get_width() / 2, v + 0.1,
                         str(v), ha='center', fontsize=9, color=TX)
            ax5.set_ylabel('İşlem Sayısı')
            plt.setp(ax5.get_xticklabels(), rotation=10, fontsize=8, color=TX)
            sty(ax5, 'Sinyal Kaynakları')

            # 6. PnL dağılımı
            ax6 = fig.add_subplot(gs[3, 1])
            pos_p = [t.pnl_dollar for t in done if t.pnl_dollar > 0]
            neg_p = [t.pnl_dollar for t in done if t.pnl_dollar < 0]
            if pos_p: ax6.hist(pos_p, bins=12, color=G, alpha=0.7, label='WIN')
            if neg_p: ax6.hist(neg_p, bins=12, color=R, alpha=0.7, label='LOSS')
            ax6.axvline(0, color='white', lw=0.6)
            ax6.axvline(metrics['var_95'], color=OR, lw=1.2, ls='--',
                        label=f'VaR95: ${metrics["var_95"]:+.0f}')
            ax6.set_xlabel('PnL ($)')
            ax6.legend(facecolor=PN, labelcolor=TX, fontsize=7)
            sty(ax6, 'PnL Dağılımı')

            # 7. Metrik kutusu
            ax7 = fig.add_subplot(gs[3, 2])
            ax7.axis('off')
            ax7.set_facecolor(PN)
            lines = [
                ('Sharpe',       f"{metrics['sharpe']:.3f}"),
                ('Sortino',      f"{metrics['sortino']:.3f}"),
                ('Calmar',       f"{metrics['calmar']:.3f}"),
                ('Profit Factor',f"{metrics['profit_factor']:.3f}"),
                ('Max DD',       f"%{metrics['max_dd']:.2f}"),
                ('Kelly Half',   f"%{metrics['kelly_half']*100:.2f}"),
                ('Avg Win',      f"${metrics['avg_win']:+.2f}"),
                ('Avg Loss',     f"${metrics['avg_loss']:+.2f}"),
                ('EV/Trade',     f"${metrics['ev_per_trade']:+.2f}"),
                ('Max L-Streak', f"{metrics['max_streak_l']}"),
            ]
            ax7.text(0.5, 1.02, 'Key Metrics', transform=ax7.transAxes,
                     ha='center', color=GD, fontsize=9, fontweight='bold')
            y_pos = 0.92
            for label, val in lines:
                ax7.text(0.05, y_pos, label, transform=ax7.transAxes,
                         color=TX, fontsize=8)
                ax7.text(0.95, y_pos, val, transform=ax7.transAxes,
                         ha='right', color=BL, fontsize=8, fontweight='bold')
                y_pos -= 0.088

            plt.savefig(out, dpi=150, bbox_inches='tight', facecolor=BG)
            plt.close()
            print(f"\n  Grafik kaydedildi → {out}")

        except Exception as e:
            print(f"\n  Grafik oluşturulamadı: {e}")

    @staticmethod
    def save_csv(trades: List[Trade], filename: str = 'xauusd_fvg_v10_trades.csv'):
        if not trades:
            return
        rows = []
        for t in trades:
            s = t.signal
            rows.append({
                'trade_id'        : t.trade_id,
                'entry_time'      : to_naive(s.entry_time),
                'exit_time'       : to_naive(t.exit_time) if t.exit_time else None,
                'direction'       : s.direction,
                'confirmation'    : s.confirmation_type,
                'confluence_count': s.confluence_count,
                'msb_type'        : s.msb_type,
                'harmonic_pattern': s.harmonic.pattern   if s.harmonic else '',
                'harmonic_tf'     : s.harmonic.timeframe if s.harmonic else '',
                'confidence'      : round(s.confidence, 2),
                'fvg1_quality'    : round(s.trigger_fvg.quality_score, 2),
                'fvg1_gap_size'   : round(s.trigger_fvg.gap_size, 2),
                'fvg1_gap_atr'    : round(s.trigger_fvg.gap_atr_ratio, 4),
                'stop_price'      : round(s.stop_price, 2),
                'risk_fraction'   : s.risk_fraction,
                'entry_price'     : t.entry_price,
                'sl'              : t.sl,
                'tp'              : t.tp,
                'risk_pts'        : t.risk,
                'risk_pct'        : t.risk_pct,
                'risk_dollar'     : t.risk_dollar,
                'exit_price'      : t.exit_price,
                'result'          : t.result,
                'pnl_dollar'      : t.pnl_dollar,
                'equity_after'    : t.equity_after,
                'rr'              : t.rr,
            })
        pd.DataFrame(rows).to_csv(filename, index=False, float_format='%.4f')
        print(f"  Trade logu kaydedildi → {filename}")


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 10: ANA FONKSİYON
# ═══════════════════════════════════════════════════════════════════════════

def main():
    INITIAL_CAPITAL = 10_000

    # Veri
    df_1h, df_5m, bt_start = DataEngine.download(verbose=True)

    # Bileşenler — BIAS=0 ortam değişkeni ile bias'sız test (weekly_bias.json'a dokunmadan)
    use_bias = os.environ.get('BIAS', '1') != '0'
    bias_provider = WeeklyBiasProvider('weekly_bias.json') if use_bias else None
    if not use_bias:
        print("  [BIAS=0] Haftalık bias DEVRE DIŞI — her iki yön serbest.\n")
    brain    = MarketBrain(bias_provider=bias_provider)
    risk_mgr = RiskManager(rr=2.0, sl_buffer=0.0005)
    # Fix 1:2 RR (breakeven kapalı). BE testi için breakeven_at_R=1.0 verilebilir.
    engine   = BacktestEngine(brain, risk_mgr, initial_capital=INITIAL_CAPITAL,
                              breakeven_at_R=None)

    # Backtest
    trades = engine.run(df_1h, df_5m, bt_start)
    if not trades:
        print("\n  Hiç işlem üretilemedi."); return

    done = [t for t in trades if t.result in ('WIN', 'LOSS')]
    if not done:
        print("\n  Tamamlanan işlem yok."); return

    # Performans
    analytics = PerformanceAnalytics(trades, INITIAL_CAPITAL)
    metrics   = analytics.compute()
    if metrics:
        analytics.print_report(metrics)
        ReportGenerator.generate(trades, metrics, INITIAL_CAPITAL,
                                 out='xauusd_fvg_v10_report.png')
        ReportGenerator.save_csv(trades, 'xauusd_fvg_v10_trades.csv')

    print("\n  Backtest tamamlandı!")


if __name__ == '__main__':
    main()
