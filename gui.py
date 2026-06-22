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


def _run_strategy(strategy: str, bias: str, rr_label: str, tbe_label: str,
                  emf: bool, capital: float) -> list[dict]:
    """Seçilen parametrelerle backtest çalıştır, satır listesi döndür."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from xauusd_fvg_engine_v10 import (
        DataEngine, MarketBrain, RiskManager, BacktestEngine,
        PerformanceAnalytics, WeeklyBiasProvider, DailyBiasProvider,
        PrivateBiasProvider, ThreeVolBrain,
        LondonReversalBrain, LondonBacktestEngine,
    )
    from config import get_config

    cfg = get_config()

    # RR / BE decode
    rr_map = {"1:1": (1.0, None), "1:2be": (2.0, 1.0), "1:2fix": (2.0, None)}
    rr, be = rr_map.get(rr_label, (2.0, None))

    # TBE decode (5M bar cinsinden)
    tbe_map = {"yok": None, "2h": 24, "4h": 48, "8h": 96}
    tbe = tbe_map.get(tbe_label, None)

    # Bias modes
    bias_modes = ["weekly", "daily", "none", "private"] if bias == "hepsi" else [bias]

    # Strategy modes
    if strategy == "hepsi":
        strategies = ["fvg", "threevol", "london"]
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

    for strat in strategies:
        for bmode in bias_modes:
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    bp = make_bias(bmode)

                    if strat == "london":
                        brain  = LondonReversalBrain(bias_provider=bp)
                        risk   = RiskManager(rr=rr, sl_buffer=cfg.sl_buffer)
                        engine = LondonBacktestEngine(
                            brain, risk,
                            initial_capital=capital,
                            breakeven_at_R=be,
                            time_exit_bars=tbe,
                            ema_macd_filter=emf,
                        )
                    else:
                        poi = "three_vol" if strat == "threevol" else "all"
                        brain  = MarketBrain(bias_provider=bp, poi_mode=poi)
                        risk   = RiskManager(rr=rr, sl_buffer=cfg.sl_buffer)
                        engine = BacktestEngine(
                            brain, risk,
                            initial_capital=capital,
                            breakeven_at_R=be,
                            time_exit_bars=tbe,
                            ema_macd_filter=emf,
                        )

                    trades  = engine.run(df_1h, df_5m, bt_start)
                    metrics = PerformanceAnalytics(trades, capital).compute()

                if metrics is None or metrics["total"] == 0:
                    results.append({
                        "strategy": strat, "bias": bmode, "rr": rr_label,
                        "total": 0, "wins": 0, "losses": 0, "wr": 0.0,
                        "pnl": 0.0, "pf": 0.0, "sharpe": 0.0, "maxdd": 0.0, "ret": 0.0,
                    })
                else:
                    results.append({
                        "strategy": strat, "bias": bmode, "rr": rr_label,
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
            except Exception as exc:
                results.append({
                    "strategy": strat, "bias": bmode, "rr": rr_label,
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
    strat_table.add_row(f"[bold {C_YEL}]hepsi[/]",    "Hepsi  (fvg + threevol + london)")
    console.print(strat_table)
    strategy = _pick("Strateji seç", ["fvg","threevol","london","hepsi"], "fvg")

    # Bias
    console.print()
    bias_table = Table(box=SIMPLE_HEAVY, show_header=False,
                       border_style=C_BLUE, padding=(0, 2))
    bias_table.add_column(); bias_table.add_column()
    bias_table.add_row(f"[{C_YEL}]weekly[/]",  "Manuel haftalık yön (weekly_bias.json)")
    bias_table.add_row(f"[{C_YEL}]daily[/]",   "Günlük yön (daily_bias.json)")
    bias_table.add_row(f"[{C_YEL}]none[/]",    "Bias yok  (EMA-MACD filtresi devreye girer)")
    bias_table.add_row(f"[{C_YEL}]private[/]", "Otomatik GARCH rejim tespiti")
    bias_table.add_row(f"[{C_YEL}]hepsi[/]",   "Tüm bias modları")
    console.print(bias_table)
    bias = _pick("Bias seç", ["weekly","daily","none","private","hepsi"],
                 cfg.get("backtest", "default_bias", default="weekly"))

    # RR
    console.print()
    rr = _pick("Risk/Ödül seç", ["1:1","1:2be","1:2fix"], "1:2fix")

    # TBE
    console.print()
    tbe = _pick("Zaman çıkışı (TBE)", ["yok","2h","4h","8h"], "8h")

    # EMA-MACD filtre
    console.print()
    emf = _confirm("EMA-MACD filtresi uygulansın mı?", default=False)

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
    summary.add_row("Bias",     bias)
    summary.add_row("RR",       rr)
    summary.add_row("TBE",      tbe)
    summary.add_row("EMA-MACD", "Evet" if emf else "Hayır")
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
            r = _run_strategy(strategy, bias, rr, tbe, emf, float(capital))
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
        console.print(_results_table(rows, title=f"Backtest Sonuçları  [{strategy.upper()} | {bias} | {rr}]"))

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
            ("live.leverage",            str(cfg.get("live","leverage",default=10)), "Kaldıraç"),
            ("live.risk_pct",            f"{cfg.get('live','risk_pct',default=1.0)}%", "Canlı risk%"),
            ("live.dry_run",             str(cfg.get("live","dry_run",default=True)), "Kağıt trade?"),
            ("private_bias.vol_lambda",  str(cfg.get("private_bias","vol_lambda",default=0.94)), "EWMA λ"),
            ("private_bias.vol_mult",    str(cfg.get("private_bias","vol_mult",default=1.20)), "Trending eşiği"),
            ("private_bias.ema_fast",    str(cfg.get("private_bias","ema_fast",default=21)), "EMA hızlı"),
            ("private_bias.ema_slow",    str(cfg.get("private_bias","ema_slow",default=55)), "EMA yavaş"),
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
        "g": ("geri", ""),
    }

    choice_list = [str(i) for i in range(1, 11)] + ["g"]
    for k, (sec, param) in options.items():
        if sec == "geri":
            console.print(f"  [{C_YEL}]{k}[/] → Geri")
        else:
            console.print(f"  [{C_YEL}]{k}[/] → {sec}.{param}")

    console.print()
    sel = _pick("Değiştirilecek parametre", choice_list, "g")
    if sel == "g":
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
    }

    while True:
        console.clear()
        _print_header()
        console.print(_main_menu_panel())
        console.print()

        choice = Prompt.ask(
            f"  [{C_YEL}]Seçim[/]",
            choices=["1", "2", "3", "4", "5", "q"],
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
