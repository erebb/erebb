#!/usr/bin/env python3
"""
gui.py — XAUUSD FVG Trading System v10  |  Rich TUI Kontrol Paneli
===================================================================
Çalıştır: python3 gui.py
Gereksinim: Python 3.9+  |  rich (pip install rich)
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# ── Proje kök dizini ─────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from rich.align import Align
from rich.box import ROUNDED, HEAVY_HEAD, SIMPLE_HEAVY, MINIMAL_DOUBLE_HEAD
from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, FloatPrompt, IntPrompt, Prompt
from rich.rule import Rule
from rich.spinner import Spinner
from rich.style import Style
from rich.table import Table
from rich.text import Text
from rich import box as rich_box

# ── Config ───────────────────────────────────────────────────────────────────
from config import Config, get_config

# ── Renk paleti (Catppuccin Mocha) ───────────────────────────────────────────
C_BG    = "#1e1e2e"
C_BG2   = "#181825"
C_FG    = "#cdd6f4"
C_FG2   = "#a6adc8"
C_BLUE  = "#89b4fa"
C_MAUVE = "#cba6f7"
C_GREEN = "#a6e3a1"
C_RED   = "#f38ba8"
C_YEL   = "#f9e2af"
C_TEAL  = "#94e2d5"
C_PINK  = "#f5c2e7"

console = Console()


# ═══════════════════════════════════════════════════════════════════════════════
# YARDIMCI FONKSIYONLAR
# ═══════════════════════════════════════════════════════════════════════════════

def _header() -> Panel:
    now = datetime.now().strftime("%Y-%m-%d  %H:%M")
    cfg = get_config()
    capital = cfg.get("backtest", "initial_capital", default=10_000)
    title = Text("✦  XAUUSD FVG TRADING SYSTEM  v10  ✦", style=f"bold {C_BLUE}")
    sub   = Text(f"Tarih: {now}   |   Sermaye: ${capital:,.0f}   |   Engine: xauusd_fvg_engine_v10.py",
                 style=C_FG2)
    body  = Align.center(Text.assemble(title, "\n", sub))
    return Panel(body, style=f"{C_BLUE} on {C_BG2}", box=HEAVY_HEAD, padding=(0, 2))


def _divider(text: str = "") -> Rule:
    return Rule(text, style=C_BLUE)


def _print_header() -> None:
    console.print()
    console.print(_header())
    console.print()


def _ok(msg: str) -> None:
    console.print(f"  [bold {C_GREEN}]✓[/]  {msg}")


def _err(msg: str) -> None:
    console.print(f"  [bold {C_RED}]✗[/]  {msg}")


def _info(msg: str) -> None:
    console.print(f"  [bold {C_BLUE}]→[/]  {msg}")


def _pick(prompt: str, choices: list[str], default: str = "") -> str:
    choices_str = " / ".join(f"[bold {C_YEL}]{c}[/]" for c in choices)
    console.print(f"\n  {prompt}  ({choices_str})")
    default_display = f"  [dim]varsayılan: {default}[/]" if default else ""
    if default_display:
        console.print(default_display)
    while True:
        val = Prompt.ask("  ›", default=default, console=console).strip().lower()
        if val in choices:
            return val
        _err(f"Geçersiz seçim — şunlardan biri olmalı: {', '.join(choices)}")


def _confirm(msg: str, default: bool = True) -> bool:
    return Confirm.ask(f"  {msg}", default=default, console=console)


# ═══════════════════════════════════════════════════════════════════════════════
# BACKTEST ÇALIŞTIRICI
# ═══════════════════════════════════════════════════════════════════════════════

def _load_data() -> tuple:
    """Veri yükle (sessiz)."""
    from xauusd_fvg_engine_v10 import DataEngine
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        df_1h, df_5m, bt_start = DataEngine.download(verbose=False)
    return df_1h, df_5m, bt_start


def _profile_get(cfg, section: str, key: str, default=None):
    """Aktif profilin override'ini uygula; yoksa config'in kendi degerini dondur.

    config.profile = "swing" -> hicbir override yok (ana ayarlar gecerli)
    config.profile = "scalp" -> config.profiles.scalp[section][key] varsa o
    kullanilir. Scalp MT5/prop komisyon yapisi icin tasarlandi; BingX'te
    ucret_R 0.30 oldugu icin ZARARDA (bkz. docs/EXIT_ANALYSIS.md)."""
    prof = str(cfg.get("profile", default="swing") or "swing")
    if prof != "swing":
        ov = (cfg.get("profiles", default={}) or {}).get(prof, {}) or {}
        sec = ov.get(section, {}) or {}
        if key in sec:
            return sec[key]
    return cfg.get(section, key, default=default)


def _profile_requires(cfg, profile: str | None = None) -> str | None:
    """Aktif profilin zorunlu kildigi broker (yoksa None).

    Scalp yalnizca MT5 komisyon yapisinda karli: 6.3$'lik stopta ucret_R
    BingX'te 0.30 (1R kazancin %30'u), MT5'te 0.019. BingX'te scalp 5 yilda
    -0.7R getiriyor. Bu yuzden profile requires_broker konur ve gui/canli bot
    yanlis broker ile calistirmayi ENGELLER."""
    prof = profile or str(cfg.get("profile", default="swing") or "swing")
    if prof == "swing":
        return None
    ov = (cfg.get("profiles", default={}) or {}).get(prof, {}) or {}
    return ov.get("requires_broker")


def _profile_broker_conflict(cfg, broker: str | None = None) -> str | None:
    """Uyumsuzluk varsa aciklama metni, yoksa None."""
    need = _profile_requires(cfg)
    if not need:
        return None
    cur = (broker or str(cfg.get("live", "broker", default="bingx"))).lower()
    if cur == str(need).lower():
        return None
    prof = str(cfg.get("profile", default="swing"))
    return ("Profil '%s' yalnizca '%s' broker ile calisir; secili broker '%s'."
            % (prof, need, cur))


def _strategy_presets(cfg) -> dict:
    """Her stratejinin SABİT preset'i (config'ten) — 1 yıllık dürüst grid'in
    en kârlı none konfigürasyonları. GUI soru sormaz, bunları işler.
    london/qwe motorları TP'yi kendi likidite hedeflerinden kurar → rr/emf
    onlar için nominaldir."""
    return {
        "fvg":      dict(bias=cfg.get("fvg", "bias", default="none"),
                         rr=str(_profile_get(cfg, "fvg", "rr", "1:2fix")),
                         emf=bool(cfg.get("fvg", "ema_filter", default=True)),
                         blackout=list(cfg.get("fvg", "blackout_hours",
                                               default=[]) or []),
                         swing_stop=bool(_profile_get(cfg, "fvg",
                                                      "swing_stop", True)),
                         limit_bars=(int(cfg.get("fvg", "limit_entry_bars",
                                                 default=3))
                                     if cfg.get("fvg", "entry_order",
                                                default="market") == "limit"
                                     else None)),
        "threevol": dict(bias=cfg.get("threevol", "bias", default="none"),
                         rr=str(_profile_get(cfg, "threevol", "rr", "1:2be")),
                         emf=bool(cfg.get("threevol", "ema_filter", default=True)),
                         blackout=list(cfg.get("threevol", "blackout_hours",
                                               default=[]) or []),
                         swing_stop=bool(_profile_get(cfg, "threevol",
                                                      "swing_stop", False)),
                         limit_bars=(int(cfg.get("threevol", "limit_entry_bars",
                                                 default=3))
                                     if cfg.get("threevol", "entry_order",
                                                default="market") == "limit"
                                     else None)),
        "harmonic": dict(bias=cfg.get("harmonic", "bias", default="none"),
                         rr=str(_profile_get(cfg, "harmonic", "rr", "1:2fix")),
                         emf=bool(cfg.get("harmonic", "ema_filter", default=True)),
                         blackout=list(cfg.get("harmonic", "blackout_hours",
                                               default=[]) or []),
                         swing_stop=bool(_profile_get(cfg, "harmonic",
                                                      "swing_stop", True)),
                         limit_bars=(int(cfg.get("harmonic", "limit_entry_bars",
                                                 default=3))
                                     if cfg.get("harmonic", "entry_order",
                                                default="market") == "limit"
                                     else None)),
        "london":   dict(bias=cfg.get("london_reversal", "bias", default="none"),
                         rr="1:2fix", emf=False, blackout=[]),
        "qwe":      dict(bias=cfg.get("qwe", "bias", default="none"),
                         rr="1:2fix", emf=False, blackout=[]),
        "fib":      dict(bias=cfg.get("fib", "bias", default="none"),
                         rr=str(_profile_get(cfg, "fib", "rr", "1:5fix")),
                         emf=bool(cfg.get("fib", "ema_filter", default=True)),
                         blackout=list(cfg.get("fib", "blackout_hours",
                                               default=[]) or []),
                         swing_stop=bool(_profile_get(cfg, "fib",
                                                      "swing_stop", True)),
                         limit_bars=(int(cfg.get("fib", "limit_entry_bars",
                                                 default=3))
                                     if cfg.get("fib", "entry_order",
                                                default="market") == "limit"
                                     else None)),
    }


def _run_strategy(strategy: str, bias: str = "", rr_label: str = "",
                  tbe_label: str = "", emf: bool = False,
                  capital: float = 10_000.0,
                  keep_trades: bool = False) -> list[dict]:
    """Backtest çalıştır, satır listesi döndür. TÜM stratejiler config'teki
    SABİT preset'leriyle koşar — bias/rr/tbe/emf argümanları geriye uyum
    için durur, YOK SAYILIR. keep_trades=True → satıra '_trades' listesi
    eklenir (scripts/run_full_backtest.py yıllık kırılım için kullanır)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from xauusd_fvg_engine_v10 import (
        DataEngine, MarketBrain, RiskManager, BacktestEngine,
        PerformanceAnalytics, WeeklyBiasProvider, DailyBiasProvider,
        PrivateBiasProvider, ThreeVolBrain,
        LondonReversalBrain, LondonBacktestEngine,
        QweBrain, QweBacktestEngine, RegimeEngine,
        FibRetestBrain, FibBacktestEngine,
    )
    from config import get_config

    cfg = get_config()

    # RR seçenekleri: "<hedef>fix" = sabit TP, "<hedef>be" = TP + 1R'de breakeven.
    # Yüksek RR adayları (1:3, 1:4, 1:5): 5 yıllık R dağılımı TÜM kazananların
    # tam 2R'de kesildiğini, 2.5R+ kovasının BOŞ olduğunu gösterdi — sabit 1:2
    # hedefi trendleri erken kapatıyor.
    rr_map = {"1:1": (1.0, None), "1:1.5": (1.5, None),
              "1:2be": (2.0, 1.0), "1:2fix": (2.0, None),
              "1:3fix": (3.0, None), "1:3be": (3.0, 1.0),
              "1:4fix": (4.0, None), "1:4be": (4.0, 1.0),
              "1:5fix": (5.0, None), "1:5be": (5.0, 1.0),
              "1:6fix": (6.0, None), "1:7fix": (7.0, None),
              "1:8fix": (8.0, None), "1:10fix": (10.0, None)}

    # Strategy modes
    # "hepsi" = 5 yıllık IS/OOS elemesinden GEÇEN stratejiler (config: enabled).
    # Elenenler (threevol/london/qwe) tek tek seçilerek yine koşulabilir.
    _sec = {"fvg": "fvg", "harmonic": "harmonic", "threevol": "threevol",
            "london": "london_reversal", "qwe": "qwe", "fib": "fib"}
    if strategy == "hepsi":
        strategies = [s for s in ["fvg", "harmonic", "threevol", "london", "qwe", "fib"]
                      if bool(cfg.get(_sec[s], "enabled", default=True))]
    else:
        strategies = [strategy]

    results = []

    # Veri yükle
    df_1h, df_5m, bt_start = _load_data()

    def make_bias(mode):
        if mode == "none":    return None
        if mode == "daily":
            from pathlib import Path
            if not Path(cfg.daily_bias_path).exists():
                DailyBiasProvider.build_from_1h(df_1h, cfg.daily_bias_path)
            return DailyBiasProvider(cfg.daily_bias_path)
        if mode == "private": return PrivateBiasProvider(df_1h)
        return WeeklyBiasProvider(cfg.weekly_bias_path)

    # TÜM stratejiler SABİT preset'le koşar (en kârlı none konfigürasyonları)
    presets = _strategy_presets(cfg)

    # Maliyet modeli (config: costs) — 0 = kapalı; gerçek ücretlerinizi girin
    cost_kw = dict(
        cost_spread_usd=float(cfg.get("costs", "spread_usd", default=0.0)),
        cost_slippage_usd=float(cfg.get("costs", "slippage_usd", default=0.0)),
        cost_commission_pct=float(cfg.get("costs", "commission_pct", default=0.0)),
        cost_maker_pct=float(cfg.get("costs", "maker_pct", default=0.02)),
        # HER İŞLEM EŞİT RİSK (config risk.risk_fraction; 0.01 = %1)
        uniform_risk_fraction=float(cfg.get("risk", "risk_fraction",
                                            default=0.01)),
    )

    # Rejim kapısı (meta-katman): threevol volatilite tabanı — düşük-vol
    # rejimde uyku (config threevol.vol_floor; 0 = kapalı)
    vol_floor = float(cfg.get("threevol", "vol_floor", default=0.0))
    gate_3v = (RegimeEngine.to_gate(
                   RegimeEngine.daily_vol_pct(df_1h) >= vol_floor, df_5m)
               if vol_floor > 0 else None)

    # ADX tabanı (rejim kapısı): 5 yıllık ay-rejim analizi, ADX<20 aylarının
    # toplam −23.6R getirdiğini ve yalnız %31'inin pozitif olduğunu gösterdi
    # (akümülasyon/yatay = sistemin kanadığı rejim). Tüm kâr ADX 30+ aylarından.
    _adx_cache: dict = {}

    def adx_gate_for(strat: str):
        sec = _cfg_sec.get(strat, strat)
        fl = float(cfg.get(sec, "adx_floor", default=0) or 0)
        if fl <= 0:
            return None
        if fl not in _adx_cache:
            _adx_cache[fl] = RegimeEngine.to_gate(
                RegimeEngine.adx_daily(df_1h) >= fl, df_5m)
        return _adx_cache[fl]

    # Günlük MACD momentum tabanı: |MACD|/fiyat %. Ay analizi, momentumun
    # olmadığı (|MACD%|<0.5) 19 ayın toplam −45.3R getirdiğini ve yalnız
    # %32'sinin pozitif olduğunu gösterdi; |MACD%|>1.5 aylarının HEPSİ pozitif.
    _macd_cache: dict = {}

    def macd_gate_for(strat: str):
        sec = _cfg_sec.get(strat, strat)
        fl = float(cfg.get(sec, "macd_floor", default=0) or 0)
        if fl <= 0:
            return None
        if fl not in _macd_cache:
            _macd_cache[fl] = RegimeEngine.to_gate(
                RegimeEngine.daily_macd_pct(df_1h) >= fl, df_5m)
        return _macd_cache[fl]

    def combined_gate(strat: str):
        """vol_floor (threevol) + adx_floor + macd_floor kapılarını VE'le."""
        gates = [g for g in (gate_3v if strat == "threevol" else None,
                             adx_gate_for(strat),
                             macd_gate_for(strat)) if g is not None]
        if not gates:
            return None
        out = gates[0]
        for g in gates[1:]:
            out = out & g
        return out

    # Makro trend kapısı (5 yıllık analiz kazananı): sinyal yönü günlük
    # SMA200 trendiyle uyuşmalı. Dar-stop reddi (min_stop_pct) ile birlikte
    # ücretin edge'i yemesini engeller — ikisi birlikte PF 1.08 → 1.72.
    _cfg_sec = {"fvg": "fvg", "harmonic": "harmonic", "threevol": "threevol",
                "london": "london_reversal", "qwe": "qwe", "fib": "fib"}
    _trend_cache: dict = {}

    def _teb(strat: str):
        """Zaman cikisi (5M bar). config <strateji>.time_exit_bars veya aktif
        profilin override'i. None/0 = kapali. Scalp profilinde 96 = 8 saat."""
        v = _profile_get(cfg, _cfg_sec.get(strat, strat), "time_exit_bars", None)
        return int(v) if v else None

    def trend_gate_for(strat: str):
        sec = _cfg_sec.get(strat, strat)
        if not bool(cfg.get(sec, "daily_trend_filter", default=False)):
            return None
        p = int(cfg.get(sec, "daily_trend_sma", default=200))
        if p not in _trend_cache:
            _trend_cache[p] = RegimeEngine.to_dir_gate(
                RegimeEngine.daily_trend(df_1h, period=p), df_5m)
        return _trend_cache[p]

    for strat in strategies:
        p = presets[strat]
        p_rr, p_be = rr_map.get(p["rr"], (2.0, None))
        rr_label   = p["rr"]
        common_kw  = dict(blackout_hours=p.get("blackout") or None,
                          swing_stop_1h=bool(p.get("swing_stop", False)),
                          limit_entry_bars=p.get("limit_bars"),
                          entry_gate=combined_gate(strat),
                          min_stop_pct=float(_profile_get(
                              cfg, _cfg_sec.get(strat, strat),
                              "min_stop_pct", 0.0)),
                          trend_gate=trend_gate_for(strat),
                          # Kısmi TP (config: <strateji>.partial_tp_r/_fraction):
                          # +X R'de pozisyonun bir kısmını kapat + SL'i BE'ye taşı,
                          # kalan runner yüksek RR hedefine gider. 0/None = kapalı.
                          partial_tp_r=(float(cfg.get(_cfg_sec.get(strat, strat),
                                                      "partial_tp_r", default=0) or 0)
                                        or None),
                          partial_tp_fraction=float(
                              cfg.get(_cfg_sec.get(strat, strat),
                                      "partial_tp_fraction", default=0.5)),
                          # Takip eden stop (config: <strateji>.trail_atr /
                          # trail_start_r). 0 = kapalı.
                          trail_atr=float(cfg.get(_cfg_sec.get(strat, strat),
                                                  "trail_atr", default=0) or 0),
                          trail_start_r=float(
                              cfg.get(_cfg_sec.get(strat, strat),
                                      "trail_start_r", default=1.0)),
                          # SL sıkılaştırma: stop × faktör, TP yapısal hedefte
                          # kalır → RR otomatik yükselir. Gerekçe: kazananların
                          # MAE'si ortalama yalnız 0.47R (stopun yarısı yetiyor).
                          sl_tighten=float(cfg.get(_cfg_sec.get(strat, strat),
                                                   "sl_tighten", default=0) or 0),
                          **cost_kw)
        for bmode in [p["bias"]]:
            bias_label = f"{bmode} (sabit)"
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    bp   = make_bias(bmode)
                    risk = RiskManager(rr=p_rr, sl_buffer=cfg.sl_buffer)

                    if strat == "london":
                        engine = LondonBacktestEngine(
                            LondonReversalBrain(bias_provider=bp), risk,
                            initial_capital=capital, breakeven_at_R=p_be,
                            time_exit_bars=_teb(strat), ema_macd_filter=p["emf"],
                            **common_kw)
                    elif strat == "qwe":
                        engine = QweBacktestEngine(
                            QweBrain(bias_provider=bp), risk,
                            initial_capital=capital, breakeven_at_R=p_be,
                            time_exit_bars=_teb(strat), ema_macd_filter=p["emf"],
                            **common_kw)
                    elif strat == "threevol":
                        # Three Vol Directional = ThreeVolBrain (doğrudan momentum)
                        engine = BacktestEngine(
                            ThreeVolBrain(bias_provider=bp), risk,
                            initial_capital=capital, breakeven_at_R=p_be,
                            time_exit_bars=_teb(strat), ema_macd_filter=p["emf"],
                            **common_kw)
                    elif strat == "fib":
                        # Fib 0.618 retest — kodda vardı ama hiç bağlanmamıştı
                        engine = FibBacktestEngine(
                            FibRetestBrain(bias_provider=bp), risk,
                            liq_finder=None,
                            initial_capital=capital, breakeven_at_R=p_be,
                            time_exit_bars=_teb(strat), ema_macd_filter=p["emf"],
                            **common_kw)
                    elif strat == "harmonic":
                        # Harmonik bot: yalnız harmonik PRZ POI girişleri
                        # (Gartley/Bat/Butterfly/Crab... → PRZ, MSB+EMA+RSI onaylı)
                        engine = BacktestEngine(
                            MarketBrain(bias_provider=bp, poi_mode="prz"), risk,
                            initial_capital=capital, breakeven_at_R=p_be,
                            time_exit_bars=_teb(strat), ema_macd_filter=p["emf"],
                            **common_kw)
                    else:
                        # poi_mode config'ten: 'all' (FVG+PRZ+OB) | 'fvg' | 'ob'.
                        # DİKKAT: 'all', harmonic'in kullandığı 'prz'yi İÇERİR →
                        # ikisi birlikte koşarsa aynı kuruluma çift risk alınır
                        # (ölçüm: harmonic işlemlerinin %97'si fvg ile aynı
                        # zaman/fiyat/sonuç). Bağımsızlık için fvg='fvg' yapın.
                        engine = BacktestEngine(
                            MarketBrain(bias_provider=bp,
                                        poi_mode=str(cfg.get("fvg", "poi_mode",
                                                             default="all"))), risk,
                            initial_capital=capital, breakeven_at_R=p_be,
                            time_exit_bars=_teb(strat), ema_macd_filter=p["emf"],
                            **common_kw)

                    trades  = engine.run(df_1h, df_5m, bt_start)
                    metrics = PerformanceAnalytics(trades, capital).compute()

                if metrics is None or metrics["total"] == 0:
                    results.append({
                        "strategy": strat, "bias": bias_label, "rr": rr_label,
                        "total": 0, "wins": 0, "losses": 0, "wr": 0.0,
                        "pnl": 0.0, "pf": 0.0, "sharpe": 0.0, "maxdd": 0.0, "ret": 0.0,
                    })
                else:
                    results.append({
                        "strategy": strat, "bias": bias_label, "rr": rr_label,
                        "total":  metrics["total"],
                        "wins":   metrics["wins"],
                        "losses": metrics["losses"],
                        "wr":     metrics["win_rate"] * 100,
                        "pnl":    metrics["net_pnl"],
                        "pf":     metrics["profit_factor"],
                        "sharpe": metrics["sharpe"],
                        "maxdd":  metrics["max_dd"],
                        "ret":    metrics["ret_pct"],
                    })
                    if keep_trades:
                        results[-1]["_trades"] = trades
            except Exception as exc:
                results.append({
                    "strategy": strat, "bias": bias_label, "rr": rr_label,
                    "total": 0, "wins": 0, "losses": 0, "wr": 0.0,
                    "pnl": 0.0, "pf": 0.0, "sharpe": 0.0, "maxdd": 0.0, "ret": 0.0,
                    "_error": str(exc),
                })

    return results


def _results_table(rows: list[dict], title: str = "Backtest Sonuçları") -> Table:
    t = Table(
        title=title,
        box=MINIMAL_DOUBLE_HEAD,
        border_style=C_BLUE,
        header_style=f"bold {C_MAUVE}",
        show_footer=False,
        padding=(0, 1),
    )
    t.add_column("Strateji", style=C_FG2, no_wrap=True)
    t.add_column("Bias",     style=C_BLUE)
    t.add_column("RR",       style=C_FG2)
    t.add_column("İşlem",    justify="right")
    t.add_column("W/L",      justify="right")
    t.add_column("WR %",     justify="right")
    t.add_column("NetPnL $", justify="right")
    t.add_column("Ret %",    justify="right")
    t.add_column("PF",       justify="right")
    t.add_column("Sharpe",   justify="right")
    t.add_column("MaxDD %",  justify="right")

    for r in rows:
        if r.get("_error"):
            t.add_row(r["strategy"], r["bias"], r["rr"],
                      "—", "—", "—", "—", "—", "—", "—",
                      f"[{C_RED}]HATA[/]")
            continue

        wr_color = C_GREEN if r["wr"] >= 50 else (C_YEL if r["wr"] >= 40 else C_RED)
        pnl_color = C_GREEN if r["pnl"] >= 0 else C_RED
        pf_color  = C_GREEN if r["pf"] >= 1.5 else (C_YEL if r["pf"] >= 1.0 else C_RED)

        t.add_row(
            r["strategy"].upper(),
            r["bias"],
            r["rr"],
            str(r["total"]) if r["total"] else "[dim]—[/]",
            f"{r['wins']}/{r['losses']}" if r["total"] else "[dim]—[/]",
            f"[{wr_color}]{r['wr']:.1f}[/]" if r["total"] else "[dim]—[/]",
            f"[{pnl_color}]{r['pnl']:+,.2f}[/]" if r["total"] else "[dim]—[/]",
            f"{r['ret']:+.2f}" if r["total"] else "[dim]—[/]",
            f"[{pf_color}]{r['pf']:.2f}[/]" if r["total"] else "[dim]—[/]",
            f"{r['sharpe']:.2f}"  if r["total"] else "[dim]—[/]",
            f"[{C_YEL}]{r['maxdd']:.2f}[/]" if r["total"] else "[dim]—[/]",
        )
    return t


# ═══════════════════════════════════════════════════════════════════════════════
# MENÜ: BACKTEST
# ═══════════════════════════════════════════════════════════════════════════════

def backtest_menu() -> None:
    console.clear()
    _print_header()
    console.print(Panel("[bold]BACKTEST[/]  — Strateji & Parametre Seçimi",
                        style=C_MAUVE, box=ROUNDED, padding=(0, 2)))
    console.print()

    cfg = get_config()

    # Strateji
    strat_table = Table(box=SIMPLE_HEAVY, show_header=False,
                        border_style=C_BLUE, padding=(0, 2))
    strat_table.add_column(); strat_table.add_column()
    strat_table.add_row(f"[bold {C_YEL}]fvg[/]",     "FVG v10  (Fair Value Gap)")
    strat_table.add_row(f"[bold {C_YEL}]threevol[/]", "Three Vol Directional")
    strat_table.add_row(f"[bold {C_YEL}]london[/]",   "London Reversal  (ICT Judas Swing)")
    strat_table.add_row(f"[bold {C_YEL}]qwe[/]",      "QWE  (Fib Pullback: BOS+HH + hacim onayı)")
    strat_table.add_row(f"[bold {C_YEL}]hepsi[/]",    "Hepsi  (fvg + threevol + london + qwe)")
    console.print(strat_table)
    strategy = _pick("Strateji seç",
                     ["fvg","harmonic","threevol","london","qwe","hepsi"], "fvg")

    # ── SABİT PRESET'ler: soru yok — her strateji kendi doğrulanmış
    #    en-kârlı-none konfigürasyonuyla koşar (config'ten) ────────────────
    console.print()
    presets = _strategy_presets(cfg)
    pt = Table(box=SIMPLE_HEAVY, border_style=C_TEAL, padding=(0, 2),
               title=f"[bold {C_TEAL}]Sabit Preset'ler[/] [dim](1 yıllık dürüst grid)[/]")
    pt.add_column("Strateji", style=f"bold {C_YEL}")
    pt.add_column("Bias"); pt.add_column("RR"); pt.add_column("EMA-MACD")
    _sec_map = {"fvg": "fvg", "harmonic": "harmonic", "threevol": "threevol",
                "london": "london_reversal", "qwe": "qwe"}
    shown = ([s for s in ["fvg", "harmonic", "threevol", "london", "qwe"]
              if bool(cfg.get(_sec_map[s], "enabled", default=True))]
             if strategy == "hepsi" else [strategy])
    for s in shown:
        p = presets[s]
        pt.add_row(s.upper(), f"{p['bias']} (sabit)", p["rr"],
                   "açık" if p["emf"] else "kapalı")
    console.print(pt)

    # Sermaye
    console.print()
    capital_default = int(cfg.initial_capital)
    capital = IntPrompt.ask(
        f"  Başlangıç sermayesi [$]  [dim](varsayılan: {capital_default:,})[/]",
        default=capital_default,
        console=console,
    )

    # Onay
    console.print()
    summary = Table(box=SIMPLE_HEAVY, show_header=False,
                    border_style=C_TEAL, padding=(0, 2))
    summary.add_column("Parametre", style=C_FG2)
    summary.add_column("Değer",     style=f"bold {C_BLUE}")
    summary.add_row("Strateji", strategy.upper())
    summary.add_row("Ayarlar",  "sabit preset'ler (yukarıdaki tablo)")
    summary.add_row("Sermaye",  f"${capital:,}")
    console.print(Panel(summary, title="[bold]Özet[/]", style=C_TEAL, box=ROUNDED))

    if not _confirm("Backtesti başlat?"):
        return

    # Çalıştır
    console.print()
    console.print(Rule(f"[bold {C_GREEN}]Backtest çalışıyor…[/]", style=C_GREEN))

    rows: list[dict] = []
    done = threading.Event()
    error_box: list[str] = []

    def worker():
        try:
            r = _run_strategy(strategy, capital=float(capital))
            rows.extend(r)
        except Exception as e:
            error_box.append(str(e))
        finally:
            done.set()

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    # Spinner ile bekle
    with Live(Spinner("dots", text=f"[{C_BLUE}] Hesaplanıyor…"), console=console,
              refresh_per_second=10, transient=True):
        done.wait()

    if error_box:
        _err(f"Backtest hatası: {error_box[0]}")
    else:
        console.print()
        console.print(_results_table(
            rows, title=f"Backtest Sonuçları  [{strategy.upper()} | sabit preset]"))

    console.print()
    Prompt.ask(f"  [dim]Devam için Enter'a bas[/]", default="", show_default=False,
               console=console)


# ═══════════════════════════════════════════════════════════════════════════════
# MENÜ: WALK-FORWARD ANALİZİ
# ═══════════════════════════════════════════════════════════════════════════════

def wfa_menu() -> None:
    console.clear()
    _print_header()
    console.print(Panel(
        "[bold]WALK-FORWARD ANALİZİ[/]  — In-Sample Optimize → Out-of-Sample Kör Test",
        style=C_MAUVE, box=ROUNDED, padding=(0, 2)))
    console.print()

    in_months  = IntPrompt.ask("  IS (in-sample) ay sayısı", default=3, console=console)
    out_months = IntPrompt.ask("  OOS (out-of-sample) ay sayısı", default=1, console=console)
    n_windows  = IntPrompt.ask("  Pencere sayısı", default=4, console=console)
    capital    = IntPrompt.ask("  Başlangıç sermayesi [$]",
                               default=int(get_config().initial_capital), console=console)

    if not _confirm(f"WFA başlat?  ({n_windows} pencere, IS:{in_months}ay, OOS:{out_months}ay)"):
        return

    console.print()
    console.print(Rule(f"[bold {C_GREEN}]WFA çalışıyor…[/]", style=C_GREEN))

    results: list[dict] = []
    done = threading.Event()
    error_box: list[str] = []

    def worker():
        try:
            sys.path.insert(0, str(ROOT / "scripts"))
            from scripts.run_test_matrix import run_wfa, run_one
            from xauusd_fvg_engine_v10 import DataEngine
            df_1h, df_5m, bt_start = _load_data()
            r = run_wfa(df_1h, df_5m, bt_start,
                        in_months=in_months, out_months=out_months, n_windows=n_windows)
            results.extend(r)
        except Exception as e:
            error_box.append(str(e))
        finally:
            done.set()

    threading.Thread(target=worker, daemon=True).start()

    with Live(Spinner("dots", text=f"[{C_BLUE}] Optimizasyon yapılıyor…"), console=console,
              refresh_per_second=10, transient=True):
        done.wait()

    if error_box:
        _err(f"WFA hatası: {error_box[0]}")
    else:
        # Tablo
        t = Table(title="Walk-Forward Analiz Sonuçları",
                  box=MINIMAL_DOUBLE_HEAD, border_style=C_BLUE,
                  header_style=f"bold {C_MAUVE}", padding=(0, 1))
        t.add_column("#",         justify="center")
        t.add_column("IS Dönemi",  style=C_FG2)
        t.add_column("OOS Dönemi", style=C_FG2)
        t.add_column("En İyi IS",  style=C_BLUE)
        t.add_column("OOS İşl",    justify="right")
        t.add_column("OOS WR%",    justify="right")
        t.add_column("OOS PnL$",   justify="right")

        cum_pnl = 0.0
        wr_list = []
        for r in results:
            m = r.get("oos_m")
            is_lbl  = f"{r['is_s'].strftime('%Y-%m')}→{r['is_e'].strftime('%Y-%m')}"
            oos_lbl = f"{r['is_e'].strftime('%Y-%m')}→{r['oos_e'].strftime('%Y-%m')}"
            if m and m["total"] > 0:
                cum_pnl += m["net_pnl"]
                wr_list.append(m["win_rate"] * 100)
                wr_col = C_GREEN if m["win_rate"] >= 0.5 else C_YEL
                pnl_col = C_GREEN if m["net_pnl"] >= 0 else C_RED
                t.add_row(
                    str(r["window"]),
                    is_lbl, oos_lbl, r["cfg"],
                    str(m["total"]),
                    f"[{wr_col}]{m['win_rate']*100:.1f}[/]",
                    f"[{pnl_col}]{m['net_pnl']:+,.2f}[/]",
                )
            else:
                t.add_row(str(r["window"]), is_lbl, oos_lbl, r["cfg"],
                          "—", "—", "—")

        console.print(t)
        avg_wr = sum(wr_list) / len(wr_list) if wr_list else 0
        pnl_col = C_GREEN if cum_pnl >= 0 else C_RED
        console.print(
            f"\n  OOS Kümülatif PnL: [{pnl_col}]${cum_pnl:+,.2f}[/]   "
            f"│   Ort OOS WR: [bold]{avg_wr:.1f}%[/]"
        )

    console.print()
    Prompt.ask("  [dim]Devam için Enter[/]", default="", show_default=False, console=console)


# ═══════════════════════════════════════════════════════════════════════════════
# MENÜ: TAM MATRİS (BÖLÜM A+C+G+H)
# ═══════════════════════════════════════════════════════════════════════════════

def full_matrix_menu() -> None:
    console.clear()
    _print_header()
    console.print(Panel(
        "[bold]TAM TEST MATRİSİ[/]  — run_test_matrix.py  (BÖLÜM T+A+C+G+H+W)",
        style=C_MAUVE, box=ROUNDED, padding=(0, 2)))
    console.print()
    _info("Bu bölüm scripts/run_test_matrix.py'yi tam olarak çalıştırır.")
    _info("Tamamlanması 5-15 dakika sürebilir.")
    console.print()

    if not _confirm("Tam matris testini başlat?"):
        return

    console.print(Rule(f"[bold {C_GREEN}]Tam Matris çalışıyor…[/]", style=C_GREEN))

    output_lines: list[str] = []
    done = threading.Event()
    error_box: list[str] = []

    def worker():
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                sys.path.insert(0, str(ROOT / "scripts"))
                import importlib, scripts.run_test_matrix as rtm
                importlib.reload(rtm)
                rtm.main()
            output_lines.extend(buf.getvalue().splitlines())
        except Exception as e:
            error_box.append(str(e))
        finally:
            done.set()

    threading.Thread(target=worker, daemon=True).start()

    with Live(Spinner("dots", text=f"[{C_BLUE}] Matris hesaplanıyor… (uzun sürebilir)"),
              console=console, refresh_per_second=5, transient=True):
        done.wait()

    if error_box:
        _err(f"Matris hatası: {error_box[0]}")
    else:
        for line in output_lines:
            console.print(line)

    console.print()
    Prompt.ask("  [dim]Devam için Enter[/]", default="", show_default=False, console=console)


# ═══════════════════════════════════════════════════════════════════════════════
# MENÜ: VERİ İNDİR
# ═══════════════════════════════════════════════════════════════════════════════

def download_menu() -> None:
    console.clear()
    _print_header()
    console.print(Panel(
        "[bold]VERİ İNDİR / GÜNCELLE[/]  — XAUUSD OHLCV",
        style=C_MAUVE, box=ROUNDED, padding=(0, 2)))
    console.print()

    cfg = get_config()
    f5m = cfg.csv_5m
    f1h = cfg.csv_1h
    _info(f"5M dosyası : {f5m}")
    _info(f"1H dosyası : {f1h}")
    console.print()

    mode = _pick("Kaynak seç",
                 ["yfinance", "bingx", "kontrol"],
                 "yfinance")

    if mode == "kontrol":
        from xauusd_fvg_engine_v10 import DataEngine
        df_1h, df_5m, bt_start = _load_data()
        console.print()
        _ok(f"5M: {len(df_5m):,} mum  |  Son: {df_5m.index[-1]}")
        _ok(f"1H: {len(df_1h):,} mum  |  Son: {df_1h.index[-1]}")
        _ok(f"Backtest başlangıcı: {bt_start}")
    else:
        _info("download_data.py çalıştırılıyor…")
        import subprocess
        args = ["python3", str(ROOT / "download_data.py")]
        if mode == "bingx":
            args.append("--bingx")
        result = subprocess.run(args, capture_output=False)
        if result.returncode == 0:
            _ok("İndirme tamamlandı.")
        else:
            _err("İndirme sırasında hata oluştu.")

    console.print()
    Prompt.ask("  [dim]Devam için Enter[/]", default="", show_default=False, console=console)


# ═══════════════════════════════════════════════════════════════════════════════
# MENÜ: AYARLAR
# ═══════════════════════════════════════════════════════════════════════════════

def settings_menu() -> None:
    console.clear()
    _print_header()
    console.print(Panel("[bold]AYARLAR[/]  — config/default.json",
                        style=C_MAUVE, box=ROUNDED, padding=(0, 2)))
    console.print()

    cfg = get_config()

    def _show_current() -> None:
        t = Table(box=SIMPLE_HEAVY, show_header=True,
                  border_style=C_BLUE, header_style=f"bold {C_MAUVE}",
                  padding=(0, 2))
        t.add_column("Parametre",    style=C_FG2)
        t.add_column("Mevcut Değer", style=f"bold {C_BLUE}")
        t.add_column("Açıklama",     style=C_FG2)

        rows = [
            ("backtest.initial_capital", f"${cfg.initial_capital:,.0f}", "Başlangıç sermayesi"),
            ("risk.risk_fraction",       f"{cfg.risk_fraction*100:.2f}%", "İşlem başına risk"),
            ("risk.sl_buffer",           f"{cfg.sl_buffer*100:.3f}%", "SL buffer"),
            ("risk.max_risk_dollar",     f"${cfg.get('risk','max_risk_dollar',default=150)}", "Max risk $"),
            ("profile",
             ("SCALP ⚠" if cfg.get("profile", default="swing") != "swing"
              else "swing"), "Profil (swing / scalp)"),
            ("live.leverage",            str(cfg.get("live","leverage",default=10)), "Kaldıraç"),
            ("live.risk_pct",            f"{cfg.get('live','risk_pct',default=1.0)}%", "Canlı risk%"),
            ("live.dry_run",             str(cfg.get("live","dry_run",default=True)), "Kağıt trade?"),
            ("private_bias.vol_lambda",  str(cfg.get("private_bias","vol_lambda",default=0.94)), "EWMA λ"),
            ("private_bias.vol_mult",    str(cfg.get("private_bias","vol_mult",default=1.20)), "Trending eşiği"),
            ("private_bias.ema_fast",    str(cfg.get("private_bias","ema_fast",default=21)), "EMA hızlı"),
            ("private_bias.ema_slow",    str(cfg.get("private_bias","ema_slow",default=55)), "EMA yavaş"),
            ("live.order_flow_guard",
             ("AÇIK ⚠" if (cfg.get("live","order_flow_guard",default={}) or {})
              .get("enabled") else "kapalı"),
             "Mikro-yapı (CVD+emir defteri) — CANLI-ÖZEL, backtest EDİLEMEZ"),
        ]
        for k, v, d in rows:
            t.add_row(k, v, d)
        console.print(t)

    _show_current()
    console.print()

    # Hangi ayarı değiştir
    options = {
        "1": ("backtest", "initial_capital"),
        "2": ("risk", "risk_fraction"),
        "3": ("risk", "sl_buffer"),
        "4": ("live", "leverage"),
        "5": ("live", "risk_pct"),
        "6": ("live", "dry_run"),
        "7": ("private_bias", "vol_lambda"),
        "8": ("private_bias", "vol_mult"),
        "9": ("private_bias", "ema_fast"),
        "10": ("private_bias", "ema_slow"),
        "o": ("order_flow", ""),
        "g": ("geri", ""),
    }

    choice_list = [str(i) for i in range(1, 11)] + ["o", "g"]
    for k, (sec, param) in options.items():
        if sec == "geri":
            console.print(f"  [{C_YEL}]{k}[/] → Geri")
        elif sec == "order_flow":
            of = (cfg.get("live", "order_flow_guard", default={}) or {})
            dur = "AÇIK ⚠" if of.get("enabled") else "kapalı"
            console.print(f"  [{C_YEL}]{k}[/] → [bold]MİKRO-YAPI KORUMASI[/] "
                          f"(order flow) — şu an: [bold]{dur}[/]")
        else:
            console.print(f"  [{C_YEL}]{k}[/] → {sec}.{param}")

    console.print()
    choice_list = list(choice_list) + ["p"]
    console.print(f"  [bold {C_YEL}]p[/]  Profil değiştir  (swing ↔ scalp)")
    sel = _pick("Değiştirilecek parametre", choice_list, "g")
    if sel == "p":
        cur = str(cfg.get("profile", default="swing") or "swing")
        console.print()
        console.print(Panel(
            f"[{C_YEL}]swing[/]  — ana sistem, 5 yıllık IS/OOS elemesinden geçti.\n"
            f"          BingX +134.4R (34.586$) · MT5 +166.6R (47.444$)\n"
            f"          Düşüş %12.3 · pozitif ay %62 · medyan kaldıraç 1.3x\n"
            f"          Prop (%10 limit): risk %0.56 → 28.560$\n\n"
            f"[{C_YEL}]scalp[/]  — [bold]YALNIZ MT5[/]. Dar stop, 1:3 hedef, 8s zaman çıkışı.\n"
            f"          MT5 +102.7R (26.715$) · düşüş %10.2 · pozitif ay %65\n"
            f"          Medyan süre 3.1 saat · medyan stop 6.3$\n"
            f"          Prop (%10 limit): risk %0.74 → 20.854$\n"
            f"          [bold {C_RED}]BingX'te −0.7R[/] (ücret_R 0.30 vs MT5 0.019)\n"
            f"          [bold {C_RED}]IS/OOS elemesinden GEÇMEDİ[/]\n"
            f"          [bold {C_RED}]Kaldıraç: medyan 4.4x, %95 dilim 11.4x, uç 38.4x[/]\n"
            f"          Broker limiti bunun altındaysa bazı işlemler açılamaz.",
            style=C_BLUE, box=ROUNDED, padding=(0, 2)))
        new = _pick("Profil", ["swing", "scalp"], cur)
        cfg.set("profile", new)
        cfg.save()
        _ok(f"profile → {new}  |  config/default.json kaydedildi.")
        warn = _profile_broker_conflict(cfg)
        if warn:
            _err(warn)
            _info("Canlı işlem menüsü bu profille BingX'i kabul etmez. "
                  "Broker'ı MT5 yapın (menü 6) veya profili swing'e alın.")
        console.print()
        Prompt.ask("  [dim]Devam için Enter[/]", default="",
                   show_default=False, console=console)
        return
    if sel == "g":
        return

    if sel == "o":
        of = dict(cfg.get("live", "order_flow_guard", default={}) or {})
        console.print()
        console.print(Panel(
            "[bold]MİKRO-YAPI (ORDER FLOW) KORUMASI[/]\n\n"
            "Sinyal anında BingX emir defterine ve son işlemlere bakar;\n"
            "tahta sinyalin aksini söylüyorsa girişi iptal eder.\n"
            "  • [bold]CVD[/]: agresör bazlı alım−satım hacim farkı\n"
            "  • [bold]Dengesizlik[/]: bid/ask duvar kalınlığı oranı\n\n"
            f"[bold {C_RED}]⚠ UYARI:[/] Bu filtre sistemin geri kalanından "
            "FARKLIDIR — tarihsel emir defteri/tick verisi olmadığı için "
            "[bold]ASLA BACKTEST EDİLMEDİ[/]. Diğer tüm mekanizmalar 5 yıllık "
            "IS/OOS testinden geçti, bu geçmedi.\n"
            "Ölçebildiğimiz vekil (proxy) CVD testi, 'CVD sinyali doğrulasın' "
            "kuralının backtest'te [bold]kaybettirdiğini[/] gösterdi "
            "(+115.9R → +87.2R). Gerçek agresör CVD'si farklı davranabilir "
            "ama bu bilinmiyor.\n\n"
            "Yalnız CANLI modda çalışır; backtest sonuçlarını etkilemez.",
            style=C_YEL, box=ROUNDED, padding=(1, 2)))
        console.print()
        yeni = _confirm("Mikro-yapı korumasını AÇ (E) / KAPAT (H)",
                        default=bool(of.get("enabled", False)))
        of["enabled"] = yeni
        if yeni:
            of["use_cvd"] = _confirm("  CVD kontrolü kullanılsın mı?",
                                     default=bool(of.get("use_cvd", True)))
            of["use_imbalance"] = _confirm("  Emir defteri dengesizliği kullanılsın mı?",
                                           default=bool(of.get("use_imbalance", True)))
            of["cvd_window_sec"] = IntPrompt.ask(
                "  CVD penceresi (saniye)",
                default=int(of.get("cvd_window_sec", 60)), console=console)
            of["cvd_block_ratio"] = FloatPrompt.ask(
                "  CVD engel eşiği (0-1; 0.65 = %65 ters agresyon)",
                default=float(of.get("cvd_block_ratio", 0.65)), console=console)
            of["imbalance_block"] = FloatPrompt.ask(
                "  Dengesizlik engel eşiği (2.0 = karşı duvar 2 kat kalın)",
                default=float(of.get("imbalance_block", 2.0)), console=console)
        cfg.set("live", "order_flow_guard", of)
        cfg.save()
        _ok(f"Mikro-yapı koruması → {'AÇIK ⚠ (test edilmemiş)' if yeni else 'kapalı'}"
            "  |  config/default.json kaydedildi.")
        console.print()
        Prompt.ask("  [dim]Devam için Enter[/]", default="", show_default=False,
                   console=console)
        return

    sec, param = options[sel]
    current = cfg.get(sec, param)

    if isinstance(current, bool):
        new_val = _confirm(f"{sec}.{param} (E/H)", default=current)
        cfg.set(sec, param, new_val)
    elif isinstance(current, float):
        new_val = FloatPrompt.ask(
            f"  Yeni değer [{sec}.{param}]  [dim](mevcut: {current})[/]",
            default=current, console=console)
        cfg.set(sec, param, new_val)
    elif isinstance(current, int):
        new_val = IntPrompt.ask(
            f"  Yeni değer [{sec}.{param}]  [dim](mevcut: {current})[/]",
            default=current, console=console)
        cfg.set(sec, param, new_val)

    cfg.save()
    _ok(f"{sec}.{param} → {new_val}  |  config/default.json kaydedildi.")
    console.print()
    Prompt.ask("  [dim]Devam için Enter[/]", default="", show_default=False, console=console)


# ═══════════════════════════════════════════════════════════════════════════════
# CANLI İŞLEM (BingX / MetaTrader 5)
# ═══════════════════════════════════════════════════════════════════════════════

def live_menu() -> None:
    """Canlı/dry-run botu başlat. Broker seçimi: BingX (REST) veya MT5."""
    console.clear()
    _print_header()
    console.print(_divider("CANLI İŞLEM"))
    cfg = get_config()

    # MT5 bu makinede kullanılabilir mi?
    try:
        from mt5_client import available as _mt5_available
        mt5_ok, mt5_why = _mt5_available()
    except Exception as e:
        mt5_ok, mt5_why = False, f"mt5_client yüklenemedi: {e}"

    t = Table(box=SIMPLE_HEAVY, show_header=False, border_style=C_BLUE,
              padding=(0, 2))
    t.add_column("k", style=f"bold {C_YEL}", no_wrap=True)
    t.add_column("v", style=C_FG)
    t.add_row("Strateji",  str(cfg.get("live", "strategy", default="fvg")))
    t.add_row("Broker",    str(cfg.get("live", "broker",   default="bingx")))
    _pf = str(cfg.get("profile", default="swing") or "swing")
    t.add_row("Profil",    (_pf if _pf == "swing"
                            else f"[{C_YEL}]{_pf}[/]  (MT5/prop için)"))
    t.add_row("Risk",      f'%{cfg.get("live", "risk_pct", default=1.0)}')
    t.add_row("Kaldıraç",  f'{cfg.get("live", "leverage", default=10)}x')
    t.add_row("Dry-run",   ("AÇIK (emir gönderilmez)"
                            if cfg.get("live", "dry_run", default=True)
                            else f"[bold {C_RED}]KAPALI — GERÇEK EMİR[/]"))
    t.add_row("BingX sembol", str(cfg.get("live", "symbol", default="-")))
    _m = cfg.get("live", "mt5", default={}) or {}
    t.add_row("MT5 sembol",   str(_m.get("symbol", "XAUUSD")))
    t.add_row("MT5 durumu",   (f"[{C_GREEN}]{mt5_why}[/]" if mt5_ok
                               else f"[{C_RED}]{mt5_why}[/]"))
    console.print(t)

    choices = ["bingx"] + (["mt5"] if mt5_ok else []) + ["q"]
    if not mt5_ok:
        console.print()
        console.print(Panel(
            f"[{C_YEL}]MT5 bu makinede kullanılamıyor.[/]\n"
            "MetaTrader5 Python paketi YALNIZCA Windows'ta ve MT5 terminali "
            "ile aynı makinede çalışır. Windows'ta:  pip install MetaTrader5\n"
            "Ayrıca sembolü MT5 Market Watch'a ekleyip config'e doğru adı "
            "yazın (XAUUSD / XAUUSD.a / GOLD / XAUUSDm).",
            style=C_YEL, box=ROUNDED, padding=(0, 2)))

    broker = _pick("Broker seç", choices,
                   str(cfg.get("live", "broker", default="bingx")))
    if broker == "q":
        return

    conflict = _profile_broker_conflict(cfg, broker)
    if conflict:
        console.print()
        console.print(Panel(
            f"[bold {C_RED}]ENGELLENDİ[/]  {conflict}\n\n"
            "Scalp profili yalnızca MT5 komisyon yapısında kârlıdır: 6.3$'lık "
            "stopta ücret 1R kazancın BingX'te %30'unu, MT5'te %1.9'unu yer. "
            "BingX'te scalp 5 yılda −0.7R getiriyor.\n\n"
            "Ayarlar → p ile profili 'swing' yapın veya MT5 brokerını seçin.",
            style=C_RED, box=ROUNDED, padding=(0, 2)))
        console.print()
        Prompt.ask("  [dim]Devam için Enter[/]", default="",
                   show_default=False, console=console)
        return

    if broker != str(cfg.get("live", "broker", default="bingx")):
        cfg.set("live", "broker", broker)
        cfg.save()
        _ok(f"live.broker → {broker}  (config/default.json kaydedildi)")

    dry = cfg.get("live", "dry_run", default=True)
    if not dry:
        console.print()
        console.print(Panel(
            f"[bold {C_RED}]DRY-RUN KAPALI — GERÇEK PARA İLE EMİR "
            f"GÖNDERİLECEK.[/]\n"
            "Ayarlar menüsünden live.dry_run=true yaparak kağıt moda "
            "geçebilirsiniz.",
            style=C_RED, box=ROUNDED, padding=(0, 2)))
        if not _confirm("Gerçek emir göndermeyi onaylıyor musunuz?",
                        default=False):
            _info("İptal edildi.")
            Prompt.ask("  [dim]Devam için Enter[/]", default="",
                       show_default=False, console=console)
            return

    if broker == "mt5":
        console.print()
        console.print(Panel(
            f"[{C_YEL}]MT5 farkları:[/]\n"
            "• Miktar LOT cinsinden gider (1 lot ≈ 100 ons) — istemci "
            "çeviriyi kendisi yapar.\n"
            "• Mum zamanları broker sunucu saatindedir; UTC farkı otomatik "
            "bulunur (config live.mt5.time_offset_hours ile ezilebilir).\n"
            "• MT5'te genel işlem akışı (tape) yoktur → OrderFlowGuard'ın "
            "CVD bileşeni çalışmaz.\n"
            "• Kaldıraç MT5'te broker hesap ayarıdır, API'den değiştirilemez.",
            style=C_BLUE, box=ROUNDED, padding=(0, 2)))

    cmd = [sys.executable, str(ROOT / "xauusd_live_trader.py"),
           "--broker", broker]
    if dry:
        cmd.append("--dry-run")
    console.print()
    _info("Çalıştırılıyor:  " + " ".join(cmd))
    _info("Durdurmak için Ctrl+C.")
    console.print()
    import subprocess
    try:
        subprocess.run(cmd, cwd=str(ROOT))
    except KeyboardInterrupt:
        console.print(f"\n  [{C_YEL}]Bot durduruldu.[/]")
    except Exception as e:
        _err(f"Bot başlatılamadı: {e}")
    console.print()
    Prompt.ask("  [dim]Devam için Enter[/]", default="", show_default=False,
               console=console)


# ═══════════════════════════════════════════════════════════════════════════════
# ANA MENÜ
# ═══════════════════════════════════════════════════════════════════════════════

def _main_menu_panel() -> Panel:
    t = Table(box=SIMPLE_HEAVY, show_header=False,
              border_style=C_BLUE, padding=(0, 3))
    t.add_column("Tuş",  style=f"bold {C_YEL}", no_wrap=True)
    t.add_column("İşlev", style=C_FG)
    t.add_row("1", "Backtest Çalıştır")
    t.add_row("2", "Walk-Forward Analizi  (IS optimize → OOS kör test)")
    t.add_row("3", "Tam Test Matrisi  (BÖLÜM A+C+G+H+W — uzun sürer)")
    t.add_row("4", "Veri İndir / Güncelle")
    t.add_row("5", "Ayarlar  (config/default.json)")
    t.add_row("6", "Canlı İşlem  (BingX / MetaTrader 5)")
    t.add_row("q", f"[{C_RED}]Çıkış[/]")
    return Panel(t, title="[bold]ANA MENÜ[/]", style=C_BLUE,
                 box=ROUNDED, padding=(1, 2))


def main() -> None:
    MENU = {
        "1": backtest_menu,
        "2": wfa_menu,
        "3": full_matrix_menu,
        "4": download_menu,
        "5": settings_menu,
        "6": live_menu,
    }

    while True:
        console.clear()
        _print_header()
        console.print(_main_menu_panel())
        console.print()

        choice = Prompt.ask(
            f"  [{C_YEL}]Seçim[/]",
            choices=["1", "2", "3", "4", "5", "6", "q"],
            default="1",
            console=console,
        )

        if choice == "q":
            console.print()
            console.print(Panel(
                f"[bold {C_GREEN}]İyi tradeler![/]  XAUUSD FVG System v10",
                style=C_GREEN, box=ROUNDED, padding=(0, 4)))
            console.print()
            sys.exit(0)

        fn = MENU.get(choice)
        if fn:
            fn()


# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print(f"\n  [{C_RED}]Kullanıcı tarafından durduruldu.[/]")
        sys.exit(0)
