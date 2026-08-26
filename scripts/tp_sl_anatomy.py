# -*- coding: utf-8 -*-
"""
TP/SL ANATOMİSİ VE OKUMA KILAVUZU
==================================
Tek belgede:
  1. TP'ler neden TP oluyor — giriş bağlamı ve yol
  2. SL'ler neden SL oluyor — ölüm tipolojisi
  3. Gerçekte ne ayırt ediyor — giriş göstergeleri vs yol göstergeleri
  4. Volatilite ne anlama geliyor, nasıl okunur
  5. Trend / rejim ne anlama geliyor, nasıl okunur
  6. Üst üste zarar eden aylar — iki ayrı ölüm şekli
  7. Pratik okuma kılavuzu
  8. Denenip elenen mekanizmalar

Defter reports/ay_derin_islemler.csv'den okunur, backtest KOŞULMAZ.
Çıktı: reports/TP_SL_ANATOMI.html
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "reports"
CAPITAL = 10_000.0

GOLD, POS, NEG, DIM = "#c9a227", "#2e9e6b", "#d1495b", "#8b9199"
TFS = {"m5": "5 dakika", "m15": "15 dakika", "h1": "1 saat",
       "h4": "4 saat", "d1": "1 gün"}


# ─────────────────────────────── veri ───────────────────────────────────────

def load() -> pd.DataFrame:
    d = pd.read_csv(OUT / "ay_derin_islemler.csv")
    d = d[d["reason"] != "open"].copy()
    d["entry"] = pd.to_datetime(d["entry"])
    d["exit"] = pd.to_datetime(d["exit"])
    d = d.sort_values("exit").reset_index(drop=True)
    bal = CAPITAL
    pn, bl = [], []
    for r in d["r"]:
        p = 0.01 * bal * r
        bal += p
        pn.append(p)
        bl.append(bal)
    d["pnl"], d["bal"] = pn, bl
    d["ym"] = d["exit"].dt.to_period("M")
    d["hour"] = d["entry"].dt.hour
    return d


def cohen(a: pd.Series, b: pd.Series) -> float:
    a = a.replace([np.inf, -np.inf], np.nan).dropna()
    b = b.replace([np.inf, -np.inf], np.nan).dropna()
    if len(a) < 10 or len(b) < 10:
        return np.nan
    sp = np.sqrt((a.var() + b.var()) / 2)
    return np.nan if not sp else (a.mean() - b.mean()) / sp


# ─────────────────────────────── grafik ─────────────────────────────────────

def png(fig) -> str:
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=110, bbox_inches="tight",
                facecolor="none", transparent=True)
    plt.close(fig)
    return base64.b64encode(b.getvalue()).decode()


def _skin(ax, ylab: str = "") -> None:
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(DIM)
    ax.tick_params(colors=DIM, labelsize=8)
    if ylab:
        ax.set_ylabel(ylab, color=DIM, fontsize=9)
    ax.grid(axis="y", color=DIM, alpha=0.18, lw=0.6)
    ax.set_axisbelow(True)


def ch_rdist(d: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(10, 3))
    bins = np.arange(-1.6, 6.2, 0.2)
    ax.hist(d[d.r <= 0].r, bins=bins, color=NEG, alpha=.85, label="kayıp")
    ax.hist(d[d.r > 0].r, bins=bins, color=POS, alpha=.85, label="kazanç")
    ax.axvline(0, color=DIM, lw=.8)
    ax.legend(fontsize=8, labelcolor=DIM, facecolor="none", edgecolor="none")
    ax.set_xlabel("işlem sonucu (R)", color=DIM, fontsize=9)
    _skin(ax, "işlem sayısı")
    return png(fig)


def ch_path(d: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for lbl, col, m in [("TP", POS, "o"), ("SL", NEG, "x")]:
        k = d[d.reason == lbl.lower()]
        ax.scatter(k.mae, k.mfe, c=col, marker=m, s=38, alpha=.75, label=lbl)
    ax.axhline(1, color=DIM, lw=.7, ls="--")
    ax.axvline(0.5, color=DIM, lw=.7, ls="--")
    ax.set_xlabel("MAE — aleyhte en derin nokta (R)", color=DIM, fontsize=9)
    ax.legend(fontsize=8, labelcolor=DIM, facecolor="none", edgecolor="none")
    _skin(ax, "MFE — lehte en yüksek nokta (R)")
    return png(fig)


def ch_cohen(rows: list) -> str:
    rows = rows[:12][::-1]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    y = np.arange(len(rows))
    v = [r[3] for r in rows]
    ax.barh(y, v, color=[POS if x > 0 else NEG for x in v], alpha=.85)
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=8, color=DIM)
    ax.axvline(0, color=DIM, lw=.8)
    for t, lbl in [(0.2, "zayıf"), (0.5, "orta"), (0.8, "güçlü")]:
        for s in (1, -1):
            ax.axvline(s * t, color=DIM, lw=.6, ls=":")
        ax.text(t, len(rows) - .4, lbl, fontsize=7, color=DIM, ha="center")
    ax.set_xlim(-3.2, 3.2)
    ax.set_xlabel("Cohen d — TP ile SL arasındaki ayrım gücü",
                  color=DIM, fontsize=9)
    _skin(ax)
    return png(fig)


def ch_vol(d: pd.DataFrame) -> str:
    d = d.copy()
    d["vb"] = pd.qcut(d.d1_atrp, 4,
                      labels=["çok düşük", "düşük", "yüksek", "çok yüksek"])
    g = d.groupby("vb", observed=True).agg(R=("r", "sum"),
                                           wr=("r", lambda s: 100 * (s > 0).mean()))
    fig, ax = plt.subplots(figsize=(10, 3.1))
    ax.bar(g.index.astype(str), g.R, color=GOLD, alpha=.9, width=.6)
    for i, (r, w) in enumerate(zip(g.R, g.wr)):
        ax.text(i, r + 1.5, "%.1fR\n%%%.0f kazanma" % (r, w), ha="center",
                fontsize=8, color=DIM)
    ax.set_ylim(0, g.R.max() * 1.35)
    ax.set_xlabel("giriş anındaki günlük ATR% çeyreği", color=DIM, fontsize=9)
    _skin(ax, "toplam R")
    return png(fig)


def ch_dur(d: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(10, 3))
    bins = np.logspace(np.log10(1), np.log10(1200), 34)
    ax.hist(d[d.reason == "sl"].dur_h, bins=bins, color=NEG, alpha=.8, label="SL")
    ax.hist(d[d.reason == "tp"].dur_h, bins=bins, color=POS, alpha=.8, label="TP")
    ax.set_xscale("log")
    ax.set_xticks([2, 6, 24, 72, 168, 720])
    ax.set_xticklabels(["2s", "6s", "1g", "3g", "1hf", "1ay"])
    ax.legend(fontsize=8, labelcolor=DIM, facecolor="none", edgecolor="none")
    ax.set_xlabel("işlemin açık kaldığı süre", color=DIM, fontsize=9)
    _skin(ax, "işlem sayısı")
    return png(fig)


def ch_month(d: pd.DataFrame, streaks: list) -> str:
    m = d.groupby("ym")["pnl"].sum()
    full = pd.period_range(m.index.min(), m.index.max(), freq="M")
    m = m.reindex(full).fillna(0)
    fig, ax = plt.subplots(figsize=(10, 3.1))
    x = [p.to_timestamp() for p in m.index]
    ax.bar(x, m.values, width=22, color=[POS if v > 0 else NEG for v in m])
    for a, b in streaks:
        ax.axvspan(pd.Timestamp(a.start_time), pd.Timestamp(b.end_time),
                   color=NEG, alpha=.13)
    ax.axhline(0, color=DIM, lw=.8)
    _skin(ax, "aylık PnL ($)")
    return png(fig)


# ─────────────────────────────── html ───────────────────────────────────────

def tbl(head: list, rows: list, cls: str = "") -> str:
    h = "".join("<th>" + str(x) + "</th>" for x in head)
    b = "".join("<tr>" + "".join("<td>" + str(c) + "</td>" for c in r)
                + "</tr>" for r in rows)
    return ('<div class="scroll"><table class="' + cls + '"><thead><tr>'
            + h + "</tr></thead><tbody>" + b + "</tbody></table></div>")


def pc(v, fmt="%+.2f"):
    s = fmt % v
    k = "pos" if v > 0 else ("neg" if v < 0 else "")
    return '<span class="' + k + '">' + s + "</span>"


def pcm(v: float) -> str:
    """Renkli para: +1.234 $ (binlik nokta). %-formatı ',' bayrağını almaz."""
    s = format(v, "+,.0f").replace(",", ".") + " $"
    k = "pos" if v > 0 else ("neg" if v < 0 else "")
    return '<span class="' + k + '">' + s + "</span>"


def build() -> str:
    from streak_analysis import monthly, streaks as find_streaks
    d = load()
    tp, sl, be = d[d.reason == "tp"], d[d.reason == "sl"], d[d.reason == "be"]
    m = monthly(d)
    sp = find_streaks(m, 2)

    # ── ayrım gücü ──────────────────────────────────────────────────────
    feats = [c for c in d.columns
             if any(c.startswith(p) for p in ("m5_", "m15_", "h1_", "h4_", "d1_"))]
    ent = []
    for c in feats:
        v = cohen(tp[c], sl[c])
        if v == v:
            ent.append((c, tp[c].replace([np.inf, -np.inf], np.nan).mean(),
                        sl[c].replace([np.inf, -np.inf], np.nan).mean(), v))
    ent.sort(key=lambda t: -abs(t[3]))
    path = [(c, tp[c].mean(), sl[c].mean(), cohen(tp[c], sl[c]))
            for c in ("mfe", "mae", "dur_h")]
    path.sort(key=lambda t: -abs(t[3]))

    P = {}
    P["genel"] = ("%d işlem · TP <b>%d</b> · SL <b>%d</b> · BE <b>%d</b> · "
                  "kazanma oranı %%%.1f · profit factor %.2f"
                  % (len(d), len(tp), len(sl), len(be),
                     100 * (d.r > 0).mean(),
                     d[d.r > 0].r.sum() / -d[d.r <= 0].r.sum()))

    # ── grafikler ───────────────────────────────────────────────────────
    P["ch_rdist"] = ch_rdist(d)
    P["ch_path"] = ch_path(d)
    P["ch_cohen"] = ch_cohen(path + ent)
    P["ch_vol"] = ch_vol(d)
    P["ch_dur"] = ch_dur(d)
    P["ch_month"] = ch_month(d, sp)

    # ── TP anatomisi ────────────────────────────────────────────────────
    mae_b = [(0, .25), (.25, .5), (.5, .75), (.75, 1.01)]
    P["tp_mae"] = tbl(
        ["MAE aralığı (stopa yaklaşma)", "TP sayısı", "Pay"],
        [["%.2f – %.2f R" % (a, b),
          int(((tp.mae >= a) & (tp.mae < b)).sum()),
          "%%%.0f" % (100 * ((tp.mae >= a) & (tp.mae < b)).mean())]
         for a, b in mae_b])
    P["tp_strat"] = tbl(
        ["Strateji", "İşlem", "TP", "SL", "BE", "Kazanma", "Ort. kazanç",
         "Ort. kayıp", "Toplam R"],
        [[s, len(g), int((g.reason == "tp").sum()), int((g.reason == "sl").sum()),
          int((g.reason == "be").sum()), "%%%.1f" % (100 * (g.r > 0).mean()),
          pc(g[g.r > 0].r.mean(), "%+.2fR"), pc(g[g.r <= 0].r.mean(), "%+.2fR"),
          pc(g.r.sum(), "%+.1fR")]
         for s, g in d.groupby("s")])

    # ── SL tipolojisi ───────────────────────────────────────────────────
    typo = [("Hiç kâra geçmeden öldü", sl.mfe < 0.25,
             "Sinyal daha başında yanlıştı — fiyat POI'den hiç dönmedi."),
            ("0.25–1R gördü, geri verdi", (sl.mfe >= 0.25) & (sl.mfe < 1),
             "Tepki geldi ama takip yoktu; en sık ölüm şekli."),
            ("1R+ gördü, geri verdi", (sl.mfe >= 1) & (sl.mfe < 2),
             "İşlem çalışmaya başlamıştı, trend devam etmedi."),
            ("2R+ gördü, geri verdi", sl.mfe >= 2,
             "En canını sıkan grup — hedefin yarısına gidip döndü.")]
    P["sl_typo"] = tbl(
        ["Ölüm şekli", "Adet", "Pay", "Ne anlama geliyor"],
        [[n, int(msk.sum()), "%%%.0f" % (100 * msk.mean()), txt]
         for n, msk, txt in typo])

    # ── ayrım tabloları ─────────────────────────────────────────────────
    P["t_path"] = tbl(
        ["Gösterge", "TP ortalaması", "SL ortalaması", "Cohen d", "Yorum"],
        [[{"mfe": "MFE (lehte en yüksek)", "mae": "MAE (aleyhte en derin)",
           "dur_h": "Süre (saat)"}[c],
          "%.2f" % a, "%.2f" % b, "<b>%+.2f</b>" % v,
          "devasa" if abs(v) > 1.5 else "orta"]
         for c, a, b, v in path])
    P["t_ent"] = tbl(
        ["Gösterge", "Zaman dilimi", "TP ort.", "SL ort.", "Cohen d"],
        [[c.split("_", 1)[1], TFS.get(c.split("_")[0], ""),
          "%.2f" % a, "%.2f" % b, "%+.3f" % v] for c, a, b, v in ent[:12]])

    # ── volatilite ──────────────────────────────────────────────────────
    dv = d.copy()
    dv["vb"] = pd.qcut(dv.d1_atrp, 4,
                       labels=["çok düşük", "düşük", "yüksek", "çok yüksek"])
    g = dv.groupby("vb", observed=True)
    P["t_vol"] = tbl(
        ["ATR% çeyreği", "1G ATR% aralığı", "İşlem", "TP", "SL", "Kazanma",
         "Toplam R", "Payı"],
        [[str(k), "%.2f – %.2f" % (x.d1_atrp.min(), x.d1_atrp.max()), len(x),
          int((x.reason == "tp").sum()), int((x.reason == "sl").sum()),
          "%%%.1f" % (100 * (x.r > 0).mean()), pc(x.r.sum(), "%+.1fR"),
          "%%%.0f" % (100 * x.r.sum() / d.r.sum())] for k, x in g])

    # ── saat ────────────────────────────────────────────────────────────
    hb = pd.cut(d.hour, [-1, 7, 11, 15, 19, 23],
                labels=["00–07", "08–11", "12–15", "16–19", "20–23"])
    P["t_hour"] = tbl(
        ["Saat (UTC)", "İşlem", "Kazanma", "Toplam R", "Not"],
        [[str(k), len(x), "%%%.1f" % (100 * (x.r > 0).mean()),
          pc(x.r.sum(), "%+.1fR"),
          "09–11 UTC bloke (blackout_hours)" if str(k) == "08–11" else
          "sistemin en verimsiz penceresi" if str(k) == "16–19" else ""]
         for k, x in d.groupby(hb, observed=True)])

    # ── rejim ───────────────────────────────────────────────────────────
    try:
        rej = pd.read_csv(OUT / "ay_rejim.csv", index_col=0)
        gg = rej.groupby("rej")
        P["t_rej"] = tbl(
            ["Rejim", "Ay", "Pozitif ay", "İşlem", "Stop oranı", "Toplam R"],
            [[k, len(x), "%%%.0f" % (100 * (x.R > 0).mean()), int(x.n.sum()),
              "%%%.0f" % (100 * x.sl.sum() / max(x.n.sum(), 1)),
              pc(x.R.sum(), "%+.1fR")] for k, x in gg])
    except Exception:
        P["t_rej"] = "<p class='note'>reports/ay_rejim.csv bulunamadı.</p>"

    # ── seriler ─────────────────────────────────────────────────────────
    srows = []
    for a, b in sorted(sp, key=lambda t: m.loc[t[0]:t[1]].pnl.sum()):
        seg = m.loc[a:b]
        tr = d[(d.ym >= a) & (d.ym <= b)]
        srows.append([str(a) + " → " + str(b), len(seg), int(seg.n.sum()),
                      pc(seg.R.sum(), "%+.1fR"),
                      pcm(seg.pnl.sum()),
                      "%%%.0f" % (100 * (tr.r > 0).mean()),
                      "%.2f" % tr.d1_atrp.mean()])
    P["t_streak"] = tbl(["Seri", "Ay", "İşlem", "R", "PnL", "Kazanma",
                         "Ort. 1G ATR%"], srows)

    allx = pd.concat([d[(d.ym >= a) & (d.ym <= b)] for a, b in sp])
    solo_m = [p for p in m.index if m.loc[p, "R"] < 0
              and not any(a <= p <= b for a, b in sp)]
    solo = d[d.ym.isin(solo_m)]
    good = d[~d.index.isin(allx.index) & ~d.index.isin(solo.index)]
    P["t_modes"] = tbl(
        ["Grup", "İşlem", "Kazanma", "1G ATR%", "Ort. MFE", "Ort. süre",
         "Ort. MAE"],
        [[n, len(x), "%%%.0f" % (100 * (x.r > 0).mean()),
          "<b>%.2f</b>" % x.d1_atrp.mean(), "%.2f R" % x.mfe.mean(),
          "%.0f saat" % x.dur_h.mean(), "%.2f R" % x.mae.mean()]
         for n, x in [("Zarar serileri (art arda)", allx),
                      ("Tek-ay zararlar", solo), ("Kârlı aylar", good)]])

    # ── sayısal metin parçaları ─────────────────────────────────────────
    P["tp_mae_pct"] = "%.0f" % (100 * (tp.mae < 0.5).mean())
    P["tp_med"] = "%.0f" % tp.dur_h.median()
    P["sl_med"] = "%.0f" % sl.dur_h.median()
    P["sl_giveback"] = "%.0f" % (100 * (sl.mfe >= 1).mean())
    P["sl_never"] = "%.0f" % (100 * (sl.mfe < 0.25).mean())
    P["best_ent"] = "%s (%s), d=%+.2f" % (ent[0][0].split("_", 1)[1],
                                          TFS.get(ent[0][0].split("_")[0], ""),
                                          ent[0][3])
    P["vol_top"] = "%+.1f" % dv[dv.vb == "çok düşük"].r.sum()
    P["vol_bot"] = "%+.1f" % dv[dv.vb == "çok yüksek"].r.sum()
    P["fin"] = format(d.bal.iloc[-1], ",.0f").replace(",", ".")

    out = TPL
    for k, v in P.items():
        out = out.replace("@@" + k + "@@", str(v))
    return out


TPL = r"""<meta charset="utf-8">
<title>TP/SL Anatomisi ve Okuma Kılavuzu</title>
<style>
:root{
  --bg:#fbfaf8;--panel:#fff;--ink:#1c1a17;--dim:#6f6963;--line:#e7e2db;
  --gold:#9a7c18;--pos:#1e7d52;--neg:#c0384a;--shade:#f4f1ea;--quote:#fdf8e8;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0f1217;--panel:#171b22;--ink:#e9e6e1;--dim:#8b9199;--line:#252b34;
  --gold:#d8b23f;--pos:#3fbd80;--neg:#e8607a;--shade:#1b2029;--quote:#1e1c14;}}
:root[data-theme=dark]{
  --bg:#0f1217;--panel:#171b22;--ink:#e9e6e1;--dim:#8b9199;--line:#252b34;
  --gold:#d8b23f;--pos:#3fbd80;--neg:#e8607a;--shade:#1b2029;--quote:#1e1c14;}
:root[data-theme=light]{
  --bg:#fbfaf8;--panel:#fff;--ink:#1c1a17;--dim:#6f6963;--line:#e7e2db;
  --gold:#9a7c18;--pos:#1e7d52;--neg:#c0384a;--shade:#f4f1ea;--quote:#fdf8e8;}

*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
 -webkit-font-smoothing:antialiased}
.wrap{max-width:1000px;margin:0 auto;padding:48px 22px 90px;
 display:flex;flex-direction:column;gap:42px}
header{border-bottom:2px solid var(--gold);padding-bottom:20px}
h1{margin:0 0 6px;font:600 33px/1.15 Georgia,"Times New Roman",serif;
 letter-spacing:-.015em;text-wrap:balance}
.lede{color:var(--dim);font-size:14px}
section{display:flex;flex-direction:column;gap:14px}
h2{margin:0;font:600 21px/1.25 Georgia,serif;padding-bottom:9px;
 border-bottom:1px solid var(--line);text-wrap:balance}
h2 .no{color:var(--gold);font-size:14px;margin-right:9px;
 font-family:ui-monospace,monospace}
h3{margin:14px 0 0;font:600 15px/1.3 Georgia,serif;color:var(--gold)}
p{margin:0}
.note{color:var(--dim);font-size:13px}
.key{background:var(--quote);border-left:3px solid var(--gold);
 padding:14px 18px;border-radius:0 4px 4px 0}
.key b{color:var(--gold)}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));
 gap:1px;background:var(--line);border:1px solid var(--line);border-radius:6px;
 overflow:hidden}
.cell{background:var(--panel);padding:14px 16px}
.cell .k{font-size:11px;letter-spacing:.05em;text-transform:uppercase;
 color:var(--dim);display:block;margin-bottom:5px}
.cell .v{font:600 19px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;
 font-variant-numeric:tabular-nums}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:6px;
 background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:13.5px;min-width:520px}
th,td{padding:8px 13px;text-align:left;border-bottom:1px solid var(--line)}
thead th{background:var(--panel);color:var(--dim);font-size:11px;
 letter-spacing:.05em;text-transform:uppercase;font-weight:600;
 border-bottom:1px solid var(--gold);white-space:nowrap}
td:nth-child(n+2){font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
 font-variant-numeric:tabular-nums;white-space:nowrap}
td:last-child{font-family:inherit;white-space:normal}
tbody tr:hover td{background:var(--shade)}
.pos{color:var(--pos);font-weight:600}.neg{color:var(--neg);font-weight:600}
img{width:100%;height:auto;display:block;border-radius:6px}
ul{margin:0;padding-left:20px}li{margin:5px 0}
footer{color:var(--dim);font-size:12.5px;border-top:1px solid var(--line);
 padding-top:18px}
</style>
<div class="wrap">

<header>
  <h1>TP/SL Anatomisi ve Okuma Kılavuzu</h1>
  <div class="lede">XAUUSD · 5 yıl · @@genel@@ · komisyon-spread-slippage dahil ·
    10.000 $ → @@fin@@ $</div>
</header>

<section>
  <h2><span class="no">00</span>Tek cümlelik cevap</h2>
  <div class="key">
    <b>Giriş anındaki hiçbir gösterge TP ile SL'i ayırt etmiyor.</b>
    Test edilen 35 gösterge içinde en güçlüsü @@best_ent@@ — istatistikte
    "zayıf" sayılan seviye. Ayrımın tamamı işlemin <b>yolunda</b>:
    TP olanlar stopa hiç yaklaşmadan gidiyor, SL olanlar daha ilk saatlerde
    dibi görüyor. Yani sistem <b>hangi işlemin kazanacağını seçemiyor</b>;
    kârı, kazananları uzun taşıyıp kaybedenleri hızlı kesmekten çıkarıyor.
  </div>
  <img src="data:image/png;base64,@@ch_rdist@@" alt="R dağılımı">
  <p class="note">Sonuç dağılımı iki kutuplu: 111 işlem ≈ −1.1R'de (stop +
    komisyon), 45 işlem 4–6R'de (1:5 hedefler), 29 işlem 0.3–2R'de
    (threevol'ün 1:2 hedefi). 2–4R kovası tamamen boş — çünkü hiçbir
    strateji oraya nişan almıyor.</p>
</section>

<section>
  <h2><span class="no">01</span>TP'ler neden TP oluyor</h2>
  <p>TP'ye giden işlemlerin ortak özelliği <b>acı çekmemeleri</b>.
    %@@tp_mae_pct@@'i stop mesafesinin yarısını dahi görmüyor.</p>
  @@tp_mae@@
  <div class="key">Bir işlem girişten sonra stopun yarısını geçtiyse,
    TP'ye gitme ihtimali hızla düşüyor. <b>Erken acı = kötü işaret.</b>
    Ama bu bilgi işe yaramaz bir uyarı değil — aksine, mekanik olarak
    kullanmayı denedim ve <b>çalışmadı</b> (bkz. bölüm 07): kazananların
    %39'u da 0.5R'den derin geri çekilme yaşıyor.</div>
  <h3>Süre: kazanan sabır ister</h3>
  <p>TP'lerin medyan süresi <b>@@tp_med@@ saat</b>, SL'lerin
    <b>@@sl_med@@ saat</b>. Kazananlar günlerce, bazen haftalarca açık
    kalıyor. Bu tesadüf değil: 1:5 hedefe ulaşmak zaman ister.</p>
  <img src="data:image/png;base64,@@ch_dur@@" alt="Süre dağılımı">
  <h3>Strateji bazında</h3>
  @@tp_strat@@
  <p class="note">threevol farklı bir hayvan: 1:2 hedefle çalışır, ortalama
    kazancı 1.71R, buna karşılık BE çıkışları var. Diğer üçü 1:5 hedefli,
    ortalama kazanç ~4.9R.</p>
</section>

<section>
  <h2><span class="no">02</span>SL'ler neden SL oluyor</h2>
  <p>Stopların hepsi aynı sebeple olmuyor. Dört ayrı ölüm şekli var:</p>
  @@sl_typo@@
  <div class="key">Stopların <b>%@@sl_never@@'u</b> hiç kâra geçmeden ölüyor —
    bunlar sinyalin baştan yanlış olduğu işlemler. Buna karşılık
    <b>%@@sl_giveback@@'ü</b> en az 1R kâr görüp geri veriyor. İkinci grup
    en sinir bozucu olanı ve <b>breakeven mekanizmasının çözmesi gereken
    şey gibi görünüyor</b> — ama 60 backtest bunun yanlış olduğunu gösterdi
    (bölüm 07).</div>
  <h3>Yol haritası: MFE ve MAE birlikte</h3>
  <img src="data:image/png;base64,@@ch_path@@" alt="MFE-MAE dağılımı">
  <p class="note">Yatay eksen işlemin ne kadar acı çektiği, dikey eksen ne
    kadar kâr gördüğü. Yeşiller (TP) sol üstte kümeleniyor: az acı, çok kâr.
    Kırmızılar (SL) sağ altta: çok acı, az kâr. Ama <b>iki bulut arasında
    geniş bir örtüşme var</b> — ayrım net değil, ve bu örtüşme her mekanik
    kuralın neden başarısız olduğunu açıklıyor.</p>
</section>

<section>
  <h2><span class="no">03</span>Gerçekte ne ayırt ediyor</h2>
  <p>Aynı ölçüyle (Cohen d) hem giriş göstergelerini hem yol göstergelerini
    karşılaştırdım. Sonuç çarpıcı:</p>
  <img src="data:image/png;base64,@@ch_cohen@@" alt="Ayrım gücü">
  <h3>Yol göstergeleri — devasa ayrım</h3>
  @@t_path@@
  <h3>Giriş göstergeleri — en güçlü 12'si bile zayıf</h3>
  @@t_ent@@
  <div class="key">Cohen d yorumu: <b>0.2 zayıf, 0.5 orta, 0.8 güçlü.</b>
    Giriş göstergelerinin en iyisi 0.38'de kalıyor — yani TP ve SL
    popülasyonları giriş anında neredeyse <b>ayırt edilemez</b>. Yol
    göstergeleri ise 2.0–3.0 aralığında, yani tamamen ayrı popülasyonlar.
    Ama yol göstergeleri işlem <b>başladıktan sonra</b> oluşur — girişte
    bilinmezler. İşte sistemin temel kısıtı bu.</div>
</section>

<section>
  <h2><span class="no">04</span>Volatilite — ne anlama geliyor, nasıl okunur</h2>
  <img src="data:image/png;base64,@@ch_vol@@" alt="Volatilite çeyrekleri">
  @@t_vol@@
  <div class="key">İlişki <b>tek yönlü ve temiz</b>: volatilite arttıkça
    getiri düşüyor. En düşük ATR çeyreği @@vol_top@@R, en yüksek çeyrek
    @@vol_bot@@R — <b>toplam kârın yarısından fazlası en sakin çeyrekten
    geliyor</b>.</div>
  <h3>Neden böyle</h3>
  <ul>
    <li><b>Stop mesafesi yapısal, volatilite değil.</b> Stoplar swing
      noktalarına konuyor. Volatilite patladığında fiyat aynı swing'i çok
      daha hızlı geçiyor — stop, olayın gürültüsüne yakalanıyor.</li>
    <li><b>Yüksek volatilite yön demek değil.</b> Rapordaki en pahalı
      seriler yüksek ATR'de oluştu (bölüm 06); fiyat çok hareket etti ama
      hiçbir yere gitmedi.</li>
    <li><b>Komisyon etkisi sabit değil.</b> Ücret notional ile ölçeklenir,
      risk stop mesafesiyle. Volatilitede stop genişlerse R başına ücret
      düşer — bu tek olumlu etki, ama yeterli değil.</li>
  </ul>
  <div class="key"><b>Nasıl okumalı:</b> ATR yüksekken sistemin beklenen
    getirisi düşer ama <b>negatife dönmez</b> (en kötü çeyrek bile
    @@vol_bot@@R). Bu yüzden "yüksek volatilitede işlem yapma" kuralı
    <b>zarar ettirir</b> — test edildi. Doğru okuma: yüksek ATR döneminde
    <b>daha az kâr bekle</b>, panikleme.</div>
</section>

<section>
  <h2><span class="no">05</span>Trend ve rejim — ne anlama geliyor</h2>
  @@t_rej@@
  <div class="key"><b>Stop oranı her rejimde neredeyse aynı: %48–57.</b>
    Boğa, ayı, yatay — fark yok. Ve <b>her rejim kârlı</b>. En kötü aylar
    her rejimden geliyor: 2026-03 güçlü ayı (−6.9R), 2022-11 temiz boğa
    (−5.7R), 2025-06 yatay (−8.5R).</div>
  <p><b>Yani "yatay piyasada zarar ediyoruz" doğru değil.</b> Yatay aylar
    27 ayın toplamında +49.2R getirdi. Rejim, sonucun açıklayıcısı değil.</p>
  <h3>Saat penceresi — rejimden daha açıklayıcı</h3>
  @@t_hour@@
  <div class="key"><b>Nasıl okumalı:</b> trend yönünü işlem <i>filtresi</i>
    olarak kullanma denemesi dört kez yapıldı (ADX, MACD, MTF hizalama,
    SMA200 uyumu) ve dördü de para kaybettirdi. Trend, sistemin
    <b>zaten uyguladığı</b> SMA200 kapısıyla hesaba katılıyor; üzerine
    eklenen her kat, kötü aylardaki büyük kazananları da kesiyor.</div>
</section>

<section>
  <h2><span class="no">06</span>Üst üste zarar eden aylar</h2>
  <img src="data:image/png;base64,@@ch_month@@" alt="Aylık PnL ve seriler">
  @@t_streak@@
  <h3>İki ayrı ölüm şekli</h3>
  @@t_modes@@
  <div class="key">Zarar serileri <b>yüksek</b> volatilitede oluşuyor
    (ATR% 2.00), tek-ay zararlar <b>düşük</b> volatilitede (0.96). Kârlı
    aylar ikisinin arasında (1.29). <b>Bunlar aynı olgu değil</b> ve aynı
    çareyi kabul etmezler.</div>
  <ul>
    <li><b>Seri ölümü (yüksek volatilite):</b> fiyat sert hareket eder ama
      tutarsız. İşlemler ortalama 51 saatte ölür (kârlı aylarda 128 saat).
      Sistem daha pozisyonu kurmadan biçilir.</li>
    <li><b>Tek-ay ölümü (düşük volatilite):</b> klasik akümülasyon. Fiyat
      hiçbir yere gitmez, hedefe ulaşacak hareket oluşmaz.</li>
  </ul>
  <p>Seri <b>uzunluğu maliyetle ilişkili değil</b>: 4 aylık seri yalnız
    −1.145 $, 3 aylık seri −3.047 $. Belirleyici olan işlem sayısı — uzun
    ama seyrek seri ucuz, kısa ama yoğun seri pahalı.</p>
</section>

<section>
  <h2><span class="no">07</span>Denenip elenen mekanizmalar</h2>
  <p>Bu raporda tarif edilen her zaafı kapatmak için mekanizma test edildi.
    Kural: IS (ilk %70) ve OOS (son %30) dilimlerinde <b>birlikte</b>
    iyileştirmeyen aday elenir.</p>
  <ul>
    <li><b>Breakeven ailesi — 60 backtest, tamamı elendi.</b> "SL'lerin
      %34'ü 1R+ görüp geri veriyor" bulgusundan yola çıkıldı. Kaba simülasyon
      +61R vaat etti, gerçek −16R çıktı. Sebep: o 1R'yi gören işlemlerin
      çoğu 5R'ye gidecek kazananlardı. harmonic BE@1.0 → +41.4R'den +7.3R'ye
      düştü.</li>
    <li><b>Giriş filtreleri — 25 aday, tamamı elendi.</b> Yön-göreli MTF
      hizalama (−11R … −95R), ADX kapısı, MACD kapısı, SMA200 geçiş
      tespiti (en iyisi −7.4R).</li>
    <li><b>Volatilite filtresi.</b> En kötü ATR çeyreği bile pozitif
      (@@vol_bot@@R) olduğu için dışlamak doğrudan zarar.</li>
    <li><b>Devre kesiciler</b> (aylık, ardışık kayıp), <b>kısmi TP</b>
      (tüm varyantlar), <b>takip eden stop</b>, <b>zaman stopu</b>,
      <b>dar stop reddi</b>.</li>
  </ul>
  <div class="key">Toplam <b>85 mekanizma varyantı</b> ölçüldü, hiçbiri
    kabul edilmedi. Ortak sebep hep aynı: aylık/rejim düzeyinde güçlü
    görünen her ayrım <b>işlem seviyesine inmiyor</b>. Kötü aylarda da
    5R'ye giden büyük kazananlar var ve her filtre onları da kesiyor.</div>
</section>

<section>
  <h2><span class="no">08</span>Pratik okuma kılavuzu</h2>
  <div class="grid2">
    <div class="cell"><span class="k">İşlem açıldı, ilk saatler</span>
      <span class="v">MAE &lt; 0.5R</span></div>
    <div class="cell"><span class="k">TP'lerin bu bandındaki payı</span>
      <span class="v">%@@tp_mae_pct@@</span></div>
    <div class="cell"><span class="k">TP medyan süre</span>
      <span class="v">@@tp_med@@ saat</span></div>
    <div class="cell"><span class="k">SL medyan süre</span>
      <span class="v">@@sl_med@@ saat</span></div>
  </div>
  <ul>
    <li><b>Bir işlem 3 günü geçtiyse muhtemelen kazanacaktır.</b> SL'lerin
      medyanı @@sl_med@@ saat; uzun yaşayan işlem genelde çalışan işlemdir.
      Bu bir kural değil, beklenti ayarıdır.</li>
    <li><b>Erken derin acı kötüye işarettir ama kesin değildir.</b>
      Kazananların %39'u da 0.5R'yi aşan geri çekilme yaşıyor. Bu yüzden
      erken müdahale (BE, takip eden stop) sistemi bozuyor.</li>
    <li><b>Yüksek ATR döneminde daha az kâr bekle.</b> Kâr durmuyor, hızı
      düşüyor. En yüksek çeyrek yine de @@vol_bot@@R.</li>
    <li><b>Art arda 2–4 zarar ayı normaldir.</b> 5 yılda 4 kez oldu, en
      uzunu 4 ay. Hiçbiri sistemi bozmadı; hepsinden trend hareketiyle
      çıkıldı, sistem kendini düzeltmek için bir şey yapmadı.</li>
    <li><b>Kazanma oranı %35 olacak.</b> Bu bir kusur değil, 1:5 hedefin
      matematiksel sonucu. Üst üste 5–6 stop görmek beklenen davranıştır.</li>
    <li><b>Rejime bakıp sistemi durdurma.</b> Boğa, ayı, yatay — üçü de
      kârlı, stop oranları aynı. Rejim okuması beklenti içindir, karar
      için değil.</li>
  </ul>
</section>

<footer>
  <b>Kaynak:</b> reports/ay_derin_islemler.csv — config/default.json
  preset'leriyle koşulan tam defter (fvg RR 1:5 · harmonic RR 1:5 ·
  threevol RR 1:2be · fib RR 1:5).<br>
  <b>Maliyetler:</b> spread 0,30 $, slippage 0,05 $, BingX VIP 0 ücretleri
  (taker %0,0500 / maker %0,0200) işlem başına bir kez düşülmüştür.<br>
  <b>Ölçüm:</b> Cohen d = iki grubun ortalama farkı / ortak standart sapma.
  IS/OOS ayrımı 2025-01-11 (ilk %70 / son %30).<br>
  <b>Üretici:</b> scripts/tp_sl_anatomy.py
</footer>
</div>
"""


if __name__ == "__main__":
    p = OUT / "TP_SL_ANATOMI.html"
    p.write_text(build(), encoding="utf-8")
    print("Rapor → %s (%.2f MB)" % (p, p.stat().st_size / 1e6))
    print("BITTI")
