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
    harmonic          : Optional['HarmonicSignal'] = None
    rsi_div_type      : Optional[str] = None
    fvg5_quality      : float = 0.0
    ema_distance_pct  : float = 0.0
    fib_level         : float = 0.0   # FibRetestBrain: 0.618 retest giriş seviyesi
    tp_hint           : float = 0.0   # LondonReversalBrain: Asya range karşı taraf TP (TP2 = runner)
    tp1_hint          : float = 0.0   # LondonReversalBrain: Asya equilibrium %50 (TP1 = kısmi kâr)


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
    exit_price   : Optional[float] = None
    exit_time    : Optional[Any]   = None
    result       : str   = 'OPEN'
    pnl_dollar   : float = 0.0
    equity_after : float = 0.0
    entry_bar_idx: int   = -1        # zaman bazlı çıkış için giriş bar indeksi
    # ── Kısmi çıkış (opt-in; tp1 None → klasik tek-TP davranışı, regresyon yok) ──
    tp1          : Optional[float] = None   # kısmi TP seviyesi (equilibrium)
    tp1_fraction : float = 0.5              # tp1'de kapatılan pozisyon oranı
    tp1_done     : bool  = False            # tp1 vuruldu mu (BE'ye taşındı)
    realized_pnl : float = 0.0              # tp1'den realize edilen kâr ($)
    # ── Çıkış adli-analizi (teşhis; işlem mantığını ETKİLEMEZ) ───────────────
    mfe_r        : float = 0.0              # açıkken lehte en uç gidiş (R çarpanı)
    mae_r        : float = 0.0              # açıkken aleyhte en uç gidiş (R çarpanı)
    exit_reason  : str   = ''               # tp|sl|be|tp1+tp|tp1+be|time|open


@dataclass
class LiquidityTPConfig:
    """EqualLiquidityFinder için konfigürasyon — hardcoded değer kalmaz."""
    min_r         : float = 2.0   # TP minimum mesafe (R cinsinden)
    max_r         : float = 4.0   # TP maksimum mesafe
    eq_tol_atr    : float = 0.5   # eşit seviye toleransı = eq_tol_atr × ATR
    swing_strength: int   = 2     # pivot tespiti için minimum strength
    swing_lookback: int   = 80    # kaç bar geriye bakılır (1H barlarda)
    min_touches   : int   = 2     # "eşit" sayılabilmesi için min dokunuş
    fallback_fvg  : bool  = True  # FVG kenarını fallback olarak kullan


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


class DailyBiasProvider:
    """
    daily_bias.json dosyasından GÜNLÜK bias okur (anahtar: 'YYYY-MM-DD').
    WeeklyBiasProvider ile aynı sözleşme: get(dt) → 'bull'|'bear'|None.
    """

    def __init__(self, filepath: str = 'daily_bias.json'):
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
                and v.strip().lower() in ('bull', 'bear')
            }
            print(f"  Günlük bias yüklendi: {len(self._data)} aktif gün "
                  f"({self.filepath.name})")
        else:
            print(f"  UYARI: {self.filepath} bulunamadı — günlük bias devre dışı")

    def get(self, dt: Any) -> Optional[str]:
        """Gün D'nin bias'ı = en son TAMAMLANMIŞ günün gerçekleşen yönü
        (dünün momentumu). LOOKAHEAD KORUMASI: aynı günün yönünü döndürmek,
        günün kapanışını gün içinde önceden bilmek olurdu — tarihsel 'daily'
        sonuçlarını şişiren hata buydu."""
        t = to_naive(dt)
        for back in range(1, 5):          # hafta sonu/tatil boşlukları için geriye tara
            key = (t - timedelta(days=back)).strftime('%Y-%m-%d')
            if key in self._data:
                return self._data[key]
        return None

    @staticmethod
    def build_from_1h(df_1h: pd.DataFrame, filepath: str = 'daily_bias.json',
                      flat_pct: float = 0.25) -> Dict[str, str]:
        """
        1H verisinden her takvim gününün gerçekleşen yönünü (close vs open)
        üretir ve daily_bias.json'a yazar. |net%| < flat_pct → o gün bias yok.
        """
        df = df_1h.copy()
        df.index = pd.to_datetime(df.index)
        out: Dict[str, str] = {
            '_kaynak': (f'XAUUSD 1H verisinden günlük yön (close vs open). '
                        f'|net%|<{flat_pct} → bias yok.')
        }
        for day, g in df.groupby(df.index.normalize()):
            o = float(g['Open'].iloc[0]); c = float(g['Close'].iloc[-1])
            net = (c - o) / o * 100
            if abs(net) < flat_pct:
                continue
            key = pd.Timestamp(day).strftime('%Y-%m-%d')
            out[key] = 'bull' if c > o else 'bear'
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        return out


class PrivateBiasProvider:
    """
    GARCH-benzeri otomatik rejim tespiti (saf numpy, lookahead yok).

    Algoritma:
      1. 1H log returns → EWMA varyans σ²_t = λ·σ²_{t-1} + (1-λ)·r²_t  (λ=0.94)
      2. Genişleyen medyan σ²_median[t] → trending: σ²_t > σ²_median × VOL_MULT
         ranging piyasa → None döndür  ← bu zaten rejim filtresidir
      3. Trend yönü: EMA21 > EMA55 → 'bull'; EMA21 < EMA55 → 'bear'
      4. Her gün: London öncesi son 1H bar (hour < 7 UTC) değerlendirmesi

    Döndür: 'bull' | 'bear' | None
    """

    VOL_LAMBDA = 0.94    # EWMA decay (RiskMetrics standardı)
    VOL_MULT   = 1.20    # σ²_t > medyan × bu oran → trending
    EMA_FAST   = 21      # 1H EMA hızlı
    EMA_SLOW   = 55      # 1H EMA yavaş

    def __init__(self, df_1h: pd.DataFrame):
        self._data: Dict[str, Optional[str]] = {}
        self._build(df_1h)

    def _build(self, df_1h: pd.DataFrame) -> None:
        df = df_1h.copy()
        df.index = pd.to_datetime(df.index, utc=True)
        close = df['Close'].values.astype(float)
        n = len(close)
        if n < self.EMA_SLOW + 10:
            return

        # 1. Log returns (causal: r[i] = log(C[i]/C[i-1]))
        ret = np.empty(n)
        ret[0] = 0.0
        prev = np.where(close[:-1] > 0, close[:-1], 1e-10)
        ret[1:] = np.log(np.where(close[1:] > 0, close[1:], 1e-10) / prev)

        # 2. EWMA variance (lookahead yok: yalnızca geçmiş barlar)
        lam = self.VOL_LAMBDA
        ewma_var = np.empty(n)
        ewma_var[0] = ret[0] ** 2
        for i in range(1, n):
            ewma_var[i] = lam * ewma_var[i - 1] + (1.0 - lam) * ret[i] ** 2

        # 3. Genişleyen medyan (lookahead yok: her bar için yalnızca [0..i] kullanılır)
        var_series = pd.Series(ewma_var)
        var_median = var_series.expanding(min_periods=self.EMA_SLOW).median().values

        # 4. EMA21 / EMA55 (adjust=False → causal / geçmişe dayalı)
        close_s = pd.Series(close, index=df.index)
        ema_fast = close_s.ewm(span=self.EMA_FAST, adjust=False).mean().values
        ema_slow = close_s.ewm(span=self.EMA_SLOW, adjust=False).mean().values

        # 5. Her gün için London öncesi son bar (hour < 7 UTC)
        dt_naive = np.array([to_naive(ts) for ts in df.index])
        daily_last_idx: Dict[str, int] = {}
        for i in range(n):
            t = dt_naive[i]
            if t.hour < 7:
                key = t.strftime('%Y-%m-%d')
                daily_last_idx[key] = i   # aynı gün içinde en son pre-London bar

        # 6. Etiketleme
        for date_str, bi in daily_last_idx.items():
            med = var_median[bi]
            if np.isnan(med) or med <= 0:
                continue
            trending = ewma_var[bi] > med * self.VOL_MULT
            if not trending:
                continue   # ranging → None (rejim filtresi)
            ef = ema_fast[bi]
            es = ema_slow[bi]
            if np.isnan(ef) or np.isnan(es):
                continue
            if ef > es:
                self._data[date_str] = 'bull'
            elif ef < es:
                self._data[date_str] = 'bear'
            # ef == es → eşit → bias yok

    def get(self, dt) -> Optional[str]:
        key = to_naive(dt).strftime('%Y-%m-%d')
        return self._data.get(key)   # 'bull' | 'bear' | None


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
    def _pivots_low(a: np.ndarray, strength: int = 2,
                    atr: Optional[np.ndarray] = None,
                    min_atr_mult: float = 0.0) -> List[int]:
        """
        Fraktal dip indeksleri (lookahead-safe değil — kapalı pencere içinde çağrılır).
        atr verilirse ATR-anlamlılık filtresi uygulanır (mikro-gürültü pivotları
        elenir; SwingEngine.compute ile aynı derinlik kriteri).
        """
        idxs = []
        for j in range(strength, len(a) - strength):
            if (all(a[j] < a[j - k] for k in range(1, strength + 1)) and
                    all(a[j] <= a[j + k] for k in range(1, strength + 1))):
                if atr is not None and min_atr_mult > 0:
                    atr_j = max(float(atr[j]), 1e-6)
                    ld = float(np.min(a[j - strength:j]))        - float(a[j])
                    rd = float(np.min(a[j + 1:j + strength + 1])) - float(a[j])
                    if (ld + rd) / 2.0 < min_atr_mult * atr_j:
                        continue
                idxs.append(j)
        return idxs

    @staticmethod
    def _pivots_high(a: np.ndarray, strength: int = 2,
                     atr: Optional[np.ndarray] = None,
                     min_atr_mult: float = 0.0) -> List[int]:
        idxs = []
        for j in range(strength, len(a) - strength):
            if (all(a[j] > a[j - k] for k in range(1, strength + 1)) and
                    all(a[j] >= a[j + k] for k in range(1, strength + 1))):
                if atr is not None and min_atr_mult > 0:
                    atr_j = max(float(atr[j]), 1e-6)
                    ld = float(a[j]) - float(np.max(a[j - strength:j]))
                    rd = float(a[j]) - float(np.max(a[j + 1:j + strength + 1]))
                    if (ld + rd) / 2.0 < min_atr_mult * atr_j:
                        continue
                idxs.append(j)
        return idxs

    @staticmethod
    def divergence(prices: np.ndarray, rsi_vals: np.ndarray,
                   strength: int = 2, atr: Optional[np.ndarray] = None,
                   min_atr_mult: float = 0.5) -> Tuple[Optional[str], float]:
        """
        Son iki ANLAMLI close pivotu üzerinden regular diverjans. (tip, güç 0-1).
        Pivotlar ATR-anlamlılık filtresinden geçer (min_atr_mult); böylece
        mikro-fraktal gürültü yerine gerçek swing dip/tepeleri karşılaştırılır.
        Pencere zaten geçmiş veridir; çağıran taraf lookahead'i yönetir.
        """
        p = np.asarray(prices, dtype=float)
        r = np.asarray(rsi_vals, dtype=float)
        a = np.asarray(atr, dtype=float) if atr is not None else None
        if len(p) < 2 * strength + 3 or np.any(np.isnan(r)):
            return None, 0.0

        # BULL: anlamlı fiyat dipleri (close)
        lows = RSIEngine._pivots_low(p, strength, a, min_atr_mult)
        if len(lows) >= 2:
            i1, i2 = lows[-2], lows[-1]
            if p[i2] < p[i1] and r[i2] > r[i1]:
                price_drop = (p[i1] - p[i2]) / (abs(p[i1]) + 1e-10)
                rsi_lift   = (r[i2] - r[i1]) / 100.0
                strg = min(1.0, (price_drop * 30 + rsi_lift) )
                return 'bull', float(max(0.05, strg))

        # BEAR: anlamlı fiyat tepeleri (close)
        highs = RSIEngine._pivots_high(p, strength, a, min_atr_mult)
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


class MACDEngine:
    """MACD (12, 26, 9) hesabı."""

    @staticmethod
    def compute(series: pd.Series,
                fast: int = 12, slow: int = 26,
                signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        ema_fast    = series.ewm(span=fast,   adjust=False).mean()
        ema_slow    = series.ewm(span=slow,   adjust=False).mean()
        macd_line   = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        return macd_line, signal_line, macd_line - signal_line


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

            # Onaylı fraktal swing yoksa NaN bırak — rolling-20 ekstremi
            # "swing" saymak sahte BOS/MSB üretirdi (yatay/trend dinlenmesinde
            # son 20 mum zirvesi aşılır ama gerçek yapı kırılımı yoktur).
            # Tüm tüketiciler NaN-korumalı (MSB5MEngine/BreakerEngine/MSBEngine).
            last_sh[i] = cur_sh
            last_sl[i] = cur_sl

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

    # Breaker MSS şimdilik KAPALI (MSS kuralları araştırılıyor; mevcut temiz
    # swing-kırılımı %21 WR ile zararlı ve mitigation'ı eziyordu).
    ENABLE_BREAKER = False

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

        # Gerçek Mitigation Block için onaylı fraktal pivot dizisi (lookahead-safe)
        piv = self._confirmed_pivots(H, L, atr, n)
        pv  = 0                       # piv içine ilerleyen işaretçi
        seq: List[tuple] = []         # bilinen onaylı pivotlar (idx, price, kind)
        mblocks: List[dict] = []      # aktif mitigation blokları
        MIT_MAX_AGE = 80              # blok dönüş beklerken yaşam süresi (bar)

        events: List[MSBEvent] = []

        for i in range(2, n):
            atr_i = max(float(atr[i]), 1e-6)
            sh    = last_sh[i - 1]
            sl    = last_sl[i - 1]

            # ── Yeni onaylanan pivotları diziye ekle + failure-swing kurulumu ─
            while pv < len(piv) and piv[pv][0] <= i:
                _, p_idx, p_price, p_kind = piv[pv]
                seq.append((p_idx, p_price, p_kind))
                if len(seq) > 8:
                    del seq[0]
                # Mitigation block (failure-to-swing): süpürme YOK, sadece
                # higher-low (bull) / lower-high (bear) ile yapı tersine döner.
                # (Breaker artık ayrı: temiz MSS = swing kapanış kırılımı, aşağıda.)
                if p_kind == 'L' and len(seq) >= 3:
                    l1, h1, l2 = seq[-3], seq[-2], seq[-1]
                    if (l1[2] == 'L' and h1[2] == 'H' and l2[2] == 'L'
                            and l2[1] > l1[1]):                  # higher-low → failure swing
                        p2 = l2[0]
                        mblocks.append(dict(
                            dir='bull', kind='mitigation', rev=float(h1[1]),
                            b_hi=float(H[p2]), b_lo=float(L[p2]),
                            state='armed', formed=i, active=-1))
                elif p_kind == 'H' and len(seq) >= 3:
                    h1, l1, h2 = seq[-3], seq[-2], seq[-1]
                    if (h1[2] == 'H' and l1[2] == 'L' and h2[2] == 'H'
                            and h2[1] < h1[1]):                  # lower-high → failure swing
                        p2 = h2[0]
                        mblocks.append(dict(
                            dir='bear', kind='mitigation', rev=float(l1[1]),
                            b_hi=float(H[p2]), b_lo=float(L[p2]),
                            state='armed', formed=i, active=-1))
                pv += 1

            # ── BREAKER (CHoCH — yapı karakteri değişimi) ──────────────────
            # Görseldeki ICT breaker: DÜŞÜŞ yapısında (alçalan tepeler) son
            # LOWER-HIGH gövde-kapanışıyla kırılır → karakter değişimi (bull).
            # Tersi: YÜKSELİŞ yapısında son HIGHER-LOW kırılır → bear CHoCH.
            # Her BOS değil; yalnız trend-karşıtı İLK kırılım (gürültü filtresi).
            # Kırılım mumu enerjik (displacement) olmalı + swing'i anlamlı geçmeli.
            body_i = abs(C[i] - O[i]); rng_i = H[i] - L[i]
            br_i   = body_i / rng_i if rng_i > 0 else 0.0
            disp_i = (body_i > 1.2 * atr_i) or (br_i >= 0.6)
            pen    = 0.10 * atr_i                       # min penetrasyon eşiği
            highs = [p for p in seq if p[2] == 'H']
            lows  = [p for p in seq if p[2] == 'L']
            if self.ENABLE_BREAKER and disp_i and len(highs) >= 2:
                sh2 = highs[-1][1]; sh1 = highs[-2][1]      # sh2 = en yeni tepe
                if (sh2 < sh1 and C[i] > sh2 + pen and C[i - 1] <= sh2):
                    stop, _ = SwingEngine.best_swing_low(
                        L, H, atr, i, lookback=50, min_strength=2,
                        max_strength=5, min_atr_mult=0.3)
                    if not np.isnan(stop) and float(stop) < C[i]:
                        events.append(MSBEvent(
                            msb_type='breaker', direction='bull', confirm_idx=i,
                            detect_time=T[i], stop_price=float(stop),
                            swing_level=float(sh2),
                            quality=min(1.0, (C[i] - sh2) / atr_i)))
            if self.ENABLE_BREAKER and disp_i and len(lows) >= 2:
                sl2 = lows[-1][1]; sl1 = lows[-2][1]        # sl2 = en yeni dip
                if (sl2 > sl1 and C[i] < sl2 - pen and C[i - 1] >= sl2):
                    stop, _ = SwingEngine.best_swing_high(
                        H, L, atr, i, lookback=50, min_strength=2,
                        max_strength=5, min_atr_mult=0.3)
                    if not np.isnan(stop) and float(stop) > C[i]:
                        events.append(MSBEvent(
                            msb_type='breaker', direction='bear', confirm_idx=i,
                            detect_time=T[i], stop_price=float(stop),
                            swing_level=float(sl2),
                            quality=min(1.0, (sl2 - C[i]) / atr_i)))

            # ── (a) BREAKER / MITIGATION BLOCK — birleşik A-B-C tespiti ────
            # Naive BOS kaldırıldı. Breaker ve mitigation aynı A-B-C yapısının
            # iki türü; tek fark ara swing önceki swing'i SÜPÜRÜYOR mu:
            #   breaker    → süpürme VAR (likidite avı), sonra dönüş
            #   mitigation → süpürme YOK (failure swing), sonra dönüş
            # Kurulum (b)'de yapılır; tetikleme bloğa geri dönüşte (c) gelir.

            # ── (b) MITIGATION/BREAKER BLOCK — yapı tersine + bloğa dönüş ───
            # Gerçek mitigation block: failure-to-swing (yüksek-dip/düşük-tepe)
            # ile yapı tersine kırılır; fiyat blok bölgesine GERİ döner ki
            # terste kalan akıllı para başabaşta kurtulsun → o dönüşte işlem.
            #   armed   → yapı henüz tersine kırılmadı (rev seviyesi beklenir)
            #   active  → tersine kırıldı; bloğa geri dönüş (reclaim) beklenir
            kept: List[dict] = []
            for b in mblocks:
                if i - b['formed'] > MIT_MAX_AGE:
                    continue                                    # süresi doldu
                if b['dir'] == 'bull':
                    if C[i] < b['b_lo']:
                        continue                                # failure-low kırıldı → iptal
                    if b['state'] == 'armed':
                        if C[i] > b['rev'] and C[i - 1] <= b['rev']:
                            b['state'] = 'active'; b['active'] = i  # yapı tersine (BOS yukarı)
                        kept.append(b)
                    elif i > b['active'] and L[i] <= b['b_hi'] and C[i] > b['b_hi']:
                        stop, _ = SwingEngine.best_swing_low(
                            L, H, atr, i, lookback=50, min_strength=2,
                            max_strength=5, min_atr_mult=0.3)
                        stop = min(float(stop), b['b_lo'])        # blok-low altı
                        events.append(MSBEvent(
                            msb_type=b['kind'], direction='bull', confirm_idx=i,
                            detect_time=T[i], stop_price=float(stop),
                            swing_level=float(b['b_hi']),
                            quality=min(1.0, (C[i] - b['b_hi']) / atr_i)))
                    else:
                        kept.append(b)                          # dönüş bekleniyor
                else:  # bear
                    if C[i] > b['b_hi']:
                        continue                                # failure-high kırıldı → iptal
                    if b['state'] == 'armed':
                        if C[i] < b['rev'] and C[i - 1] >= b['rev']:
                            b['state'] = 'active'; b['active'] = i  # yapı tersine (BOS aşağı)
                        kept.append(b)
                    elif i > b['active'] and H[i] >= b['b_lo'] and C[i] < b['b_lo']:
                        stop, _ = SwingEngine.best_swing_high(
                            H, L, atr, i, lookback=50, min_strength=2,
                            max_strength=5, min_atr_mult=0.3)
                        stop = max(float(stop), b['b_hi'])        # blok-high üstü
                        events.append(MSBEvent(
                            msb_type=b['kind'], direction='bear', confirm_idx=i,
                            detect_time=T[i], stop_price=float(stop),
                            swing_level=float(b['b_lo']),
                            quality=min(1.0, (b['b_lo'] - C[i]) / atr_i)))
                    else:
                        kept.append(b)
            mblocks = kept

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

    def _confirmed_pivots(self, H: np.ndarray, L: np.ndarray,
                          atr: np.ndarray, n: int) -> List[tuple]:
        """
        Lookahead-safe onaylı fraktal pivotlar (SwingEngine ile aynı kural).
        Pivot j, j+strength barında onaylanır. Dönüş: [(cbar, idx, price, kind)]
        cbar artan sırada; kind 'H'|'L'. Mitigation failure-swing için kullanılır.
        """
        s = self.strength; mam = self.min_atr_mult
        piv: List[tuple] = []
        for i in range(n):
            j = i - s
            if j < s:
                continue
            atr_j = max(float(atr[j]), 1e-6)
            if (all(H[j] > H[j - k] for k in range(1, s + 1)) and
                    all(H[j] > H[j + k] for k in range(1, s + 1))):
                ld = float(H[j]) - float(np.max(H[j - s:j]))
                rd = float(H[j]) - float(np.max(H[j + 1:j + s + 1]))
                if (ld + rd) / 2 >= mam * atr_j:
                    piv.append((i, j, float(H[j]), 'H'))
            if (all(L[j] < L[j - k] for k in range(1, s + 1)) and
                    all(L[j] < L[j + k] for k in range(1, s + 1))):
                ld = float(np.min(L[j - s:j])) - float(L[j])
                rd = float(np.min(L[j + 1:j + s + 1])) - float(L[j])
                if (ld + rd) / 2 >= mam * atr_j:
                    piv.append((i, j, float(L[j]), 'L'))
        return piv

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
        # AltBat & Butterfly kaldırıldı (backtest: %0 WR, net zarar kaynağı).
        STD = [
            ('Gartley',   0.550, 0.680, 0.750, 0.820, (1.618, 1.414, 1.272, 1.272, 1.272), True),
            ('Bat',       0.320, 0.560, 0.850, 0.920, (2.618, 2.000, 1.618, 1.618, 1.618), True),
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

    RSI_WINDOW         = 50   # mum sayısı (5M) — anlamlı swing pivotları için
                              # iki ATR-anlamlı close pivotu sığsın (eski 30 dardı)
    TOUCH_MAX_AGE_BARS = 24   # dokunuştan sonra MSB için bekleme penceresi (24×5dk=2sa)
                              # HTF FVG içi LTF akümülasyonu (XAUUSD) için 100dk dardı.

    def __init__(self, bias_provider: Optional['WeeklyBiasProvider'] = None,
                 poi_mode: str = 'all'):
        self.bias = bias_provider
        # poi_mode: 'all' | 'fvg' | 'ob' | 'prz'
        # 'all' → mevcut davranış (tüm POI kaynakları)
        self.poi_mode = poi_mode
        self.last_skip_reason: Optional[str] = None
        # Adım-bazlı teşhis: sinyalin hangi adımda öldüğünü sayar
        self.stats = dict(step1_fail=0, step2_fail=0, step3_fail=0)
        # KULLANIM KURALI: her 1H FVG yalnızca bir kez işlem açabilir
        self.used_fvg_ids: set = set()
        # STATEFUL: dokunmuş ama henüz MSB ile tetiklenmemiş 1H FVG'ler (yön bazlı)
        #   {fvg_id, fvg, touch_idx, touch_time}
        self.pending: Dict[str, List[dict]] = {'bull': [], 'bear': []}

    # ── RSI Diverjansı (RSIEngine'e delege) ──────────────────────────────
    def rsi_divergence(self, prices: np.ndarray, rsi_vals: np.ndarray,
                       atr_vals: Optional[np.ndarray] = None
                       ) -> Tuple[Optional[str], float]:
        """Anlamlı (ATR-filtreli) close pivotları üzerinden regular diverjans."""
        return RSIEngine.divergence(prices, rsi_vals, strength=2,
                                    atr=atr_vals, min_atr_mult=0.5)

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
                 prz_harm: Optional[Dict] = None,
                 ATR: Optional[np.ndarray] = None,
                 # 1H Order Block POIs
                 ob1_bull: Optional[List[FVG]] = None,
                 ob1_bear: Optional[List[FVG]] = None,
                 mit_ob_bull: Optional[Dict] = None,
                 mit_ob_bear: Optional[Dict] = None,
                 poi1h_eng: Optional['FVGEngine'] = None,
                 ) -> Optional[TradeSignal]:

        # last_skip_reason her çağrıda sıfırlanır (stale değer bug fix)
        self.last_skip_reason = None
        przfvg_bull  = przfvg_bull or [];  przfvg_bear  = przfvg_bear or []
        mit_prz      = mit_prz or {};      prz_harm     = prz_harm or {}
        ob1_bull     = ob1_bull or [];     ob1_bear     = ob1_bear or []
        mit_ob_bull  = mit_ob_bull or {};  mit_ob_bear  = mit_ob_bear or {}

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
            ob1_raw    = ob1_bull if direction == 'bull' else ob1_bear
            mit_ob     = mit_ob_bull if direction == 'bull' else mit_ob_bear

            # ── ADIM 1: WICK dokunuşu — çoklu POI kaynağı ─────────────────
            #   poi_mode filtresi: 'all'→hepsi, 'fvg'/'ob'/'prz'→yalnız o
            pm = self.poi_mode
            sources: List[tuple] = []
            if pm in ('all', 'fvg'):
                sources.append(('fvg', fvg1_raw, mit1, fvg1_eng))
            if pm in ('all', 'prz') and prz_eng is not None and przfvg_raw:
                sources.append(('prz', przfvg_raw, mit_prz, prz_eng))
            if poi1h_eng is not None and ob1_raw and pm in ('all', 'ob'):
                sources.append(('ob', ob1_raw, mit_ob, poi1h_eng))

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
            mit_by_kind = {'fvg': mit1, 'prz': mit_prz,
                           'ob': mit_ob}
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
            atr_win = ATR[sl_:idx + 1] if ATR is not None else None
            div_type, div_str = self.rsi_divergence(
                C[sl_:idx + 1], RSI[sl_:idx + 1], atr_win)
            rsi_ok = (div_type == direction)
            # EMA100 ve EMA200 ikisi de KESİN ŞART — TÜM işlem türleri için
            # (FVG/PRZ/OB/BB/HS hepsi bu tek kapıdan geçer): bull → fiyat her
            # iki EMA üstünde, bear → her ikisinin altında. RSI yalnız ek
            # konfluens (risk boyutunu 0.5R↔1R etkiler), giriş şartı değil.
            bias_main = bias_allows and ema_ok

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
            tk = trigger['kind']
            if   tk == 'prz': src.append('PRZ')
            elif tk == 'ob':  src.append('OB')
            conf_label = '+'.join(src)

            harmonic_ref = (prz_harm.get(trigger['fvg_id'])
                            if tk == 'prz' else None)

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
                risk_fraction: float,
                tp_override: Optional[float] = None) -> Optional[Dict]:

        if direction == 'bull':
            sl   = stop_price * (1.0 - self.sl_buffer)
            risk = abs(entry - sl)
            tp   = tp_override if tp_override is not None else entry + risk * self.rr
        else:
            sl   = stop_price * (1.0 + self.sl_buffer)
            risk = abs(sl - entry)
            tp   = tp_override if tp_override is not None else entry - risk * self.rr

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
# BÖLÜM 6b: 1H ORDER BLOCK POI TESPİTİ
# ═══════════════════════════════════════════════════════════════════════════

def _pivots_1h(
    H: np.ndarray, L: np.ndarray, atr: np.ndarray,
    n: int, strength: int = 3, min_atr_mult: float = 0.3,
) -> List[tuple]:
    """Lookahead-safe 1H fraktal pivotlar. Dönüş: [(cbar, j, price, 'H'|'L')]
    cbar = onay barı (j+strength), j = gerçek pivot barı. ATR filtreli."""
    piv: List[tuple] = []
    for i in range(n):
        j = i - strength
        if j < strength:
            continue
        atr_j = max(float(atr[j]), 1e-6)
        if (all(H[j] > H[j - k] for k in range(1, strength + 1)) and
                all(H[j] > H[j + k] for k in range(1, strength + 1))):
            ld = float(H[j]) - float(np.max(H[j - strength:j]))
            rd = float(H[j]) - float(np.max(H[j + 1:j + strength + 1]))
            if (ld + rd) / 2 >= min_atr_mult * atr_j:
                piv.append((i, j, float(H[j]), 'H'))
        if (all(L[j] < L[j - k] for k in range(1, strength + 1)) and
                all(L[j] < L[j + k] for k in range(1, strength + 1))):
            ld = float(np.min(L[j - strength:j])) - float(L[j])
            rd = float(np.min(L[j + 1:j + strength + 1])) - float(L[j])
            if (ld + rd) / 2 >= min_atr_mult * atr_j:
                piv.append((i, j, float(L[j]), 'L'))
    return piv


def _last_confirmed_swings(
    H: np.ndarray, L: np.ndarray, atr: np.ndarray, n: int, strength: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Her bar c için o ana kadar ONAYLI (lookahead-safe) son swing high/low
    fiyatı ve bar indeksi. piv = _pivots_1h (cbar=onay barı, j=gerçek pivot)."""
    piv = _pivots_1h(H, L, atr, n, strength)
    sh_price = np.full(n, np.nan); sh_bar = np.full(n, -1, dtype=int)
    sl_price = np.full(n, np.nan); sl_bar = np.full(n, -1, dtype=int)
    cur_shp = np.nan; cur_shb = -1; cur_slp = np.nan; cur_slb = -1
    pi = 0
    for c in range(n):
        while pi < len(piv) and piv[pi][0] <= c:   # cbar <= c → onaylandı
            _, jb, pr, kd = piv[pi]
            if kd == 'H':
                cur_shp = pr; cur_shb = jb
            else:
                cur_slp = pr; cur_slb = jb
            pi += 1
        sh_price[c] = cur_shp; sh_bar[c] = cur_shb
        sl_price[c] = cur_slp; sl_bar[c] = cur_slb
    return sh_price, sh_bar, sl_price, sl_bar


def detect_order_blocks_1h(
    H: np.ndarray, L: np.ndarray, O: np.ndarray, C: np.ndarray,
    T: Any, atr: np.ndarray, direction: str,
    strength: int = 3, k_atr: float = 1.2, body_ratio_min: float = 0.60,
    max_ob_to_bos: int = 6, require_fvg: bool = True,
) -> List[FVG]:
    """
    Gerçek ICT/SMC Order Block tespiti (lookahead-safe).

    Geçerli OB için ZORUNLU şartlar (her renk-değişimi OB DEĞİL):
      1. BOS/MSS: impuls, önceki onaylı swing high/low'u GÖVDE-KAPANIŞIYLA kırar.
      2. Displacement: impuls bacağında en az bir mum body > k_atr*ATR
         VEYA body/range >= body_ratio_min (enerjik hareket).
      3. FVG: impuls bacağı 3-mum Fair Value Gap bırakır (require_fvg=True → şart).
      4. Yakınlık (immediacy): OB ile BOS arası <= max_ob_to_bos mum.
      5. OB mumu = impuls başlangıcından önceki son ters-renk mum
         (bull → son bearish; bear → son bullish), kümede en uç low/high'lı.
    Zone = [L[ob], H[ob]] (tam mum aralığı).
    detect_time = BOS mumu kapanışı (T[bos] + 1h) — lookahead engeli.
    Kalite: displacement gücü + FVG + premium/discount + likidite süpürme.
    """
    n = len(H)
    detect_offset = pd.Timedelta(hours=1)
    sh_price, sh_bar, sl_price, sl_bar = _last_confirmed_swings(
        H, L, atr, n, strength)
    fvgs: List[FVG] = []
    seen_ob: set = set()

    for c in range(1, n):
        # ── 1. BOS: gövde-kapanışı son onaylı swing'i kırar (taze kırılım) ─
        if direction == 'bull':
            lvl = sh_price[c]; lvl_bar = sh_bar[c]
            if np.isnan(lvl) or lvl_bar < 0:
                continue
            if not (C[c] > lvl and C[c - 1] <= lvl):
                continue
        else:
            lvl = sl_price[c]; lvl_bar = sl_bar[c]
            if np.isnan(lvl) or lvl_bar < 0:
                continue
            if not (C[c] < lvl and C[c - 1] >= lvl):
                continue

        # ── 5. OB mumu: impuls öncesi son ters-renk mum (yakınlık penceresi) ─
        lo_k = max(c - max_ob_to_bos, 1)
        ob_bar = None
        for k in range(c - 1, lo_k - 1, -1):
            is_bear = O[k] > C[k]
            is_bull = C[k] > O[k]
            if direction == 'bull' and is_bear:
                ob_bar = k; break
            if direction == 'bear' and is_bull:
                ob_bar = k; break
        if ob_bar is None or ob_bar in seen_ob:
            continue

        # ── 2. Displacement: impuls bacağında (ob_bar+1..c) enerjik mum ────
        disp = False; disp_str = 0.0
        for m in range(ob_bar + 1, c + 1):
            body = abs(C[m] - O[m]); rng = H[m] - L[m]
            atr_m = max(float(atr[m]), 1e-6)
            br = body / rng if rng > 0 else 0.0
            if body > k_atr * atr_m or br >= body_ratio_min:
                disp = True
                disp_str = max(disp_str, min(1.0, body / atr_m / 2.0))
        if not disp:
            continue

        # ── 3. FVG: impuls bacağında 3-mum boşluğu ────────────────────────
        has_fvg = False
        for m in range(ob_bar + 1, c):
            if m - 1 < 0 or m + 1 >= n:
                continue
            if direction == 'bull' and L[m + 1] > H[m - 1]:
                has_fvg = True; break
            if direction == 'bear' and H[m + 1] < L[m - 1]:
                has_fvg = True; break
        if require_fvg and not has_fvg:
            continue

        seen_ob.add(ob_bar)

        h_, l_ = float(H[ob_bar]), float(L[ob_bar])
        o_, c_ = float(O[ob_bar]), float(C[ob_bar])
        span = h_ - l_
        if span < 0.5:
            continue
        atr_j = max(float(atr[ob_bar]), 1e-6)

        # ── 7. Premium/discount: dealing range (swing low↔high) içindeki yer ─
        pd_bonus = 0.0
        if direction == 'bull' and sl_bar[c] >= 0 and not np.isnan(sl_price[c]):
            rng_lo = sl_price[c]; rng_hi = lvl
            if rng_hi > rng_lo:
                pos = ((h_ + l_) / 2 - rng_lo) / (rng_hi - rng_lo)
                pd_bonus = 1.0 if pos <= 0.5 else 0.0      # discount'ta → bonus
        elif direction == 'bear' and sh_bar[c] >= 0 and not np.isnan(sh_price[c]):
            rng_hi = sh_price[c]; rng_lo = lvl
            if rng_hi > rng_lo:
                pos = ((h_ + l_) / 2 - rng_lo) / (rng_hi - rng_lo)
                pd_bonus = 1.0 if pos >= 0.5 else 0.0      # premium'da → bonus

        # ── 8. Kalite skoru ────────────────────────────────────────────────
        quality = min(100.0,
                      30.0 * disp_str +
                      25.0 * (1.0 if has_fvg else 0.0) +
                      15.0 * pd_bonus +
                      20.0 * min(1.0, span / atr_j) +
                      10.0 * abs(c_ - o_) / (span + 1e-10))

        fvgs.append(FVG(
            fvg_id=_next_fvg_id(), timeframe='1h_ob', direction=direction,
            index=T[ob_bar],
            detect_time=T[c] + detect_offset,
            top=h_, bottom=l_, mid=(h_ + l_) / 2,
            gap_size=span, gap_atr_ratio=span / atr_j,
            momentum=abs(c_ - o_) / (span + 1e-10),
            quality_score=quality, created_i=ob_bar,
        ))
    return fvgs


def _build_poi_mit_map(
    poi_list: List[FVG], C: np.ndarray, T: Any,
    detect_offset: pd.Timedelta = pd.Timedelta(hours=1),
) -> Dict[int, Optional[Any]]:
    """
    POI geçersizleşme zamanı haritası (lookahead-safe).
    Bull POI: close < b_lo  → zone'un altına kapandı → tüketildi.
    Bear POI: close > b_hi  → zone'un üstüne kapandı → tüketildi.
    Zaman = ihlal barı kapanışı (T[i] + detect_offset).
    """
    n = len(C)
    mit_map: Dict[int, Optional[Any]] = {}
    for poi in poi_list:
        poi_detect = to_naive(poi.detect_time)
        start_i = next((i for i in range(n) if to_naive(T[i]) >= poi_detect), None)
        if start_i is None:
            mit_map[poi.fvg_id] = None
            continue
        mit_map[poi.fvg_id] = None
        for i in range(start_i, n):
            ci = float(C[i])
            if poi.direction == 'bull' and ci < poi.bottom:
                mit_map[poi.fvg_id] = to_naive(T[i]) + detect_offset
                break
            elif poi.direction == 'bear' and ci > poi.top:
                mit_map[poi.fvg_id] = to_naive(T[i]) + detect_offset
                break
    return mit_map


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
                 breakeven_at_R: Optional[float] = None,
                 time_exit_bars: Optional[int] = None,
                 ema_macd_filter: bool = False,
                 partial_tp_r: Optional[float] = None,
                 partial_tp_fraction: float = 0.5,
                 blackout_hours: Optional[list] = None,
                 sl_tighten: Optional[float] = None,
                 cost_spread_usd: float = 0.0,
                 cost_slippage_usd: float = 0.0,
                 cost_commission_pct: float = 0.0):
        self.brain   = brain
        self.risk    = risk_mgr
        self.capital = initial_capital
        self.breakeven_at_R = breakeven_at_R
        # partial_tp_r: +X R'de pozisyonun partial_tp_fraction kadarını kapat,
        # kalan SL'i breakeven'a taşı (mevcut tp1 altyapısı; None = kapalı).
        # Gerekçe (çıkış adli-analizi): kaybedenlerin önemli bölümü stop
        # olmadan önce ≥1R kâr görüyor — kilitlenmeyen kâr geri veriliyor.
        self.partial_tp_r        = partial_tp_r
        self.partial_tp_fraction = partial_tp_fraction
        # blackout_hours: bu UTC saatlerinde GİRİŞ yapılmaz (sinyal atlanır).
        self.blackout_hours = set(blackout_hours or [])
        # sl_tighten: yapısal stop mesafesi × bu katsayı (örn. 0.75 → %25 dar
        # stop); TP FİYATI orijinal yapısal hedefte kalır (RR doğal yükselir).
        # None/1.0 = kapalı.
        self.sl_tighten = sl_tighten
        # ── Maliyet modeli (gidiş-dönüş): pozisyon büyüklüğü üzerinden ──────
        #   qty_oz = risk_dollar / risk;  maliyet = qty×(spread + 2×slippage)
        #   + commission_pct/100 × qty × (giriş+çıkış fiyatı). 0 = kapalı.
        self.cost_spread_usd     = cost_spread_usd
        self.cost_slippage_usd   = cost_slippage_usd
        self.cost_commission_pct = cost_commission_pct
        # time_exit_bars: N 5M bar sonra ne TP ne SL olduysa marketten kapat.
        # None → kapalı. Örn 48 → 48×5dk = 4 saat.
        self.time_exit_bars   = time_exit_bars
        # ema_macd_filter: True ise sinyal sonrası 1H EMA9/21 + MACD kontrolü.
        self.ema_macd_filter  = ema_macd_filter
        # Alt sınıflar brain.evaluate() çağrısına ek kwargs iletmek için kullanır.
        self._extra_brain_kwargs: dict = {}

    def _trade_cost(self, t: 'Trade') -> float:
        """Gidiş-dönüş işlem maliyeti ($). Kısmi çıkışlar dahil tam pozisyon
        üzerinden bir kez uygulanır (muhafazakâr yaklaşım)."""
        if not (self.cost_spread_usd or self.cost_slippage_usd
                or self.cost_commission_pct):
            return 0.0
        qty = t.risk_dollar / max(t.risk, 1e-9)      # etkin oz büyüklüğü
        ep  = t.exit_price if t.exit_price is not None else t.entry_price
        return (qty * (self.cost_spread_usd + 2.0 * self.cost_slippage_usd)
                + self.cost_commission_pct / 100.0 * qty * (t.entry_price + ep))

    def _make_entry_trade(self, signal: TradeSignal, idx: int,
                          O: np.ndarray, equity: float, trade_id: int,
                          fvg1_bull=None, fvg1_bear=None,
                          mit1_bull=None, mit1_bear=None,
                          fvg1_eng=None,
                          H1=None, L1=None, ATR1=None,
                          T1: Optional[np.ndarray] = None) -> Optional[Trade]:
        """
        Entry trade nesnesi oluşturur.
        Alt sınıflar bunu override ederek dinamik TP vs. uygulayabilir.
        H1/L1/ATR1/T1: EqualLiquidityFinder kullanan alt sınıflar için geçirilir.
        T1: float timestamp array (np.array([t.timestamp() for t in df1.index])).
        """
        entry = float(O[idx + 1])
        stop_price  = signal.stop_price
        tp_override = None
        rr_eff      = self.risk.rr
        # SL sıkılaştırma (opt-in): stop mesafesi × faktör; TP FİYATI orijinal
        # yapısal hedefte kalır → RR doğal olarak yükselir (rr/f).
        if self.sl_tighten and 0.0 < self.sl_tighten < 1.0:
            dist = abs(entry - stop_price)
            sgn  = 1 if signal.direction == 'bull' else -1
            stop_price  = entry - sgn * dist * self.sl_tighten
            tp_override = entry + sgn * self.risk.rr * dist
            rr_eff      = self.risk.rr / self.sl_tighten
        r = self.risk.compute(signal.direction, entry,
                              stop_price, equity, signal.risk_fraction,
                              tp_override=tp_override)
        if r is None:
            return None
        # Genel kısmi-TP (opt-in): +partial_tp_r R'de kısmi kâr + SL→BE
        tp1 = None
        if self.partial_tp_r is not None and self.partial_tp_r > 0:
            tp1 = round(entry + self.partial_tp_r * r['risk']
                        * (1 if signal.direction == 'bull' else -1), 2)
        return Trade(
            trade_id      = trade_id,
            signal        = signal,
            entry_price   = round(entry, 2),
            sl            = r['sl'],
            tp            = r['tp'],
            risk          = r['risk'],
            risk_pct      = r['risk_pct'],
            risk_dollar   = r['risk_dollar'],
            rr            = rr_eff,
            risk_fraction = r['risk_fraction'],
            entry_bar_idx = idx,
            tp1           = tp1,
            tp1_fraction  = self.partial_tp_fraction,
        )

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
        df1 = EMAEngine.add(df1, 9, 21)
        _ml, _ms, _ = MACDEngine.compute(df1['Close'])
        df1['macd_line']   = _ml
        df1['macd_signal'] = _ms

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

        # Harmonik motor — yalnız 5M (15M/1H/4H düşük WR nedeniyle kapatıldı)
        print("  Harmonik...", end=' ')
        harm_eng = HarmonicEngine(swing=5, min_conf=40.0, max_prz_pct=4.0)
        harmonics: List[HarmonicSignal] = []
        try:
            harmonics += harm_eng.detect(df5, '5m')
        except Exception as e:
            print(f"(harmonik hata: {e})", end=' ')
        harm_bull = [s for s in harmonics if s.direction == 'bull']
        harm_bear = [s for s in harmonics if s.direction == 'bear']
        print(f"Bull:{len(harm_bull)}  Bear:{len(harm_bear)}  (5m:{len(harmonics)})")

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

        # 1H OB POI
        print("  1H POI (OB)...", end=' ')
        H1   = df1['High'].values.astype(float)
        L1   = df1['Low'].values.astype(float)
        O1   = df1['Open'].values.astype(float)
        C1   = df1['Close'].values.astype(float)
        T1   = df1.index
        atr1 = df1['atr'].values.astype(float)
        t1_ts = np.array([to_naive(t).timestamp() for t in T1])
        EMA9_1h   = df1['ema9'].values.astype(float)
        EMA21_1h  = df1['ema21'].values.astype(float)
        MACD_L_1h = df1['macd_line'].values.astype(float)
        MACD_S_1h = df1['macd_signal'].values.astype(float)
        C1_arr    = df1['Close'].values.astype(float)

        ob_bull = detect_order_blocks_1h(H1, L1, O1, C1, T1, atr1, 'bull')
        ob_bear = detect_order_blocks_1h(H1, L1, O1, C1, T1, atr1, 'bear')

        poi1h_eng  = FVGEngine('1h_ob', max_age_hours=72, buf_ratio=0.02)
        _off1h     = pd.Timedelta(hours=1)
        mit_ob_bull = _build_poi_mit_map(ob_bull, C1, T1, _off1h)
        mit_ob_bear = _build_poi_mit_map(ob_bear, C1, T1, _off1h)
        print(f"OB {len(ob_bull)}b/{len(ob_bear)}s")

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

        trades: List[Trade] = []
        trade_id             = 0
        active_fvg: Optional[Trade] = None   # FVG/ana slot (PRZ olmayan)
        active_prz: Optional[Trade] = None   # Harmonik PRZ slot
        equity               = float(self.capital)

        # ── Tek işlem çıkış mantığı (iki slot için ortak) ────────────────
        def _process_exit(t: Trade) -> Tuple[bool, float]:
            """(çıktı_mı, equity_delta). t alanları güncellenir (in-place).

            Kısmi TP1 (opt-in): t.tp1 set ise, TP1 vurulduğunda pozisyonun
            t.tp1_fraction kadarı kapanır, kalan SL breakeven'a taşınır ve işlem
            AÇIK kalır. tp1=None → klasik tek-TP davranışı (regresyon yok).
            Sonuç sınıfı toplam PnL'e göre belirlenir (kısmi + kalan)."""
            d      = t.signal.direction
            R      = t.risk
            entry  = t.entry_price
            partial = 0.0

            # ── Kısmi TP1 — tek TP/SL kontrolünden ÖNCE ──────────────────
            if t.tp1 is not None and not t.tp1_done:
                hit_tp1 = (H[idx] >= t.tp1) if d == 'bull' else (L[idx] <= t.tp1)
                hit_sl0 = (L[idx] <= t.sl)  if d == 'bull' else (H[idx] >= t.sl)
                if hit_tp1 and not hit_sl0:   # aynı barda SL varsa muhafazakar: TP1 atla
                    mult1   = ((t.tp1 - entry) if d == 'bull'
                               else (entry - t.tp1)) / (R + 1e-10)
                    partial = mult1 * t.risk_dollar * t.tp1_fraction
                    t.realized_pnl += partial
                    t.tp1_done = True
                    t.sl = round(entry, 2)    # kalan pozisyon → breakeven

            rem_frac = (1.0 - t.tp1_fraction) if t.tp1_done else 1.0

            hit_tp = (H[idx] >= t.tp) if d == 'bull' else (L[idx] <= t.tp)
            hit_sl = (L[idx] <= t.sl) if d == 'bull' else (H[idx] >= t.sl)
            if hit_sl and hit_tp:
                hit_tp = False
            if hit_tp or hit_sl:
                ep   = t.tp if hit_tp else t.sl
                mult = ((ep - entry) if d == 'bull' else (entry - ep)) / (R + 1e-10)
                dlr  = mult * t.risk_dollar * rem_frac
                t.exit_price = ep
                dlr -= self._trade_cost(t)          # gidiş-dönüş maliyeti
                total = t.realized_pnl + dlr
                t.exit_time = TM[idx]
                t.result     = ('WIN' if total > 0.01 else
                                ('BE' if abs(total) <= 0.01 else 'LOSS'))
                t.pnl_dollar = round(total, 2)
                t.exit_reason = ('tp' if hit_tp else
                                 ('be' if abs(ep - entry) < 0.011 else 'sl'))
                if t.tp1_done:
                    t.exit_reason = 'tp1+' + t.exit_reason
                return True, partial + dlr
            if self.breakeven_at_R is not None and t.sl != entry:
                be_lvl  = (entry + self.breakeven_at_R * R if d == 'bull'
                           else entry - self.breakeven_at_R * R)
                reached = (H[idx] >= be_lvl) if d == 'bull' else (L[idx] <= be_lvl)
                if reached:
                    t.sl = round(entry, 2)
                    be_hit = (L[idx] <= t.sl) if d == 'bull' else (H[idx] >= t.sl)
                    if be_hit:
                        t.exit_price = t.sl
                        cost  = self._trade_cost(t)
                        total = t.realized_pnl - cost   # kalan BE'de → 0 − maliyet
                        t.exit_time = TM[idx]
                        t.result = ('WIN' if total > 0.01 else
                                    ('BE' if abs(total) <= 0.01 else 'LOSS'))
                        t.pnl_dollar = round(total, 2)
                        t.exit_reason = 'be'
                        return True, partial - cost
            return False, partial

        for idx in bt_idx:
            if idx + 1 >= len(df5):
                break

            # ── Açık işlemleri kapat (FVG ve PRZ slotları bağımsız) ──────
            for slot_key in ('fvg', 'prz'):
                t = active_fvg if slot_key == 'fvg' else active_prz
                if t is None:
                    continue
                # ── MFE/MAE teşhis takibi (R cinsinden; mantığı etkilemez) ──
                _d = t.signal.direction
                _R = t.risk + 1e-10
                if _d == 'bull':
                    t.mfe_r = max(t.mfe_r, (float(H[idx]) - t.entry_price) / _R)
                    t.mae_r = max(t.mae_r, (t.entry_price - float(L[idx])) / _R)
                else:
                    t.mfe_r = max(t.mfe_r, (t.entry_price - float(L[idx])) / _R)
                    t.mae_r = max(t.mae_r, (float(H[idx]) - t.entry_price) / _R)
                exited, delta = _process_exit(t)
                equity += delta   # kısmi kâr ve/veya final çıkış (yoksa 0 → regresyon yok)
                if not exited and self.time_exit_bars is not None:
                    bars_open = idx - t.entry_bar_idx
                    if bars_open >= self.time_exit_bars:
                        close_price = float(C[idx])
                        d = t.signal.direction
                        rem_frac = (1.0 - t.tp1_fraction) if t.tp1_done else 1.0
                        mult = ((close_price - t.entry_price) if d == 'bull'
                                else (t.entry_price - close_price)) / (t.risk + 1e-10)
                        tdelta = mult * t.risk_dollar * rem_frac
                        t.exit_price = round(close_price, 2)
                        tdelta -= self._trade_cost(t)   # gidiş-dönüş maliyeti
                        equity += tdelta
                        total  = t.realized_pnl + tdelta
                        t.exit_price = round(close_price, 2)
                        t.exit_time  = TM[idx]
                        t.result     = ('WIN' if total > 0.01 else
                                        ('BE' if abs(total) <= 0.01 else 'LOSS'))
                        t.pnl_dollar = round(total, 2)
                        t.exit_reason = ('tp1+time' if t.tp1_done else 'time')
                        exited = True
                if exited:
                    t.equity_after  = round(equity, 2)
                    trades.append(t)
                    if slot_key == 'fvg':
                        active_fvg = None
                    else:
                        active_prz = None

            # İki slot da doluysa sinyal arama
            if active_fvg is not None and active_prz is not None:
                continue

            # Sinyal değerlendirme
            signal = self.brain.evaluate(
                idx=idx,
                C=C, O=O, H=H, L=L,
                E100=E100, E200=E200, RSI=RSI, ATR=ATR,
                TM=TM,
                fvg1_bull=fvg1_bull, mit1_bull=mit1_bull,
                fvg1_bear=fvg1_bear, mit1_bear=mit1_bear,
                fvg1_eng=fvg1_eng,
                msb_events_bull=msb_events_bull,
                msb_events_bear=msb_events_bear,
                przfvg_bull=przfvg_bull, przfvg_bear=przfvg_bear,
                mit_prz=mit_prz, prz_eng=prz_eng, prz_harm=prz_harm,
                ob1_bull=ob_bull, ob1_bear=ob_bear,
                mit_ob_bull=mit_ob_bull, mit_ob_bear=mit_ob_bear,
                poi1h_eng=poi1h_eng,
                **self._extra_brain_kwargs,
            )

            if signal is None:
                reason = self.brain.last_skip_reason
                if reason == 'no_bias':
                    dbg['no_bias'] += 1
                else:
                    dbg['no_signal'] += 1
                continue

            # ── EMA-MACD filtresi (opsiyonel) ─────────────────────────────
            if self.ema_macd_filter:
                cur_ts = to_naive(TM[idx]).timestamp()
                h1_pos = int(np.searchsorted(t1_ts, cur_ts, side='right')) - 1
                if h1_pos >= 0:
                    ema9 = EMA9_1h[h1_pos]
                    ema21 = EMA21_1h[h1_pos]
                    ml   = MACD_L_1h[h1_pos]
                    ms   = MACD_S_1h[h1_pos]
                    c1   = C1_arr[h1_pos]
                    if signal.direction == 'bull':
                        ok = (ema9 > ema21) and (c1 > ema9) and (ml > ms)
                    else:
                        ok = (ema9 < ema21) and (c1 < ema9) and (ml < ms)
                    if not ok:
                        dbg['no_signal'] += 1
                        continue

            # ── Saat karartması (blackout): bu UTC saatlerinde giriş yok ────
            if self.blackout_hours:
                eh = to_naive(TM[idx + 1]).hour if idx + 1 < len(TM) \
                     else to_naive(TM[idx]).hour
                if eh in self.blackout_hours:
                    dbg['no_signal'] += 1
                    continue

            # Sinyali ilgili slota yönlendir; dolu slot için atla
            is_prz = 'PRZ' in signal.confirmation_type
            if is_prz and active_prz is not None:
                continue   # PRZ slot dolu; FVG slot serbest ama PRZ sinyali geldi
            if not is_prz and active_fvg is not None:
                continue   # FVG slot dolu; PRZ slot serbest ama FVG sinyali geldi

            # Entry trade oluştur (alt sınıflar _make_entry_trade override eder)
            trade_id += 1
            new_trade = self._make_entry_trade(
                signal=signal, idx=idx, O=O, equity=equity, trade_id=trade_id,
                fvg1_bull=fvg1_bull, fvg1_bear=fvg1_bear,
                mit1_bull=mit1_bull, mit1_bear=mit1_bear,
                fvg1_eng=fvg1_eng,
                H1=H1, L1=L1, ATR1=atr1, T1=t1_ts,
            )
            if new_trade is None:
                trade_id -= 1
                dbg['risk_fail'] += 1
                continue

            dbg['generated'] += 1
            if signal.harmonic is not None:
                dbg['harmonic'] += 1
            if is_prz:
                active_prz = new_trade
            else:
                active_fvg = new_trade

            # Kullanım kuralı: tetikleyici FVG'yi tüket + pending'den çıkar
            if signal.trigger_fvg is not None:
                fid = signal.trigger_fvg.fvg_id
                self.brain.used_fvg_ids.add(fid)
                for d in ('bull', 'bear'):
                    self.brain.pending[d] = [
                        p for p in self.brain.pending[d] if p['fvg_id'] != fid]

        # Dönem sonu açık işlemler
        for t in (active_fvg, active_prz):
            if t is not None:
                t.exit_price   = float(C[-1])
                t.exit_time    = TM[-1]
                t.result       = 'OPEN'
                t.pnl_dollar   = round(t.realized_pnl, 2)  # kısmi kâr realize edildiyse yansıt
                t.equity_after = round(equity, 2)
                t.exit_reason  = 'open'
                trades.append(t)

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

    def monte_carlo(self, n_sim: int = 10_000, ruin_dd: float = 20.0) -> Optional[Dict]:
        """10k trade-sırası karıştırma ile MaxDD dağılımını hesaplar."""
        pnls = np.array([t.pnl_dollar for t in self.done])
        if len(pnls) < 5:
            return None
        rng = np.random.default_rng(42)
        max_dds = np.empty(n_sim)
        for i in range(n_sim):
            shuffled = pnls[rng.permutation(len(pnls))]
            eq = self.capital + np.cumsum(shuffled)
            pk = np.maximum.accumulate(eq)
            max_dds[i] = ((pk - eq) / (pk + 1e-10) * 100.0).max()
        return {
            'p50_maxdd': float(np.percentile(max_dds, 50)),
            'p95_maxdd': float(np.percentile(max_dds, 95)),
            'p99_maxdd': float(np.percentile(max_dds, 99)),
            'ruin_pct' : float((max_dds > ruin_dd).mean() * 100.0),
            'n_trades' : int(len(pnls)),
            'n_sim'    : n_sim,
            'ruin_dd'  : ruin_dd,
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

        # Konfluens BİLEŞENLERİ — her biri ayrı (kombine etiket '+' ile bölünür).
        # Bir işlem birden çok bileşene sayılır: 'EMA+PRZ' hem EMA hem PRZ'ye.
        comp_d: Dict[str, Dict] = {}
        for t in self.done:
            comps = [c for c in t.signal.confirmation_type.split('+') if c]
            for c in comps:
                comp_d.setdefault(c, {'n': 0, 'w': 0, 'l': 0, 'be': 0, 'pnl': 0.0})
                comp_d[c]['n']   += 1
                comp_d[c]['w']   += 1 if t.result == 'WIN'  else 0
                comp_d[c]['l']   += 1 if t.result == 'LOSS' else 0
                comp_d[c]['be']  += 1 if t.result == 'BE'   else 0
                comp_d[c]['pnl'] += t.pnl_dollar
        print(f"\n  ── KONFLUENS BİLEŞENLERİ (her biri ayrı) ───────────────────")
        for c in sorted(comp_d, key=lambda k: comp_d[k]['pnl'], reverse=True):
            d  = comp_d[c]
            wr = d['w'] / (d['w'] + d['l']) * 100 if (d['w'] + d['l']) else 0
            print(f"  {c:<8} : {d['n']:3d} işlem | "
                  f"{d['w']}W/{d['l']}L/{d['be']}BE | "
                  f"%{wr:.0f} WR | ${d['pnl']:>+8.2f}")

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

        # Monte Carlo
        mc = self.monte_carlo()
        if mc:
            print(f"\n  ── MONTE CARLO ({mc['n_sim']:,} simülasyon │ {mc['n_trades']} işlem) ────────────────────")
            print(f"  Medyan MaxDD       : %{mc['p50_maxdd']:.2f}")
            print(f"  P95 MaxDD          : %{mc['p95_maxdd']:.2f}  ← tipik kötü senaryo")
            print(f"  P99 MaxDD          : %{mc['p99_maxdd']:.2f}  ← ekstrem senaryo")
            print(f"  Çöküş ihtimali     : %{mc['ruin_pct']:.1f}  (MaxDD>%{mc['ruin_dd']:.0f})")

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

    # Bileşenler — bias seçimi ortam değişkenleriyle:
    #   BIAS=0        → bias yok (her iki yön serbest)
    #   BIASMODE=daily→ günlük bias (daily_bias.json; yoksa veriden üretilir)
    #   varsayılan    → haftalık bias (weekly_bias.json)
    use_bias  = os.environ.get('BIAS', '1') != '0'
    bias_mode = os.environ.get('BIASMODE', 'weekly').lower()
    if not use_bias:
        bias_provider = None
        print("  [BIAS=0] Bias DEVRE DIŞI — her iki yön serbest.\n")
    elif bias_mode == 'daily':
        if not Path('daily_bias.json').exists():
            print("  daily_bias.json yok → 1H verisinden üretiliyor...")
            DailyBiasProvider.build_from_1h(df_1h, 'daily_bias.json')
        bias_provider = DailyBiasProvider('daily_bias.json')
        print("  [BIASMODE=daily] Günlük bias aktif (TEST — hindsight içerir).\n")
    else:
        bias_provider = WeeklyBiasProvider('weekly_bias.json')
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


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 10: FİB RETEST STRATEJİSİ
# ═══════════════════════════════════════════════════════════════════════════

import calendar as _cal

class SessionFilter:
    """
    London + NY seansı — DST-düzeltmeli UTC saatleri.

    Londra BST: son Pazar Mart → son Pazar Ekim (UTC+1 yaz saati)
      GMT kışı : 08:00–12:00 UTC   |  BST yazı: 07:00–11:00 UTC
    New York:
      EST kışı : 13:00–21:00 UTC   |  EDT yazı: 12:00–20:00 UTC

    Tatil: US + UK piyasa tatilleri (statik set).
    Tokyo 05.11.2024 değişikliği: 30 dk erkene alındı — bilgi notu, filtrelenmiyor.
    """

    # ABD piyasa tatilleri (ay-gün çiftleri; bazıları yıla göre kayar)
    _US_FIXED = {(1,1),(6,19),(7,4),(12,25)}        # New Year, Juneteenth, IndDay, Xmas

    # UK sabit tatiller (ay-gün)
    _UK_FIXED = {(1,1),(12,25),(12,26)}              # New Year, Christmas, Boxing Day

    # Yüzer tatiller için yaklaşım tablosu (2024-2028)
    _US_FLOAT: Dict[str, set] = {
        '2024': {(1,15),(2,19),(3,29),(5,27),(9,2),(11,28)},
        '2025': {(1,20),(2,17),(4,18),(5,26),(9,1),(11,27)},
        '2026': {(1,19),(2,16),(4,3),(5,25),(9,7),(11,26)},
        '2027': {(1,18),(2,15),(4,26),(5,31),(9,6),(11,25)},
        '2028': {(1,17),(2,21),(4,14),(5,29),(9,4),(11,23)},
    }
    _UK_FLOAT: Dict[str, set] = {
        '2024': {(3,29),(4,1),(5,6),(5,27),(8,26),(12,26)},
        '2025': {(4,18),(4,21),(5,5),(5,26),(8,25)},
        '2026': {(4,3),(4,6),(5,4),(5,25),(8,31)},
        '2027': {(3,26),(3,29),(5,3),(5,31),(8,30)},
        '2028': {(4,14),(4,17),(5,1),(5,29),(8,28)},
    }

    @staticmethod
    def _last_sunday(year: int, month: int) -> datetime:
        last_day = _cal.monthrange(year, month)[1]
        d = datetime(year, month, last_day)
        return d - timedelta(days=d.weekday() + 1 if d.weekday() != 6 else 0)

    @staticmethod
    def _nth_sunday(year: int, month: int, n: int) -> datetime:
        d = datetime(year, month, 1)
        offset = (6 - d.weekday()) % 7
        return d + timedelta(days=offset + (n - 1) * 7)

    def is_london_dst(self, dt: datetime) -> bool:
        y = dt.year
        start = self._last_sunday(y, 3)
        end   = self._last_sunday(y, 10)
        return start <= dt.replace(hour=1,minute=0,second=0,microsecond=0) < end

    def is_ny_dst(self, dt: datetime) -> bool:
        y = dt.year
        start = self._nth_sunday(y, 3, 2)
        end   = self._nth_sunday(y, 11, 1)
        return start <= dt.replace(hour=2,minute=0,second=0,microsecond=0) < end

    def is_london_session(self, dt: datetime) -> bool:
        h = dt.hour + dt.minute / 60.0
        if self.is_london_dst(dt):
            return 7.0 <= h < 11.0   # BST yazı: 07–11 UTC
        return 8.0 <= h < 12.0       # GMT kışı: 08–12 UTC

    def is_ny_session(self, dt: datetime) -> bool:
        h = dt.hour + dt.minute / 60.0
        if self.is_ny_dst(dt):
            return 12.0 <= h < 20.0  # EDT yazı: 12–20 UTC
        return 13.0 <= h < 21.0      # EST kışı: 13–21 UTC

    def is_holiday(self, dt: datetime) -> bool:
        key = str(dt.year)
        md  = (dt.month, dt.day)
        us_h = self._US_FIXED | self._US_FLOAT.get(key, set())
        uk_h = self._UK_FIXED | self._UK_FLOAT.get(key, set())
        return md in us_h or md in uk_h

    def is_active(self, dt: datetime) -> bool:
        if self.is_holiday(dt):
            return False
        return self.is_london_session(dt) or self.is_ny_session(dt)


@dataclass
class FibRetestState:
    """MSB sonrası 0.618 retest bekleme durumu."""
    direction      : str
    fvg            : FVG
    fvg_touch_idx  : int
    fib_low        : float    # bull: FVG bölgesindeki en düşük dip
    fib_high       : float    # bull: MSB'den sonra görülen en yüksek tepe (rolling)
    msb_confirm_idx: int
    msb_event      : MSBEvent
    age_bars       : int = 0
    peak_locked    : bool = False
    bars_no_new_peak: int = 0  # tepe güncellemesiz geçen bar sayısı (kilitleme için)

    PEAK_LOCK_BARS  : int = field(default=3, init=False, repr=False)
    TIMEOUT_BARS    : int = field(default=48, init=False, repr=False)


class LiquidityTargetFinder:
    """
    TP: entry'den yön doğrultusunda 2R–5R aralığındaki
    ilk mitigas edilmemiş 1H FVG kenarı.
    Aralıkta hedef yoksa 2R kullanılır.
    """

    def find_tp(self, direction: str, entry: float, sl: float,
                fvg1_list: List[FVG], mit_map: Dict,
                current_time: Any,
                fvg1_eng: 'FVGEngine') -> float:
        risk = abs(entry - sl)
        if risk < 1e-6:
            return entry + 2 * risk if direction == 'bull' else entry - 2 * risk

        if direction == 'bull':
            min_tp = entry + 2.0 * risk
            max_tp = entry + 5.0 * risk
        else:
            min_tp = entry - 2.0 * risk
            max_tp = entry - 5.0 * risk

        active = fvg1_eng.get_active(fvg1_list, mit_map, current_time)
        candidates = []
        for fvg in active:
            if direction == 'bull':
                edge = fvg.bottom   # yukarıdaki FVG alt kenarı = likidite
                if min_tp < edge <= max_tp:
                    candidates.append(edge)
            else:
                edge = fvg.top      # aşağıdaki FVG üst kenarı = likidite
                if max_tp <= edge < min_tp:
                    candidates.append(edge)
        if candidates:
            return min(candidates) if direction == 'bull' else max(candidates)
        return min_tp  # fallback: 2R


class EqualLiquidityFinder:
    """
    TP hedef önceliği:
      1. Eşit tepeler/dipler (equal highs/lows) — liquidity cluster
      2. Açık 1H FVG kenarı (doldurulmamış dengesizlik)
      3. Fallback: min_tp = config.min_r × risk

    config.min_r – config.max_r (varsayılan 2R–4R) dışındaki hedefler elenir.
    """

    def __init__(self, config: LiquidityTPConfig = None):
        self.cfg = config or LiquidityTPConfig()

    def find_tp(self,
                direction   : str,
                entry       : float,
                sl          : float,
                H1          : np.ndarray,
                L1          : np.ndarray,
                ATR1        : np.ndarray,
                idx         : int,
                fvg1_list   : List[FVG],
                mit_map     : Dict,
                current_time: Any,
                fvg1_eng    : 'FVGEngine',
                T1          : Optional[np.ndarray] = None) -> float:
        """T1: float timestamp array of 1H bars (from np.array([t.timestamp() for t in df1.index]))."""

        risk = abs(entry - sl)
        if risk < 1e-6:
            return (entry + self.cfg.min_r * risk if direction == 'bull'
                    else entry - self.cfg.min_r * risk)

        if direction == 'bull':
            min_tp = entry + self.cfg.min_r * risk
            max_tp = entry + self.cfg.max_r * risk
        else:
            min_tp = entry - self.cfg.min_r * risk
            max_tp = entry - self.cfg.max_r * risk

        # ── Adım 1: Eşit tepeler/dipler ──────────────────────────────────
        # Compute correct 1H index — idx is the 5M bar index, not 1H
        if T1 is not None and len(T1) > 0:
            ct     = to_naive(current_time).timestamp()
            h1_idx = int(np.searchsorted(T1, ct, side='right')) - 1
            h1_idx = max(0, min(h1_idx, len(H1) - 1))
        else:
            h1_idx = min(idx, len(H1) - 1)

        look_start = max(0, h1_idx - self.cfg.swing_lookback)
        n_slice    = h1_idx - look_start + 1

        slice_h   = H1[look_start : h1_idx + 1]
        slice_l   = L1[look_start : h1_idx + 1]
        slice_atr = ATR1[look_start : h1_idx + 1]

        atr_now = float(slice_atr[-1]) if len(slice_atr) > 0 and slice_atr[-1] > 0 \
                  else max(risk * 0.5, 1e-6)
        tol = self.cfg.eq_tol_atr * atr_now

        # Use _pivots_1h for actual swing high/low prices (SwingEngine returns
        # rolling-last-price arrays, not binary indicators)
        if n_slice >= 2 * self.cfg.swing_strength + 1:
            pivots = _pivots_1h(slice_h, slice_l, slice_atr, n_slice,
                                strength=self.cfg.swing_strength)
            if direction == 'bull':
                raw_levels = np.array([p[2] for p in pivots if p[3] == 'H'])
            else:
                raw_levels = np.array([p[2] for p in pivots if p[3] == 'L'])
        else:
            raw_levels = np.array([])

        eql_candidates = []
        for level in raw_levels:
            in_range = (min_tp < level <= max_tp) if direction == 'bull' \
                       else (max_tp <= level < min_tp)
            if not in_range:
                continue
            touches = int(np.sum(np.abs(raw_levels - level) <= tol))
            if touches >= self.cfg.min_touches:
                eql_candidates.append(level)

        if eql_candidates:
            return (min(eql_candidates) if direction == 'bull'
                    else max(eql_candidates))

        # ── Adım 2: Açık 1H FVG kenarı ───────────────────────────────────
        if self.cfg.fallback_fvg and fvg1_eng is not None:
            active = fvg1_eng.get_active(fvg1_list, mit_map, current_time)
            fvg_cands = []
            for fvg in active:
                edge = fvg.bottom if direction == 'bull' else fvg.top
                if direction == 'bull' and min_tp < edge <= max_tp:
                    fvg_cands.append(edge)
                elif direction == 'bear' and max_tp <= edge < min_tp:
                    fvg_cands.append(edge)
            if fvg_cands:
                return (min(fvg_cands) if direction == 'bull'
                        else max(fvg_cands))

        # ── Adım 3: Fallback min_r ────────────────────────────────────────
        return min_tp


class FibRetestBrain:
    """
    Bias-özel Fib 0.618 Retest Stratejisi.

    Akış (her 5M barında):
      Adım 1: 1H FVG'ye wick dokunuşu → pending kayıt
              bull: fib_anchor = lowest L(-40bar..touch)
              bear: fib_anchor = highest H(-40bar..touch)
      Adım 2: Bias + EMA onayı (MarketBrain ile aynı kural)
      Adım 3: MSB onayı (5M) → FibRetestState oluştur
              bull: fib_extreme başlangıcı = H[msb_bar] (rolling max)
              bear: fib_extreme başlangıcı = L[msb_bar] (rolling min)
      Adım 4: Rolling extreme güncelle; L/H 0.618'e ulaşırsa sinyal üret
              İptal: yapı kırıldı VEYA peak kilitli sonrası yeni extreme VEYA timeout
    """

    TOUCH_MAX_AGE_BARS = 24
    FIB_RATIO          = 0.618
    PEAK_LOCK_BARS     = 3     # bu kadar bar yeni extreme olmadıysa kilitle
    TIMEOUT_BARS       = 48    # 48×5dk = 4sa

    def __init__(self,
                 bias_provider: Optional['WeeklyBiasProvider'] = None,
                 session_filter: Optional[SessionFilter] = None):
        self.bias    = bias_provider
        self.session = session_filter
        self.used_fvg_ids: set = set()
        self.pending_msb: Dict[str, List[dict]] = {'bull': [], 'bear': []}
        self.tracking: Dict[str, List[FibRetestState]] = {'bull': [], 'bear': []}
        self.stats = dict(step1_fail=0, step2_fail=0, step3_fail=0,
                          step4_no_session=0, step4_cancelled=0)
        self.last_skip_reason: Optional[str] = None  # BacktestEngine uyumluluğu
        # MarketBrain uyumluluğu için pending dict (BacktestEngine'in FVG tüketim mantığı)
        self.pending: Dict[str, List[dict]] = {'bull': [], 'bear': []}

    def _ema_confirm(self, close: float, e100: float, e200: float,
                     direction: str) -> bool:
        if direction == 'bull':
            return close > e100 and close > e200
        return close < e100 and close < e200

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
                 ATR: Optional[np.ndarray] = None,
                 **kwargs) -> Optional[TradeSignal]:

        self.last_skip_reason = None
        cur_time   = TM[idx]
        t          = to_naive(cur_time)
        cur_close  = float(C[idx])
        weekly_dir = self.bias.get(cur_time) if self.bias is not None else None

        if self.bias is not None and weekly_dir is None:
            self.last_skip_reason = 'no_bias'

        for direction in ('bull', 'bear'):
            fvg1_raw   = fvg1_bull if direction == 'bull' else fvg1_bear
            mit1       = mit1_bull if direction == 'bull' else mit1_bear
            msb_events = msb_events_bull if direction == 'bull' else msb_events_bear
            pend       = self.pending_msb[direction]
            track      = self.tracking[direction]

            # ── ADIM 1: 1H FVG wick dokunuşu ─────────────────────────────
            active_fvgs = fvg1_eng.get_active(fvg1_raw, mit1, t)
            pend_ids    = {p['fvg_id'] for p in pend}
            track_ids   = {s.fvg.fvg_id for s in track}
            for fvg in active_fvgs:
                if fvg.fvg_id in self.used_fvg_ids:
                    continue
                if fvg.fvg_id in pend_ids or fvg.fvg_id in track_ids:
                    continue
                span = fvg.top - fvg.bottom
                buf  = span * fvg1_eng.buf_ratio
                if L[idx] <= (fvg.top + buf) and H[idx] >= (fvg.bottom - buf):
                    lk_start = max(0, idx - 40)
                    # anchor: bull=lowest L (fib başlangıç dibi), bear=highest H (fib başlangıç tepesi)
                    anchor = (float(np.min(L[lk_start:idx + 1]))
                              if direction == 'bull'
                              else float(np.max(H[lk_start:idx + 1])))
                    pend.append({'fvg_id': fvg.fvg_id, 'fvg': fvg,
                                 'touch_idx': idx, 'touch_time': t,
                                 'fib_anchor': anchor})
                    pend_ids.add(fvg.fvg_id)

            # Pending yaşlandır / tüket
            self.pending_msb[direction] = [
                p for p in pend
                if p['fvg_id'] not in self.used_fvg_ids
                and (mit1.get(p['fvg_id']) is None
                     or to_naive(mit1[p['fvg_id']]) > t)
                and (idx - p['touch_idx']) <= self.TOUCH_MAX_AGE_BARS
            ]
            pend = self.pending_msb[direction]

            if not pend and not track:
                self.stats['step1_fail'] += 1
                continue

            # ── ADIM 2: Bias + EMA onayı ──────────────────────────────────
            bias_ok = (self.bias is None) or (weekly_dir == direction)
            ema_ok  = self._ema_confirm(cur_close,
                                        float(E100[idx]), float(E200[idx]),
                                        direction)
            if not (bias_ok and ema_ok):
                if not track:
                    self.stats['step2_fail'] += 1
                    continue

            # ── ADIM 3: MSB onayı → pending'den tracking'e geçir ─────────
            if bias_ok and ema_ok and pend:
                promoted = set()
                for p in list(pend):
                    tch   = p['touch_idx']
                    event: Optional[MSBEvent] = None
                    for e in reversed(msb_events):
                        if e.confirm_idx > idx:
                            continue
                        if e.confirm_idx < tch:
                            break
                        event = e
                        break
                    if event is None:
                        continue
                    # bull: fib_low=anchor(dip), fib_high=extreme_init(tepe)
                    # bear: fib_high=anchor(tepe), fib_low=extreme_init(dip)
                    if direction == 'bull':
                        fl = p['fib_anchor']
                        fh = float(H[event.confirm_idx])
                    else:
                        fl = float(L[event.confirm_idx])
                        fh = p['fib_anchor']
                    state = FibRetestState(
                        direction       = direction,
                        fvg             = p['fvg'],
                        fvg_touch_idx   = tch,
                        fib_low         = fl,
                        fib_high        = fh,
                        msb_confirm_idx = event.confirm_idx,
                        msb_event       = event,
                    )
                    track.append(state)
                    promoted.add(p['fvg_id'])
                self.pending_msb[direction] = [
                    x for x in self.pending_msb[direction]
                    if x['fvg_id'] not in promoted
                ]

            # ── ADIM 4: Tracking — extreme güncelle, 0.618 bekle ─────────
            signal_candidate: Optional[TradeSignal] = None
            still_tracking: List[FibRetestState] = []

            for state in track:
                state.age_bars += 1

                if state.age_bars > self.TIMEOUT_BARS:
                    self.stats['step4_cancelled'] += 1
                    self.used_fvg_ids.add(state.fvg.fvg_id)
                    continue

                # Yapısal iptal: fib anchor kırıldı
                if direction == 'bull' and L[idx] < state.fib_low * 0.999:
                    self.stats['step4_cancelled'] += 1
                    self.used_fvg_ids.add(state.fvg.fvg_id)
                    continue
                if direction == 'bear' and H[idx] > state.fib_high * 1.001:
                    self.stats['step4_cancelled'] += 1
                    self.used_fvg_ids.add(state.fvg.fvg_id)
                    continue

                # Extreme güncelle
                if direction == 'bull':
                    # fib_high = rolling max (impulse tepesi)
                    if H[idx] > state.fib_high:
                        if state.peak_locked:
                            self.stats['step4_cancelled'] += 1
                            self.used_fvg_ids.add(state.fvg.fvg_id)
                            continue
                        state.fib_high = float(H[idx])
                        state.bars_no_new_peak = 0
                    else:
                        state.bars_no_new_peak += 1
                        if (not state.peak_locked
                                and state.bars_no_new_peak >= self.PEAK_LOCK_BARS):
                            state.peak_locked = True
                else:
                    # fib_low = rolling min (impulse dibi)
                    if L[idx] < state.fib_low:
                        if state.peak_locked:
                            self.stats['step4_cancelled'] += 1
                            self.used_fvg_ids.add(state.fvg.fvg_id)
                            continue
                        state.fib_low = float(L[idx])
                        state.bars_no_new_peak = 0
                    else:
                        state.bars_no_new_peak += 1
                        if (not state.peak_locked
                                and state.bars_no_new_peak >= self.PEAK_LOCK_BARS):
                            state.peak_locked = True

                # 0.618 seviyesi
                swing_range = state.fib_high - state.fib_low
                if swing_range < 0.5:
                    still_tracking.append(state)
                    continue

                if direction == 'bull':
                    fib_0618 = state.fib_high - self.FIB_RATIO * swing_range
                    touched  = L[idx] <= fib_0618
                else:
                    fib_0618 = state.fib_low + self.FIB_RATIO * swing_range
                    touched  = H[idx] >= fib_0618

                if not touched:
                    still_tracking.append(state)
                    continue

                # Seans filtresi
                if self.session is not None and not self.session.is_active(t):
                    self.stats['step4_no_session'] += 1
                    still_tracking.append(state)
                    continue

                # Sinyal oluştur
                sig = TradeSignal(
                    entry_time        = cur_time,
                    direction         = direction,
                    trigger_fvg       = state.fvg,
                    confirmation_type = 'FIB618',
                    confidence        = min(100.0, 50 + state.fvg.quality_score / 2),
                    msb_type          = state.msb_event.msb_type,
                    confluence_count  = 1,
                    stop_price        = state.msb_event.stop_price,
                    risk_fraction     = 0.005,
                    fib_level         = round(fib_0618, 2),
                )
                if (signal_candidate is None or
                        state.fvg.quality_score >
                        signal_candidate.trigger_fvg.quality_score):
                    signal_candidate = sig
                self.used_fvg_ids.add(state.fvg.fvg_id)

            self.tracking[direction] = still_tracking
            if signal_candidate is not None:
                return signal_candidate

        return None


class FibBacktestEngine(BacktestEngine):
    """
    BacktestEngine'den kalıtım alır; tek fark: entry sırasında
    LiquidityTargetFinder veya EqualLiquidityFinder üzerinden dinamik TP.
    liq_finder=None olursa standart RR TP kullanılır (BacktestEngine gibi).
    """

    def __init__(self, brain, risk_mgr: RiskManager,
                 liq_finder=None,
                 initial_capital: float = 10_000,
                 breakeven_at_R: Optional[float] = None):
        super().__init__(brain, risk_mgr, initial_capital, breakeven_at_R)
        self.liq_finder = liq_finder

    def _make_entry_trade(self, signal: TradeSignal, idx: int,
                          O: np.ndarray, equity: float, trade_id: int,
                          fvg1_bull=None, fvg1_bear=None,
                          mit1_bull=None, mit1_bear=None,
                          fvg1_eng=None,
                          H1=None, L1=None, ATR1=None,
                          T1: Optional[np.ndarray] = None) -> Optional[Trade]:
        entry = float(O[idx + 1])
        tp_override = None

        if self.liq_finder is not None and fvg1_eng is not None:
            fvg_list = fvg1_bull if signal.direction == 'bull' else fvg1_bear
            mit_map  = mit1_bull if signal.direction == 'bull' else mit1_bear
            sl_est = (signal.stop_price * (1.0 - self.risk.sl_buffer)
                      if signal.direction == 'bull'
                      else signal.stop_price * (1.0 + self.risk.sl_buffer))

            if isinstance(self.liq_finder, EqualLiquidityFinder):
                tp_cand = self.liq_finder.find_tp(
                    signal.direction, entry, sl_est,
                    H1, L1, ATR1, idx,
                    fvg_list or [], mit_map or {},
                    to_naive(signal.entry_time), fvg1_eng,
                    T1=T1,
                )
            else:
                tp_cand = self.liq_finder.find_tp(
                    signal.direction, entry, sl_est,
                    fvg_list or [], mit_map or {},
                    to_naive(signal.entry_time), fvg1_eng,
                )

            if signal.direction == 'bull' and tp_cand > entry:
                tp_override = tp_cand
            elif signal.direction == 'bear' and tp_cand < entry:
                tp_override = tp_cand

        r = self.risk.compute(signal.direction, entry,
                              signal.stop_price, equity,
                              signal.risk_fraction,
                              tp_override=tp_override)
        if r is None:
            return None
        return Trade(
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


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 12: THREE_VOL (ThreeVolBrain)
# ═══════════════════════════════════════════════════════════════════════════

class ThreeVolBrain:
    """
    Three White Soldiers / Three Black Crows → doğrudan momentum girişi.
    FVG veya POI dokunuşu GEREKMİYOR.

    Akış:
      1. MSB5MEngine three_vol olayı bu barda onaylandı
      2. Bias + EMA100/200 onayı (her ikisi şart)
      3. Giriş: bir sonraki bar açılışı
      SL: olay.stop_price (2. mumun Low/High, wick dahil)
    """

    THREE_VOL_MAX_BARS = 1   # sinyal yalnızca olayın onay barında geçerli

    def __init__(self, bias_provider=None):
        self.bias             = bias_provider
        self.last_skip_reason: Optional[str] = None
        self.used_fvg_ids: set = set()
        self.pending: Dict[str, list] = {'bull': [], 'bear': []}
        self.stats = dict(step1_fail=0, step2_fail=0, step3_fail=0)

    def _ema_ok(self, close: float, e100: float, e200: float, direction: str) -> bool:
        if direction == 'bull':
            return close > e100 and close > e200
        return close < e100 and close < e200

    def evaluate(self, idx: int,
                 C: np.ndarray, O: np.ndarray,
                 H: np.ndarray, L: np.ndarray,
                 E100: np.ndarray, E200: np.ndarray,
                 TM: pd.Index,
                 msb_events_bull: List[MSBEvent],
                 msb_events_bear: List[MSBEvent],
                 ATR: Optional[np.ndarray] = None,
                 RSI: Optional[np.ndarray] = None,
                 **_) -> Optional[TradeSignal]:
        self.last_skip_reason = None
        cur_time  = TM[idx]
        cur_close = float(C[idx])
        weekly_dir = self.bias.get(cur_time) if self.bias is not None else None

        for direction in ('bull', 'bear'):
            if self.bias is not None and weekly_dir != direction:
                continue
            if not self._ema_ok(cur_close, float(E100[idx]), float(E200[idx]), direction):
                self.stats['step2_fail'] += 1
                continue
            events = msb_events_bull if direction == 'bull' else msb_events_bear
            for e in events:
                if e.confirm_idx == idx and e.msb_type == 'three_vol':
                    return TradeSignal(
                        entry_time        = cur_time,
                        direction         = direction,
                        trigger_fvg       = None,
                        confirmation_type = 'EMA+3VOL',
                        confidence        = min(100.0, float(e.quality) * 100),
                        msb_type          = 'three_vol',
                        confluence_count  = 1,
                        stop_price        = e.stop_price,
                        risk_fraction     = 0.01,
                    )
            self.stats['step1_fail'] += 1

        if self.bias is not None and weekly_dir is None:
            self.last_skip_reason = 'no_bias'
        else:
            self.last_skip_reason = 'no_signal'
        return None


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 13: LONDON REVERSAL (ICT Judas Swing)
# ═══════════════════════════════════════════════════════════════════════════

class AsianRangeCalculator:
    """
    Her 5M bara karşı en son tamamlanmış Asya seansı (23:00–05:59 UTC) H/L.

    Seans gece yarısını aşar → lookahead koruması kritik:
      - 23:xx barlar: Pazartesi seansının başlangıcı ama seans devam ediyor
        → önceki tamamlanmış seansı (Pazar 23:00–Pazartesi 05:59) kullan
      - 06:00+ barlar: Seans tamamlandı → mevcut seansı kullan ✓
    """

    @staticmethod
    def compute(df_5m: pd.DataFrame,
                start_utc: int = 23, end_utc: int = 6) -> Tuple[np.ndarray, np.ndarray]:
        """Her 5M bara karşı en son TAMAMLANMIŞ Asya seansı H/L (lookahead-safe).

        Pencere parametrik:
          • start_utc > end_utc → gece yarısını aşan pencere (örn. 23→06, varsayılan).
          • start_utc < end_utc → aynı gün penceresi (örn. 00→05, kanonik ICT).
        """
        idx = df_5m.index
        if hasattr(idx, 'tz') and idx.tz is not None:
            idx = idx.tz_convert('UTC').tz_localize(None)
        dt  = pd.DatetimeIndex(idx)
        H   = df_5m['High'].values.astype(float)
        L   = df_5m['Low'].values.astype(float)
        n   = len(df_5m)
        one_day = pd.Timedelta(days=1)
        crossing = start_utc > end_utc

        if crossing:
            asian_mask = (dt.hour < end_utc) | (dt.hour >= start_utc)
        else:
            asian_mask = (dt.hour >= start_utc) & (dt.hour < end_utc)

        # Seans tarihi = o seansın ait olduğu London günü (end_utc'de kapanır)
        daily_h: dict = {}
        daily_l: dict = {}
        for i in range(n):
            if not asian_mask[i]:
                continue
            if crossing and dt[i].hour >= start_utc:
                key = (dt[i] + one_day).strftime('%Y-%m-%d')   # ertesi günün seansı
            else:
                key = dt[i].strftime('%Y-%m-%d')
            h_val = float(H[i]); l_val = float(L[i])
            if key not in daily_h or h_val > daily_h[key]:
                daily_h[key] = h_val
            if key not in daily_l or l_val < daily_l[key]:
                daily_l[key] = l_val

        ASIAN_H = np.full(n, np.nan)
        ASIAN_L = np.full(n, np.nan)
        for i in range(n):
            if crossing:
                if asian_mask[i]:
                    # Seans devam ediyor → önceki tamamlanmış seans (lookahead yok)
                    key = (dt[i] if dt[i].hour >= start_utc
                           else (dt[i] - one_day)).strftime('%Y-%m-%d')
                else:
                    key = dt[i].strftime('%Y-%m-%d')   # tamamlandı → mevcut seans
            else:
                # Aynı-gün penceresi: end_utc'den önce seans tamamlanmadı → dün
                if dt[i].hour >= end_utc:
                    key = dt[i].strftime('%Y-%m-%d')
                else:
                    key = (dt[i] - one_day).strftime('%Y-%m-%d')
            if key in daily_h:
                ASIAN_H[i] = daily_h[key]
                ASIAN_L[i] = daily_l[key]

        return ASIAN_H, ASIAN_L

    @staticmethod
    def compute_pdhl(df_5m: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """Her 5M bara karşı önceki TAMAMLANMIŞ UTC takvim gününün High/Low
        (PDH/PDL likidite havuzları, lookahead-safe)."""
        idx = df_5m.index
        if hasattr(idx, 'tz') and idx.tz is not None:
            idx = idx.tz_convert('UTC').tz_localize(None)
        dt  = pd.DatetimeIndex(idx)
        H   = df_5m['High'].values.astype(float)
        L   = df_5m['Low'].values.astype(float)
        n   = len(df_5m)
        one_day = pd.Timedelta(days=1)

        daily_h: dict = {}
        daily_l: dict = {}
        for i in range(n):
            key = dt[i].strftime('%Y-%m-%d')
            daily_h[key] = max(daily_h.get(key, -1e18), float(H[i]))
            daily_l[key] = min(daily_l.get(key,  1e18), float(L[i]))

        PDH = np.full(n, np.nan)
        PDL = np.full(n, np.nan)
        for i in range(n):
            key = (dt[i] - one_day).strftime('%Y-%m-%d')   # önceki gün (kapalı)
            if key in daily_h:
                PDH[i] = daily_h[key]
                PDL[i] = daily_l[key]
        return PDH, PDL


class LondonReversalBrain:
    """
    ICT London Reversal (Judas Swing) — London Killzone'da likidite süpürmesi + dönüş.

    SÜPÜRME: London Killzone içinde fiyat bir likidite havuzunu (Asya H/L ve
    opsiyonel olarak önceki gün H/L = PDH/PDL) wick'le aşar VE içeri kapanır
    (rejection). Süpürme bias'ın TERSİ yöndedir (manipülasyon), dönüş bias yönünde.
    Sweep derinliği min < depth < max (gerçek breakout elenir).

    GİRİŞ — entry_mode (config):
      • 'retest' (CONFIG VARSAYILANI): süpürme sonrası fiyat süpürülen seviyeye
        geri dönünce giriş (limit-retest yaklaşımı, dar stop). SL = Judas ekstremi.
        Varsayılan preset: retest + sweep_window_bars=12 + private bias — grid
        backtest'te dört bias modunda da pozitif tek kombinasyon.
      • 'immediate': süpürme+reddediş barında anında giriş (O[idx+1]).
        SL = reddediş wick ucu. En çok işlem üreten mod (kod fallback'i).
      • 'cisd_break': süpürme sonrası ≤ max_cisd_bars içinde bir bar reddediş barının
        zıt ucunu kapanışla kırarsa (CISD/MSS) giriş. SL = Judas ekstremi.
      • 'fvg_ote': CISD displacement'i bir 5M FVG bırakır; fiyat FVG'ye geri çekilince
        giriş. SL = Judas ekstremi.
      • 'ote': CISD kırılımı sonrası dönüş bacağının %62–79 fib geri çekilmesine
        (Optimal Trade Entry, optimal 0.705) fiyat girince giriş. SL = Judas ekstremi
        (fib 1.0) ötesi — ICT'nin klasik giriş tekniği.

    FİLTRE BORU HATTI (hepsi config, 0/None = kapalı):
      hafta sonu/tatil → killzone → bias → günlük limit → Asya range geçerli →
      Asya range boyutu (min/max × ATR) → [sweep anı] derinlik min/max ×ATR →
      reddediş kalitesi (close-pos) → killzone alt-penceresi (erken sweep) →
      displacement (tetik barı gövdesi ≥ X × ATR).

    TP1 = Asya equilibrium (%50) — kısmi kâr + SL→BE.  TP2 = Asya karşı taraf — runner.
    Günde max 1 işlem. Likidite havuzları AsianRangeCalculator ile lookahead-safe.
    """

    MIN_SWEEP_MULT      = 0.05   # ATR × bu oran = min sweep derinliği
    MIN_SWEEP_PTS       = 0.30   # mutlak minimum ($)
    MAX_SWEEP_DIST_MULT = 1.5    # ATR × bu orandan derin = gerçek breakout → atla
    ENTRY_MODE          = 'immediate'  # bkz. VALID_ENTRY_MODES
    VALID_ENTRY_MODES   = ('immediate', 'cisd_break', 'fvg_ote', 'retest', 'ote')
    USE_PDH_PDL         = True   # önceki gün H/L'sini de likidite havuzu say
    MAX_CISD_BARS       = 6      # süpürme → CISD için max bekleme
    MAX_ENTRY_BARS      = 12     # CISD→FVG/OTE girişi veya seviye retest'i için max bekleme
    FVG_MIN_GAP         = 0.20   # displacement FVG min boşluk ($)
    REJECTION_CLOSE_PCT = 0.60   # sweep barı kendi aralığının uzak %40'ında kapanmalı
                                 # (güçlü reddediş; zayıf mikro-stop gürültüsünü eler) 0=kapalı
                                 # 0.60: bias modlarında regresyon yok + none gürültüsü azalır
    WEEKEND_FILTER      = True   # Cumartesi/Pazar girişleri engelle (7/24 kripto-altın
                                 # verisinde hafta sonu "London killzone" gerçek değildir)
    ASIAN_RANGE_MIN_ATR = 0.0    # Asya range < X×ATR → gün atla: dar range'in likiditesi
                                 # anlamsız (0=kapalı)
    ASIAN_RANGE_MAX_ATR = 0.0    # Asya range > X×ATR → gün atla: volatil gece, hedefler
                                 # aşırı uzak (0=kapalı)
    SWEEP_WINDOW_BARS   = 0      # sweep killzone'un ilk N barında olmalı; geç süpürme
                                 # daha az güvenilir (0=tüm killzone)
    DISPLACEMENT_MIN_ATR = 0.0   # tetik barının gücü ≥ X×ATR (0=kapalı):
                                 #   immediate/retest → reddediş mesafesi (bull: C-L)
                                 #   cisd/fvg_ote/ote → kırılım barı gövdesi |C-O|
    OTE_MIN             = 0.62   # OTE bölgesi alt fib (retracement başlangıcı)
    OTE_MAX             = 0.79   # OTE bölgesi üst fib (SL fib 1.0 = Judas ekstremi)

    def __init__(self, bias_provider=None):
        self.bias             = bias_provider
        self.last_skip_reason: Optional[str] = None
        self.used_fvg_ids: set = set()   # arayüz uyumu
        self._session         = SessionFilter()
        self._last_signal_date: Optional[object] = None   # günlük işlem limiti
        self._st: Optional[dict] = None                   # aktif setup durumu

        # Config'ten oku (yoksa sınıf sabitleri) — hardcoded olmaktan çıkar
        try:
            from config import get_config
            lc = get_config().section('london_reversal')
        except Exception:
            lc = {}
        self.MIN_SWEEP_MULT      = float(lc.get('min_sweep_mult', self.MIN_SWEEP_MULT))
        self.MIN_SWEEP_PTS       = float(lc.get('min_sweep_pts',  self.MIN_SWEEP_PTS))
        self.MAX_SWEEP_DIST_MULT = float(lc.get('max_sweep_mult', self.MAX_SWEEP_DIST_MULT))
        self.ENTRY_MODE          = str(lc.get('entry_mode',  self.ENTRY_MODE))
        self.USE_PDH_PDL         = bool(lc.get('use_pdh_pdl', self.USE_PDH_PDL))
        self.MAX_CISD_BARS       = int(lc.get('max_cisd_bars',  self.MAX_CISD_BARS))
        self.MAX_ENTRY_BARS      = int(lc.get('max_entry_bars', self.MAX_ENTRY_BARS))
        self.FVG_MIN_GAP         = float(lc.get('fvg_min_gap',  self.FVG_MIN_GAP))
        self.REJECTION_CLOSE_PCT = float(lc.get('rejection_close_pct', self.REJECTION_CLOSE_PCT))
        self.WEEKEND_FILTER      = bool(lc.get('weekend_filter', self.WEEKEND_FILTER))
        self.ASIAN_RANGE_MIN_ATR  = float(lc.get('asian_range_min_atr',  self.ASIAN_RANGE_MIN_ATR))
        self.ASIAN_RANGE_MAX_ATR  = float(lc.get('asian_range_max_atr',  self.ASIAN_RANGE_MAX_ATR))
        self.SWEEP_WINDOW_BARS    = int(lc.get('sweep_window_bars',      self.SWEEP_WINDOW_BARS))
        self.DISPLACEMENT_MIN_ATR = float(lc.get('displacement_min_atr', self.DISPLACEMENT_MIN_ATR))
        self.OTE_MIN              = float(lc.get('ote_min', self.OTE_MIN))
        self.OTE_MAX              = float(lc.get('ote_max', self.OTE_MAX))
        # Geriye dönük uyum: eski require_mss bayrağı → cisd_break
        if lc.get('require_mss') and self.ENTRY_MODE == 'immediate':
            self.ENTRY_MODE = 'cisd_break'
        # Geçersiz entry_mode (config typo) → sessizce 0 işlem üretmesin
        if self.ENTRY_MODE not in self.VALID_ENTRY_MODES:
            self.ENTRY_MODE = 'immediate'

        self.stats = dict(no_session=0, no_asian=0, swept=0,
                          cisd=0, signal=0, expired=0,
                          too_deep=0, weak_reject=0, daily_limit=0,
                          range_small=0, range_wide=0, late_sweep=0, weak_disp=0,
                          step1_fail=0, step2_fail=0, step3_fail=0)

    # ── London Killzone: 06:00–09:00 UTC BST / 07:00–10:00 UTC GMT ───────────
    def _is_london_killzone(self, t: datetime) -> bool:
        if self.WEEKEND_FILTER and t.weekday() >= 5:   # Cmt/Paz: gerçek London seansı yok
            return False
        h = t.hour + t.minute / 60.0
        if self._session.is_london_dst(t):
            return 6.0 <= h < 9.0    # BST (yaz): 06:00–09:00 UTC (Frankfurt dahil)
        return 7.0 <= h < 10.0       # GMT (kış): 07:00–10:00 UTC

    def _make_signal(self, idx, TM, direction, extreme, ah, al) -> TradeSignal:
        """Giriş sinyali. TP2 = karşı taraf (runner), TP1 = equilibrium (kısmi)."""
        eq = (ah + al) / 2.0
        return TradeSignal(
            entry_time        = TM[idx],
            direction         = direction,
            trigger_fvg       = None,
            confirmation_type = 'LONDON-REV',
            confidence        = 80.0,
            msb_type          = 'london_' + self.ENTRY_MODE,
            confluence_count  = 1,
            stop_price        = extreme,                 # SL = wick/Judas ekstremi (lookahead yok)
            risk_fraction     = 0.005,
            tp_hint           = (ah if direction == 'bull' else al),  # TP2 = karşı taraf
            tp1_hint          = eq,                      # TP1 = equilibrium (%50)
        )

    def _fire(self, idx, TM, direction, extreme, ah, al, today) -> TradeSignal:
        sig = self._make_signal(idx, TM, direction, extreme, ah, al)
        self.stats['signal'] += 1
        self._last_signal_date = today
        self._st = None
        return sig

    def evaluate(self, idx: int,
                 C: np.ndarray, O: np.ndarray,
                 H: np.ndarray, L: np.ndarray,
                 E100: np.ndarray, E200: np.ndarray,
                 TM: pd.Index,
                 msb_events_bull: List[MSBEvent],
                 msb_events_bear: List[MSBEvent],
                 asian_high: Optional[np.ndarray] = None,
                 asian_low:  Optional[np.ndarray] = None,
                 ATR: Optional[np.ndarray] = None,
                 RSI: Optional[np.ndarray] = None,
                 pdh: Optional[np.ndarray] = None,
                 pdl: Optional[np.ndarray] = None,
                 **_) -> Optional[TradeSignal]:

        self.last_skip_reason = None
        t = to_naive(TM[idx])

        # ── Filtre boru hattı: sweep öncesi gün/bar kapıları ─────────────────
        if asian_high is None or asian_low is None:
            self.last_skip_reason = 'no_asian'
            return None
        ah = float(asian_high[idx])
        al = float(asian_low[idx])
        atr_val = (float(ATR[idx]) if ATR is not None
                   and not np.isnan(float(ATR[idx])) else 2.0)

        skip = self._pass_filters(t, ah, al, atr_val)
        if skip is not None:
            if skip == 'no_session' and self._st is not None:
                self.stats['expired'] += 1     # killzone bitti → bekleyen setup iptal
                self._st = None
            self.last_skip_reason = skip
            return None

        weekly_dir = self.bias.get(t) if self.bias is not None else None

        today = t.date()
        if self._st is not None and self._st['date'] != today:
            self._st = None

        open_c  = float(O[idx])
        close_c = float(C[idx])
        low_c   = float(L[idx])
        high_c  = float(H[idx])

        # ── 1) Stateful modlar: aktif setup'ı ilerlet ────────────────────────
        if self.ENTRY_MODE != 'immediate' and self._st is not None:
            sig = self._progress_setup(idx, TM, H, L, open_c, close_c, low_c,
                                       high_c, ah, al, atr_val, today)
            if sig is not None:
                return sig

        # ── 2) Yeni süpürme tespiti (state A) ────────────────────────────────
        if self._st is None:
            # Killzone alt-penceresi: Judas tipik olarak açılışın ilk saatlerinde
            # gelir; geç süpürmeler daha az güvenilir → ele.
            if self.SWEEP_WINDOW_BARS > 0:
                kz_start = 6.0 if self._session.is_london_dst(t) else 7.0
                bars_in  = int(((t.hour + t.minute / 60.0) - kz_start) * 12 + 0.5)
                if bars_in >= self.SWEEP_WINDOW_BARS:
                    self.stats['late_sweep'] += 1
                    self.last_skip_reason = 'late_sweep'
                    return None

            min_depth = max(self.MIN_SWEEP_PTS, atr_val * self.MIN_SWEEP_MULT)
            max_depth = atr_val * self.MAX_SWEEP_DIST_MULT
            allowed   = (['bull', 'bear'] if self.bias is None else [weekly_dir])
            bar_rng   = max(high_c - low_c, 1e-9)
            # Reddediş kalitesi: sweep barı kendi aralığının uzak ucunda kapanmalı.
            #   bull → kapanış üst %(1-pct)'te | bear → alt %(1-pct)'te.
            rej_bull = (close_c - low_c) / bar_rng >= self.REJECTION_CLOSE_PCT
            rej_bear = (high_c - close_c) / bar_rng >= self.REJECTION_CLOSE_PCT
            # Displacement (immediate/retest): reddediş mesafesi ≥ X×ATR.
            # (CISD modlarında displacement kırılım barında ölçülür.)
            dm = self.DISPLACEMENT_MIN_ATR
            need_disp = dm > 0 and self.ENTRY_MODE in ('immediate', 'retest')
            disp_bull = (not need_disp) or (close_c - low_c)  >= dm * atr_val
            disp_bear = (not need_disp) or (high_c - close_c) >= dm * atr_val

            for direction in allowed:
                if direction == 'bull':
                    levels = [al]
                    if self.USE_PDH_PDL and pdl is not None and not np.isnan(float(pdl[idx])):
                        levels.append(float(pdl[idx]))
                    for lv in levels:
                        depth = lv - low_c
                        if depth > min_depth and close_c > lv:     # aşağı süpürme + içeri kapanış
                            if depth > max_depth:
                                self.stats['too_deep'] += 1
                                self.stats['step2_fail'] += 1
                                continue
                            if not rej_bull:                       # zayıf reddediş → ele
                                self.stats['weak_reject'] += 1
                                continue
                            if not disp_bull:                      # cılız reddediş barı → ele
                                self.stats['weak_disp'] += 1
                                continue
                            self.stats['swept'] += 1
                            if self.ENTRY_MODE == 'immediate':
                                return self._fire(idx, TM, 'bull', low_c, ah, al, today)
                            self._st = dict(dir='bull', sweep_idx=idx, ref=high_c,
                                            judas=low_c, lv=lv, max_d=max_depth,
                                            phase='swept', date=today)
                            break
                    if self._st is not None:
                        break
                else:
                    levels = [ah]
                    if self.USE_PDH_PDL and pdh is not None and not np.isnan(float(pdh[idx])):
                        levels.append(float(pdh[idx]))
                    for lv in levels:
                        depth = high_c - lv
                        if depth > min_depth and close_c < lv:     # yukarı süpürme + içeri kapanış
                            if depth > max_depth:
                                self.stats['too_deep'] += 1
                                self.stats['step2_fail'] += 1
                                continue
                            if not rej_bear:                       # zayıf reddediş → ele
                                self.stats['weak_reject'] += 1
                                continue
                            if not disp_bear:                      # cılız reddediş barı → ele
                                self.stats['weak_disp'] += 1
                                continue
                            self.stats['swept'] += 1
                            if self.ENTRY_MODE == 'immediate':
                                return self._fire(idx, TM, 'bear', high_c, ah, al, today)
                            self._st = dict(dir='bear', sweep_idx=idx, ref=low_c,
                                            judas=high_c, lv=lv, max_d=max_depth,
                                            phase='swept', date=today)
                            break
                    if self._st is not None:
                        break

        self.last_skip_reason = 'no_signal'
        return None

    def _pass_filters(self, t: datetime, ah: float, al: float,
                      atr_val: float) -> Optional[str]:
        """Sweep öncesi filtre boru hattı. Geçmeyen ilk filtrenin adını döner
        (None = tüm filtreler geçti). Sıra:
        killzone (hafta sonu dahil) + tatil → Asya range geçerli →
        Asya range boyutu (ATR-göreli) → bias mevcut → günlük limit."""
        if not self._is_london_killzone(t) or self._session.is_holiday(t):
            return 'no_session'
        if np.isnan(ah) or np.isnan(al) or (ah - al) < 0.5:
            self.stats['no_asian'] += 1
            return 'no_asian'
        # Asya range boyutu yalnızca yeni setup ararken uygulanır (ATR bar bar
        # oynadığı için sınırda bir gün aktif setup'ı iptal ettirmesin).
        if self._st is None:
            rng_atr = (ah - al) / max(atr_val, 1e-9)
            if self.ASIAN_RANGE_MIN_ATR > 0 and rng_atr < self.ASIAN_RANGE_MIN_ATR:
                self.stats['range_small'] += 1
                return 'range_small'
            if self.ASIAN_RANGE_MAX_ATR > 0 and rng_atr > self.ASIAN_RANGE_MAX_ATR:
                self.stats['range_wide'] += 1
                return 'range_wide'
        if self.bias is not None and self.bias.get(t) is None:
            return 'no_bias'
        if self._last_signal_date == t.date():
            self._st = None
            self.stats['daily_limit'] += 1
            return 'daily_limit'
        return None

    def _progress_setup(self, idx, TM, H, L, open_c, close_c, low_c, high_c,
                        ah, al, atr_val, today):
        """Stateful giriş modlarının (cisd_break / fvg_ote / retest / ote)
        state machine'i. Tüm tetikler bar KAPANIŞINDA değerlendirilir; giriş
        O[idx+1] → lookahead yok."""
        s = self._st
        d = s['dir']
        # toplam zaman aşımı
        if (idx - s['sweep_idx']) > (self.MAX_CISD_BARS + self.MAX_ENTRY_BARS):
            self.stats['expired'] += 1
            self._st = None
            return None
        # Judas ekstremini güncelle (SL). Derinleşme max_d'yi aşarsa süpürme
        # değil gerçek breakout'tur → setup iptal.
        if d == 'bull':
            s['judas'] = min(s['judas'], low_c)
            if (s['lv'] - s['judas']) > s['max_d']:
                self.stats['too_deep'] += 1
                self._st = None
                return None
        else:
            s['judas'] = max(s['judas'], high_c)
            if (s['judas'] - s['lv']) > s['max_d']:
                self.stats['too_deep'] += 1
                self._st = None
                return None

        # ── retest: süpürülen seviyeye dönüş (limit-retest yaklaşımı) ────────
        if self.ENTRY_MODE == 'retest':
            if (idx - s['sweep_idx']) > self.MAX_ENTRY_BARS:
                self.stats['expired'] += 1
                self._st = None
                return None
            touch = (low_c <= s['lv']) if d == 'bull' else (high_c >= s['lv'])
            held  = (close_c > s['lv']) if d == 'bull' else (close_c < s['lv'])
            if touch and held:     # seviyeye değdi ve seviyenin doğru tarafında tuttu
                return self._fire(idx, TM, d, s['judas'], ah, al, today)
            return None

        # ── swept → CISD kırılımı (cisd_break / fvg_ote / ote ortak) ─────────
        if s['phase'] == 'swept':
            if (idx - s['sweep_idx']) > self.MAX_CISD_BARS:
                self.stats['expired'] += 1
                self._st = None
                return None
            broke = (close_c > s['ref']) if d == 'bull' else (close_c < s['ref'])
            if not broke:
                return None
            # Displacement: kırılım barı gövdesi ≥ X×ATR (enerjik dönüş şartı);
            # cılızsa setup 'swept'te kalır, daha güçlü kırılım beklenir.
            if self.DISPLACEMENT_MIN_ATR > 0 and \
                    abs(close_c - open_c) < self.DISPLACEMENT_MIN_ATR * atr_val:
                self.stats['weak_disp'] += 1
                return None
            self.stats['cisd'] += 1
            if self.ENTRY_MODE == 'cisd_break':
                return self._fire(idx, TM, d, s['judas'], ah, al, today)
            if self.ENTRY_MODE == 'ote':
                # Dönüş bacağı başlangıcı: Judas ekstremi → kırılım barı ekstremi
                s['leg_ext'] = high_c if d == 'bull' else low_c
                s['phase'] = 'cisd'; s['cisd_idx'] = idx
                return None
            # fvg_ote: CISD displacement bir 5M FVG bıraktı mı?
            #   bull FVG: L[idx] > H[idx-2] → geri çekilme kenarı = L[idx]
            #   bear FVG: H[idx] < L[idx-2] → geri çekilme kenarı = H[idx]
            if idx >= 2:
                if d == 'bull':
                    gap = low_c - float(H[idx - 2])
                    if gap > self.FVG_MIN_GAP:
                        s['fvg_edge'] = low_c
                        s['phase'] = 'cisd'; s['cisd_idx'] = idx
                else:
                    gap = float(L[idx - 2]) - high_c
                    if gap > self.FVG_MIN_GAP:
                        s['fvg_edge'] = high_c
                        s['phase'] = 'cisd'; s['cisd_idx'] = idx
            return None

        # ── cisd → giriş tetiği (fvg_ote: FVG kenarı | ote: %62–79 fib) ─────
        if s['phase'] == 'cisd':
            if (idx - s['cisd_idx']) > self.MAX_ENTRY_BARS:
                self.stats['expired'] += 1
                self._st = None
                return None
            if self.ENTRY_MODE == 'ote':
                # OTE: dönüş bacağının %62–79 geri çekilme bölgesi. Bacak ucu
                # geri çekilme başlayana dek güncellenir (fib canlı çizilir).
                if d == 'bull':
                    s['leg_ext'] = max(s['leg_ext'], high_c)
                    leg  = s['leg_ext'] - s['judas']
                    z62  = s['leg_ext'] - self.OTE_MIN * leg
                    z79  = s['leg_ext'] - self.OTE_MAX * leg
                    if leg > 0 and low_c <= z62 and close_c >= z79:
                        return self._fire(idx, TM, 'bull', s['judas'], ah, al, today)
                else:
                    s['leg_ext'] = min(s['leg_ext'], low_c)
                    leg  = s['judas'] - s['leg_ext']
                    z62  = s['leg_ext'] + self.OTE_MIN * leg
                    z79  = s['leg_ext'] + self.OTE_MAX * leg
                    if leg > 0 and high_c >= z62 and close_c <= z79:
                        return self._fire(idx, TM, 'bear', s['judas'], ah, al, today)
                return None
            # fvg_ote: FVG proksimal kenarına geri çekilme
            if d == 'bull' and low_c <= s['fvg_edge']:
                return self._fire(idx, TM, 'bull', s['judas'], ah, al, today)
            if d == 'bear' and high_c >= s['fvg_edge']:
                return self._fire(idx, TM, 'bear', s['judas'], ah, al, today)
        return None


class LondonBacktestEngine(BacktestEngine):
    """
    LondonReversalBrain için özel engine.
    Asya range dizilerini hesaplar → brain.evaluate()'a iletir.
    TP1 = Asya equilibrium (%50, kısmi kâr) | TP2 = Asya karşı taraf (runner).
    TP2'ye göre RR < MIN_RR → işlem reddedilir.
    """

    MIN_RR       = 1.5    # TP2'ye min RR (kısmi banking expectancy'yi düzeltir)
    TP1_FRACTION = 0.5    # equilibrium'da kapatılan oran

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rr_reject_count = 0   # yetersiz RR nedeniyle reddedilen işlem sayısı
        try:
            from config import get_config
            lc = get_config().section('london_reversal')
        except Exception:
            lc = {}
        self.MIN_RR        = float(lc.get('min_rr',        self.MIN_RR))
        self.TP1_FRACTION  = float(lc.get('tp1_fraction',  self.TP1_FRACTION))
        self.ASIAN_START   = int(lc.get('asian_start_utc', 23))
        self.ASIAN_END     = int(lc.get('asian_end_utc',   6))
        self.USE_PDH_PDL   = bool(lc.get('use_pdh_pdl',    True))

    def run(self, df_1h: pd.DataFrame, df_5m: pd.DataFrame,
            backtest_start: datetime) -> List[Trade]:
        ASIAN_H, ASIAN_L = AsianRangeCalculator.compute(
            df_5m, self.ASIAN_START, self.ASIAN_END)
        kw = {'asian_high': ASIAN_H, 'asian_low': ASIAN_L}
        if self.USE_PDH_PDL:
            PDH, PDL = AsianRangeCalculator.compute_pdhl(df_5m)
            kw['pdh'] = PDH; kw['pdl'] = PDL
        self._extra_brain_kwargs = kw
        result = super().run(df_1h, df_5m, backtest_start)
        self._extra_brain_kwargs = {}
        return result

    def _make_entry_trade(self, signal: TradeSignal, idx: int,
                          O: np.ndarray, equity: float, trade_id: int,
                          fvg1_bull=None, fvg1_bear=None,
                          mit1_bull=None, mit1_bear=None,
                          fvg1_eng=None,
                          H1=None, L1=None, ATR1=None,
                          T1: Optional[np.ndarray] = None) -> Optional[Trade]:
        if signal.tp_hint == 0.0:
            return super()._make_entry_trade(
                signal, idx, O, equity, trade_id,
                fvg1_bull=fvg1_bull, fvg1_bear=fvg1_bear,
                mit1_bull=mit1_bull, mit1_bear=mit1_bear,
                fvg1_eng=fvg1_eng, H1=H1, L1=L1, ATR1=ATR1, T1=T1,
            )

        entry     = float(O[idx + 1])
        direction = signal.direction
        buf       = self.risk.sl_buffer

        # ICT Judas Swing TP kuralı:
        #   TP2 = Asya range karşı sınırı (runner, değişmez likidite hedefi)
        #   TP1 = Asya equilibrium (%50) — geçerliyse kısmi kâr + SL → BE
        #   RR(TP2) < MIN_RR → işlemi reddet
        tp2 = signal.tp_hint    # bull: Asya yüksek; bear: Asya düşük
        eq  = signal.tp1_hint   # equilibrium (%50)

        if direction == 'bull':
            sl_raw    = signal.stop_price * (1.0 - buf)
            risk_per  = max(entry - sl_raw, 0.01)
            actual_rr = (tp2 - entry) / risk_per
            # TP1 yalnızca giriş equilibrium'un altındaysa (önünde) geçerli
            tp1 = eq if (eq > entry and eq < tp2) else None
            geom_ok = entry > sl_raw + 0.01     # giriş SL'nin doğru tarafında olmalı
        else:
            sl_raw    = signal.stop_price * (1.0 + buf)
            risk_per  = max(sl_raw - entry, 0.01)
            actual_rr = (entry - tp2) / risk_per
            tp1 = eq if (eq < entry and eq > tp2) else None
            geom_ok = entry < sl_raw - 0.01

        if not geom_ok:                          # açılış SL'ye gap'lendi → geçersiz
            if hasattr(self.brain, '_last_signal_date'):
                self.brain._last_signal_date = None   # gün limitini geri ver
            return None

        if actual_rr < self.MIN_RR:
            self.rr_reject_count += 1
            # Gün limitini geri ver: sinyal işleme dönüşmedi, aynı gün yeni
            # bir sweep/setup tekrar değerlendirilebilsin.
            if hasattr(self.brain, '_last_signal_date'):
                self.brain._last_signal_date = None
            return None   # TP2 yetersiz RR → işlem açılmaz

        r = self.risk.compute(direction, entry, signal.stop_price, equity,
                              signal.risk_fraction, tp_override=tp2)
        if r is None:
            return None
        return Trade(
            trade_id      = trade_id,
            signal        = signal,
            entry_price   = round(entry, 2),
            sl            = r['sl'],
            tp            = r['tp'],
            risk          = r['risk'],
            risk_pct      = r['risk_pct'],
            risk_dollar   = r['risk_dollar'],
            rr            = actual_rr,
            risk_fraction = r['risk_fraction'],
            entry_bar_idx = idx,
            tp1           = (round(tp1, 2) if tp1 is not None else None),
            tp1_fraction  = self.TP1_FRACTION,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# BÖLÜM 14: QWE — Fib Retracement Pullback (BOS + HH + Golden Zone + Hacim onayı)
# ═══════════════════════════════════════════════════════════════════════════════

class FibonacciEngine:
    """
    Fibonacci retracement / extension motoru — bacak bazlı, yön farkındalıklı.

    Konvansiyon: bacak (lo, hi) mutlak fiyattır. 'bull' bacak yukarı hareketi
    temsil eder (dip lo → tepe hi); retracement TEPEDEN geriye ölçülür:
        R(f) = hi − f·(hi−lo)   (bull)   |   R(f) = lo + f·(hi−lo)   (bear)
    Extension hedefi hareketin ötesidir:
        E(f) = hi + f·(hi−lo)   (bull)   |   E(f) = lo − f·(hi−lo)   (bear)

    GOLDEN_ZONE = (0.618, 0.786): "dengeli geri çekilme" bölgesi (OTE eşdeğeri).
    Salt aritmetik → durum yok, lookahead riski yok. Tüm stratejilerce
    yeniden kullanılabilir.
    """

    RETRACEMENTS = (0.236, 0.382, 0.5, 0.618, 0.705, 0.786, 0.886, 1.0, 1.13)
    EXTENSIONS   = (0.272, 0.618, 1.0, 1.618)
    GOLDEN_ZONE  = (0.618, 0.786)

    @staticmethod
    def retracement(lo: float, hi: float, ratio: float,
                    direction: str = 'bull') -> float:
        leg = hi - lo
        return hi - ratio * leg if direction == 'bull' else lo + ratio * leg

    @staticmethod
    def extension(lo: float, hi: float, ratio: float,
                  direction: str = 'bull') -> float:
        leg = hi - lo
        return hi + ratio * leg if direction == 'bull' else lo - ratio * leg

    @staticmethod
    def levels(lo: float, hi: float, direction: str = 'bull',
               ratios: Optional[tuple] = None) -> Dict[float, float]:
        """Oran → fiyat sözlüğü (varsayılan: standart retracement seti)."""
        rs = ratios if ratios is not None else FibonacciEngine.RETRACEMENTS
        return {r: FibonacciEngine.retracement(lo, hi, r, direction) for r in rs}

    @staticmethod
    def zone(lo: float, hi: float, direction: str = 'bull',
             z: Optional[tuple] = None) -> tuple:
        """(alt, üst) fiyat bandı — varsayılan Golden Zone (0.618–0.786)."""
        z0, z1 = z if z is not None else FibonacciEngine.GOLDEN_ZONE
        a = FibonacciEngine.retracement(lo, hi, z0, direction)
        b = FibonacciEngine.retracement(lo, hi, z1, direction)
        return (min(a, b), max(a, b))

    @staticmethod
    def position(price: float, lo: float, hi: float,
                 direction: str = 'bull') -> float:
        """Fiyatın bacak içindeki retracement oranı (0 = hareket ucu, 1 = başlangıç)."""
        leg = max(hi - lo, 1e-9)
        return (hi - price) / leg if direction == 'bull' else (price - lo) / leg


class VolumeEngine:
    """
    Hacim analitiği motoru — lookahead-safe.

    Tüm referans ölçüleri YALNIZCA önceki barların hacmini kullanır (shift 1).
    Medyan bazlı RVOL tercih edilir: haber spike'ları ortalamayı bozar,
    medyanı bozamaz.

      • rolling_median_prior : önceki `window` barın medyan hacmi
      • rel_volume           : v / medyan  (RVOL; NaN-güvenli)
      • is_low_volume        : düşük hacimli retest onayı (v ≤ ratio × medyan)
      • is_high_volume       : yüksek hacimli base/kırılım tespiti
      • block_sum            : 5M hacmi zaman bloklarına toplar (üst TF mumu)
    """

    @staticmethod
    def rolling_median_prior(vol: np.ndarray, window: int = 48) -> np.ndarray:
        return pd.Series(vol).rolling(window).median().shift(1).values

    @staticmethod
    def rel_volume(vol: np.ndarray, window: int = 48) -> np.ndarray:
        med = VolumeEngine.rolling_median_prior(vol, window)
        with np.errstate(divide='ignore', invalid='ignore'):
            rv = np.where(np.nan_to_num(med) > 0, vol / med, np.nan)
        return rv

    @staticmethod
    def is_low_volume(v: float, med: float, ratio: float) -> bool:
        """True → hacim referansın ratio katının ALTINDA (zayıf karşı baskı)."""
        return (not np.isnan(med)) and med > 0 and v <= ratio * med

    @staticmethod
    def is_high_volume(v: float, med: float, ratio: float = 1.5) -> bool:
        return (not np.isnan(med)) and med > 0 and v >= ratio * med


class QweSwingEngine:
    """
    QWE için 1H/4H yapı tespiti. TÜM tespitler doğrulama-gecikmeli:
    bir swing/blok ancak gelecekteki k bar / blok kapandıktan sonra "bilinir"
    (confirm index) → lookahead yok.
    """

    @staticmethod
    def find_swings(H: np.ndarray, L: np.ndarray, k: int = 2) -> List[tuple]:
        """Fractal swing noktaları: (bar, fiyat, 'H'|'L', confirm_bar).
        H[i] ±k penceresinin TEK maksimumu ise swing high (low ayna);
        confirm_bar = i + k (bu bar kapanmadan swing bilinemez)."""
        n = len(H)
        out = []
        for i in range(k, n - k):
            wh = H[i - k:i + k + 1]
            if H[i] >= wh.max() and (wh == H[i]).sum() == 1:
                out.append((i, float(H[i]), 'H', i + k))
            wl = L[i - k:i + k + 1]
            if L[i] <= wl.min() and (wl == L[i]).sum() == 1:
                out.append((i, float(L[i]), 'L', i + k))
        return out

    @staticmethod
    def detect_setups(df: pd.DataFrame, k: int = 2,
                      min_leg_atr: float = 1.5, max_age: int = 48,
                      bar_minutes: int = 60) -> List[dict]:
        """
        Impulsive Move setup'ları (bull; bear ayna) — TF-bağımsız (1H/4H yapı):
          yapı → BOS (kapanış son doğrulanmış swing high'ı aşar) →
          BOS sonrası tepe swing high (HH) doğrulanır → bacak = dip → HH.
        "Impulsive" şartı: bacak ≥ min_leg_atr × ATR14 (aynı TF).
        Dönen setup: dict(dir, lo, hi, avail_ts, expire_ts) — avail_ts = HH'i
        doğrulayan barın KAPANIŞ zamanı (ns epoch); o andan önce setup hiçbir
        alt-TF bara görünmez (lookahead koruması zaman damgasıyla).
        """
        H = df['High'].values.astype(float)
        L = df['Low'].values.astype(float)
        C = df['Close'].values.astype(float)
        n = len(C)
        ts = pd.to_datetime(df.index)
        if ts.tz is not None:
            ts = ts.tz_localize(None)
        t_i8 = ts.values.astype('datetime64[ns]').astype(np.int64)
        BAR_NS = bar_minutes * 60 * 1_000_000_000
        tr = np.maximum(H[1:] - L[1:],
                        np.maximum(np.abs(H[1:] - C[:-1]), np.abs(L[1:] - C[:-1])))
        atr = pd.Series(np.r_[np.nan, tr]).rolling(14).mean().shift(1).values

        by_confirm = sorted(QweSwingEngine.find_swings(H, L, k),
                            key=lambda s: (s[3], s[0]))
        ptr = 0
        last_sh = None    # (bar, fiyat) — son DOĞRULANMIŞ yapı swing high'ı
        last_sl = None
        pend_bull = None  # BOS oldu, HH swing onayı bekleniyor
        pend_bear = None
        setups: List[dict] = []

        for i in range(n):
            # bar i kapandı → bu barla doğrulanan swingleri işle
            while ptr < len(by_confirm) and by_confirm[ptr][3] <= i:
                b, px, typ, cf = by_confirm[ptr]; ptr += 1
                if typ == 'H':
                    if (pend_bull is not None and b > pend_bull['bos_from']
                            and px > pend_bull['broken']):
                        lo_px = float(L[pend_bull['lo_bar']:b + 1].min())
                        leg = px - lo_px
                        a = atr[cf] if cf < n else np.nan
                        if not np.isnan(a) and leg >= min_leg_atr * a:
                            av = t_i8[cf] + BAR_NS      # onay barının kapanış anı
                            setups.append(dict(dir='bull', lo=lo_px, hi=px,
                                               avail_ts=av,
                                               expire_ts=av + max_age * BAR_NS))
                        pend_bull = None
                    last_sh = (b, px)
                else:
                    if (pend_bear is not None and b > pend_bear['bos_from']
                            and px < pend_bear['broken']):
                        hi_px = float(H[pend_bear['hi_bar']:b + 1].max())
                        leg = hi_px - px
                        a = atr[cf] if cf < n else np.nan
                        if not np.isnan(a) and leg >= min_leg_atr * a:
                            av = t_i8[cf] + BAR_NS
                            setups.append(dict(dir='bear', lo=px, hi=hi_px,
                                               avail_ts=av,
                                               expire_ts=av + max_age * BAR_NS))
                        pend_bear = None
                    last_sl = (b, px)

            # bar i kapanışında BOS kontrolü (yalnızca doğrulanmış yapıya karşı)
            if pend_bull is None:
                if last_sh is not None and last_sl is not None and C[i] > last_sh[1]:
                    pend_bull = dict(bos_from=i, broken=last_sh[1],
                                     lo_bar=last_sl[0], lo_px=last_sl[1])
            elif C[i] < pend_bull['lo_px']:
                pend_bull = None            # yapı çöktü → BOS geçersiz
            if pend_bear is None:
                if last_sh is not None and last_sl is not None and C[i] < last_sl[1]:
                    pend_bear = dict(bos_from=i, broken=last_sl[1],
                                     hi_bar=last_sh[0], hi_px=last_sh[1])
            elif C[i] > pend_bear['hi_px']:
                pend_bear = None

        setups.sort(key=lambda s: s['avail_ts'])
        return setups

    @staticmethod
    def compute_4h_context(df_1h: pd.DataFrame, ema_fast: int = 20,
                           ema_slow: int = 50, k: int = 2):
        """
        4H bağlam (görsel: 4H = Direction + Key Levels).
        Dönen: (block_starts[int64], dir_by_block, liq_levels)
          dir_by_block[j] = j. blok İÇİNDEKİ kararlar için yön — yalnızca j-1'e
          kadar KAPANMIŞ blokların EMA'sından ('bull'|'bear'|'none').
          liq_levels = [(fiyat, avail_block)] — 4H fractal swing seviyeleri;
          avail_block'tan önceki bloklarda görünmez.
        """
        ts = pd.to_datetime(df_1h.index)
        if ts.tz is not None:
            ts = ts.tz_localize(None)
        blocks = ts.floor('4h')
        g = df_1h.groupby(blocks.values).agg(
            H=('High', 'max'), L=('Low', 'min'), Cl=('Close', 'last'))
        bh = g['H'].values.astype(float)
        bl = g['L'].values.astype(float)
        bc = g['Cl'].values.astype(float)
        m = len(bc)
        ef = pd.Series(bc).ewm(span=ema_fast, adjust=False).mean().values
        es = pd.Series(bc).ewm(span=ema_slow, adjust=False).mean().values
        dirb = np.array(['none'] * m, dtype=object)
        for j in range(1, m):
            if j >= ema_slow:               # ısınma bitmeden yön verme
                dirb[j] = 'bull' if ef[j - 1] > es[j - 1] else 'bear'
        liq = [(px, cf + 1) for (b, px, typ, cf)
               in QweSwingEngine.find_swings(bh, bl, k)]
        # KRİTİK: ns'e normalize et. asi8 saniye-çözünürlüklü index'te saniye
        # döndürür; q_t5 (ns) ile searchsorted karşılaştırması bozulur ve her
        # bar SON bloğa eşlenirdi → 4H yön filtresi geleceği görürdü.
        block_starts = (pd.DatetimeIndex(g.index).values
                        .astype('datetime64[ns]').astype(np.int64))
        return block_starts, dirb, liq


class QweBrain:
    """
    QWE — paylaşılan işlem mantığı: Impulsive Move (BOS+HH) → fib geri çekilme
    kademesine düşük hacimli, güçlü reddedişli onay mumu → giriş.

    Kademeler (config entry_level):
      '382' Impulsive Move  → SL 61.8%   | '618' Golden Zone      → SL 88.6%
      '786' Institutional   → SL 113%    | '886' Stop Hunt LVL    → SL 113%

    Onay katmanları (görsel 5-6): **15M onay mumu** (trader'ın küçük-TF onayı) —
    reddediş close-pos + kapanış giriş seviyesinin doğru tarafında ("zone held")
    + opsiyonel düşük-hacim retest'i (VolumeEngine, 15M blok hacmi) + opsiyonel
    4H yön ve 4H likidite çakışması. Fib matematiği FibonacciEngine'dendir.
    TP1 = HH (kısmi + BE), TP2 = bacağın -%27.2 uzantısı (runner).

    Lookahead: setup HH doğrulama 1H barı kapanmadan görünmez; onay yalnızca
    bir 15M bloğu KAPATAN 5M barın kapanışında değerlendirilir (15M mumu o anda
    tamamlanmıştır); giriş bir sonraki 5M barın açılışında (= 15M kapanış anı).
    """

    FIB_ENTRY = {'382': 0.382, '618': 0.618, '786': 0.786, '886': 0.886}
    FIB_SL    = {'382': 0.618, '618': 0.886, '786': 1.13,  '886': 1.13}

    ENTRY_LEVEL          = '618'
    TP_EXT               = 0.272
    REJECTION_CLOSE_PCT  = 0.60
    MAX_RETEST_VOL_RATIO = 0.0    # bar hacmi ≤ X × rolling-medyan (0=kapalı)
    REQUIRE_4H_LIQ       = False  # giriş seviyesi bir 4H swing seviyesine yakın olmalı
    USE_4H_DIR           = True   # setup yönü 4H EMA yönüyle aynı olmalı
    LIQ_TOL_ATR          = 3.0    # 4H LIQ yakınlık toleransı (× 5M ATR)
    DAILY_LIMIT          = 2
    WEEKEND_FILTER       = True

    def __init__(self, bias_provider=None):
        self.bias = bias_provider
        self.last_skip_reason: Optional[str] = None
        self.used_fvg_ids: set = set()                       # arayüz uyumu
        self.pending: Dict[str, List[dict]] = {'bull': [], 'bear': []}
        try:
            from config import get_config
            qc = get_config().section('qwe')
        except Exception:
            qc = {}
        self.ENTRY_LEVEL          = str(qc.get('entry_level', self.ENTRY_LEVEL))
        if self.ENTRY_LEVEL not in self.FIB_ENTRY:
            self.ENTRY_LEVEL = '618'
        self.TP_EXT               = float(qc.get('tp_ext', self.TP_EXT))
        self.REJECTION_CLOSE_PCT  = float(qc.get('rejection_close_pct', self.REJECTION_CLOSE_PCT))
        self.MAX_RETEST_VOL_RATIO = float(qc.get('max_retest_vol_ratio', self.MAX_RETEST_VOL_RATIO))
        self.REQUIRE_4H_LIQ       = bool(qc.get('require_4h_liq', self.REQUIRE_4H_LIQ))
        self.USE_4H_DIR           = bool(qc.get('use_4h_dir', self.USE_4H_DIR))
        self.LIQ_TOL_ATR          = float(qc.get('liq_tol_atr', self.LIQ_TOL_ATR))
        self.DAILY_LIMIT          = int(qc.get('daily_limit', self.DAILY_LIMIT))
        self.WEEKEND_FILTER       = bool(qc.get('weekend_filter', self.WEEKEND_FILTER))

        self._ptr = 0                     # sıradaki aktive edilecek setup
        self._active: List[dict] = []
        self._date_count: Dict[object, int] = {}
        self._last_today = None
        self.last_setup_key: Optional[tuple] = None   # son sinyalin setup kimliği
        self._used_keys: set = set()                  # dışarıdan işaretlenen setup'lar
        self.stats = dict(setups_seen=0, touched=0, weak_reject=0, high_vol=0,
                          no_liq=0, wrong_4h=0, wrong_bias=0, invalidated=0,
                          expired=0, daily_limit=0, signal=0,
                          step1_fail=0, step2_fail=0, step3_fail=0)

    def _refund_daily(self):
        """MIN_RR reddi gün limitini tüketmesin (sinyal işleme dönüşmedi)."""
        if self._last_today is not None and self._date_count.get(self._last_today, 0) > 0:
            self._date_count[self._last_today] -= 1

    @staticmethod
    def setup_key(s: dict) -> tuple:
        """Setup'ın kalıcı kimliği (canlı state persistence için)."""
        return (s['dir'], round(float(s['lo']), 2),
                round(float(s['hi']), 2), int(s['avail_ts']))

    def mark_used(self, keys) -> None:
        """Canlı trader: tick'ler/yeniden başlatmalar arası çifte-giriş koruması.
        Verilen anahtarlarla eşleşen setup'lar (aktif veya ileride aktive
        olacak) kullanılmış sayılır."""
        self._used_keys.update(tuple(k) for k in keys)
        for s in self._active:
            if self.setup_key(s) in self._used_keys:
                s['used'] = True

    def evaluate(self, idx: int,
                 C: np.ndarray, O: np.ndarray,
                 H: np.ndarray, L: np.ndarray,
                 E100: np.ndarray, E200: np.ndarray,
                 TM: pd.Index,
                 msb_events_bull: List[MSBEvent],
                 msb_events_bear: List[MSBEvent],
                 ATR: Optional[np.ndarray] = None,
                 qwe_setups: Optional[List[dict]] = None,
                 q_t5: Optional[np.ndarray] = None,
                 q_block: Optional[np.ndarray] = None,
                 q_dir4=None, q_liq=None,
                 q15_close: Optional[np.ndarray] = None,
                 q15_O: Optional[np.ndarray] = None,
                 q15_H: Optional[np.ndarray] = None,
                 q15_L: Optional[np.ndarray] = None,
                 q15_V: Optional[np.ndarray] = None,
                 q15_volmed: Optional[np.ndarray] = None,
                 **_) -> Optional[TradeSignal]:

        self.last_skip_reason = None
        if qwe_setups is None or q_t5 is None or q15_close is None:
            self.last_skip_reason = 'no_signal'
            return None
        # Onay TF'i: yalnızca bir 15M bloğu kapatan 5M barında karar verilir
        if not q15_close[idx]:
            self.last_skip_reason = 'no_signal'
            return None
        t   = to_naive(TM[idx])
        now = int(q_t5[idx])              # bu 5M barın BAŞLANGIÇ anı (ns epoch)

        # ── Yeni doğrulanan setup'ları aktive et (avail_ts = yapı barının
        #    kapanış anı; ondan önceki hiçbir bar setup'ı göremez) ───────────
        while self._ptr < len(qwe_setups) and qwe_setups[self._ptr]['avail_ts'] <= now:
            s_new = dict(qwe_setups[self._ptr])
            if self._used_keys and self.setup_key(s_new) in self._used_keys:
                s_new['used'] = True     # daha önce işlem görmüş (canlı state)
            self._active.append(s_new)
            self._ptr += 1
            self.stats['setups_seen'] += 1

        # Tamamlanmış 15M onay mumu (blok içi kümülatif diziler bu barda tam mumdur)
        close_c = float(C[idx])
        low_c   = float(q15_L[idx])
        high_c  = float(q15_H[idx])
        fe = self.FIB_ENTRY[self.ENTRY_LEVEL]
        fs = self.FIB_SL[self.ENTRY_LEVEL]

        # ── Bakım: süre dolumu + SL seviyesinin kapanışla ihlali ────────────
        keep = []
        for s in self._active:
            if s['expire_ts'] <= now:
                self.stats['expired'] += 1
                continue
            slp = FibonacciEngine.retracement(s['lo'], s['hi'], fs, s['dir'])
            if (s['dir'] == 'bull' and close_c < slp) or \
               (s['dir'] == 'bear' and close_c > slp):
                self.stats['invalidated'] += 1
                continue
            keep.append(s)
        self._active = keep
        if not self._active:
            self.last_skip_reason = 'no_signal'
            return None

        # ── Filtre boru hattı ────────────────────────────────────────────────
        if self.WEEKEND_FILTER and t.weekday() >= 5:
            self.last_skip_reason = 'no_session'
            return None
        today = t.date()
        if self._date_count.get(today, 0) >= self.DAILY_LIMIT:
            self.stats['daily_limit'] += 1
            self.last_skip_reason = 'daily_limit'
            return None
        wdir = self.bias.get(t) if self.bias is not None else None
        if self.bias is not None and wdir is None:
            self.last_skip_reason = 'no_bias'
            return None
        atr_val = (float(ATR[idx]) if ATR is not None
                   and not np.isnan(float(ATR[idx])) else 2.0)
        blk = int(q_block[idx]) if q_block is not None else -1
        bar_rng = max(high_c - low_c, 1e-9)

        # ── Giriş tetiği: kademe seviyesine dokunuş + onay mumu ─────────────
        for s in self._active:
            if s.get('used'):
                continue
            d   = s['dir']
            lvl = FibonacciEngine.retracement(s['lo'], s['hi'], fe, d)
            slp = FibonacciEngine.retracement(s['lo'], s['hi'], fs, d)
            if d == 'bull':
                touched = low_c <= lvl
                rej  = (close_c - low_c) / bar_rng >= self.REJECTION_CLOSE_PCT
                held = close_c > lvl              # bölge tuttu: kapanış seviyenin üstünde
            else:
                touched = high_c >= lvl
                rej  = (high_c - close_c) / bar_rng >= self.REJECTION_CLOSE_PCT
                held = close_c < lvl
            if not touched:
                continue
            self.stats['touched'] += 1
            if wdir is not None and d != wdir:
                self.stats['wrong_bias'] += 1
                continue
            if self.USE_4H_DIR and q_dir4 is not None and blk >= 0 \
                    and q_dir4[blk] != d:
                self.stats['wrong_4h'] += 1
                continue
            if not (rej and held):                # onay mumu yok
                self.stats['weak_reject'] += 1
                continue
            if self.MAX_RETEST_VOL_RATIO > 0 and q15_V is not None \
                    and q15_volmed is not None:
                if not VolumeEngine.is_low_volume(float(q15_V[idx]),
                                                  float(q15_volmed[idx]),
                                                  self.MAX_RETEST_VOL_RATIO):
                    self.stats['high_vol'] += 1   # yüksek hacimli retest → karşı baskı
                    continue
            if self.REQUIRE_4H_LIQ and q_liq:
                tol = self.LIQ_TOL_ATR * atr_val
                if not any(abs(lvl - px) <= tol
                           for (px, ab) in q_liq if ab <= blk):
                    self.stats['no_liq'] += 1
                    continue

            # ── SİNYAL ───────────────────────────────────────────────────────
            s['used'] = True
            self.last_setup_key = self.setup_key(s)
            self._date_count[today] = self._date_count.get(today, 0) + 1
            self._last_today = today
            self.stats['signal'] += 1
            tp2 = FibonacciEngine.extension(s['lo'], s['hi'], self.TP_EXT, d)
            tp1 = s['hi'] if d == 'bull' else s['lo']   # HH/LL (fib 0.0)
            return TradeSignal(
                entry_time        = TM[idx],
                direction         = d,
                trigger_fvg       = None,
                confirmation_type = 'QWE',
                confidence        = 75.0,
                msb_type          = 'qwe_' + self.ENTRY_LEVEL,
                confluence_count  = 1,
                stop_price        = slp,          # kademenin fib SL seviyesi
                risk_fraction     = 0.005,
                tp_hint           = tp2,          # TP2 = -%27.2 uzantı (runner)
                tp1_hint          = tp1,          # TP1 = HH (kısmi kâr + BE)
            )

        self.last_skip_reason = 'no_signal'
        return None


class QweBacktestEngine(BacktestEngine):
    """
    QweBrain için engine: 1H setup'ları, 4H bağlamı ve 5M hacim dizilerini
    hesaplayıp brain'e iletir. TP1 (HH, kısmi) + TP2 (uzantı, runner) ve
    MIN_RR kapısı LondonBacktestEngine ile aynı desendedir.
    """

    MIN_RR       = 1.5
    TP1_FRACTION = 0.5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rr_reject_count = 0
        try:
            from config import get_config
            qc = get_config().section('qwe')
        except Exception:
            qc = {}
        self.MIN_RR         = float(qc.get('min_rr',        self.MIN_RR))
        self.TP1_FRACTION   = float(qc.get('tp1_fraction',  self.TP1_FRACTION))
        self.SWING_K        = int(qc.get('swing_k',         2))
        self.MIN_LEG_ATR    = float(qc.get('min_leg_atr',   1.5))
        self.MAX_SETUP_AGE  = int(qc.get('max_setup_age',   48))
        self.EMA4H_FAST     = int(qc.get('ema4h_fast',      20))
        self.EMA4H_SLOW     = int(qc.get('ema4h_slow',      50))
        self.STRUCTURE_TF   = str(qc.get('structure_tf',    '1h')).lower()
        if self.STRUCTURE_TF not in ('1h', '4h'):
            self.STRUCTURE_TF = '1h'
        self.CONFIRM_TF_MIN = int(qc.get('confirm_tf_min',  15))
        self.VOL_MED_WINDOW = int(qc.get('vol_med_window',  48))

    @staticmethod
    def _naive_i8(index) -> np.ndarray:
        """Index'i tz'siz ns-epoch int64'e çevirir. Birim normalize edilir:
        pandas 2.x saniye-çözünürlüklü index'lerde asi8 saniye döndürür ve
        farklı kaynaklı index'ler karışırsa searchsorted sessizce bozulur."""
        ts = pd.to_datetime(index)
        if ts.tz is not None:
            ts = ts.tz_localize(None)
        return ts.values.astype('datetime64[ns]').astype(np.int64)

    @classmethod
    def prepare_kwargs(cls, df_1h: pd.DataFrame, df_5m: pd.DataFrame, *,
                       structure_tf: str = '1h', swing_k: int = 2,
                       min_leg_atr: float = 1.5, max_setup_age: int = 48,
                       ema_fast: int = 20, ema_slow: int = 50,
                       confirm_tf_min: int = 15,
                       vol_med_window: int = 48) -> dict:
        """QweBrain.evaluate() bağlam dizilerini üretir. Backtest ve CANLI
        trader AYNI fonksiyonu kullanır → tek implementasyon, drift yok."""
        # ── Yapı TF'i: 1H (intraday-swing) veya 4H (haftalık swing) ─────────
        if str(structure_tf).lower() == '4h':
            ts1 = pd.to_datetime(df_1h.index)
            if ts1.tz is not None:
                ts1 = ts1.tz_localize(None)
            df_struct = df_1h.groupby(ts1.floor('4h')).agg(
                {'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'})
            bar_minutes = 240
        else:
            df_struct = df_1h
            bar_minutes = 60
        setups = QweSwingEngine.detect_setups(
            df_struct, k=swing_k, min_leg_atr=min_leg_atr,
            max_age=max_setup_age, bar_minutes=bar_minutes)

        blk_starts, dir4, liq = QweSwingEngine.compute_4h_context(
            df_1h, ema_fast=ema_fast, ema_slow=ema_slow, k=swing_k)

        t5 = cls._naive_i8(df_5m.index)
        q_block = np.searchsorted(blk_starts, t5, side='right') - 1

        # ── Onay TF mumu (varsayılan 15M): blok içi kümülatif OHLCV —
        #    bloğu KAPATAN 5M barında diziler tamamlanmış onay mumunu verir ──
        ts5 = pd.to_datetime(df_5m.index)
        if ts5.tz is not None:
            ts5 = ts5.tz_localize(None)
        blk15 = ts5.floor(f'{confirm_tf_min}min')
        b15 = blk15.values.astype('datetime64[ns]').astype(np.int64)
        q15_close = np.r_[b15[1:] != b15[:-1], True]
        vol5 = (df_5m['Volume'].values.astype(float)
                if 'Volume' in df_5m.columns else np.zeros(len(df_5m)))
        g = pd.DataFrame({'O': df_5m['Open'].values.astype(float),
                          'H': df_5m['High'].values.astype(float),
                          'L': df_5m['Low'].values.astype(float),
                          'V': vol5}, index=blk15).groupby(level=0)
        q15_O = g['O'].transform('first').values
        q15_H = g['H'].cummax().values
        q15_L = g['L'].cummin().values
        q15_V = g['V'].cumsum().values
        # 15M blok hacim medyanı: önceki `vol_med_window` TAMAMLANMIŞ blok
        v15 = g['V'].sum()
        med15 = VolumeEngine.rolling_median_prior(v15.values, vol_med_window)
        blkpos = np.searchsorted(
            v15.index.values.astype('datetime64[ns]').astype(np.int64), b15)
        q15_volmed = med15[blkpos]

        return dict(
            qwe_setups=setups, q_t5=t5, q_block=q_block,
            q_dir4=dir4, q_liq=liq,
            q15_close=q15_close, q15_O=q15_O, q15_H=q15_H, q15_L=q15_L,
            q15_V=q15_V, q15_volmed=q15_volmed)

    def run(self, df_1h: pd.DataFrame, df_5m: pd.DataFrame,
            backtest_start: datetime) -> List[Trade]:
        self._extra_brain_kwargs = self.prepare_kwargs(
            df_1h, df_5m,
            structure_tf=self.STRUCTURE_TF, swing_k=self.SWING_K,
            min_leg_atr=self.MIN_LEG_ATR, max_setup_age=self.MAX_SETUP_AGE,
            ema_fast=self.EMA4H_FAST, ema_slow=self.EMA4H_SLOW,
            confirm_tf_min=self.CONFIRM_TF_MIN,
            vol_med_window=self.VOL_MED_WINDOW)
        try:
            return super().run(df_1h, df_5m, backtest_start)
        finally:
            self._extra_brain_kwargs = {}

    def _make_entry_trade(self, signal: TradeSignal, idx: int,
                          O: np.ndarray, equity: float, trade_id: int,
                          fvg1_bull=None, fvg1_bear=None,
                          mit1_bull=None, mit1_bear=None,
                          fvg1_eng=None,
                          H1=None, L1=None, ATR1=None,
                          T1: Optional[np.ndarray] = None) -> Optional[Trade]:
        if signal.tp_hint == 0.0:
            return super()._make_entry_trade(
                signal, idx, O, equity, trade_id,
                fvg1_bull=fvg1_bull, fvg1_bear=fvg1_bear,
                mit1_bull=mit1_bull, mit1_bear=mit1_bear,
                fvg1_eng=fvg1_eng, H1=H1, L1=L1, ATR1=ATR1, T1=T1,
            )

        entry     = float(O[idx + 1])
        direction = signal.direction
        buf       = self.risk.sl_buffer
        tp2       = signal.tp_hint        # bacak uzantısı (runner)
        hh        = signal.tp1_hint       # HH/LL (kısmi kâr)

        if direction == 'bull':
            sl_raw    = signal.stop_price * (1.0 - buf)
            risk_per  = max(entry - sl_raw, 0.01)
            actual_rr = (tp2 - entry) / risk_per
            tp1 = hh if (hh > entry and hh < tp2) else None
            geom_ok = entry > sl_raw + 0.01     # giriş SL'nin sağ tarafında olmalı
        else:
            sl_raw    = signal.stop_price * (1.0 + buf)
            risk_per  = max(sl_raw - entry, 0.01)
            actual_rr = (entry - tp2) / risk_per
            tp1 = hh if (hh < entry and hh > tp2) else None
            geom_ok = entry < sl_raw - 0.01

        if not geom_ok:                          # açılış SL'ye gap'lendi → geçersiz
            if hasattr(self.brain, '_refund_daily'):
                self.brain._refund_daily()
            return None

        if actual_rr < self.MIN_RR:
            self.rr_reject_count += 1
            if hasattr(self.brain, '_refund_daily'):
                self.brain._refund_daily()   # gün limitini geri ver
            return None

        r = self.risk.compute(direction, entry, signal.stop_price, equity,
                              signal.risk_fraction, tp_override=tp2)
        if r is None:
            return None
        return Trade(
            trade_id      = trade_id,
            signal        = signal,
            entry_price   = round(entry, 2),
            sl            = r['sl'],
            tp            = r['tp'],
            risk          = r['risk'],
            risk_pct      = r['risk_pct'],
            risk_dollar   = r['risk_dollar'],
            rr            = actual_rr,
            risk_fraction = r['risk_fraction'],
            entry_bar_idx = idx,
            tp1           = (round(tp1, 2) if tp1 is not None else None),
            tp1_fraction  = self.TP1_FRACTION,
        )


if __name__ == '__main__':
    main()
