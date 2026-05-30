#!/usr/bin/env python3
"""
BingX XAUUSD Canlı Trading Botu
Motor: xauusd_fvg_engine_v10.py (FVG/OB/HS/PRZ + EMA/RSI/MSB)

Kullanım:
  python3 xauusd_live_trader.py --bias weekly    # her hafta başı terminal prompt
  python3 xauusd_live_trader.py --bias daily     # her gün başı terminal prompt
  python3 xauusd_live_trader.py --bias none      # bias filtresi yok
  python3 xauusd_live_trader.py --bias weekly --dry-run  # kağıt işlem
"""

import argparse
import hmac
import json
import sys
import time
import traceback
import urllib.parse
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

# ── Engine importları ──────────────────────────────────────────────────────────
import xauusd_fvg_engine_v10 as _eng
from xauusd_fvg_engine_v10 import (
    FVG, MSBEvent, TradeSignal, HarmonicSignal,
    FVGEngine, MSB5MEngine, HarmonicEngine,
    MarketBrain, RiskManager,
    EMAEngine, RSIEngine, IndicatorEngine,
    detect_order_blocks_1h, detect_horseshoe_1h,
    _build_poi_mit_map, to_naive,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  BingX REST API Client
# ═══════════════════════════════════════════════════════════════════════════════

class BingXClient:
    """BingX Perpetual Futures V2 REST API wrapper."""

    BASE = "https://open-api.bingx.com"

    def __init__(self, api_key: str, api_secret: str,
                 symbol: str = "XAUT-USDT"):
        self.key    = api_key
        self.secret = api_secret
        self.symbol = symbol
        self._sess  = requests.Session()
        self._sess.headers.update({
            'X-BX-APIKEY': self.key,
            'Content-Type': 'application/x-www-form-urlencoded',
        })

    # ── İmzalama ──────────────────────────────────────────────────────────────
    def _sign(self, params: dict) -> Tuple[str, str]:
        """
        Sorted query string oluştur ve HMAC-SHA256 imzala.
        Döndürür: (query_string, signature)
        """
        qs  = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}"
                       for k, v in sorted(params.items()))
        sig = hmac.new(
            self.secret.encode('utf-8'),
            qs.encode('utf-8'),
            digestmod=sha256,
        ).hexdigest()
        return qs, sig

    # ── Temel istek gönderici ──────────────────────────────────────────────────
    def _request(self, method: str, path: str, params: dict,
                 signed: bool = True, retries: int = 3) -> Any:
        url   = self.BASE + path
        delay = 2
        last_err: Exception = RuntimeError("bilinmeyen hata")

        for attempt in range(retries):
            try:
                if not signed:
                    resp = self._sess.request(
                        method, url, params=params, timeout=10
                    )
                else:
                    p = dict(params)
                    p['timestamp'] = int(time.time() * 1000)
                    qs, sig = self._sign(p)
                    signed_url = f"{url}?{qs}&signature={sig}"
                    resp = self._sess.request(method, signed_url, timeout=10)

                resp.raise_for_status()
                body = resp.json()
                code = body.get('code', 0)
                if code != 0:
                    raise RuntimeError(
                        f"BingX hata {code}: {body.get('msg', '')}"
                    )
                return body.get('data', body)

            except Exception as e:
                last_err = e
                if attempt < retries - 1:
                    print(f"  API hata ({attempt+1}/{retries}): {e} "
                          f"— {delay}s bekle")
                    time.sleep(delay)
                    delay *= 2

        raise last_err

    # ── Market verisi ──────────────────────────────────────────────────────────
    def klines(self, interval: str, limit: int = 900) -> list:
        """
        OHLCV mum verisi. İmzasız (public endpoint).
        Döndürür: [[timestamp_ms, open, high, low, close, volume], ...]
        """
        data = self._request(
            'GET', '/openApi/swap/v2/quote/klines',
            params={'symbol': self.symbol, 'interval': interval,
                    'limit': min(limit, 1440)},
            signed=False,
        )
        if isinstance(data, dict):
            data = data.get('data', data)
        return data if isinstance(data, list) else []

    # ── Hesap ──────────────────────────────────────────────────────────────────
    def get_balance(self) -> float:
        """USDT serbest margin (availableMargin)."""
        data = self._request('GET', '/openApi/swap/v3/user/balance', {})
        balances = data.get('balance', []) if isinstance(data, dict) else []
        for b in balances:
            if b.get('asset') == 'USDT':
                return float(b.get('availableMargin', 0))
        return 0.0

    # ── Pozisyon ───────────────────────────────────────────────────────────────
    def get_position(self) -> Optional[dict]:
        """Açık pozisyon varsa döndürür (positionAmt != 0), yoksa None."""
        data = self._request(
            'GET', '/openApi/swap/v2/trade/openPositions',
            params={'symbol': self.symbol},
        )
        positions = data if isinstance(data, list) else \
                    data.get('positions', []) if isinstance(data, dict) else []
        for p in positions:
            if float(p.get('positionAmt', 0)) != 0:
                return p
        return None

    # ── Kaldıraç ───────────────────────────────────────────────────────────────
    def set_leverage(self, leverage: int) -> None:
        self._request('POST', '/openApi/swap/v2/trade/leverage', {
            'symbol': self.symbol, 'leverage': leverage,
        })

    # ── Order gönder ───────────────────────────────────────────────────────────
    def place_order(self, side: str, qty: float,
                    sl: float, tp: float) -> dict:
        """
        Market order + exchange-side SL/TP.
        side: 'BUY' (long) | 'SELL' (short)
        """
        pos_side = 'LONG' if side == 'BUY' else 'SHORT'
        params: dict = {
            'symbol':          self.symbol,
            'side':            side,
            'positionSide':    pos_side,
            'type':            'MARKET',
            'quantity':        str(qty),
            'stopLossPrice':   str(round(sl, 2)),
            'takeProfitPrice': str(round(tp, 2)),
        }
        result = self._request('POST', '/openApi/swap/v2/trade/order', params)
        # Yanıt: {"order": {"orderId": 12345, ...}} veya doğrudan dict
        if isinstance(result, dict) and 'order' in result:
            return result['order']
        return result if isinstance(result, dict) else {}

    # ── Tüm açık emirleri iptal ─────────────────────────────────────────────
    def cancel_all_orders(self) -> None:
        try:
            self._request(
                'DELETE', '/openApi/swap/v2/trade/allOpenOrders',
                params={'symbol': self.symbol},
            )
        except Exception as e:
            print(f"  cancel_all_orders: {e}")

    # ── Pozisyonu kapat ─────────────────────────────────────────────────────
    def close_position(self) -> None:
        pos = self.get_position()
        if not pos:
            return
        amt = float(pos.get('positionAmt', 0))
        if amt == 0:
            return
        side     = 'SELL' if amt > 0 else 'BUY'
        pos_side = 'LONG' if amt > 0 else 'SHORT'
        self._request('POST', '/openApi/swap/v2/trade/order', {
            'symbol':       self.symbol,
            'side':         side,
            'positionSide': pos_side,
            'type':         'MARKET',
            'quantity':     str(abs(round(amt, 3))),
        })
        print("  Pozisyon market'ten kapatıldı.")


# ═══════════════════════════════════════════════════════════════════════════════
#  Interactive Bias Provider
# ═══════════════════════════════════════════════════════════════════════════════

class InteractiveBiasProvider:
    """
    Terminal prompt — haftalık/günlük periyot değişiminde blocking input.
    MarketBrain.WeeklyBiasProvider ile aynı arayüz: get(dt) → 'bull'|'bear'|None
    """

    def __init__(self, mode: str):
        assert mode in ('weekly', 'daily'), f"Geçersiz mod: {mode}"
        self.mode          = mode
        self._current_key: Optional[str] = None
        self._current_bias: Optional[str] = None

    def get(self, dt: Any) -> Optional[str]:
        """
        Yeni hafta/gün başladıysa blocking terminal prompt.
        Önceki periyottaki bias değerini önbellekten döndürür.
        """
        t   = to_naive(dt) if hasattr(dt, 'tzinfo') else dt
        key = self._period_key(t)
        if key != self._current_key:
            self._current_key  = key
            self._current_bias = self._prompt(key)
        return self._current_bias

    def _period_key(self, dt: datetime) -> str:
        if self.mode == 'weekly':
            iso = dt.isocalendar()
            return f"{iso[0]}-W{iso[1]:02d}"
        return dt.strftime('%Y-%m-%d')

    def _prompt(self, key: str) -> Optional[str]:
        label = "HAFTA" if self.mode == 'weekly' else "GÜN"
        print(f"\n{'═'*54}")
        print(f"  YENİ {label}: {key}")
        print(f"{'═'*54}")
        while True:
            try:
                val = input("  Bias girin  [bull / bear / none]: ").strip().lower()
            except EOFError:
                print("  EOF — bias=None")
                return None
            if val in ('bull', 'bear'):
                print(f"  ✓  Bias: {val.upper()}")
                return val
            if val in ('none', ''):
                print("  ✓  Bias: YOK (EMA konfluensi hâlâ zorunlu)")
                return None
            print("  Geçersiz giriş. 'bull', 'bear' veya 'none' yazın.")


# ═══════════════════════════════════════════════════════════════════════════════
#  Live Data Engine
# ═══════════════════════════════════════════════════════════════════════════════

class LiveDataEngine:
    """BingX kline → engine formatında pandas DataFrame."""

    @staticmethod
    def fetch(client: BingXClient, interval: str,
              limit: int = 900) -> pd.DataFrame:
        """
        Döndürür: columns=[Open, High, Low, Close, Volume]
                  index=UTC-naive datetime (engine beklentisi)
        Son (henüz kapanmamış) bar çıkarılır.
        """
        raw = client.klines(interval, limit)
        if not raw:
            raise RuntimeError(f"BingX {interval} kline boş döndü")

        rows = []
        for row in raw:
            if isinstance(row, (list, tuple)) and len(row) >= 6:
                rows.append({
                    'ts':     int(row[0]),
                    'Open':   float(row[1]),
                    'High':   float(row[2]),
                    'Low':    float(row[3]),
                    'Close':  float(row[4]),
                    'Volume': float(row[5]),
                })
        if not rows:
            raise RuntimeError(f"BingX {interval} parse hatası")

        df = pd.DataFrame(rows)
        df.index = pd.to_datetime(df.pop('ts'), unit='ms', utc=True)
        df.index = df.index.tz_localize(None)   # UTC naive (engine formatı)
        df       = df.sort_index()
        df       = df.iloc[:-1]                  # son kapanmamış bar çıkar
        return df


# ═══════════════════════════════════════════════════════════════════════════════
#  Lot Hesaplayıcı
# ═══════════════════════════════════════════════════════════════════════════════

def compute_lot(entry: float, sl: float,
                risk_dollar: float,
                min_lot: float = 0.001) -> float:
    """
    Dollar risk → XAUUSD ounce miktarı.
    risk_dollar / |entry - sl| = kaç ounce açmamız gerektiği.
    """
    risk_per_unit = abs(entry - sl)
    if risk_per_unit < 0.01:
        return 0.0
    qty = risk_dollar / risk_per_unit
    return max(min_lot, round(qty, 3))


# ═══════════════════════════════════════════════════════════════════════════════
#  State Manager
# ═══════════════════════════════════════════════════════════════════════════════

class StateManager:
    """
    live_state.json — bot yeniden başladığında açık pozisyonu hatırlar.
    """

    def __init__(self, path: str = 'live_state.json'):
        self.path        = Path(path)
        self.active      = False
        self.order_id    = None
        self.direction: Optional[str] = None
        self.entry       = 0.0
        self.sl          = 0.0
        self.tp          = 0.0
        self.qty         = 0.0
        self.signal_type = ''
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            d = json.loads(self.path.read_text())
            self.active      = bool(d.get('active', False))
            self.order_id    = d.get('order_id')
            self.direction   = d.get('direction')
            self.entry       = float(d.get('entry',  0))
            self.sl          = float(d.get('sl',     0))
            self.tp          = float(d.get('tp',     0))
            self.qty         = float(d.get('qty',    0))
            self.signal_type = d.get('signal_type', '')
            if self.active:
                print(f"  Önceki pozisyon bulundu: "
                      f"{self.direction.upper()} @ {self.entry:.2f} "
                      f"(SL:{self.sl} TP:{self.tp})")
        except Exception as e:
            print(f"  live_state.json okuma hatası: {e}")

    def save(self, order_id: Any, direction: str, entry: float,
             sl: float, tp: float, qty: float, signal_type: str) -> None:
        self.active      = True
        self.order_id    = order_id
        self.direction   = direction
        self.entry       = entry
        self.sl          = sl
        self.tp          = tp
        self.qty         = qty
        self.signal_type = signal_type
        self._write()

    def clear(self) -> None:
        self.active = False
        self._write()

    def _write(self) -> None:
        self.path.write_text(json.dumps({
            'active':      self.active,
            'order_id':    self.order_id,
            'direction':   self.direction,
            'entry':       self.entry,
            'sl':          self.sl,
            'tp':          self.tp,
            'qty':         self.qty,
            'signal_type': self.signal_type,
        }, indent=2))


# ═══════════════════════════════════════════════════════════════════════════════
#  Live Trader — Ana Sınıf
# ═══════════════════════════════════════════════════════════════════════════════

class LiveTrader:
    """
    5M bar kapanışına senkronize döngü.
    Her tickte: BingX'ten veri çek → engine detection → sinyal ara → order gönder.
    """

    # Kaç bar geriye giderek brain.pending state'ini yeniden kur.
    # TOUCH_MAX_AGE_BARS = 24; biraz daha geniş tutalım.
    LOOKBACK_BARS = 32

    def __init__(self,
                 client:        BingXClient,
                 bias_provider,                # InteractiveBiasProvider | None
                 leverage:      int   = 10,
                 risk_pct:      float = 1.0,   # % (örn. 1.0 = %1)
                 capital:       float = 0.0,   # $ kasa (0 = API'den oku)
                 dry_run:       bool  = False):
        self.client        = client
        self.bias_provider = bias_provider
        self.leverage      = leverage
        self.risk_pct      = risk_pct / 100.0  # 1.0 → 0.01
        self.capital       = capital
        self.dry_run       = dry_run
        self.state         = StateManager()
        self.risk_mgr      = RiskManager(rr=2.0)

    # ── 5M bar kapanışına senkronize ─────────────────────────────────────────
    def _wait_for_bar_close(self) -> None:
        """
        Bir sonraki 5M bar kapanışına kadar uyur.
        Bar kapanışının 4 saniye sonrasında uyanır (BingX'e yetişmesi için).
        """
        now  = datetime.utcnow()
        secs = (now.minute % 5) * 60 + now.second + now.microsecond / 1e6
        wait = max(0.0, (300.0 - secs) + 4.0)
        if wait > 10:
            time.sleep(wait)

    # ── Tüm detections ───────────────────────────────────────────────────────
    def _run_all_detections(self,
                            df_5m: pd.DataFrame,
                            df_1h: pd.DataFrame) -> dict:
        """
        BacktestEngine.run() detection bloğunun birebir kopyası.
        _fvg_counter sıfırlanır → FVG ID'leri tekrar çalıştırmalar arası tutarlı.
        """
        # ID kararlılığı: her tick aynı veri → aynı ID'ler
        _eng._fvg_counter = 0

        # 5M göstergeler
        df5 = df_5m.copy()
        df5 = EMAEngine.add(df5, 100, 200)
        df5['rsi'] = RSIEngine.wilder(df5['Close'], 14)
        df5['atr'] = IndicatorEngine.atr(df5, 14)

        # 1H göstergeler
        df1 = df_1h.copy()
        df1['atr'] = IndicatorEngine.atr(df1, 14)

        # 1H FVG
        fvg1_eng  = FVGEngine('1h', min_gap=2.0, max_age_hours=48, buf_ratio=0.02)
        fvg1_bull = fvg1_eng.detect(df1, 'bull', df1['atr'])
        fvg1_bear = fvg1_eng.detect(df1, 'bear', df1['atr'])
        mit1_bull = fvg1_eng.build_mitigation_map(df1, fvg1_bull)
        mit1_bear = fvg1_eng.build_mitigation_map(df1, fvg1_bear)

        # 5M MSB
        msb_eng         = MSB5MEngine(vol_mult=1.5, vol_window=20)
        msb_events      = msb_eng.detect(df5, df5['atr'])
        msb_events_bull = [e for e in msb_events if e.direction == 'bull']
        msb_events_bear = [e for e in msb_events if e.direction == 'bear']

        # Harmonik + PRZ pseudo-FVG
        harm_eng    = HarmonicEngine(swing=5, min_conf=40.0, max_prz_pct=4.0)
        harmonics: List[HarmonicSignal] = []
        try:
            harmonics += harm_eng.detect(df5, '5m')
        except Exception:
            pass

        prz_eng         = FVGEngine('prz', max_age_hours=24 * 30, buf_ratio=0.02)
        przfvg_bull: List[FVG] = []
        przfvg_bear: List[FVG] = []
        mit_prz:     Dict[int, Any] = {}
        prz_harm:    Dict[int, HarmonicSignal] = {}

        for hsig in harmonics:
            top    = hsig.prz_high
            bottom = hsig.prz_low
            pf = FVG(
                fvg_id       = _eng._next_fvg_id(),
                timeframe    = 'prz',
                direction    = hsig.direction,
                index        = hsig.detect_time,
                detect_time  = hsig.detect_time,
                top          = top,
                bottom       = bottom,
                mid          = (top + bottom) / 2,
                gap_size     = top - bottom,
                gap_atr_ratio= 0.0,
                momentum     = 0.0,
                quality_score= hsig.conf,
                created_i    = 0,
            )
            mit_prz[pf.fvg_id]  = to_naive(hsig.expiry_time)
            prz_harm[pf.fvg_id] = hsig
            (przfvg_bull if hsig.direction == 'bull'
             else przfvg_bear).append(pf)

        # 1H OB / HS (BB kapalı: %38 WR)
        H1   = df1['High'].values.astype(float)
        L1   = df1['Low'].values.astype(float)
        O1   = df1['Open'].values.astype(float)
        C1   = df1['Close'].values.astype(float)
        T1   = df1.index
        atr1 = df1['atr'].values.astype(float)

        ob_bull = detect_order_blocks_1h(H1, L1, O1, C1, T1, atr1, 'bull')
        ob_bear = detect_order_blocks_1h(H1, L1, O1, C1, T1, atr1, 'bear')
        hs_bull = detect_horseshoe_1h(H1, L1, O1, C1, T1, 'bull')
        hs_bear = detect_horseshoe_1h(H1, L1, O1, C1, T1, 'bear')
        bb_bull: List[FVG] = []
        bb_bear: List[FVG] = []

        poi1h_eng   = FVGEngine('1h_ob', max_age_hours=72, buf_ratio=0.02)
        _off1h      = pd.Timedelta(hours=1)
        mit_ob_bull = _build_poi_mit_map(ob_bull, C1, T1, _off1h)
        mit_ob_bear = _build_poi_mit_map(ob_bear, C1, T1, _off1h)
        mit_bb_bull = _build_poi_mit_map(bb_bull, C1, T1, _off1h)
        mit_bb_bear = _build_poi_mit_map(bb_bear, C1, T1, _off1h)
        mit_hs_bull = _build_poi_mit_map(hs_bull, C1, T1, _off1h)
        mit_hs_bear = _build_poi_mit_map(hs_bear, C1, T1, _off1h)

        # 5M numpy array'leri
        C    = df5['Close'].values.astype(float)
        O    = df5['Open'].values.astype(float)
        H    = df5['High'].values.astype(float)
        L    = df5['Low'].values.astype(float)
        ATR  = df5['atr'].values.astype(float)
        E100 = df5['ema100'].values.astype(float)
        E200 = df5['ema200'].values.astype(float)
        RSI  = df5['rsi'].values.astype(float)
        TM   = df5.index

        return dict(
            C=C, O=O, H=H, L=L, ATR=ATR,
            E100=E100, E200=E200, RSI=RSI, TM=TM,
            fvg1_bull=fvg1_bull,  mit1_bull=mit1_bull,
            fvg1_bear=fvg1_bear,  mit1_bear=mit1_bear,
            fvg1_eng=fvg1_eng,
            msb_events_bull=msb_events_bull,
            msb_events_bear=msb_events_bear,
            przfvg_bull=przfvg_bull, przfvg_bear=przfvg_bear,
            mit_prz=mit_prz, prz_eng=prz_eng, prz_harm=prz_harm,
            ob1_bull=ob_bull,    ob1_bear=ob_bear,
            mit_ob_bull=mit_ob_bull, mit_ob_bear=mit_ob_bear,
            bb1_bull=bb_bull,    bb1_bear=bb_bear,
            mit_bb_bull=mit_bb_bull, mit_bb_bear=mit_bb_bear,
            hs1_bull=hs_bull,    hs1_bear=hs_bear,
            mit_hs_bull=mit_hs_bull, mit_hs_bear=mit_hs_bear,
            poi1h_eng=poi1h_eng,
        )

    # ── Sliding-window sinyal ara ─────────────────────────────────────────────
    def _find_signal(self, ctx: dict,
                     brain: MarketBrain) -> Optional[TradeSignal]:
        """
        Son LOOKBACK_BARS barı brain.evaluate() ile sırayla işler.
        Bu sayede cross-bar pending state (FVG touch → MSB trigger) yeniden kurulur.
        Yalnız SON barda üretilen sinyali döndürür.
        """
        n     = len(ctx['C'])
        start = max(0, n - self.LOOKBACK_BARS - 1)
        end   = n - 1   # son kapanan bar

        last_signal: Optional[TradeSignal] = None

        for idx in range(start, end + 1):
            sig = brain.evaluate(
                idx          = idx,
                C=ctx['C'],  O=ctx['O'],  H=ctx['H'],  L=ctx['L'],
                E100=ctx['E100'], E200=ctx['E200'],
                RSI=ctx['RSI'],   ATR=ctx['ATR'],  TM=ctx['TM'],
                fvg1_bull    = ctx['fvg1_bull'],
                mit1_bull    = ctx['mit1_bull'],
                fvg1_bear    = ctx['fvg1_bear'],
                mit1_bear    = ctx['mit1_bear'],
                fvg1_eng     = ctx['fvg1_eng'],
                msb_events_bull = ctx['msb_events_bull'],
                msb_events_bear = ctx['msb_events_bear'],
                przfvg_bull  = ctx['przfvg_bull'],
                przfvg_bear  = ctx['przfvg_bear'],
                mit_prz      = ctx['mit_prz'],
                prz_eng      = ctx['prz_eng'],
                prz_harm     = ctx['prz_harm'],
                ob1_bull     = ctx['ob1_bull'],
                ob1_bear     = ctx['ob1_bear'],
                mit_ob_bull  = ctx['mit_ob_bull'],
                mit_ob_bear  = ctx['mit_ob_bear'],
                bb1_bull     = ctx['bb1_bull'],
                bb1_bear     = ctx['bb1_bear'],
                mit_bb_bull  = ctx['mit_bb_bull'],
                mit_bb_bear  = ctx['mit_bb_bear'],
                hs1_bull     = ctx['hs1_bull'],
                hs1_bear     = ctx['hs1_bear'],
                mit_hs_bull  = ctx['mit_hs_bull'],
                mit_hs_bear  = ctx['mit_hs_bear'],
                poi1h_eng    = ctx['poi1h_eng'],
            )
            # Yalnız son barın sinyalini al
            if idx == end and sig is not None:
                last_signal = sig

        return last_signal

    # ── İşlem aç ─────────────────────────────────────────────────────────────
    def _enter_trade(self, signal: TradeSignal,
                     equity: float, last_close: float) -> None:
        entry = last_close

        # SL/TP fiyatlarını hesapla (RiskManager'dan)
        r = self.risk_mgr.compute(
            signal.direction, entry, signal.stop_price,
            equity, signal.risk_fraction,
        )
        if r is None:
            print("  Risk hesabı geçersiz — işlem atlandı")
            return

        # Lot hesabı: kullanıcının risk_pct'si + konfluens ölçeği
        # signal.risk_fraction: 0.01 (EMA+RSI) veya 0.005 (EMA tek)
        # Pozisyon büyüklüğü YALNIZCA stop riskine göre belirlenir:
        #   lot = (stop olursa kaybedilecek $) / |entry - sl|
        # Kaldıraç lot'u değiştirmez; sadece gereken marjini etkiler.
        confluence_scale = signal.risk_fraction / 0.01   # 1.0 veya 0.5
        actual_risk      = equity * self.risk_pct * confluence_scale
        qty              = compute_lot(entry, r['sl'], actual_risk)

        if qty < 0.001:
            print(f"  Lot çok küçük ({qty:.4f}) — işlem atlandı")
            return

        notional = qty * entry
        margin   = notional / self.leverage if self.leverage else notional

        side  = 'BUY' if signal.direction == 'bull' else 'SELL'
        label = signal.confirmation_type

        print(f"\n  ┌── SİNYAL: {signal.direction.upper()} ──────────────────")
        print(f"  │  Tip   : {label}")
        print(f"  │  MSB   : {signal.msb_type}")
        print(f"  │  Entry : ~{entry:.2f}")
        print(f"  │  SL    : {r['sl']:.2f}")
        print(f"  │  TP    : {r['tp']:.2f}")
        print(f"  │  Lot   : {qty} oz")
        print(f"  │  Risk  : ${actual_risk:.2f} ({self.risk_pct*100:.1f}% × "
              f"{confluence_scale:.1f}x)  [stop olursa kayıp]")
        print(f"  │  Kasa  : ${equity:.2f}  |  Kaldıraç: {self.leverage}x")
        print(f"  │  Pozis.: ${notional:.2f} notional  |  Marjin: ${margin:.2f}")
        if margin > equity:
            print(f"  │  ⚠ Gereken marjin (${margin:.2f}) kasadan büyük — "
                  f"kaldıracı artırın")
        print(f"  └{'─'*40}")

        if self.dry_run:
            print("  [DRY-RUN] Order gönderilmedi.\n")
            return

        try:
            result   = self.client.place_order(side, qty, r['sl'], r['tp'])
            order_id = result.get('orderId', 'N/A')
            print(f"  ✓  Order açıldı: #{order_id}\n")
            self.state.save(
                order_id    = order_id,
                direction   = signal.direction,
                entry       = entry,
                sl          = r['sl'],
                tp          = r['tp'],
                qty         = qty,
                signal_type = label,
            )
        except Exception as e:
            print(f"  ✗  ORDER HATASI: {e}\n")

    # ── Pozisyon kontrolü ─────────────────────────────────────────────────────
    def _check_position(self) -> None:
        """Kaydedilmiş pozisyon BingX'te kapandıysa state'i temizler."""
        if not self.state.active:
            return
        if self.dry_run:
            return
        try:
            pos = self.client.get_position()
            if not pos:
                print(f"  Pozisyon kapandı  "
                      f"({self.state.direction.upper()} @ {self.state.entry:.2f})")
                self.state.clear()
        except Exception as e:
            print(f"  Pozisyon kontrol hatası: {e}")

    # ── Bar özet logu ─────────────────────────────────────────────────────────
    def _log_bar(self, now: datetime, price: float,
                 bias: Optional[str]) -> None:
        ts   = now.strftime('%Y-%m-%d %H:%M') + ' UTC'
        bias_= bias.upper() if bias else 'YOK'
        poz  = (f"{self.state.direction.upper()}@{self.state.entry:.2f}"
                if self.state.active else 'YOK')
        mode = 'DRY-RUN' if self.dry_run else 'CANLI'
        print(f"[{ts}]  Fiyat:{price:.2f}  Bias:{bias_}  "
              f"Poz:{poz}  [{mode}]")

    # ── Ana döngü ─────────────────────────────────────────────────────────────
    def run(self) -> None:
        print("═" * 58)
        print("  BingX XAUUSD Live Trader")
        print(f"  Motor  : xauusd_fvg_engine_v10")
        print(f"  Sembol : {self.client.symbol}")
        print(f"  Risk   : {self.risk_pct*100:.1f}%  |  "
              f"Kaldıraç: {self.leverage}x")
        kasa_str = (f"${self.capital:.2f} (manuel)" if self.capital > 0
                    else "API bakiyesi")
        print(f"  Kasa   : {kasa_str}")
        print(f"  Mod    : {'DRY-RUN  ⚠️' if self.dry_run else 'CANLI  ✓'}")
        if self.bias_provider is not None:
            print(f"  Bias   : {self.bias_provider.mode.upper()} (terminal prompt)")
        else:
            print("  Bias   : NONE (EMA zorunlu, bias yok)")
        print("═" * 58)

        # Kaldıraç ayarla (canlı modda)
        if not self.dry_run:
            try:
                self.client.set_leverage(self.leverage)
                print(f"  Kaldıraç {self.leverage}x ayarlandı.")
            except Exception as e:
                print(f"  Kaldıraç ayar hatası: {e}")

        # MarketBrain — bias_provider='none' ise None geçilir
        brain = MarketBrain(bias_provider=self.bias_provider)
        current_bias: Optional[str] = None

        print("\n  5M bar kapanışı bekleniyor...\n")

        while True:
            try:
                # ── 5M bar kapanışına senkronize ol ──────────────────────────
                self._wait_for_bar_close()
                now = datetime.utcnow()

                # ── Bias prompt (yeni periyotta blocking) ─────────────────────
                if self.bias_provider is not None:
                    current_bias = self.bias_provider.get(now)

                # ── Pozisyon kapandı mı? ──────────────────────────────────────
                self._check_position()

                # ── Veri çek ─────────────────────────────────────────────────
                df_5m = LiveDataEngine.fetch(self.client, '5m', 900)
                df_1h = LiveDataEngine.fetch(self.client, '1h', 200)

                last_close = float(df_5m['Close'].iloc[-1])
                self._log_bar(now, last_close, current_bias)

                # ── Sinyal yalnız açık pozisyon yokken ───────────────────────
                if not self.state.active:
                    ctx = self._run_all_detections(df_5m, df_1h)

                    # Her tickte pending'i sıfırla; LOOKBACK ile yeniden kur
                    brain.pending      = {'bull': [], 'bear': []}
                    brain.used_fvg_ids = set()

                    signal = self._find_signal(ctx, brain)

                    if signal is not None:
                        # Kasa önceliği: manuel capital > API bakiyesi > dry-run varsayılanı
                        if self.capital > 0:
                            equity = self.capital
                        elif not self.dry_run:
                            equity = self.client.get_balance()
                        else:
                            equity = 10_000.0
                        self._enter_trade(signal, equity, last_close)
                    else:
                        reason = brain.last_skip_reason or '—'
                        print(f"  Sinyal: yok  ({reason})")
                else:
                    print("  Aktif pozisyon var — sinyal aranmıyor")

            except KeyboardInterrupt:
                print("\n\nCtrl+C — durduruldu.")
                if self.state.active and not self.dry_run:
                    print(f"  UYARI: Açık pozisyon var! "
                          f"({self.state.direction.upper()} @ {self.state.entry})")
                    print("  BingX panelinden veya "
                          "'python3 xauusd_live_trader.py --close' ile kapatın.")
                break
            except Exception as e:
                print(f"  HATA: {e}")
                traceback.print_exc()
                print("  30 saniye sonra devam ediliyor...")
                time.sleep(30)


# ═══════════════════════════════════════════════════════════════════════════════
#  Config & CLI
# ═══════════════════════════════════════════════════════════════════════════════

_CONFIG_TEMPLATE = {
    "api_key":    "YOUR_BINGX_API_KEY",
    "api_secret": "YOUR_BINGX_API_SECRET",
    "symbol":     "XAUT-USDT",
    "leverage":   10,
    "risk_pct":   1.0,
    "capital":    0,
}


def load_config(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        p.write_text(json.dumps(_CONFIG_TEMPLATE, indent=2))
        print(f"  '{path}' oluşturuldu. API bilgilerinizi doldurun, tekrar çalıştırın.")
        sys.exit(0)
    return json.loads(p.read_text())


def main() -> None:
    parser = argparse.ArgumentParser(
        description='BingX XAUUSD Canlı Trading Botu',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  python3 xauusd_live_trader.py --bias weekly
  python3 xauusd_live_trader.py --bias daily
  python3 xauusd_live_trader.py --bias none
  python3 xauusd_live_trader.py --bias weekly --dry-run
  python3 xauusd_live_trader.py --bias weekly --leverage 5 --risk-pct 0.5
  python3 xauusd_live_trader.py --bias weekly --balance 500 --leverage 10
  python3 xauusd_live_trader.py --close   (açık pozisyonu kapat)
        """,
    )
    parser.add_argument(
        '--bias', choices=['weekly', 'daily', 'none'], default='weekly',
        help='Bias modu: weekly=haftalık, daily=günlük, none=filtre yok',
    )
    parser.add_argument('--leverage', type=int,   default=None,
                        help='Kaldıraç (config varsayılanını geçersiz kılar)')
    parser.add_argument('--risk-pct', type=float, default=None,
                        help='Risk yüzdesi, örn. 1.0 = %%1')
    parser.add_argument('--balance',  type=float, default=None,
                        help='Kasa ($). Girilirse API bakiyesi yerine bu kullanılır')
    parser.add_argument('--symbol',   default=None,
                        help='BingX sembolü (varsayılan: XAUT-USDT)')
    parser.add_argument('--config',   default='live_config.json',
                        help='Config dosyası yolu')
    parser.add_argument('--dry-run',  action='store_true',
                        help='Kağıt işlem — BingX\'e order gönderilmez')
    parser.add_argument('--close',    action='store_true',
                        help='Açık pozisyonu market\'ten kapat ve çık')
    args = parser.parse_args()

    cfg = load_config(args.config)

    api_key    = cfg.get('api_key',    '')
    api_secret = cfg.get('api_secret', '')
    symbol     = args.symbol   or cfg.get('symbol',   'XAUT-USDT')
    leverage   = args.leverage or int(cfg.get('leverage', 10))
    risk_pct   = args.risk_pct or float(cfg.get('risk_pct',  1.0))
    capital    = (args.balance if args.balance is not None
                  else float(cfg.get('capital', 0)))

    # API anahtarı kontrolü (dry-run hariç)
    if not args.dry_run and (
        not api_key or api_key == 'YOUR_BINGX_API_KEY'
    ):
        print("HATA: API anahtarı ayarlanmamış.")
        print(f"      '{args.config}' dosyasını açıp api_key / api_secret girin.")
        sys.exit(1)

    client = BingXClient(api_key, api_secret, symbol)

    # --close: pozisyonu kapat ve çık
    if args.close:
        print("Açık pozisyon kapatılıyor...")
        client.close_position()
        StateManager().clear()
        print("Tamamlandı.")
        return

    # Bias provider
    if args.bias == 'none':
        bias_provider = None
    else:
        bias_provider = InteractiveBiasProvider(args.bias)

    trader = LiveTrader(
        client        = client,
        bias_provider = bias_provider,
        leverage      = leverage,
        risk_pct      = risk_pct,
        capital       = capital,
        dry_run       = args.dry_run,
    )
    trader.run()


if __name__ == '__main__':
    main()
