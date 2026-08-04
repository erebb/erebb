# -*- coding: utf-8 -*-
"""
AY AY / YIL YIL PnL RAPORU
===========================
Son sistemin (config/default.json preset'leri) tam defteri:
  • Yıl yıl: işlem sayısı, W/L/BE, WR, R, $ PnL, yıl sonu bakiye
  • Ay ay: aynı kırılım, yıl yıl gruplanmış
  • Strateji × yıl matrisi
  • Özkaynak eğrisi + aylık bar grafiği

Bakiye modeli: her işlem giriş anındaki bakiyenin %1'i risk (bileşik).
  bal *= (1 + 0.01 × R)     — 10.000$ → 35.991$ ile birebir doğrulandı.
KOMİSYON DAHİL: R değerleri motordan gelir, spread+slippage+taker/maker
ücretleri işlem başına bir kez düşülmüş hâldedir.

Girdi : reports/ay_derin_islemler.csv (scripts/month_deepdive.py üretir)
Çıktı : reports/PNL_RAPORU.html
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports"
LEDGER = OUT / "ay_derin_islemler.csv"
CAPITAL = 10_000.0
RISK_FRAC = 0.01

POS, NEG, GOLD = "#2e9e6b", "#d1495b", "#c9a227"


# ─────────────────────────────── defter ─────────────────────────────────────

def load() -> pd.DataFrame:
    d = pd.read_csv(LEDGER)
    d["entry"] = pd.to_datetime(d["entry"])
    d["exit"] = pd.to_datetime(d["exit"])
    d = d[d["reason"] != "open"].copy()
    d = d.sort_values("exit").reset_index(drop=True)

    # bileşik bakiye: risk = giriş anındaki bakiyenin %1'i
    bal = CAPITAL
    op, pnl, cl = [], [], []
    for r in d["r"]:
        op.append(bal)
        p = RISK_FRAC * bal * r
        bal += p
        pnl.append(p)
        cl.append(bal)
    d["bal_open"], d["pnl"], d["bal"] = op, pnl, cl
    d["ym"] = d["exit"].dt.to_period("M")
    d["yr"] = d["exit"].dt.year
    d["res"] = np.where(d["r"] > 0.01, "W", np.where(d["r"] < -0.01, "L", "BE"))
    return d


def agg(d: pd.DataFrame, key: str) -> pd.DataFrame:
    g = d.groupby(key)
    t = pd.DataFrame({
        "n": g.size(),
        "w": g["res"].apply(lambda s: (s == "W").sum()),
        "l": g["res"].apply(lambda s: (s == "L").sum()),
        "be": g["res"].apply(lambda s: (s == "BE").sum()),
        "r": g["r"].sum(),
        "pnl": g["pnl"].sum(),
        "bal": g["bal"].last(),
    })
    t["wr"] = 100.0 * t["w"] / t["n"]
    gross_w = g.apply(lambda x: x.loc[x["r"] > 0, "r"].sum(), include_groups=False)
    gross_l = g.apply(lambda x: -x.loc[x["r"] <= 0, "r"].sum(), include_groups=False)
    t["pf"] = np.where(gross_l > 0, gross_w / gross_l.replace(0, np.nan), np.inf)
    t["ret"] = 100.0 * t["pnl"] / (t["bal"] - t["pnl"])
    return t


# ─────────────────────────────── grafik ─────────────────────────────────────

def png(fig) -> str:
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=110, bbox_inches="tight",
                facecolor="none", transparent=True)
    plt.close(fig)
    return base64.b64encode(b.getvalue()).decode()


def chart_equity(d: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(11, 3.6))
    ax.plot(d["exit"], d["bal"], color=GOLD, lw=1.8)
    ax.fill_between(d["exit"], CAPITAL, d["bal"], color=GOLD, alpha=0.13)
    peak = d["bal"].cummax()
    dd = 100 * (d["bal"] / peak - 1)
    i = int(dd.idxmin())
    ax.annotate("maks. düşüş %%%.1f" % abs(dd.min()),
                xy=(d["exit"][i], d["bal"][i]), xytext=(0, -34),
                textcoords="offset points", ha="center", fontsize=8,
                color=NEG, arrowprops=dict(arrowstyle="->", color=NEG, lw=1))
    ax.axhline(CAPITAL, color="#888", lw=0.8, ls="--")
    ax.set_ylabel("bakiye ($)", fontsize=9)
    _skin(ax)
    return png(fig)


def chart_months(t: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(11, 3.2))
    x = [p.to_timestamp() for p in t.index]
    ax.bar(x, t["pnl"], width=22,
           color=[POS if v > 0 else NEG for v in t["pnl"]])
    ax.axhline(0, color="#888", lw=0.8)
    ax.set_ylabel("aylık PnL ($)", fontsize=9)
    _skin(ax)
    return png(fig)


def _skin(ax) -> None:
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#9a9a9a")
    ax.tick_params(colors="#9a9a9a", labelsize=8)
    ax.yaxis.label.set_color("#9a9a9a")
    ax.grid(axis="y", color="#9a9a9a", alpha=0.18, lw=0.6)
    ax.set_axisbelow(True)


# ─────────────────────────────── html ───────────────────────────────────────

TR_AY = ["Oca", "Şub", "Mar", "Nis", "May", "Haz",
         "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]


def money(v: float) -> str:
    """+12.345 biçimi (binlik ayracı nokta). %-formatı ',' bayrağını
    desteklemediği için format() ile."""
    return format(v, "+,.0f").replace(",", ".")


def cls(v: float) -> str:
    return "pos" if v > 0 else ("neg" if v < 0 else "zero")


def row(label: str, m, indent: bool = False) -> str:
    pf = "∞" if not np.isfinite(m["pf"]) else "%.2f" % m["pf"]
    return (
        '<tr class="%s"><th>%s</th>'
        '<td class="num">%d</td>'
        '<td class="num sub">%d / %d / %d</td>'
        '<td class="num">%.1f%%</td>'
        '<td class="num">%s</td>'
        '<td class="num %s">%+.1f</td>'
        '<td class="num %s">%s $</td>'
        '<td class="num %s">%+.1f%%</td>'
        '<td class="num bal">%s $</td></tr>'
        % ("ind" if indent else "", label, m["n"], m["w"], m["l"], m["be"],
           m["wr"], pf, cls(m["r"]), m["r"], cls(m["pnl"]), money(m["pnl"]),
           cls(m["ret"]), m["ret"], format(m["bal"], ",.0f").replace(",", "."))
    )


HEAD = ("<tr><th>Dönem</th><th class='num'>İşlem</th>"
        "<th class='num'>K / Z / BE</th><th class='num'>Kazanma</th>"
        "<th class='num'>PF</th><th class='num'>R</th>"
        "<th class='num'>PnL</th><th class='num'>Getiri</th>"
        "<th class='num'>Bakiye</th></tr>")


def build() -> str:
    d = load()
    yr, mo = agg(d, "yr"), agg(d, "ym")
    fin = d["bal"].iloc[-1]
    yrs = (d["exit"].iloc[-1] - d["exit"].iloc[0]).days / 365.25
    cagr = 100 * ((fin / CAPITAL) ** (1 / yrs) - 1)
    peak = d["bal"].cummax()
    mdd = abs((d["bal"] / peak - 1).min()) * 100
    gw, gl = d[d.r > 0].r.sum(), -d[d.r <= 0].r.sum()

    kpi = [("Toplam PnL", money(fin - CAPITAL) + " $", cls(fin - CAPITAL)),
           ("Son bakiye", format(fin, ",.0f").replace(",", ".") + " $", "zero"),
           ("Toplam getiri", "+%.1f%%" % (100 * (fin / CAPITAL - 1)), "pos"),
           ("Yıllık bileşik", "+%.1f%%" % cagr, "pos"),
           ("İşlem", "%d" % len(d), "zero"),
           ("Kazanma oranı", "%.1f%%" % (100 * (d.r > 0).mean()), "zero"),
           ("Profit factor", "%.2f" % (gw / gl), "zero"),
           ("Maks. düşüş", "%.1f%%" % mdd, "neg")]
    kpi_html = "".join(
        '<div class="kpi"><span class="k">%s</span>'
        '<span class="v %s">%s</span></div>' % (a, c, b) for a, b, c in kpi)

    # yıl + ay tablosu (ay satırları yılın altında girintili)
    rows = []
    for y in sorted(yr.index):
        rows.append(row(str(y), yr.loc[y]))
        for p in [q for q in mo.index if q.year == y]:
            rows.append(row("%s %d" % (TR_AY[p.month - 1], p.year),
                            mo.loc[p], indent=True))

    # strateji × yıl
    sy = d.pivot_table(index="s", columns="yr", values="pnl", aggfunc="sum")
    sn = d.pivot_table(index="s", columns="yr", values="r", aggfunc="size")
    sh = ["<tr><th>Strateji</th>"
          + "".join("<th class='num'>%d</th>" % c for c in sy.columns)
          + "<th class='num'>Toplam</th></tr>"]
    for s in sy.index:
        cells = ""
        for c in sy.columns:
            v, n = sy.loc[s, c], sn.loc[s, c]
            cells += ("<td class='num'>—</td>" if pd.isna(v) else
                      "<td class='num %s'>%s $<span class='sub'> %d</span></td>"
                      % (cls(v), money(v), n))
        tot = sy.loc[s].sum()
        sh.append("<tr><th>%s</th>%s<td class='num %s'><b>%s $</b>"
                  "<span class='sub'> %d</span></td></tr>"
                  % (s, cells, cls(tot), money(tot), int(sn.loc[s].sum())))

    pos_m = int((mo["pnl"] > 0).sum())
    note = ("%d ayın %d'i pozitif (%%%.0f) · %d yılın %d'i pozitif"
            % (len(mo), pos_m, 100 * pos_m / len(mo),
               len(yr), int((yr["pnl"] > 0).sum())))

    # CSS'te % (width:100%, color-mix 8%) bol olduğu için %-formatlama YERİNE
    # @@token@@ değişimi kullanılır — kaçış hatası imkânsız hâle gelir.
    out = TPL
    for k, v in dict(kpi=kpi_html, head=HEAD, rows="".join(rows),
                     strat="".join(sh), note=note,
                     eq=chart_equity(d), mb=chart_months(mo),
                     first=d["exit"].iloc[0].strftime("%d.%m.%Y"),
                     last=d["exit"].iloc[-1].strftime("%d.%m.%Y")).items():
        out = out.replace("@@%s@@" % k, str(v))
    return out


TPL = """<meta charset="utf-8">
<title>XAUUSD — Ay Ay / Yıl Yıl PnL</title>
<style>
:root{
  --bg:#fbfaf8; --panel:#fff; --ink:#1c1a17; --dim:#77706a; --line:#e6e1da;
  --gold:#a8871c; --pos:#1e7d52; --neg:#c0384a; --shade:#f3f0ea;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0e1116; --panel:#161a21; --ink:#e9e6e1; --dim:#8b9199; --line:#242a33;
  --gold:#d8b23f; --pos:#3fbd80; --neg:#e8607a; --shade:#1b2029;}}
:root[data-theme=dark]{
  --bg:#0e1116; --panel:#161a21; --ink:#e9e6e1; --dim:#8b9199; --line:#242a33;
  --gold:#d8b23f; --pos:#3fbd80; --neg:#e8607a; --shade:#1b2029;}
:root[data-theme=light]{
  --bg:#fbfaf8; --panel:#fff; --ink:#1c1a17; --dim:#77706a; --line:#e6e1da;
  --gold:#a8871c; --pos:#1e7d52; --neg:#c0384a; --shade:#f3f0ea;}

*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:44px 22px 80px;
  display:flex;flex-direction:column;gap:34px}

header{border-bottom:2px solid var(--gold);padding-bottom:18px}
h1{margin:0 0 4px;font:600 30px/1.15 Georgia,"Times New Roman",serif;
  letter-spacing:-.01em;text-wrap:balance}
.sub2{color:var(--dim);font-size:13px}
.tag{display:inline-block;margin-top:10px;padding:3px 9px;border-radius:3px;
  background:var(--shade);border:1px solid var(--line);color:var(--dim);
  font-size:11px;letter-spacing:.06em;text-transform:uppercase}

.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));
  gap:1px;background:var(--line);border:1px solid var(--line);border-radius:6px;
  overflow:hidden}
.kpi{background:var(--panel);padding:14px 16px;display:flex;
  flex-direction:column;gap:5px}
.kpi .k{font-size:11px;letter-spacing:.05em;text-transform:uppercase;
  color:var(--dim)}
.kpi .v{font:600 21px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
  font-variant-numeric:tabular-nums}

h2{margin:0 0 12px;font:600 15px/1.3 Georgia,serif;letter-spacing:.02em;
  padding-bottom:7px;border-bottom:1px solid var(--line)}
h2 span{color:var(--dim);font:400 12px/1 sans-serif;margin-left:9px}

.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:6px;
  background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:13px;min-width:760px}
th,td{padding:7px 12px;text-align:left;border-bottom:1px solid var(--line);
  white-space:nowrap}
thead th{position:sticky;top:0;background:var(--panel);color:var(--dim);
  font-size:11px;letter-spacing:.05em;text-transform:uppercase;font-weight:600;
  border-bottom:1px solid var(--gold)}
tbody th{font-weight:600}
.num{text-align:right;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  font-variant-numeric:tabular-nums}
tbody tr:not(.ind){background:var(--shade)}
tbody tr:not(.ind) th{color:var(--gold);font-size:14px}
tr.ind th{padding-left:26px;font-weight:400;color:var(--dim)}
tr:hover td,tr:hover th{background:color-mix(in srgb,var(--gold) 8%,transparent)}
.pos{color:var(--pos)} .neg{color:var(--neg)} .zero{color:var(--ink)}
.sub{color:var(--dim);font-size:11px}
.bal{color:var(--dim)}
img{width:100%;height:auto;display:block}
footer{color:var(--dim);font-size:12px;border-top:1px solid var(--line);
  padding-top:16px}
footer b{color:var(--ink)}
</style>
<div class="wrap">
<header>
  <h1>XAUUSD — Ay Ay / Yıl Yıl Kâr-Zarar</h1>
  <div class="sub2">@@first@@ – @@last@@ · 10.000 $ başlangıç · işlem başına
    bakiyenin %1'i risk (bileşik)</div>
  <div class="tag">komisyon · spread · slippage dahil</div>
</header>

<section class="kpis">@@kpi@@</section>

<section>
  <h2>Özkaynak eğrisi</h2>
  <img src="data:image/png;base64,@@eq@@" alt="Özkaynak eğrisi">
</section>

<section>
  <h2>Aylık PnL</h2>
  <img src="data:image/png;base64,@@mb@@" alt="Aylık PnL">
</section>

<section>
  <h2>Yıl yıl / ay ay <span>@@note@@</span></h2>
  <div class="scroll"><table>
    <thead>@@head@@</thead><tbody>@@rows@@</tbody>
  </table></div>
</section>

<section>
  <h2>Strateji × yıl <span>hücrede PnL, küçük rakam işlem sayısı</span></h2>
  <div class="scroll"><table><tbody>@@strat@@</tbody></table></div>
</section>

<footer>
  <b>Bakiye modeli:</b> her işlem, giriş anındaki bakiyenin %1'ini riske atar
  (bileşik). Bir işlemin dolar sonucu = 0,01 × o andaki bakiye × R.<br>
  <b>Maliyetler:</b> R değerleri motordan gelir; spread 0,30 $, slippage
  0,05 $ ve BingX VIP 0 ücretleri (taker %0,0500 / maker %0,0200) işlem
  başına <b>bir kez</b> düşülmüş hâldedir. Tablodaki hiçbir rakam brüt değil.<br>
  <b>Kaynak:</b> reports/ay_derin_islemler.csv — config/default.json
  preset'leriyle koşulan tam defter.
</footer>
</div>
"""


if __name__ == "__main__":
    p = OUT / "PNL_RAPORU.html"
    p.write_text(build(), encoding="utf-8")
    print("Rapor → %s (%.1f KB)" % (p, p.stat().st_size / 1024))
