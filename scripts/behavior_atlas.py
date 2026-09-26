# -*- coding: utf-8 -*-
"""
XAUUSD DAVRANIS ATLASI — seans karakteri ve kosullu davranislar
================================================================
Tumdengelimsel metodolojinin ilk katmani: seanslarin HUYU cikarilir.
Uzerine HTF/makro beklenti bindirilecek.

SEANS TANIMLARI (kullanicinin tablosu, TR = UTC+3):
  Tokyo    03:00-09:30 TR -> 00:00-06:30 UTC   "yon belirleyici ama sakin"
  Londra   09:30-16:00 TR -> 06:30-13:00 UTC   "tuzaklar sik"
  New York 16:00-23:00 TR -> 13:00-20:00 UTC   "asil uclar burada"
  (bu tanimlarda seanslar ARDISIK, ortusme yok)

Olculen katmanlar
  1. Seans karakteri: range, gun payi, govde, verimlilik, yon dagilimi
  2. Ekstremum imzasi: seans ici konum + gunun ekstremumu hangi seansta
  3. Tuzak profili: nihai yonun tersine sapma, derinlik ve zamanlama
  4. Gecis matrisi: Tokyo->Londra->NY yon devamliligi
  5. Kosullu davranis: Tokyo=Londra iken NY ne yapiyor
  6. Haftanin gunu etkisi
  7. HTF bindirmesi: gunluk SMA200 trendine gore seans davranisi

Cikti: reports/DAVRANIS_ATLASI.html
"""
from __future__ import annotations
import base64, io, sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "reports"

SEANS = {"Tokyo": (0.0, 6.5), "Londra": (6.5, 13.0), "New York": (13.0, 20.0)}
RENK = {"Tokyo": "#c9a227", "Londra": "#4C78A8", "New York": "#c0384a"}
GUNLER = ["Pzt", "Sal", "Çar", "Per", "Cum"]


def wilson(k, n):
    if n == 0: return (0.0, 0.0)
    z = 1.959963985; p = k / n; d = 1 + z * z / n
    m = (p + z * z / (2 * n)) / d
    s = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * max(0, m - s), 100 * min(1, m + s))


def topla():
    from gui import _load_data
    from xauusd_fvg_engine_v10 import RegimeEngine
    df1h, df5, _ = _load_data()
    for d in (df1h, df5):
        d.index = pd.to_datetime(d.index)
        if getattr(d.index, "tz", None) is not None:
            d.index = d.index.tz_localize(None)
    df5 = df5[df5.index.dayofweek < 5]
    trend = RegimeEngine.daily_trend(df1h, period=200)     # NEDENSEL (shift 1)

    gun = df5.index.normalize()
    rows = []
    for d, gg in df5.groupby(gun):
        sa = gg.index.hour + gg.index.minute / 60.0
        gh, gl = float(gg.High.max()), float(gg.Low.min())
        grng = gh - gl
        if grng <= 0 or len(gg) < 100:
            continue
        r = {"gun": d, "hafta": d.dayofweek, "grng": grng,
             "gpct": 100 * grng / float(gg.Open.iloc[0]),
             "trend": float(trend.get(d, 0.0))}
        hi_t = float(sa[np.argmax(gg.High.values)])
        lo_t = float(sa[np.argmin(gg.Low.values)])
        for ad, (a, b) in SEANS.items():
            r["hi_" + ad] = a <= hi_t < b
            r["lo_" + ad] = a <= lo_t < b
        ok = True
        for ad, (a, b) in SEANS.items():
            s = gg[(sa >= a) & (sa < b)]
            if len(s) < 12: ok = False; break
            o, c = float(s.Open.iloc[0]), float(s.Close.iloc[-1])
            h, l = float(s.High.max()), float(s.Low.min())
            n = len(s)
            r[ad + "_yon"] = 1 if c > o else -1
            r[ad + "_rngpct"] = 100 * (h - l) / o
            r[ad + "_pay"] = 100 * (h - l) / grng
            r[ad + "_govde"] = abs(c - o) / (h - l) if h > l else 0.0
            yol = float(s.Close.diff().abs().sum())
            r[ad + "_er"] = abs(c - o) / yol if yol > 0 else 0.0
            ekst = np.concatenate([[np.argmax(s.High.values)],
                                   [np.argmin(s.Low.values)]]) / max(n - 1, 1)
            r[ad + "_ekst_konum"] = float(np.mean(ekst))
            yon = r[ad + "_yon"]
            ters = (o - l) if yon == 1 else (h - o)
            leh = (h - o) if yon == 1 else (o - l)
            r[ad + "_tuzak"] = 100 * max(0.0, ters) / grng
            r[ad + "_asil"] = 100 * max(0.0, leh) / grng
            arr = s.Low.values if yon == 1 else s.High.values
            j = int(np.argmin(arr)) if yon == 1 else int(np.argmax(arr))
            r[ad + "_tuzak_saat"] = float((s.index[j] - s.index[0]).total_seconds() / 3600)
        if ok: rows.append(r)
    return pd.DataFrame(rows)


def png(fig):
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=110, bbox_inches="tight",
                facecolor="none", transparent=True)
    plt.close(fig)
    return base64.b64encode(b.getvalue()).decode()


def _sk(ax, yl=""):
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    for s in ("left", "bottom"): ax.spines[s].set_color("#8b9199")
    ax.tick_params(colors="#8b9199", labelsize=8)
    if yl: ax.set_ylabel(yl, color="#8b9199", fontsize=9)
    ax.grid(axis="y", color="#8b9199", alpha=.18, lw=.6); ax.set_axisbelow(True)


def ch_gunici(d):
    """Gun ici ekstremum yogunlugu — saat saat."""
    from gui import _load_data
    fig, ax = plt.subplots(figsize=(11, 3.2))
    kova = np.zeros(24)
    for ad, (a, b) in SEANS.items():
        ax.axvspan(a, b, color=RENK[ad], alpha=.10)
        ax.text((a + b) / 2, 0.94, ad, transform=ax.get_xaxis_transform(),
                ha="center", fontsize=9, color=RENK[ad], weight="bold")
    for ad in SEANS:
        pass
    # saat bazli yogunluk defterden degil, seans paylarindan cizilir
    paylar = [(ad, 100 * (d["hi_" + ad] | d["lo_" + ad]).mean()) for ad in SEANS]
    for ad, (a, b) in SEANS.items():
        v = 100 * (d["hi_" + ad] | d["lo_" + ad]).mean()
        ax.bar((a + b) / 2, v, width=(b - a) * .8, color=RENK[ad], alpha=.85)
        ax.text((a + b) / 2, v + 1.5, "%%%.1f" % v, ha="center", fontsize=9,
                color=RENK[ad], weight="bold")
    ax.set_xlim(0, 24); ax.set_xticks(range(0, 25, 2))
    ax.set_xlabel("UTC saat", color="#8b9199", fontsize=9)
    _sk(ax, "günün ekstremumunu içerme oranı")
    return png(fig)


def ch_karakter(d):
    fig, axes = plt.subplots(1, 3, figsize=(11, 3))
    for ax, (kol, baslik) in zip(axes, [("rngpct", "medyan range %"),
                                        ("pay", "günün range payı %"),
                                        ("er", "verimlilik (ER)")]):
        v = [d[ad + "_" + kol].median() for ad in SEANS]
        ax.bar(list(SEANS), v, color=[RENK[a] for a in SEANS], alpha=.85)
        for i, x in enumerate(v):
            ax.text(i, x, "%.2f" % x, ha="center", va="bottom", fontsize=8,
                    color="#8b9199")
        ax.set_title(baslik, fontsize=9, color="#8b9199")
        _sk(ax)
        ax.tick_params(axis="x", labelsize=8)
    plt.tight_layout()
    return png(fig)


def tbl(head, rows):
    h = "".join("<th>%s</th>" % x for x in head)
    b = "".join("<tr>" + "".join("<td>%s</td>" % c for c in r) + "</tr>"
                for r in rows)
    return ('<div class="scroll"><table><thead><tr>%s</tr></thead>'
            "<tbody>%s</tbody></table></div>" % (h, b))


def build():
    d = topla()
    n = len(d)
    P = {"n": str(n), "ilk": str(d.gun.iloc[0].date()), "son": str(d.gun.iloc[-1].date())}

    # 1 — karakter
    P["t_karakter"] = tbl(
        ["Seans", "UTC", "Medyan range%", "Gün payı%", "Gövde", "Verimlilik",
         "Yükseliş oranı"],
        [[ad, "%02d:%02d–%02d:%02d" % (int(a), (a % 1) * 60, int(b), (b % 1) * 60),
          "%.2f" % d[ad + "_rngpct"].median(),
          "%.1f" % d[ad + "_pay"].median(),
          "%.2f" % d[ad + "_govde"].median(),
          "%.3f" % d[ad + "_er"].median(),
          "%%%.1f" % (100 * (d[ad + "_yon"] > 0).mean())]
         for ad, (a, b) in SEANS.items()])
    P["ch_karakter"] = ch_karakter(d)

    # 2 — ekstremum
    P["ch_gunici"] = ch_gunici(d)
    P["t_ekst"] = tbl(
        ["Seans", "Günün yükseği", "Günün düşüğü", "En az biri",
         "Seans içi konum"],
        [[ad, "%%%.1f" % (100 * d["hi_" + ad].mean()),
          "%%%.1f" % (100 * d["lo_" + ad].mean()),
          "<b>%%%.1f</b>" % (100 * (d["hi_" + ad] | d["lo_" + ad]).mean()),
          "%.2f  (0=baş, 1=son)" % d[ad + "_ekst_konum"].median()]
         for ad in SEANS])

    # 3 — tuzak
    P["t_tuzak"] = tbl(
        ["Seans", "Tuzak derinliği (medyan)", "Asıl hareket (medyan)",
         "Oran", "Tuzak zamanı (medyan)", "≥%5 tuzak oranı"],
        [[ad, "%%%.1f" % d[ad + "_tuzak"].median(),
          "%%%.1f" % d[ad + "_asil"].median(),
          "%.1f×" % (d[ad + "_asil"].median() / max(d[ad + "_tuzak"].median(), .01)),
          "%.2f saat" % d[ad + "_tuzak_saat"].median(),
          "%%%.1f" % (100 * (d[ad + "_tuzak"] >= 5).mean())]
         for ad in SEANS])

    # 4 — gecis matrisi
    rows = []
    for a, b in (("Tokyo", "Londra"), ("Londra", "New York"),
                 ("Tokyo", "New York")):
        k = int((d[a + "_yon"] == d[b + "_yon"]).sum())
        lo, hi = wilson(k, n)
        rows.append([a + " → " + b, "%d/%d" % (k, n), "<b>%%%.1f</b>" % (100 * k / n),
                     "[%%%.1f–%%%.1f]" % (lo, hi)])
    P["t_gecis"] = tbl(["Geçiş", "Sayı", "Aynı yön", "%95 aralık"], rows)

    # 5 — kosullu
    ayni = d[d.Tokyo_yon == d.Londra_yon]; fark = d[d.Tokyo_yon != d.Londra_yon]
    rows = []
    for ad, sub in (("Tokyo = Londra", ayni), ("Tokyo ≠ Londra", fark)):
        k = int((sub.Londra_yon == sub["New York_yon"]).sum())
        lo, hi = wilson(k, len(sub))
        rows.append([ad, "%d gün (%%%.1f)" % (len(sub), 100 * len(sub) / n),
                     "<b>%%%.1f</b>" % (100 * k / len(sub)),
                     "[%%%.1f–%%%.1f]" % (lo, hi),
                     "%%%.1f" % (100 * (sub["New York_tuzak"] >= 5).mean()),
                     "%%%.1f" % (100 * (sub.gpct > d.gpct.median()).mean())])
    P["t_kosullu"] = tbl(["Durum", "Gün", "NY, Londra yönünde", "%95 aralık",
                          "NY'de ≥%5 tuzak", "Geniş gün oranı"], rows)

    # 6 — haftanin gunu
    rows = []
    for i, g in enumerate(GUNLER):
        s = d[d.hafta == i]
        if s.empty: continue
        rows.append([g, len(s), "%.2f" % s.gpct.median(),
                     "%%%.1f" % (100 * (s["hi_New York"] | s["lo_New York"]).mean()),
                     "%%%.1f" % (100 * (s["New York_tuzak"] >= 5).mean()),
                     "%%%.1f" % (100 * (s.Londra_yon == s["New York_yon"]).mean())])
    P["t_hafta"] = tbl(["Gün", "Sayı", "Günlük range%", "Ekstremum NY'de",
                        "NY tuzak ≥%5", "Londra=NY"], rows)

    # 7 — HTF bindirmesi
    rows = []
    for ad, sub in (("Günlük trend YUKARI", d[d.trend > 0]),
                    ("Günlük trend AŞAĞI", d[d.trend < 0])):
        if sub.empty: continue
        rows.append([ad, len(sub), "%.2f" % sub.gpct.median(),
                     "%%%.1f" % (100 * (sub["New York_yon"] > 0).mean()),
                     "%%%.1f" % (100 * (sub.Londra_yon == sub["New York_yon"]).mean()),
                     "%%%.1f" % (100 * (sub["New York_tuzak"] >= 5).mean()),
                     "%%%.1f" % (100 * (sub["hi_New York"] | sub["lo_New York"]).mean())])
    P["t_htf"] = tbl(["HTF durumu", "Gün", "Range%", "NY yukarı kapanış",
                      "Londra=NY", "NY tuzak ≥%5", "Ekstremum NY'de"], rows)

    out = TPL
    for k, v in P.items():
        out = out.replace("@@" + k + "@@", str(v))
    return out


TPL = r"""<meta charset="utf-8">
<title>XAUUSD Davranış Atlası</title>
<style>
:root{--bg:#fbfaf8;--panel:#fff;--ink:#1c1a17;--dim:#6f6963;--line:#e7e2db;
 --gold:#9a7c18;--pos:#1e7d52;--neg:#c0384a;--shade:#f4f1ea;--quote:#fdf8e8}
@media(prefers-color-scheme:dark){:root{--bg:#0f1217;--panel:#171b22;
 --ink:#e9e6e1;--dim:#8b9199;--line:#252b34;--gold:#d8b23f;--pos:#3fbd80;
 --neg:#e8607a;--shade:#1b2029;--quote:#1e1c14}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:15.5px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1020px;margin:0 auto;padding:44px 22px 80px;
 display:flex;flex-direction:column;gap:38px}
header{border-bottom:2px solid var(--gold);padding-bottom:18px}
h1{margin:0 0 5px;font:600 31px/1.15 Georgia,serif;letter-spacing:-.01em}
.lede{color:var(--dim);font-size:13.5px}
section{display:flex;flex-direction:column;gap:13px}
h2{margin:0;font:600 20px/1.25 Georgia,serif;padding-bottom:8px;
 border-bottom:1px solid var(--line)}
h2 .no{color:var(--gold);font:400 13px/1 ui-monospace,monospace;margin-right:9px}
p{margin:0}
.key{background:var(--quote);border-left:3px solid var(--gold);
 padding:13px 17px;border-radius:0 4px 4px 0;font-size:14.5px}
.key b{color:var(--gold)}
.note{color:var(--dim);font-size:13px}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:6px;
 background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:13.5px;min-width:520px}
th,td{padding:8px 13px;text-align:left;border-bottom:1px solid var(--line);
 white-space:nowrap}
thead th{background:var(--panel);color:var(--dim);font-size:11px;
 letter-spacing:.05em;text-transform:uppercase;font-weight:600;
 border-bottom:1px solid var(--gold)}
td:nth-child(n+2){font-family:ui-monospace,Menlo,monospace;
 font-variant-numeric:tabular-nums}
tbody tr:hover td{background:var(--shade)}
img{width:100%;height:auto;display:block;border-radius:6px}
ul{margin:0;padding-left:20px}li{margin:5px 0}
footer{color:var(--dim);font-size:12.5px;border-top:1px solid var(--line);
 padding-top:16px}
footer b{color:var(--ink)}
</style>
<div class="wrap">
<header>
  <h1>XAUUSD Davranış Atlası</h1>
  <div class="lede">@@n@@ iş günü · @@ilk@@ – @@son@@ · seans pencereleri
    XAU_Atlas tanımı (TR = UTC+3)</div>
</header>

<section>
  <h2><span class="no">01</span>Seans karakteri</h2>
  @@t_karakter@@
  <img src="data:image/png;base64,@@ch_karakter@@" alt="Seans karakteri">
  <p class="note"><b>Verimlilik (ER)</b> = |kapanış−açılış| / toplam yol.
    1'e yakın = temiz trend, 0'a yakın = zikzak. <b>Gövde</b> =
    |kapanış−açılış| / (yüksek−düşük).</p>
</section>

<section>
  <h2><span class="no">02</span>Ekstremum imzası — günün kararı nerede veriliyor</h2>
  <img src="data:image/png;base64,@@ch_gunici@@" alt="Ekstremum dağılımı">
  @@t_ekst@@
</section>

<section>
  <h2><span class="no">03</span>Tuzak profili</h2>
  <p class="note">Tuzak = seansın <b>nihai yönünün tersine</b> en derin sapma.
    Değerler günlük range'in yüzdesi.</p>
  @@t_tuzak@@
</section>

<section>
  <h2><span class="no">04</span>Geçiş matrisi — yön devamlılığı</h2>
  @@t_gecis@@
</section>

<section>
  <h2><span class="no">05</span>Koşullu davranış — Tokyo ve Londra hizalıyken</h2>
  @@t_kosullu@@
</section>

<section>
  <h2><span class="no">06</span>Haftanın günü</h2>
  @@t_hafta@@
</section>

<section>
  <h2><span class="no">07</span>HTF bindirmesi — günlük SMA200 trendine göre</h2>
  <p class="note">Tümdengelimin ikinci katmanı: seans huyu, makro yöne göre
    değişiyor mu? Trend göstergesi nedensel (shift 1).</p>
  @@t_htf@@
</section>

<footer>
  <b>Yöntem:</b> 5 dakikalık XAUUSD verisi, hafta sonu ve &lt;12 barlık
  seanslar elenmiştir. Oranlarda %95 Wilson güven aralığı verilir.<br>
  <b>Nedensellik:</b> HTF trend göstergesi shift(1) ile hesaplanır; seans
  istatistikleri tamamlanmış seanslardan alınır.<br>
  <b>Üretici:</b> scripts/behavior_atlas.py
</footer>
</div>
"""


if __name__ == "__main__":
    p = OUT / "DAVRANIS_ATLASI.html"
    p.write_text(build(), encoding="utf-8")
    print("Atlas → %s (%.0f KB)" % (p, p.stat().st_size / 1024))
    print("BITTI")
