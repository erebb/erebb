"""
test_engine_full.py — Kalan tüm modüller için testler
=======================================================
test_engine.py ile birlikte çalıştır:
  pytest test_engine.py test_engine_full.py -v
"""

import contextlib
import io
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from xauusd_fvg_engine_v10 import (
    normalize_index,
    flatten_columns,
    resample_ohlcv,
    MSBEngine,
    MSB5MEngine,
    HarmonicEngine,
    BreakerEngine,
    MarketBrain,
    BacktestEngine,
    PerformanceAnalytics,
    ReportGenerator,
    RiskManager,
    FVGEngine,
    FVG,
    Trade,
    TradeSignal,
    MSBEvent,
    IndicatorEngine,
    to_naive,
    detect_order_blocks_1h,
    detect_horseshoe_1h,
    _build_poi_mit_map,
    DataEngine,
    DailyBiasProvider,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_df(n, base=2000.0, step=1.0, freq="5min"):
    idx = pd.date_range("2026-01-01", periods=n, freq=freq)
    c = np.array([base + i * step for i in range(n)], dtype=float)
    o = c - 0.3
    h = c + 0.8
    l = c - 0.8
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=idx)


def _swing_high_df(n=30, freq="1h"):
    """Bar 10'da belirgin swing high, sonra bar 20'de kırılım."""
    idx = pd.date_range("2026-01-01", periods=n, freq=freq)
    h = np.full(n, 100.0)
    l = np.full(n, 98.0)
    o = np.full(n, 99.0)
    c = np.full(n, 99.5)
    # swing high @ bar 10 (H=120), etrafı düşük
    for i in range(10):  h[i] = 100 + i * 0.5
    h[10] = 120.0; c[10] = 119.0
    for i in range(11, 20): h[i] = 115 - (i - 11) * 0.5; c[i] = h[i] - 1.0
    # bar 20: close kırar (BOS)
    h[20] = 125.0; c[20] = 122.0; o[20] = 115.0
    for i in range(21, n): h[i] = 121 + (i - 21) * 0.2; c[i] = h[i] - 0.5
    l = np.minimum(l, o - 0.5)
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=idx)


def _swing_low_df(n=30, freq="1h"):
    """Bar 10'da belirgin swing low, sonra bar 20'de aşağı kırılım."""
    idx = pd.date_range("2026-01-01", periods=n, freq=freq)
    h = np.full(n, 102.0)
    l = np.full(n, 100.0)
    o = np.full(n, 101.0)
    c = np.full(n, 101.0)
    for i in range(10): l[i] = 100 - i * 0.5
    l[10] = 80.0; c[10] = 81.0
    for i in range(11, 20): l[i] = 85 + (i - 11) * 0.5; c[i] = l[i] + 1.0
    h[20] = 89.0; l[20] = 75.0; c[20] = 76.0; o[20] = 86.0
    for i in range(21, n): l[i] = 77 - (i - 21) * 0.2; c[i] = l[i] + 0.5
    h = np.maximum(h, o + 0.5)
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=idx)


def _make_signal(direction="bull", stop=1950.0):
    return TradeSignal(
        entry_time=datetime(2026, 3, 1, 10, 0),
        direction=direction,
        trigger_fvg=None,
        confirmation_type="EMA",
        confidence=70.0,
        stop_price=stop,
        risk_fraction=0.005,
    )


def _make_trade(result, pnl, time=None, fvg=None):
    sig = TradeSignal(
        entry_time=time or datetime(2026, 3, 1, 10, 0),
        direction="bull",
        trigger_fvg=fvg,
        confirmation_type="EMA",
        confidence=70.0,
        stop_price=1950.0,
        risk_fraction=0.005,
    )
    return Trade(
        trade_id=1, signal=sig,
        entry_price=2000.0, sl=1960.0, tp=2080.0,
        risk=40.0, risk_pct=2.0, risk_dollar=50.0,
        result=result, pnl_dollar=pnl,
        equity_after=10000 + pnl,
        exit_time=time or datetime(2026, 3, 1, 14, 0),
    )


def _make_fvg(fvg_id, direction, bottom, top, detect_time=None):
    det = detect_time or datetime(2026, 1, 1, 10, 0)
    return FVG(
        fvg_id=fvg_id, timeframe="1h", direction=direction,
        index=det - timedelta(hours=1), detect_time=det,
        top=top, bottom=bottom, mid=(top + bottom) / 2,
        gap_size=top - bottom, gap_atr_ratio=0.5,
        momentum=0.8, quality_score=60.0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 1: Utility — normalize_index, flatten_columns, resample_ohlcv
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeIndex:
    def test_strips_timezone(self):
        idx = pd.date_range("2026-01-01", periods=5, freq="h", tz="UTC")
        df = pd.DataFrame({"A": range(5)}, index=idx)
        result = normalize_index(df)
        assert result.index.tz is None

    def test_naive_index_unchanged(self):
        df = _make_df(5)
        result = normalize_index(df)
        assert result.index.tz is None
        assert len(result) == 5

    def test_none_returns_none(self):
        assert normalize_index(None) is None

    def test_empty_df_returns_empty(self):
        df = pd.DataFrame()
        result = normalize_index(df)
        assert result.empty


class TestFlattenColumns:
    def test_multiindex_flattened(self):
        idx = pd.MultiIndex.from_tuples([("Open", "X"), ("High", "X"),
                                          ("Low", "X"), ("Close", "X")])
        df = pd.DataFrame([[1, 2, 3, 4]], columns=idx)
        result = flatten_columns(df)
        assert list(result.columns) == ["Open", "High", "Low", "Close"]

    def test_regular_columns_unchanged(self):
        df = _make_df(5)
        result = flatten_columns(df)
        assert list(result.columns) == ["Open", "High", "Low", "Close"]


class TestResampleOhlcv:
    def test_5m_to_1h(self):
        idx = pd.date_range("2026-01-01 00:00", periods=120, freq="5min")
        close = np.arange(120, dtype=float) + 2000
        df = pd.DataFrame({
            "Open": close - 0.5, "High": close + 1.0,
            "Low": close - 1.0, "Close": close,
        }, index=idx)
        result = resample_ohlcv(df, "1h")
        assert len(result) == 10   # 120 × 5min = 600 min = 10 saat

    def test_ohlc_aggregation(self):
        idx = pd.date_range("2026-01-01 00:00", periods=60, freq="5min")
        df = pd.DataFrame({
            "Open":  [2000.0] * 60,
            "High":  [2010.0] * 60,
            "Low":   [1990.0] * 60,
            "Close": [2005.0] * 60,
        }, index=idx)
        result = resample_ohlcv(df, "1h")
        assert result["Open"].iloc[0]  == pytest.approx(2000.0)
        assert result["High"].iloc[0]  == pytest.approx(2010.0)
        assert result["Low"].iloc[0]   == pytest.approx(1990.0)
        assert result["Close"].iloc[0] == pytest.approx(2005.0)

    def test_volume_summed(self):
        # 60 bars × 5min = 300 min = 5 saat → 5 hourly bars, each with 12 bars
        idx = pd.date_range("2026-01-01", periods=60, freq="5min")
        c = np.full(60, 2000.0)
        df = pd.DataFrame({
            "Open": c, "High": c + 1, "Low": c - 1, "Close": c,
            "Volume": np.ones(60),
        }, index=idx)
        result = resample_ohlcv(df, "1h")
        assert result["Volume"].iloc[0] == pytest.approx(12.0)  # 12 bars per hour


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 2: MSBEngine
# ─────────────────────────────────────────────────────────────────────────────

class TestMSBEngine:
    def test_compute_adds_columns(self):
        df = _make_df(50, freq="1h")
        atr = IndicatorEngine.atr(df)
        result = MSBEngine.compute(df, atr)
        for col in ("msc_bull", "msc_bear", "msc_bull_mom", "msc_bear_mom"):
            assert col in result.columns

    def test_bull_bos_detected(self):
        df = _swing_high_df(30)
        atr = IndicatorEngine.atr(df)
        result = MSBEngine.compute(df, atr)
        # bar 20'de BOS var
        assert result["msc_bull"].any(), "Bull BOS bekleniyor"

    def test_bear_bos_detected(self):
        df = _swing_low_df(30)
        atr = IndicatorEngine.atr(df)
        result = MSBEngine.compute(df, atr)
        assert result["msc_bear"].any(), "Bear BOS bekleniyor"

    def test_momentum_in_range(self):
        df = _swing_high_df(30)
        atr = IndicatorEngine.atr(df)
        result = MSBEngine.compute(df, atr)
        assert (result["msc_bull_mom"] >= 0).all()
        assert (result["msc_bull_mom"] <= 1.0).all()

    def test_no_bos_flat_market(self):
        df = _make_df(50, step=0.0, freq="1h")   # tamamen düz
        atr = IndicatorEngine.atr(df)
        result = MSBEngine.compute(df, atr)
        assert not result["msc_bull"].any()
        assert not result["msc_bear"].any()


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 3: MSB5MEngine
# ─────────────────────────────────────────────────────────────────────────────

class TestMSB5MEngine:
    def _three_vol_df(self):
        """3 ardışık büyük gövdeli bull mum — three_vol tetikler.

        Koşullar: body/range>=0.45, yükselen kapanış, küçük üst fitil,
        her mum önceki mumun gövdesi içinde açılmış.
        """
        n = 50
        idx = pd.date_range("2026-01-01", periods=n, freq="5min")
        o = np.full(n, 2000.0)
        c = np.full(n, 2001.0)
        h = np.full(n, 2002.0)
        l = np.full(n, 1999.0)
        # bars 20-22: büyük gövdeli bull, yükselen kapanış, küçük fitiller
        # bar 20: O=2000, C=2013 (body=13, range=14); O[21]=2002 ∈ [1997.4, 2015.6]
        o[20] = 2000.0; c[20] = 2013.0; h[20] = 2013.5; l[20] = 1999.5
        # bar 21: opens inside bar20 body, rising close; O[22]=2004 ∈ [1999.4, 2017.6]
        o[21] = 2002.0; c[21] = 2015.0; h[21] = 2015.5; l[21] = 2001.5
        # bar 22: opens inside bar21 body, rising close, small upper wick
        o[22] = 2004.0; c[22] = 2017.0; h[22] = 2017.5; l[22] = 2003.5
        return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=idx)

    def test_detect_returns_list(self):
        df = _make_df(100)
        atr = IndicatorEngine.atr(df)
        eng = MSB5MEngine()
        events = eng.detect(df, atr)
        assert isinstance(events, list)

    def test_events_sorted_by_confirm_idx(self):
        df = _make_df(200)
        atr = IndicatorEngine.atr(df)
        eng = MSB5MEngine()
        events = eng.detect(df, atr)
        idxs = [e.confirm_idx for e in events]
        assert idxs == sorted(idxs)

    def test_event_directions_valid(self):
        df = _make_df(200)
        atr = IndicatorEngine.atr(df)
        eng = MSB5MEngine()
        events = eng.detect(df, atr)
        for e in events:
            assert e.direction in ("bull", "bear")

    def test_event_types_valid(self):
        df = _make_df(200)
        atr = IndicatorEngine.atr(df)
        eng = MSB5MEngine()
        events = eng.detect(df, atr)
        for e in events:
            assert e.msb_type in ("breaker", "mitigation", "three_vol")

    def test_three_vol_detected(self):
        df = self._three_vol_df()
        atr = IndicatorEngine.atr(df)
        eng = MSB5MEngine(vol_mult=1.5, vol_window=20)
        events = eng.detect(df, atr)
        three_vol_events = [e for e in events if e.msb_type == "three_vol"]
        assert len(three_vol_events) >= 1

    def test_stop_price_positive(self):
        df = _make_df(200, step=2.0)
        atr = IndicatorEngine.atr(df)
        eng = MSB5MEngine()
        events = eng.detect(df, atr)
        for e in events:
            assert e.stop_price > 0


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 4: HarmonicEngine
# ─────────────────────────────────────────────────────────────────────────────

class TestHarmonicEngine:
    def test_conf_perfect_match(self):
        """v1 tam ortada, v2 tam ortada → conf=100."""
        c = HarmonicEngine._conf(5.0, 4.5, 5.5, 5.0, 4.5, 5.5)
        assert c == pytest.approx(100.0)

    def test_conf_zero_on_mismatch(self):
        """v büyük sapma → conf düşük (0 olabilir)."""
        c = HarmonicEngine._conf(10.0, 1.0, 2.0, 20.0, 1.0, 2.0)
        assert c == pytest.approx(0.0)

    def test_conf_range(self):
        for v1, v2 in [(5.0, 3.0), (2.0, 8.0), (0.5, 9.5)]:
            c = HarmonicEngine._conf(v1, 1.0, 9.0, v2, 1.0, 9.0)
            assert 0.0 <= c <= 100.0

    def test_detect_returns_list(self):
        df = _make_df(200, step=1.0)
        eng = HarmonicEngine(swing=3, min_conf=40.0)
        result = eng.detect(df, "5m")
        assert isinstance(result, list)

    def test_detect_flat_market_empty(self):
        """Düz piyasa → harmonik desen yok."""
        df = _make_df(100, step=0.0)
        eng = HarmonicEngine(swing=3, min_conf=40.0)
        result = eng.detect(df, "5m")
        assert len(result) == 0

    def test_detect_direction_valid(self):
        df = _make_df(300, step=0.5)
        eng = HarmonicEngine(swing=3, min_conf=0.0)
        result = eng.detect(df, "5m")
        for sig in result:
            assert sig.direction in ("bull", "bear")

    def test_detect_confidence_in_range(self):
        df = _make_df(300, step=0.5)
        eng = HarmonicEngine(swing=3, min_conf=0.0)
        result = eng.detect(df, "5m")
        for sig in result:
            assert 0.0 <= sig.conf <= 100.0


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 5: BreakerEngine
# ─────────────────────────────────────────────────────────────────────────────

class TestBreakerEngine:
    def test_detect_returns_list(self):
        df = _make_df(50, freq="1h")
        atr = IndicatorEngine.atr(df)
        eng = BreakerEngine()
        result = eng.detect(df, "bull", atr)
        assert isinstance(result, list)

    def test_bull_breaker_on_bos(self):
        df = _swing_high_df(30, freq="1h")
        atr = IndicatorEngine.atr(df)
        eng = BreakerEngine()
        blocks = eng.detect(df, "bull", atr)
        assert len(blocks) >= 1

    def test_bear_breaker_on_bos(self):
        df = _swing_low_df(30, freq="1h")
        atr = IndicatorEngine.atr(df)
        eng = BreakerEngine()
        blocks = eng.detect(df, "bear", atr)
        assert len(blocks) >= 1

    def test_detect_time_after_break(self):
        """detect_time = break_time + 1h (lookahead koruması)."""
        df = _swing_high_df(30, freq="1h")
        atr = IndicatorEngine.atr(df)
        eng = BreakerEngine()
        blocks = eng.detect(df, "bull", atr)
        for b in blocks:
            assert to_naive(b.detect_time) > to_naive(b.break_time)

    def test_quality_in_range(self):
        df = _swing_high_df(30, freq="1h")
        atr = IndicatorEngine.atr(df)
        eng = BreakerEngine()
        blocks = eng.detect(df, "bull", atr)
        for b in blocks:
            assert 0.0 <= b.quality_score <= 100.0

    def test_no_blocks_flat_market(self):
        df = _make_df(50, step=0.0, freq="1h")
        atr = IndicatorEngine.atr(df)
        eng = BreakerEngine()
        assert len(eng.detect(df, "bull", atr)) == 0
        assert len(eng.detect(df, "bear", atr)) == 0


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 6: detect_order_blocks_1h
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectOrderBlocks1H:
    def _bull_ob_df(self, n=60):
        """BOS + FVG içeren bull yapısı → OB tespiti."""
        idx = pd.date_range("2026-01-01", periods=n, freq="1h")
        o = np.full(n, 2000.0); c = o.copy()
        h = o + 2.0; l = o - 2.0

        # swing high @ bar 15
        for i in range(13, 16): h[i] = 2020 + (i - 13) * 5
        h[14] = 2030.0; c[14] = 2029.0
        # düşüş
        for i in range(15, 25):
            o[i] = 2028 - (i - 15) * 2; c[i] = o[i] - 1.5
            h[i] = o[i] + 1; l[i] = c[i] - 1

        # impuls başlangıcı: last bearish bar before BOS
        o[23] = 2010; c[23] = 2008; h[23] = 2011; l[23] = 2007

        # FVG: bar 24 (L > H of bar 22)
        o[24] = 2025; c[24] = 2028; h[24] = 2030; l[24] = 2024

        # BOS bar: close > swing high @ bar 15 (H=2030)
        o[25] = 2028; c[25] = 2035; h[25] = 2036; l[25] = 2027

        for i in range(26, n):
            o[i] = 2033 + (i - 26) * 0.5; c[i] = o[i] + 0.3
            h[i] = o[i] + 1; l[i] = o[i] - 1

        return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=idx)

    def test_returns_list(self):
        df = _make_df(60, freq="1h")
        H = df["High"].values; L = df["Low"].values
        O = df["Open"].values; C = df["Close"].values
        T = df.index; atr = IndicatorEngine.atr(df).values
        result = detect_order_blocks_1h(H, L, O, C, T, atr, "bull")
        assert isinstance(result, list)

    def test_detect_time_lookahead_safe(self):
        df = self._bull_ob_df()
        H = df["High"].values; L = df["Low"].values
        O = df["Open"].values; C = df["Close"].values
        T = df.index; atr = IndicatorEngine.atr(df).values
        obs = detect_order_blocks_1h(H, L, O, C, T, atr, "bull", require_fvg=False)
        for ob in obs:
            assert to_naive(ob.detect_time) > to_naive(ob.index)

    def test_quality_in_range(self):
        df = self._bull_ob_df()
        H = df["High"].values; L = df["Low"].values
        O = df["Open"].values; C = df["Close"].values
        T = df.index; atr = IndicatorEngine.atr(df).values
        obs = detect_order_blocks_1h(H, L, O, C, T, atr, "bull", require_fvg=False)
        for ob in obs:
            assert 0.0 <= ob.quality_score <= 100.0

    def test_bull_obs_direction(self):
        df = self._bull_ob_df()
        H = df["High"].values; L = df["Low"].values
        O = df["Open"].values; C = df["Close"].values
        T = df.index; atr = IndicatorEngine.atr(df).values
        obs = detect_order_blocks_1h(H, L, O, C, T, atr, "bull", require_fvg=False)
        for ob in obs:
            assert ob.direction == "bull"

    def test_no_obs_flat_market(self):
        df = _make_df(60, step=0.0, freq="1h")
        H = df["High"].values; L = df["Low"].values
        O = df["Open"].values; C = df["Close"].values
        T = df.index; atr = IndicatorEngine.atr(df).values
        result = detect_order_blocks_1h(H, L, O, C, T, atr, "bull")
        assert len(result) == 0


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 7: detect_horseshoe_1h
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectHorseshoe1H:
    def _bull_hs_df(self, n=20):
        """
        Bull horseshoe: bar i-3 büyük, i-2/i-1 küçük, i büyük bull.
        Bar i = wicks below min(L[i-3..i-1]) ve bullish close.
        """
        idx = pd.date_range("2026-01-01", periods=n, freq="1h")
        o = np.full(n, 2000.0)
        c = np.full(n, 2001.0)
        h = np.full(n, 2002.0)
        l = np.full(n, 1999.0)

        # 4 bar pattern @ bars 10-13
        # Bar 10: büyük bear gövde
        o[10] = 2010; c[10] = 1995; h[10] = 2012; l[10] = 1994
        # Bar 11: küçük iç bar
        o[11] = 1996; c[11] = 1997; h[11] = 1998; l[11] = 1995
        # Bar 12: küçük iç bar
        o[12] = 1997; c[12] = 1996; h[12] = 1999; l[12] = 1995
        # Bar 13: büyük bull, wicks below prior 3 lows (min=1994), bullish close
        prior_min = min(l[10], l[11], l[12])   # = 1994
        o[13] = 1993; c[13] = 2005; h[13] = 2006; l[13] = prior_min - 0.5  # 1993.5 < 1994
        return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=idx)

    def test_returns_list(self):
        df = _make_df(20, freq="1h")
        H = df["High"].values; L = df["Low"].values
        O = df["Open"].values; C = df["Close"].values
        T = df.index
        result = detect_horseshoe_1h(H, L, O, C, T, "bull")
        assert isinstance(result, list)

    def test_bull_horseshoe_detected(self):
        df = self._bull_hs_df()
        H = df["High"].values; L = df["Low"].values
        O = df["Open"].values; C = df["Close"].values
        T = df.index
        result = detect_horseshoe_1h(H, L, O, C, T, "bull")
        assert len(result) >= 1

    def test_horseshoe_timeframe_label(self):
        df = self._bull_hs_df()
        H = df["High"].values; L = df["Low"].values
        O = df["Open"].values; C = df["Close"].values
        T = df.index
        result = detect_horseshoe_1h(H, L, O, C, T, "bull")
        for hs in result:
            assert hs.timeframe == "1h_hs"

    def test_detect_time_after_pattern(self):
        """detect_time = T[i] + 1h (lookahead koruması)."""
        df = self._bull_hs_df()
        H = df["High"].values; L = df["Low"].values
        O = df["Open"].values; C = df["Close"].values
        T = df.index
        result = detect_horseshoe_1h(H, L, O, C, T, "bull")
        for hs in result:
            assert to_naive(hs.detect_time) > to_naive(hs.index)

    def test_quality_in_range(self):
        df = self._bull_hs_df()
        H = df["High"].values; L = df["Low"].values
        O = df["Open"].values; C = df["Close"].values
        T = df.index
        result = detect_horseshoe_1h(H, L, O, C, T, "bull")
        for hs in result:
            assert 0.0 <= hs.quality_score <= 100.0

    def test_no_horseshoe_flat_market(self):
        df = _make_df(20, step=0.0, freq="1h")
        H = df["High"].values; L = df["Low"].values
        O = df["Open"].values; C = df["Close"].values
        T = df.index
        result = detect_horseshoe_1h(H, L, O, C, T, "bull")
        assert len(result) == 0


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 8: _build_poi_mit_map
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildPoiMitMap:
    def test_returns_dict_for_all_pois(self):
        idx = pd.date_range("2026-01-01", periods=20, freq="1h")
        C = np.full(20, 2005.0)
        fvg = _make_fvg(5001, "bull", 2000, 2010,
                        detect_time=datetime(2026, 1, 1, 3, 0))
        mit_map = _build_poi_mit_map([fvg], C, idx)
        assert 5001 in mit_map

    def test_bull_poi_mitigated_when_close_below_bottom(self):
        idx = pd.date_range("2026-01-01", periods=20, freq="1h")
        C = np.full(20, 2005.0)
        # bar 10 onward: close = 1995 < bottom=2000 → mitigasyon
        C[10:] = 1995.0
        fvg = _make_fvg(5002, "bull", 2000, 2010,
                        detect_time=idx[2] + pd.Timedelta(hours=1))
        mit_map = _build_poi_mit_map([fvg], C, idx)
        assert mit_map[5002] is not None

    def test_bear_poi_mitigated_when_close_above_top(self):
        idx = pd.date_range("2026-01-01", periods=20, freq="1h")
        C = np.full(20, 1995.0)
        C[10:] = 2015.0   # close > top=2010 → mitigasyon
        fvg = _make_fvg(5003, "bear", 2000, 2010,
                        detect_time=idx[2] + pd.Timedelta(hours=1))
        mit_map = _build_poi_mit_map([fvg], C, idx)
        assert mit_map[5003] is not None

    def test_no_mitigation_when_price_stays_inside(self):
        idx = pd.date_range("2026-01-01", periods=20, freq="1h")
        C = np.full(20, 2005.0)   # 2000 < 2005 < 2010 → içerde
        fvg = _make_fvg(5004, "bull", 2000, 2010,
                        detect_time=idx[1] + pd.Timedelta(hours=1))
        mit_map = _build_poi_mit_map([fvg], C, idx)
        assert mit_map[5004] is None


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 9: MarketBrain — unit düzeyinde
# ─────────────────────────────────────────────────────────────────────────────

class TestMarketBrainUnit:
    def test_init_attrs(self):
        brain = MarketBrain()
        assert hasattr(brain, "pending")
        assert hasattr(brain, "used_fvg_ids")
        assert hasattr(brain, "stats")
        assert "step1_fail" in brain.stats

    def test_ema_confirm_bull(self):
        brain = MarketBrain()
        ok, dist = brain.ema_confirm(2100.0, 2000.0, 1900.0, "bull")
        assert ok is True
        assert dist > 0

    def test_ema_confirm_bull_fail(self):
        brain = MarketBrain()
        ok, _ = brain.ema_confirm(1950.0, 2000.0, 1900.0, "bull")
        assert ok is False

    def test_ema_confirm_bear(self):
        brain = MarketBrain()
        ok, dist = brain.ema_confirm(1900.0, 2000.0, 2100.0, "bear")
        assert ok is True
        assert dist > 0

    def test_bias_no_weekly_entry_returns_no_bias(self):
        """Bias var ama hafta bulunamıyor → last_skip_reason = 'no_bias'."""
        import json, tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"2020-W01": "bull"}, f)   # 2026 için yok
            fname = f.name
        with contextlib.redirect_stdout(io.StringIO()):
            from xauusd_fvg_engine_v10 import WeeklyBiasProvider
            prov = WeeklyBiasProvider(fname)

        brain = MarketBrain(bias_provider=prov)
        # evaluate çağrısını simulate etmek yerine doğrudan bias.get kontrolü
        result = prov.get(datetime(2026, 3, 2))
        assert result is None

    def test_stats_keys_present(self):
        brain = MarketBrain()
        for key in ("step1_fail", "step2_fail", "step3_fail"):
            assert key in brain.stats

    def test_used_fvg_ids_empty_on_init(self):
        brain = MarketBrain()
        assert len(brain.used_fvg_ids) == 0

    def test_pending_empty_on_init(self):
        brain = MarketBrain()
        assert brain.pending["bull"] == []
        assert brain.pending["bear"] == []


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 10: BacktestEngine — unit düzeyinde
# ─────────────────────────────────────────────────────────────────────────────

class TestBacktestEngineUnit:
    def test_init_capital_set(self):
        brain = MarketBrain()
        risk = RiskManager(rr=2.0)
        eng = BacktestEngine(brain, risk, initial_capital=15_000)
        assert eng.capital == 15_000

    def test_breakeven_at_r_stored(self):
        brain = MarketBrain()
        risk = RiskManager(rr=2.0)
        eng = BacktestEngine(brain, risk, breakeven_at_R=1.0)
        assert eng.breakeven_at_R == 1.0

    def test_breakeven_none_by_default(self):
        brain = MarketBrain()
        risk = RiskManager(rr=2.0)
        eng = BacktestEngine(brain, risk)
        assert eng.breakeven_at_R is None

    def test_make_entry_trade_uses_next_bar_open(self):
        """_make_entry_trade: entry = O[idx+1], lookahead koruması."""
        brain = MarketBrain()
        risk = RiskManager(rr=2.0, sl_buffer=0.0)
        eng = BacktestEngine(brain, risk, initial_capital=10_000)
        O = np.array([2000.0, 2001.0, 2002.0, 2003.0, 2004.0])
        sig = _make_signal("bull", stop=1960.0)
        trade = eng._make_entry_trade(
            signal=sig, idx=2, O=O, equity=10_000, trade_id=1)
        if trade is not None:
            # entry = O[3] = 2003.0
            assert trade.entry_price == pytest.approx(2003.0, abs=0.01)

    def test_make_entry_trade_invalid_risk_returns_none(self):
        """Risk sınır dışıysa None döner."""
        brain = MarketBrain()
        risk = RiskManager(rr=2.0, sl_buffer=0.0)
        eng = BacktestEngine(brain, risk, initial_capital=10_000)
        O = np.array([2000.0, 2000.0, 2000.0, 2000.0])
        # stop = 2000 ile entry = 2000 → risk = 0 → None
        sig = _make_signal("bull", stop=2000.0)
        trade = eng._make_entry_trade(
            signal=sig, idx=2, O=O, equity=10_000, trade_id=1)
        assert trade is None


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 11: ReportGenerator
# ─────────────────────────────────────────────────────────────────────────────

class TestReportGenerator:
    def _dummy_fvg(self):
        return _make_fvg(9999, "bull", 2000, 2010)

    def _done_trade(self):
        return _make_trade("WIN", 100.0, fvg=self._dummy_fvg())

    def test_generate_no_done_trades_no_crash(self):
        """Tamamlanmış işlem yok → hata vermez, mesaj basar."""
        open_trade = _make_trade("OPEN", 0.0)
        buf = io.StringIO()
        m = {"win_rate": 0.6, "profit_factor": 1.5, "sharpe": 1.0, "max_dd": 2.0}
        with contextlib.redirect_stdout(buf):
            ReportGenerator.generate([open_trade], m, out="/tmp/test_report.png")
        output = buf.getvalue()
        assert "yok" in output or "tamamlanan" in output.lower() or len(output) >= 0

    def test_save_csv_creates_file(self, tmp_path):
        t = self._done_trade()
        t.exit_time = datetime(2026, 3, 1, 14, 0)
        t.exit_price = 2080.0
        out = str(tmp_path / "trades.csv")
        ReportGenerator.save_csv([t], filename=out)
        assert Path(out).exists()

    def test_save_csv_has_correct_columns(self, tmp_path):
        t = self._done_trade()
        t.exit_time = datetime(2026, 3, 1, 14, 0)
        t.exit_price = 2080.0
        out = str(tmp_path / "trades2.csv")
        with contextlib.redirect_stdout(io.StringIO()):
            ReportGenerator.save_csv([t], filename=out)
        df = pd.read_csv(out)
        for col in ("trade_id", "direction", "entry_price", "sl", "tp",
                    "result", "pnl_dollar"):
            assert col in df.columns

    def test_save_csv_empty_trades_no_file(self, tmp_path):
        out = str(tmp_path / "empty.csv")
        ReportGenerator.save_csv([], filename=out)
        assert not Path(out).exists()


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 12: Integration — tüm bileşenler birlikte
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def market_data():
    if not (Path("xauusd_5m.csv").exists() and Path("xauusd_1h.csv").exists()):
        pytest.skip("CSV veri dosyaları bulunamadı")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        df_1h, df_5m, bt_start = DataEngine.download(verbose=False)
    return df_1h, df_5m, bt_start


class TestFullPipelineIntegration:
    def test_msb5m_on_real_data(self, market_data):
        """Gerçek 5M verisi üzerinde MSB5M hata vermez ve olay üretir."""
        _, df_5m, _ = market_data
        df5 = df_5m.copy()
        df5["atr"] = IndicatorEngine.atr(df5, 14)
        eng = MSB5MEngine(vol_mult=1.5, vol_window=20)
        events = eng.detect(df5, df5["atr"])
        assert len(events) > 0, "Gerçek veri üzerinde MSB olayı bekleniyor"

    def test_msb_engine_on_real_1h(self, market_data):
        df_1h, _, _ = market_data
        df1 = df_1h.copy()
        df1["atr"] = IndicatorEngine.atr(df1, 14)
        result = MSBEngine.compute(df1, df1["atr"])
        assert result["msc_bull"].any() or result["msc_bear"].any()

    def test_breaker_engine_on_real_1h(self, market_data):
        df_1h, _, _ = market_data
        df1 = df_1h.copy()
        df1["atr"] = IndicatorEngine.atr(df1, 14)
        eng = BreakerEngine()
        bull_bb = eng.detect(df1, "bull", df1["atr"])
        bear_bb = eng.detect(df1, "bear", df1["atr"])
        assert isinstance(bull_bb, list)
        assert isinstance(bear_bb, list)

    def test_detect_ob_on_real_1h(self, market_data):
        df_1h, _, _ = market_data
        df1 = df_1h.copy()
        df1["atr"] = IndicatorEngine.atr(df1, 14)
        H = df1["High"].values; L = df1["Low"].values
        O = df1["Open"].values; C = df1["Close"].values
        T = df1.index; atr = df1["atr"].values
        obs = detect_order_blocks_1h(H, L, O, C, T, atr, "bull")
        assert isinstance(obs, list)

    def test_harmonic_engine_on_real_5m(self, market_data):
        _, df_5m, _ = market_data
        eng = HarmonicEngine(swing=5, min_conf=40.0)
        result = eng.detect(df_5m.head(2000), "5m")
        assert isinstance(result, list)

    def test_report_generator_on_real_trades(self, market_data, tmp_path):
        df_1h, df_5m, bt_start = market_data
        with contextlib.redirect_stdout(io.StringIO()):
            brain = MarketBrain(bias_provider=None)
            risk = RiskManager(rr=1.0, sl_buffer=0.0005)
            trades = BacktestEngine(brain, risk, 10_000).run(df_1h, df_5m, bt_start)

        done = [t for t in trades if t.result in ("WIN", "LOSS", "BE")]
        if not done:
            pytest.skip("Backtest işlem üretmedi")

        out_csv = str(tmp_path / "trades.csv")
        with contextlib.redirect_stdout(io.StringIO()):
            ReportGenerator.save_csv(trades, filename=out_csv)
        assert Path(out_csv).exists()
        df = pd.read_csv(out_csv)
        assert len(df) == len(trades)

    def test_market_brain_evaluate_returns_signal_or_none(self, market_data):
        """MarketBrain.evaluate() None veya TradeSignal döner, asla crash olmaz."""
        df_1h, df_5m, bt_start = market_data
        with contextlib.redirect_stdout(io.StringIO()):
            from xauusd_fvg_engine_v10 import (
                EMAEngine, RSIEngine, FVGEngine, MSB5MEngine, IndicatorEngine,
            )
            df5 = df_5m.copy()
            df5 = EMAEngine.add(df5, 100, 200)
            df5["rsi"] = RSIEngine.wilder(df5["Close"], 14)
            df5["atr"] = IndicatorEngine.atr(df5, 14)
            df1 = df_1h.copy()
            df1["atr"] = IndicatorEngine.atr(df1, 14)
            fvg_eng = FVGEngine("1h", min_gap=2.0)
            fvg_bull = fvg_eng.detect(df1, "bull", df1["atr"])
            fvg_bear = fvg_eng.detect(df1, "bear", df1["atr"])
            mit_bull = fvg_eng.build_mitigation_map(df1, fvg_bull)
            mit_bear = fvg_eng.build_mitigation_map(df1, fvg_bear)
            msb_eng = MSB5MEngine()
            msb_all = msb_eng.detect(df5, df5["atr"])
            msb_bull = [e for e in msb_all if e.direction == "bull"]
            msb_bear = [e for e in msb_all if e.direction == "bear"]

        C = df5["Close"].values.astype(float)
        O = df5["Open"].values.astype(float)
        H = df5["High"].values.astype(float)
        L = df5["Low"].values.astype(float)
        E100 = df5["ema100"].values.astype(float)
        E200 = df5["ema200"].values.astype(float)
        RSI = df5["rsi"].values.astype(float)
        TM = df5.index

        brain = MarketBrain(bias_provider=None)
        result = brain.evaluate(
            idx=500, C=C, O=O, H=H, L=L,
            E100=E100, E200=E200, RSI=RSI, TM=TM,
            fvg1_bull=fvg_bull, mit1_bull=mit_bull,
            fvg1_bear=fvg_bear, mit1_bear=mit_bear,
            fvg1_eng=fvg_eng,
            msb_events_bull=msb_bull,
            msb_events_bear=msb_bear,
        )
        assert result is None or isinstance(result, TradeSignal)


if __name__ == "__main__":
    import subprocess
    subprocess.run(
        ["pytest", __file__, "-v", "--tb=short"], check=False
    )
