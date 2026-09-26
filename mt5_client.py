# -*- coding: utf-8 -*-
"""
mt5_client.py — MetaTrader 5 broker istemcisi
==============================================
BingXClient ile BİREBİR AYNI arayüzü uygular, böylece LiveTrader tek satır
değişmeden MT5 üzerinden çalışır:

    klines · verify_symbol · get_depth · get_recent_trades · get_balance
    get_position · set_leverage · place_order · place_limit_order
    cancel_all_orders · close_position   (+ .symbol niteliği)

PLATFORM: MetaTrader5 Python paketi YALNIZCA Windows'ta ve MT5 terminali ile
AYNI makinede çalışır. Linux'ta import edilemez — bu dosya o durumda anlamlı
bir hata verir, sessizce çökmez.

BingX ile ARASINDAKİ ÜÇ ÖNEMLİ FARK (hepsi bu dosyada kapatılır):

1. MİKTAR BİRİMİ. BingX ons cinsinden miktar alır; MT5 LOT alır ve XAUUSD'de
   1 lot genelde 100 ons'tur. Bu istemci dışarıya ONS arayüzü verir, içeride
   lota çevirir (`trade_contract_size`), broker'ın volume_step/min/max
   sınırlarına yuvarlar. Yanlış çevirim 100 kat pozisyon demektir.

2. ZAMAN DİLİMİ. MT5 mum zamanları BROKER sunucu saatindedir (çoğu broker
   UTC+2/+3, yaz saatiyle değişir), motor ise UTC-naive bekler. Sistemin
   blackout saatleri (09–11 UTC) ve günlük barları buna bağlı olduğu için
   kayma sessiz ama ciddi hasar verir. Bu istemci son barın zamanını gerçek
   UTC ile karşılaştırıp offset'i OTOMATİK bulur (saate yuvarlar), config ile
   ezilebilir (`live.mt5.time_offset_hours`).

3. TAPE YOK. MT5'te BingX'teki gibi genel "son işlemler" akışı yoktur, bu
   yüzden OrderFlowGuard'ın CVD bileşeni MT5'te ÇALIŞAMAZ; get_recent_trades
   boş döner ve guard CVD'yi atlar (imbalance, DOM açıksa çalışır).

Kaldıraç MT5'te hesap/sembol seviyesinde brokerca belirlenir; set_leverage
bilinçli olarak NO-OP'tur (sessizce yok saymak yerine bunu loglar).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

try:
    import MetaTrader5 as mt5
except Exception as _e:                                   # pragma: no cover
    mt5 = None
    _IMPORT_ERR = _e
else:
    _IMPORT_ERR = None


_TF = {}
if mt5 is not None:
    _TF = {
        '1m': mt5.TIMEFRAME_M1,   '5m': mt5.TIMEFRAME_M5,
        '15m': mt5.TIMEFRAME_M15, '30m': mt5.TIMEFRAME_M30,
        '1h': mt5.TIMEFRAME_H1,   '4h': mt5.TIMEFRAME_H4,
        '1d': mt5.TIMEFRAME_D1,
    }


class MT5Client:
    """MetaTrader 5 istemcisi — BingXClient arayüzü."""

    def __init__(self, symbol: str = 'XAUUSD',
                 login: int = 0, password: str = '', server: str = '',
                 terminal_path: str = '',
                 time_offset_hours: Optional[float] = None,
                 deviation: int = 20, magic: int = 20261005):
        if mt5 is None:
            raise RuntimeError(
                "MetaTrader5 paketi yüklenemedi (%s).\n"
                "  MT5 Python paketi YALNIZCA Windows'ta ve MT5 terminali ile\n"
                "  aynı makinede çalışır. Kurulum:  pip install MetaTrader5"
                % _IMPORT_ERR)

        self.symbol = symbol
        self.deviation = int(deviation)
        self.magic = int(magic)
        self._offset_cfg = time_offset_hours
        self._offset: Optional[float] = None

        kw: dict = {}
        if terminal_path:
            kw['path'] = terminal_path
        if login:
            kw.update(login=int(login), password=password, server=server)
        if not mt5.initialize(**kw):
            raise RuntimeError("mt5.initialize() başarısız: %s"
                               % (mt5.last_error(),))

        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(
                "Sembol '%s' bulunamadı. Broker'lar farklı adlar kullanır "
                "(XAUUSD, XAUUSD.a, GOLD, XAUUSDm...). MT5'te Market Watch'a "
                "ekleyip config'e doğru adı yazın." % symbol)
        if not info.visible and not mt5.symbol_select(symbol, True):
            raise RuntimeError("Sembol '%s' Market Watch'a eklenemedi" % symbol)

        self.info = mt5.symbol_info(symbol)
        # 1 lot kaç ons? XAUUSD'de tipik olarak 100.
        self.contract_size = float(getattr(self.info, 'trade_contract_size',
                                           100.0) or 100.0)
        self.vol_min = float(getattr(self.info, 'volume_min', 0.01) or 0.01)
        self.vol_max = float(getattr(self.info, 'volume_max', 100.0) or 100.0)
        self.vol_step = float(getattr(self.info, 'volume_step', 0.01) or 0.01)
        self.digits = int(getattr(self.info, 'digits', 2) or 2)
        self._filling = self._pick_filling()

    # ── kurulum yardımcıları ────────────────────────────────────────────
    def _pick_filling(self) -> int:
        """Broker'ın desteklediği dolum modunu seç. Yanlış mod 'Unsupported
        filling mode' hatası verir ve emir HİÇ gitmez."""
        mode = int(getattr(self.info, 'filling_mode', 0) or 0)
        if mode & 1:
            return mt5.ORDER_FILLING_FOK
        if mode & 2:
            return mt5.ORDER_FILLING_IOC
        return mt5.ORDER_FILLING_RETURN

    def _utc_offset(self) -> float:
        """Broker sunucu saati ile UTC arasındaki fark (saat).
        Son M1 barının zamanı ile gerçek UTC karşılaştırılıp saate yuvarlanır;
        böylece yaz saati geçişleri kendiliğinden düzelir."""
        if self._offset_cfg is not None:
            return float(self._offset_cfg)
        if self._offset is not None:
            return self._offset
        r = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M1, 0, 1)
        if r is None or not len(r):
            self._offset = 0.0
            return 0.0
        srv = float(r[-1]['time'])
        now = datetime.now(timezone.utc).timestamp()
        self._offset = round((srv - now) / 3600.0)
        return self._offset

    # ── piyasa verisi ───────────────────────────────────────────────────
    def klines(self, interval: str, limit: int = 900) -> list:
        """[[ts_ms_UTC, open, high, low, close, volume], ...] — BingX formatı.
        Son (kapanmamış) bar dahil döner; LiveDataEngine.fetch onu atar."""
        tf = _TF.get(interval)
        if tf is None:
            raise ValueError("desteklenmeyen zaman dilimi: %s" % interval)
        r = mt5.copy_rates_from_pos(self.symbol, tf, 0, int(limit))
        if r is None or not len(r):
            return []
        off = self._utc_offset() * 3600.0
        return [[int((float(b['time']) - off) * 1000),
                 float(b['open']), float(b['high']), float(b['low']),
                 float(b['close']), float(b['tick_volume'])] for b in r]

    def verify_symbol(self) -> bool:
        return mt5.symbol_info(self.symbol) is not None

    def get_depth(self, limit: int = 20) -> dict:
        """DOM. Broker yayınlamıyorsa boş döner (guard imbalance'ı atlar)."""
        try:
            mt5.market_book_add(self.symbol)
            book = mt5.market_book_get(self.symbol)
        except Exception:
            book = None
        if not book:
            return {'bids': [], 'asks': []}
        bids = [[float(i.price), float(i.volume)] for i in book
                if i.type == mt5.BOOK_TYPE_BUY][:limit]
        asks = [[float(i.price), float(i.volume)] for i in book
                if i.type == mt5.BOOK_TYPE_SELL][:limit]
        return {'bids': bids, 'asks': asks}

    def get_recent_trades(self, limit: int = 200) -> list:
        """MT5'te genel tape YOKTUR → boş. OrderFlowGuard CVD'yi atlar."""
        return []

    # ── hesap / pozisyon ────────────────────────────────────────────────
    def get_balance(self) -> float:
        a = mt5.account_info()
        return float(getattr(a, 'margin_free', 0.0)) if a else 0.0

    def get_position(self) -> Optional[dict]:
        """BingX uyumlu dict; 'positionAmt' İŞARETLİ ONS (long +, short −)."""
        pos = mt5.positions_get(symbol=self.symbol)
        if not pos:
            return None
        net = 0.0
        first = pos[0]
        for p in pos:
            lots = float(p.volume) * (1 if p.type == mt5.POSITION_TYPE_BUY
                                      else -1)
            net += lots
        if abs(net) < 1e-9:
            return None
        return {
            'symbol': self.symbol,
            'positionAmt': net * self.contract_size,      # ons
            'positionSide': 'LONG' if net > 0 else 'SHORT',
            'entryPrice': float(first.price_open),
            'unrealizedProfit': float(sum(p.profit for p in pos)),
            'ticket': int(first.ticket),
        }

    def set_leverage(self, leverage: int) -> None:
        """MT5'te kaldıraç hesap/sembol bazında BROKER tarafından belirlenir;
        API'den ayarlanamaz. Sessiz geçmek yerine bildirilir."""
        print("  MT5: kaldıraç API'den ayarlanamaz (broker hesap ayarı). "
              "İstenen %sx yok sayıldı." % leverage)

    # ── emirler ─────────────────────────────────────────────────────────
    def _lots(self, qty_oz: float) -> float:
        """Ons → lot; broker adımına yuvarla ve sınırlara kelepçele."""
        lots = float(qty_oz) / self.contract_size
        lots = math.floor(lots / self.vol_step + 1e-9) * self.vol_step
        lots = max(self.vol_min, min(self.vol_max, lots))
        return round(lots, 8)

    def _send(self, req: dict) -> dict:
        res = mt5.order_send(req)
        if res is None:
            raise RuntimeError("order_send None döndü: %s" % (mt5.last_error(),))
        if res.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError("MT5 emir reddedildi: retcode=%s comment=%s"
                               % (res.retcode, getattr(res, 'comment', '')))
        return {'orderId': int(res.order), 'price': float(res.price),
                'volume': float(res.volume), 'retcode': int(res.retcode)}

    def place_order(self, side: str, qty: float,
                    sl: float, tp: float) -> dict:
        """Market emir + SL/TP. side: 'BUY' | 'SELL', qty ONS cinsinden."""
        tick = mt5.symbol_info_tick(self.symbol)
        is_buy = side.upper() == 'BUY'
        return self._send({
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': self.symbol,
            'volume': self._lots(qty),
            'type': mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
            'price': float(tick.ask if is_buy else tick.bid),
            'sl': round(float(sl), self.digits),
            'tp': round(float(tp), self.digits),
            'deviation': self.deviation,
            'magic': self.magic,
            'comment': 'xauusd-fvg',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': self._filling,
        })

    def place_limit_order(self, side: str, qty: float, price: float,
                          sl: float, tp: float) -> dict:
        """Bekleyen LIMIT emir + SL/TP. qty ONS cinsinden."""
        is_buy = side.upper() == 'BUY'
        return self._send({
            'action': mt5.TRADE_ACTION_PENDING,
            'symbol': self.symbol,
            'volume': self._lots(qty),
            'type': (mt5.ORDER_TYPE_BUY_LIMIT if is_buy
                     else mt5.ORDER_TYPE_SELL_LIMIT),
            'price': round(float(price), self.digits),
            'sl': round(float(sl), self.digits),
            'tp': round(float(tp), self.digits),
            'magic': self.magic,
            'comment': 'xauusd-fvg',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': self._filling,
        })

    def cancel_all_orders(self) -> None:
        orders = mt5.orders_get(symbol=self.symbol) or ()
        for o in orders:
            try:
                mt5.order_send({'action': mt5.TRADE_ACTION_REMOVE,
                                'order': int(o.ticket)})
            except Exception as e:
                print("  cancel_all_orders: %s" % e)

    def close_position(self) -> None:
        pos = mt5.positions_get(symbol=self.symbol)
        if not pos:
            return
        tick = mt5.symbol_info_tick(self.symbol)
        for p in pos:
            is_buy = p.type == mt5.POSITION_TYPE_BUY
            try:
                self._send({
                    'action': mt5.TRADE_ACTION_DEAL,
                    'symbol': self.symbol,
                    'volume': float(p.volume),
                    'type': (mt5.ORDER_TYPE_SELL if is_buy
                             else mt5.ORDER_TYPE_BUY),
                    'position': int(p.ticket),
                    'price': float(tick.bid if is_buy else tick.ask),
                    'deviation': self.deviation,
                    'magic': self.magic,
                    'comment': 'xauusd-fvg-close',
                    'type_time': mt5.ORDER_TIME_GTC,
                    'type_filling': self._filling,
                })
            except Exception as e:
                print("  close_position(%s): %s" % (p.ticket, e))
        print("  MT5: pozisyon(lar) market'ten kapatıldı.")

    # ── teşhis ──────────────────────────────────────────────────────────
    def describe(self) -> str:
        a = mt5.account_info()
        return ("MT5 bağlı | sembol %s | 1 lot = %.0f ons | lot adımı %.2f "
                "(min %.2f, max %.0f) | UTC offset %+.0f saat | hesap %s @ %s "
                "| bakiye %.2f %s"
                % (self.symbol, self.contract_size, self.vol_step,
                   self.vol_min, self.vol_max, self._utc_offset(),
                   getattr(a, 'login', '?'), getattr(a, 'server', '?'),
                   getattr(a, 'balance', 0.0), getattr(a, 'currency', '')))

    def shutdown(self) -> None:
        try:
            mt5.shutdown()
        except Exception:
            pass


def available() -> Tuple[bool, str]:
    """(kullanılabilir mi, sebep) — GUI menüsü bunu gösterir."""
    if mt5 is None:
        return False, ("MetaTrader5 paketi yok/yüklenemiyor — yalnızca "
                       "Windows'ta ve MT5 terminaliyle aynı makinede çalışır")
    return True, "hazır"
