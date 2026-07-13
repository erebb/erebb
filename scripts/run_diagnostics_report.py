# -*- coding: utf-8 -*-
"""
Teşhis Backtest Raporu — kurumsal metrik seti (kendi bilgisayarında çalıştır)
=============================================================================
Dört stratejinin SABİT preset'lerini (GUI paritesi: gerçek BingX maliyetleri,
%1 uniform risk, threevol rejim kapısı, limit girişler, swing stoplar) koşar
ve ÖNCEKİ raporun metriklerinin (aylık/saatlik PnL, volatilite, equity) yanına
şu teşhisleri ekler:

  1. Rejim & bağlam (giriş anı): ATR14, Bollinger bant genişliği (BBW),
     Long/Short asimetri kırılımı, HTF (1H/4H) trend uyumu, 4H RSI,
     PDH/PDL/haftalık açılış yakınlık skoru, strateji kesişim (confluence) matrisi.
  2. Zaman & sermaye maliyeti: kazanan/kaybeden işlem süreleri, zaman-stopu
     what-if tablosu, drawdown SÜRESİ (underwater günler), haftanın günü dağılımı
     (+ Cuma öğleden sonra alt-kümesi).
  3. Emir uygulama: doluş oranı, doluşa-kadar-bar (time-to-fill), kaçan limit
     emirlerin FIRSAT MALİYETİ (gölge simülasyon), near-miss mesafeleri,
     W (limit penceresi) taraması, London gölge-limit near-miss raporu,
     London zaman-toleransı (killzone ±30 dk) ve katılık (strictness) matrisi.

Çıktılar (reports/diagnostics/):
  rapor_diagnostik.html   — UTF-8 Türkçe rapor, grafikler gömülü (tek dosya)
  ledger_diagnostik.csv   — işlem başına TÜM teşhis alanları (canlı slippage
                            karşılaştırması için entry/exit/qty/maliyet alanları)

Kullanım:
  python3 scripts/run_diagnostics_report.py            # tam (matrisler dahil)
  python3 scripts/run_diagnostics_report.py --fast     # matris taramalarını atla

Not: 5 yıllık veride tam koşu ~1-1.5 saat sürebilir (≈20 backtest koşusu);
--fast yalnız 4 temel koşuyla ~15-20 dk'da biter. Bütün gölge simülasyonlar
YALNIZ RAPOR içindir — işlem mantığını değiştirmez.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import io
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

OUT_DIR = ROOT / "reports" / "diagnostics"

STRATS = ["fvg", "threevol", "london", "qwe"]
RR_PRESET = {"fvg": (2.0, None), "threevol": (2.0, 1.0),
             "london": (2.0, None), "qwe": (2.0, None)}
DOW_TR = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


# ═══════════════════════════════ yardımcılar ═══════════════════════════════

def fig_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def img(fig, alt="grafik") -> str:
    return f'<img src="data:image/png;base64,{fig_b64(fig)}" alt="{alt}">'


def tbl(headers, rows, note: str = "") -> str:
    h = "".join(f"<th>{x}</th>" for x in headers)
    b = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>"
                for r in rows)
    n = f'<p class="note">{note}</p>' if note else ""
    return (f'<div class="twrap"><table><thead><tr>{h}</tr></thead>'
            f"<tbody>{b}</tbody></table></div>{n}")


def f2(x): return f"{x:+.2f}" if isinstance(x, (int, float)) else x
def f0(x): return f"{x:+.0f}" if isinstance(x, (int, float)) else x
def pc(x): return f"{x:.1f}%"


def perf(pnls: list) -> dict:
    """Basit performans özeti (PnL listesi $)."""
    n = len(pnls)
    if n == 0:
        return dict(n=0, wr=0.0, pnl=0.0, pf=0.0, avg=0.0)
    w = [p for p in pnls if p > 0]
    l = [p for p in pnls if p <= 0]
    gw, gl = sum(w), abs(sum(l))
    return dict(n=n, wr=len(w) / n * 100, pnl=sum(pnls),
                pf=(gw / gl if gl > 0 else float("inf")), avg=sum(pnls) / n)


def perf_row(label, d):
    pf = "∞" if d["pf"] == float("inf") else f"{d['pf']:.2f}"
    return [label, d["n"], pc(d["wr"]), f2(d["pnl"]), pf, f2(d["avg"])]


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


# ═════════════════════ bağlam dizileri (hepsi CAUSAL) ═══════════════════════

def build_context(df_5m: pd.DataFrame, df_1h: pd.DataFrame) -> dict:
    """Giriş anında BİLİNEN göstergeler. Lookup'lar 'bilinme anı' indeksiyle
    kurulur (bar değeri ancak bar KAPANDIKTAN sonra bilinir) → sinyal barında
    asof() ile bakmak lookahead içermez."""
    ctx = {}

    # 5M ATR14 & Bollinger(20) — sinyal barının kendisi kapanışta bilinir
    c5, h5, l5 = df_5m["Close"], df_5m["High"], df_5m["Low"]
    tr = pd.concat([h5 - l5, (h5 - c5.shift(1)).abs(),
                    (l5 - c5.shift(1)).abs()], axis=1).max(axis=1)
    ctx["atr14_5m"] = tr.rolling(14).mean()
    ma, sd = c5.rolling(20).mean(), c5.rolling(20).std()
    bbw = (4 * sd / ma * 100)                     # bant genişliği, fiyatın %'si
    ctx["bbw_5m"] = bbw
    ctx["bbw_ratio"] = bbw / bbw.rolling(288 * 30, min_periods=288 * 5).median()

    # 1H ATR14 + EMA21/55 trendi — 1H barı kapanınca bilinir → indeks +1h
    c1, h1, l1 = df_1h["Close"], df_1h["High"], df_1h["Low"]
    tr1 = pd.concat([h1 - l1, (h1 - c1.shift(1)).abs(),
                     (l1 - c1.shift(1)).abs()], axis=1).max(axis=1)
    ctx["atr14_1h"] = pd.Series(tr1.rolling(14).mean().values,
                                index=df_1h.index + pd.Timedelta(hours=1))
    e21 = c1.ewm(span=21, adjust=False).mean()
    e55 = c1.ewm(span=55, adjust=False).mean()
    ctx["trend_1h"] = pd.Series(np.where(e21.values > e55.values, "bull", "bear"),
                                index=df_1h.index + pd.Timedelta(hours=1))

    # 4H trend (EMA20/50) + RSI14 — 4H barı kapanınca bilinir → indeks +4h
    df4 = df_1h.resample("4h", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
    ).dropna(subset=["Close"])
    c4 = df4["Close"]
    e20 = c4.ewm(span=20, adjust=False).mean()
    e50 = c4.ewm(span=50, adjust=False).mean()
    idx4 = df4.index + pd.Timedelta(hours=4)
    ctx["trend_4h"] = pd.Series(np.where(e20.values > e50.values, "bull", "bear"),
                                index=idx4)
    ctx["rsi_4h"] = pd.Series(rsi_wilder(c4).values, index=idx4)

    # PDH / PDL — önceki TAMAMLANMIŞ günün H/L; gün bitince bilinir → +1 gün
    daily = df_5m.resample("1D").agg({"High": "max", "Low": "min"}).dropna()
    ctx["pdh"] = pd.Series(daily["High"].values, index=daily.index + pd.Timedelta(days=1))
    ctx["pdl"] = pd.Series(daily["Low"].values, index=daily.index + pd.Timedelta(days=1))

    # Haftalık açılış — haftanın İLK barının açılışı (hafta içinde causal)
    wk_start = df_5m.index.normalize() - pd.to_timedelta(
        df_5m.index.weekday, unit="D")
    wopen = df_5m["Open"].groupby(wk_start).first()
    ctx["wopen"] = wopen  # lookup: aynı formülle hafta anahtarı üret

    return ctx


def ctx_at(series: pd.Series, ts) -> float:
    v = series.asof(ts)
    return float(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else float("nan")


# ═══════════════════════ işlem defteri zenginleştirme ═══════════════════════

def est_cost(strat: str, t, limit_mode: bool, costs: dict) -> float:
    """Motorun _trade_cost formülünün kopyası (raporlama; ledger'a yazılır)."""
    if t.risk <= 0 or t.risk_dollar <= 0:
        return 0.0
    qty = t.risk_dollar / t.risk
    ex = t.exit_price if t.exit_price else t.entry_price
    if limit_mode:
        return (costs["maker_pct"] / 100 * qty * t.entry_price
                + costs["commission_pct"] / 100 * qty * ex
                + qty * costs["slippage_usd"])
    return (qty * (costs["spread_usd"] + 2 * costs["slippage_usd"])
            + costs["commission_pct"] / 100 * qty * (t.entry_price + ex))


def build_ledger(rows: list, ctx: dict, costs: dict,
                 limit_strats: set) -> pd.DataFrame:
    from xauusd_fvg_engine_v10 import to_naive
    recs = []
    for r in rows:
        strat = r["strategy"]
        for t in r.get("_trades", []):
            ts = to_naive(t.signal.entry_time)
            ex_ts = to_naive(t.exit_time) if t.exit_time is not None else None
            dur_h = ((ex_ts - ts).total_seconds() / 3600.0
                     if ex_ts is not None else np.nan)
            d = t.signal.direction
            price = t.entry_price
            pdh = ctx_at(ctx["pdh"], ts)
            pdl = ctx_at(ctx["pdl"], ts)
            wk = ts.normalize() - pd.Timedelta(days=ts.weekday())
            wo = float(ctx["wopen"].get(wk, np.nan))
            atr5 = ctx_at(ctx["atr14_5m"], ts)
            dists = [abs(price - x) for x in (pdh, pdl, wo) if not np.isnan(x)]
            near_atr = (min(dists) / atr5 if dists and atr5 > 0 else np.nan)
            t1 = ctx_at_str(ctx["trend_1h"], ts)
            t4 = ctx_at_str(ctx["trend_4h"], ts)
            recs.append(dict(
                strategy=strat, entry_ts=ts, exit_ts=ex_ts, direction=d,
                entry=price, exit=t.exit_price, stop_dist=t.risk,
                risk_dollar=t.risk_dollar,
                qty=round(t.risk_dollar / t.risk, 4) if t.risk > 0 else 0.0,
                pnl=t.pnl_dollar,
                pnl_r=(t.pnl_dollar / t.risk_dollar if t.risk_dollar > 0 else 0.0),
                result=t.result, exit_reason=getattr(t, "exit_reason", ""),
                mfe_r=getattr(t, "mfe_r", np.nan),
                mae_r=getattr(t, "mae_r", np.nan),
                dur_h=dur_h, dow=ts.weekday(), hour=ts.hour,
                atr14_5m=atr5, atr14_1h=ctx_at(ctx["atr14_1h"], ts),
                bbw_5m=ctx_at(ctx["bbw_5m"], ts),
                bbw_ratio=ctx_at(ctx["bbw_ratio"], ts),
                trend_1h=t1, trend_4h=t4,
                rsi_4h=ctx_at(ctx["rsi_4h"], ts),
                htf1h_align=(d == t1), htf4h_align=(d == t4),
                dist_pdh_pct=((price - pdh) / price * 100 if not np.isnan(pdh) else np.nan),
                dist_pdl_pct=((price - pdl) / price * 100 if not np.isnan(pdl) else np.nan),
                dist_wopen_pct=((price - wo) / price * 100 if not np.isnan(wo) else np.nan),
                near_level_atr=near_atr,
                est_cost=round(est_cost(strat, t, strat in limit_strats, costs), 2),
                assumed_slip_usd=(0.0 if strat in limit_strats
                                  else costs["slippage_usd"]),
            ))
    led = pd.DataFrame(recs).sort_values("entry_ts").reset_index(drop=True)

    # Kesişim (confluence): ±3 bar (15 dk) içinde başka stratejinin sinyali
    ts_arr = led["entry_ts"].values.astype("datetime64[ns]").astype(np.int64)
    tol = int(15 * 60 * 1e9)
    confl_n, confl_with, confl_same = [], [], []
    for i in range(len(led)):
        lo = np.searchsorted(ts_arr, ts_arr[i] - tol, side="left")
        hi = np.searchsorted(ts_arr, ts_arr[i] + tol, side="right")
        others = led.iloc[lo:hi]
        others = others[(others.index != i)
                        & (others["strategy"] != led.at[i, "strategy"])]
        confl_n.append(len(others))
        confl_with.append("+".join(sorted(set(others["strategy"]))))
        confl_same.append(bool((others["direction"]
                                == led.at[i, "direction"]).any()))
    led["confl_n"] = confl_n
    led["confl_with"] = confl_with
    led["confl_same_dir"] = confl_same
    return led


def ctx_at_str(series: pd.Series, ts) -> str:
    v = series.asof(ts)
    return str(v) if isinstance(v, str) else ""


# ═══════════════════════════ gölge simülatörü ═══════════════════════════════

class Shadow:
    """Kaçan limit emirleri / zaman-stopu what-if için fiyat yürüyüşü.
    Kötümser kural: aynı barda SL ve TP ikisi de değerse SL sayılır.
    YALNIZ RAPOR amaçlıdır (kısmi TP / swing-stop güncellemeleri yaklaşıktır)."""

    def __init__(self, df_5m: pd.DataFrame):
        self.T = df_5m.index.values.astype("datetime64[ns]").astype(np.int64)
        self.H = df_5m["High"].to_numpy(float)
        self.L = df_5m["Low"].to_numpy(float)
        self.C = df_5m["Close"].to_numpy(float)

    def pos_after(self, ts) -> int:
        return int(np.searchsorted(self.T, np.datetime64(ts).astype("datetime64[ns]").astype(np.int64), side="right"))

    def idx_of(self, ts) -> int:
        """ts zaman damgasına AİT bar indeksi (yoksa en yakın önceki)."""
        return self.pos_after(ts) - 1

    def close_at(self, ts) -> float:
        p = self.idx_of(ts)
        return float(self.C[p]) if 0 <= p < len(self.C) else float("nan")

    def scan_limit(self, sig_idx: int, direction: str, limit: float,
                   W: int) -> dict:
        """Limit emir yaşam döngüsünü 5M veriden yeniden kur (motor mantığının
        kopyası): sinyal barı sig_idx'te limit konur, sig_idx+1..sig_idx+W
        barlarında dolum aranır. Dönen: filled(bool), fill_bars, min_dist."""
        end = min(sig_idx + W, len(self.T) - 1)
        min_dist = float("inf")
        for i in range(sig_idx + 1, end + 1):
            if direction == "bull":
                gap = self.L[i] - limit
                touched = self.L[i] <= limit
            else:
                gap = limit - self.H[i]
                touched = self.H[i] >= limit
            min_dist = min(min_dist, max(gap, 0.0))
            if touched:
                return dict(filled=True, fill_bars=i - sig_idx, min_dist=0.0)
        return dict(filled=False, fill_bars=None,
                    min_dist=(min_dist if min_dist != float("inf") else np.nan))

    def run(self, ts, direction: str, entry: float, stop: float, tp: float,
            be_at_r: float | None = None, max_bars: int = 288 * 90) -> dict:
        """Sinyal barından SONRAKİ bardan itibaren yürür. Dönen: outcome
        ('tp'|'sl'|'be'|'open'), r (R cinsi sonuç), bars."""
        risk = abs(entry - stop)
        if risk <= 0:
            return dict(outcome="open", r=0.0, bars=0)
        sgn = 1.0 if direction == "bull" else -1.0
        be_armed = False
        be_trig = entry + sgn * risk * (be_at_r or 0.0)
        start = self.pos_after(ts)
        end = min(start + max_bars, len(self.T))
        cur_stop = stop
        for i in range(start, end):
            hi, lo = self.H[i], self.L[i]
            if be_at_r and not be_armed:
                if (direction == "bull" and hi >= be_trig) or \
                   (direction == "bear" and lo <= be_trig):
                    be_armed = True
                    cur_stop = entry
            hit_sl = lo <= cur_stop if direction == "bull" else hi >= cur_stop
            hit_tp = hi >= tp if direction == "bull" else lo <= tp
            if hit_sl:                                # kötümser: SL öncelikli
                r = 0.0 if (be_armed and cur_stop == entry) \
                    else -abs(entry - cur_stop) / risk
                return dict(outcome=("be" if r == 0.0 else "sl"),
                            r=r, bars=i - start + 1)
            if hit_tp:
                return dict(outcome="tp", r=abs(tp - entry) / risk,
                            bars=i - start + 1)
        return dict(outcome="open",
                    r=sgn * (self.C[end - 1] - entry) / risk if end > start else 0.0,
                    bars=end - start)


# ═══════════════ market-mod sinyal toplama (motora dokunmadan) ══════════════

def collect_signals(strat: str, cfg, capital: float, shadow: Shadow,
                    spread: float) -> list:
    """Stratejiyi MARKET modda koşar (config entry_order geçici 'market') ve
    HER sinyali döndürür. Limit emir yaşam döngüsü, motor enstrümantasyonu
    OLMADAN, sinyal barının kapanışından limit fiyatı (close∓spread) üretilip
    5M veride ileri taranarak yeniden kurulur (motorla aynı kural). market_pnl
    = o sinyal MARKET girilseydi motorun ürettiği gerçek sonuç → dolmayan
    limitlerin fırsat maliyeti budur."""
    from gui import _run_strategy
    from xauusd_fvg_engine_v10 import to_naive
    orig = cfg.get(strat, "entry_order", default="market")
    if orig == "limit":
        cfg.set(strat, "entry_order", "market")
    try:
        rr = _run_strategy(strat, capital=capital, keep_trades=True)[0]
    finally:
        if orig == "limit":
            cfg.set(strat, "entry_order", orig)
    sigs = []
    for t in rr.get("_trades", []):
        ent_ts = to_naive(t.signal.entry_time)
        sig_idx = shadow.idx_of(ent_ts) - 1          # entry = O[idx+1] → sinyal idx
        if sig_idx < 0:
            continue
        sig_close = float(shadow.C[sig_idx])
        d = t.signal.direction
        limit = round(sig_close - spread if d == "bull" else sig_close + spread, 2)
        sigs.append(dict(
            sig_idx=sig_idx, direction=d, limit=limit,
            entry=t.entry_price, stop=t.signal.stop_price,
            tp_hint=getattr(t.signal, "tp_hint", 0.0),
            market_pnl=t.pnl_dollar,
            market_r=(t.pnl_dollar / t.risk_dollar if t.risk_dollar > 0 else 0.0),
            result=t.result))
    return sigs, rr


def recon_fills(sigs: list, shadow: Shadow, W: int) -> dict:
    """collect_signals çıktısını W penceresiyle dolum/kaçış olarak ayırır."""
    fills, miss = [], []
    for s in sigs:
        res = shadow.scan_limit(s["sig_idx"], s["direction"], s["limit"], W)
        rec = {**s, **res}
        (fills if res["filled"] else miss).append(rec)
    return dict(fills=fills, miss=miss, n=len(sigs))


# ═══════════════════════════════ bölümler ═══════════════════════════════════

def sec_overview(rows, led: pd.DataFrame, df_1h: pd.DataFrame,
                 capital: float) -> str:
    html = ["<h2 id='s1'>1. Genel Bakış (önceki rapor metrikleri)</h2>"]
    r_rows = []
    tot = 0.0
    for r in rows:
        r_rows.append([r["strategy"], r["bias"], r["total"], pc(r["wr"]),
                       f2(r["pnl"]), f"{r['pf']:.2f}", f"{r['sharpe']:.2f}",
                       pc(r["maxdd"])])
        tot += r["pnl"]
    r_rows.append(["<b>TOPLAM</b>", "", "", "", f"<b>{f2(tot)}</b>", "", "", ""])
    html.append(tbl(["Strateji", "Bias", "N", "WR", "PnL $", "PF", "Sharpe",
                     "MaxDD"], r_rows))

    # Aylık PnL + gerçekleşen volatilite
    led2 = led.dropna(subset=["exit_ts"]).copy()
    led2["month"] = led2["exit_ts"].dt.to_period("M").astype(str)
    piv = led2.pivot_table(index="month", columns="strategy", values="pnl",
                           aggfunc="sum").fillna(0.0)
    months = list(piv.index)
    dvol = (df_1h["Close"].resample("1D").last().dropna().pct_change()
            .rolling(20).std() * 100)
    mvol = dvol.groupby(dvol.index.to_period("M").astype(str)).mean()

    fig, ax = plt.subplots(figsize=(11, 4.2))
    bottom_pos = np.zeros(len(months))
    bottom_neg = np.zeros(len(months))
    colors = {"fvg": "#4C78A8", "threevol": "#F58518",
              "london": "#54A24B", "qwe": "#B279A2"}
    for s in [c for c in STRATS if c in piv.columns]:
        v = piv[s].to_numpy()
        base = np.where(v >= 0, bottom_pos, bottom_neg)
        ax.bar(months, v, bottom=base, label=s, color=colors.get(s))
        bottom_pos += np.where(v >= 0, v, 0)
        bottom_neg += np.where(v < 0, v, 0)
    ax.axhline(0, color="#888", lw=0.8)
    ax2 = ax.twinx()
    ax2.plot(months, mvol.reindex(months).to_numpy(), color="#E45756",
             marker="o", ms=3, lw=1.2, label="Günlük vol (20g, %)")
    ax2.set_ylabel("Volatilite %")
    ax.set_ylabel("Aylık PnL $")
    ax.tick_params(axis="x", rotation=60, labelsize=8)
    ax.legend(loc="upper left", fontsize=8)
    ax2.legend(loc="upper right", fontsize=8)
    ax.set_title("Aylık net PnL (strateji katkısı) + gerçekleşen volatilite")
    html.append(img(fig, "aylık pnl"))

    m_rows = [[m] + [f0(piv.at[m, s]) if s in piv.columns else "0"
                     for s in STRATS] + [f0(piv.loc[m].sum())]
              for m in months]
    html.append(tbl(["Ay"] + STRATS + ["Toplam"], m_rows))

    # Saatlik PnL
    hp = led.pivot_table(index="hour", columns="strategy", values="pnl",
                         aggfunc="sum").fillna(0.0)
    fig, ax = plt.subplots(figsize=(11, 3.4))
    hp.sum(axis=1).plot(kind="bar", ax=ax,
                        color=np.where(hp.sum(axis=1) >= 0, "#54A24B", "#E45756"))
    ax.set_title("Saatlik toplam net PnL (giriş saati, UTC)")
    ax.set_xlabel("UTC saat")
    ax.set_ylabel("$")
    html.append(img(fig, "saatlik pnl"))

    # Equity eğrisi (birleşik, kapanış sırasına göre)
    led3 = led2.sort_values("exit_ts")
    eq = capital + led3["pnl"].cumsum()
    fig, ax = plt.subplots(figsize=(11, 3.4))
    ax.plot(led3["exit_ts"], eq, color="#4C78A8", lw=1.4)
    ax.set_title("Birleşik equity (tüm stratejiler, işlem kapanış sırası)")
    ax.set_ylabel("$")
    html.append(img(fig, "equity"))
    return "\n".join(html)


def sec_longshort(led: pd.DataFrame) -> str:
    html = ["<h2 id='s2'>2. Long / Short Kırılımı (asimetrik analiz)</h2>",
            "<p>Sistem boğada mı taşınıyor? Short bacakta stop/TP geometrisi "
            "bozuk mu? — yön başına ayrı muhasebe.</p>"]
    rows = []
    for s in STRATS:
        for d, lab in [("bull", "LONG"), ("bear", "SHORT")]:
            g = led[(led["strategy"] == s) & (led["direction"] == d)]
            if len(g) == 0:
                rows.append([s, lab, 0, "—", "—", "—", "—", "—", "—"])
                continue
            p = perf(list(g["pnl"]))
            rows.append([s, lab, p["n"], pc(p["wr"]), f2(p["pnl"]),
                         ("∞" if p["pf"] == float("inf") else f"{p['pf']:.2f}"),
                         f"{g['stop_dist'].mean():.2f}$",
                         f"{g['pnl_r'].mean():+.2f}R",
                         f"{g['dur_h'].mean():.1f}s"])
    return "\n".join(html + [tbl(
        ["Strateji", "Yön", "N", "WR", "PnL $", "PF", "Ort. stop mesafesi",
         "Ort. R", "Ort. süre"], rows,
        "Ort. stop mesafesi $ cinsidir; short'ta sistematik olarak daha genişse "
        "TP hedefleri de orantısız uzak kalıyor olabilir.")])


def _bucket_table(led, s, col, unit, k=5):
    g = led[(led["strategy"] == s)].dropna(subset=[col])
    if len(g) < k * 2:
        return None
    try:
        cats = pd.qcut(g[col], k, duplicates="drop")
    except ValueError:
        return None
    rows = []
    for iv, grp in g.groupby(cats, observed=True):
        p = perf(list(grp["pnl"]))
        rows.append([f"{iv.left:.2f}–{iv.right:.2f}{unit}", p["n"],
                     pc(p["wr"]), f2(p["pnl"]),
                     ("∞" if p["pf"] == float("inf") else f"{p['pf']:.2f}")])
    return rows


def sec_regime(led: pd.DataFrame) -> str:
    html = ["<h2 id='s3'>3. Giriş Anı Rejim Metrikleri (ATR14 & BBW)</h2>",
            "<p>Her işlemin tetiklendiği bardaki 5M ATR(14) ve Bollinger bant "
            "genişliği kaydedildi (ledger sütunları: <code>atr14_5m, bbw_5m, "
            "bbw_ratio</code>). Kantil tabloları stratejinin bozulduğu "
            "matematiksel eşiği gösterir (örn. QWE için ATR tavanı).</p>"]
    for s in STRATS:
        html.append(f"<h3>{s}</h3>")
        r1 = _bucket_table(led, s, "atr14_5m", "$")
        if r1:
            html.append("<h4>Giriş anı ATR14 (5M) kantilleri</h4>")
            html.append(tbl(["ATR aralığı", "N", "WR", "PnL $", "PF"], r1))
        r2 = _bucket_table(led, s, "bbw_ratio", "×")
        if r2:
            html.append("<h4>BBW / 30g medyan oranı kantilleri "
                        "(&lt;1 = sıkışma)</h4>")
            html.append(tbl(["BBW oranı", "N", "WR", "PnL $", "PF"], r2))
        if not r1 and not r2:
            html.append("<p class='note'>Yetersiz işlem.</p>")
    return "\n".join(html)


def sec_duration(led: pd.DataFrame, shadow: Shadow) -> str:
    html = ["<h2 id='s4'>4. İşlem Süresi & Zaman-Stopu (Time-in-Trade)</h2>"]
    rows = []
    for s in STRATS:
        g = led[led["strategy"] == s].dropna(subset=["dur_h"])
        w = g[g["pnl"] > 0]["dur_h"]
        l = g[g["pnl"] <= 0]["dur_h"]
        rows.append([s,
                     f"{w.mean():.1f} / {w.median():.1f}" if len(w) else "—",
                     f"{l.mean():.1f} / {l.median():.1f}" if len(l) else "—",
                     f"{g['dur_h'].max():.0f}" if len(g) else "—"])
    html.append(tbl(["Strateji", "KAZANAN ort/medyan (saat)",
                     "KAYBEDEN ort/medyan (saat)", "En uzun (saat)"], rows,
                    "Kaybedenler kazananlardan belirgin uzunsa sermaye kilidi "
                    "(capital lock) var demektir — zaman stopu adayı."))

    # Zaman-stopu what-if: T saatte hâlâ açık olan işlem o barın kapanışından çıkar
    html.append("<h3>Zaman-stopu what-if (yaklaşık)</h3>")
    rows = []
    for s in STRATS:
        g = led[led["strategy"] == s].dropna(subset=["dur_h"])
        if len(g) == 0:
            continue
        actual = g["pnl"].sum()
        line = [s, f2(actual)]
        for T in (12, 24, 36, 48, 72):
            tot = 0.0
            for _, t in g.iterrows():
                if t["dur_h"] <= T:
                    tot += t["pnl"]
                else:
                    px = shadow.close_at(t["entry_ts"] + pd.Timedelta(hours=T))
                    sgn = 1.0 if t["direction"] == "bull" else -1.0
                    r_ = sgn * (px - t["entry"]) / t["stop_dist"] \
                        if t["stop_dist"] > 0 and not np.isnan(px) else 0.0
                    tot += r_ * t["risk_dollar"] - t["est_cost"]
            line.append(f2(tot))
        rows.append(line)
    html.append(tbl(["Strateji", "Gerçek PnL", "T=12s", "T=24s", "T=36s",
                     "T=48s", "T=72s"], rows,
                    "Yaklaşımlar: kısmi TP1 dolumları ve BE taşımaları "
                    "T-anı fiyat yürüyüşünde modellenmez — tablo yön "
                    "göstergesidir, kesin PnL değildir. Bir T sütunu gerçek "
                    "PnL'i anlamlı aşıyorsa o stratejiye zaman stopu ekleyip "
                    "IS/OOS ile doğrulayın."))
    return "\n".join(html)


def sec_dd(led: pd.DataFrame, capital: float) -> str:
    html = ["<h2 id='s5'>5. Drawdown Süresi (underwater analizi)</h2>"]

    def dd_stats(g):
        g = g.dropna(subset=["exit_ts"]).sort_values("exit_ts")
        if len(g) == 0:
            return None
        eq = capital + g["pnl"].cumsum().to_numpy()
        ts = list(g["exit_ts"])
        peak, peak_t = eq[0], ts[0]
        periods = []
        cur_start, cur_depth = None, 0.0
        for i in range(len(eq)):
            if eq[i] >= peak:
                if cur_start is not None:
                    periods.append((cur_start, ts[i], cur_depth))
                    cur_start = None
                peak, peak_t = eq[i], ts[i]
                cur_depth = 0.0
            else:
                if cur_start is None:
                    cur_start = peak_t
                cur_depth = max(cur_depth, (peak - eq[i]) / peak * 100)
        if cur_start is not None:                       # hâlâ su altında
            periods.append((cur_start, None, cur_depth))
        periods.sort(key=lambda p: ((p[1] or g["exit_ts"].iloc[-1]) - p[0]),
                     reverse=True)
        return periods[:3]

    rows = []
    groups = [("BİRLEŞİK", led)] + [(s, led[led["strategy"] == s]) for s in STRATS]
    for name, g in groups:
        top = dd_stats(g)
        if not top:
            continue
        for j, (a, b, depth) in enumerate(top):
            dur = ((b - a).days if b is not None
                   else (g["exit_ts"].max() - a).days)
            rows.append([name if j == 0 else "", f"#{j+1}",
                         str(a.date()), (str(b.date()) if b is not None
                                         else "devam ediyor"),
                         f"{dur} gün", pc(depth)])
    html.append(tbl(["Portföy", "Sıra", "Tepe tarihi", "Yeni tepe",
                     "Su altı süresi", "Derinlik"], rows,
                    "En uzun 3 underwater dönemi. Derinlik kadar SÜRE de "
                    "psikolojik dayanılabilirliği belirler."))
    return "\n".join(html)


def sec_dow(led: pd.DataFrame) -> str:
    html = ["<h2 id='s6'>6. Haftanın Günü Dağılımı</h2>"]
    rows = []
    for s in STRATS:
        g = led[led["strategy"] == s]
        line = [s]
        for d in range(7):
            gd = g[g["dow"] == d]
            line.append(f"{f0(gd['pnl'].sum())} ({len(gd)})" if len(gd) else "—")
        rows.append(line)
    html.append(tbl(["Strateji"] + DOW_TR, rows,
                    "Hücre: PnL $ (işlem sayısı). Giriş gününe göredir."))

    fri = led[(led["dow"] == 4) & (led["hour"] >= 12)]
    p = perf(list(fri["pnl"]))
    html.append(f"<p><b>Cuma ≥12 UTC girişleri (hafta sonu gap riski):</b> "
                f"N={p['n']}, WR={pc(p['wr'])}, PnL={f2(p['pnl'])}$. "
                f"Belirgin negatifse 'Cuma öğleden sonra flat' kuralı "
                f"IS/OOS ile test edilmeye değer.</p>")
    return "\n".join(html)


def sec_execution(sig_cache: dict, cfg, shadow: Shadow) -> str:
    html = ["<h2 id='s7'>7. Emir Uygulama & Fırsat Maliyeti (limit modu)</h2>",
            "<p>Limit yaşam döngüsü motora dokunmadan yeniden kuruldu: strateji "
            "MARKET modda koşulur, her sinyalin limit fiyatı (sinyal barı "
            "kapanışı ∓ spread) 5M veride ileri taranır. Dolmayan sinyalin "
            "<b>market girilseydi</b> motorun ürettiği gerçek PnL'i = fırsat "
            "maliyeti.</p>"]
    for s in ("fvg", "threevol"):
        if s not in sig_cache:
            continue
        sigs = sig_cache[s]
        W = int(cfg.get(s, "limit_entry_bars", default=3))
        rc = recon_fills(sigs, shadow, W)
        fills, miss, n = rc["fills"], rc["miss"], rc["n"]
        if n == 0:
            continue
        html.append(f"<h3>{s} — W={W}: {len(fills)}/{n} doldu "
                    f"(doluş %{len(fills)/n*100:.0f})</h3>")
        if fills:
            fb = [e["fill_bars"] for e in fills]
            html.append(f"<p>Doluşa-kadar-bar (time-to-fill): ort "
                        f"{np.mean(fb):.2f}, medyan {int(np.median(fb))}, "
                        f"dağılım: " + ", ".join(
                            f"{b} bar → {fb.count(b)}" for b in sorted(set(fb)))
                        + "</p>")
        if miss:
            oc = sum(e["market_pnl"] for e in miss)
            oc_tp = sum(1 for e in miss if e["market_pnl"] > 0)
            nm_buckets = {0.10: [0, 0.0], 0.25: [0, 0.0], 0.50: [0, 0.0],
                          1.00: [0, 0.0]}
            for e in miss:
                for b in nm_buckets:
                    if not np.isnan(e["min_dist"]) and e["min_dist"] <= b:
                        nm_buckets[b][0] += 1
                        nm_buckets[b][1] += e["market_pnl"]
            html.append(
                f"<p><b>Fırsat maliyeti:</b> dolmayan {len(miss)} sinyal "
                f"market girilseydi toplam <b>{oc:+.2f}$</b> ederdi "
                f"({oc_tp} tanesi kârla kapandı). Pozitif ve büyükse W'yi "
                f"genişletmek (bkz. §8) veya limiti gevşetmek "
                f"değerlendirilebilir — ama IS/OOS şart.</p>")
            html.append(tbl(
                ["Limit'e kalan mesafe", "Kaçan N", "Market PnL $"],
                [[f"≤ {b:.2f}$", nm_buckets[b][0], f2(nm_buckets[b][1])]
                 for b in nm_buckets],
                "Near-miss: fiyatın limite en fazla bu kadar yaklaşıp dönmediği "
                "kaçan sinyaller. Market PnL o sinyalin motor sonucudur "
                "(kısmi TP/swing-stop dahil — yaklaşık değil, gerçek)."))
    html.append("<p class='note'>Canlı slippage karşılaştırması: "
                "<code>ledger_diagnostik.csv</code> her işlem için entry/exit/"
                "qty/est_cost/assumed_slip_usd alanlarını içerir — canlı fill "
                "fiyatlarıyla satır satır diff alınabilir (London market "
                "girişlerinde varsayım 0.05$).</p>")
    return "\n".join(html)


def sec_w_sweep(sig_cache: dict, cfg, capital: float, shadow: Shadow) -> str:
    from gui import _run_strategy
    html = ["<h2 id='s8'>8. Limit Penceresi (W) Taraması</h2>",
            "<p>W = limit emrin geçerli kaldığı 5M bar sayısı. PnL gerçek "
            "limit-mod motor koşusundan; doluş oranı market sinyallerinden "
            "yeniden kurulur.</p>"]
    rows_out = []
    for s in ("fvg", "threevol"):
        orig = cfg.get(s, "limit_entry_bars", default=3)
        sigs = sig_cache.get(s, [])
        for W in (2, 3, 4, 5):
            cfg.set(s, "limit_entry_bars", W)
            rr = _run_strategy(s, capital=capital)[0]
            cfg.set(s, "limit_entry_bars", orig)
            rc = recon_fills(sigs, shadow, W)
            fillp = (len(rc["fills"]) / rc["n"] * 100) if rc["n"] else 0.0
            oc = sum(e["market_pnl"] for e in rc["miss"])
            star = " ★" if W == orig else ""
            rows_out.append([f"{s}{star}", W, rr["total"], pc(rr["wr"]),
                             f2(rr["pnl"]), f"{rr['pf']:.2f}", f"%{fillp:.0f}",
                             f2(oc)])
    html.append(tbl(["Strateji", "W", "N", "WR", "PnL $", "PF", "Doluş",
                     "Kaçan fırsat $"], rows_out,
                    "★ = mevcut ayar. Karar kuralı: W ancak IS ve OOS'ta "
                    "birlikte iyileşiyorsa değiştirilmeli (tek dönem tablosu "
                    "yön gösterir)."))
    return "\n".join(html)


def _london_tol_brain_cls():
    """Rapor-yerel London alt sınıfı: killzone başlangıcını N dakika öne çeker.
    Motora dokunmadan zaman-toleransı gölge analizi sağlar."""
    from xauusd_fvg_engine_v10 import LondonReversalBrain

    class _TolBrain(LondonReversalBrain):
        def __init__(self, early_min=0.0, **kw):
            super().__init__(**kw)
            self._early = early_min / 60.0

        def _is_london_killzone(self, t):
            if self.WEEKEND_FILTER and t.weekday() >= 5:
                return False
            h = t.hour + t.minute / 60.0
            if self._session.is_london_dst(t):
                return 6.0 - self._early <= h < 9.0
            return 7.0 - self._early <= h < 10.0
    return _TolBrain


def _run_london(df_1h, df_5m, bt_start, capital, costs_kw, *,
                brain=None, mutate=None):
    from xauusd_fvg_engine_v10 import (
        LondonBacktestEngine, LondonReversalBrain, PrivateBiasProvider,
        RiskManager, PerformanceAnalytics)
    if brain is None:
        brain = LondonReversalBrain(bias_provider=PrivateBiasProvider(df_1h))
    if mutate:
        for k, v in mutate.items():
            setattr(brain, k, v)
    eng = LondonBacktestEngine(
        brain, RiskManager(rr=2.0), initial_capital=capital,
        breakeven_at_R=None, time_exit_bars=None, ema_macd_filter=False,
        **costs_kw)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        trades = eng.run(df_1h, df_5m, bt_start)
        m = PerformanceAnalytics(trades, capital).compute()
    return trades, m


def sec_london(df_1h, df_5m, bt_start, capital, costs_kw,
               london_sigs: list, shadow: Shadow) -> str:
    html = ["<h2 id='s9'>9. London — Gölge Kurgular</h2>"]

    # 9a. Gölge-LİMİT near-miss (gerçek preset MARKET girer; 'limit girseydik'
    # sorusuna market sinyallerinden yeniden kurulan cevap)
    html.append("<h3>9a. Gölge-limit (W=3) near-miss raporu</h3>")
    rc = recon_fills(london_sigs, shadow, 3)
    fills, miss = rc["fills"], rc["miss"]
    html.append(f"<p>Gölge limit doluşu: {len(fills)}/{rc['n']} "
                f"(gerçek preset MARKET girer — bu kurgu limit alternatifini "
                f"ölçer).</p>")
    if miss:
        rows = []
        for e in sorted(miss, key=lambda x: (np.nan_to_num(x["min_dist"],
                                                           nan=9e9))):
            rows.append([f"{e['limit']:.2f}", e["direction"],
                         (f"{e['min_dist']:.2f}$" if not np.isnan(e["min_dist"])
                          else "—"),
                         f2(e["market_pnl"]),
                         "kâr" if e["market_pnl"] > 0 else "zarar"])
        oc = sum(e["market_pnl"] for e in miss)
        near = sum(e["market_pnl"] for e in miss
                   if not np.isnan(e["min_dist"]) and e["min_dist"] <= 0.5)
        html.append(tbl(["Limit", "Yön", "Kaçırma mesafesi", "Market PnL $",
                         "Sonuç"], rows,
                        f"Toplam kaçan fırsat {oc:+.2f}$; bunun ≤0.5$ "
                        f"mesafeyle kaçanları {near:+.2f}$. İkincisi büyük ve "
                        f"pozitifse limiti bir tık gevşetmenin (ya da W=4) "
                        f"doğrudan getirisi budur."))
    else:
        html.append("<p>Kaçan gölge-limit yok.</p>")

    # 9b. Zaman toleransı (killzone öne çekme + sweep penceresi) — yerel alt sınıf
    html.append("<h3>9b. Zaman toleransı matrisi (killzone genişletme)</h3>")
    TolBrain = _london_tol_brain_cls()
    from xauusd_fvg_engine_v10 import PrivateBiasProvider
    combos = [(0, 4), (0, 6), (0, 8), (0, 12), (15, 6), (30, 6), (30, 12)]
    rows = []
    for early, win in combos:
        brain = TolBrain(early_min=float(early),
                         bias_provider=PrivateBiasProvider(df_1h))
        brain.SWEEP_WINDOW_BARS = int(win)
        _, mm = _run_london(df_1h, df_5m, bt_start, capital, costs_kw,
                            brain=brain)
        lab = f"başlangıç −{early}dk, pencere {win} bar (~{win*5}dk)"
        base = " <b>(mevcut)</b>" if (early, win) == (0, 6) else ""
        if mm:
            rows.append([lab + base, mm["total"], pc(mm["win_rate"] * 100),
                         f2(mm["net_pnl"]), f"{mm['profit_factor']:.2f}"])
        else:
            rows.append([lab + base, 0, "—", "—", "—"])
    html.append(tbl(["Tolerans bandı", "N", "WR", "PnL $", "PF"], rows,
                    "Killzone başlangıcını öne çekmek (−dk) ve sweep penceresini "
                    "genişletmek N'i nasıl değiştiriyor? Genişletme ancak WR/PF "
                    "korunuyorsa anlamlı."))

    # 9c. Katılık (strictness) matrisi
    html.append("<h3>9c. Katılık matrisi (kurallar %10/20/30 gevşetilirse)</h3>")
    from xauusd_fvg_engine_v10 import LondonReversalBrain as LRB
    base_brain = LRB()
    rows = []
    for relax, lab in [(1.0, "Mevcut kurallar"), (0.9, "%10 gevşek"),
                       (0.8, "%20 gevşek"), (0.7, "%30 gevşek")]:
        mut = dict(
            MIN_SWEEP_MULT=base_brain.MIN_SWEEP_MULT * relax,
            MIN_SWEEP_PTS=base_brain.MIN_SWEEP_PTS * relax,
            DISPLACEMENT_MIN_ATR=base_brain.DISPLACEMENT_MIN_ATR * relax,
            REJECTION_CLOSE_PCT=base_brain.REJECTION_CLOSE_PCT * relax)
        _, mm = _run_london(df_1h, df_5m, bt_start, capital, costs_kw,
                            mutate=mut)
        if mm:
            rows.append([lab, mm["total"], pc(mm["win_rate"] * 100),
                         f2(mm["net_pnl"]), f"{mm['profit_factor']:.2f}"])
        else:
            rows.append([lab, 0, "—", "—", "—"])
    html.append(tbl(["Katılık", "N", "WR", "PnL $", "PF"], rows,
                    "Gevşetilen kurallar: sweep min derinlik (mult+pts), "
                    "displacement eşiği, reddediş kapanış yüzdesi — hepsi "
                    "birlikte ölçeklenir. N artarken PF çöküyorsa mevcut "
                    "katılık doğrudur."))
    return "\n".join(html)


def sec_htf(led: pd.DataFrame) -> str:
    html = ["<h2 id='s10'>10. HTF (1H/4H) Trend Uyumu</h2>",
            "<p>İşlem yönü ana trendle aynı mı (aligned) yoksa ters mi "
            "(counter)? Ledger: <code>trend_1h, trend_4h, rsi_4h</code>.</p>"]
    rows = []
    for s in STRATS:
        g = led[led["strategy"] == s]
        for col, tf in [("htf1h_align", "1H"), ("htf4h_align", "4H")]:
            for val, lab in [(True, "UYUMLU"), (False, "TERS")]:
                gg = g[g[col] == val]
                if len(gg) == 0:
                    continue
                p = perf(list(gg["pnl"]))
                rows.append([s, tf, lab, p["n"], pc(p["wr"]), f2(p["pnl"]),
                             ("∞" if p["pf"] == float("inf")
                              else f"{p['pf']:.2f}")])
    html.append(tbl(["Strateji", "TF", "Trend", "N", "WR", "PnL $", "PF"],
                    rows,
                    "TERS satır belirgin negatifse counter-trend filtresi "
                    "adayıdır (IS/OOS doğrulaması şart)."))
    rows2 = []
    for s in STRATS:
        g = led[led["strategy"] == s].dropna(subset=["rsi_4h"])
        if len(g) < 10:
            continue
        r1 = _bucket_table(led.dropna(subset=["rsi_4h"]), s, "rsi_4h", "", 4)
        if r1:
            rows2.append(f"<h4>{s} — 4H RSI kantilleri</h4>"
                         + tbl(["4H RSI", "N", "WR", "PnL $", "PF"], r1))
    return "\n".join(html + rows2)


def sec_keylevel(led: pd.DataFrame) -> str:
    html = ["<h2 id='s11'>11. Key Level (PDH/PDL/Haftalık Açılış) "
            "Yakınlık Skoru</h2>",
            "<p>Giriş fiyatının en yakın önemli seviyeye uzaklığı, giriş anı "
            "ATR'siyle normalize (<code>near_level_atr</code>).</p>"]
    edges = [(0, 1, "&lt; 1 ATR (seviyenin dibinde)"), (1, 3, "1–3 ATR"),
             (3, 6, "3–6 ATR"), (6, 1e9, "&gt; 6 ATR (boşlukta)")]
    rows = []
    for s in STRATS:
        g = led[led["strategy"] == s].dropna(subset=["near_level_atr"])
        for lo, hi, lab in edges:
            gg = g[(g["near_level_atr"] >= lo) & (g["near_level_atr"] < hi)]
            if len(gg) == 0:
                continue
            p = perf(list(gg["pnl"]))
            rows.append([s, lab, p["n"], pc(p["wr"]), f2(p["pnl"]),
                         ("∞" if p["pf"] == float("inf") else f"{p['pf']:.2f}")])
    html.append(tbl(["Strateji", "Seviyeye uzaklık", "N", "WR", "PnL $", "PF"],
                    rows,
                    "Seviye dibinde (&lt;1 ATR) sistematik kayıp = likidite "
                    "duvarına çarpma; lokasyon filtresi adayı."))
    return "\n".join(html)


def sec_confluence(led: pd.DataFrame) -> str:
    html = ["<h2 id='s12'>12. Sinyal Kesişimi (Confluence) Matrisi</h2>",
            "<p>Aynı ±15 dk penceresinde birden fazla stratejinin işlem "
            "açtığı durumlar.</p>"]
    rows = []
    for s in STRATS:
        g = led[led["strategy"] == s]
        solo = g[g["confl_n"] == 0]
        conf = g[g["confl_n"] > 0]
        same = g[(g["confl_n"] > 0) & (g["confl_same_dir"])]
        for gg, lab in [(solo, "TEK BAŞINA"), (conf, "KESİŞİMLİ (her yön)"),
                        (same, "KESİŞİMLİ + AYNI YÖN")]:
            if len(gg) == 0:
                continue
            p = perf(list(gg["pnl"]))
            rows.append([s, lab, p["n"], pc(p["wr"]), f2(p["pnl"]),
                         ("∞" if p["pf"] == float("inf") else f"{p['pf']:.2f}")])
    html.append(tbl(["Strateji", "Durum", "N", "WR", "PnL $", "PF"], rows,
                    "AYNI YÖN kesişimi belirgin güçlüyse 'double-size' kuralı "
                    "adayıdır — ama N küçükken karar verme, IS/OOS şart."))
    pair = defaultdict(int)
    for _, t in led[led["confl_n"] > 0].iterrows():
        for other in t["confl_with"].split("+"):
            if other:
                pair[tuple(sorted([t["strategy"], other]))] += 1
    if pair:
        html.append(tbl(["Çift", "Kesişim (işlem sayısı)"],
                        [[f"{a} + {b}", n // 2 or n]
                         for (a, b), n in sorted(pair.items())],
                        "Çiftler iki taraftan sayıldığı için ~yarıya "
                        "normalize edilmiştir."))
    return "\n".join(html)


# ═══════════════════════════════ HTML iskeleti ══════════════════════════════

CSS = """
body{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;margin:0 auto;
     max-width:1080px;padding:24px;background:#101418;color:#dfe6ee;line-height:1.5}
h1{font-size:1.5em;border-bottom:2px solid #3d5a80;padding-bottom:8px}
h2{font-size:1.2em;color:#9fc2e8;margin-top:2em;border-bottom:1px solid #2a3542;
   padding-bottom:4px}
h3{font-size:1.05em;color:#c7d6e8}h4{color:#aab8c8;margin-bottom:4px}
table{border-collapse:collapse;font-size:0.86em;margin:8px 0;
      font-variant-numeric:tabular-nums}
th,td{border:1px solid #2a3542;padding:4px 9px;text-align:right}
th{background:#1a222c;color:#9fc2e8}td:first-child,th:first-child{text-align:left}
.twrap{overflow-x:auto}img{max-width:100%;border:1px solid #2a3542;
      border-radius:4px;margin:8px 0}
.note{font-size:0.82em;color:#8ea0b5;margin:2px 0 14px}
code{background:#1a222c;padding:1px 5px;border-radius:3px}
.toc a{color:#7fb3e8;text-decoration:none;display:block;padding:1px 0}
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Teşhis backtest raporu")
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--fast", action="store_true",
                    help="Matris taramalarını (W, London gölge) atla")
    args = ap.parse_args()

    from gui import _run_strategy, _load_data
    from config import get_config
    cfg = get_config()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Veri yükleniyor...")
    df_1h, df_5m, bt_start = _load_data()
    days = (df_5m.index.max() - df_5m.index.min()).days
    print(f"  {df_5m.index.min()} → {df_5m.index.max()} "
          f"({days} gün ≈ {days/365:.1f} yıl)")

    costs = dict(
        spread_usd=float(cfg.get("costs", "spread_usd", default=0.3)),
        slippage_usd=float(cfg.get("costs", "slippage_usd", default=0.05)),
        commission_pct=float(cfg.get("costs", "commission_pct", default=0.05)),
        maker_pct=float(cfg.get("costs", "maker_pct", default=0.02)))
    costs_kw = dict(
        cost_spread_usd=costs["spread_usd"],
        cost_slippage_usd=costs["slippage_usd"],
        cost_commission_pct=costs["commission_pct"],
        cost_maker_pct=costs["maker_pct"],
        uniform_risk_fraction=float(cfg.get("risk", "risk_fraction",
                                            default=0.01)))
    limit_strats = {s for s in ("fvg", "threevol")
                    if cfg.get(s, "entry_order", default="market") == "limit"}

    print("Temel koşu: 4 strateji (sabit preset'ler)...")
    rows = _run_strategy("hepsi", capital=args.capital, keep_trades=True)
    for r in rows:
        if r.get("_error"):
            print(f"  UYARI {r['strategy']}: {r['_error']}")

    print("Bağlam göstergeleri (causal) hesaplanıyor...")
    ctx = build_context(df_5m, df_1h)
    led = build_ledger(rows, ctx, costs, limit_strats)
    led_path = OUT_DIR / "ledger_diagnostik.csv"
    led.to_csv(led_path, index=False, encoding="utf-8-sig")
    print(f"  Ledger → {led_path} ({len(led)} işlem)")

    shadow = Shadow(df_5m)

    # Emir-uygulama analizleri için market-mod sinyalleri (motora dokunmadan
    # yeniden kurma girdisi). fvg/threevol limit modda → market koşusu ayrı;
    # london zaten market → 9a gölge-limit girdisi.
    sig_cache = {}
    if not args.fast:
        print("Market-mod sinyalleri toplanıyor (fvg/threevol/london)...")
        for s in ("fvg", "threevol", "london"):
            sigs, _ = collect_signals(s, cfg, args.capital, shadow,
                                      costs["spread_usd"])
            sig_cache[s] = sigs
            print(f"  {s}: {len(sigs)} market sinyali")

    sections = []
    print("Bölüm 1-6: genel bakış, long/short, rejim, süre, DD, gün...")
    sections.append(sec_overview(rows, led, df_1h, args.capital))
    sections.append(sec_longshort(led))
    sections.append(sec_regime(led))
    sections.append(sec_duration(led, shadow))
    sections.append(sec_dd(led, args.capital))
    sections.append(sec_dow(led))
    if args.fast:
        sections.append("<h2 id='s7'>7-9. Emir uygulama & matris taramaları"
                        "</h2><p class='note'>--fast ile atlandı "
                        "(market-mod yeniden kurma + W taraması + London "
                        "gölge kurguları).</p>")
    else:
        print("Bölüm 7: emir uygulama + fırsat maliyeti...")
        sections.append(sec_execution(sig_cache, cfg, shadow))
        print("Bölüm 8: W taraması (8 backtest koşusu)...")
        sections.append(sec_w_sweep(sig_cache, cfg, args.capital, shadow))
        print("Bölüm 9: London gölge kurguları (~11 koşu)...")
        sections.append(sec_london(df_1h, df_5m, bt_start, args.capital,
                                   costs_kw, sig_cache.get("london", []),
                                   shadow))
    print("Bölüm 10-12: HTF, key level, kesişim...")
    sections.append(sec_htf(led))
    sections.append(sec_keylevel(led))
    sections.append(sec_confluence(led))

    toc = ('<div class="toc"><b>İçindekiler</b>'
           + "".join(f'<a href="#s{i}">{i}. {t}</a>' for i, t in enumerate(
               ["Genel Bakış", "Long/Short", "Giriş Anı Rejimi (ATR/BBW)",
                "Süre & Zaman-Stopu", "Drawdown Süresi", "Haftanın Günü",
                "Emir Uygulama & Fırsat Maliyeti", "W Taraması",
                "London Gölge Kurguları", "HTF Uyumu", "Key Level Yakınlığı",
                "Kesişim Matrisi"], start=1)) + "</div>")

    html = (f'<meta charset="utf-8"><title>Teşhis Raporu — XAUUSD</title>'
            f"<style>{CSS}</style>"
            f"<h1>XAUUSD Algoritmik Sistem — Teşhis Raporu</h1>"
            f"<p>Dönem: <b>{df_5m.index.min().date()} → "
            f"{df_5m.index.max().date()}</b> ({days/365:.1f} yıl) | "
            f"Gerçek BingX maliyetleri | %1 uniform risk | sabit preset'ler"
            f"{' | <b>--fast</b> (matrissiz)' if args.fast else ''}</p>"
            + toc + "\n".join(sections)
            + '<p class="note">Tüm gölge kurgular ve what-if tabloları YALNIZ '
              "teşhis amaçlıdır; hiçbir mekanizma IS/OOS doğrulaması olmadan "
              "preset'e alınmamalıdır (kural: OOS'ta çürüyen dışarı).</p>")

    out = OUT_DIR / "rapor_diagnostik.html"
    out.write_text(html, encoding="utf-8")
    print(f"\nRapor → {out}")
    print("Bitti.")


if __name__ == "__main__":
    main()
