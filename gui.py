"""
gui.py — XAUUSD FVG Trading System v10  Modern Kontrol Paneli
=============================================================
Çalıştır: python3 gui.py
Gereksinim: Python 3.9+  (tkinter standart kütüphane)
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Any, Optional

# ── Proje kök dizininden çalıştığımızdan emin ol ─────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from config import Config, get_config

# ═══════════════════════════════════════════════════════════════════════════════
# TEMA & STİL
# ═══════════════════════════════════════════════════════════════════════════════

BG       = "#1e1e2e"   # zemin
BG2      = "#181825"   # ikincil zemin
BG3      = "#313244"   # panel / kart
FG       = "#cdd6f4"   # ana yazı
FG2      = "#a6adc8"   # ikincil yazı
ACC      = "#89b4fa"   # vurgu mavi
ACC2     = "#cba6f7"   # vurgu mor
OK       = "#a6e3a1"   # yeşil / başarı
WRN      = "#f38ba8"   # kırmızı / uyarı
WARN2    = "#fab387"   # turuncu / uyarı2
SEL_BG   = "#45475a"   # seçim arka planı
BORDER   = "#6c7086"   # kenarlık

FONT_MONO = ("Consolas", 10)
FONT_UI   = ("Segoe UI", 10)
FONT_H1   = ("Segoe UI", 14, "bold")
FONT_H2   = ("Segoe UI", 11, "bold")
FONT_SMALL= ("Segoe UI", 9)


def _apply_theme(root: tk.Tk) -> None:
    style = ttk.Style(root)
    # clam en iyi özelleştirilebilir temel temadır
    style.theme_use("clam")

    style.configure(".",
        background=BG, foreground=FG,
        fieldbackground=BG3, selectbackground=SEL_BG,
        selectforeground=FG, font=FONT_UI,
        bordercolor=BORDER, darkcolor=BG2, lightcolor=BG3,
        troughcolor=BG2, arrowcolor=FG2,
    )
    style.configure("TFrame",  background=BG)
    style.configure("TLabel",  background=BG, foreground=FG)
    style.configure("Card.TFrame", background=BG3, relief="flat")

    style.configure("TNotebook",
        background=BG2, tabmargins=[2, 4, 0, 0],
    )
    style.configure("TNotebook.Tab",
        background=BG3, foreground=FG2, padding=[14, 6],
        font=FONT_UI,
    )
    style.map("TNotebook.Tab",
        background=[("selected", BG)],
        foreground=[("selected", ACC)],
    )

    style.configure("TButton",
        background=BG3, foreground=FG, padding=[10, 6],
        relief="flat", borderwidth=0,
    )
    style.map("TButton",
        background=[("active", SEL_BG), ("pressed", ACC)],
        foreground=[("active", FG)],
    )
    style.configure("Accent.TButton",
        background=ACC, foreground=BG, font=("Segoe UI", 10, "bold"),
        padding=[12, 7],
    )
    style.map("Accent.TButton",
        background=[("active", ACC2), ("pressed", BG3)],
    )
    style.configure("Danger.TButton",
        background=WRN, foreground=BG, font=("Segoe UI", 10, "bold"),
        padding=[10, 7],
    )
    style.map("Danger.TButton",
        background=[("active", "#eba0ac"), ("pressed", BG3)],
    )

    style.configure("TRadiobutton",
        background=BG, foreground=FG, font=FONT_UI,
        indicatorcolor=BG3, indicatorrelief="flat",
    )
    style.map("TRadiobutton",
        indicatorcolor=[("selected", ACC), ("active", ACC2)],
    )
    style.configure("TCheckbutton",
        background=BG, foreground=FG, font=FONT_UI,
        indicatorcolor=BG3,
    )
    style.map("TCheckbutton",
        indicatorcolor=[("selected", ACC), ("active", ACC2)],
    )
    style.configure("TCombobox",
        fieldbackground=BG3, selectbackground=SEL_BG, foreground=FG,
        background=BG3, arrowcolor=FG2,
    )
    style.map("TCombobox", fieldbackground=[("readonly", BG3)])
    style.configure("TEntry",
        fieldbackground=BG3, foreground=FG, insertcolor=FG,
    )
    style.configure("TScale", background=BG, troughcolor=BG3)
    style.configure("Horizontal.TSeparator", background=BORDER)
    style.configure("TScrollbar",
        background=BG3, troughcolor=BG2, arrowcolor=FG2,
        bordercolor=BG3,
    )
    root.configure(bg=BG)


# ═══════════════════════════════════════════════════════════════════════════════
# ANA PENCERE
# ═══════════════════════════════════════════════════════════════════════════════

class TradingGUI(tk.Tk):

    def __init__(self) -> None:
        super().__init__()
        self.cfg = get_config()
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None

        w = self.cfg.get("gui", "window_width",  default=1100)
        h = self.cfg.get("gui", "window_height", default=720)
        self.title("XAUUSD FVG Trading System  v10")
        self.geometry(f"{w}x{h}")
        self.minsize(900, 600)
        self.configure(bg=BG)

        _apply_theme(self)
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI İnşaatı ────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._build_header()
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.tab_bt  = BacktestTab(nb, self)
        self.tab_lt  = LiveTab(nb, self)
        self.tab_cfg = SettingsTab(nb, self)

        nb.add(self.tab_bt,  text="  📊  Backtest  ")
        nb.add(self.tab_lt,  text="  ⚡  Canlı Trader  ")
        nb.add(self.tab_cfg, text="  ⚙  Ayarlar  ")

        self._status_var = tk.StringVar(value="Hazır.")
        bar = tk.Label(self, textvariable=self._status_var,
                       bg=BG2, fg=FG2, font=FONT_SMALL,
                       anchor="w", padx=10, pady=4)
        bar.pack(side="bottom", fill="x")

    def _build_header(self) -> None:
        hdr = tk.Frame(self, bg=BG2, pady=10)
        hdr.pack(fill="x", padx=0)
        tk.Label(hdr, text="XAUUSD  FVG  Trading  System",
                 bg=BG2, fg=ACC, font=("Segoe UI", 15, "bold")).pack(side="left", padx=16)
        tk.Label(hdr, text="v10.0  │  Smart Money ICT",
                 bg=BG2, fg=FG2, font=FONT_SMALL).pack(side="left")
        tk.Label(hdr, text="Gold  (XAU/USD)",
                 bg=BG2, fg=WARN2, font=FONT_UI).pack(side="right", padx=16)

    # ── Durum çubuğu ──────────────────────────────────────────────────────────

    def set_status(self, msg: str, color: str = FG2) -> None:
        self._status_var.set(f"  {msg}")

    # ── Thread yönetimi ───────────────────────────────────────────────────────

    def run_task(self, fn, *args, on_done=None) -> None:
        if self._worker and self._worker.is_alive():
            self.set_status("⚠  Zaten çalışan bir görev var.", WRN)
            return
        self._stop_event.clear()
        def _wrapper():
            try:
                fn(*args)
            finally:
                if on_done:
                    self.after(0, on_done)
        self._worker = threading.Thread(target=_wrapper, daemon=True)
        self._worker.start()

    def stop_task(self) -> None:
        self._stop_event.set()
        self.set_status("Durduruluyor…")

    def _on_close(self) -> None:
        self._stop_event.set()
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
# BACKTEST SEKMESİ
# ═══════════════════════════════════════════════════════════════════════════════

class BacktestTab(ttk.Frame):

    def __init__(self, parent, app: TradingGUI) -> None:
        super().__init__(parent)
        self.app = app
        self.cfg = app.cfg

        # ── Değişkenler ──────────────────────────────────────────────────────
        self.v_strategy   = tk.StringVar(value="fvg")
        self.v_bias       = tk.StringVar(value=self.cfg.get("backtest","default_bias",default="weekly"))
        self.v_rr         = tk.StringVar(value="1:2 fix")
        self.v_tbe        = tk.StringVar(value="8h (96 bar)")
        self.v_emf        = tk.BooleanVar(value=False)
        self.v_wfa        = tk.BooleanVar(value=False)
        self.v_monte      = tk.BooleanVar(value=True)
        self.v_capital    = tk.StringVar(value=str(int(self.cfg.initial_capital)))
        self.v_risk_pct   = tk.DoubleVar(value=self.cfg.risk_fraction * 100)

        self._build()

    def _build(self) -> None:
        # Sol panel + sağ çıktı yan yana
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        left = ttk.Frame(self, style="Card.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(8,4), pady=8)
        left.configure(width=300)

        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=(4,8), pady=8)
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self._build_left(left)
        self._build_right(right)

    # ── Sol Kontrol Paneli ────────────────────────────────────────────────────

    def _build_left(self, f: ttk.Frame) -> None:
        pad = {"padx": 12, "pady": 3}

        # Strateji
        _section(f, "STRATEJİ")
        strategies = [
            ("FVG v10  (Ana Strateji)",      "fvg"),
            ("ThreeVol Directional",          "threevol"),
            ("Harmonik PRZ Only",             "prz"),
            ("London Reversal  (ICT)",        "london"),
            ("Tam Matrix  (A+C+G+H+W)",       "full"),
        ]
        for lbl, val in strategies:
            ttk.Radiobutton(f, text=lbl, variable=self.v_strategy, value=val,
                            command=self._on_strategy_change).pack(anchor="w", **pad)

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=6, padx=8)

        # Parametreler
        _section(f, "PARAMETRELER")
        _combo_row(f, "Bias:", self.v_bias,
                   ["weekly", "daily", "none", "private"], pad)
        _combo_row(f, "RR:", self.v_rr,
                   ["1:1", "1:2 BE@1R", "1:2 fix"], pad)
        self._tbe_row_frame = _combo_row(f, "TBE:", self.v_tbe,
                   ["Yok", "2h (24 bar)", "4h (48 bar)", "8h (96 bar)"], pad)

        ttk.Checkbutton(f, text="EMA-MACD Filtresi",
                        variable=self.v_emf).pack(anchor="w", **pad)
        ttk.Checkbutton(f, text="Walk-Forward Analizi",
                        variable=self.v_wfa).pack(anchor="w", **pad)
        ttk.Checkbutton(f, text="Monte Carlo (10k sim)",
                        variable=self.v_monte).pack(anchor="w", **pad)

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=6, padx=8)

        # Sermaye & Risk
        _section(f, "SERMAYE & RİSK")
        _entry_row(f, "Başlangıç ($):", self.v_capital, pad)

        risk_f = ttk.Frame(f)
        risk_f.pack(fill="x", **pad)
        tk.Label(risk_f, text="Risk %:", width=13, anchor="w",
                 bg=BG3, fg=FG2, font=FONT_UI).pack(side="left")
        self._risk_label = tk.Label(risk_f, text=f"{self.v_risk_pct.get():.2f}%",
                                    width=6, bg=BG3, fg=ACC, font=FONT_UI)
        self._risk_label.pack(side="right")
        s = ttk.Scale(f, orient="horizontal", from_=0.1, to=2.0,
                      variable=self.v_risk_pct,
                      command=lambda _: self._risk_label.config(
                          text=f"{self.v_risk_pct.get():.2f}%"))
        s.pack(fill="x", padx=12, pady=2)

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=6, padx=8)

        # Butonlar
        ttk.Button(f, text="▶  BACKTEST ÇALIŞTIR", style="Accent.TButton",
                   command=self._run).pack(fill="x", padx=12, pady=4)
        ttk.Button(f, text="■  Durdur",
                   command=self.app.stop_task).pack(fill="x", padx=12, pady=2)
        ttk.Button(f, text="⬇  Veriyi Güncelle",
                   command=self._download_data).pack(fill="x", padx=12, pady=2)

    # ── Sağ Çıktı Alanı ──────────────────────────────────────────────────────

    def _build_right(self, f: ttk.Frame) -> None:
        # Araç çubuğu
        tb = ttk.Frame(f)
        tb.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Button(tb, text="💾  Kaydet", command=self._save_output).pack(side="left", padx=2)
        ttk.Button(tb, text="🗑  Temizle", command=self._clear_output).pack(side="left", padx=2)
        self._progress_var = tk.StringVar(value="")
        tk.Label(tb, textvariable=self._progress_var,
                 bg=BG, fg=ACC, font=FONT_SMALL).pack(side="right", padx=8)

        # Konsol
        self._out = scrolledtext.ScrolledText(
            f, wrap="word", state="disabled",
            bg=BG2, fg=FG, font=FONT_MONO,
            insertbackground=FG, relief="flat",
            borderwidth=0, highlightthickness=1,
            highlightbackground=BORDER,
            selectbackground=SEL_BG,
        )
        self._out.grid(row=1, column=0, sticky="nsew")
        f.rowconfigure(1, weight=1)

        # Renk etiketleri
        self._out.tag_configure("ok",   foreground=OK)
        self._out.tag_configure("warn", foreground=WRN)
        self._out.tag_configure("acc",  foreground=ACC)
        self._out.tag_configure("hdr",  foreground=ACC2, font=(*FONT_MONO[:2], "bold"))
        self._out.tag_configure("dim",  foreground=FG2)

    # ── Event Handler'lar ────────────────────────────────────────────────────

    def _on_strategy_change(self) -> None:
        s = self.v_strategy.get()
        # London için TBE mantıklı değil
        if s == "london":
            self.v_tbe.set("Yok")
        elif s in ("fvg", "full"):
            self.v_tbe.set("8h (96 bar)")

    def _run(self) -> None:
        self.app.run_task(self._backtest_task,
                          on_done=lambda: self.app.set_status("Tamamlandı."))
        self.app.set_status("Çalışıyor…")

    def _backtest_task(self) -> None:
        strategy  = self.v_strategy.get()
        bias      = self.v_bias.get()
        rr_str    = self.v_rr.get()
        tbe_str   = self.v_tbe.get()
        emf       = self.v_emf.get()
        do_wfa    = self.v_wfa.get()
        capital   = _safe_float(self.v_capital.get(), 10_000)
        risk_frac = self.v_risk_pct.get() / 100.0

        rr_map = {"1:1": (1.0, None), "1:2 BE@1R": (2.0, 1.0), "1:2 fix": (2.0, None)}
        tbe_map = {"Yok": None, "2h (24 bar)": 24, "4h (48 bar)": 48, "8h (96 bar)": 96}
        rr, be  = rr_map.get(rr_str, (2.0, None))
        tbe     = tbe_map.get(tbe_str)

        self._log_clear()
        self._log(f"═══ BACKTEST  │  {strategy.upper()}  │  bias={bias}  │  RR={rr_str}  │  TBE={tbe_str} ═══\n",
                  tag="hdr")

        try:
            from xauusd_fvg_engine_v10 import (
                DataEngine, MarketBrain, RiskManager,
                BacktestEngine, PerformanceAnalytics,
                WeeklyBiasProvider, DailyBiasProvider,
                PrivateBiasProvider,
                ThreeVolBrain, LondonReversalBrain, LondonBacktestEngine,
                to_naive,
            )
        except ImportError as e:
            self._log(f"Import hatası: {e}\n", tag="warn")
            return

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            df_1h, df_5m, bt_start = DataEngine.download(verbose=False)
        self._log(f"Veri yüklendi  │  5M: {len(df_5m)} bar  │  1H: {len(df_1h)} bar\n", tag="dim")

        if self.app._stop_event.is_set():
            return

        def make_bias(mode):
            if mode == "none":    return None
            if mode == "daily":   return DailyBiasProvider(self.cfg.daily_bias_path)
            if mode == "private": return PrivateBiasProvider(df_1h)
            return WeeklyBiasProvider(self.cfg.weekly_bias_path)

        def run_one(bias_mode, _rr=rr, _be=be, _tbe=tbe, _emf=emf, poi="all"):
            bp = make_bias(bias_mode)
            brain = MarketBrain(bias_provider=bp, poi_mode=poi)
            risk  = RiskManager(rr=_rr, sl_buffer=self.cfg.sl_buffer)
            eng   = BacktestEngine(brain, risk,
                                   initial_capital=capital,
                                   breakeven_at_R=_be,
                                   time_exit_bars=_tbe,
                                   ema_macd_filter=_emf)
            buf2 = io.StringIO()
            with contextlib.redirect_stdout(buf2):
                trades = eng.run(df_1h, df_5m, bt_start)
            return trades, PerformanceAnalytics(trades, capital).compute()

        def run_london(bias_mode):
            bp    = make_bias(bias_mode)
            brain = LondonReversalBrain(bias_provider=bp)
            risk  = RiskManager(rr=2.0, sl_buffer=self.cfg.sl_buffer)
            eng   = LondonBacktestEngine(brain, risk,
                                         initial_capital=capital,
                                         breakeven_at_R=None)
            buf2 = io.StringIO()
            with contextlib.redirect_stdout(buf2):
                trades = eng.run(df_1h, df_5m, bt_start)
            return trades, PerformanceAnalytics(trades, capital).compute()

        BIASES = ["weekly", "daily", "none", "private"]

        # ── Tek strateji ────────────────────────────────────────────────────
        if strategy in ("fvg", "threevol", "prz"):
            poi_map = {"fvg": "all", "threevol": "threevol", "prz": "prz"}
            poi = poi_map[strategy]

            if self.app._stop_event.is_set(): return
            trades, m = run_one(bias, poi=poi)
            self._print_metrics(m, bias, rr_str, tbe_str)
            if self.v_monte.get() and m:
                pa = PerformanceAnalytics(trades, capital)
                mc = pa.monte_carlo()
                if mc:
                    self._log_mc(mc)

        elif strategy == "london":
            if self.app._stop_event.is_set(): return
            trades, m = run_london(bias)
            self._print_metrics(m, bias, "adaptive", "Yok")
            if self.v_monte.get() and m:
                pa = PerformanceAnalytics(trades, capital)
                mc = pa.monte_carlo()
                if mc:
                    self._log_mc(mc)

        # ── Tam Matrix ──────────────────────────────────────────────────────
        elif strategy == "full":
            for strat_name, poi in [("FVG v10","all"),("ThreeVol","threevol"),("PRZ","prz")]:
                if self.app._stop_event.is_set(): return
                self._log(f"\n── {strat_name} ──────────────────────────────────\n", tag="acc")
                self._log(f"  {'Bias':<10} {'İşl':>5} {'WR%':>7} {'PnL$':>11} {'Sharpe':>8} {'MaxDD%':>8}\n", tag="dim")
                for bm in BIASES:
                    if self.app._stop_event.is_set(): return
                    _, m = run_one(bm, poi=poi)
                    self._log_row(bm, m)

            self._log(f"\n── London Reversal ───────────────────────────────\n", tag="acc")
            self._log(f"  {'Bias':<10} {'İşl':>5} {'WR%':>7} {'PnL$':>11} {'Sharpe':>8} {'MaxDD%':>8}\n", tag="dim")
            for bm in BIASES:
                if self.app._stop_event.is_set(): return
                _, m = run_london(bm)
                self._log_row(bm, m)

            if do_wfa:
                self._run_wfa(df_1h, df_5m, bt_start, capital, run_one)

        if do_wfa and strategy != "full":
            self._run_wfa(df_1h, df_5m, bt_start, capital, run_one)

        self._log("\n✔  Backtest tamamlandı.\n", tag="ok")

    def _run_wfa(self, df_1h, df_5m, bt_start, capital, run_one_fn) -> None:
        from xauusd_fvg_engine_v10 import PerformanceAnalytics, to_naive
        import pandas as pd

        self._log("\n── Walk-Forward Analizi (IS:3ay → OOS:1ay) ──────────\n", tag="acc")
        bt_ts = to_naive(pd.Timestamp(bt_start, tz="UTC"))

        bias_list  = ["weekly", "daily", "none", "private"]
        rr_configs = [(1.0, None), (2.0, 1.0), (2.0, None)]
        in_m, out_m, n_win = 3, 1, 4

        def _filt(trades, s, e):
            return [t for t in trades
                    if s <= to_naive(t.signal.entry_time) < e]

        cum_pnl = 0.0
        for w in range(n_win):
            if self.app._stop_event.is_set(): return
            is_s  = bt_ts + pd.DateOffset(months=w * out_m)
            is_e  = bt_ts + pd.DateOffset(months=w * out_m + in_m)
            oos_e = bt_ts + pd.DateOffset(months=w * out_m + in_m + out_m)
            if oos_e > to_naive(df_5m.index[-1]):
                break

            best_score, best_cfg = -1e9, None
            for bm in bias_list:
                for (_rr, _be) in rr_configs:
                    if self.app._stop_event.is_set(): return
                    try:
                        all_tr, _ = run_one_fn(bm, _rr=_rr, _be=_be, _tbe=None, _emf=False)
                        is_tr = _filt(all_tr, is_s, is_e)
                        if len(is_tr) < 3: continue
                        m = PerformanceAnalytics(is_tr, capital).compute()
                        if m is None: continue
                        score = m["sharpe"] * (1.0 - m["max_dd"] / 100.0)
                        if score > best_score:
                            best_score, best_cfg = score, (bm, _rr, _be)
                    except Exception:
                        continue
            if best_cfg is None:
                continue
            bm, _rr, _be = best_cfg
            cfg_lbl = f"{bm}/{_rr:.0f}:{'BE' if _be else 'fix'}"
            try:
                oos_all, _ = run_one_fn(bm, _rr=_rr, _be=_be, _tbe=None, _emf=False)
                oos_tr = _filt(oos_all, is_e, oos_e)
                m_oos  = PerformanceAnalytics(oos_tr, capital).compute() if oos_tr else None
            except Exception:
                m_oos = None

            is_lbl  = f"{is_s.strftime('%Y-%m')}→{is_e.strftime('%Y-%m')}"
            oos_lbl = f"{is_e.strftime('%Y-%m')}→{oos_e.strftime('%Y-%m')}"
            if m_oos and m_oos["total"] > 0:
                cum_pnl += m_oos["net_pnl"]
                wr_pct = m_oos["win_rate"] * 100
                self._log(
                    f"  Pencere {w+1}  IS:{is_lbl}  OOS:{oos_lbl}  "
                    f"cfg={cfg_lbl:<16} işl={m_oos['total']:>3}  "
                    f"WR={wr_pct:.1f}%  PnL={m_oos['net_pnl']:>+9.2f}\n"
                )
            else:
                self._log(f"  Pencere {w+1}  OOS:{oos_lbl}  cfg={cfg_lbl}  işlem yok\n", tag="dim")

        self._log(f"  OOS Kümülatif PnL: ${cum_pnl:>+9.2f}\n", tag="ok")

    # ── Metrik yazdırma ───────────────────────────────────────────────────────

    def _print_metrics(self, m, bias, rr_str, tbe_str) -> None:
        if m is None or m["total"] == 0:
            self._log("  → İşlem bulunamadı.\n", tag="warn")
            return
        wr = m["win_rate"] * 100
        tag = "ok" if m["net_pnl"] > 0 else "warn"
        self._log(f"\n  Bias={bias}  │  RR={rr_str}  │  TBE={tbe_str}\n", tag="acc")
        self._log(f"  İşlem : {m['total']}  │  Win: {m['wins']}  │  Loss: {m['losses']}\n")
        self._log(f"  WR    : {wr:.1f}%\n")
        self._log(f"  NetPnL: ${m['net_pnl']:>+10.2f}\n", tag=tag)
        self._log(f"  Getiri: %{m['ret_pct']:>+.2f}\n")
        self._log(f"  Sharpe: {m['sharpe']:.3f}  │  MaxDD: {m['max_dd']:.2f}%  │  PF: {m['profit_factor']:.2f}\n")

    def _log_mc(self, mc: dict) -> None:
        self._log(f"\n  Monte Carlo ({mc['n_sim']:,} sim │ {mc['n_trades']} işlem)\n", tag="acc")
        self._log(f"  Medyan MaxDD: %{mc['p50_maxdd']:.2f}  │  P95: %{mc['p95_maxdd']:.2f}"
                  f"  │  P99: %{mc['p99_maxdd']:.2f}\n")
        ruin_tag = "warn" if mc["ruin_pct"] > 5 else "dim"
        self._log(f"  Çöküş ihtimali: %{mc['ruin_pct']:.1f}\n", tag=ruin_tag)

    def _log_row(self, bias: str, m) -> None:
        if m is None or m["total"] == 0:
            self._log(f"  {bias:<10} {'—':>5}\n", tag="dim")
            return
        wr = m["win_rate"] * 100
        tag = "ok" if m["net_pnl"] > 0 else "warn"
        self._log(f"  {bias:<10} {m['total']:>5} {wr:>6.1f}% "
                  f"{m['net_pnl']:>+11.2f} {m['sharpe']:>8.2f} {m['max_dd']:>8.2f}%\n",
                  tag=tag)

    # ── Konsol işlemleri ──────────────────────────────────────────────────────

    def _log(self, text: str, tag: str = "") -> None:
        def _do():
            self._out.configure(state="normal")
            if tag:
                self._out.insert("end", text, tag)
            else:
                self._out.insert("end", text)
            self._out.see("end")
            self._out.configure(state="disabled")
        self.app.after(0, _do)

    def _log_clear(self) -> None:
        def _do():
            self._out.configure(state="normal")
            self._out.delete("1.0", "end")
            self._out.configure(state="disabled")
        self.app.after(0, _do)

    def _clear_output(self) -> None:
        self._log_clear()

    def _save_output(self) -> None:
        content = self._out.get("1.0", "end")
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files","*.txt"),("All files","*.*")],
            initialfile="backtest_sonuc.txt",
        )
        if path:
            Path(path).write_text(content, encoding="utf-8")
            self.app.set_status(f"Kaydedildi: {path}")

    def _download_data(self) -> None:
        def task():
            self._log("Veri indiriliyor…\n", tag="acc")
            try:
                result = subprocess.run(
                    [sys.executable, str(ROOT / "download_data.py"), "--yahoo-1h"],
                    capture_output=True, text=True, cwd=str(ROOT),
                )
                self._log(result.stdout or "Tamamlandı.\n", tag="ok")
                if result.returncode != 0:
                    self._log(result.stderr, tag="warn")
            except Exception as e:
                self._log(f"Hata: {e}\n", tag="warn")
        self.app.run_task(task)


# ═══════════════════════════════════════════════════════════════════════════════
# CANLI TRADER SEKMESİ
# ═══════════════════════════════════════════════════════════════════════════════

class LiveTab(ttk.Frame):

    def __init__(self, parent, app: TradingGUI) -> None:
        super().__init__(parent)
        self.app = app
        self.cfg = app.cfg

        self.v_bias    = tk.StringVar(value="weekly")
        self.v_dry     = tk.BooleanVar(value=True)
        self.v_lev     = tk.StringVar(value=str(self.cfg.get("live","leverage",default=10)))
        self.v_risk    = tk.StringVar(value=str(self.cfg.get("live","risk_pct",default=1.0)))
        self.v_symbol  = tk.StringVar(value=self.cfg.get("live","symbol",default="NCCGOLD2USD-USDT"))
        self._proc: Optional[subprocess.Popen] = None

        self._build()

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        left = ttk.Frame(self, style="Card.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(8,4), pady=8)

        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=(4,8), pady=8)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        self._build_left(left)
        self._build_right(right)

    def _build_left(self, f: ttk.Frame) -> None:
        pad = {"padx": 12, "pady": 4}
        _section(f, "CANLI TRADER AYARLARI")

        _combo_row(f, "Bias:", self.v_bias, ["weekly","daily","none"], pad)
        _entry_row(f, "Kaldıraç:", self.v_lev, pad)
        _entry_row(f, "Risk %:", self.v_risk, pad)
        _entry_row(f, "Sembol:", self.v_symbol, pad)
        ttk.Checkbutton(f, text="Kağıt Trade (Dry-Run)",
                        variable=self.v_dry).pack(anchor="w", **pad)

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=8, padx=8)

        ttk.Button(f, text="▶  Trader'ı Başlat", style="Accent.TButton",
                   command=self._start).pack(fill="x", padx=12, pady=4)
        ttk.Button(f, text="■  Durdur",
                   command=self._stop).pack(fill="x", padx=12, pady=2)
        ttk.Button(f, text="⚠  Tüm Pozisyonları Kapat", style="Danger.TButton",
                   command=self._close_all).pack(fill="x", padx=12, pady=4)

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=8, padx=8)

        info = (
            "BingX API anahtarları\n"
            "live_config.json içinde\n"
            "saklanmalıdır.\n\n"
            "Kağıt trade modunda\n"
            "gerçek emir açılmaz."
        )
        tk.Label(f, text=info, bg=BG3, fg=FG2, font=FONT_SMALL,
                 justify="left", wraplength=220).pack(padx=12, pady=4, anchor="w")

    def _build_right(self, f: ttk.Frame) -> None:
        tk.Label(f, text="Canlı Trader Logu", bg=BG, fg=ACC,
                 font=FONT_H2).grid(row=0, column=0, sticky="w", pady=(4,2))
        self._log_box = scrolledtext.ScrolledText(
            f, wrap="word", state="disabled",
            bg=BG2, fg=FG, font=FONT_MONO,
            relief="flat", borderwidth=0,
            highlightthickness=1, highlightbackground=BORDER,
        )
        self._log_box.grid(row=1, column=0, sticky="nsew")
        self._log_box.tag_configure("ok",  foreground=OK)
        self._log_box.tag_configure("err", foreground=WRN)

    def _log(self, text: str, tag: str = "") -> None:
        def _do():
            self._log_box.configure(state="normal")
            self._log_box.insert("end", text, tag)
            self._log_box.see("end")
            self._log_box.configure(state="disabled")
        self.app.after(0, _do)

    def _start(self) -> None:
        if self._proc and self._proc.poll() is None:
            messagebox.showwarning("Uyarı", "Trader zaten çalışıyor!")
            return
        args = [
            sys.executable, str(ROOT / "xauusd_live_trader.py"),
            "--bias", self.v_bias.get(),
            "--leverage", self.v_lev.get(),
            "--risk-pct", self.v_risk.get(),
            "--symbol", self.v_symbol.get(),
        ]
        if self.v_dry.get():
            args.append("--dry-run")
        try:
            self._proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=str(ROOT), bufsize=1,
            )
            self._log("Trader başlatıldı…\n", tag="ok")
            threading.Thread(target=self._stream_log, daemon=True).start()
        except Exception as e:
            self._log(f"Başlatma hatası: {e}\n", tag="err")

    def _stream_log(self) -> None:
        for line in iter(self._proc.stdout.readline, ""):
            self._log(line)
        self._log("\n[Trader durdu]\n", tag="err")

    def _stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._log("Trader durduruldu.\n", tag="err")

    def _close_all(self) -> None:
        if not messagebox.askyesno("Onay", "Tüm açık pozisyonlar kapatılacak. Emin misiniz?"):
            return
        try:
            subprocess.run(
                [sys.executable, str(ROOT / "xauusd_live_trader.py"), "--close"],
                cwd=str(ROOT),
            )
            self._log("Tüm pozisyonlar kapatıldı.\n", tag="ok")
        except Exception as e:
            self._log(f"Hata: {e}\n", tag="err")


# ═══════════════════════════════════════════════════════════════════════════════
# AYARLAR SEKMESİ
# ═══════════════════════════════════════════════════════════════════════════════

class SettingsTab(ttk.Frame):

    def __init__(self, parent, app: TradingGUI) -> None:
        super().__init__(parent)
        self.app = app
        self.cfg = app.cfg
        self._vars: dict[str, tk.StringVar] = {}
        self._build()

    def _build(self) -> None:
        canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))

        pad = {"padx": 16, "pady": 4}

        sections = [
            ("backtest", "BACKTEST", [
                ("initial_capital",  "Başlangıç Sermayesi ($)"),
                ("default_rr",       "Varsayılan RR"),
                ("default_tbe_bars", "Varsayılan TBE (bar)"),
                ("warmup_days",      "Isınma Günleri"),
            ]),
            ("risk", "RİSK YÖNETİMİ", [
                ("risk_fraction",   "Risk Fraksiyonu (ör: 0.005 = 0.5%)"),
                ("sl_buffer",       "SL Buffer"),
                ("min_risk_dollar", "Min Risk $"),
                ("max_risk_dollar", "Max Risk $"),
            ]),
            ("private_bias", "PRİVATE BIAS (EWMA/EMA)", [
                ("vol_lambda", "EWMA Lambda (λ)"),
                ("vol_mult",   "Volatilite Çarpanı"),
                ("ema_fast",   "Hızlı EMA Periyodu"),
                ("ema_slow",   "Yavaş EMA Periyodu"),
            ]),
            ("live", "CANLI TRADER", [
                ("leverage",    "Kaldıraç"),
                ("risk_pct",    "Risk % / işlem"),
                ("tbe_minutes", "TBE (dakika)"),
                ("symbol",      "BingX Sembol"),
            ]),
            ("paths", "DOSYA YOLLARI", [
                ("csv_5m",      "5M CSV Dosyası"),
                ("csv_1h",      "1H CSV Dosyası"),
                ("weekly_bias", "Weekly Bias JSON"),
                ("daily_bias",  "Daily Bias JSON"),
            ]),
        ]

        for section_key, section_lbl, fields in sections:
            _section(inner, section_lbl)
            for field_key, field_lbl in fields:
                var_key = f"{section_key}.{field_key}"
                val = self.cfg.get(section_key, field_key, default="")
                var = tk.StringVar(value=str(val))
                self._vars[var_key] = var
                row = ttk.Frame(inner)
                row.pack(fill="x", **pad)
                tk.Label(row, text=field_lbl + ":", width=34, anchor="w",
                         bg=BG, fg=FG2, font=FONT_SMALL).pack(side="left")
                ttk.Entry(row, textvariable=var, width=28).pack(side="left")
            ttk.Separator(inner, orient="horizontal").pack(fill="x", padx=16, pady=6)

        btn_row = ttk.Frame(inner)
        btn_row.pack(fill="x", padx=16, pady=8)
        ttk.Button(btn_row, text="💾  Kaydet ve Uygula", style="Accent.TButton",
                   command=self._save).pack(side="left", padx=4)
        ttk.Button(btn_row, text="↺  Varsayılanlara Dön",
                   command=self._reset).pack(side="left", padx=4)
        ttk.Button(btn_row, text="📂  JSON'ı Düzenleyicide Aç",
                   command=self._open_json).pack(side="right", padx=4)

    def _save(self) -> None:
        for var_key, var in self._vars.items():
            section, field = var_key.split(".", 1)
            raw = var.get().strip()
            # int / float dönüşümü
            try:
                val: Any = int(raw)
            except ValueError:
                try:
                    val = float(raw)
                except ValueError:
                    val = raw
            self.cfg.set(section, field, val)
        self.cfg.save()
        self.app.set_status("Ayarlar kaydedildi.")
        messagebox.showinfo("Kaydedildi", "Ayarlar config/default.json'a yazıldı.")

    def _reset(self) -> None:
        from config import _BUILTIN_DEFAULTS, _deep_copy
        self.cfg._data = _deep_copy(_BUILTIN_DEFAULTS)
        self.cfg.save()
        # Alanları güncelle
        for var_key, var in self._vars.items():
            section, field = var_key.split(".", 1)
            var.set(str(self.cfg.get(section, field, default="")))
        self.app.set_status("Varsayılanlara döndürüldü.")

    def _open_json(self) -> None:
        path = str(ROOT / "config" / "default.json")
        try:
            os.startfile(path)
        except AttributeError:
            subprocess.Popen(["xdg-open", path])


# ═══════════════════════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR
# ═══════════════════════════════════════════════════════════════════════════════

def _section(parent: tk.Widget, title: str) -> None:
    tk.Label(parent, text=title, bg=parent.cget("bg"),
             fg=ACC, font=FONT_H2).pack(anchor="w", padx=12, pady=(10, 2))


def _combo_row(parent: tk.Widget, label: str, var: tk.StringVar,
               values: list, pad: dict) -> ttk.Frame:
    row = ttk.Frame(parent)
    row.pack(fill="x", **pad)
    tk.Label(row, text=label, width=13, anchor="w",
             bg=row.cget("bg"), fg=FG2, font=FONT_UI).pack(side="left")
    cb = ttk.Combobox(row, textvariable=var, values=values,
                      state="readonly", width=18)
    cb.pack(side="left")
    return row


def _entry_row(parent: tk.Widget, label: str, var: tk.StringVar,
               pad: dict) -> None:
    row = ttk.Frame(parent)
    row.pack(fill="x", **pad)
    tk.Label(row, text=label, width=13, anchor="w",
             bg=row.cget("bg"), fg=FG2, font=FONT_UI).pack(side="left")
    ttk.Entry(row, textvariable=var, width=18).pack(side="left")


def _safe_float(s: str, default: float) -> float:
    try:
        return float(s.replace(",", "").replace("$", "").strip())
    except ValueError:
        return default


# ═══════════════════════════════════════════════════════════════════════════════
# GİRİŞ NOKTASI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = TradingGUI()
    app.mainloop()
