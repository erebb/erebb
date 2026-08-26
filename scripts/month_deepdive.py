# -*- coding: utf-8 -*-
"""
AY DERİN ANALİZİ — en iyi ay, en kötü ay ve TÜM zarar eden aylar
=================================================================
Sorular:
  • En iyi ay neden en iyi oldu? Hangi işlemler TP'ye gitti, o anda trend /
    EMA dizilimi / MACD / volatilite / hacim neydi?
  • En kötü ay neden battı? Her stop'un giriş anındaki bağlamı neydi?
  • Zarar eden AYLARIN ORTAK PAYDASI ne? (trend, EMA, MACD, volatilite)

Çıktı: reports/AY_DERIN_ANALIZ.html  (grafikler gömülü, tek dosya, UTF-8)
Kullanım: python3 scripts/month_deepdive.py
"""

from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "reports"
STRATS = ["fvg", "harmonic", "threevol", "fib"]


# ═══════════════════════════ veri + defter ══════════════════════════════════

def build():
    from final_report import build_context, at
    from gui import _run_strategy, _load_data
    from xauusd_fvg_engine_v10 import to_naive
    df_1h, df_5m, _ = _load_data()
    print("Bağlam göstergeleri...", flush=True)
    ctx = build_context(df_5m, df_1h)
    rows = []
    for s in STRATS:
        r = _run_strategy(s, keep_trades=True)[0]
        print(f"  {s}: N={r['total']} PnL={r['pnl']:+.1f}", flush=True)
        for t in r.get("_trades", []):
            if t.exit_time is None or t.risk_dollar <= 0:
                continue
            ts, xs = to_naive(t.signal.entry_time), to_naive(t.exit_time)
            rec = dict(s=s, entry=ts, exit=xs, dir=t.signal.direction,
                       r=t.pnl_dollar / t.risk_dollar, px=t.entry_price,
                       sl=t.sl, tp=t.tp, stop=t.risk, reason=getattr(t, "exit_reason", ""),
                       mfe=getattr(t, "mfe_r", np.nan), mae=getattr(t, "mae_r", np.nan),
                       dur_h=(xs - ts).total_seconds() / 3600)
            for k, v in ctx.items():
                rec[k] = at(v, ts)
            rows.append(rec)
    d = pd.DataFrame(rows).sort_values("exit").reset_index(drop=True)
    d["ym"] = d["exit"].dt.to_period("M")
    return d, df_1h, df_5m


def daily(df_1h):
    dd = df_1h.resample("1D").agg({"Open": "first", "High": "max", "Low": "min",
                                   "Close": "last", "Volume": "sum"}).dropna(subset=["Close"])
    c = dd["Close"]
    dd["ema20"] = c.ewm(span=20, adjust=False).mean()
    dd["ema50"] = c.ewm(span=50, adjust=False).mean()
    dd["ema200"] = c.ewm(span=200, adjust=False).mean()
    ef, es = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    dd["macd"] = ef - es
    dd["sig"] = dd["macd"].ewm(span=9, adjust=False).mean()
    dd["hist"] = dd["macd"] - dd["sig"]
    tr = pd.concat([dd.High - dd.Low, (dd.High - c.shift()).abs(),
                    (dd.Low - c.shift()).abs()], axis=1).max(axis=1)
    dd["atrp"] = tr.rolling(14).mean() / c * 100
    ma, sd = c.rolling(20).mean(), c.rolling(20).std()
    dd["bbw"] = 4 * sd / ma * 100
    return dd


# ═══════════════════════════ görsel ═════════════════════════════════════════

def b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", facecolor="#12161c")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def month_chart(dd, tr, ym, title):
    lo = pd.Timestamp(ym.start_time) - pd.Timedelta(days=20)
    hi = pd.Timestamp(ym.end_time) + pd.Timedelta(days=3)
    w = dd[(dd.index >= lo) & (dd.index <= hi)]
    if len(w) < 3:
        return ""
    fig, ax = plt.subplots(3, 1, figsize=(13, 9), sharex=True,
                           gridspec_kw={"height_ratios": [3, 1.2, 1.2]},
                           facecolor="#12161c")
    for a in ax:
        a.set_facecolor("#12161c"); a.tick_params(colors="#9fb0c4", labelsize=8)
        for sp in a.spines.values():
            sp.set_color("#2a3542")
        a.grid(alpha=0.15, color="#3a4552")
    up = w.Close >= w.Open
    ax[0].vlines(w.index, w.Low, w.High, color="#7c8896", lw=0.8)
    ax[0].vlines(w.index[up], w.Open[up], w.Close[up], color="#26a69a", lw=4)
    ax[0].vlines(w.index[~up], w.Open[~up], w.Close[~up], color="#ef5350", lw=4)
    for col, cl, lb in [("ema20", "#f5c542", "EMA20"), ("ema50", "#4C78A8", "EMA50"),
                        ("ema200", "#B279A2", "EMA200")]:
        ax[0].plot(w.index, w[col], lw=1.2, color=cl, label=lb)
    for i, t in enumerate(tr.itertuples(), 1):
        col = "#26a69a" if t.r > 0 else "#ef5350"
        ax[0].scatter(t.entry, t.px, marker="^" if t.dir == "bull" else "v",
                      s=130, color=col, edgecolors="white", linewidths=1, zorder=6)
        ax[0].annotate(f"{i}", (t.entry, t.px), color="white", fontsize=8,
                       weight="bold", xytext=(4, 6), textcoords="offset points")
    ax[0].set_title(title, color="#e6edf5", fontsize=12)
    ax[0].set_ylabel("Fiyat $", color="#9fb0c4")
    ax[0].legend(fontsize=8, facecolor="#1a222c", labelcolor="#9fb0c4")
    ax[1].bar(w.index, w["hist"], color=np.where(w["hist"] >= 0, "#26a69a", "#ef5350"))
    ax[1].plot(w.index, w["macd"], lw=1.2, color="#4C78A8", label="MACD")
    ax[1].plot(w.index, w["sig"], lw=1.2, color="#f5c542", label="Sinyal")
    ax[1].axhline(0, color="#7c8896", lw=.7)
    ax[1].set_ylabel("MACD (1G)", color="#9fb0c4")
    ax[1].legend(fontsize=7, facecolor="#1a222c", labelcolor="#9fb0c4")
    ax[2].plot(w.index, w["atrp"], lw=1.3, color="#E45756", label="ATR14 %")
    ax[2].plot(w.index, w["bbw"], lw=1.1, color="#B279A2", ls="--", label="BB genişliği %")
    ax[2].set_ylabel("Volatilite", color="#9fb0c4")
    ax[2].legend(fontsize=7, facecolor="#1a222c", labelcolor="#9fb0c4")
    ax[2].xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    fig.tight_layout()
    return b64(fig)


def stack_txt(v):
    return {2: "BOĞA (9>21>50)", 1: "karışık↑", -1: "karışık↓",
            -2: "AYI (9<21<50)"}.get(int(v) if v == v else 0, "—")


def trade_table(tr):
    rows = []
    for i, t in enumerate(tr.itertuples(), 1):
        sonuc = ("<span class='p'>TP</span>" if t.reason == "tp" else
                 "<span class='n'>STOP</span>" if t.reason == "sl" else
                 f"<span class='b'>{t.reason.upper()}</span>")
        rows.append([
            i, t.s, "LONG" if t.dir == "bull" else "SHORT",
            str(t.entry)[:16], f"{t.px:,.1f}",
            sonuc, f"<b class='{'p' if t.r>0 else 'n'}'>{t.r:+.2f}R</b>",
            f"{t.mfe:+.2f}", f"{t.mae:.2f}", f"{t.dur_h:.0f}s",
            stack_txt(getattr(t, "d1_stack", np.nan)),
            f"{getattr(t,'d1_macd',np.nan):+.2f}",
            f"{getattr(t,'h4_macd',np.nan):+.2f}",
            f"{getattr(t,'d1_atrp',np.nan):.2f}",
            f"{getattr(t,'d1_volr',np.nan):.2f}",
            f"{getattr(t,'d1_rsi',np.nan):.0f}"])
    head = ["#", "Strateji", "Yön", "Giriş", "Fiyat", "Çıkış", "R", "MFE", "MAE",
            "Süre", "Günlük EMA", "1G MACD%", "4H MACD%", "1G ATR%", "Hacim×", "1G RSI"]
    h = "".join(f"<th>{x}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows)
    return (f'<div class="tw"><table><thead><tr>{h}</tr></thead>'
            f"<tbody>{b}</tbody></table></div>")


CSS = """
body{background:#0e1218;color:#dfe6ee;font-family:-apple-system,'Segoe UI',Roboto,sans-serif;
     max-width:1250px;margin:auto;padding:26px;line-height:1.55}
h1{border-bottom:3px solid #3d5a80;padding-bottom:10px}
h2{color:#f5c542;margin-top:2.4em;border-bottom:1px solid #2a3542;padding-bottom:6px}
h3{color:#9fc2e8;margin-top:1.5em}
img{max-width:100%;border:1px solid #2a3542;border-radius:5px;margin:10px 0}
table{border-collapse:collapse;font-size:.8em;margin:8px 0;width:100%;
      font-variant-numeric:tabular-nums}
th,td{border:1px solid #2a3542;padding:3px 7px;text-align:right}
th{background:#1a222c;color:#9fc2e8}td:first-child,th:first-child{text-align:center}
.tw{overflow-x:auto}.p{color:#26a69a;font-weight:600}.n{color:#ef5350;font-weight:600}
.b{color:#f5c542;font-weight:600}
.note{font-size:.84em;color:#8ea0b5}
.kutu{background:#161d26;border-left:4px solid #f5c542;padding:12px 16px;margin:14px 0;
      border-radius:0 5px 5px 0}
.iyi{border-left-color:#26a69a}.kotu{border-left-color:#ef5350}
.big{font-size:1.3em;font-weight:700}
"""


def ay_bolumu(d, dd, ym, baslik, sinif):
    tr = d[d.ym == ym].sort_values("entry")
    R = tr.r.sum()
    tp = tr[tr.reason == "tp"]; sl = tr[tr.reason == "sl"]
    h = [f'<h2>{baslik}: {ym} — <span class="{"p" if R>0 else "n"}">{R:+.2f}R</span></h2>']
    h.append(f'<div class="kutu {sinif}"><span class="big">{len(tr)} işlem</span> · '
             f'TP: <b class="p">{len(tp)}</b> ({tp.r.sum():+.1f}R) · '
             f'STOP: <b class="n">{len(sl)}</b> ({sl.r.sum():+.1f}R) · '
             f'WR %{(tr.r>0).mean()*100:.0f}</div>')
    # ayın piyasa bağlamı
    w = dd[(dd.index >= pd.Timestamp(ym.start_time)) &
           (dd.index <= pd.Timestamp(ym.end_time))]
    if len(w):
        ret = (w.Close.iloc[-1] / w.Open.iloc[0] - 1) * 100
        eff = abs(w.Close.pct_change().sum()) / max(w.Close.pct_change().abs().sum(), 1e-9)
        h.append(f'<p class="note">Altın aylık getiri <b>{ret:+.2f}%</b> · '
                 f'trend verimliliği <b>{eff:.2f}</b> '
                 f'({"TRENDLİ" if eff>=.30 else "AKÜMÜLASYON" if eff<.18 else "karışık"}) · '
                 f'ay ortalaması: MACD {w["macd"].mean()/w["Close"].mean()*100:+.2f}% · '
                 f'ATR {w["atrp"].mean():.2f}% · BB genişliği {w["bbw"].mean():.2f}%</p>')
    img = month_chart(dd, tr, ym, f"{ym} — işlemler numaralı (▲long ▼short, yeşil=kâr)")
    if img:
        h.append(f'<img src="data:image/png;base64,{img}">')
    h.append("<h3>İşlem işlem: giriş anındaki bağlam ve sonuç</h3>")
    h.append(trade_table(tr))
    # neden TP / neden STOP
    if len(tp) and len(sl):
        h.append("<h3>Bu ayda TP'ler stop'lardan ne ile ayrıldı?</h3>")
        rows = []
        for lab, col in [("Günlük EMA dizilimi (+2=boğa)", "d1_stack"),
                         ("Günlük MACD %", "d1_macd"), ("4H MACD %", "h4_macd"),
                         ("1H MACD %", "h1_macd"), ("Günlük ATR %", "d1_atrp"),
                         ("Günlük BB genişliği", "d1_bbw"),
                         ("Hacim / medyan", "d1_volr"), ("Günlük RSI", "d1_rsi"),
                         ("MFE (R)", "mfe"), ("MAE (R)", "mae"),
                         ("Süre (saat)", "dur_h")]:
            if col not in tr.columns:
                continue
            a, b = tp[col].dropna(), sl[col].dropna()
            if len(a) == 0 or len(b) == 0:
                continue
            rows.append([lab, f"{a.mean():+.2f}", f"{b.mean():+.2f}",
                         f'<span class="{"p" if a.mean()>b.mean() else "n"}">'
                         f'{a.mean()-b.mean():+.2f}</span>'])
        h.append(tbl3(["Gösterge", "TP olanlar", "STOP olanlar", "Fark"], rows))
    return "\n".join(h)


def tbl3(head, rows):
    hh = "".join(f"<th>{x}</th>" for x in head)
    bb = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table><thead><tr>{hh}</tr></thead><tbody>{bb}</tbody></table></div>'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("Veri + backtest...")
    d, df_1h, df_5m = build()
    dd = daily(df_1h)
    d.to_csv(OUT / "ay_derin_islemler.csv", index=False, encoding="utf-8-sig")
    m = d.groupby("ym").agg(R=("r", "sum"), N=("r", "size"),
                            WR=("r", lambda x: (x > 0).mean()*100))
    # aylık piyasa bağlamı
    mk = pd.DataFrame({
        "getiri": dd.Close.pct_change().resample("ME").sum()*100,
        "eff": dd.Close.pct_change().resample("ME").apply(
            lambda x: abs(x.sum())/x.abs().sum() if x.abs().sum() > 0 else 0),
        "macd": (dd["macd"]/dd["Close"]*100).resample("ME").mean(),
        "hist": (dd["hist"]/dd["Close"]*100).resample("ME").mean(),
        "atrp": dd["atrp"].resample("ME").mean(),
        "bbw": dd["bbw"].resample("ME").mean(),
        "e20_50": ((dd["ema20"] > dd["ema50"]).astype(float)).resample("ME").mean()*100,
        "ustu200": ((dd["Close"] > dd["ema200"]).astype(float)).resample("ME").mean()*100})
    mk.index = mk.index.to_period("M")
    m = m.join(mk).dropna(subset=["R"])
    best, worst = m.R.idxmax(), m.R.idxmin()

    parts = [ay_bolumu(d, dd, best, "EN İYİ AY", "iyi"),
             ay_bolumu(d, dd, worst, "EN KÖTÜ AY", "kotu")]

    # ── tüm zarar eden aylar ──
    neg = m[m.R < 0].sort_values("R")
    pos = m[m.R > 0]
    h = [f'<h2>Zarar Eden TÜM Aylar ({len(neg)} ay)</h2>']
    rows = []
    for ym, r in neg.iterrows():
        tr = d[d.ym == ym]
        R_, N_, WR_ = r["R"], int(r["N"]), r["WR"]
        get_, eff_ = r["getiri"], r["eff"]
        mac_, his_ = r["macd"], r["hist"]
        atr_, bbw_ = r["atrp"], r["bbw"]
        e_, u_ = r["e20_50"], r["ustu200"]
        rej = ("TRENDLİ" if eff_ >= .30 else
               "AKÜMÜLASYON" if eff_ < .18 else "karışık")
        kir = "/".join(f"{s2}:{g.r.sum():+.1f}" for s2, g in tr.groupby("s"))
        rows.append([str(ym), f'<span class="n">{R_:+.1f}</span>', N_,
                     f"%{WR_:.0f}", f"{get_:+.1f}%", f"{eff_:.2f}", rej,
                     f"{mac_:+.2f}", f"{his_:+.3f}", f"{atr_:.2f}",
                     f"{bbw_:.1f}", f"%{e_:.0f}", f"%{u_:.0f}", kir])
    h.append(tbl3(["Ay", "R", "N", "WR", "Altın %", "Verim", "Rejim", "MACD%",
                   "MACD hist%", "ATR%", "BB gen.", "EMA20>50 gün%", "200 üstü gün%",
                   "Strateji kırılımı"], rows))
    # ── zarar vs kâr aylarının ortak paydası ──
    h.append("<h3>Zarar eden aylar ile kâr eden aylar: ortak payda</h3>")
    rows = []
    for lab, col in [("Altın aylık getiri %", "getiri"),
                     ("Trend verimliliği (Kaufman)", "eff"),
                     ("Günlük MACD %", "macd"), ("MACD histogram %", "hist"),
                     ("Günlük ATR %", "atrp"), ("BB genişliği %", "bbw"),
                     ("EMA20>EMA50 olan gün %", "e20_50"),
                     ("Fiyat EMA200 üstü gün %", "ustu200"),
                     ("İşlem sayısı", "N"), ("WR %", "WR")]:
        a, b = neg[col].dropna(), pos[col].dropna()
        if len(a) == 0 or len(b) == 0:
            continue
        pooled = np.sqrt((a.var() + b.var())/2) or 1e-9
        dcoh = (b.mean() - a.mean())/pooled
        güç = "GÜÇLÜ" if abs(dcoh) >= .5 else ("orta" if abs(dcoh) >= .25 else "zayıf")
        rows.append([lab, f"{a.mean():+.2f}", f"{b.mean():+.2f}",
                     f'<span class="{"p" if dcoh>0 else "n"}">{b.mean()-a.mean():+.2f}</span>',
                     f"{dcoh:+.2f}", güç])
    h.append(tbl3(["Gösterge", "ZARAR ayları", "KÂR ayları", "Fark",
                   "Cohen's d", "Ayırt edicilik"], rows))
    # ── çıkış nedenleri: zarar aylarında vs kâr aylarında ──
    d["neg_ay"] = d.ym.isin(set(neg.index))
    rows = []
    for reason, g in d.groupby("reason"):
        a = g[g.neg_ay]; b = g[~g.neg_ay]
        rows.append([reason or "(yok)", len(a), f"{a.r.sum():+.1f}",
                     len(b), f"{b.r.sum():+.1f}"])
    h.append("<h3>Çıkış nedenleri: zarar aylarında vs kâr aylarında</h3>")
    h.append(tbl3(["Çıkış", "Zarar ayı N", "Zarar ayı R",
                   "Kâr ayı N", "Kâr ayı R"], rows))
    parts.append("\n".join(h))

    html = (f'<meta charset="utf-8"><title>Ay Derin Analizi</title>'
            f"<style>{CSS}</style><h1>XAUUSD — Ay Derin Analizi</h1>"
            f'<p class="note">{len(d)} işlem · {len(m)} ay · '
            f'en iyi <b>{best}</b> ({m.R.max():+.1f}R) · '
            f'en kötü <b>{worst}</b> ({m.R.min():+.1f}R) · '
            f'zarar eden ay: {len(neg)}/{len(m)}</p>'
            + "\n".join(parts))
    p = OUT / "AY_DERIN_ANALIZ.html"
    p.write_text(html, encoding="utf-8")
    print(f"\nRapor → {p} ({p.stat().st_size/1e6:.1f} MB)")
    print(f"en iyi ay {best} {m.R.max():+.1f}R | en kötü ay {worst} {m.R.min():+.1f}R")
    print("BITTI")


if __name__ == "__main__":
    main()
