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
class TradeSignal:
    """Tam onaylı trade sinyali."""
    entry_time        : Any
    direction         : str
    trigger_fvg       : FVG
    msc_signal        : MSCSignal
    confirmation_type : str       # 'RSI_DIV' | 'FVG_5M' | 'EMA_CONFIRM'
    confidence        : float     # 0–100
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
    rr          : float = 2.0
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

    TICKER = "GC=F"

    @staticmethod
    def download(verbose: bool = True):
        end      = datetime.now()
        start_1h = end - timedelta(days=90)
        start_5m = end - timedelta(days=57)
        bt_start = end - timedelta(days=30)

        if verbose:
            print("═" * 65)
            print("  XAUUSD  │  FVG Strategy Engine  │  v9.0  │  Day Trade")
            print("═" * 65)
            print(f"\n  Veri indiriliyor... ({DataEngine.TICKER})")

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

        if verbose:
            wm = len(df_5m[df_5m.index < bt_start])
            bt = len(df_5m[df_5m.index >= bt_start])
            print(f"  1H : {len(df_1h)} mum  ({start_1h.date()} → {end.date()})")
            print(f"  5M : {len(df_5m)} mum  (ısınma:{wm}  backtest:{bt})")
            print(f"  Backtest dönemi: {bt_start.date()} → {end.date()}\n")

        return df_1h, df_5m, bt_start


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 3: İNDİKATÖR ENGİNİ
# ═══════════════════════════════════════════════════════════════════════════

class IndicatorEngine:
    """Vektörize teknik göstergeler."""

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        d  = series.diff()
        ag = d.clip(lower=0).ewm(com=period - 1, min_periods=period).mean()
        al = (-d.clip(upper=0)).ewm(com=period - 1, min_periods=period).mean()
        return 100 - 100 / (1 + ag / (al + 1e-10))

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        h  = df['High']
        l  = df['Low']
        pc = df['Close'].shift(1)
        tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
        return tr.ewm(span=period, adjust=False).mean()

    @staticmethod
    def msc_signals(df: pd.DataFrame, lookback: int = 10) -> pd.DataFrame:
        """BOS / CHoCH tespiti — momentum ve body ratio ile zenginleştirilmiş."""
        df = df.copy()
        for col in ('msc_bull', 'msc_bear'):
            df[col] = False
        for col in ('msc_bull_mom', 'msc_bear_mom'):
            df[col] = 0.0

        H = df['High'].values.astype(float)
        L = df['Low'].values.astype(float)
        C = df['Close'].values.astype(float)
        O = df['Open'].values.astype(float)

        for i in range(lookback, len(df)):
            wh  = float(np.max(H[i - lookback:i]))
            wl  = float(np.min(L[i - lookback:i]))
            rng = H[i] - L[i]

            if C[i] > wh and C[i - 1] <= wh:
                mom = min(1.0, (C[i] - wh) / (rng + 1e-10))
                df.iloc[i, df.columns.get_loc('msc_bull')]     = True
                df.iloc[i, df.columns.get_loc('msc_bull_mom')] = float(mom)

            if C[i] < wl and C[i - 1] >= wl:
                mom = min(1.0, (wl - C[i]) / (rng + 1e-10))
                df.iloc[i, df.columns.get_loc('msc_bear')]     = True
                df.iloc[i, df.columns.get_loc('msc_bear_mom')] = float(mom)

        return df

    @staticmethod
    def swing_low(L: np.ndarray, idx: int, lookback: int = 30, strength: int = 2) -> float:
        end   = idx - strength
        start = max(strength, idx - lookback)
        for j in range(end, start - 1, -1):
            if j - strength < 0:
                continue
            if (all(L[j] < L[j - k] for k in range(1, strength + 1)) and
                    all(L[j] < L[j + k] for k in range(1, strength + 1))):
                return float(L[j])
        return float(np.min(L[max(0, idx - lookback):idx + 1]))

    @staticmethod
    def swing_high(H: np.ndarray, idx: int, lookback: int = 30, strength: int = 2) -> float:
        end   = idx - strength
        start = max(strength, idx - lookback)
        for j in range(end, start - 1, -1):
            if j - strength < 0:
                continue
            if (all(H[j] > H[j - k] for k in range(1, strength + 1)) and
                    all(H[j] > H[j + k] for k in range(1, strength + 1))):
                return float(H[j])
        return float(np.max(H[max(0, idx - lookback):idx + 1]))

    @staticmethod
    def significant_swing_low(
        L: np.ndarray, H: np.ndarray, atr: np.ndarray,
        idx: int,
        lookback: int = 50,
        min_strength: int = 2,
        max_strength: int = 5,
        min_atr_mult: float = 0.3,
    ) -> Tuple[float, float]:
        """ATR-adaptive swing low. Returns (price, score). Higher score = more significant."""
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
                atr_val = float(atr[j]) if float(atr[j]) > 0 else 1.0
                left_depth  = float(np.min(L[j - s:j]))    - float(L[j])
                right_depth = float(np.min(L[j + 1:j + s + 1])) - float(L[j])
                swing_depth = (left_depth + right_depth) / 2.0
                if swing_depth < min_atr_mult * atr_val:
                    break
                score = s + swing_depth / atr_val
                candidates.append((float(L[j]), score))
                break
        if candidates:
            return max(candidates, key=lambda x: x[1])
        return float(np.min(L[max(0, idx - lookback):idx + 1])), 0.0

    @staticmethod
    def significant_swing_high(
        H: np.ndarray, L: np.ndarray, atr: np.ndarray,
        idx: int,
        lookback: int = 50,
        min_strength: int = 2,
        max_strength: int = 5,
        min_atr_mult: float = 0.3,
    ) -> Tuple[float, float]:
        """ATR-adaptive swing high. Returns (price, score). Higher score = more significant."""
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
                atr_val = float(atr[j]) if float(atr[j]) > 0 else 1.0
                left_depth  = float(H[j]) - float(np.max(H[j - s:j]))
                right_depth = float(H[j]) - float(np.max(H[j + 1:j + s + 1]))
                swing_depth = (left_depth + right_depth) / 2.0
                if swing_depth < min_atr_mult * atr_val:
                    break
                score = s + swing_depth / atr_val
                candidates.append((float(H[j]), score))
                break
        if candidates:
            return max(candidates, key=lambda x: x[1])
        return float(np.max(H[max(0, idx - lookback):idx + 1])), 0.0


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
                detect_time   = T[i],
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
            fvg_time = to_naive(fvg.index)
            start_i  = next((j for j in range(n)
                             if to_naive(T[j]) > fvg_time), None)
            if start_i is None:
                mit_map[fvg.fvg_id] = None
                continue

            mit_map[fvg.fvg_id] = None
            for j in range(start_i, n):
                c = C[j]
                if fvg.direction == 'bull' and c <= fvg.top:
                    mit_map[fvg.fvg_id] = to_naive(T[j]); break
                elif fvg.direction == 'bear' and c >= fvg.bottom:
                    mit_map[fvg.fvg_id] = to_naive(T[j]); break

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
                          window_secs: int = 3600) -> Tuple[bool, float]:
        """Son N saniyede mitigasyon yaşamamış FVG var mı? (bool, kalite)"""
        t      = to_naive(current_time)
        cutoff = t - timedelta(seconds=window_secs)
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

    Adım 1 → Adım 2 → Adım 3 (RSI | FVG5 | EMA)

    Haftalık bias: WeeklyBiasProvider üzerinden. Bias yoksa o hafta işlem yapılmaz.
    Yalnızca London open (07-12 UTC) ve NY open (13-17 UTC) seansları.
    """

    RSI_WINDOW  = 10    # mum sayısı (5M → ~50 dk)
    MSC_WINDOW  = 12    # mum sayısı (5M → ~60 dk)
    FVG5_WIN    = 3600  # saniye (60 dk)
    SESSIONS    = [(7, 12), (13, 17)]

    def __init__(self, bias_provider: Optional['WeeklyBiasProvider'] = None):
        self.bias = bias_provider
        self.last_skip_reason: Optional[str] = None

    def in_session(self, hour: int) -> bool:
        return any(s <= hour < e for s, e in self.SESSIONS)

    # ── RSI Diverjansı ──────────────────────────────────────────────────
    def rsi_divergence(self, prices: np.ndarray,
                       rsi_vals: np.ndarray) -> Tuple[Optional[str], float]:
        """
        Regular bull: fiyat düşük dip → RSI yüksek dip → yukarı dönüş
        Regular bear: fiyat yüksek tepe → RSI düşük tepe → aşağı dönüş
        Döndürür: (tip, güç 0-1)
        """
        if len(prices) < 4 or np.any(np.isnan(rsi_vals)):
            return None, 0.0
        p    = prices.astype(float)
        r    = rsi_vals.astype(float)
        half = max(2, len(p) // 2)
        il   = int(np.argmin(p[:half]))
        ih   = int(np.argmax(p[:half]))

        if p[-1] < p[il] and r[-1] > r[il]:
            strength = min(1.0, ((p[il] - p[-1]) / (abs(p[il]) + 1e-10) +
                                 (r[-1] - r[il]) / (abs(r[il]) + 1e-10)) * 2.5)
            return 'bull', float(strength)

        if p[-1] > p[ih] and r[-1] < r[ih]:
            strength = min(1.0, ((p[-1] - p[ih]) / (abs(p[ih]) + 1e-10) +
                                 (r[ih] - r[-1]) / (abs(r[ih]) + 1e-10)) * 2.5)
            return 'bear', float(strength)

        return None, 0.0

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
                 MSC_B: np.ndarray, MSC_R: np.ndarray,
                 MSC_B_M: np.ndarray, MSC_R_M: np.ndarray,
                 TM: pd.Index,
                 fvg1_bull: List[FVG], mit1_bull: Dict,
                 fvg1_bear: List[FVG], mit1_bear: Dict,
                 fvg5_bull: List[FVG], mit5_bull: Dict,
                 fvg5_bear: List[FVG], mit5_bear: Dict,
                 fvg1_eng: 'FVGEngine',
                 fvg5_eng: 'FVGEngine') -> Optional[TradeSignal]:

        cur_time  = TM[idx]
        cur_close = float(C[idx])
        hour      = to_naive(cur_time).hour

        # ── HAFTALIK BİAS FİLTRESİ ──────────────────────────────────────
        if self.bias is not None:
            weekly_dir = self.bias.get(cur_time)
            if weekly_dir is None:
                self.last_skip_reason = 'no_bias'
                return None
        else:
            weekly_dir = None   # bias dosyası yok → her iki yön serbest

        # Seans filtresi
        if not self.in_session(hour):
            return None

        t = to_naive(cur_time)
        best_signal: Optional[TradeSignal] = None
        best_conf = 0.0

        for direction in ('bull', 'bear'):
            # Bias varsa sadece bias yönünde işlem
            if weekly_dir is not None and direction != weekly_dir:
                continue
            fvg1_raw = fvg1_bull if direction == 'bull' else fvg1_bear
            mit1     = mit1_bull if direction == 'bull' else mit1_bear
            fvg5_raw = fvg5_bull if direction == 'bull' else fvg5_bear
            mit5     = mit5_bull if direction == 'bull' else mit5_bear

            # ── ADIM 1: Fiyat aktif 1H FVG'de mi? ───────────────────
            active_1h    = fvg1_eng.get_active(fvg1_raw, mit1, t)
            touching_fvg = fvg1_eng.price_touching(cur_close, active_1h)
            if touching_fvg is None:
                continue

            # ── ADIM 2: Son 60 dk'da beklenti yönünde 5M MSC var mı? ─
            ws      = max(0, idx - self.MSC_WINDOW)
            msc_arr = MSC_B if direction == 'bull' else MSC_R
            msc_mom = MSC_B_M if direction == 'bull' else MSC_R_M

            best_msc: Optional[MSCSignal] = None
            best_msc_mom = 0.0
            for j in range(ws, idx + 1):
                if msc_arr[j] and float(msc_mom[j]) > best_msc_mom:
                    best_msc_mom = float(msc_mom[j])
                    rng  = float(H[j] - L[j])
                    body = abs(float(C[j]) - float(O[j]))
                    best_msc = MSCSignal(
                        time           = TM[j],
                        direction      = direction,
                        idx            = j,
                        swing_level    = 0.0,
                        close_at_break = float(C[j]),
                        momentum_score = best_msc_mom,
                        body_ratio     = body / (rng + 1e-10),
                    )

            if best_msc is None:
                continue

            # ── ADIM 3: Onay ─────────────────────────────────────────
            conf_type    = None
            conf_val     = 0.0
            rsi_div_type = None
            fvg5_q       = 0.0
            ema_dist     = 0.0

            # 3a: RSI Diverjansı
            sl_ = max(0, idx - self.RSI_WINDOW)
            div_type, div_str = self.rsi_divergence(C[sl_:idx+1], RSI[sl_:idx+1])
            if direction == 'bull' and div_type == 'bull':
                conf_type, conf_val, rsi_div_type = 'RSI_DIV', div_str, div_type
            elif direction == 'bear' and div_type == 'bear':
                conf_type, conf_val, rsi_div_type = 'RSI_DIV', div_str, div_type

            # 3b: Son 60 dk'da aktif 5M FVG
            if conf_type is None:
                has5, q5 = fvg5_eng.has_recent_active(
                    fvg5_raw, mit5, t, window_secs=self.FVG5_WIN)
                if has5:
                    conf_type, conf_val, fvg5_q = 'FVG_5M', q5 / 100.0, q5

            # 3c: EMA100 + EMA200 onayı
            if conf_type is None:
                ema_ok, ema_d = self.ema_confirm(
                    cur_close, float(E100[idx]), float(E200[idx]), direction)
                if ema_ok:
                    conf_type    = 'EMA_CONFIRM'
                    conf_val     = min(1.0, ema_d / 0.5)
                    ema_dist     = ema_d

            if conf_type is None:
                continue

            # ── Güven Skoru (0-100) ───────────────────────────────────
            session_q  = 1.0 if 8 <= hour <= 12 else 0.7
            confidence = min(100.0,
                             30 * (touching_fvg.quality_score / 100.0) +
                             30 * best_msc.momentum_score +
                             30 * conf_val +
                             10 * session_q)

            if confidence > best_conf:
                best_conf   = confidence
                best_signal = TradeSignal(
                    entry_time        = cur_time,
                    direction         = direction,
                    trigger_fvg       = touching_fvg,
                    msc_signal        = best_msc,
                    confirmation_type = conf_type,
                    confidence        = confidence,
                    rsi_div_type      = rsi_div_type,
                    fvg5_quality      = fvg5_q,
                    ema_distance_pct  = ema_dist,
                )

        return best_signal


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 6: RİSK YÖNETİCİSİ
# ═══════════════════════════════════════════════════════════════════════════

class RiskManager:
    """
    Swing tabanlı SL, 1:2 RR TP ve sabit kesirli pozisyon büyüklüğü.
    """

    def __init__(self, risk_per_trade: float = 0.005, rr: float = 2.0,
                 sl_buffer: float = 0.0005):
        self.risk_per_trade = risk_per_trade
        self.rr             = rr
        self.sl_buffer      = sl_buffer
        self.min_risk       = 0.50
        self.max_risk       = 150.0
        self.max_risk_pct   = 2.0

    def compute(self, idx: int, direction: str,
                entry: float, H: np.ndarray, L: np.ndarray,
                ATR: np.ndarray,
                equity: float) -> Optional[Dict]:

        if direction == 'bull':
            swing, _ = IndicatorEngine.significant_swing_low(
                L, H, ATR, idx, lookback=50, min_strength=2, max_strength=5, min_atr_mult=0.3)
            sl   = swing * (1.0 - self.sl_buffer)
            risk = abs(entry - sl)
            tp   = entry + risk * self.rr
        else:
            swing, _ = IndicatorEngine.significant_swing_high(
                H, L, ATR, idx, lookback=50, min_strength=2, max_strength=5, min_atr_mult=0.3)
            sl   = swing * (1.0 + self.sl_buffer)
            risk = abs(sl - entry)
            tp   = entry - risk * self.rr

        if not (self.min_risk <= risk <= self.max_risk):
            return None
        if risk / entry * 100 > self.max_risk_pct:
            return None
        if direction == 'bull' and tp <= entry:
            return None
        if direction == 'bear' and tp >= entry:
            return None

        return {
            'sl'         : round(sl,   2),
            'tp'         : round(tp,   2),
            'risk'       : round(risk, 2),
            'risk_pct'   : round(risk / entry * 100, 4),
            'risk_dollar': round(equity * self.risk_per_trade, 2),
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
                 initial_capital: float = 10_000):
        self.brain   = brain
        self.risk    = risk_mgr
        self.capital = initial_capital

    def run(self, df_1h: pd.DataFrame, df_5m: pd.DataFrame,
            backtest_start: datetime) -> List[Trade]:

        print("  Göstergeler hesaplanıyor...")

        # 5M göstergeler
        df5 = df_5m.copy()
        df5['ema100'] = IndicatorEngine.ema(df5['Close'], 100)
        df5['ema200'] = IndicatorEngine.ema(df5['Close'], 200)
        df5['rsi']    = IndicatorEngine.rsi(df5['Close'], 14)
        df5['atr']    = IndicatorEngine.atr(df5, 14)
        df5           = IndicatorEngine.msc_signals(df5, lookback=10)

        df1 = df_1h.copy()
        df1['atr'] = IndicatorEngine.atr(df1, 14)

        # FVG motorları
        fvg1_eng = FVGEngine('1h', min_gap=2.0,  max_age_hours=48, buf_ratio=0.05)
        fvg5_eng = FVGEngine('5m', min_gap=0.50, max_age_hours=4,  buf_ratio=0.05)

        print("  1H FVG...", end=' ')
        fvg1_bull = fvg1_eng.detect(df1, 'bull', df1['atr'])
        fvg1_bear = fvg1_eng.detect(df1, 'bear', df1['atr'])
        mit1_bull = fvg1_eng.build_mitigation_map(df1, fvg1_bull)
        mit1_bear = fvg1_eng.build_mitigation_map(df1, fvg1_bear)
        print(f"Bull:{len(fvg1_bull)}  Bear:{len(fvg1_bear)}")

        print("  5M FVG...", end=' ')
        fvg5_bull = fvg5_eng.detect(df5, 'bull', df5['atr'])
        fvg5_bear = fvg5_eng.detect(df5, 'bear', df5['atr'])
        mit5_bull = fvg5_eng.build_mitigation_map(df5, fvg5_bull)
        mit5_bear = fvg5_eng.build_mitigation_map(df5, fvg5_bear)
        print(f"Bull:{len(fvg5_bull)}  Bear:{len(fvg5_bear)}")

        # Array'ler
        C    = df5['Close'].values.astype(float)
        O    = df5['Open'].values.astype(float)
        H    = df5['High'].values.astype(float)
        L    = df5['Low'].values.astype(float)
        ATR  = df5['atr'].values.astype(float)
        E100 = df5['ema100'].values.astype(float)
        E200 = df5['ema200'].values.astype(float)
        RSI  = df5['rsi'].values.astype(float)
        MB   = df5['msc_bull'].values
        MR   = df5['msc_bear'].values
        MB_M = df5['msc_bull_mom'].values.astype(float)
        MR_M = df5['msc_bear_mom'].values.astype(float)
        TM   = df5.index

        bs      = to_naive(backtest_start)
        bt_idx  = np.where(np.array([to_naive(t) >= bs for t in TM]))[0]

        print(f"\n  Sinyaller taranıyor... ({len(bt_idx)} mum | {bs.date()} sonrası)\n")

        dbg = dict(session=0, no_bias=0, no_signal=0, risk_fail=0, generated=0)

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
                hit_tp = (H[idx] >= active.tp) if d == 'bull' else (L[idx] <= active.tp)
                hit_sl = (L[idx] <= active.sl) if d == 'bull' else (H[idx] >= active.sl)
                if hit_sl and hit_tp:
                    hit_tp = False  # aynı mumda her ikisi → SL önce

                if hit_tp or hit_sl:
                    mult   = active.rr if hit_tp else -1.0
                    dollar = mult * active.risk_dollar
                    equity += dollar
                    active.exit_price    = active.tp if hit_tp else active.sl
                    active.exit_time     = TM[idx]
                    active.result        = 'WIN' if hit_tp else 'LOSS'
                    active.pnl_dollar    = round(dollar, 2)
                    active.equity_after  = round(equity, 2)
                    trades.append(active)
                    in_trade = False
                    active   = None
                continue

            # Sinyal değerlendirme
            signal = self.brain.evaluate(
                idx=idx,
                C=C, O=O, H=H, L=L,
                E100=E100, E200=E200, RSI=RSI,
                MSC_B=MB, MSC_R=MR, MSC_B_M=MB_M, MSC_R_M=MR_M,
                TM=TM,
                fvg1_bull=fvg1_bull, mit1_bull=mit1_bull,
                fvg1_bear=fvg1_bear, mit1_bear=mit1_bear,
                fvg5_bull=fvg5_bull, mit5_bull=mit5_bull,
                fvg5_bear=fvg5_bear, mit5_bear=mit5_bear,
                fvg1_eng=fvg1_eng, fvg5_eng=fvg5_eng,
            )

            if signal is None:
                reason = self.brain.last_skip_reason
                self.brain.last_skip_reason = None
                if reason == 'no_bias':
                    dbg['no_bias'] += 1
                elif not self.brain.in_session(to_naive(TM[idx]).hour):
                    dbg['session'] += 1
                else:
                    dbg['no_signal'] += 1
                continue

            # Risk hesapla
            entry = float(O[idx + 1])
            r = self.risk.compute(idx, signal.direction, entry, H, L, ATR, equity)
            if r is None:
                dbg['risk_fail'] += 1
                continue

            # İşlem oluştur
            trade_id += 1
            dbg['generated'] += 1
            active = Trade(
                trade_id    = trade_id,
                signal      = signal,
                entry_price = round(entry, 2),
                sl          = r['sl'],
                tp          = r['tp'],
                risk        = r['risk'],
                risk_pct    = r['risk_pct'],
                risk_dollar = r['risk_dollar'],
                rr          = self.risk.rr,
            )
            in_trade = True

        # Dönem sonu açık işlem
        if in_trade and active is not None:
            active.exit_price    = float(C[-1])
            active.exit_time     = TM[-1]
            active.result        = 'OPEN'
            active.equity_after  = round(equity, 2)
            trades.append(active)

        print(f"  FİLTRE ÖZETİ:")
        print(f"    Bias filtresi      : {dbg['no_bias']:>6}")
        print(f"    Seans dışı         : {dbg['session']:>6}")
        print(f"    Sinyal yok         : {dbg['no_signal']:>6}")
        print(f"    Risk filtresi      : {dbg['risk_fail']:>6}")
        print(f"    Üretilen sinyaller : {dbg['generated']:>6}")
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
        self.done    = [t for t in trades if t.result in ('WIN', 'LOSS')]

    def compute(self) -> Optional[Dict]:
        if not self.done:
            return None

        pnls = np.array([t.pnl_dollar for t in self.done])
        eq   = self.capital + np.cumsum(pnls)
        peak = np.maximum.accumulate(eq)
        dd   = (peak - eq) / (peak + 1e-10) * 100

        wins      = sum(1 for t in self.done if t.result == 'WIN')
        total     = len(self.done)
        wr        = wins / total
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
            'losses'        : total - wins,
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
        print("  XAUUSD  │  FVG Strategy Engine  │  v9.0  │  Performans")
        if entry_times:
            print(f"  Dönem : {min(entry_times).date()}  →  {max(entry_times).date()}")
        print(SEP)

        print(f"\n  ── GENEL ──────────────────────────────────────────────────")
        print(f"  Toplam İşlem        : {m['total']}")
        print(f"  Kazanç              : {m['wins']:3d}  (%{m['win_rate']*100:.1f})")
        print(f"  Kayıp               : {m['losses']:3d}  (%{(1-m['win_rate'])*100:.1f})")

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

            done = [t for t in trades if t.result in ('WIN', 'LOSS')]
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
                f'XAUUSD  │  FVG Engine v9.0  │  {dr}  '
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
                'confidence'      : round(s.confidence, 2),
                'fvg1_quality'    : round(s.trigger_fvg.quality_score, 2),
                'fvg1_gap_size'   : round(s.trigger_fvg.gap_size, 2),
                'fvg1_gap_atr'    : round(s.trigger_fvg.gap_atr_ratio, 4),
                'msc_momentum'    : round(s.msc_signal.momentum_score, 4),
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
    RISK_PER_TRADE  = 0.005   # %0.5

    # Veri
    df_1h, df_5m, bt_start = DataEngine.download(verbose=True)

    # Bileşenler
    bias_provider = WeeklyBiasProvider('weekly_bias.json')
    brain    = MarketBrain(bias_provider=bias_provider)
    risk_mgr = RiskManager(risk_per_trade=RISK_PER_TRADE, rr=2.0, sl_buffer=0.0005)
    engine   = BacktestEngine(brain, risk_mgr, initial_capital=INITIAL_CAPITAL)

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
