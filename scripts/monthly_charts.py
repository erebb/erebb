# -*- coding: utf-8 -*-
"""
AY AY KAPSAMLI PİYASA + İŞLEM RAPORU
=====================================
Backtest dönemindeki HER ay için tek sayfalık görsel + sayısal dosya üretir:

  Panel 1  Günlük fiyat + EMA20/50/200 + o ayın İŞLEMLERİ (giriş/çıkış, kâr/zarar)
  Panel 2  MACD (günlük): çizgi, sinyal, histogram
  Panel 3  Volatilite: günlük ATR% + 20g gerçekleşen volatilite + Bollinger genişliği
  Panel 4  Hacim + PROXY CVD (kümülatif işaretli hacim)

  Tablo A  ÇOK ZAMAN DİLİMLİ gösterge anlık görüntüsü (5M/15M/1H/4H/1D):
           EMA9/21/50/200 dizilimi, MACD çizgi/sinyal/histogram, RSI14, ATR14
  Tablo B  Ayın işlem istatistikleri (N, WR, R, PnL, strateji kırılımı)
  Not      Bilinen makro olaylar (elle derlenmiş — canlı takvim DEĞİL)

DÜRÜSTLÜK NOTLARI (rapora da basılır):
  • CVD PROXY'dir: veri seti yalnız toplam hacim içerir, alıcı/satıcı (bid/ask)
    ayrımı YOKTUR. Proxy = sign(Close−Open) × Volume kümülatifi. Gerçek
    emir-defteri CVD'si değildir; yön eğilimi göstergesidir.
  • Haber notları modelin bilgisinden elle derlenmiştir, canlı ekonomik takvim
    beslemesi değildir. Eksik/yaklaşık olabilir.

Kullanım:
  python3 scripts/monthly_charts.py                    # tüm aylar
  python3 scripts/monthly_charts.py --from 2025-01     # belirli aydan itibaren
  python3 scripts/monthly_charts.py --trades yol.csv   # işlem dosyası
Çıktı: reports/monthly/aylik_rapor.html (grafikler gömülü, tek dosya)
"""

from __future__ import annotations

import argparse
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
OUT_DIR = ROOT / "reports" / "monthly"

# ── Bilinen makro olaylar (ELLE DERLENMİŞ — canlı takvim değil) ──────────────
NEWS = {
    "2021-08": "Fed taper sinyalleri; reel faizler yükseliyor — altın baskı altında",
    "2021-09": "FOMC taper takvimi netleşiyor; dolar güçlü",
    "2021-11": "ABD TÜFE %6.2 (30 yılın zirvesi) — enflasyon korkusu, altın sıçraması",
    "2021-12": "Fed taper hızlandırma; 2022 için 3 faiz artışı sinyali",
    "2022-02": "RUSYA-UKRAYNA SAVAŞI (24 Şubat) — güvenli liman talebi, altın fırlıyor",
    "2022-03": "Fed ilk artış (+25bp); altın 2070$ zirvesi sonrası geri çekilme",
    "2022-05": "Fed +50bp; dolar endeksi 20 yılın zirvesine yakın",
    "2022-06": "Fed +75bp (1994'ten beri en büyük); altın satışı",
    "2022-09": "Fed +75bp üst üste; DXY 114 — altın 1615$'a dip yaptı",
    "2022-11": "TÜFE beklentinin altında; dolar sert geri çekildi, altın ralli",
    "2023-03": "SVB / Credit Suisse BANKA KRİZİ — güvenli liman, altın 2000$ üstü",
    "2023-05": "ABD borç tavanı krizi; bankacılık stresi sürüyor",
    "2023-07": "Fed son artış (5.25-5.50); 'higher for longer' söylemi",
    "2023-10": "İSRAİL-HAMAS SAVAŞI (7 Ekim) — jeopolitik prim, altın toparlanma",
    "2023-12": "Fed pivot sinyali; 2024 indirim beklentisi — altın rekor bölgesi",
    "2024-03": "Altın YENİ REKOR (2200$+); merkez bankası alımları",
    "2024-04": "Jeopolitik gerilim (İran-İsrail); altın 2400$",
    "2024-08": "Küresel carry-trade çözülmesi (Yen); risk-off",
    "2024-09": "Fed ilk indirim (-50bp); altın rekor tazeliyor",
    "2024-10": "ABD seçim belirsizliği; altın 2790$ zirve",
    "2024-11": "Seçim sonrası dolar rallisi; altın geri çekilme",
    "2025-01": "Yeni yönetim / tarife belirsizliği; altın talebi",
    "2025-02": "Tarife açıklamaları; enflasyon endişesi — altın güçlü",
    "2025-04": "Küresel tarife şoku; volatilite patlaması, altın 3400$+",
    "2025-06": "Orta Doğu gerilimi; güvenli liman",
    "2025-09": "Fed indirim döngüsü; altın 3700$+",
    "2025-10": "Altın 4000$ eşiği — merkez bankası + ETF alımları",
    "2026-01": "Altın 4300$+; enflasyon/faiz belirsizliği sürüyor",
    "2026-03": "Sert geri çekilme — kâr realizasyonu (aylık ~-15%)",
    "2026-04": "Toparlanma; volatilite yüksek",
}


def load_data():
    d = {}
    for tf, f in [("5m", "xauusd_5m.csv"), ("15m", "xauusd_15m.csv"),
                  ("1h", "xauusd_1h.csv"), ("4h", "xauusd_4h.csv")]:
        p = ROOT / f
        if p.exists():
            d[tf] = pd.read_csv(p, index_col=0, parse_dates=True)
    if "1h" not in d:
        sys.exit("HATA: xauusd_1h.csv yok.")
    h = d["1h"]
    d["1d"] = h.resample("1D").agg({"Open": "first", "High": "max", "Low": "min",
                                    "Close": "last", "Volume": "sum"}).dropna(subset=["Close"])
    return d


def ind(df: pd.DataFrame) -> dict:
    """Bir zaman dilimi için EMA/MACD/RSI/ATR/BB."""
    c, h, l = df["Close"], df["High"], df["Low"]
    out = {}
    for p in (9, 21, 20, 50, 200):
        out[f"ema{p}"] = c.ewm(span=p, adjust=False).mean()
    ef, es = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    out["macd"] = ef - es
    out["signal"] = out["macd"].ewm(span=9, adjust=False).mean()
    out["hist"] = out["macd"] - out["signal"]
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    out["rsi"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    out["atr"] = tr.rolling(14).mean()
    ma, sd = c.rolling(20).mean(), c.rolling(20).std()
    out["bbw"] = (4 * sd / ma * 100)
    # PROXY CVD: mum yönüyle işaretlenmiş hacim (gerçek bid/ask CVD DEĞİL)
    if "Volume" in df.columns:
        out["cvd"] = (np.sign(c - df["Open"]) * df["Volume"]).cumsum()
    return out


def b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=85, bbox_inches="tight", facecolor="#12161c")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def month_figure(dd, di, trades_m, ym) -> str:
    """4 panelli aylık grafik."""
    lo = pd.Timestamp(ym.start_time) - pd.Timedelta(days=25)
    hi = pd.Timestamp(ym.end_time)
    w = dd[(dd.index >= lo) & (dd.index <= hi)]
    if len(w) < 3:
        return ""
    fig, ax = plt.subplots(4, 1, figsize=(13, 12), sharex=True,
                           gridspec_kw={"height_ratios": [3, 1.2, 1.2, 1.2]},
                           facecolor="#12161c")
    for a in ax:
        a.set_facecolor("#12161c")
        a.tick_params(colors="#9fb0c4", labelsize=8)
        for s in a.spines.values():
            s.set_color("#2a3542")
        a.grid(alpha=0.15, color="#3a4552")
    # P1 fiyat + EMA + işlemler
    up = w.Close >= w.Open
    ax[0].vlines(w.index, w.Low, w.High, color="#7c8896", lw=0.7)
    ax[0].vlines(w.index[up], w.Open[up], w.Close[up], color="#26a69a", lw=3.5)
    ax[0].vlines(w.index[~up], w.Open[~up], w.Close[~up], color="#ef5350", lw=3.5)
    for p, col in [(20, "#f5c542"), (50, "#4C78A8"), (200, "#B279A2")]:
        s = di[f"ema{p}"].reindex(w.index)
        ax[0].plot(w.index, s, lw=1.1, color=col, label=f"EMA{p}")
    for _, t in trades_m.iterrows():
        col = "#26a69a" if t.r > 0 else "#ef5350"
        ax[0].scatter(t.entry, w.Close.asof(t.entry), marker="^", s=70,
                      color=col, edgecolors="white", linewidths=0.5, zorder=5)
        ax[0].scatter(t["exit"], w.Close.asof(t["exit"]), marker="v", s=70,
                      color=col, edgecolors="white", linewidths=0.5, zorder=5)
    ax[0].set_ylabel("Fiyat $", color="#9fb0c4", fontsize=9)
    ax[0].legend(fontsize=7, facecolor="#1a222c", labelcolor="#9fb0c4", loc="upper left")
    ax[0].set_title(f"{ym} — günlük fiyat, EMA ve işlemler (▲giriş ▼çıkış)",
                    color="#e6edf5", fontsize=11)
    # P2 MACD
    m = di["macd"].reindex(w.index); s_ = di["signal"].reindex(w.index)
    hst = di["hist"].reindex(w.index)
    ax[1].bar(w.index, hst, color=np.where(hst >= 0, "#26a69a", "#ef5350"), width=0.8)
    ax[1].plot(w.index, m, lw=1.1, color="#4C78A8", label="MACD")
    ax[1].plot(w.index, s_, lw=1.1, color="#f5c542", label="Sinyal")
    ax[1].axhline(0, color="#7c8896", lw=0.6)
    ax[1].set_ylabel("MACD (1G)", color="#9fb0c4", fontsize=9)
    ax[1].legend(fontsize=7, facecolor="#1a222c", labelcolor="#9fb0c4")
    # P3 volatilite
    atrp = (di["atr"] / dd.Close * 100).reindex(w.index)
    rv = (dd.Close.pct_change().rolling(20).std() * 100).reindex(w.index)
    ax[2].plot(w.index, atrp, lw=1.2, color="#E45756", label="ATR14 (%fiyat)")
    ax[2].plot(w.index, rv, lw=1.2, color="#54A24B", label="20g gerçekleşen vol %")
    ax[2].plot(w.index, di["bbw"].reindex(w.index), lw=1.0, color="#B279A2",
               ls="--", label="Bollinger genişliği %")
    ax[2].set_ylabel("Volatilite", color="#9fb0c4", fontsize=9)
    ax[2].legend(fontsize=7, facecolor="#1a222c", labelcolor="#9fb0c4")
    # P4 hacim + proxy CVD
    if "Volume" in dd.columns:
        ax[3].bar(w.index, w.Volume, color="#4C78A8", alpha=0.65, width=0.8, label="Hacim")
        ax3b = ax[3].twinx()
        ax3b.plot(w.index, di["cvd"].reindex(w.index), lw=1.4, color="#f5c542",
                  label="PROXY CVD (kümülatif)")
        ax3b.tick_params(colors="#9fb0c4", labelsize=8)
        ax3b.set_ylabel("proxy CVD", color="#f5c542", fontsize=8)
        ax[3].legend(fontsize=7, loc="upper left", facecolor="#1a222c", labelcolor="#9fb0c4")
        ax3b.legend(fontsize=7, loc="upper right", facecolor="#1a222c", labelcolor="#9fb0c4")
    ax[3].set_ylabel("Hacim", color="#9fb0c4", fontsize=9)
    ax[3].xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    fig.tight_layout()
    return b64(fig)


def mtf_table(data, inds, ts) -> str:
    """Ay sonunda TÜM zaman dilimlerinde gösterge anlık görüntüsü."""
    rows = []
    for tf in ["5m", "15m", "1h", "4h", "1d"]:
        if tf not in data:
            continue
        d, i = data[tf], inds[tf]
        sub = d[d.index <= ts]
        if len(sub) < 5:
            continue
        t = sub.index[-1]
        def g(k):
            try:
                v = i[k].asof(t)
                return float(v) if pd.notna(v) else np.nan
            except Exception:
                return np.nan
        c = float(sub.Close.iloc[-1])
        e9, e21, e50, e200 = g("ema9"), g("ema21"), g("ema50"), g("ema200")
        dizilim = ("BOĞA (9>21>50)" if e9 > e21 > e50 else
                   "AYI (9<21<50)" if e9 < e21 < e50 else "KARIŞIK")
        mac, sig, hst = g("macd"), g("signal"), g("hist")
        rows.append(
            f"<tr><td>{tf.upper()}</td><td>{c:,.2f}</td><td>{dizilim}</td>"
            f"<td>{e9:,.1f}</td><td>{e21:,.1f}</td><td>{e50:,.1f}</td>"
            f"<td>{e200:,.1f}</td>"
            f"<td class='{'p' if mac>sig else 'n'}'>{mac:+.2f}</td>"
            f"<td>{sig:+.2f}</td>"
            f"<td class='{'p' if hst>0 else 'n'}'>{hst:+.2f}</td>"
            f"<td>{g('rsi'):.0f}</td><td>{g('atr'):.2f}</td>"
            f"<td>{g('bbw'):.2f}%</td>"
            f"<td>{'200 ÜSTÜ' if c>e200 else '200 ALTI'}</td></tr>")
    return ("<table><thead><tr><th>TF</th><th>Kapanış</th><th>EMA dizilimi</th>"
            "<th>EMA9</th><th>EMA21</th><th>EMA50</th><th>EMA200</th>"
            "<th>MACD</th><th>Sinyal</th><th>Hist</th><th>RSI14</th>"
            "<th>ATR14</th><th>BB gen.</th><th>Konum</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")


CSS = """
body{background:#0e1218;color:#dfe6ee;font-family:-apple-system,'Segoe UI',Roboto,sans-serif;
     max-width:1200px;margin:auto;padding:22px;line-height:1.5}
h1{border-bottom:2px solid #3d5a80;padding-bottom:8px}
h2{color:#f5c542;margin-top:2.2em;border-bottom:1px solid #2a3542;padding-bottom:5px}
img{max-width:100%;border:1px solid #2a3542;border-radius:5px;margin:8px 0}
table{border-collapse:collapse;font-size:.8em;margin:8px 0;width:100%;
      font-variant-numeric:tabular-nums}
th,td{border:1px solid #2a3542;padding:3px 7px;text-align:right}
th{background:#1a222c;color:#9fc2e8}td:first-child,th:first-child{text-align:left}
.p{color:#26a69a}.n{color:#ef5350}
.kar{color:#26a69a;font-weight:bold}.zarar{color:#ef5350;font-weight:bold}
.note{font-size:.82em;color:#8ea0b5}
.haber{background:#1a222c;border-left:3px solid #f5c542;padding:8px 12px;margin:8px 0;
       border-radius:0 4px 4px 0}
.uyari{background:#2a1a1a;border-left:3px solid #ef5350;padding:10px 14px;margin:14px 0}
.toc{columns:4;font-size:.85em}.toc a{color:#7fb3e8;text-decoration:none;display:block}
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Ay ay kapsamlı piyasa+işlem raporu")
    ap.add_argument("--trades", default=None, help="işlem CSV (s,entry,exit,r)")
    ap.add_argument("--from", dest="frm", default=None, help="YYYY-MM")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Veri yükleniyor...")
    data = load_data()
    inds = {tf: ind(df) for tf, df in data.items()}
    dd, di = data["1d"], inds["1d"]

    # işlemler
    tp = args.trades
    if tp is None:
        for c in [ROOT / "reports/diagnostics/vip0_trades.csv",
                  Path("/tmp/claude-0/-home-user-erebb/"
                       "e6e0473b-7334-5192-859a-95f78b445430/scratchpad/vip0_trades.csv")]:
            if c.exists():
                tp = str(c); break
    if tp and Path(tp).exists():
        tr = pd.read_csv(tp, parse_dates=["entry", "exit"])
        tr = tr[tr.s != "london"] if "s" in tr.columns else tr
        print(f"  işlem: {len(tr)} ({tp})")
    else:
        tr = pd.DataFrame(columns=["s", "entry", "exit", "r"])
        print("  UYARI: işlem dosyası yok — yalnız piyasa panelleri üretilecek")
    if len(tr):
        tr["ym"] = tr["exit"].dt.to_period("M")

    months = pd.period_range(dd.index.min().to_period("M"),
                             dd.index.max().to_period("M"), freq="M")
    if args.frm:
        months = months[months >= pd.Period(args.frm, freq="M")]

    parts = []
    toc = []
    for ym in months:
        tm = tr[tr.ym == ym] if len(tr) else pd.DataFrame(columns=["s", "entry", "exit", "r"])
        R = tm.r.sum() if len(tm) else 0.0
        cls = "kar" if R > 0 else ("zarar" if R < 0 else "")
        toc.append(f'<a href="#m{ym}">{ym} <span class="{cls}">{R:+.1f}R</span></a>')
        print(f"  {ym} ...", flush=True)
        img = month_figure(dd, di, tm, ym)
        mstart, mend = pd.Timestamp(ym.start_time), pd.Timestamp(ym.end_time)
        w = dd[(dd.index >= mstart) & (dd.index <= mend)]
        if len(w) == 0:
            continue
        ret = (w.Close.iloc[-1] / w.Open.iloc[0] - 1) * 100
        vol = w.Close.pct_change().std() * 100
        rng = (w.High.max() - w.Low.min()) / w.Close.mean() * 100
        s = [f'<h2 id="m{ym}">{ym} — <span class="{cls}">{R:+.2f}R</span> '
             f'({len(tm)} işlem)</h2>']
        s.append(f'<p class="note">Altın aylık getiri <b>{ret:+.2f}%</b> | '
                 f'günlük vol <b>{vol:.2f}%</b> | aylık aralık <b>{rng:.1f}%</b> | '
                 f'kapanış <b>{w.Close.iloc[-1]:,.2f}$</b></p>')
        if str(ym) in NEWS:
            s.append(f'<div class="haber">📰 <b>Makro:</b> {NEWS[str(ym)]}'
                     f'<br><span class="note">(elle derlenmiş not — canlı takvim '
                     f'beslemesi değil)</span></div>')
        if img:
            s.append(f'<img src="data:image/png;base64,{img}" alt="{ym}">')
        s.append("<h3>Çok zaman dilimli gösterge anlık görüntüsü (ay sonu)</h3>")
        s.append(mtf_table(data, inds, mend))
        if len(tm):
            rows = []
            for st, g in tm.groupby("s"):
                rows.append(f"<tr><td>{st}</td><td>{len(g)}</td>"
                            f"<td>{(g.r>0).mean()*100:.0f}%</td>"
                            f"<td class='{'p' if g.r.sum()>0 else 'n'}'>{g.r.sum():+.2f}R</td>"
                            f"<td>{g.r.max():+.2f}R</td><td>{g.r.min():+.2f}R</td></tr>")
            s.append("<h3>Ayın işlemleri</h3><table><thead><tr><th>Strateji</th>"
                     "<th>N</th><th>WR</th><th>R</th><th>En iyi</th><th>En kötü</th>"
                     "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")
        else:
            s.append('<p class="note">Bu ay işlem yok.</p>')
        parts.append("\n".join(s))

    html = (f'<meta charset="utf-8"><title>XAUUSD Ay Ay Rapor</title>'
            f"<style>{CSS}</style><h1>XAUUSD — Ay Ay Piyasa ve İşlem Raporu</h1>"
            f'<p class="note">Dönem {months[0]} – {months[-1]} | '
            f'{len(months)} ay | veri: 5M/15M/1H/4H + günlük türetme</p>'
            '<div class="uyari"><b>Dürüstlük notları:</b><br>'
            '• <b>CVD PROXY\'dir</b> — veri setinde yalnız toplam hacim var, '
            'alıcı/satıcı (bid/ask) ayrımı YOK. Proxy = sign(Close−Open) × Hacim '
            'kümülatifi; gerçek emir-defteri CVD\'si değildir.<br>'
            '• <b>Haber notları elle derlenmiştir</b>, canlı ekonomik takvim '
            'beslemesi değildir; eksik veya yaklaşık olabilir.</div>'
            f'<div class="toc">{"".join(toc)}</div>'
            + "\n".join(parts))
    out = OUT_DIR / "aylik_rapor.html"
    out.write_text(html, encoding="utf-8")
    print(f"\nRapor → {out}  ({out.stat().st_size/1e6:.1f} MB)")
    print("BITTI")


if __name__ == "__main__":
    main()
