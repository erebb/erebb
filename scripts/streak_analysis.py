# -*- coding: utf-8 -*-
"""
ZARAR SERİLERİ ANALİZİ — arka arkaya kaybedilen aylar
======================================================
Sorular:
  • 4 ay üst üste kaybettiği yer (2023-05→08) neden oldu? İşlemler neden stop?
  • "bir kaybet → ÇOK kaybet → bir daha kaybet" deseni (2026-02→04,
    2025-05→06, 2022-10→11) hangi piyasa koşulunda çıkıyor?
  • Serilerin ORTAK PAYDASI ne? Tek aylık zararlardan farkı var mı?
  • Seriden nasıl çıkılmış — toparlanma neye bağlı?

Grafik/tablo altyapısı scripts/month_deepdive.py'den yeniden kullanılır.
Defter reports/ay_derin_islemler.csv'den okunur (backtest KOŞULMAZ).

Çıktı: reports/ZARAR_SERILERI.html
Kullanım: python3 scripts/streak_analysis.py
"""

from __future__ import annotations

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
CAPITAL = 10_000.0


def mny(v: float, sign: bool = True) -> str:
    """1.234 / +1.234 biçimi. %-formatı ',' bayrağını desteklemez."""
    return format(v, "+,.0f" if sign else ",.0f").replace(",", ".")


# ─────────────────────────────── defter ─────────────────────────────────────

def ledger() -> pd.DataFrame:
    d = pd.read_csv(OUT / "ay_derin_islemler.csv")
    d["entry"] = pd.to_datetime(d["entry"])
    d["exit"] = pd.to_datetime(d["exit"])
    d = d[d["reason"] != "open"].sort_values("exit").reset_index(drop=True)
    bal = CAPITAL
    pn, bl = [], []
    for r in d["r"]:
        p = 0.01 * bal * r
        bal += p
        pn.append(p)
        bl.append(bal)
    d["pnl"], d["bal"] = pn, bl
    d["ym"] = d["exit"].dt.to_period("M")
    return d


def monthly(d: pd.DataFrame) -> pd.DataFrame:
    m = d.groupby("ym").agg(n=("r", "size"), R=("r", "sum"), pnl=("pnl", "sum"),
                            bal=("bal", "last"))
    full = pd.period_range(m.index.min(), m.index.max(), freq="M")
    m = m.reindex(full)
    m[["n", "R", "pnl"]] = m[["n", "R", "pnl"]].fillna(0.0)
    m["bal"] = m["bal"].ffill()
    return m


def streaks(m: pd.DataFrame, min_len: int = 2) -> list[tuple]:
    """Ardışık negatif ay serileri → [(başlangıç_period, bitiş_period), ...]"""
    neg = (m["R"] < 0).tolist()
    out, s = [], None
    for i, v in enumerate(neg):
        if v and s is None:
            s = i
        if not v and s is not None:
            out.append((s, i - 1))
            s = None
    if s is not None:
        out.append((s, len(neg) - 1))
    return [(m.index[a], m.index[b]) for a, b in out if b - a + 1 >= min_len]


# ─────────────────────────────── grafik ─────────────────────────────────────

def streak_chart(dd: pd.DataFrame, tr: pd.DataFrame, p0, p1, title: str) -> str:
    from month_deepdive import b64
    lo = pd.Timestamp(p0.start_time) - pd.Timedelta(days=25)
    hi = pd.Timestamp(p1.end_time) + pd.Timedelta(days=25)
    w = dd[(dd.index >= lo) & (dd.index <= hi)]
    if len(w) < 3:
        return ""
    fig, ax = plt.subplots(3, 1, figsize=(13.5, 9.4), sharex=True,
                           gridspec_kw={"height_ratios": [3, 1.2, 1.2]},
                           facecolor="#12161c")
    for a in ax:
        a.set_facecolor("#12161c")
        a.tick_params(colors="#9fb0c4", labelsize=8)
        for sp in a.spines.values():
            sp.set_color("#2a3542")
        a.grid(alpha=0.15, color="#3a4552")
        # seri penceresini gölgele
        a.axvspan(pd.Timestamp(p0.start_time), pd.Timestamp(p1.end_time),
                  color="#ef5350", alpha=0.07)

    up = w.Close >= w.Open
    ax[0].vlines(w.index, w.Low, w.High, color="#7c8896", lw=0.8)
    ax[0].vlines(w.index[up], w.Open[up], w.Close[up], color="#26a69a", lw=3.4)
    ax[0].vlines(w.index[~up], w.Open[~up], w.Close[~up], color="#ef5350", lw=3.4)
    for col, cl, lb in [("ema20", "#f5c542", "EMA20"),
                        ("ema50", "#4C78A8", "EMA50"),
                        ("ema200", "#B279A2", "EMA200")]:
        ax[0].plot(w.index, w[col], lw=1.2, color=cl, label=lb)
    for i, t in enumerate(tr.itertuples(), 1):
        col = "#26a69a" if t.r > 0 else "#ef5350"
        ax[0].scatter(t.entry, t.px, marker="^" if t.dir == "bull" else "v",
                      s=125, color=col, edgecolors="white", linewidths=1, zorder=6)
        ax[0].annotate(str(i), (t.entry, t.px), color="white", fontsize=8,
                       weight="bold", xytext=(4, 6), textcoords="offset points")
    ax[0].set_title(title, color="#e6edf5", fontsize=12)
    ax[0].set_ylabel("Fiyat $", color="#9fb0c4")
    ax[0].legend(fontsize=8, facecolor="#1a222c", labelcolor="#9fb0c4")

    ax[1].bar(w.index, w["hist"],
              color=np.where(w["hist"] >= 0, "#26a69a", "#ef5350"))
    ax[1].plot(w.index, w["macd"], lw=1.2, color="#4C78A8", label="MACD")
    ax[1].plot(w.index, w["sig"], lw=1.2, color="#f5c542", label="Sinyal")
    ax[1].axhline(0, color="#7c8896", lw=.7)
    ax[1].set_ylabel("MACD (1G)", color="#9fb0c4")
    ax[1].legend(fontsize=7, facecolor="#1a222c", labelcolor="#9fb0c4")

    ax[2].plot(w.index, w["atrp"], lw=1.3, color="#E45756", label="ATR14 %")
    ax[2].plot(w.index, w["bbw"], lw=1.1, color="#B279A2", ls="--",
               label="BB genişliği %")
    ax[2].set_ylabel("Volatilite", color="#9fb0c4")
    ax[2].legend(fontsize=7, facecolor="#1a222c", labelcolor="#9fb0c4")
    ax[2].xaxis.set_major_formatter(mdates.DateFormatter("%d %b %y"))
    fig.tight_layout()
    return b64(fig)


def equity_chart(d: pd.DataFrame, spans: list[tuple]) -> str:
    from month_deepdive import b64
    fig, ax = plt.subplots(figsize=(13.5, 3.4), facecolor="#12161c")
    ax.set_facecolor("#12161c")
    ax.plot(d["exit"], d["bal"], color="#f5c542", lw=1.7)
    for p0, p1 in spans:
        ax.axvspan(pd.Timestamp(p0.start_time), pd.Timestamp(p1.end_time),
                   color="#ef5350", alpha=0.18)
    ax.axhline(CAPITAL, color="#7c8896", lw=.8, ls="--")
    ax.set_ylabel("Bakiye $", color="#9fb0c4")
    ax.set_title("Özkaynak eğrisi — kırmızı bantlar zarar serileri",
                 color="#e6edf5", fontsize=11)
    ax.tick_params(colors="#9fb0c4", labelsize=8)
    for sp in ax.spines.values():
        sp.set_color("#2a3542")
    ax.grid(alpha=0.15, color="#3a4552")
    fig.tight_layout()
    return b64(fig)


# ─────────────────────────────── bölüm ──────────────────────────────────────

def diagnose(tr: pd.DataFrame, dd: pd.DataFrame, p0, p1) -> list[str]:
    """Seriye özgü, veriden türetilen teşhis cümleleri."""
    out = []
    lo, hi = pd.Timestamp(p0.start_time), pd.Timestamp(p1.end_time)
    w = dd[(dd.index >= lo) & (dd.index <= hi)]
    if len(w) > 2:
        chg = 100 * (w.Close.iloc[-1] / w.Close.iloc[0] - 1)
        rng = 100 * (w.High.max() - w.Low.min()) / w.Close.iloc[0]
        eff = abs(chg) / rng if rng else 0
        out.append("Fiyat serinin başından sonuna <b>%+.1f%%</b> hareket etti; "
                   "aradaki tepe-dip aralığı <b>%%%.1f</b>. Verimlilik oranı "
                   "<b>%.2f</b> — %s." % (
                       chg, rng, eff,
                       "1'e yakın olsaydı temiz trend olurdu; bu seviye "
                       "testere/yönsüz piyasa demek" if eff < 0.45 else
                       "yön vardı, sorun yönsüzlük değil"))
        out.append("Serideki günlerin <b>%%%.0f</b>'inde günlük MACD sıfır "
                   "bandındaydı (|MACD%%| &lt; 0.5) — momentumun öldüğü aralık."
                   % (100 * (w["macd"].abs() / w.Close * 100 < 0.5).mean()))
    n = len(tr)
    if n:
        lg = int((tr["dir"] == "bull").sum())
        out.append("<b>%d işlem</b>: %d long / %d short. Kazanan <b>%d</b>, "
                   "stop <b>%d</b>, BE <b>%d</b>."
                   % (n, lg, n - lg, int((tr.r > 0).sum()),
                      int((tr.reason == "sl").sum()),
                      int((tr.reason == "be").sum())))
        near = tr[(tr.r <= 0) & (tr.mfe >= 1.0)]
        if len(near):
            out.append("Kaybedenlerin <b>%d</b> tanesi stop olmadan önce "
                       "<b>≥1R</b> kâra gitti (en yükseği %.1fR) — sinyaller "
                       "yanlış değildi, hedefe ulaşacak takip hareketi gelmedi."
                       % (len(near), near.mfe.max()))
        by = tr.groupby("s")["r"].agg(["size", "sum"])
        out.append("Strateji dağılımı: " + " · ".join(
            "<b>%s</b> %d işlem %+.1fR" % (s, r["size"], r["sum"])
            for s, r in by.iterrows()))
        worst = tr.loc[tr.r.idxmin()]
        out.append("En pahalı tek işlem: <b>%s</b> %s girişi %s, %+.2fR "
                   "(%.0f saat açık kaldı)."
                   % (worst.s, "LONG" if worst["dir"] == "bull" else "SHORT",
                      str(worst.entry)[:16], worst.r, worst.dur_h))
    return out


def section(d: pd.DataFrame, m: pd.DataFrame, dd: pd.DataFrame,
            p0, p1, baslik: str) -> str:
    tr = d[(d.ym >= p0) & (d.ym <= p1)].sort_values("entry")
    from month_deepdive import trade_table
    seg = m.loc[p0:p1]
    R, P = seg.R.sum(), seg.pnl.sum()
    bal0 = m["bal"].shift(1).get(p0, CAPITAL)
    h = ['<h2>%s — <span class="n">%+.1fR / %s $</span></h2>'
         % (baslik, R, mny(P))]
    h.append('<div class="kutu kotu"><span class="big">%d ay üst üste</span> · '
             '%d işlem · bakiye <b>%s $</b> → <b>%s $</b> '
             '(<span class="n">%%%.1f</span>)</div>'
             % (len(seg), int(seg.n.sum()), mny(bal0, False),
                mny(seg.bal.iloc[-1], False),
                100 * (seg.bal.iloc[-1] / bal0 - 1)))

    # ay ay kırılım
    rows = "".join(
        '<tr><td>%s</td><td class="%s">%+.1fR</td><td class="%s">%s $</td>'
        '<td>%d</td></tr>'
        % (p, "n" if r.R < 0 else "p", r.R, "n" if r.pnl < 0 else "p",
           mny(r.pnl), int(r.n))
        for p, r in seg.iterrows())
    h.append('<div class="tw"><table><thead><tr><th>Ay</th><th>R</th>'
             '<th>PnL</th><th>İşlem</th></tr></thead><tbody>%s</tbody>'
             '</table></div>' % rows)

    h.append(streak_chart(dd, tr, p0, p1,
                          "%s — günlük mumlar, işlemler numaralı" % baslik))
    h.append("<h3>Teşhis</h3><ul>%s</ul>"
             % "".join("<li>%s</li>" % x for x in diagnose(tr, dd, p0, p1)))
    h.append("<h3>İşlem işlem</h3>")
    h.append(trade_table(tr))

    # seriden çıkış
    nxt = m.index[m.index > p1]
    if len(nxt):
        q = nxt[0]
        r = m.loc[q]
        h.append('<div class="kutu %s"><b>Seriden çıkış:</b> %s ayı '
                 '<span class="%s">%+.1fR / %s $</span> (%d işlem). %s</div>'
                 % ("iyi" if r.R > 0 else "kotu", q, "p" if r.R > 0 else "n",
                    r.R, mny(r.pnl), int(r.n),
                    "Toparlanma tek bir trend hareketinden geldi — sistem "
                    "kendini düzeltmek için hiçbir şey yapmadı, piyasa yön "
                    "verdi." if r.R > 0 else "Toparlanma gecikti."))
    return "".join(h)


# ─────────────────────────────── main ───────────────────────────────────────

def main() -> None:
    from month_deepdive import daily, CSS
    from gui import _load_data

    d = ledger()
    m = monthly(d)
    df_1h, _df5, _ = _load_data()
    dd = daily(df_1h)

    sp = streaks(m, min_len=2)
    sp = sorted(sp, key=lambda t: m.loc[t[0]:t[1]].pnl.sum())   # en pahalı önce
    print("seri sayisi:", len(sp), flush=True)

    parts = ["<h1>Zarar Serileri — Arka Arkaya Kaybedilen Aylar</h1>"]
    parts.append('<p class="note">Kaynak: reports/ay_derin_islemler.csv '
                 '(config/default.json preset\'leri). Tüm rakamlar '
                 'komisyon-spread-slippage dahil. Bakiye bileşik: her işlem '
                 'o anki bakiyenin %1\'ini riske atar.</p>')
    parts.append(equity_chart(d, sp))

    # özet tablo
    rows = ""
    for p0, p1 in sp:
        seg = m.loc[p0:p1]
        rows += ('<tr><td>%s → %s</td><td>%d</td><td class="n">%+.1fR</td>'
                 '<td class="n">%s $</td><td>%d</td></tr>'
                 % (p0, p1, len(seg), seg.R.sum(), mny(seg.pnl.sum()),
                    int(seg.n.sum())))
    parts.append('<h2>Özet</h2><div class="tw"><table><thead><tr><th>Seri</th>'
                 '<th>Ay</th><th>R</th><th>PnL</th><th>İşlem</th></tr></thead>'
                 '<tbody>%s</tbody></table></div>' % rows)

    for p0, p1 in sp:
        n = (p1 - p0).n + 1
        etiket = ("%d AY ÜST ÜSTE" % n) if n >= 3 else "%d AY ÜST ÜSTE" % n
        parts.append(section(d, m, dd, p0, p1,
                             "%s: %s → %s" % (etiket, p0, p1)))
        print("  bolum:", p0, "->", p1, flush=True)

    # ortak payda
    allstreak = pd.concat([d[(d.ym >= a) & (d.ym <= b)] for a, b in sp])
    solo_months = [p for p in m.index if m.loc[p, "R"] < 0
                   and not any(a <= p <= b for a, b in sp)]
    solo = d[d.ym.isin(solo_months)]
    good = d[~d.index.isin(allstreak.index) & ~d.index.isin(solo.index)]
    cmp_rows = ""
    for lbl, x in [("Zarar serileri", allstreak), ("Tek-ay zararlar", solo),
                   ("Kârlı aylar", good)]:
        cmp_rows += ('<tr><td>%s</td><td>%d</td><td>%.0f%%</td><td>%.2f</td>'
                     '<td>%.2f</td><td>%.2f</td><td>%.0f</td><td>%.2f</td></tr>'
                     % (lbl, len(x), 100 * (x.r > 0).mean(),
                        x.d1_macd.abs().mean(), x.d1_atrp.mean(),
                        x.mfe.mean(), x.dur_h.mean(), x.mae.mean()))
    parts.append('<h2>Ortak payda — seriler, tek-ay zararlar ve kârlı aylar</h2>'
                 '<div class="tw"><table><thead><tr><th>Grup</th><th>İşlem</th>'
                 '<th>WR</th><th>|1G MACD%%|</th><th>1G ATR%%</th>'
                 '<th>Ort. MFE</th>'
                 '<th>Ort. süre (s)</th><th>Ort. MAE</th></tr></thead>'
                 '<tbody>%s</tbody></table></div>' % cmp_rows)

    html = ("<!doctype html><meta charset='utf-8'>"
            "<title>Zarar Serileri Analizi</title><style>%s</style>%s"
            % (CSS, "".join(parts)))
    p = OUT / "ZARAR_SERILERI.html"
    p.write_text(html, encoding="utf-8")
    print("Rapor → %s (%.1f MB)" % (p, p.stat().st_size / 1e6))
    print("BITTI")


if __name__ == "__main__":
    main()
