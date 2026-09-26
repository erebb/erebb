# -*- coding: utf-8 -*-
"""
SCALP AY/YIL RAPORU
====================
scripts/scalp_lab.py'nin ürettiği defterleri (reports/scalp__*.csv) alır,
her varyant için ay ay ve yıl yıl tablo çıkarır ve hepsini tek HTML'de
karşılaştırır.

Bakiye OLAY TABANLI (scripts/equity.py): pozisyon giriş anındaki
gerçekleşmiş bakiyeye göre boyutlanır, kâr/zarar çıkışta hesaba geçer.

İKİ RİSK SÜTUNU
  %1        — normal hesap kıyası (diğer raporlarla aynı ölçek)
  prop      — yüzen zarar dahil düşüşü %10 limitin %80'ine getiren risk
              oranıyla. Prop hesabında karşılaştırma ancak böyle adil olur:
              düşük düşüşlü bir varyant daha yüksek risk kullanabilir.

Çıktı: reports/SCALP_AY_YIL.html
Kullanım: python3 scripts/scalp_report.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "reports"
CAPITAL = 10_000.0

TR_AY = ["Oca", "Şub", "Mar", "Nis", "May", "Haz",
         "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]


def money(v: float, sign: bool = True) -> str:
    return format(v, "+,.0f" if sign else ",.0f").replace(",", ".")


def cls(v: float) -> str:
    return "pos" if v > 0 else ("neg" if v < 0 else "")


def load_all() -> dict:
    out = {}
    for p in sorted(OUT.glob("scalp__*.csv")):
        name = p.stem[len("scalp__"):]
        cost, _, variant = name.partition("__")
        d = pd.read_csv(p, parse_dates=["entry", "exit"])
        if not d.empty:
            out[(cost, variant)] = d
    return out


def enrich(d: pd.DataFrame, f: float) -> pd.DataFrame:
    from equity import event_equity
    r = event_equity(d, f, CAPITAL)
    d = d.copy()
    d["pnl"] = r["pnl"]
    d["bal"] = CAPITAL + pd.Series(r["pnl"]).cumsum()
    d["ym"] = d["exit"].dt.to_period("M")
    d["yr"] = d["exit"].dt.year
    return d, r


def agg(d: pd.DataFrame, key: str) -> pd.DataFrame:
    g = d.groupby(key)
    t = pd.DataFrame({
        "n": g.size(),
        "w": g["r"].apply(lambda s: int((s > 0).sum())),
        "r": g["r"].sum(),
        "pnl": g["pnl"].sum(),
        "bal": g["bal"].last(),
    })
    t["wr"] = 100.0 * t["w"] / t["n"]
    gw = g["r"].apply(lambda s: s[s > 0].sum())
    gl = g["r"].apply(lambda s: -s[s <= 0].sum())
    t["pf"] = np.where(gl > 0, gw / gl.replace(0, np.nan), np.inf)
    return t


def rows_for(d: pd.DataFrame) -> str:
    yr, mo = agg(d, "yr"), agg(d, "ym")
    out = []
    for y in sorted(yr.index):
        for label, m, ind in ([(str(y), yr.loc[y], False)]
                              + [("%s %d" % (TR_AY[p.month - 1], p.year),
                                  mo.loc[p], True)
                                 for p in mo.index if p.year == y]):
            pf = "∞" if not np.isfinite(m["pf"]) else "%.2f" % m["pf"]
            out.append(
                '<tr class="%s"><th>%s</th><td class="num">%d</td>'
                '<td class="num">%.0f%%</td><td class="num">%s</td>'
                '<td class="num %s">%+.1f</td><td class="num %s">%s $</td>'
                '<td class="num bal">%s $</td></tr>'
                % ("ind" if ind else "", label, m["n"], m["wr"], pf,
                   cls(m["r"]), m["r"], cls(m["pnl"]), money(m["pnl"]),
                   money(m["bal"], False)))
    return "".join(out)


HEAD = ("<tr><th>Dönem</th><th class='num'>İşlem</th><th class='num'>Kazanma</th>"
        "<th class='num'>PF</th><th class='num'>R</th><th class='num'>PnL</th>"
        "<th class='num'>Bakiye</th></tr>")


def build() -> str:
    from equity import event_equity
    from scalp_lab import risk_for_prop

    data = load_all()
    if not data:
        raise SystemExit("reports/scalp__*.csv bulunamadı — önce "
                         "scripts/scalp_lab.py koşturun")

    # ── özet: tüm varyantlar ────────────────────────────────────────────
    summ = []
    detail = []
    for (cost, variant), d in sorted(data.items()):
        e1 = event_equity(d, 0.01, CAPITAL)
        fp = risk_for_prop(d)
        ep = event_equity(d, fp, CAPITAL)
        isk = d.entry < pd.Timestamp("2025-01-11")
        summ.append(dict(cost=cost, variant=variant, n=len(d),
                         wr=100 * (d.r > 0).mean(), r=d.r.sum(),
                         is_r=d[isk].r.sum(), oos_r=d[~isk].r.sum(),
                         dur=d.dur_h.median(), stop=d.stop.median(),
                         b1=e1["final"], dd1=e1["dd"],
                         fp=fp * 100, bp=ep["final"]))
    S = pd.DataFrame(summ)
    srows = ""
    for _, x in S.iterrows():
        srows += ("<tr><td>%s</td><td>%s</td><td class='num'>%d</td>"
                  "<td class='num'>%.0f%%</td><td class='num %s'>%+.1f</td>"
                  "<td class='num'>%+.1f / %+.1f</td><td class='num'>%.1f s</td>"
                  "<td class='num'>%.1f $</td><td class='num'>%s $</td>"
                  "<td class='num'>%%%.1f</td><td class='num'>%%%.2f</td>"
                  "<td class='num'><b>%s $</b></td></tr>"
                  % (x["cost"], x["variant"], x["n"], x["wr"], cls(x["r"]),
                     x["r"], x["is_r"], x["oos_r"], x["dur"], x["stop"],
                     money(x["b1"], False), x["dd1"], x["fp"],
                     money(x["bp"], False)))

    # ── her varyant için ay/yıl tablosu ─────────────────────────────────
    for (cost, variant), d in sorted(data.items()):
        dd, r = enrich(d, 0.01)
        fp = risk_for_prop(d)
        dp, rp = enrich(d, fp)
        detail.append(
            '<section><h2>%s &nbsp;·&nbsp; <span class="cost">%s</span></h2>'
            '<p class="note">%d işlem · medyan süre %.1f saat · medyan stop '
            '%.1f $ · %%1 riskte %s $ (düşüş %%%.1f) · prop riski %%%.2f ile '
            '%s $</p>'
            '<div class="scroll"><table><thead>%s</thead><tbody>%s</tbody>'
            '</table></div></section>'
            % (variant, cost, len(d), d.dur_h.median(), d.stop.median(),
               money(r["final"], False), r["dd"], fp * 100,
               money(rp["final"], False), HEAD, rows_for(dd)))

    out = TPL
    for k, v in dict(summ=srows, detail="".join(detail),
                     nvar=str(len(data))).items():
        out = out.replace("@@" + k + "@@", v)
    return out


TPL = r"""<meta charset="utf-8">
<title>Scalp — Ay / Yıl Tabloları</title>
<style>
:root{--bg:#fbfaf8;--panel:#fff;--ink:#1c1a17;--dim:#6f6963;--line:#e7e2db;
 --gold:#9a7c18;--pos:#1e7d52;--neg:#c0384a;--shade:#f4f1ea}
@media (prefers-color-scheme:dark){:root{--bg:#0f1217;--panel:#171b22;
 --ink:#e9e6e1;--dim:#8b9199;--line:#252b34;--gold:#d8b23f;--pos:#3fbd80;
 --neg:#e8607a;--shade:#1b2029}}
:root[data-theme=dark]{--bg:#0f1217;--panel:#171b22;--ink:#e9e6e1;
 --dim:#8b9199;--line:#252b34;--gold:#d8b23f;--pos:#3fbd80;--neg:#e8607a;
 --shade:#1b2029}
:root[data-theme=light]{--bg:#fbfaf8;--panel:#fff;--ink:#1c1a17;--dim:#6f6963;
 --line:#e7e2db;--gold:#9a7c18;--pos:#1e7d52;--neg:#c0384a;--shade:#f4f1ea}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1120px;margin:0 auto;padding:44px 22px 80px;
 display:flex;flex-direction:column;gap:34px}
header{border-bottom:2px solid var(--gold);padding-bottom:18px}
h1{margin:0 0 5px;font:600 30px/1.15 Georgia,serif;letter-spacing:-.01em}
h2{margin:0 0 10px;font:600 18px/1.3 Georgia,serif;padding-bottom:8px;
 border-bottom:1px solid var(--line)}
h2 .cost{color:var(--dim);font:400 13px/1 sans-serif}
.note{color:var(--dim);font-size:13px;margin:0 0 10px}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:6px;
 background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:13px;min-width:620px}
th,td{padding:7px 12px;text-align:left;border-bottom:1px solid var(--line);
 white-space:nowrap}
thead th{background:var(--panel);color:var(--dim);font-size:11px;
 letter-spacing:.05em;text-transform:uppercase;font-weight:600;
 border-bottom:1px solid var(--gold);position:sticky;top:0}
.num{text-align:right;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
 font-variant-numeric:tabular-nums}
tbody tr:not(.ind){background:var(--shade)}
tbody tr:not(.ind) th{color:var(--gold);font-weight:600}
tr.ind th{padding-left:24px;font-weight:400;color:var(--dim)}
.pos{color:var(--pos)}.neg{color:var(--neg)}.bal{color:var(--dim)}
section{display:flex;flex-direction:column}
footer{color:var(--dim);font-size:12.5px;border-top:1px solid var(--line);
 padding-top:16px}
footer b{color:var(--ink)}
</style>
<div class="wrap">
<header>
  <h1>Scalp — Ay / Yıl Tabloları</h1>
  <div class="note">@@nvar@@ varyant · maliyet profilleri karşılaştırmalı ·
    bakiye olay tabanlı bileşik</div>
</header>

<section>
  <h2>Özet — tüm varyantlar</h2>
  <div class="scroll"><table><thead><tr>
    <th>Maliyet</th><th>Varyant</th><th class="num">İşlem</th>
    <th class="num">Kazanma</th><th class="num">R</th>
    <th class="num">IS / OOS</th><th class="num">Medyan süre</th>
    <th class="num">Medyan stop</th><th class="num">%1 bakiye</th>
    <th class="num">%1 düşüş</th><th class="num">Prop risk</th>
    <th class="num">Prop bakiye</th>
  </tr></thead><tbody>@@summ@@</tbody></table></div>
  <p class="note"><b>Prop risk</b> = yüzen zarar dahil düşüşü %10 limitin
    %80'ine getiren risk oranı. <b>Prop bakiye</b> o riskle 5 yıllık sonuç —
    prop hesabında varyantlar ancak böyle adil kıyaslanır: düşük düşüşlü bir
    varyant daha yüksek risk kullanabilir.</p>
</section>

@@detail@@

<footer>
  <b>Kaynak:</b> reports/scalp__*.csv (scripts/scalp_lab.py).
  Motor, gui ve config diske yazılmadan bellekte yamalanarak koşuldu.<br>
  <b>Bakiye:</b> olay tabanlı bileşik — pozisyon giriş anındaki gerçekleşmiş
  bakiyeye göre boyutlanır, kâr/zarar çıkışta hesaba geçer.<br>
  <b>UYARI:</b> scalp varyantları IS/OOS elemesinden GEÇMEDİ; kaba bir
  tarama sonucudur. Maliyet profilleri varsayımdır — gerçek broker
  spread/komisyon rakamlarıyla doğrulanmalıdır.
</footer>
</div>
"""


if __name__ == "__main__":
    p = OUT / "SCALP_AY_YIL.html"
    p.write_text(build(), encoding="utf-8")
    print("Rapor → %s (%.1f KB)" % (p, p.stat().st_size / 1024))
    print("BITTI")
