#!/usr/bin/env python3
"""
BingX XAUUSD Canlı Trading Botu
Motor: xauusd_fvg_engine_v10.py (FVG/OB/HS/PRZ + EMA/RSI/MSB)

Kullanım:
  python3 xauusd_live_trader.py                          # fvg (varsayılan), weekly bias
  python3 xauusd_live_trader.py --bias daily             # fvg, günlük bias prompt
  python3 xauusd_live_trader.py --strategy qwe           # QWE swing (bias ZORUNLU none)
  python3 xauusd_live_trader.py --strategy qwe --dry-run # QWE kağıt işlem
  python3 xauusd_live_trader.py --bias weekly --dry-run  # fvg kağıt işlem
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
    QweBrain, QweBacktestEngine, BacktestEngine,
    ThreeVolBrain, LondonReversalBrain,
    AsianRangeCalculator, PrivateBiasProvider,
    EMAEngine, RSIEngine, IndicatorEngine, MACDEngine,
    detect_order_blocks_1h,
    _build_poi_mit_map, to_naive,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  BingX REST API Client
# ═══════════════════════════════════════════════════════════════════════════════

class BingXClient:
    """BingX Perpetual Futures V2 REST API wrapper."""

    BASE = "https://open-api.bingx.com"

    def __init__(self, api_key: str, api_secret: str,
                 symbol: str = "NCCGOLD2USD-USDT"):
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

    # ── Kontratlar / sembol doğrulama ───────────────────────────────────────────
    def contracts(self) -> list:
        """Tüm perpetual kontratları (public). [{'symbol':..,'asset':..}, ...]"""
        data = self._request(
            'GET', '/openApi/swap/v2/quote/contracts', params={}, signed=False,
        )
        if isinstance(data, dict):
            data = data.get('data', data)
        return data if isinstance(data, list) else []

    def verify_symbol(self) -> bool:
        """
        self.symbol borsada gerçek API sembolü mü kontrol eder.

        DİKKAT: BingX uygulamasında görünen ad (ör. 'GOLD(XAU)-USDT') bir
        displayName'dir; gerçek API sembolü farklıdır (ör. 'NCCGOLD2USD-USDT').
        Kullanıcı yanlışlıkla displayName girerse, otomatik olarak gerçek
        sembole çevirir. Hiç eşleşme yoksa altın kontratlarını listeler.
        Ağ hatasında True döndürür — başlatmayı engellemez.
        """
        try:
            rows = self.contracts()
        except Exception as e:
            print(f"  Sembol doğrulanamadı (ağ?): {e} — devam ediliyor.")
            return True
        if not rows:
            return True

        syms = {str(c.get('symbol', '')) for c in rows}
        if self.symbol in syms:
            return True

        # Kullanıcı displayName girmiş olabilir → gerçek sembole çevir
        for c in rows:
            if str(c.get('displayName', '')) == self.symbol:
                real = str(c.get('symbol', ''))
                print(f"  '{self.symbol}' bir görünen ad (displayName); "
                      f"gerçek sembol: '{real}' — otomatik geçildi.")
                self.symbol = real
                return True

        # Hiç eşleşme yok → altın kontratlarını sembol + displayName ile listele
        print(f"\n  ⚠ '{self.symbol}' BingX'te bulunamadı!")
        gold = [c for c in rows
                if 'XAU' in str(c.get('symbol', '')).upper()
                or 'GOLD' in str(c.get('symbol', '')).upper()
                or 'GOLD' in str(c.get('displayName', '')).upper()]
        if gold:
            print("  Altın kontratları (API sembolü  ←  uygulamada görünen):")
            for c in gold:
                print(f"      {c.get('symbol'):<22}  ←  {c.get('displayName')}")
            print("  --symbol'e soldaki API sembolünü yazın.")
        return False

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

    def place_limit_order(self, side: str, qty: float, price: float,
                          sl: float, tp: float) -> dict:
        """LIMIT (maker) giriş + borsa-taraflı SL/TP. GTC — dolmazsa
        çağıran iptal eder (pending yaşam döngüsü LiveTrader'da)."""
        pos_side = 'LONG' if side == 'BUY' else 'SHORT'
        params: dict = {
            'symbol':          self.symbol,
            'side':            side,
            'positionSide':    pos_side,
            'type':            'LIMIT',
            'price':           str(round(price, 2)),
            'quantity':        str(qty),
            'timeInForce':     'GTC',
            'stopLossPrice':   str(round(sl, 2)),
            'takeProfitPrice': str(round(tp, 2)),
        }
        result = self._request('POST', '/openApi/swap/v2/trade/order', params)
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
        self.open_time: Optional[str] = None    # TBE: giriş zamanı (ISO UTC)
        self.tbe_minutes: Optional[int] = None  # TBE: maksimum açık kalma süresi
        # QWE kısmi-TP alanları (geriye uyumlu: eski kayıtlarda yoklar)
        self.orders: list = []                  # [{'order_id','tp','qty'}, ...]
        self.tp1_filled  = False
        self.setup_key: Optional[list] = None   # işlemin QWE setup kimliği
        self.qwe_used: list = []                # işlem görmüş setup anahtarları
        # ThreeVol yazılımsal BE@1R durumu
        self.be_arm_price: Optional[float] = None
        self.be_armed = False
        # LİMİT giriş bekleyen emir durumu
        self.pending_entry = False
        self.entry_expire: Optional[str] = None   # ISO UTC
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
            self.open_time   = d.get('open_time')
            self.tbe_minutes = d.get('tbe_minutes')
            self.orders      = d.get('orders', [])
            self.tp1_filled  = bool(d.get('tp1_filled', False))
            self.setup_key   = d.get('setup_key')
            self.qwe_used    = d.get('qwe_used', [])
            self.be_arm_price = d.get('be_arm_price')
            self.be_armed     = bool(d.get('be_armed', False))
            self.pending_entry = bool(d.get('pending_entry', False))
            self.entry_expire  = d.get('entry_expire')
            if self.active:
                tbe_str = f"  TBE: {self.tbe_minutes}dk" if self.tbe_minutes else ""
                print(f"  Önceki pozisyon bulundu: "
                      f"{self.direction.upper()} @ {self.entry:.2f} "
                      f"(SL:{self.sl} TP:{self.tp}){tbe_str}")
        except Exception as e:
            print(f"  live_state.json okuma hatası: {e}")

    def save(self, order_id: Any, direction: str, entry: float,
             sl: float, tp: float, qty: float, signal_type: str,
             tbe_minutes: Optional[int] = None,
             orders: Optional[list] = None,
             setup_key: Optional[list] = None) -> None:
        self.active      = True
        self.order_id    = order_id
        self.direction   = direction
        self.entry       = entry
        self.sl          = sl
        self.tp          = tp
        self.qty         = qty
        self.signal_type = signal_type
        self.open_time   = datetime.utcnow().isoformat()
        self.tbe_minutes = tbe_minutes
        self.orders      = orders or []
        self.tp1_filled  = False
        self.setup_key   = list(setup_key) if setup_key is not None else None
        if setup_key is not None:
            self.mark_setup_used(setup_key, write=False)
        self._write()

    def mark_setup_used(self, key, write: bool = True) -> None:
        """QWE: bu setup bir kez işlem gördü → yeniden başlatma/tick'ler arası
        çifte-giriş koruması (son 100 anahtar saklanır)."""
        k = list(key)
        if k not in self.qwe_used:
            self.qwe_used.append(k)
            self.qwe_used = self.qwe_used[-100:]
        if write:
            self._write()

    def clear(self) -> None:
        self.active      = False
        self.open_time   = None
        self.tbe_minutes = None
        self.orders      = []
        self.tp1_filled  = False
        self.setup_key   = None
        self.be_arm_price = None
        self.be_armed     = False
        self.pending_entry = False
        self.entry_expire  = None
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
            'open_time':   self.open_time,
            'tbe_minutes': self.tbe_minutes,
            'orders':      self.orders,
            'tp1_filled':  self.tp1_filled,
            'setup_key':   self.setup_key,
            'qwe_used':    self.qwe_used,
            'be_arm_price': self.be_arm_price,
            'be_armed':     self.be_armed,
            'pending_entry': self.pending_entry,
            'entry_expire':  self.entry_expire,
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

    # Bias moduna göre varsayılan TBE (dakika cinsinden):
    #   weekly → 480dk (8h)   — backtest'te Δskor +0.81
    #   none   → 480dk (8h)   — backtest'te Δskor +0.77
    #   daily  → None (kapalı) — backtest'te daily bias'a zarar verdi
    _DEFAULT_TBE: dict = {'weekly': 480, 'none': 480, 'daily': None}

    # QWE: 15M onaylı swing — pencere 1 gün (aktivasyon avail_ts catch-up
    # ile pencereden bağımsız; pencere yalnız gün-içi used/limit state'ini kurar)
    LOOKBACK_QWE = 288

    def __init__(self,
                 client:        BingXClient,
                 bias_provider,                # InteractiveBiasProvider | None
                 bias_mode:     str   = 'none',
                 leverage:      int   = 10,
                 risk_pct:      float = 1.0,   # % (örn. 1.0 = %1)
                 capital:       float = 0.0,   # $ kasa (0 = API'den oku)
                 dry_run:       bool  = False,
                 tbe_minutes:   Optional[int] = -1,   # -1 = bias'a göre otomatik
                 strategy:      str   = 'fvg'):       # 'fvg' (varsayılan) | 'qwe'
        self.client        = client
        self.strategy      = (strategy if strategy in
                              ('fvg', 'qwe', 'threevol', 'london') else 'fvg')
        # SABİT PRESET'ler (backtest ile birebir):
        #   fvg      : bias none + EMA-MACD + blackout 09-11
        #   threevol : bias none + EMA-MACD + blackout 09-11 + BE@1R (yazılımsal)
        #   london   : bias PRIVATE (GARCH, otomatik — prompt yok), w6, kısmi TP
        #   qwe      : bias none (swing), kısmi TP
        if self.strategy in ('qwe', 'fvg', 'threevol', 'london'):
            bias_provider = None          # london kendi private'ını tick'te kurar
            bias_mode     = 'none'
        # Giriş karartma saatleri (config: <strateji>.blackout_hours)
        try:
            from config import get_config
            self._blackout = set(
                get_config().get(self.strategy, 'blackout_hours',
                                 default=[]) or [])
        except Exception:
            self._blackout = set()
        self.bias_provider = bias_provider
        self.leverage      = leverage
        self.risk_pct      = risk_pct / 100.0  # 1.0 → 0.01
        self.capital       = capital
        self.dry_run       = dry_run
        self.state         = StateManager()
        self.risk_mgr      = RiskManager(rr=2.0)
        # TBE: tüm sabit preset'ler TBE'siz doğrulandı → otomatikte kapalı
        # (kullanıcı --tbe ile açıkça isterse uygulanır)
        if tbe_minutes == -1 or tbe_minutes is None:
            self.tbe_minutes: Optional[int] = None
        else:
            self.tbe_minutes = tbe_minutes
        # QWE config parametreleri (engine config modülünden)
        try:
            from config import get_config
            self._qcfg = get_config().section('qwe')
        except Exception:
            self._qcfg = {}

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
        # EMA9/21 + MACD (none-bias filtresi için)
        df1 = EMAEngine.add(df1, 9, 21)
        _ml, _ms, _ = MACDEngine.compute(df1['Close'])
        df1['macd_line']   = _ml
        df1['macd_signal'] = _ms

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

        # 1H Order Blocks
        H1   = df1['High'].values.astype(float)
        L1   = df1['Low'].values.astype(float)
        O1   = df1['Open'].values.astype(float)
        C1   = df1['Close'].values.astype(float)
        T1   = df1.index
        atr1 = df1['atr'].values.astype(float)

        ob_bull = detect_order_blocks_1h(H1, L1, O1, C1, T1, atr1, 'bull')
        ob_bear = detect_order_blocks_1h(H1, L1, O1, C1, T1, atr1, 'bear')

        poi1h_eng   = FVGEngine('1h_ob', max_age_hours=72, buf_ratio=0.02)
        _off1h      = pd.Timedelta(hours=1)
        mit_ob_bull = _build_poi_mit_map(ob_bull, C1, T1, _off1h)
        mit_ob_bear = _build_poi_mit_map(ob_bear, C1, T1, _off1h)

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
            poi1h_eng=poi1h_eng,
            df_1h_ind=df1,   # 1H EMA9/21+MACD (none-bias filtresi için)
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
                poi1h_eng    = ctx['poi1h_eng'],
            )
            # Yalnız son barın sinyalini al
            if idx == end and sig is not None:
                # None bias → EMA9/21+MACD filtresi (backtest davranışıyla tutarlı)
                if self.bias_provider is None:
                    sig = self._apply_ema_macd_filter(sig, ctx)
                last_signal = sig

        return last_signal

    def _apply_ema_macd_filter(self, sig: Optional[TradeSignal],
                               ctx: dict) -> Optional[TradeSignal]:
        """None bias'ta EMA9/21+MACD trend filtresi — backtestle tutarlı."""
        if sig is None:
            return None
        import pandas as pd
        df1 = ctx.get('df_1h_ind')
        if df1 is None or df1.empty:
            return sig
        try:
            row = df1.iloc[-1]   # en son kapanan 1H bar
            ema9 = float(row['ema9'])
            ema21= float(row['ema21'])
            ml   = float(row['macd_line'])
            ms   = float(row['macd_signal'])
            c1   = float(row['Close'])
        except (KeyError, IndexError):
            return sig
        if sig.direction == 'bull':
            ok = (ema9 > ema21) and (c1 > ema9) and (ml > ms)
        else:
            ok = (ema9 < ema21) and (c1 < ema9) and (ml < ms)
        if not ok:
            print("  EMA-MACD filtresi → sinyal atlandı")
            return None
        return sig

    # ── QWE sinyal yolu ──────────────────────────────────────────────────────
    def _find_signal_qwe(self, df_5m: pd.DataFrame,
                         df_1h: pd.DataFrame) -> Optional[TradeSignal]:
        """
        QWE (fib pullback swing) sinyali. Bağlam dizileri backtest'le AYNI
        fonksiyondan gelir (QweBacktestEngine.prepare_kwargs → drift yok).
        Brain her tick taze kurulur; işlem görmüş setup'lar state'ten
        mark_used ile işaretlenir. Yalnız SON kapanan barın sinyali kullanılır.
        """
        qc = self._qcfg
        kw = QweBacktestEngine.prepare_kwargs(
            df_1h, df_5m,
            structure_tf   = str(qc.get('structure_tf', '1h')),
            swing_k        = int(qc.get('swing_k', 2)),
            min_leg_atr    = float(qc.get('min_leg_atr', 1.5)),
            max_setup_age  = int(qc.get('max_setup_age', 48)),
            ema_fast       = int(qc.get('ema4h_fast', 20)),
            ema_slow       = int(qc.get('ema4h_slow', 50)),
            confirm_tf_min = int(qc.get('confirm_tf_min', 15)),
            vol_med_window = int(qc.get('vol_med_window', 48)),
        )
        df5 = df_5m.copy()
        df5['atr'] = IndicatorEngine.atr(df5, 14)
        C   = df5['Close'].values.astype(float)
        O   = df5['Open'].values.astype(float)
        H   = df5['High'].values.astype(float)
        L   = df5['Low'].values.astype(float)
        ATR = df5['atr'].values.astype(float)
        TM  = df5.index
        Z   = np.zeros(len(C))   # E100/E200 QWE'de kullanılmaz (imza uyumu)

        brain = QweBrain(bias_provider=None)   # ZORUNLU none
        if self.state.qwe_used:
            brain.mark_used(self.state.qwe_used)
        self._qwe_brain = brain                # log/teşhis için

        n     = len(C)
        start = max(0, n - self.LOOKBACK_QWE - 1)
        end   = n - 1
        last_signal: Optional[TradeSignal] = None
        for idx in range(start, end + 1):
            sig = brain.evaluate(
                idx=idx, C=C, O=O, H=H, L=L, E100=Z, E200=Z, TM=TM,
                msb_events_bull=[], msb_events_bear=[], ATR=ATR, **kw)
            if idx == end:
                last_signal = sig
        return last_signal

    def _find_signal_london(self, df_5m: pd.DataFrame,
                            df_1h: pd.DataFrame) -> Optional[TradeSignal]:
        """London Reversal canlı sinyali. Bias = PRIVATE (GARCH, 1H'den
        otomatik — prompt YOK). Bağlam (Asya range + PDH/PDL) backtest ile
        aynı hesaplayıcıdan. Pencere 288 bar: gün içi daily-limit state'i
        yeniden kurulur; yalnız SON kapanan barın sinyali kullanılır."""
        from config import get_config
        lc = get_config().section('london_reversal')
        ASIAN_H, ASIAN_L = AsianRangeCalculator.compute(
            df_5m, int(lc.get('asian_start_utc', 23)),
            int(lc.get('asian_end_utc', 6)))
        kw = {'asian_high': ASIAN_H, 'asian_low': ASIAN_L}
        if bool(lc.get('use_pdh_pdl', True)):
            PDH, PDL = AsianRangeCalculator.compute_pdhl(df_5m)
            kw['pdh'] = PDH; kw['pdl'] = PDL
        df5 = df_5m.copy()
        df5['atr'] = IndicatorEngine.atr(df5, 14)
        C = df5['Close'].values.astype(float)
        O = df5['Open'].values.astype(float)
        H = df5['High'].values.astype(float)
        L = df5['Low'].values.astype(float)
        ATR = df5['atr'].values.astype(float)
        TM  = df5.index
        Z   = np.zeros(len(C))
        brain = LondonReversalBrain(
            bias_provider=PrivateBiasProvider(df_1h))
        self._london_brain = brain
        n = len(C); start = max(0, n - 288 - 1); end = n - 1
        last = None
        for idx in range(start, end + 1):
            sig = brain.evaluate(idx=idx, C=C, O=O, H=H, L=L,
                                 E100=Z, E200=Z, TM=TM,
                                 msb_events_bull=[], msb_events_bear=[],
                                 ATR=ATR, **kw)
            if idx == end:
                last = sig
        return last

    def _check_3v_be(self) -> None:
        """ThreeVol yazılımsal BE@1R: fiyat +1R'a değince silahlanır;
        sonra girişe sararsa pozisyon market'ten kapatılır. Borsa SL'i
        felaket-stopu olarak yerinde kalır. (5dk örnekleme — bar içi
        spike'ları kaçırabilir; backtest'teki anlık BE'nin yaklaşığıdır.)"""
        if (self.dry_run or not self.state.active
                or self.state.signal_type != 'EMA+3VOL'
                or self.state.be_arm_price is None):
            return
        try:
            pos = self.client.get_position()
            if not pos:
                return
            mark = float(pos.get('markPrice') or pos.get('avgPrice') or 0)
            if mark <= 0:
                return
            d = self.state.direction
            if not self.state.be_armed:
                reached = (mark >= self.state.be_arm_price if d == 'bull'
                           else mark <= self.state.be_arm_price)
                if reached:
                    self.state.be_armed = True
                    self.state._write()
                    print("  3VOL: +1R görüldü → yazılımsal BE aktif")
            if self.state.be_armed:
                against = (mark <= self.state.entry if d == 'bull'
                           else mark >= self.state.entry)
                if against:
                    print("  3VOL: BE — fiyat girişe sardı, pozisyon kapatılıyor")
                    self.client.close_position()
                    self.client.cancel_all_orders()
                    self.state.clear()
        except Exception as e:
            print(f"  3VOL BE kontrol hatası: {e}")

    def _enter_trade_partial(self, signal: TradeSignal,
                             equity: float, last_close: float,
                             min_rr: float, label: str,
                             setup_key=None) -> None:
        """
        Kısmi-TP girişi (QWE ve LONDON): İKİ yarım market emri — yarım TP1
        (kısmi kâr), yarım TP2 (runner); ikisinde de borsa-taraflı SL.
        Backtest'teki TP1-sonrası BE, canlıda YAZILIMSAL yaklaşıklıkla
        sağlanır (_check_position: TP1 dolunca fiyat girişe sararsa kalan
        yarım market'ten kapatılır; borsa SL'i felaket-stopu olarak kalır).
        """
        entry = last_close
        tp2   = signal.tp_hint
        tp1v  = signal.tp1_hint
        r = self.risk_mgr.compute(signal.direction, entry, signal.stop_price,
                                  equity, signal.risk_fraction, tp_override=tp2)
        if r is None:
            print("  Risk hesabı geçersiz — işlem atlandı")
            return
        sl = r['sl']
        # MIN_RR kapısı (backtest ile tutarlı)
        risk_per = abs(entry - sl)
        if risk_per < 0.01 or abs(tp2 - entry) / max(risk_per, 0.01) < min_rr:
            print(f"  RR < {min_rr} — işlem atlandı")
            return
        # TP1 geçerliliği (giriş HH'in gerisinde olmalı)
        if signal.direction == 'bull':
            tp1 = tp1v if (tp1v > entry and tp1v < tp2) else None
        else:
            tp1 = tp1v if (tp1v < entry and tp1v > tp2) else None

        # HER İŞLEM EŞİT 1R: risk = kasa × risk_pct (konfluens ölçeği YOK)
        actual_risk = equity * self.risk_pct
        qty  = compute_lot(entry, sl, actual_risk)
        half = round(qty / 2, 3)
        two_legs = tp1 is not None and half >= 0.001
        if qty < 0.001:
            print(f"  Lot çok küçük ({qty:.4f}) — işlem atlandı")
            return
        side = 'BUY' if signal.direction == 'bull' else 'SELL'

        print(f"\n  ┌── {label} SİNYAL: {signal.direction.upper()} ─────────────")
        print(f"  │  Tip   : {signal.confirmation_type} ({signal.msb_type})")
        print(f"  │  Entry : ~{entry:.2f}   SL: {sl:.2f}")
        if two_legs:
            print(f"  │  TP1   : {tp1:.2f}  (yarım {half} oz — kısmi kâr)")
            print(f"  │  TP2   : {tp2:.2f}  (yarım {half} oz — runner)")
            print(f"  │  BE    : TP1 dolunca yazılımsal breakeven aktif")
        else:
            print(f"  │  TP    : {tp2:.2f}  (tek emir {qty} oz)")
        print(f"  │  Risk  : ${actual_risk:.2f}  |  Kasa: ${equity:.2f}")
        print(f"  │  TBE   : kapalı (swing)")
        print(f"  └{'─'*40}")

        legs = ([(half, tp1), (half, tp2)] if two_legs else [(qty, tp2)])
        skey = setup_key

        if self.dry_run:
            for q, tp in legs:
                print(f"  [DRY-RUN] {side} {q} oz  SL={sl:.2f} TP={tp:.2f}")
            print()
            self.state.save(order_id='DRY-RUN', direction=signal.direction,
                            entry=entry, sl=sl, tp=tp2, qty=qty,
                            signal_type=label, tbe_minutes=None,
                            orders=[{'order_id': 'DRY-RUN', 'tp': tp, 'qty': q}
                                    for q, tp in legs],
                            setup_key=skey)
            return
        try:
            placed = []
            for q, tp in legs:
                res = self.client.place_order(side, q, sl, tp)
                placed.append({'order_id': res.get('orderId', 'N/A'),
                               'tp': tp, 'qty': q})
                print(f"  ✓  Order: #{placed[-1]['order_id']} "
                      f"{q} oz TP={tp:.2f}")
            print()
            self.state.save(order_id=placed[0]['order_id'],
                            direction=signal.direction, entry=entry, sl=sl,
                            tp=tp2, qty=qty, signal_type=label,
                            tbe_minutes=None, orders=placed, setup_key=skey)
        except Exception as e:
            print(f"  ✗  ORDER HATASI: {e}\n")

    def _check_qwe_partial(self) -> None:
        """QWE canlı: TP1 dolumu tespiti + yazılımsal breakeven."""
        if self.dry_run or self.state.signal_type not in ('QWE', 'LONDON-REV') \
                or len(self.state.orders) < 2:
            return
        try:
            pos = self.client.get_position()
            if not pos:
                return   # tam kapanış _check_position'da ele alınır
            amt   = abs(float(pos.get('positionAmt', 0)))
            half  = float(self.state.orders[0]['qty'])
            if not self.state.tp1_filled and amt <= half * 1.05:
                self.state.tp1_filled = True
                self.state._write()
                print("  QWE: TP1 doldu → yazılımsal BE aktif (kalan runner)")
            if self.state.tp1_filled:
                mark = float(pos.get('markPrice') or pos.get('avgPrice') or 0)
                if mark > 0:
                    against = (mark <= self.state.entry
                               if self.state.direction == 'bull'
                               else mark >= self.state.entry)
                    if against:
                        print("  QWE: BE — fiyat girişe sardı, runner kapatılıyor")
                        self.client.close_position()
                        self.client.cancel_all_orders()
                        self.state.clear()
        except Exception as e:
            print(f"  QWE kısmi kontrol hatası: {e}")

    # ── İşlem aç ─────────────────────────────────────────────────────────────
    def _apply_swing_stop(self, signal: TradeSignal, entry: float) -> None:
        """fvg/threevol preset'i: SL'i son onaylı 1H swing yapısına genişlet
        (backtest ile AYNI fonksiyon: BacktestEngine.swing_stop_price)."""
        try:
            from config import get_config
            if not bool(get_config().get(self.strategy, 'swing_stop',
                                         default=False)):
                return
            df1 = getattr(self, '_df1h_cache', None)
            if df1 is None or len(df1) < 20:
                return
            H1 = df1['High'].values.astype(float)
            L1 = df1['Low'].values.astype(float)
            A1 = IndicatorEngine.atr(df1, 14).values.astype(float)
            T1 = np.array([to_naive(t).timestamp() for t in df1.index])
            ets = to_naive(signal.entry_time).timestamp() \
                if signal.entry_time is not None else T1[-1] + 3600
            sw = BacktestEngine.swing_stop_price(
                signal.direction, entry, ets, H1, L1, T1, A1)
            if sw is None:
                return
            wider = (sw < signal.stop_price if signal.direction == 'bull'
                     else sw > signal.stop_price)
            if wider:
                print(f"  Swing stop: {signal.stop_price:.2f} → {sw:.2f} "
                      f"(1H yapı)")
                signal.stop_price = sw
        except Exception as e:
            print(f"  swing-stop hesabı atlandı: {e}")

    def _enter_trade(self, signal: TradeSignal,
                     equity: float, last_close: float) -> None:
        entry = last_close
        self._apply_swing_stop(signal, entry)

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
        # HER İŞLEM EŞİT 1R: risk = kasa × risk_pct (konfluens ölçeği kaldırıldı;
        # tüm stratejiler/sinyaller aynı dolar riskini taşır)
        actual_risk      = equity * self.risk_pct
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
        print(f"  │  Risk  : ${actual_risk:.2f} ({self.risk_pct*100:.1f}% — "
              f"her işlem eşit 1R)  [stop olursa kayıp]")
        print(f"  │  Kasa  : ${equity:.2f}  |  Kaldıraç: {self.leverage}x")
        print(f"  │  Pozis.: ${notional:.2f} notional  |  Marjin: ${margin:.2f}")
        if margin > equity:
            print(f"  │  ⚠ Gereken marjin (${margin:.2f}) kasadan büyük — "
                  f"kaldıracı artırın")
        tbe_str = f"{self.tbe_minutes}dk ({self.tbe_minutes//60}h)" \
                  if self.tbe_minutes else "kapalı"
        print(f"  │  TBE   : {tbe_str}")
        print(f"  └{'─'*40}")

        # LİMİT giriş modu (config: <strateji>.entry_order = 'limit'):
        # limit fiyatı = kapanış ∓ spread (bid/ask tarafı); dolmazsa
        # W×5dk sonra iptal (_check_position pending yaşam döngüsü).
        from config import get_config as _gc
        use_limit = (_gc().get(self.strategy, 'entry_order',
                               default='market') == 'limit')
        if use_limit:
            spread = float(_gc().get('costs', 'spread_usd', default=0.30)) or 0.30
            wbars  = int(_gc().get(self.strategy, 'limit_entry_bars', default=3))
            lim = (entry - spread if signal.direction == 'bull'
                   else entry + spread)
            from datetime import timedelta as _td
            expire = (datetime.utcnow() + _td(minutes=5 * wbars)).isoformat()
            print(f"  LİMİT giriş: {lim:.2f} (spread dahil)  "
                  f"— {wbars} bar içinde dolmazsa iptal")
            if self.dry_run:
                print("  [DRY-RUN] LIMIT order gönderilmedi (dolum varsayıldı).\n")
                self.state.save(order_id='DRY-RUN', direction=signal.direction,
                                entry=lim, sl=r['sl'], tp=r['tp'], qty=qty,
                                signal_type=label, tbe_minutes=self.tbe_minutes)
                return
            try:
                res = self.client.place_limit_order(side, qty, lim,
                                                    r['sl'], r['tp'])
                self.state.save(order_id=res.get('orderId', 'N/A'),
                                direction=signal.direction, entry=lim,
                                sl=r['sl'], tp=r['tp'], qty=qty,
                                signal_type=label, tbe_minutes=self.tbe_minutes)
                self.state.pending_entry = True
                self.state.entry_expire  = expire
                self.state._write()
                print(f"  ✓  LIMIT order kondu: #{self.state.order_id}\n")
            except Exception as e:
                print(f"  ✗  LIMIT ORDER HATASI: {e}\n")
            return

        if self.dry_run:
            print("  [DRY-RUN] Order gönderilmedi.\n")
            self.state.save(
                order_id    = 'DRY-RUN',
                direction   = signal.direction,
                entry       = entry,
                sl          = r['sl'],
                tp          = r['tp'],
                qty         = qty,
                signal_type = label,
                tbe_minutes = self.tbe_minutes,
            )
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
                tbe_minutes = self.tbe_minutes,
            )
        except Exception as e:
            print(f"  ✗  ORDER HATASI: {e}\n")

    # ── Pozisyon kontrolü ─────────────────────────────────────────────────────
    def _check_position(self) -> None:
        """
        Kaydedilmiş pozisyon BingX'te kapandıysa state'i temizler.
        TBE süresi dolduysa pozisyonu market'ten kapatır.
        """
        if not self.state.active:
            return
        # ── Bekleyen LİMİT emri: doldu mu / süresi doldu mu? ────────────────
        if self.state.pending_entry and not self.dry_run:
            try:
                pos = self.client.get_position()
                if pos and abs(float(pos.get('positionAmt', 0))) > 0:
                    self.state.pending_entry = False
                    self.state.open_time = datetime.utcnow().isoformat()
                    # threevol: BE kolunu dolum sonrası kur
                    if self.state.signal_type == 'EMA+3VOL':
                        dist = abs(self.state.entry - self.state.sl)
                        self.state.be_arm_price = (
                            self.state.entry + dist
                            if self.state.direction == 'bull'
                            else self.state.entry - dist)
                        self.state.be_armed = False
                    self.state._write()
                    print("  LIMIT emir DOLDU → pozisyon aktif")
                elif (self.state.entry_expire and
                      datetime.utcnow() >
                      datetime.fromisoformat(self.state.entry_expire)):
                    print("  LIMIT emir dolmadı → iptal (sinyal kaçtı)")
                    self.client.cancel_all_orders()
                    self.state.clear()
            except Exception as e:
                print(f"  pending kontrol hatası: {e}")
            return
        if self.dry_run:
            # Dry-run: sadece TBE süresini logla
            if self.state.tbe_minutes and self.state.open_time:
                open_dt  = datetime.fromisoformat(self.state.open_time)
                elapsed  = (datetime.utcnow() - open_dt).total_seconds() / 60
                remaining = self.state.tbe_minutes - elapsed
                if remaining <= 0:
                    print(f"  [DRY-RUN] TBE: {elapsed:.0f}dk geçti → "
                          f"gerçekte market'ten kapatılırdı.")
                    self.state.clear()
            return
        try:
            # ── TBE kontrolü (TP/SL'den önce) ───────────────────────────────
            if self.state.tbe_minutes and self.state.open_time:
                open_dt = datetime.fromisoformat(self.state.open_time)
                elapsed = (datetime.utcnow() - open_dt).total_seconds() / 60
                if elapsed >= self.state.tbe_minutes:
                    print(f"  TBE: {elapsed:.0f}dk geçti "
                          f"({self.state.tbe_minutes}dk limit) → pozisyon kapatılıyor")
                    self.client.close_position()
                    self.state.clear()
                    return

            # ── Normal TP/SL kontrolü ────────────────────────────────────────
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
        strat_desc = {
            'qwe':      'QWE — fib pullback swing (618, 15M onay) [none sabit]',
            'fvg':      'FVG intraday [none+EMA+blackout 09-11 sabit]',
            'threevol': 'ThreeVol momentum [none+EMA+blackout+BE@1R sabit]',
            'london':   'London Reversal [private(GARCH)+w6 sabit, kısmi TP]',
        }[self.strategy]
        print(f"  Strateji: {strat_desc}")
        print(f"  Sembol : {self.client.symbol}")
        print(f"  Risk   : {self.risk_pct*100:.1f}%  |  "
              f"Kaldıraç: {self.leverage}x")
        kasa_str = (f"${self.capital:.2f} (manuel)" if self.capital > 0
                    else "API bakiyesi")
        print(f"  Kasa   : {kasa_str}")
        print(f"  Mod    : {'DRY-RUN  ⚠️' if self.dry_run else 'CANLI  ✓'}")
        if self.strategy == 'qwe':
            print("  Bias   : NONE — ZORUNLU (QWE swing: bias kapısı yok)")
        elif self.bias_provider is not None:
            print(f"  Bias   : {self.bias_provider.mode.upper()} (terminal prompt)")
        else:
            print("  Bias   : NONE (EMA zorunlu, bias yok)")
        tbe_str = (f"{self.tbe_minutes}dk ({self.tbe_minutes//60}h) — "
                   f"süre dolunca market kapat"
                   if self.tbe_minutes else "kapalı")
        print(f"  TBE    : {tbe_str}")
        print("═" * 58)

        # Sembol borsada gerçekten var mı? (yanlış sembol = sessiz hata önler)
        if not self.client.verify_symbol():
            print("  Doğru sembolle tekrar çalıştırın. Çıkılıyor.")
            return

        # Kaldıraç ayarla (canlı modda)
        if not self.dry_run:
            try:
                self.client.set_leverage(self.leverage)
                print(f"  Kaldıraç {self.leverage}x ayarlandı.")
            except Exception as e:
                print(f"  Kaldıraç ayar hatası: {e}")

        # MarketBrain yalnız fvg yolunda gerekir (qwe kendi brain'ini tick
        # başına taze kurar)
        brain = (MarketBrain(bias_provider=self.bias_provider)
                 if self.strategy == 'fvg' else None)
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

                # ── Pozisyon kapandı mı? (+ QWE kısmi-TP / yazılımsal BE) ────
                self._check_qwe_partial()
                self._check_3v_be()
                self._check_position()

                # ── Veri çek (QWE: 4H EMA50 ısınması için ~37 gün 1H) ────────
                df_5m = LiveDataEngine.fetch(self.client, '5m', 900)
                df_1h = LiveDataEngine.fetch(
                    self.client, '1h', 900 if self.strategy == 'qwe' else 200)

                last_close = float(df_5m['Close'].iloc[-1])
                self._df1h_cache = df_1h        # swing-stop hesabı için
                self._log_bar(now, last_close, current_bias)

                # ── Sinyal yalnız açık pozisyon yokken ───────────────────────
                if not self.state.active:
                    def _equity():
                        return (self.capital if self.capital > 0 else
                                (self.client.get_balance()
                                 if not self.dry_run else 10_000.0))

                    if self.strategy == 'qwe':
                        signal = self._find_signal_qwe(df_5m, df_1h)
                        if signal is not None:
                            self._enter_trade_partial(
                                signal, _equity(), last_close,
                                min_rr=float(self._qcfg.get('min_rr', 1.5)),
                                label='QWE',
                                setup_key=getattr(self._qwe_brain,
                                                  'last_setup_key', None))
                        else:
                            reason = (self._qwe_brain.last_skip_reason
                                      if hasattr(self, '_qwe_brain') else '—')
                            print(f"  Sinyal: yok  ({reason or '—'})")
                        continue

                    if self.strategy == 'london':
                        signal = self._find_signal_london(df_5m, df_1h)
                        if signal is not None:
                            from config import get_config
                            lmin = float(get_config().get(
                                'london_reversal', 'min_rr', default=1.5))
                            self._enter_trade_partial(
                                signal, _equity(), last_close,
                                min_rr=lmin, label='LONDON-REV')
                        else:
                            reason = (self._london_brain.last_skip_reason
                                      if hasattr(self, '_london_brain') else '—')
                            print(f"  Sinyal: yok  ({reason or '—'})")
                        continue

                    if self.strategy == 'threevol':
                        # Rejim kapısı: volatilite tabanı (nedensel — dünün
                        # verisiyle; backtest RegimeEngine ile birebir)
                        from config import get_config as _gc
                        from xauusd_fvg_engine_v10 import RegimeEngine
                        vf = float(_gc().get('threevol', 'vol_floor',
                                             default=0.0))
                        if vf > 0:
                            vnow = RegimeEngine.daily_vol_pct(df_1h).iloc[-1]
                            if pd.notna(vnow) and vnow < vf:
                                print(f"  Rejim: UYKU — günlük vol "
                                      f"{vnow:.2f} < taban {vf} (3VOL bekliyor)")
                                continue
                        ctx = self._run_all_detections(df_5m, df_1h)
                        brain3 = ThreeVolBrain(bias_provider=None)
                        signal = self._find_signal(ctx, brain3)
                        if (signal is not None and self._blackout
                                and now.hour in self._blackout):
                            print(f"  Sinyal blackout saatinde "
                                  f"({now.hour}:xx UTC) — atlandı")
                            signal = None
                        if signal is not None:
                            self._enter_trade(signal, _equity(), last_close)
                            # Yazılımsal BE@1R kolu (preset: 1:2be)
                            if self.state.active:
                                dist = abs(self.state.entry - self.state.sl)
                                self.state.be_arm_price = (
                                    self.state.entry + dist
                                    if self.state.direction == 'bull'
                                    else self.state.entry - dist)
                                self.state.be_armed = False
                                self.state._write()
                        else:
                            print(f"  Sinyal: yok  "
                                  f"({brain3.last_skip_reason or '—'})")
                        continue

                    ctx = self._run_all_detections(df_5m, df_1h)

                    # Her tickte pending'i sıfırla; LOOKBACK ile yeniden kur
                    brain.pending      = {'bull': [], 'bear': []}
                    brain.used_fvg_ids = set()

                    signal = self._find_signal(ctx, brain)

                    # Preset: fvg blackout saatlerinde giriş yok (09-11 UTC)
                    if (signal is not None and self._blackout
                            and now.hour in self._blackout):
                        print(f"  Sinyal blackout saatinde ({now.hour}:xx UTC) — atlandı")
                        signal = None

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
    "symbol":     "NCCGOLD2USD-USDT",  # = uygulamadaki 'GOLD(XAU)-USDT'
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
        '--strategy', choices=['fvg', 'qwe', 'threevol', 'london'], default=None,
        help="Strateji (hepsi SABİT preset): fvg (none+EMA+blackout) | "
             "qwe (none, swing) | threevol (none+EMA+blackout+BE@1R) | "
             "london (private/GARCH otomatik, kısmi TP)",
    )
    parser.add_argument(
        '--bias', choices=['weekly', 'daily', 'none'], default='weekly',
        help='Bias modu (yalnız fvg): weekly=haftalık, daily=günlük, none=yok. '
             'QWE stratejisinde YOK SAYILIR (zorunlu none).',
    )
    parser.add_argument('--leverage', type=int,   default=None,
                        help='Kaldıraç (config varsayılanını geçersiz kılar)')
    parser.add_argument('--risk-pct', type=float, default=None,
                        help='Risk yüzdesi, örn. 1.0 = %%1')
    parser.add_argument('--balance',  type=float, default=None,
                        help='Kasa ($). Girilirse API bakiyesi yerine bu kullanılır')
    parser.add_argument('--symbol',   default=None,
                        help='BingX API sembolü (varsayılan: NCCGOLD2USD-USDT '
                             '= uygulamadaki GOLD(XAU)-USDT)')
    parser.add_argument('--config',   default='live_config.json',
                        help='Config dosyası yolu')
    parser.add_argument('--dry-run',  action='store_true',
                        help='Kağıt işlem — BingX\'e order gönderilmez')
    parser.add_argument('--tbe',      type=int, default=None,
                        help='Zaman bazlı çıkış (dakika). Varsayılan: '
                             'weekly/none=480dk, daily=kapalı. 0=zorla kapat')
    parser.add_argument('--close',    action='store_true',
                        help='Açık pozisyonu market\'ten kapat ve çık')
    args = parser.parse_args()

    cfg = load_config(args.config)

    api_key    = cfg.get('api_key',    '')
    api_secret = cfg.get('api_secret', '')
    symbol     = args.symbol   or cfg.get('symbol',   'NCCGOLD2USD-USDT')
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

    # Strateji: CLI > live_config.json > config/default.json (live.strategy) > fvg
    strategy = args.strategy or cfg.get('strategy')
    if not strategy:
        try:
            from config import get_config
            strategy = get_config().get('live', 'strategy', default='fvg')
        except Exception:
            strategy = 'fvg'

    # Bias provider — SABİT PRESET'ler: bias prompt'u HİÇ kurulmaz
    # (fvg/threevol/qwe: none; london: private/GARCH otomatik)
    if strategy in ('qwe', 'fvg', 'threevol', 'london'):
        if args.bias != 'weekly':   # kullanıcı açıkça bias istediyse uyar
            print(f"  Not: {strategy.upper()} sabit preset — "
                  f"--bias {args.bias} yok sayıldı (bias=none).")
        bias_provider = None
    elif args.bias == 'none':
        bias_provider = None
    else:
        bias_provider = InteractiveBiasProvider(args.bias)

    # TBE: --tbe 0 → kapalı, --tbe N → N dakika, --tbe yok → bias'a göre otomatik
    tbe_minutes = -1  # -1 = otomatik
    if args.tbe is not None:
        tbe_minutes = None if args.tbe == 0 else args.tbe

    trader = LiveTrader(
        client        = client,
        bias_provider = bias_provider,
        bias_mode     = args.bias,
        leverage      = leverage,
        risk_pct      = risk_pct,
        capital       = capital,
        dry_run       = args.dry_run,
        tbe_minutes   = tbe_minutes,
        strategy      = strategy,
    )
    trader.run()


if __name__ == '__main__':
    main()
